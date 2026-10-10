"""RAG gate (E5.2): the project's golden retrieval set and its recall@5 / MRR runs."""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.api._upload import save_capped_upload
from adapta.config import settings
from adapta.db.models import Dataset, DatasetStatus, Project, RagEvalRun
from adapta.db.session import get_db
from adapta.domain.errors import InvalidRequest, NotFound
from adapta.models.generated import (
    GoldenQuestionResult,
    GoldenResults,
    GoldenRun,
    GoldenSetResponse,
)
from adapta.models.generated import Status as ApiRunStatus
from adapta.models.generated import Trigger as ApiTrigger
from adapta.services import golden as golden_service
from adapta.services.auth import get_current_user, require_team_member, require_team_writer

router = APIRouter(prefix="/projects/{project_id}/golden", tags=["golden"])


async def _get_project(db: AsyncSession, project_id: str) -> Project:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise NotFound(message=f"Project not found: {project_id}")
    return project


def _set_response(ds: Dataset) -> GoldenSetResponse:
    return GoldenSetResponse(dataset_id=ds.id, name=ds.name, num_questions=ds.num_samples or 0)


def _run_response(r: RagEvalRun) -> GoldenRun:
    return GoldenRun(
        id=r.id,
        status=ApiRunStatus(r.status.value),
        trigger=ApiTrigger(r.trigger),
        dataset_id=r.dataset_id,
        k=r.k,
        n_questions=r.n_questions,
        recall_at_5=r.recall,
        mrr=r.mrr,
        p50_ms=r.p50_ms,
        baseline_recall=r.baseline_recall,
        delta=r.delta,
        regression=r.regression,
        error=r.error,
        created_at=r.created_at.isoformat(),
        finished_at=r.finished_at.isoformat() if r.finished_at else None,
        questions=[GoldenQuestionResult(**q) for q in (r.questions or [])],
    )


@router.post("", response_model=GoldenSetResponse)
async def set_golden_set(
    project_id: str,
    file: Optional[UploadFile] = File(None),
    dataset_id: Optional[str] = Form(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    if (file is None) == (dataset_id is None):
        raise InvalidRequest(message="Send exactly one of 'file' (.jsonl) or 'dataset_id'.")

    if dataset_id is not None:
        ds = (
            await db.execute(
                select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
            )
        ).scalar_one_or_none()
        if ds is None:
            raise NotFound(message=f"Dataset not found: {dataset_id}")
        if ds.kind != "rag_eval" or ds.status != DatasetStatus.valid or not ds.storage_path:
            raise InvalidRequest(message="The dataset must be a valid 'rag_eval' set.")
        questions = await asyncio.to_thread(golden_service.load_questions, ds.storage_path)
        ds.num_samples = len(questions)
    else:
        assert file is not None
        filename = (file.filename or "golden.jsonl")[-200:]
        if not filename.endswith(".jsonl"):
            raise InvalidRequest(message="The golden set must be a .jsonl file.")
        ds_dir = settings.datasets_dir / project_id
        ds_dir.mkdir(parents=True, exist_ok=True)
        new_id = str(uuid.uuid4())
        dest = ds_dir / f"{new_id}_{filename}"
        await save_capped_upload(file, dest)
        try:
            questions = await asyncio.to_thread(golden_service.load_questions, dest)
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
        ds = Dataset(
            id=new_id,
            project_id=project_id,
            name=filename,
            storage_path=str(dest),
            status=DatasetStatus.valid,
            num_samples=len(questions),
            kind="rag_eval",
            task=None,
        )
        db.add(ds)

    project.golden_dataset_id = ds.id
    await db.commit()  # durable before the response and before any run reads it
    return _set_response(ds)


@router.post("/run", response_model=GoldenRun, status_code=202)
async def run_golden(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    ds = await golden_service.load_golden_set(db, project)
    if ds is None:
        raise InvalidRequest(message="This project has no golden set yet. Upload one first.")
    run = await golden_service.active_run(db, project_id)
    if run is None:
        run = await golden_service.queue_run(db, project, ds, "manual")
    return _run_response(run)


@router.get("/results", response_model=GoldenResults)
async def golden_results(
    project_id: str,
    limit: int = Query(10, ge=1, le=50),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    ds = await golden_service.load_golden_set(db, project)
    runs = (
        await db.execute(
            select(RagEvalRun)
            .where(RagEvalRun.project_id == project_id)
            .order_by(RagEvalRun.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return GoldenResults(
        golden_set=_set_response(ds) if ds is not None else None,
        runs=[_run_response(r) for r in runs],
    )
