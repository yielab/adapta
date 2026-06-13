"""POST /projects/{project_id}/datasets/synthesize — generate a dataset from indexed docs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from brain.db.models import Collection, Dataset, DatasetStatus, Project, ProjectType
from brain.db.session import get_db
from brain.domain.errors import InvalidRequest, ProjectNotFound
from brain.services.auth import get_current_user, require_team_writer

router = APIRouter()


class SynthesizeRequest(BaseModel):
    n_pairs_per_chunk: int = Field(default=3, ge=1, le=10)
    max_chunks: int = Field(default=50, ge=1, le=500)
    system_prompt: Optional[str] = Field(default=None, max_length=1000)
    base_model: Optional[str] = None


class SynthesizeResponse(BaseModel):
    dataset_id: str
    status: str
    message: str


async def _run_synthesis(
    project_id: str,
    dataset_id: str,
    req: SynthesizeRequest,
    db_url: str,
) -> None:
    """Background task: run synthesis and update the Dataset record."""
    from sqlalchemy.ext.asyncio import AsyncSession as _AS
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from brain.domain.errors import DomainError
    from brain.services.synthesis import synthesize_from_project

    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(engine, class_=_AS, expire_on_commit=False)

    async with async_session() as db:
        try:
            _path, count = await synthesize_from_project(
                project_id=project_id,
                n_pairs_per_chunk=req.n_pairs_per_chunk,
                max_chunks=req.max_chunks,
                system_prompt=req.system_prompt,
                base_model=req.base_model,
            )
            result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
            ds = result.scalar_one_or_none()
            if ds:
                ds.storage_path = str(_path)
                ds.num_samples = count
                ds.status = DatasetStatus.valid
                await db.commit()
        except DomainError as exc:
            result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
            ds = result.scalar_one_or_none()
            if ds:
                ds.status = DatasetStatus.invalid
                ds.validation_error = exc.message
                await db.commit()
        except Exception:
            result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
            ds = result.scalar_one_or_none()
            if ds:
                ds.status = DatasetStatus.invalid
                ds.validation_error = "Synthesis failed"
                await db.commit()
    await engine.dispose()


@router.post(
    "/projects/{project_id}/datasets/synthesize",
    response_model=SynthesizeResponse,
    status_code=202,
    tags=["datasets"],
    summary="Synthesize an instruction dataset from indexed documents",
)
async def synthesize_dataset(
    project_id: str,
    req: SynthesizeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SynthesizeResponse:
    # Load project and verify access
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ProjectNotFound(message=f"Project {project_id} not found")
    await require_team_writer(db, current_user.id, project.team_id)

    if project.type != ProjectType.finetune:
        raise InvalidRequest(message="Dataset synthesis is only available for finetune projects")

    # Verify the project has an indexed collection
    coll_result = await db.execute(select(Collection).where(Collection.project_id == project_id))
    collection = coll_result.scalar_one_or_none()
    if not collection or collection.num_chunks == 0:
        raise InvalidRequest(message="No indexed documents found. Upload and index files first.")

    # Create a placeholder Dataset record (status=synthesizing)
    dataset_id = str(uuid.uuid4())
    ds = Dataset(
        id=dataset_id,
        project_id=project_id,
        name=f"synthesized_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        storage_path="",  # filled in by background task
        status=DatasetStatus.validating,
    )
    db.add(ds)
    await db.commit()

    from brain.config import settings

    background_tasks.add_task(
        _run_synthesis,
        project_id=project_id,
        dataset_id=dataset_id,
        req=req,
        db_url=settings.database_url,
    )

    return SynthesizeResponse(
        dataset_id=dataset_id,
        status=DatasetStatus.validating,
        message=f"Synthesis started. Poll GET /v1/projects/{project_id}/datasets/{dataset_id} for status.",
    )
