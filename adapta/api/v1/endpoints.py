"""Project endpoint management (create, get, enable/disable)."""

import json
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.db.models import (
    Collection,
    Endpoint,
    EndpointStatus,
    JobStatus,
    Project,
    ProjectStatus,
    ProjectType,
    TrainingJob,
)
from adapta.db.session import get_db
from adapta.domain.errors import Conflict, InvalidRequest, NotFound
from adapta.models.generated import (
    AdapterProvenance,
    EndpointResponse,
    Gate,
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
    """Populate v2 provenance fields from the DB."""
    adapter: Optional[AdapterProvenance] = None
    retrieval: Optional[RetrievalSummary] = None

    if ep.adapter_path:
        # Find the most recent succeeded job that owns this adapter.
        job_result = await db.execute(
            select(TrainingJob)
            .where(
                TrainingJob.project_id == project.id,
                TrainingJob.status == JobStatus.succeeded,
                TrainingJob.eval_passed.is_(True),
            )
            .order_by(TrainingJob.created_at.desc())
        )
        job = job_result.scalars().first()
        if job:
            base_score: Optional[float] = None
            score_delta: Optional[float] = None
            gate = "absolute"
            if job.eval_metrics:
                try:
                    m = json.loads(job.eval_metrics)
                    base_score = m.get("base_score")
                    score_delta = m.get("score_delta")
                    if base_score is not None and score_delta is not None:
                        gate = "improvement"
                except Exception:
                    pass
            adapter = AdapterProvenance(
                job_id=job.id,
                eval_score=job.eval_score or 0.0,
                base_score=base_score,
                score_delta=score_delta,
                gate=Gate(gate),
            )

    # Retrieval layer: any project can also have indexed documents.
    col_result = await db.execute(select(Collection).where(Collection.project_id == project.id))
    collection = col_result.scalar_one_or_none()
    if collection and collection.num_chunks > 0:
        retrieval = RetrievalSummary(indexed_chunks=collection.num_chunks)

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
        adapter=adapter,
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
    - Fine-tune: project must have a succeeded training job with eval_passed=True.
    """
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)

    ep_result = await db.execute(select(Endpoint).where(Endpoint.project_id == project_id))
    existing = ep_result.scalar_one_or_none()
    if existing:
        raise InvalidRequest(message="Endpoint already exists for this project")

    adapter_path = None

    if project.type == ProjectType.rag:
        col_result = await db.execute(select(Collection).where(Collection.project_id == project_id))
        collection = col_result.scalar_one_or_none()
        if not collection or collection.num_chunks == 0:
            raise InvalidRequest(
                message="No indexed documents found. Upload and index files first."
            )

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

    base = re.sub(r"[^a-z0-9-]", "-", project.name.lower()).strip("-")[:55] or "endpoint"
    suffix = project.id.replace("-", "")[:8]
    slug = f"{base}-{suffix}"

    endpoint = Endpoint(
        project_id=project_id,
        slug=slug,
        status=EndpointStatus.active,
        base_model=project.base_model,
        adapter_path=adapter_path,
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
