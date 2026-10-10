"""Adapter import (E4.2): upload a LoRA, list it, read its gate status, delete it.

Static validation only — the adapter lands ``uploaded``; scoring and the
``processing -> passed | failed`` transitions belong to the adapter job (E4.4).
"""

import asyncio
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.api._upload import save_capped_upload
from adapta.config import settings
from adapta.db.models import (
    Adapter,
    AdapterStatus,
    Dataset,
    DatasetStatus,
    Endpoint,
    Project,
    ProjectType,
)
from adapta.db.session import get_db
from adapta.domain.errors import AdapterInUse, InvalidAdapter, InvalidRequest, NotFound
from adapta.models.generated import AdapterFormat as ApiAdapterFormat
from adapta.models.generated import AdapterResponse
from adapta.models.generated import AdapterStatus as ApiAdapterStatus
from adapta.services import adapters as adapter_service
from adapta.services.auth import get_current_user, require_team_member, require_team_writer

router = APIRouter(prefix="/projects/{project_id}/adapters", tags=["adapters"])


def adapter_response(a: Adapter) -> AdapterResponse:
    """The API shape of an Adapter row (shared with the endpoints router)."""
    return AdapterResponse(
        id=a.id,
        project_id=a.project_id,
        name=a.name,
        base_model=a.base_model,
        format=ApiAdapterFormat(a.format.value),
        sha256=a.sha256,
        size_bytes=a.size_bytes,
        eval_dataset_id=a.eval_dataset_id,
        status=ApiAdapterStatus(a.status.value),
        failure_reason=a.failure_reason,
        eval_metrics=a.eval_metrics,
        created_at=a.created_at.isoformat(),
    )


async def _get_finetune_project(db: AsyncSession, project_id: str) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFound(message=f"Project not found: {project_id}")
    if project.type != ProjectType.finetune:
        raise InvalidRequest(message="This endpoint is for fine-tune projects only")
    return project


async def _get_adapter(db: AsyncSession, project_id: str, adapter_id: str) -> Adapter:
    result = await db.execute(
        select(Adapter).where(Adapter.id == adapter_id, Adapter.project_id == project_id)
    )
    adapter = result.scalar_one_or_none()
    if not adapter:
        raise NotFound(message="Adapter not found")
    return adapter


@router.post("", response_model=AdapterResponse, status_code=202)
async def upload_adapter(
    project_id: str,
    file: UploadFile = File(...),
    eval_dataset_id: str = Form(...),
    name: str = Form(default=""),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_finetune_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)

    filename = file.filename or "adapter"
    # Extension check first: cheap, and spares streaming a wrong file type to disk.
    adapter_service.format_for_filename(filename)

    ds_result = await db.execute(
        select(Dataset).where(Dataset.id == eval_dataset_id, Dataset.project_id == project_id)
    )
    dataset = ds_result.scalar_one_or_none()
    if dataset is None:
        raise InvalidAdapter(
            message="eval_dataset_id must be the id of a dataset in this project "
            f"(got {eval_dataset_id!r})."
        )
    if dataset.status != DatasetStatus.valid:
        raise InvalidAdapter(
            message="The eval dataset must have status 'valid' "
            f"(it is '{dataset.status.value}'); wait for validation or upload another."
        )

    adapter_id = str(uuid.uuid4())
    upload_path = adapter_service.adapter_dir(adapter_id) / "upload"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Hard cap while streaming (413 over the limit); the helper drops the partial file.
        await save_capped_upload(file, upload_path, max_upload_mb=settings.adapter_max_upload_mb)
        stored = await asyncio.to_thread(
            adapter_service.validate_and_store,
            upload_path,
            filename,
            project.base_model,
            adapter_id,
        )
    except BaseException:
        adapter_service.remove_adapter_files(adapter_id)
        raise

    adapter = Adapter(
        id=adapter_id,
        project_id=project_id,
        name=(name.strip() or filename)[:128],
        base_model=stored.base_model,
        format=stored.format,
        peft_dir=str(stored.peft_dir) if stored.peft_dir else None,
        gguf_path=str(stored.gguf_path) if stored.gguf_path else None,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        eval_dataset_id=eval_dataset_id,
        status=AdapterStatus.uploaded,
        created_by=current_user.id,
    )
    db.add(adapter)
    try:
        await db.commit()  # durable before the response (and before any job reads it)
    except BaseException:
        adapter_service.remove_adapter_files(adapter_id)
        raise
    await db.refresh(adapter)
    return adapter_response(adapter)


@router.get("", response_model=List[AdapterResponse])
async def list_adapters(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_finetune_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    result = await db.execute(
        select(Adapter).where(Adapter.project_id == project_id).order_by(Adapter.created_at.desc())
    )
    return [adapter_response(a) for a in result.scalars().all()]


@router.get("/{adapter_id}", response_model=AdapterResponse)
async def get_adapter(
    project_id: str,
    adapter_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_finetune_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    return adapter_response(await _get_adapter(db, project_id, adapter_id))


@router.delete("/{adapter_id}", status_code=204)
async def delete_adapter(
    project_id: str,
    adapter_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_finetune_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    adapter = await _get_adapter(db, project_id, adapter_id)

    bound = await db.scalar(
        select(func.count()).select_from(Endpoint).where(Endpoint.adapter_id == adapter_id)
    )
    if bound:
        raise AdapterInUse(
            message="This adapter is bound to the project's endpoint; it cannot be deleted "
            "while the endpoint serves it."
        )
    await db.delete(adapter)
    await db.commit()
    adapter_service.remove_adapter_files(adapter_id)
