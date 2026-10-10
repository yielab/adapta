"""Startup reconciliation for interrupted background work.

File indexing runs as an ``index`` job on the worker (E3.7); dataset validation runs
as a FastAPI BackgroundTask. If the worker or app dies mid-task, the row is left in a
transient state forever — a file stuck at ``processing``, a dataset at ``validating`` —
with no task alive to finish it. On app startup (and on worker startup, for files)
mark those orphans terminal so the operator sees a clear failure (and can re-upload)
instead of an indefinite spinner. A file whose index job is still ``queued`` in Redis
is NOT an orphan: the queue outlives the app and the worker will get to it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_FILE_MSG = "Indexing was interrupted by a server restart — re-upload the file to retry."
_ADAPTER_MSG = "Processing was interrupted by a restart — upload the adapter again to retry."
_DATASET_MSG = "Validation was interrupted by a server restart — re-upload the dataset to retry."


async def _job_is_live(file_id: str, *, worker_startup: bool) -> bool:
    """True when Redis still holds a live index job for this file.

    ``queued`` is always live. ``running`` is live only while a worker heartbeat is fresh —
    and never at worker startup, when by definition no job of this (single) worker is running.
    Redis being unreachable means nothing is live: the job could not run anyway.
    """
    from adapta.services.jobs import get_job_queue

    try:
        queue = get_job_queue()
        meta = await queue.get_status(file_id)
        if not meta:
            return False
        if meta.get("status") == "queued":
            return True
        if meta.get("status") == "running" and not worker_startup:
            return await queue.worker_alive()
    except Exception:  # noqa: BLE001 — a sweep must never fail on a Redis hiccup
        logger.warning("Sweep could not read the job state for %s", file_id)
    return False


async def sweep_stuck_files(*, worker_startup: bool = False) -> int:
    """Fail files left ``pending``/``processing`` with no live index job. Returns the count."""
    from sqlalchemy import select

    from adapta.db.models import FileStatus, ProjectFile
    from adapta.db.session import AsyncSessionLocal
    from adapta.services.jobs import get_job_queue

    swept: list[str] = []
    async with AsyncSessionLocal() as db:
        stuck = (
            (
                await db.execute(
                    select(ProjectFile).where(
                        ProjectFile.status.in_([FileStatus.pending, FileStatus.processing])
                    )
                )
            )
            .scalars()
            .all()
        )
        for f in stuck:
            if await _job_is_live(f.id, worker_startup=worker_startup):
                continue
            f.status = FileStatus.failed
            f.error_message = _FILE_MSG
            swept.append(f.id)
        if swept:
            await db.commit()
    for fid in swept:  # keep the job record honest; best effort
        try:
            await get_job_queue().update_status(fid, status="failed", error=_FILE_MSG)
        except Exception:  # noqa: BLE001
            pass
    if swept:
        logger.info("Sweep: failed %d stuck file(s)", len(swept))
    return len(swept)


async def sweep_stuck_tasks() -> tuple[int, int]:
    """Fail files/datasets left in a transient state by a crash. Returns (files, datasets)."""
    from sqlalchemy import select

    from adapta.db.models import (
        Adapter,
        AdapterStatus,
        Dataset,
        DatasetStatus,
    )
    from adapta.db.session import AsyncSessionLocal

    files = await sweep_stuck_files()
    datasets = 0
    async with AsyncSessionLocal() as db:
        stuck_datasets = (
            (await db.execute(select(Dataset).where(Dataset.status == DatasetStatus.validating)))
            .scalars()
            .all()
        )
        for d in stuck_datasets:
            d.status = DatasetStatus.invalid
            d.validation_error = _DATASET_MSG
            datasets += 1

        # An adapter job killed mid-run (worker crash/restart) leaves the row `processing`.
        stuck_adapters = (
            (await db.execute(select(Adapter).where(Adapter.status == AdapterStatus.processing)))
            .scalars()
            .all()
        )
        for a in stuck_adapters:
            a.status = AdapterStatus.failed
            a.failure_reason = _ADAPTER_MSG

        if datasets or stuck_adapters:
            await db.commit()
            logger.info(
                "Startup sweep: failed %d stuck dataset(s) and %d stuck adapter(s)",
                datasets,
                len(stuck_adapters),
            )
    return files, datasets
