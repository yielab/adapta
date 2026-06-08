"""Project endpoint management (create, get, enable/disable)."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import Endpoint, EndpointStatus, JobStatus, Project, ProjectType, TrainingJob
from brain.db.session import get_db
from brain.domain.errors import InvalidRequest, NotFound
from brain.services.auth import get_current_user, require_team_member

router = APIRouter(prefix="/projects/{project_id}/endpoint", tags=["endpoints"])


class EndpointResponse(BaseModel):
    id: str
    slug: str
    status: str
    base_model: str
    adapter_path: Optional[str]
    project_type: str


async def _get_project(db: AsyncSession, project_id: str) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFound(message=f"Project not found: {project_id}")
    return project


def _ep_resp(ep: Endpoint, project_type: str) -> EndpointResponse:
    return EndpointResponse(
        id=ep.id,
        slug=ep.slug,
        status=ep.status.value,
        base_model=ep.base_model,
        adapter_path=ep.adapter_path,
        project_type=project_type,
    )


@router.post("", response_model=EndpointResponse, status_code=201)
async def create_endpoint(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create the endpoint for this project.
    - RAG: project must have at least one indexed file.
    - Fine-tune: project must have a succeeded training job with eval_passed=True.
    """
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)

    # Check existing endpoint
    ep_result = await db.execute(select(Endpoint).where(Endpoint.project_id == project_id))
    existing = ep_result.scalar_one_or_none()
    if existing:
        raise InvalidRequest(message="Endpoint already exists for this project")

    adapter_path = None

    if project.type == ProjectType.rag:
        from brain.db.models import Collection
        col_result = await db.execute(select(Collection).where(Collection.project_id == project_id))
        collection = col_result.scalar_one_or_none()
        if not collection or collection.num_chunks == 0:
            raise InvalidRequest(message="No indexed documents found. Upload and index files first.")

    elif project.type == ProjectType.finetune:
        job_result = await db.execute(
            select(TrainingJob)
            .where(
                TrainingJob.project_id == project_id,
                TrainingJob.status == JobStatus.succeeded,
                TrainingJob.eval_passed.is_(True),
            )
            .order_by(TrainingJob.created_at.desc())
        )
        job = job_result.scalars().first()
        if not job:
            raise InvalidRequest(
                message="No successful training job found. Train a dataset first and ensure it passes the eval gate."
            )
        adapter_path = job.adapter_path

    import re
    slug = re.sub(r"[^a-z0-9-]", "-", project.name.lower())[:64]

    endpoint = Endpoint(
        project_id=project_id,
        slug=slug,
        status=EndpointStatus.active,
        base_model=project.base_model,
        adapter_path=adapter_path,
    )
    db.add(endpoint)
    await db.flush()
    return _ep_resp(endpoint, project.type.value)


@router.get("", response_model=EndpointResponse)
async def get_endpoint(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    ep_result = await db.execute(select(Endpoint).where(Endpoint.project_id == project_id))
    endpoint = ep_result.scalar_one_or_none()
    if not endpoint:
        raise NotFound(message="No endpoint for this project. Create one first.")
    return _ep_resp(endpoint, project.type.value)
