"""
Background worker — consumes jobs from the Redis queue and dispatches each to the
handler registered for its ``kind`` in :data:`HANDLERS`.
Run as a separate process/container (same image as the app):
    python -m adapta.worker.main

The loop owns liveness (heartbeat + ``--healthcheck``) and graceful shutdown (an
in-flight job is requeued on SIGTERM). Handlers: ``adapter`` (E4.4), ``index`` (E3.7). A job whose kind has no handler fails with :class:`UnknownJobKind`.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Awaitable, Callable

from adapta.config import settings
from adapta.core.logging_config import configure_logging
from adapta.domain.errors import DomainError, Timeout, UnknownJobKind
from adapta.services.jobs import get_job_queue

configure_logging()
logger = logging.getLogger("adapta.worker")

# kind -> async handler(meta). A handler records its own progress and terminal
# status through the queue; an exception it raises fails the job.
async def _adapter_job(meta: dict) -> None:
    """``adapter`` job (E4.4): convert, probe, score and decide one imported LoRA."""
    from adapta.services import adapters

    adapter_id = (meta.get("payload") or {}).get("id") or meta["job_id"]
    queue = get_job_queue()
    await queue.update_status(meta["job_id"], status="running")
    await adapters.process_adapter(adapter_id)
    await queue.update_status(meta["job_id"], status="succeeded", progress=1.0)


async def _index_attempt(file_id: str, *, final: bool) -> bool:
    """One deadline-bounded attempt of :func:`index_file_by_id` (E1.15).

    Returns the same "retry wanted" flag. A blown deadline (a hung Chroma, a stuck parser)
    is a transient failure on the first attempt and raises a typed :class:`Timeout`
    on the final one, after the file has been marked ``failed``.
    """
    from adapta.api.v1.files import index_file_by_id

    deadline = settings.index_job_timeout_seconds
    try:
        return await asyncio.wait_for(index_file_by_id(file_id, final=final), timeout=deadline)
    except asyncio.TimeoutError as exc:
        logger.error(
            "Index job for %s exceeded its %s s deadline (final attempt: %s).", file_id, deadline, final
        )
        if not final:
            return True
        message = (
            f"Indexing timed out after {deadline} s - the vector index or the document parser "
            "stopped answering. Check the stack with GET /health/deep, then upload the file again."
        )
        await _fail_file(file_id, message)
        raise Timeout(
            message=message, internal_detail=f"index deadline {deadline}s, file {file_id}"
        ) from exc


async def _fail_file(file_id: str, message: str) -> None:
    """Mark a file ``failed`` after the deadline cancelled its attempt; drop any stray vectors."""
    from sqlalchemy import select

    from adapta.db.models import FileStatus, ProjectFile
    from adapta.db.session import AsyncSessionLocal
    from adapta.services.rag import get_rag_service

    async with AsyncSessionLocal() as db:
        pfile = (
            await db.execute(select(ProjectFile).where(ProjectFile.id == file_id))
        ).scalar_one_or_none()
        if pfile is None or pfile.status not in (FileStatus.pending, FileStatus.processing):
            return
        project_id = pfile.project_id
        pfile.status = FileStatus.failed
        pfile.error_message = message
        await db.commit()
    try:  # the abandoned attempt may still have upserted; Chroma may still be hung -> bounded
        await asyncio.to_thread(get_rag_service().delete_file_chunks, project_id, file_id)
    except Exception:  # noqa: BLE001
        logger.warning("Could not clean up vectors of timed-out file %s", file_id)


async def _run_index_job(meta: dict) -> None:
    """``index`` job (E3.7): parse → chunk → embed → store one uploaded file.

    Payload ``{"id": file_id}`` (the job id is also the file id). The body is
    ``files.index_file_by_id`` → ``_index_file``; the file row carries the outcome
    (``indexed``/``failed``), so the job itself ends ``succeeded`` once the file is
    terminal. One automatic retry on a transient failure, and each attempt is bounded by
    ``index_job_timeout_seconds`` (E1.15): two timeouts end the file ``failed`` and the job
    ``failed`` with a clear message, and the worker moves on to the next job.
    """
    file_id = (meta.get("payload") or {}).get("id") or meta["job_id"]
    queue = get_job_queue()
    await queue.update_status(meta["job_id"], status="running")
    if await _index_attempt(file_id, final=False):
        logger.warning("Index job for %s hit a transient failure — retrying once.", file_id)
        await _index_attempt(file_id, final=True)
    await queue.update_status(meta["job_id"], status="succeeded", progress=1.0)


HANDLERS: dict[str, Callable[[dict], Awaitable[None]]] = {
    "adapter": _adapter_job,
    "index": _run_index_job,
}


def _warm_up() -> None:
    """Pay the Docling / embedding-model load once, at startup, not on the first job."""
    try:
        from adapta.services.documents import _get_converter
        from adapta.services.embeddings import get_embedding_service

        converter = _get_converter()
        init = getattr(converter, "initialize_pipeline", None)
        if init is not None:
            from docling.datamodel.base_models import InputFormat

            init(InputFormat.PDF)
        _ = get_embedding_service().dimension
        logger.info("Worker warm-up done (document parser + embedder loaded).")
    except Exception:  # noqa: BLE001 — warm-up is an optimisation; the first job will load lazily
        logger.exception("Worker warm-up failed; models will load on the first job.")


async def _run_job(meta: dict) -> None:
    kind = meta.get("kind")
    handler = HANDLERS.get(kind) if isinstance(kind, str) else None
    if handler is None:
        raise UnknownJobKind(
            message="This job type is not supported.",
            internal_detail=f"No handler registered for job kind {kind!r} (job {meta.get('job_id')})",
        )
    await handler(meta)


async def worker_loop() -> None:
    settings.ensure_dirs()  # data dirs must exist before any job runs
    queue = get_job_queue()
    await queue.connect()

    # No job of this (single) worker is running yet: any file still pending/processing
    # without a queued job was orphaned by a previous worker death.
    try:
        from adapta.services.maintenance import sweep_stuck_files

        await sweep_stuck_files(worker_startup=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Worker-startup sweep failed: %s", exc)
    await queue.heartbeat()
    await asyncio.to_thread(_warm_up)

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()
    in_flight: dict = {"task": None}

    def _request_shutdown(signame: str) -> None:
        logger.info("%s received — stopping; any in-flight job will be requeued.", signame)
        shutdown.set()
        task = in_flight["task"]
        if task is not None and not task.done():
            task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_shutdown, sig.name)

    logger.info("Worker connected to Redis, waiting for jobs...")
    await queue.heartbeat()
    while not shutdown.is_set():
        await queue.heartbeat()
        try:
            meta = await queue.dequeue(timeout=5)
        except Exception as exc:
            logger.exception("Worker loop error: %s", exc)
            await asyncio.sleep(2)
            continue
        if meta is None:
            continue

        job_id = meta.get("job_id", "unknown")
        task = asyncio.ensure_future(_run_job(meta))
        in_flight["task"] = task
        try:
            # Keep the liveness key fresh while a long job (OCR of a big PDF) runs:
            # the heartbeat TTL is 90 s, so a busy worker would otherwise report unhealthy.
            while not task.done():
                await asyncio.wait({task}, timeout=30)
                await queue.heartbeat()
            await task
        except asyncio.CancelledError:
            # Graceful shutdown mid-job: return it to the queue so it isn't lost.
            logger.warning("Job %s interrupted by shutdown — requeuing.", job_id)
            await queue.requeue(job_id)
            break
        except DomainError as exc:
            logger.error("Job %s failed: %s", job_id, exc.internal_detail or exc.message)
            await queue.update_status(job_id, status="failed", error=exc.message)
        except Exception:
            logger.exception("Unhandled error in job %s", job_id)
            await queue.update_status(job_id, status="failed", error="Job failed.")
        finally:
            in_flight["task"] = None

    await queue.close()
    logger.info("Worker stopped.")


async def _healthcheck() -> int:
    """Return 0 if a worker heartbeat is fresh in Redis, 1 otherwise.

    Used by the container healthcheck so a silently dead/hung worker (which still
    looks `Up` to Docker) is reported unhealthy.
    """
    queue = get_job_queue()
    await queue.connect()
    try:
        return 0 if await queue.worker_alive() else 1
    finally:
        await queue.close()


def main() -> None:
    if "--healthcheck" in sys.argv:
        raise SystemExit(asyncio.run(_healthcheck()))
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
