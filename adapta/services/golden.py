"""The RAG gate (E5.2): a per-project golden retrieval set scored as recall@5 / MRR.

The fine-tune gate stops a bad adapter from serving; this is the retrieval counterpart. It
never blocks - it *warns* when a re-index or a config change makes retrieval measurably worse.

Shared with the offline golden harness (``tests/integration/test_rag_golden.py``): the
scoring primitives :func:`first_rank` and :func:`summarize` are the single implementation of
recall@k / MRR / p50, and the question rows are the E3.8 / E4.8 ``rag_eval`` shape
``{q, expected_file, lang?, expected_page?}``.

Flow: the API stores the set as a ``rag_eval`` :class:`Dataset` and points
``projects.golden_dataset_id`` at it; a run is a :class:`RagEvalRun` row plus a ``rag_eval``
worker job (:func:`process_run`). A run is queued by ``POST .../golden/run`` and, when a
golden set exists, after every successful index job (:func:`enqueue_after_index`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.db.models import (
    Dataset,
    DatasetStatus,
    Project,
    ProjectFile,
    RagEvalRun,
    RagEvalRunStatus,
)
from adapta.domain.errors import InvalidRequest

logger = logging.getLogger(__name__)

GOLDEN_JOB_KIND = "rag_eval"
GOLDEN_K = 5
MIN_QUESTIONS = 1
MAX_QUESTIONS = 200
# Noise handling. Retrieval is not bit-for-bit repeatable (RRF ties, per-project chunk ids),
# so a run is judged against the *median of the previous BASELINE_RUNS runs* on the same
# golden set, and flagged only when recall fell by more than one question's worth
# (1/n) AND more than REGRESSION_FLOOR. A single flipped question never raises the chip.
BASELINE_RUNS = 3
REGRESSION_FLOOR = 0.05
# A queued/running run older than this is presumed lost (worker died); it no longer blocks.
STALE_RUN_AFTER = timedelta(minutes=15)


# ── scoring primitives (shared with the offline harness) ─────────────────────────────────


def first_rank(sources: Sequence[str], expected: str) -> Optional[int]:
    """1-based rank of the first chunk from ``expected``; None when absent."""
    for i, src in enumerate(sources, start=1):
        if src == expected:
            return i
    return None


def summarize(rows: Sequence[dict], k: int = GOLDEN_K) -> dict:
    """recall@k, MRR and p50 latency over rows carrying ``rank`` (int | None) and ``ms``."""
    n = len(rows)
    hits = sum(1 for r in rows if r["rank"] is not None and r["rank"] <= k)
    rr = sum(1.0 / r["rank"] for r in rows if r["rank"] is not None)
    return {
        "n": n,
        "recall": hits / n if n else 0.0,
        "mrr": rr / n if n else 0.0,
        "p50_ms": statistics.median(r["ms"] for r in rows) if rows else 0.0,
    }


def judge(recall: float, n: int, previous: Sequence[float]) -> tuple[Optional[float], Optional[float], bool]:
    """``(baseline, delta, regression)`` of a finished run against the previous runs' recalls.

    ``previous`` is newest-first; only the first :data:`BASELINE_RUNS` count. No history ->
    ``(None, None, False)``.
    """
    window = list(previous)[:BASELINE_RUNS]
    if not window or n <= 0:
        return None, None, False
    baseline = statistics.median(window)
    delta = round(recall - baseline, 4)
    threshold = max(REGRESSION_FLOOR, 1.0 / n)
    return round(baseline, 4), delta, (-delta) > threshold + 1e-9


# ── question files ───────────────────────────────────────────────────────────────────────


def parse_questions(text: str) -> list[dict]:
    """Parse and validate golden-set JSONL; raises a typed 400 naming the first bad line."""
    rows: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            raise InvalidRequest(message=f"Line {lineno} is not valid JSON.") from None
        if not isinstance(obj, dict):
            raise InvalidRequest(message=f"Line {lineno} must be a JSON object.")
        q, expected = obj.get("q"), obj.get("expected_file")
        if not (isinstance(q, str) and q.strip()):
            raise InvalidRequest(message=f"Line {lineno}: 'q' must be a non-empty string.")
        if not (isinstance(expected, str) and expected.strip()):
            raise InvalidRequest(
                message=f"Line {lineno}: 'expected_file' must be the filename of the answering document."
            )
        lang = obj.get("lang")
        rows.append(
            {
                "q": q.strip(),
                "expected_file": expected.strip(),
                "lang": lang if isinstance(lang, str) else None,
            }
        )
    if not MIN_QUESTIONS <= len(rows) <= MAX_QUESTIONS:
        raise InvalidRequest(
            message=f"A golden set needs {MIN_QUESTIONS}-{MAX_QUESTIONS} questions; this one has {len(rows)}."
        )
    return rows


def load_questions(path: str | Path) -> list[dict]:
    return parse_questions(Path(path).read_text(encoding="utf-8"))


async def load_golden_set(db: AsyncSession, project: Project) -> Optional[Dataset]:
    """The project's golden dataset, or None (unset, deleted, or no longer valid)."""
    if not project.golden_dataset_id:
        return None
    ds = (
        await db.execute(
            select(Dataset).where(
                Dataset.id == project.golden_dataset_id, Dataset.project_id == project.id
            )
        )
    ).scalar_one_or_none()
    if ds is None or ds.status != DatasetStatus.valid or not ds.storage_path:
        return None
    return ds


# ── runs ─────────────────────────────────────────────────────────────────────────────────


async def active_run(db: AsyncSession, project_id: str, *, only_queued: bool = False) -> Optional[RagEvalRun]:
    """A fresh queued (or running) run of the project, if any."""
    states = [RagEvalRunStatus.queued] if only_queued else [RagEvalRunStatus.queued, RagEvalRunStatus.running]
    cutoff = datetime.now(timezone.utc) - STALE_RUN_AFTER
    return (
        await db.execute(
            select(RagEvalRun)
            .where(
                RagEvalRun.project_id == project_id,
                RagEvalRun.status.in_(states),
                RagEvalRun.created_at > cutoff,
            )
            .order_by(RagEvalRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def queue_run(db: AsyncSession, project: Project, ds: Dataset, trigger: str) -> RagEvalRun:
    """Create a ``queued`` run, commit, then enqueue its worker job (commit first: the worker
    opens its own session). A dead queue marks the run failed instead of leaving it queued."""
    from adapta.services.jobs import get_job_queue

    run = RagEvalRun(project_id=project.id, dataset_id=ds.id, trigger=trigger, k=GOLDEN_K)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    try:
        await get_job_queue().enqueue(run.id, GOLDEN_JOB_KIND, {"id": run.id})
    except Exception:
        logger.exception("Could not enqueue the RAG-gate job for run %s", run.id)
        run.status = RagEvalRunStatus.failed
        run.error = "The job queue is unavailable; run the gate again."
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(run)
    return run


async def enqueue_after_index(file_id: str) -> None:
    """Worker hook: after a file indexed, queue a gate run if the project has a golden set.

    Best effort (never fails the index job). A run that is still *queued* will see this
    file's chunks when it starts, so only one is queued per burst of uploads.
    """
    from adapta.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(ProjectFile.project_id, ProjectFile.status).where(ProjectFile.id == file_id)
                )
            ).first()
            if row is None or getattr(row.status, "value", row.status) != "indexed":
                return
            project = (await db.execute(select(Project).where(Project.id == row.project_id))).scalar_one_or_none()
            if project is None:
                return
            ds = await load_golden_set(db, project)
            if ds is None or await active_run(db, project.id, only_queued=True) is not None:
                return
            await queue_run(db, project, ds, "index")
    except Exception:  # noqa: BLE001
        logger.exception("Could not queue the RAG gate after indexing %s", file_id)


async def _fail(db: AsyncSession, run: RagEvalRun, message: str) -> None:
    run.status = RagEvalRunStatus.failed
    run.error = message
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()


async def process_run(run_id: str) -> None:
    """``rag_eval`` job body: retrieve every golden question with the serving config, score,
    judge against earlier runs, store metrics + per-question hits. Never raises for a bad
    set or an empty index - those end the run ``failed`` with a readable reason."""
    from adapta.config import settings
    from adapta.db.session import AsyncSessionLocal
    from adapta.services.app_settings import resolve_setting
    from adapta.services.rag import count_project_chunks, get_rag_service

    async with AsyncSessionLocal() as db:
        run = (await db.execute(select(RagEvalRun).where(RagEvalRun.id == run_id))).scalar_one_or_none()
        if run is None:
            logger.warning("RAG-gate run %s vanished before it started.", run_id)
            return
        run.status = RagEvalRunStatus.running
        await db.commit()

        project = (await db.execute(select(Project).where(Project.id == run.project_id))).scalar_one_or_none()
        ds = (
            await db.execute(select(Dataset).where(Dataset.id == run.dataset_id))
        ).scalar_one_or_none() if run.dataset_id else None
        if project is None or ds is None or not ds.storage_path:
            return await _fail(db, run, "The golden set no longer exists. Set it again.")
        try:
            questions = await asyncio.to_thread(load_questions, ds.storage_path)
        except (InvalidRequest, OSError) as exc:
            return await _fail(db, run, getattr(exc, "message", "The golden set could not be read."))
        if await count_project_chunks(db, project.id) == 0:
            return await _fail(db, run, "No indexed documents to retrieve from. Index documents first.")
        try:
            top_k = int(await resolve_setting(db, project.team_id, "rag_top_k"))
        except Exception:  # noqa: BLE001
            top_k = settings.rag_top_k

        rag = get_rag_service()
        rows: list[dict] = []
        try:
            for q in questions:
                t0 = time.perf_counter()
                # retrieve() is blocking and its sparse leg refuses to run on the event loop.
                chunks = await asyncio.to_thread(rag.retrieve, project.id, q["q"], top_k=top_k)
                ms = (time.perf_counter() - t0) * 1000
                rank = first_rank([c.source for c in chunks], q["expected_file"])
                rows.append({**q, "rank": rank, "ms": ms})
        except Exception:
            logger.exception("RAG-gate run %s failed while retrieving", run_id)
            return await _fail(db, run, "Retrieval failed during the run. Check GET /health/deep and run it again.")

        stats = summarize(rows, GOLDEN_K)
        previous = (
            await db.execute(
                select(RagEvalRun.recall)
                .where(
                    RagEvalRun.project_id == project.id,
                    RagEvalRun.dataset_id == ds.id,
                    RagEvalRun.status == RagEvalRunStatus.succeeded,
                    RagEvalRun.recall.is_not(None),
                    RagEvalRun.id != run.id,
                )
                .order_by(RagEvalRun.created_at.desc())
                .limit(BASELINE_RUNS)
            )
        ).scalars().all()
        baseline, delta, regression = judge(
            stats["recall"], stats["n"], [x for x in previous if x is not None]
        )

        run.n_questions = stats["n"]
        run.recall = round(stats["recall"], 4)
        run.mrr = round(stats["mrr"], 4)
        run.p50_ms = round(stats["p50_ms"], 1)
        run.baseline_recall, run.delta, run.regression = baseline, delta, regression
        run.questions = [
            {
                "q": r["q"],
                "expected_file": r["expected_file"],
                "lang": r["lang"],
                "rank": r["rank"],
                "hit": r["rank"] is not None and r["rank"] <= GOLDEN_K,
                "ms": round(r["ms"], 1),
            }
            for r in rows
        ]
        run.status = RagEvalRunStatus.succeeded
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(
            "rag_eval run=%s project=%s n=%d recall@%d=%.3f mrr=%.3f baseline=%s regression=%s",
            run.id, project.id, stats["n"], GOLDEN_K, stats["recall"], stats["mrr"], baseline, regression,
        )


# ── read side (endpoint summary) ─────────────────────────────────────────────────────────


async def latest_quality(db: AsyncSession, project_id: str) -> Optional[dict]:
    """Fields for ``RetrievalSummary.quality``: the newest succeeded run (+ whether a newer
    one is in flight), or None before the first finished run."""
    last = (
        await db.execute(
            select(RagEvalRun)
            .where(RagEvalRun.project_id == project_id, RagEvalRun.status == RagEvalRunStatus.succeeded)
            .order_by(RagEvalRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is None or last.recall is None:
        return None
    return {
        "run_id": last.id,
        "recall_at_5": last.recall,
        "mrr": last.mrr or 0.0,
        "n_questions": last.n_questions or 0,
        "run_at": (last.finished_at or last.created_at).isoformat(),
        "baseline_recall": last.baseline_recall,
        "delta": last.delta,
        "regression": last.regression,
        "running": await active_run(db, project_id) is not None,
    }
