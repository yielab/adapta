"""Project endpoint management (create, get, enable/disable)."""

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from adapta.api.v1.adapters import adapter_response
from adapta.core import model_manager
from adapta.db.models import (
    Adapter,
    AdapterAction,
    AdapterEvent,
    AdapterStatus,
    Endpoint,
    EndpointStatus,
    Project,
    ProjectStatus,
    ProjectType,
)
from adapta.db.session import get_db
from adapta.domain.errors import Conflict, InvalidRequest, NotFound
from adapta.models.generated import (
    Action as ApiAction,
)
from adapta.models.generated import (
    AdapterEvent as ApiAdapterEvent,
)
from adapta.models.generated import (
    EndpointResponse,
    PromoteAdapterRequest,
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
from adapta.services import adapters as adapter_service
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
        adapter=adapter_response(ep.adapter) if ep.adapter is not None else None,
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
    - Fine-tune: serves the project's latest adapter that passed the gate (E4.2); with none,
      the request is refused.
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

    adapter_id: Optional[str] = None
    if project.type == ProjectType.finetune:
        passed = await db.execute(
            select(Adapter)
            .where(Adapter.project_id == project_id, Adapter.status == AdapterStatus.passed)
            .order_by(Adapter.created_at.desc())
            .limit(1)
        )
        adapter = passed.scalar_one_or_none()
        if adapter is None:
            raise InvalidRequest(
                message="No adapter has passed the eval gate yet. Import an adapter "
                "(POST /v1/projects/{id}/adapters) and wait for its status to be 'passed'."
            )
        adapter_id = adapter.id

    import re

    base = re.sub(r"[^a-z0-9-]", "-", project.name.lower()).strip("-")[:55] or "endpoint"
    suffix = project.id.replace("-", "")[:8]
    slug = f"{base}-{suffix}"

    endpoint = Endpoint(
        id=str(uuid.uuid4()),
        project_id=project_id,
        slug=slug,
        status=EndpointStatus.active,
        base_model=project.base_model,
        adapter_id=adapter_id,
    )
    db.add(endpoint)
    project.status = ProjectStatus.ready
    try:
        if adapter_id is not None:
            # The event FKs the endpoint row: flush it first, then open the audit trail.
            await db.flush()
            db.add(
                AdapterEvent(
                    endpoint_id=endpoint.id,
                    adapter_id=adapter_id,
                    action=AdapterAction.promote,
                    actor_user_id=current_user.id,
                )
            )
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


async def _get_endpoint(db: AsyncSession, project_id: str) -> Endpoint:
    result = await db.execute(select(Endpoint).where(Endpoint.project_id == project_id))
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise NotFound(message="No endpoint for this project. Create one first.")
    return endpoint


@router.post("/promote", response_model=EndpointResponse)
async def promote_adapter(
    project_id: str,
    body: PromoteAdapterRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-bind the endpoint to another `passed` adapter of this project (E4.5).

    Takes effect on the next chat request without a restart: chat resolves
    ``endpoint.adapter.gguf_path`` per request and the model cache is keyed on (base, adapter),
    so the new variant loads on demand; the previous variant is evicted. Promoting an adapter
    that served this endpoint before is recorded as a ``rollback``.
    """
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    endpoint = await _get_endpoint(db, project_id)
    if project.type != ProjectType.finetune:
        raise InvalidRequest(message="Only fine-tune endpoints serve an adapter.")

    result = await db.execute(
        select(Adapter).where(Adapter.id == body.adapter_id, Adapter.project_id == project_id)
    )
    adapter = result.scalar_one_or_none()
    if adapter is None:
        raise NotFound(message=f"Adapter not found: {body.adapter_id}")
    if adapter.status != AdapterStatus.passed:
        raise InvalidRequest(
            message=f"Only adapters that passed the eval gate can be promoted "
            f"(this one is '{adapter.status.value}')."
        )
    if endpoint.adapter_id == adapter.id:
        raise InvalidRequest(message="This adapter is already the one being served.")
    if not adapter.gguf_path:
        raise InvalidRequest(message="This adapter has no servable GGUF; re-import it.")

    served_before = await db.execute(
        select(AdapterEvent.id)
        .where(AdapterEvent.endpoint_id == endpoint.id, AdapterEvent.adapter_id == adapter.id)
        .limit(1)
    )
    action = (
        AdapterAction.rollback if served_before.first() is not None else AdapterAction.promote
    )
    old = endpoint.adapter
    old_path = old.gguf_path if old is not None else None

    endpoint.adapter_id = adapter.id
    endpoint.adapter = adapter
    db.add(
        AdapterEvent(
            endpoint_id=endpoint.id,
            adapter_id=adapter.id,
            action=action,
            actor_user_id=current_user.id,
        )
    )
    await db.commit()  # before evicting: no request may reload the old binding afterwards

    if old_path:
        await model_manager.evict(endpoint.base_model, old_path)
    return await _build_response(db, endpoint, project)


@router.get("/export", response_class=FileResponse)
async def export_adapter(
    project_id: str,
    format: Literal["ollama"],
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download the served adapter as an Ollama bundle (E2.2): ``adapter.gguf``, ``Modelfile``,
    ``README.txt``. Only a ``passed`` adapter bound to the endpoint can be exported."""
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    endpoint = await _get_endpoint(db, project_id)
    adapter = endpoint.adapter
    if adapter is None:
        raise NotFound(message="This endpoint serves no adapter to export.")
    tmp_dir = Path(tempfile.mkdtemp(prefix="adapta-export-"))
    try:
        bundle = adapter_service.build_ollama_bundle(adapter, tmp_dir / "bundle.zip")
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return FileResponse(
        bundle,
        media_type="application/zip",
        filename=f"{endpoint.slug}-ollama.zip",
        background=BackgroundTask(shutil.rmtree, tmp_dir, ignore_errors=True),
    )


@router.get("/history", response_model=list[ApiAdapterEvent])
async def endpoint_history(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Promotion / rollback audit trail, newest first."""
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    endpoint = await _get_endpoint(db, project_id)
    result = await db.execute(
        select(AdapterEvent)
        .where(AdapterEvent.endpoint_id == endpoint.id)
        .order_by(AdapterEvent.created_at.desc())
    )
    return [
        ApiAdapterEvent(
            id=e.id,
            endpoint_id=e.endpoint_id,
            adapter_id=e.adapter_id,
            adapter_name=e.adapter.name if e.adapter is not None else None,
            action=ApiAction(e.action.value),
            actor_user_id=e.actor_user_id,
            actor_email=e.actor.email if e.actor is not None else None,
            eval_metrics=e.adapter.eval_metrics if e.adapter is not None else None,
            created_at=e.created_at.isoformat(),
        )
        for e in result.scalars().all()
    ]
