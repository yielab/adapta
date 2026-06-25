"""Dataset upload + validation for fine-tune projects."""

import asyncio
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.config import settings
from adapta.db.models import Dataset, DatasetStatus, Project, ProjectType
from adapta.db.session import get_db
from adapta.domain.errors import InvalidRequest, NotFound
from adapta.models.generated import DatasetResponse, Modality
from adapta.services.auth import get_current_user, require_team_member, require_team_writer
from adapta.services.training import validate_dataset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/datasets", tags=["datasets"])


def _ds_resp(d: Dataset) -> DatasetResponse:
    return DatasetResponse(
        id=d.id,
        name=d.name,
        status=d.status.value,
        num_samples=d.num_samples,
        modality=Modality(d.modality),
        num_images=d.num_images,
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


async def _validate_in_background(dataset_id: str, path: Path, is_bundle: bool = False) -> None:
    """Validate an uploaded dataset out-of-band and record the terminal status.

    Runs in its own DB session (the request's session is already closed). The row
    is committed by the request handler *before* this task is scheduled, but a
    freshly-pooled connection can briefly lag the commit, so the lookup retries a
    few times rather than returning silently (which left datasets stuck at
    ``validating`` — see TODO §4.4).
    """
    from sqlalchemy import select

    from adapta.db.session import AsyncSessionLocal

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
                    "status will remain 'validating'.",
                    dataset_id,
                )
                return

            manifest, bundle_dir = path, None
            if is_bundle:
                # Extract the zip beside it (zip-slip/caps enforced) and validate
                # the manifest against the extracted images (§V2.1).
                from adapta.services.training import BundleError, extract_bundle

                bundle_dir = path.parent / f"{dataset_id}_bundle"
                try:
                    manifest = extract_bundle(path, bundle_dir)
                except BundleError as exc:
                    dataset.status = DatasetStatus.invalid
                    dataset.validation_error = str(exc)
                    await db.commit()
                    logger.info("Dataset bundle rejected: %s — %s", dataset_id, exc)
                    return

            is_valid, error, num_samples, num_images = validate_dataset(
                manifest, bundle_dir=bundle_dir
            )
            dataset.status = DatasetStatus.valid if is_valid else DatasetStatus.invalid
            dataset.validation_error = error
            dataset.num_samples = num_samples
            dataset.num_images = num_images or None
            dataset.modality = "vision" if num_images else "text"
            if is_valid and is_bundle:
                # Training (§V3) reads the manifest; images resolve relative to it.
                dataset.storage_path = str(manifest)
            await db.commit()
            logger.info(
                "Dataset validation task done: %s -> %s (%s samples, %s images)",
                dataset_id,
                dataset.status.value,
                num_samples,
                num_images,
            )
    except Exception:
        logger.exception("Dataset validation task crashed for %s", dataset_id)
        # Never leave the dataset stuck at 'validating' on an unexpected failure —
        # the operator must see a terminal status. Best-effort mark it invalid.
        try:
            async with AsyncSessionLocal() as db2:
                result = await db2.execute(select(Dataset).where(Dataset.id == dataset_id))
                d = result.scalar_one_or_none()
                if d is not None and d.status == DatasetStatus.validating:
                    d.status = DatasetStatus.invalid
                    d.validation_error = "Validation failed due to an internal error."
                    await db2.commit()
        except Exception:
            logger.exception("Could not mark dataset %s invalid after crash", dataset_id)


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
    is_bundle = filename.endswith(".zip")
    if not filename.endswith(".jsonl") and not is_bundle:
        raise InvalidRequest(
            message="Dataset must be a .jsonl file, or a .zip bundle (one root "
            ".jsonl manifest + the images it references) for image datasets."
        )
    # Truncate from the front (keeps the extension): the name is metadata, and an
    # over-long one would overflow datasets.name String(256) → 500.
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

    # Stream to disk with a HARD cap so a hostile/oversized upload can't fill the disk
    # before validation runs (Content-Length is client-controlled; count real bytes).
    dest = ds_dir / f"{dataset.id}_{filename}"
    max_upload = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_upload:
                    raise InvalidRequest(
                        message=f"Upload exceeds the {settings.max_upload_mb} MB limit"
                    )
                out.write(chunk)
    except InvalidRequest:
        dest.unlink(missing_ok=True)  # drop the partial; the uncommitted row rolls back
        raise

    dataset.storage_path = str(dest)
    # Commit now so the row is durable BEFORE the background task is scheduled —
    # otherwise the task's fresh session races the request's deferred commit,
    # finds nothing, and the dataset is stuck at 'validating' forever (§4.4).
    dataset_id = dataset.id
    await db.commit()
    background_tasks.add_task(_validate_in_background, dataset_id, dest, is_bundle)

    return {"id": dataset_id, "name": filename, "status": "validating"}


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
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise NotFound(message="Dataset not found")
    return _ds_resp(dataset)
