"""Dataset upload + validation for fine-tune projects."""

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.config import settings
from adapta.db.models import Dataset, DatasetStatus, Project, ProjectType
from adapta.db.session import get_db
from adapta.domain.errors import InvalidRequest, NotFound
from adapta.models.generated import (
    DatasetCurateRequest,
    DatasetResponse,
    DatasetRowsResponse,
    Modality,
)
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
        source_dataset_id=d.source_dataset_id,
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


async def _get_valid_dataset(db: AsyncSession, project_id: str, dataset_id: str) -> Dataset:
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise NotFound(message="Dataset not found")
    if dataset.status != DatasetStatus.valid:
        raise InvalidRequest(
            message=f"Dataset is not valid (status: {dataset.status.value}). "
            "Only valid datasets can be reviewed or curated."
        )
    return dataset


def _read_jsonl(path: str) -> list[dict]:
    """Read all rows from a JSONL file, skipping blank lines."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@router.get("/{dataset_id}/rows", response_model=DatasetRowsResponse)
async def get_dataset_rows(
    project_id: str,
    dataset_id: str,
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=100, ge=1, le=500),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a page of JSONL rows from a valid dataset (D6 review)."""
    project = await _get_finetune_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    dataset = await _get_valid_dataset(db, project_id, dataset_id)

    rows = await asyncio.to_thread(_read_jsonl, dataset.storage_path)
    total = len(rows)
    start = page * page_size
    page_rows = rows[start : start + page_size]
    return DatasetRowsResponse(rows=page_rows, total=total, page=page, page_size=page_size)


@router.post("/{dataset_id}/curate", response_model=DatasetResponse, status_code=201)
async def curate_dataset(
    project_id: str,
    dataset_id: str,
    body: DatasetCurateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save curated rows as a new valid dataset derived from dataset_id (D6 review)."""
    project = await _get_finetune_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    source = await _get_valid_dataset(db, project_id, dataset_id)

    if not body.rows:
        raise InvalidRequest(message="rows must not be empty")

    # Write rows to a temp file and validate against the training dataset schema.
    # Use a temp path so we never leave a partial file in the datasets dir on error.
    ds_dir = settings.datasets_dir / project_id
    ds_dir.mkdir(parents=True, exist_ok=True)

    def _write_and_validate() -> tuple[bool, str | None, int, int, Path]:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", dir=ds_dir, delete=False, encoding="utf-8"
        ) as tmp:
            tmp_path = Path(tmp.name)
            for row in body.rows:
                tmp.write(json.dumps(row) + "\n")
        is_valid, error, num_samples, num_images = validate_dataset(tmp_path)
        return is_valid, error, num_samples, num_images or 0, tmp_path

    is_valid, error, num_samples, num_images, tmp_path = await asyncio.to_thread(
        _write_and_validate
    )

    if not is_valid:
        tmp_path.unlink(missing_ok=True)
        raise InvalidRequest(message=f"Curated rows failed validation: {error}")

    # Move the temp file to its permanent name now that validation passed.
    final_name = f"curated_{source.name}"[-200:]  # keep extension, cap length
    final_path = ds_dir / final_name
    # Avoid collisions by appending the new dataset id (determined after flush).
    curated = Dataset(
        project_id=project_id,
        name=final_name,
        storage_path="",  # filled after flush gives us the id
        status=DatasetStatus.valid,
        num_samples=num_samples,
        num_images=num_images if num_images else None,
        modality="vision" if num_images else "text",
        source_dataset_id=source.id,
    )
    db.add(curated)
    await db.flush()  # assigns curated.id

    final_path = ds_dir / f"{curated.id}_{final_name}"
    tmp_path.rename(final_path)
    curated.storage_path = str(final_path)
    await db.commit()

    logger.info("Curated dataset %s created from %s (%d rows)", curated.id, source.id, num_samples)
    return _ds_resp(curated)
