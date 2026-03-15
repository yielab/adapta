"""Training API endpoints"""

import logging
import tempfile
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel, Field

from brain.training.data_manager import data_manager
from brain.training.job_manager import job_manager
from brain.training.models import TrainingConfig, JobState, TrainingMetrics
from brain.training.trainer import trainer

logger = logging.getLogger(__name__)

router = APIRouter()


# Background task for training execution
async def run_training_job(job_id: str):
    """
    Execute a training job in the background.

    This function runs the actual LoRA training and updates job status.
    """
    try:
        # Get job
        job = await job_manager.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        # Update state to preparing
        await job_manager.update_job_state(job_id, JobState.PREPARING)

        # Progress callback to update metrics
        async def progress_callback(job_id, step, epoch, loss, learning_rate):
            """Callback for training progress updates"""
            job = await job_manager.get_job(job_id)
            if job:
                metrics = TrainingMetrics(
                    step=step,
                    epoch=int(epoch) if epoch else 0,
                    loss=loss,
                    learning_rate=learning_rate,
                )
                job.add_metrics(metrics)

                # Save job with updated metrics
                job_dir = job_manager._get_job_dir(job_id)
                job.save(job_dir / "job.json")

        # Update state to training
        await job_manager.update_job_state(job_id, JobState.TRAINING)

        # Run training
        success = await trainer.train(
            job_id=job_id,
            base_model=job.base_model,
            dataset_path=job.dataset_path,
            output_dir=job.output_dir,
            adapter_path=job.adapter_path,
            config=job.config,
            progress_callback=progress_callback,
        )

        if success:
            # Update state to completed
            await job_manager.update_job_state(job_id, JobState.COMPLETED)
            logger.info(f"Training job {job_id} completed successfully")
        else:
            await job_manager.update_job_state(
                job_id, JobState.FAILED, error_message="Training returned False"
            )

    except Exception as e:
        logger.error(f"Training job {job_id} failed: {e}")
        import traceback
        await job_manager.update_job_state(
            job_id,
            JobState.FAILED,
            error_message=str(e),
            error_traceback=traceback.format_exc(),
        )


# Request/Response Models
class TrainingConfigRequest(BaseModel):
    """Training configuration from API request"""

    # LoRA parameters
    lora_r: int = Field(default=16, ge=1, le=64)
    lora_alpha: int = Field(default=32, ge=1, le=128)
    lora_dropout: float = Field(default=0.05, ge=0.0, le=0.5)
    target_modules: Optional[List[str]] = None

    # Training parameters
    num_epochs: int = Field(default=3, ge=1, le=20)
    batch_size: int = Field(default=4, ge=1, le=32)
    learning_rate: float = Field(default=2e-4, gt=0.0, le=0.01)
    warmup_steps: int = Field(default=100, ge=0)
    gradient_accumulation_steps: int = Field(default=4, ge=1)
    max_seq_length: int = Field(default=2048, ge=128, le=4096)

    # Advanced options
    use_qlora: bool = True
    gradient_checkpointing: bool = True


class StartTrainingRequest(BaseModel):
    """Request to start a training job"""

    base_model: str = Field(..., description="Base model to fine-tune")
    dataset_name: str = Field(..., description="Name of uploaded dataset")
    adapter_name: str = Field(..., description="Name for the trained adapter")
    config: Optional[TrainingConfigRequest] = None


class TrainingJobResponse(BaseModel):
    """Training job response"""

    job_id: str
    agent_id: str
    base_model: str
    adapter_name: str
    state: str
    progress: float
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None


class TrainingStatusResponse(BaseModel):
    """Training status response"""

    job_id: str
    state: str
    progress: float
    current_step: int
    total_steps: int
    current_epoch: int
    total_epochs: int
    current_loss: Optional[float] = None
    current_lr: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    estimated_time_remaining: Optional[float] = None
    error_message: Optional[str] = None


class DatasetResponse(BaseModel):
    """Dataset information response"""

    name: str
    agent_id: str
    num_examples: int
    num_tokens: int
    avg_tokens_per_example: float
    is_valid: bool
    validation_errors: List[str]
    created_at: float


class QueueStatusResponse(BaseModel):
    """Queue status response"""

    total_jobs: int
    queued: int
    running: int
    completed: int
    failed: int
    cancelled: int


# Endpoints

@router.post("/agents/{agent_id}/training/data", response_model=DatasetResponse)
async def upload_training_data(
    agent_id: str,
    file: UploadFile = File(...),
    dataset_name: Optional[str] = None,
):
    """
    Upload training data for an agent

    The file must be in JSONL format with the following structure:
    ```json
    {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
    {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
    ```

    Each line should be a valid JSON object with a "messages" array.
    """
    # Validate file extension
    if not file.filename or not file.filename.endswith(".jsonl"):
        raise HTTPException(
            status_code=400,
            detail="File must be in JSONL format (.jsonl extension)",
        )

    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl") as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)

        # Upload and validate dataset
        dataset = await data_manager.upload_dataset(
            agent_id=agent_id,
            file_path=tmp_path,
            dataset_name=dataset_name or file.filename.replace(".jsonl", ""),
        )

        # Clean up temp file
        tmp_path.unlink()

        return DatasetResponse(
            name=dataset.name,
            agent_id=dataset.agent_id,
            num_examples=dataset.num_examples,
            num_tokens=dataset.num_tokens,
            avg_tokens_per_example=dataset.avg_tokens_per_example,
            is_valid=dataset.is_valid,
            validation_errors=dataset.validation_errors,
            created_at=dataset.created_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading training data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload dataset: {str(e)}")


@router.get("/agents/{agent_id}/training/data", response_model=List[DatasetResponse])
async def list_training_datasets(agent_id: str):
    """List all training datasets for an agent"""
    try:
        datasets = data_manager.list_datasets(agent_id)
        return [
            DatasetResponse(
                name=ds.name,
                agent_id=ds.agent_id,
                num_examples=ds.num_examples,
                num_tokens=ds.num_tokens,
                avg_tokens_per_example=ds.avg_tokens_per_example,
                is_valid=ds.is_valid,
                validation_errors=ds.validation_errors,
                created_at=ds.created_at,
            )
            for ds in datasets
        ]
    except Exception as e:
        logger.error(f"Error listing datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/training/data/{dataset_name}")
async def delete_training_dataset(agent_id: str, dataset_name: str):
    """Delete a training dataset"""
    try:
        deleted = data_manager.delete_dataset(agent_id, dataset_name)
        if not deleted:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return {"message": "Dataset deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/training/jobs", response_model=TrainingJobResponse)
async def start_training_job(
    agent_id: str,
    request: StartTrainingRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a new training job

    This will queue a training job to fine-tune the specified base model
    using the provided dataset.

    Note: Training dependencies (torch, transformers, peft) must be installed.
    Install with: pip install brain[training]
    """
    try:
        # Validate dataset exists
        dataset = data_manager.get_dataset(agent_id, request.dataset_name)
        if not dataset:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset '{request.dataset_name}' not found for agent '{agent_id}'",
            )

        if not dataset.is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset '{request.dataset_name}' is not valid. Errors: {dataset.validation_errors[:5]}",
            )

        # Create training config
        config_data = request.config.dict() if request.config else {}
        training_config = TrainingConfig(**config_data)

        # Create job
        job = await job_manager.create_job(
            agent_id=agent_id,
            base_model=request.base_model,
            dataset_path=dataset.file_path,
            adapter_name=request.adapter_name,
            config=training_config,
        )

        # Start training in background
        background_tasks.add_task(run_training_job, job.job_id)

        logger.info(f"Created and started training job {job.job_id}")

        return TrainingJobResponse(
            job_id=job.job_id,
            agent_id=job.agent_id,
            base_model=job.base_model,
            adapter_name=job.adapter_name,
            state=job.state.value,
            progress=job.progress,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error_message=job.error_message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting training job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/training/jobs", response_model=List[TrainingJobResponse])
async def list_training_jobs(
    agent_id: str,
    state: Optional[str] = None,
):
    """List all training jobs for an agent"""
    try:
        state_filter = JobState(state) if state else None
        jobs = await job_manager.list_jobs(agent_id=agent_id, state=state_filter)

        return [
            TrainingJobResponse(
                job_id=job.job_id,
                agent_id=job.agent_id,
                base_model=job.base_model,
                adapter_name=job.adapter_name,
                state=job.state.value,
                progress=job.progress,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
                error_message=job.error_message,
            )
            for job in jobs
        ]
    except Exception as e:
        logger.error(f"Error listing training jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/training/jobs/{job_id}", response_model=TrainingStatusResponse)
async def get_training_status(agent_id: str, job_id: str):
    """Get status of a training job"""
    try:
        status = await job_manager.get_job_status(job_id)
        if not status:
            raise HTTPException(status_code=404, detail="Job not found")

        # Verify job belongs to agent
        job = await job_manager.get_job(job_id)
        if job and job.agent_id != agent_id:
            raise HTTPException(status_code=404, detail="Job not found")

        return TrainingStatusResponse(
            job_id=status.job_id,
            state=status.state.value,
            progress=status.progress,
            current_step=status.current_step,
            total_steps=status.total_steps,
            current_epoch=status.current_epoch,
            total_epochs=status.total_epochs,
            current_loss=status.current_loss,
            current_lr=status.current_lr,
            started_at=status.started_at,
            completed_at=status.completed_at,
            estimated_time_remaining=status.estimated_time_remaining,
            error_message=status.error_message,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting training status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/training/jobs/{job_id}")
async def cancel_training_job(agent_id: str, job_id: str):
    """Cancel a training job"""
    try:
        # Verify job belongs to agent
        job = await job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.agent_id != agent_id:
            raise HTTPException(status_code=404, detail="Job not found")

        success = await job_manager.cancel_job(job_id)
        if not success:
            raise HTTPException(status_code=400, detail="Job cannot be cancelled")

        return {"message": "Job cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training/queue", response_model=QueueStatusResponse)
async def get_queue_status():
    """Get overall training queue status"""
    try:
        status = job_manager.get_queue_status()
        return QueueStatusResponse(**status)
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/training/data/example", response_model=DatasetResponse)
async def create_example_dataset(agent_id: str):
    """
    Create an example training dataset for testing

    This creates a small example dataset with 3 conversation examples
    that can be used to test the training pipeline.
    """
    try:
        dataset = data_manager.create_example_dataset(agent_id)

        return DatasetResponse(
            name=dataset.name,
            agent_id=dataset.agent_id,
            num_examples=dataset.num_examples,
            num_tokens=dataset.num_tokens,
            avg_tokens_per_example=dataset.avg_tokens_per_example,
            is_valid=dataset.is_valid,
            validation_errors=dataset.validation_errors,
            created_at=dataset.created_at,
        )
    except Exception as e:
        logger.error(f"Error creating example dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))
