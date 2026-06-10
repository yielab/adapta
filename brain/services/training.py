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

from brain.config import settings
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
    eval_metrics: Optional[str] = None,
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
        if eval_metrics is not None:
            row.eval_metrics = eval_metrics
        if error is not None:
            row.error_message = error
        await db.commit()


def check_min_training_samples(num_samples: Optional[int]) -> None:
    """Reject a too-small dataset before a job is created (A4.6).

    Below ``settings.min_training_samples`` the held-out eval split collapses
    (e.g. 1 row → 0 held out → the gate scores the training rows), so the eval
    gate would only measure memorization. Raising here keeps that signal honest.
    """
    n = num_samples or 0
    if n < settings.min_training_samples:
        raise InvalidRequest(
            message=(
                f"Dataset has {n} sample(s); at least {settings.min_training_samples} "
                "are required to train. A smaller set can't be split into a held-out "
                "eval set, so the gate would only measure memorization."
            )
        )


async def recover_orphaned_jobs(max_attempts: int = 1) -> tuple[int, int]:
    """Reconcile jobs a crashed worker left behind (A4.2). Returns (requeued, failed).

    A hard crash (OOM-kill, power loss, segfault) pops a job off the Redis queue
    but never drives it to a terminal state — so it sits ``running`` in Postgres
    forever with no live worker. A failed enqueue (or a wiped Redis) can likewise
    leave a job ``queued`` in Postgres but absent from the queue. On worker startup
    we find both and either requeue them (reconstructing the payload from Postgres,
    so it survives a wiped Redis) or fail them once they've burned their retries.

    Single-worker assumption: at startup no other worker is live, so any ``running``
    job is orphaned. Run this before the dequeue loop.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from brain.db.models import JobStatus as _JobStatus
    from brain.db.models import Project, TrainingJob
    from brain.db.session import AsyncSessionLocal

    queue = get_job_queue()
    queued_ids = set(await queue.queued_job_ids())
    requeued = failed = 0

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(TrainingJob).where(
                    TrainingJob.status.in_([_JobStatus.running, _JobStatus.queued])
                )
            )
        ).scalars().all()

        for row in rows:
            # A `queued` job that's still in the Redis queue is legitimately waiting.
            if row.status == _JobStatus.queued and row.id in queued_ids:
                continue

            is_crash = row.status == _JobStatus.running
            if is_crash:
                # Only a real crash (was `running`) consumes a retry; a lost-enqueue
                # `queued` job never actually ran.
                row.attempts = (row.attempts or 0) + 1

            dataset = (
                await db.execute(select(Dataset).where(Dataset.id == row.dataset_id))
            ).scalar_one_or_none()
            project = (
                await db.execute(select(Project).where(Project.id == row.project_id))
            ).scalar_one_or_none()

            give_up = (is_crash and row.attempts > max_attempts) or dataset is None or project is None
            if give_up:
                reason = (
                    "dataset or project no longer exists"
                    if dataset is None or project is None
                    else f"worker crashed during training and exhausted retries ({max_attempts})"
                )
                row.status = _JobStatus.failed
                row.error_message = f"Job could not be recovered — {reason}."
                row.finished_at = datetime.now(timezone.utc)
                await db.commit()
                await queue.update_status(row.id, status="failed", error=row.error_message)
                failed += 1
                logger.warning("Orphaned job %s failed during recovery — %s", row.id, reason)
                continue

            assert dataset is not None and project is not None  # give_up covered None
            row.status = _JobStatus.queued
            row.progress = 0.0
            await db.commit()

            payload = {
                "job_id": row.id,
                "project_id": row.project_id,
                "dataset_id": row.dataset_id,
                "dataset_path": dataset.storage_path,
                "base_model": project.base_model,
                "training_config": json.loads(row.training_config) if row.training_config else {},
            }
            await queue.enqueue(row.id, payload)
            requeued += 1
            logger.warning(
                "Requeued orphaned job %s (was %s, attempt %d)",
                row.id, "running" if is_crash else "queued-lost", row.attempts,
            )

    if requeued or failed:
        logger.info("Crash recovery: %d job(s) requeued, %d failed", requeued, failed)
    return requeued, failed


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
    check_min_training_samples(dataset.num_samples)

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
