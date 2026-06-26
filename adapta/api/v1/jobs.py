"""Training job endpoints (enqueue, status, logs)."""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.db.models import Project, TrainingJob
from adapta.db.session import get_db
from adapta.domain.errors import NotFound
from adapta.models.generated import JobCreateRequest, JobResponse, JobStatus
from adapta.services.auth import get_current_user, require_team_member, require_team_writer
from adapta.services.jobs import get_job_queue
from adapta.services.training import enqueue_training_job

router = APIRouter(prefix="/projects/{project_id}/jobs", tags=["jobs"])


def _job_resp(j: TrainingJob) -> JobResponse:
    eval_metrics: Optional[dict] = None
    if j.eval_metrics:
        try:
            eval_metrics = json.loads(j.eval_metrics)
        except (ValueError, TypeError):
            eval_metrics = None  # never let a malformed blob 500 the job read
    return JobResponse(
        id=j.id,
        status=JobStatus(j.status.value),
        progress=j.progress,
        logs=j.logs,
        adapter_path=j.adapter_path,
        eval_score=j.eval_score,
        eval_passed=j.eval_passed,
        eval_metrics=eval_metrics,
        error_message=j.error_message,
        created_at=j.created_at.isoformat(),
    )


async def _get_project(db: AsyncSession, project_id: str) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFound(message=f"Project not found: {project_id}")
    return project


@router.post("", response_model=JobResponse, status_code=202)
async def create_job(
    project_id: str,
    body: JobCreateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)

    # exclude_unset keeps only client-supplied hyperparameters; server defaults
    # and validation fill the rest in the training worker.
    config = body.training_config.model_dump(exclude_unset=True) if body.training_config else None
    from adapta.models.generated import Method

    method = body.method.value if isinstance(body.method, Method) else "sft"
    job = await enqueue_training_job(
        db,
        project_id=project_id,
        dataset_id=body.dataset_id,
        base_model=project.base_model,
        training_config=config,
        method=method,
    )
    return _job_resp(job)


@router.get("", response_model=List[JobResponse])
async def list_jobs(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    result = await db.execute(select(TrainingJob).where(TrainingJob.project_id == project_id))
    return [_job_resp(j) for j in result.scalars().all()]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    project_id: str,
    job_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)

    result = await db.execute(
        select(TrainingJob).where(TrainingJob.id == job_id, TrainingJob.project_id == project_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise NotFound(message="Job not found")

    try:
        queue = get_job_queue()
        live = await queue.get_status(job_id)
        if live:
            job.progress = live.get("progress", job.progress)
            if live.get("logs"):
                job.logs = live["logs"]
    except Exception:
        pass

    return _job_resp(job)
