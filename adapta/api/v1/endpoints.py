"""Project endpoint management (create, get, enable/disable)."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.db.models import (
    Endpoint,
    EndpointStatus,
    Project,
    ProjectStatus,
    ProjectType,
)
from adapta.db.session import get_db
from adapta.domain.errors import Conflict, InvalidRequest, NotFound
from adapta.models.generated import (
    EndpointResponse,
    RetrievalSummary,
)
from adapta.models.generated import (
    EndpointStatus as ApiEndpointStatus,
)
from adapta.models.generated import (
    Modality as ApiModality,
)
from adapta.models.generated import (
    ProjectType as ApiProjectType,
)
from adapta.services.auth import get_current_user, require_team_member, require_team_writer
from adapta.services.rag import count_project_chunks

router = APIRouter(prefix="/projects/{project_id}/endpoint", tags=["endpoints"])


async def _get_project(db: AsyncSession, project_id: str) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFound(message=f"Project not found: {project_id}")
    return project


def _modality_for(base_model: str) -> str:
    try:
        from adapta.core.model_catalog import all_entries

        for e in all_entries():
            if e.name == base_model:
                return e.modality
    except Exception:
        pass
    return "text"


async def _build_response(
    db: AsyncSession,
    ep: Endpoint,
    project: Project,
) -> EndpointResponse:
    """Build the endpoint response (retrieval summary from the vector store)."""
    retrieval: Optional[RetrievalSummary] = None

    indexed_chunks = await count_project_chunks(db, project.id)
    if indexed_chunks > 0:
        retrieval = RetrievalSummary(indexed_chunks=indexed_chunks)

    project_type = project.type.value if hasattr(project.type, "value") else str(project.type)
    return EndpointResponse(
        id=ep.id,
        slug=ep.slug,
        status=ApiEndpointStatus(
            ep.status.value if hasattr(ep.status, "value") else str(ep.status)
        ),
        base_model=ep.base_model,
        modality=ApiModality(_modality_for(ep.base_model)),
        project_type=ApiProjectType(project_type),
        created_at=ep.created_at.isoformat(),
        retrieval=retrieval,
        adapter_path=ep.adapter_path,
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
    - Fine-tune: needs an imported adapter that passed the gate (not yet available).
    """
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)

    ep_result = await db.execute(select(Endpoint).where(Endpoint.project_id == project_id))
    existing = ep_result.scalar_one_or_none()
    if existing:
        raise InvalidRequest(message="Endpoint already exists for this project")

    if project.type == ProjectType.rag:
        if await count_project_chunks(db, project_id) == 0:
            raise InvalidRequest(
                message="No indexed documents found. Upload and index files first."
            )

    elif project.type == ProjectType.finetune:
        raise InvalidRequest(message="Import an adapter first")

    import re

    base = re.sub(r"[^a-z0-9-]", "-", project.name.lower()).strip("-")[:55] or "endpoint"
    suffix = project.id.replace("-", "")[:8]
    slug = f"{base}-{suffix}"

    endpoint = Endpoint(
        project_id=project_id,
        slug=slug,
        status=EndpointStatus.active,
        base_model=project.base_model,
    )
    db.add(endpoint)
    project.status = ProjectStatus.ready
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict(
            message="Endpoint slug already in use; could not create endpoint.",
            internal_detail=f"IntegrityError creating endpoint for project {project_id}: {exc}",
        ) from exc
    return await _build_response(db, endpoint, project)


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
    return await _build_response(db, endpoint, project)
