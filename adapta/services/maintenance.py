"""Startup reconciliation for in-process background tasks.

File indexing and dataset validation run as FastAPI BackgroundTasks. If the app
crashes (or is restarted) mid-task, the row is left in a transient state forever —
a file stuck at ``processing``, a dataset at ``validating`` — with no task alive to
finish it. On startup, before serving, mark those orphans terminal so the operator
sees a clear failure (and can re-upload) instead of an indefinite spinner.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_FILE_MSG = "Indexing was interrupted by a server restart — re-upload the file to retry."
_ADAPTER_MSG = "Processing was interrupted by a restart — upload the adapter again to retry."
_DATASET_MSG = "Validation was interrupted by a server restart — re-upload the dataset to retry."


async def sweep_stuck_tasks() -> tuple[int, int]:
    """Fail files/datasets left in a transient state by a crash. Returns (files, datasets)."""
    from sqlalchemy import select

    from adapta.db.models import (
        Adapter,
        AdapterStatus,
        Dataset,
        DatasetStatus,
        FileStatus,
        ProjectFile,
    )
    from adapta.db.session import AsyncSessionLocal

    files = datasets = 0
    async with AsyncSessionLocal() as db:
        stuck_files = (
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
        for f in stuck_files:
            f.status = FileStatus.failed
            f.error_message = _FILE_MSG
            files += 1

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

        if files or datasets or stuck_adapters:
            await db.commit()
            logger.info(
                "Startup sweep: failed %d stuck file(s), %d stuck dataset(s) and %d stuck adapter(s)",
                files,
                datasets,
                len(stuck_adapters),
            )
    return files, datasets
