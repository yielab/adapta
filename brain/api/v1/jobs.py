"""Training job endpoints (enqueue, status, logs)."""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import Project, TrainingJob
from brain.db.session import get_db
from brain.domain.errors import NotFound
from brain.services.auth import get_current_user, require_team_member, require_team_writer
from brain.services.jobs import get_job_queue
from brain.services.training import enqueue_training_job

router = APIRouter(prefix="/projects/{project_id}/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    dataset_id: str
    training_config: Optional[dict] = None


class JobResponse(BaseModel):
    id: str
    status: str
    progress: float
    logs: Optional[str]
    adapter_path: Optional[str]
    eval_score: Optional[float]
    eval_passed: Optional[bool]
    error_message: Optional[str]
    created_at: str


def _job_resp(j: TrainingJob) -> JobResponse:
    return JobResponse(
        id=j.id,
        status=j.status.value,
        progress=j.progress,
        logs=j.logs,
        adapter_path=j.adapter_path,
        eval_score=j.eval_score,
        eval_passed=j.eval_passed,
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

    job = await enqueue_training_job(
        db,
        project_id=project_id,
        dataset_id=body.dataset_id,
        base_model=project.base_model,
        training_config=body.training_config,
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

    # Merge live progress from Redis if available
    result = await db.execute(
        select(TrainingJob).where(TrainingJob.id == job_id, TrainingJob.project_id == project_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise NotFound(message="Job not found")

    # Enrich with live Redis status
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
