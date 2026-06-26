"""Redis-backed async training job queue.

Jobs are stored as JSON keyed by job_id in Redis; the queue list holds
job_ids. The worker BLPOP-pops from the list and reads the metadata key.
Progress updates overwrite the metadata key in-place so the API can poll
live state without touching Postgres mid-run.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from redis.exceptions import TimeoutError as RedisTimeoutError

from adapta.config import settings

logger = logging.getLogger(__name__)

QUEUE_KEY = "adapta:training_queue"
JOB_KEY_PREFIX = "adapta:job:"
HEARTBEAT_KEY = "adapta:worker:heartbeat"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobQueue:
    """Async Redis job queue for training jobs."""

    def __init__(self, redis_url: str):
        self._url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(self._url, decode_responses=True)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    @property
    def redis(self) -> aioredis.Redis:
        if not self._redis:
            raise RuntimeError("JobQueue not connected — call connect() first")
        return self._redis

    async def enqueue(self, job_id: str, payload: dict) -> None:
        """Push job payload to the queue and store metadata."""
        meta = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0.0,
            "enqueued_at": _now_iso(),
            "payload": payload,
        }
        pipe = self.redis.pipeline()
        pipe.set(f"{JOB_KEY_PREFIX}{job_id}", json.dumps(meta))
        pipe.rpush(QUEUE_KEY, job_id)
        await pipe.execute()

    async def dequeue(self, timeout: int = 10) -> Optional[dict]:
        """Blocking pop; returns job meta dict or None on timeout (empty queue)."""
        try:
            result = await self.redis.blpop([QUEUE_KEY], timeout=timeout)
        except RedisTimeoutError:
            # redis-py asyncio raises TimeoutError when the socket read deadline
            # fires before BLPOP returns nil on an idle queue. That is a normal
            # empty poll, not an error — don't let it surface as a worker-loop error.
            return None
        if not result:
            return None
        _, job_id_val = result
        job_id: str = job_id_val if isinstance(job_id_val, str) else job_id_val.decode()
        raw = await self.redis.get(f"{JOB_KEY_PREFIX}{job_id}")
        if not raw:
            return None
        return json.loads(raw)  # type: ignore[no-any-return]

    async def queued_job_ids(self) -> list[str]:
        """All job_ids currently waiting in the queue list (not yet dequeued).

        Used at worker startup to distinguish a legitimately-waiting ``queued`` job
        from one that was lost (in Postgres as queued but absent from the Redis list
        after a crash) — lost ones are failed rather than left stuck."""
        vals = await self.redis.lrange(QUEUE_KEY, 0, -1)
        return [v if isinstance(v, str) else v.decode() for v in vals]

    async def heartbeat(self, ttl: int = 90) -> None:
        """Refresh the worker liveness key (TTL-expiring). A dead/hung worker stops
        refreshing it, so `worker_alive()` (and the container healthcheck) go red."""
        await self.redis.set(HEARTBEAT_KEY, _now_iso(), ex=ttl)

    async def worker_alive(self) -> bool:
        return bool(await self.redis.exists(HEARTBEAT_KEY))

    async def requeue(self, job_id: str) -> None:
        """Put a job back at the FRONT of the queue and reset it to queued.

        Used for graceful shutdown: an in-flight job is returned to the queue so
        the work restarts on the next worker rather than being lost at `running`.
        """
        await self.update_status(job_id, status="queued", progress=0.0)
        await self.redis.lpush(QUEUE_KEY, job_id)

    async def update_status(
        self,
        job_id: str,
        *,
        status: str,
        progress: Optional[float] = None,
        logs: Optional[str] = None,
        adapter_path: Optional[str] = None,
        eval_score: Optional[float] = None,
        eval_passed: Optional[bool] = None,
        eval_metrics: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        raw = await self.redis.get(f"{JOB_KEY_PREFIX}{job_id}")
        meta = json.loads(raw) if raw else {"job_id": job_id}
        meta["status"] = status
        if progress is not None:
            meta["progress"] = progress
        if logs is not None:
            meta["logs"] = logs
        if adapter_path is not None:
            meta["adapter_path"] = adapter_path
        if eval_score is not None:
            meta["eval_score"] = eval_score
        if eval_passed is not None:
            meta["eval_passed"] = eval_passed
        if eval_metrics is not None:
            meta["eval_metrics"] = eval_metrics
        if error is not None:
            meta["error"] = error
        if status in ("succeeded", "failed", "cancelled"):
            meta["finished_at"] = _now_iso()
        await self.redis.set(f"{JOB_KEY_PREFIX}{job_id}", json.dumps(meta))

    async def get_status(self, job_id: str) -> Optional[dict]:
        raw = await self.redis.get(f"{JOB_KEY_PREFIX}{job_id}")
        return json.loads(raw) if raw else None


_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = JobQueue(settings.redis_url)
    return _queue
