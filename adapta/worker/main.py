"""
Background worker — consumes jobs from the Redis queue and dispatches each to the
handler registered for its ``kind`` in :data:`HANDLERS`.
Run as a separate process/container (same image as the app):
    python -m adapta.worker.main

The loop owns liveness (heartbeat + ``--healthcheck``) and graceful shutdown (an
in-flight job is requeued on SIGTERM). Handlers: ``adapter`` (E4.4). A job whose kind has no handler fails with :class:`UnknownJobKind`.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Awaitable, Callable

from adapta.config import settings
from adapta.core.logging_config import configure_logging
from adapta.domain.errors import DomainError, UnknownJobKind
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


HANDLERS: dict[str, Callable[[dict], Awaitable[None]]] = {"adapter": _adapter_job}


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
