"""
Data preparation API endpoints for training
"""

import logging
import asyncio
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from brain.training.data_preparation.pipeline import DataPreparationPipeline, BatchProcessor
from brain.training.data_preparation.base import DataSource

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class DataSourceConfig(BaseModel):
    """Configuration for a data source"""
    type: str = Field(..., description="Type: url, sitemap, documentation, api_doc, changes")
    location: str = Field(..., description="URL, file path, or API endpoint")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    version: Optional[str] = Field(default=None, description="Version information")


class DataPrepConfig(BaseModel):
    """Configuration for data preparation pipeline"""
    collector_type: str = Field(default="web", description="web, documentation, api, changes")
    preprocessor_type: str = Field(default="markdown", description="drupal, code, markdown, default")
    formatter_type: str = Field(default="jsonl", description="jsonl, instruction, conversation, delta")

    # Collector config
    rate_limit: float = Field(default=1.0, description="Seconds between requests")
    max_depth: int = Field(default=3, description="Maximum crawl depth")
    follow_links: bool = Field(default=False, description="Follow links in pages")
    max_pages: int = Field(default=100, description="Maximum pages to collect")
    cache_hours: int = Field(default=24, description="Hours to cache collected data")

    # Preprocessor config
    target_version: Optional[str] = Field(default=None, description="Target version for delta training")
    enable_versioning: bool = Field(default=False, description="Enable version-aware processing")
    language: Optional[str] = Field(default=None, description="Programming language for code preprocessing")
    framework: Optional[str] = Field(default=None, description="Framework name for code preprocessing")

    # Formatter config
    max_length: int = Field(default=2048, description="Maximum token length")
    include_metadata: bool = Field(default=True, description="Include metadata in output")
    instruction_templates: Optional[Dict[str, str]] = Field(default=None, description="Custom instruction templates")


class PrepareDataRequest(BaseModel):
    """Request to prepare training data"""
    sources: List[DataSourceConfig] = Field(..., description="Data sources to process")
    config: Optional[DataPrepConfig] = Field(default=None, description="Pipeline configuration")
    output_name: Optional[str] = Field(default=None, description="Name for output file")


class DrupalPrepRequest(BaseModel):
    """Request to prepare Drupal training data"""
    target_version: str = Field(default="11", description="Target Drupal version")
    include_change_records: bool = Field(default=True, description="Include change records")
    max_pages: int = Field(default=100, description="Maximum pages to collect")


class BatchPrepRequest(BaseModel):
    """Request to prepare multiple domain datasets"""
    batch_configs: List[Dict[str, Any]] = Field(..., description="List of domain configurations")
    max_concurrent: int = Field(default=3, description="Maximum concurrent pipelines")


class DataPrepResponse(BaseModel):
    """Response from data preparation"""
    job_id: str
    status: str
    output_file: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    created_at: float


class DataPrepStatusResponse(BaseModel):
    """Status of data preparation job"""
    job_id: str
    status: str  # pending, collecting, preprocessing, formatting, completed, failed
    progress: float
    sources_processed: int
    items_collected: int
    items_preprocessed: int
    items_formatted: int
    errors: List[str]
    output_file: Optional[str] = None
    created_at: float
    completed_at: Optional[float] = None


# Job tracking
class DataPrepJob:
    """Track data preparation jobs"""
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status = "pending"
        self.progress = 0.0
        self.stats = {}
        self.errors = []
        self.output_file = None
        self.created_at = time.time()
        self.completed_at = None


# Global job tracker (in production, use database)
prep_jobs: Dict[str, DataPrepJob] = {}


# Endpoints

@router.post("/agents/{agent_id}/training/prepare", response_model=DataPrepResponse)
async def prepare_training_data(
    agent_id: str,
    request: PrepareDataRequest,
    background_tasks: BackgroundTasks,
):
    """
    Prepare training data from various sources.

    This endpoint allows you to collect, preprocess, and format data
    from websites, documentation, APIs, etc. for training.

    Supported source types:
    - url: Single web page
    - sitemap: XML sitemap
    - documentation: Documentation tree
    - api_doc: API documentation
    - changes: Change records/migration guides

    Supported preprocessors:
    - drupal: Drupal-specific processing
    - code: Code documentation processing
    - markdown: General markdown processing
    - default: Basic text processing

    Supported formatters:
    - jsonl: Standard JSONL format
    - instruction: Instruction-tuning format
    - conversation: Multi-turn conversation format
    - delta: Version-aware delta training format
    """
    try:
        import uuid
        job_id = str(uuid.uuid4())
        job = DataPrepJob(job_id)
        prep_jobs[job_id] = job

        # Convert request to DataSource objects
        sources = []
        for source_config in request.sources:
            sources.append(DataSource(
                type=source_config.type,
                location=source_config.location,
                metadata=source_config.metadata or {},
                version=source_config.version
            ))

        # Configure output
        output_dir = Path(f"/app/data/agents/{agent_id}/prepared_data")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_name = request.output_name or f"training_data_{job_id[:8]}.jsonl"
        output_file = output_dir / output_name

        # Start preparation in background
        async def run_preparation():
            try:
                job.status = "collecting"

                # Create pipeline
                config = request.config.dict() if request.config else {}
                config['output_dir'] = str(output_dir)

                pipeline = DataPreparationPipeline(config)

                # Extract component types from config
                collector_type = config.pop('collector_type', 'web')
                preprocessor_type = config.pop('preprocessor_type', 'markdown')
                formatter_type = config.pop('formatter_type', 'jsonl')

                # Configure components
                pipeline.configure(
                    collector_type=collector_type,
                    preprocessor_type=preprocessor_type,
                    formatter_type=formatter_type,
                    **config
                )

                # Run pipeline with progress updates
                def update_progress(phase: str, progress: float):
                    job.status = phase
                    job.progress = progress
                    if hasattr(pipeline, 'stats'):
                        job.stats = pipeline.stats

                # Run preparation
                result_file = await pipeline.prepare_data(sources, output_file)

                # Update job
                job.status = "completed"
                job.progress = 1.0
                job.output_file = str(result_file)
                job.stats = pipeline.stats
                job.completed_at = time.time()

                logger.info(f"Data preparation completed for job {job_id}")

            except Exception as e:
                logger.error(f"Data preparation failed for job {job_id}: {e}")
                job.status = "failed"
                job.errors.append(str(e))

        background_tasks.add_task(run_preparation)

        return DataPrepResponse(
            job_id=job_id,
            status=job.status,
            output_file=None,
            stats=None,
            created_at=job.created_at
        )

    except Exception as e:
        logger.error(f"Error starting data preparation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/training/prepare/drupal", response_model=DataPrepResponse)
async def prepare_drupal_training_data(
    agent_id: str,
    request: DrupalPrepRequest,
    background_tasks: BackgroundTasks,
):
    """
    Specialized endpoint for preparing Drupal training data.

    This automatically configures the pipeline for Drupal documentation,
    including:
    - User guides
    - API documentation
    - Change records (if enabled)
    - Version-specific delta training

    The data is preprocessed with Drupal-specific patterns and formatted
    for optimal training on Drupal knowledge.
    """
    try:
        import uuid
        job_id = str(uuid.uuid4())
        job = DataPrepJob(job_id)
        prep_jobs[job_id] = job

        output_dir = Path(f"/app/data/agents/{agent_id}/prepared_data")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Start Drupal preparation in background
        async def run_drupal_preparation():
            try:
                job.status = "collecting"

                pipeline = DataPreparationPipeline({
                    'output_dir': str(output_dir),
                    'max_pages': request.max_pages
                })

                # Run Drupal-specific preparation
                result_file = await pipeline.prepare_drupal_training_data(
                    target_version=request.target_version,
                    include_change_records=request.include_change_records
                )

                # Update job
                job.status = "completed"
                job.progress = 1.0
                job.output_file = str(result_file)
                job.stats = pipeline.stats
                job.completed_at = time.time()

                logger.info(f"Drupal data preparation completed for job {job_id}")

            except Exception as e:
                logger.error(f"Drupal data preparation failed: {e}")
                job.status = "failed"
                job.errors.append(str(e))

        background_tasks.add_task(run_drupal_preparation)

        return DataPrepResponse(
            job_id=job_id,
            status=job.status,
            output_file=None,
            stats=None,
            created_at=job.created_at
        )

    except Exception as e:
        logger.error(f"Error starting Drupal data preparation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/training/prepare/batch", response_model=List[DataPrepResponse])
async def prepare_batch_training_data(
    agent_id: str,
    request: BatchPrepRequest,
    background_tasks: BackgroundTasks,
):
    """
    Prepare training data for multiple domains in parallel.

    This endpoint allows processing multiple domain configurations
    simultaneously, useful for creating comprehensive training datasets.

    Example batch config:
    ```json
    {
        "batch_configs": [
            {
                "domain": "drupal",
                "version": "11"
            },
            {
                "domain": "react",
                "sources": [
                    {"type": "url", "location": "https://react.dev/learn"}
                ],
                "options": {
                    "language": "javascript",
                    "framework": "react"
                }
            }
        ]
    }
    ```
    """
    try:
        import uuid
        jobs = []

        for config in request.batch_configs:
            job_id = str(uuid.uuid4())
            job = DataPrepJob(job_id)
            prep_jobs[job_id] = job
            jobs.append(job)

        output_dir = Path(f"/app/data/agents/{agent_id}/prepared_data")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Start batch processing in background
        async def run_batch_preparation():
            try:
                processor = BatchProcessor({
                    'output_dir': str(output_dir),
                    'max_concurrent': request.max_concurrent
                })

                results = await processor.process_batch(request.batch_configs)

                # Update job statuses
                for i, job in enumerate(jobs):
                    if i < len(results):
                        job.status = "completed"
                        job.output_file = str(results[i])
                        job.progress = 1.0
                    else:
                        job.status = "failed"
                        job.errors.append("Batch processing error")
                    job.completed_at = time.time()

                logger.info(f"Batch preparation completed: {len(results)} successful")

            except Exception as e:
                logger.error(f"Batch preparation failed: {e}")
                for job in jobs:
                    job.status = "failed"
                    job.errors.append(str(e))

        background_tasks.add_task(run_batch_preparation)

        return [
            DataPrepResponse(
                job_id=job.job_id,
                status=job.status,
                output_file=None,
                stats=None,
                created_at=job.created_at
            )
            for job in jobs
        ]

    except Exception as e:
        logger.error(f"Error starting batch preparation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training/prepare/{job_id}", response_model=DataPrepStatusResponse)
async def get_preparation_status(job_id: str):
    """
    Get status of a data preparation job.

    Returns detailed information about the preparation progress,
    including statistics and any errors encountered.
    """
    try:
        job = prep_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return DataPrepStatusResponse(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress,
            sources_processed=job.stats.get('sources_processed', 0),
            items_collected=job.stats.get('items_collected', 0),
            items_preprocessed=job.stats.get('items_preprocessed', 0),
            items_formatted=job.stats.get('items_formatted', 0),
            errors=job.errors + job.stats.get('errors', []),
            output_file=job.output_file,
            created_at=job.created_at,
            completed_at=job.completed_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preparation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training/prepare/jobs")
async def list_preparation_jobs():
    """
    List all data preparation jobs.

    Returns a list of all jobs with their current status.
    """
    jobs_list = []
    for job_id, job in prep_jobs.items():
        jobs_list.append({
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
            "errors": len(job.errors) if job.errors else 0
        })

    return {
        "total": len(jobs_list),
        "jobs": jobs_list
    }


@router.get("/training/prepare/examples")
async def get_preparation_examples():
    """
    Get example configurations for data preparation.

    Returns sample configurations for various domains and use cases.
    """
    examples = {
        "drupal": {
            "description": "Prepare Drupal 11 documentation for training",
            "request": {
                "sources": [
                    {
                        "type": "documentation",
                        "location": "https://www.drupal.org/docs/user_guide/en",
                        "metadata": {"category": "user_guide"}
                    },
                    {
                        "type": "api_doc",
                        "location": "https://api.drupal.org/api/drupal/11",
                        "metadata": {"category": "api_reference"}
                    }
                ],
                "config": {
                    "collector_type": "documentation",
                    "preprocessor_type": "drupal",
                    "formatter_type": "delta",
                    "target_version": "11",
                    "enable_versioning": True
                }
            }
        },
        "react": {
            "description": "Prepare React documentation for training",
            "request": {
                "sources": [
                    {
                        "type": "documentation",
                        "location": "https://react.dev/learn",
                        "metadata": {"category": "tutorial"}
                    },
                    {
                        "type": "api_doc",
                        "location": "https://react.dev/reference",
                        "metadata": {"category": "api_reference"}
                    }
                ],
                "config": {
                    "collector_type": "documentation",
                    "preprocessor_type": "code",
                    "formatter_type": "instruction",
                    "language": "javascript",
                    "framework": "react"
                }
            }
        },
        "custom_docs": {
            "description": "Prepare custom markdown documentation",
            "request": {
                "sources": [
                    {
                        "type": "url",
                        "location": "https://example.com/docs",
                        "metadata": {"category": "main_docs"}
                    }
                ],
                "config": {
                    "collector_type": "web",
                    "preprocessor_type": "markdown",
                    "formatter_type": "conversation",
                    "follow_links": True,
                    "max_depth": 2
                }
            }
        }
    }

    return examples


@router.delete("/training/prepare/{job_id}")
async def cancel_preparation_job(job_id: str):
    """
    Cancel a data preparation job.

    Note: This will only work if the job is still pending or in early stages.
    """
    try:
        job = prep_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status in ["completed", "failed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job in {job.status} state"
            )

        job.status = "cancelled"
        job.errors.append("Cancelled by user")

        return {"message": "Job cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        raise HTTPException(status_code=500, detail=str(e))