"""Dataset upload + validation for fine-tune projects."""

import asyncio
import logging
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.config import settings
from brain.db.models import Dataset, DatasetStatus, Project, ProjectType
from brain.db.session import get_db
from brain.domain.errors import InvalidRequest, NotFound
from brain.services.auth import get_current_user, require_team_member, require_team_writer
from brain.services.training import validate_dataset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/datasets", tags=["datasets"])


class DatasetResponse(BaseModel):
    id: str
    name: str
    status: str
    num_samples: Optional[int]
    validation_error: Optional[str]
    created_at: str


def _ds_resp(d: Dataset) -> DatasetResponse:
    return DatasetResponse(
        id=d.id,
        name=d.name,
        status=d.status.value,
        num_samples=d.num_samples,
        validation_error=d.validation_error,
        created_at=d.created_at.isoformat(),
    )


async def _get_finetune_project(db: AsyncSession, project_id: str) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFound(message=f"Project not found: {project_id}")
    if project.type != ProjectType.finetune:
        raise InvalidRequest(message="This endpoint is for fine-tune projects only")
    return project


async def _validate_in_background(dataset_id: str, path: Path) -> None:
    """Validate an uploaded dataset out-of-band and record the terminal status.

    Runs in its own DB session (the request's session is already closed). The row
    is committed by the request handler *before* this task is scheduled, but a
    freshly-pooled connection can briefly lag the commit, so the lookup retries a
    few times rather than returning silently (which left datasets stuck at
    ``validating`` — see TODO §4.4).
    """
    from sqlalchemy import select

    from brain.db.session import AsyncSessionLocal

    logger.info("Dataset validation task started: %s", dataset_id)
    try:
        async with AsyncSessionLocal() as db:
            dataset = None
            for _ in range(10):
                result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
                dataset = result.scalar_one_or_none()
                if dataset is not None:
                    break
                await asyncio.sleep(0.1)
            if dataset is None:
                logger.error(
                    "Dataset validation task could not find row %s after retries — "
                    "status will remain 'validating'.", dataset_id,
                )
                return

            is_valid, error, num_samples = validate_dataset(path)
            dataset.status = DatasetStatus.valid if is_valid else DatasetStatus.invalid
            dataset.validation_error = error
            dataset.num_samples = num_samples
            await db.commit()
            logger.info(
                "Dataset validation task done: %s -> %s (%s samples)",
                dataset_id, dataset.status.value, num_samples,
            )
    except Exception:
        logger.exception("Dataset validation task crashed for %s", dataset_id)


@router.post("", status_code=202)
async def upload_dataset(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_finetune_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)

    filename = file.filename or "dataset.jsonl"
    if not filename.endswith(".jsonl"):
        raise InvalidRequest(message="Dataset must be a .jsonl file")
    # Truncate from the front (keeps the .jsonl suffix): the name is metadata,
    # and an over-long one would overflow datasets.name String(256) → 500.
    filename = filename[-200:]

    ds_dir = settings.datasets_dir / project_id
    ds_dir.mkdir(parents=True, exist_ok=True)

    dataset = Dataset(
        project_id=project_id,
        name=filename,
        storage_path="",
        status=DatasetStatus.validating,
    )
    db.add(dataset)
    await db.flush()

    dest = ds_dir / f"{dataset.id}_{file.filename}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    dataset.storage_path = str(dest)
    # Commit now so the row is durable BEFORE the background task is scheduled —
    # otherwise the task's fresh session races the request's deferred commit,
    # finds nothing, and the dataset is stuck at 'validating' forever (§4.4).
    dataset_id = dataset.id
    await db.commit()
    background_tasks.add_task(_validate_in_background, dataset_id, dest)

    return {"id": dataset_id, "name": file.filename, "status": "validating"}


@router.get("", response_model=List[DatasetResponse])
async def list_datasets(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_finetune_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    result = await db.execute(select(Dataset).where(Dataset.project_id == project_id))
    return [_ds_resp(d) for d in result.scalars().all()]


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    project_id: str,
    dataset_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_finetune_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    result = await db.execute(select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise NotFound(message="Dataset not found")
    return _ds_resp(dataset)
