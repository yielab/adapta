"""Training API endpoints"""

import logging
import tempfile
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel, Field

from brain.training.data_manager import data_manager
from brain.training.job_manager import job_manager
from brain.training.models import TrainingConfig, JobState, TrainingMetrics, EvaluationMetrics, EvaluationResult
from brain.training.trainer import trainer
from brain.training.evaluator import evaluator
from brain.core.adapter_manager import adapter_manager

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
            # Register the trained adapter
            job = await job_manager.get_job(job_id)
            if job:
                try:
                    # Get final loss from metrics
                    final_loss = job.metrics[-1].loss if job.metrics else None

                    # Register adapter with adapter manager
                    adapter_manager.register_adapter(
                        agent_id=job.agent_id,
                        adapter_name=job.adapter_name,
                        base_model=job.base_model,
                        adapter_path=job.adapter_path,
                        training_job_id=job_id,
                        num_epochs=job.config.num_epochs,
                        final_loss=final_loss,
                    )
                    logger.info(f"Registered adapter for agent {job.agent_id}: {job.adapter_name}")
                except Exception as e:
                    logger.error(f"Failed to register adapter: {e}")
                    # Continue anyway - training succeeded

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


class MetricsDataPoint(BaseModel):
    """Single metrics data point"""

    step: int
    epoch: int
    loss: float
    learning_rate: float
    grad_norm: Optional[float] = None
    timestamp: float
    eval_loss: Optional[float] = None
    perplexity: Optional[float] = None


class TrainingMetricsResponse(BaseModel):
    """Training metrics history response"""

    job_id: str
    agent_id: str
    adapter_name: str
    state: str
    metrics: List[MetricsDataPoint]
    total_steps: int
    total_epochs: int


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


class AdapterResponse(BaseModel):
    """Adapter information response"""

    adapter_id: str
    agent_id: str
    adapter_name: str
    base_model: str
    training_job_id: str
    created_at: float
    num_epochs: int
    final_loss: Optional[float] = None
    is_merged: bool = False


class EvaluationMetricsResponse(BaseModel):
    """Evaluation metrics response"""

    loss: float
    perplexity: float
    accuracy: Optional[float] = None
    exact_match: Optional[float] = None
    token_accuracy: Optional[float] = None
    bleu_score: Optional[float] = None
    coherence_score: Optional[float] = None
    fluency_score: Optional[float] = None


class SamplePrediction(BaseModel):
    """Sample prediction from evaluation"""

    input: str
    expected: str
    predicted: str


class EvaluationResponse(BaseModel):
    """Evaluation result response"""

    eval_id: str
    job_id: str
    agent_id: str
    adapter_name: str
    adapter_path: str
    dataset_path: str
    num_examples: int
    metrics: EvaluationMetricsResponse
    sample_predictions: List[SamplePrediction]
    created_at: float
    duration_seconds: float


class EvaluationRequest(BaseModel):
    """Request to evaluate an adapter"""

    dataset_name: Optional[str] = Field(None, description="Name of validation dataset to use (default: use training dataset)")
    num_samples: int = Field(5, description="Number of sample predictions to generate", ge=1, le=20)
    max_examples: Optional[int] = Field(None, description="Maximum examples to evaluate (None = all)", ge=1)


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


@router.get("/agents/{agent_id}/training/jobs/{job_id}/metrics", response_model=TrainingMetricsResponse)
async def get_training_metrics(agent_id: str, job_id: str):
    """Get full metrics history for a training job"""
    try:
        job = await job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Verify job belongs to agent
        if job.agent_id != agent_id:
            raise HTTPException(status_code=404, detail="Job not found")

        # Convert metrics to response format
        metrics_data = [
            MetricsDataPoint(
                step=m.step,
                epoch=m.epoch,
                loss=m.loss,
                learning_rate=m.learning_rate,
                grad_norm=m.grad_norm,
                timestamp=m.timestamp,
                eval_loss=m.eval_loss,
                perplexity=m.perplexity,
            )
            for m in job.metrics
        ]

        # Calculate total steps (if job has status)
        status = await job_manager.get_job_status(job_id)
        total_steps = status.total_steps if status else 0
        total_epochs = status.total_epochs if status else job.config.num_epochs

        return TrainingMetricsResponse(
            job_id=job.job_id,
            agent_id=job.agent_id,
            adapter_name=job.adapter_name,
            state=job.state.value,
            metrics=metrics_data,
            total_steps=total_steps,
            total_epochs=total_epochs,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting training metrics: {e}")
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


# Adapter Management Endpoints


@router.get("/agents/{agent_id}/adapters", response_model=List[AdapterResponse])
async def list_adapters(agent_id: str):
    """
    List all trained adapters for an agent

    Returns all LoRA adapters that have been trained for this agent.
    """
    try:
        adapters = adapter_manager.list_adapters(agent_id=agent_id)

        return [
            AdapterResponse(
                adapter_id=adapter.adapter_id,
                agent_id=adapter.agent_id,
                adapter_name=adapter.adapter_name,
                base_model=adapter.base_model,
                training_job_id=adapter.training_job_id,
                created_at=adapter.created_at,
                num_epochs=adapter.num_epochs,
                final_loss=adapter.final_loss,
                is_merged=adapter.is_merged,
            )
            for adapter in adapters
        ]
    except Exception as e:
        logger.error(f"Error listing adapters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/adapters/latest", response_model=AdapterResponse)
async def get_latest_adapter(agent_id: str):
    """
    Get the latest trained adapter for an agent

    Returns the most recently created adapter for this agent.
    """
    try:
        adapter = adapter_manager.get_latest_adapter(agent_id)

        if not adapter:
            raise HTTPException(
                status_code=404,
                detail=f"No adapters found for agent {agent_id}"
            )

        return AdapterResponse(
            adapter_id=adapter.adapter_id,
            agent_id=adapter.agent_id,
            adapter_name=adapter.adapter_name,
            base_model=adapter.base_model,
            training_job_id=adapter.training_job_id,
            created_at=adapter.created_at,
            num_epochs=adapter.num_epochs,
            final_loss=adapter.final_loss,
            is_merged=adapter.is_merged,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting latest adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/adapters/{adapter_id}/merge")
async def merge_adapter(
    agent_id: str,
    adapter_id: str,
    background_tasks: BackgroundTasks,
    output_name: Optional[str] = None,
    quantization: str = "q4_k_m",
):
    """
    Merge a LoRA adapter with its base model to create a standalone GGUF model

    This is necessary because llama-cpp-python doesn't support LoRA adapters directly.
    The merged model can then be used for inference.

    Note: This requires training dependencies and may take several minutes.
    """
    try:
        # Verify adapter exists and belongs to agent
        adapter = adapter_manager.get_adapter(adapter_id)
        if not adapter:
            raise HTTPException(status_code=404, detail="Adapter not found")

        if adapter.agent_id != agent_id:
            raise HTTPException(status_code=404, detail="Adapter not found")

        # Start merge in background
        async def do_merge():
            try:
                merged_path = await adapter_manager.merge_adapter_with_base(
                    adapter_id=adapter_id,
                    output_name=output_name,
                    quantization=quantization,
                )
                logger.info(f"Adapter merge completed: {merged_path}")
            except Exception as e:
                logger.error(f"Adapter merge failed: {e}")

        background_tasks.add_task(do_merge)

        return {
            "message": "Adapter merge started",
            "adapter_id": adapter_id,
            "output_name": output_name or f"{agent_id}_{adapter.adapter_name}_merged",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting adapter merge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/adapters/{adapter_id}")
async def delete_adapter(agent_id: str, adapter_id: str):
    """
    Delete a trained adapter

    This will remove the adapter files and metadata.
    """
    try:
        # Verify adapter exists and belongs to agent
        adapter = adapter_manager.get_adapter(adapter_id)
        if not adapter:
            raise HTTPException(status_code=404, detail="Adapter not found")

        if adapter.agent_id != agent_id:
            raise HTTPException(status_code=404, detail="Adapter not found")

        success = adapter_manager.delete_adapter(adapter_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete adapter")

        return {"message": "Adapter deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Evaluation Endpoints


@router.post("/agents/{agent_id}/training/jobs/{job_id}/evaluate", response_model=EvaluationResponse)
async def evaluate_trained_adapter(
    agent_id: str,
    job_id: str,
    request: EvaluationRequest = EvaluationRequest(),
    background_tasks: BackgroundTasks = None,
):
    """
    Evaluate a trained adapter on a validation dataset.

    This endpoint runs evaluation to compute quality metrics like loss and perplexity.
    It also generates sample predictions for inspection.

    The evaluation runs synchronously and returns results when complete.
    For large datasets, use the max_examples parameter to limit evaluation time.
    """
    try:
        # Get training job
        job = await job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Training job not found")

        # Verify job belongs to agent
        if job.agent_id != agent_id:
            raise HTTPException(status_code=404, detail="Training job not found")

        # Check job is completed
        if job.state != JobState.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Job must be completed to evaluate (current state: {job.state.value})",
            )

        # Get adapter path
        if not job.adapter_path:
            raise HTTPException(status_code=400, detail="Adapter path not found")

        adapter_path = Path(job.adapter_path)
        if not adapter_path.exists():
            raise HTTPException(status_code=404, detail="Adapter files not found")

        # Determine dataset to use
        dataset_path = job.dataset_path
        if request.dataset_name:
            # Look for named validation dataset
            datasets = data_manager.list_datasets(agent_id)
            dataset = next((d for d in datasets if d.name == request.dataset_name), None)
            if not dataset:
                raise HTTPException(status_code=404, detail=f"Dataset '{request.dataset_name}' not found")
            dataset_path = dataset.file_path

        # Run evaluation
        logger.info(f"Starting evaluation for job {job_id}")
        result = await evaluator.evaluate_adapter(
            job_id=job_id,
            agent_id=agent_id,
            adapter_name=job.adapter_name,
            adapter_path=adapter_path,
            base_model=job.base_model,
            dataset_path=dataset_path,
            num_samples=request.num_samples,
            max_examples=request.max_examples,
        )

        # Convert to response format
        return EvaluationResponse(
            eval_id=result.eval_id,
            job_id=result.job_id,
            agent_id=result.agent_id,
            adapter_name=result.adapter_name,
            adapter_path=result.adapter_path,
            dataset_path=result.dataset_path,
            num_examples=result.num_examples,
            metrics=EvaluationMetricsResponse(**result.metrics.to_dict()),
            sample_predictions=[
                SamplePrediction(**pred) for pred in result.sample_predictions
            ],
            created_at=result.created_at,
            duration_seconds=result.duration_seconds,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error evaluating adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/adapters/{adapter_id}/evaluate", response_model=EvaluationResponse)
async def evaluate_adapter_by_id(
    agent_id: str,
    adapter_id: str,
    request: EvaluationRequest = EvaluationRequest(),
):
    """
    Evaluate an adapter by its adapter ID.

    This is a convenience endpoint that looks up the adapter and evaluates it.
    """
    try:
        # Get adapter
        adapter = adapter_manager.get_adapter(adapter_id)
        if not adapter:
            raise HTTPException(status_code=404, detail="Adapter not found")

        # Verify adapter belongs to agent
        if adapter.agent_id != agent_id:
            raise HTTPException(status_code=404, detail="Adapter not found")

        # Get training job to find dataset
        job = await job_manager.get_job(adapter.training_job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Training job not found")

        # Determine dataset
        dataset_path = job.dataset_path
        if request.dataset_name:
            datasets = data_manager.list_datasets(agent_id)
            dataset = next((d for d in datasets if d.name == request.dataset_name), None)
            if not dataset:
                raise HTTPException(status_code=404, detail=f"Dataset '{request.dataset_name}' not found")
            dataset_path = dataset.file_path

        # Get adapter path
        adapter_path = Path(adapter.adapter_path)
        if not adapter_path.exists():
            raise HTTPException(status_code=404, detail="Adapter files not found")

        # Run evaluation
        logger.info(f"Starting evaluation for adapter {adapter_id}")
        result = await evaluator.evaluate_adapter(
            job_id=adapter.training_job_id,
            agent_id=agent_id,
            adapter_name=adapter.adapter_name,
            adapter_path=adapter_path,
            base_model=adapter.base_model,
            dataset_path=dataset_path,
            num_samples=request.num_samples,
            max_examples=request.max_examples,
        )

        # Convert to response format
        return EvaluationResponse(
            eval_id=result.eval_id,
            job_id=result.job_id,
            agent_id=result.agent_id,
            adapter_name=result.adapter_name,
            adapter_path=result.adapter_path,
            dataset_path=result.dataset_path,
            num_examples=result.num_examples,
            metrics=EvaluationMetricsResponse(**result.metrics.to_dict()),
            sample_predictions=[
                SamplePrediction(**pred) for pred in result.sample_predictions
            ],
            created_at=result.created_at,
            duration_seconds=result.duration_seconds,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error evaluating adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))
