"""
Training coordination service.
Handles dataset validation and job enqueuing; actual training runs in the worker.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import Dataset, DatasetStatus, JobStatus, TrainingJob
from brain.domain.errors import InvalidRequest, NotFound
from brain.services.jobs import get_job_queue

logger = logging.getLogger(__name__)

DATASET_SCHEMA_PATH = Path("specs/schemas/training_dataset.schema.json")


def _load_schema() -> Optional[dict]:
    if DATASET_SCHEMA_PATH.exists():
        return json.loads(DATASET_SCHEMA_PATH.read_text())  # type: ignore[no-any-return]
    return None


def validate_dataset(path: Path) -> tuple[bool, Optional[str], int]:
    """
    Validate a JSONL file against the instruction-pair schema.
    Returns (is_valid, error_message, num_samples).
    Each line must be {"prompt": str, "response": str}.
    """
    try:
        schema = _load_schema()
        samples = []
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    return False, f"Line {i}: invalid JSON — {exc}", 0

                if not isinstance(obj.get("prompt"), str) or not obj["prompt"].strip():
                    return False, f"Line {i}: missing or empty 'prompt' field", 0
                if not isinstance(obj.get("response"), str) or not obj["response"].strip():
                    return False, f"Line {i}: missing or empty 'response' field", 0

                if schema:
                    import jsonschema
                    try:
                        jsonschema.validate(obj, schema)
                    except jsonschema.ValidationError as e:
                        return False, f"Line {i}: schema violation — {e.message}", 0

                samples.append(obj)

        if not samples:
            return False, "Dataset is empty — must have at least one instruction pair", 0

        return True, None, len(samples)

    except Exception as exc:
        return False, str(exc), 0


async def update_job_record(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    logs: Optional[str] = None,
    adapter_path: Optional[str] = None,
    eval_score: Optional[float] = None,
    eval_passed: Optional[bool] = None,
    error: Optional[str] = None,
) -> None:
    """Persist a training job's lifecycle to Postgres (the source of truth the API
    and the endpoint-creation gate read).

    The Redis ``JobQueue.update_status`` only updates live progress; without this the
    Postgres row stayed at ``queued`` forever, so a finished job never looked terminal
    to ``GET /jobs/{id}`` and a passed adapter could never bind an endpoint.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from brain.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(select(TrainingJob).where(TrainingJob.id == job_id))
        ).scalar_one_or_none()
        if row is None:
            logger.error("update_job_record: job %s not found — cannot persist status", job_id)
            return
        if status is not None:
            row.status = JobStatus(status)
            if status == "running" and row.started_at is None:
                row.started_at = datetime.now(timezone.utc)
            if status in ("succeeded", "failed", "cancelled"):
                row.finished_at = datetime.now(timezone.utc)
        if progress is not None:
            row.progress = progress
        if logs is not None:
            row.logs = logs
        if adapter_path is not None:
            row.adapter_path = adapter_path
        if eval_score is not None:
            row.eval_score = eval_score
        if eval_passed is not None:
            row.eval_passed = eval_passed
        if error is not None:
            row.error_message = error
        await db.commit()


async def enqueue_training_job(
    db: AsyncSession,
    project_id: str,
    dataset_id: str,
    base_model: str,
    training_config: Optional[dict] = None,
) -> TrainingJob:
    """Create a TrainingJob record and push it to the Redis queue."""
    from sqlalchemy import select
    result = await db.execute(select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id))
    dataset: Optional[Dataset] = result.scalar_one_or_none()
    if not dataset:
        raise NotFound(message="Dataset not found")
    if dataset.status != DatasetStatus.valid:
        raise InvalidRequest(message="Dataset is not valid — cannot start training")

    job = TrainingJob(
        project_id=project_id,
        dataset_id=dataset_id,
        status=JobStatus.queued,
        training_config=json.dumps(training_config or {}),
    )
    db.add(job)
    await db.flush()

    payload = {
        "job_id": job.id,
        "project_id": project_id,
        "dataset_id": dataset_id,
        "dataset_path": dataset.storage_path,
        "base_model": base_model,
        "training_config": training_config or {},
    }

    queue = get_job_queue()
    await queue.enqueue(job.id, payload)
    logger.info("Training job %s enqueued for project %s", job.id, project_id)
    return job
