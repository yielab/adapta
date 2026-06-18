"""
Unit tests for the Redis-backed training job queue (adapta/services/jobs.py).

Infrastructure is mocked at the boundary with an in-memory fake Redis so these
run in the offline gate. Notably covers the idle-poll path: an idle BLPOP that
raises redis TimeoutError must be treated as an empty poll, not an error
(regression guard for the worker log-flood fix).
"""

import json

import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from adapta.services.jobs import JOB_KEY_PREFIX, QUEUE_KEY, JobQueue


class _FakePipeline:
    def __init__(self, store, queue):
        self._store = store
        self._queue = queue
        self._ops = []

    def set(self, key, value):
        self._ops.append(("set", key, value))
        return self

    def rpush(self, key, value):
        self._ops.append(("rpush", key, value))
        return self

    async def execute(self):
        for op in self._ops:
            if op[0] == "set":
                self._store[op[1]] = op[2]
            elif op[0] == "rpush":
                self._queue.setdefault(op[1], []).append(op[2])
        self._ops.clear()


class FakeRedis:
    """Minimal async Redis stand-in covering the calls JobQueue makes."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.lists: dict[str, list] = {}
        self.blpop_should_timeout = False

    def pipeline(self):
        return _FakePipeline(self.store, self.lists)

    async def blpop(self, keys, timeout=0):
        if self.blpop_should_timeout:
            raise RedisTimeoutError("Timeout reading from redis:6379")
        key = keys[0] if isinstance(keys, list) else keys
        lst = self.lists.get(key, [])
        if not lst:
            return None
        return (key, lst.pop(0))

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    async def exists(self, key):
        return 1 if key in self.store else 0


@pytest.fixture
def queue():
    q = JobQueue("redis://fake:6379/0")
    q._redis = FakeRedis()
    return q


async def test_enqueue_then_dequeue_roundtrip(queue):
    await queue.enqueue("job-1", {"base_model": "x", "dataset_path": "/tmp/d.jsonl"})
    # metadata stored + id on the queue
    assert QUEUE_KEY in queue._redis.lists
    assert json.loads(queue._redis.store[f"{JOB_KEY_PREFIX}job-1"])["status"] == "queued"

    meta = await queue.dequeue(timeout=1)
    assert meta is not None
    assert meta["job_id"] == "job-1"
    assert meta["payload"]["base_model"] == "x"


async def test_dequeue_empty_queue_returns_none(queue):
    assert await queue.dequeue(timeout=1) is None


async def test_dequeue_timeout_is_empty_poll_not_error(queue):
    # The redis-py asyncio BLPOP read-timeout must surface as an empty poll.
    queue._redis.blpop_should_timeout = True
    assert await queue.dequeue(timeout=1) is None


async def test_update_status_merges_fields(queue):
    await queue.enqueue("job-2", {"base_model": "y"})
    await queue.dequeue(timeout=1)
    await queue.update_status("job-2", status="running", progress=0.5)
    await queue.update_status(
        "job-2", status="succeeded", eval_score=0.81, eval_passed=True, adapter_path="/a"
    )
    meta = await queue.get_status("job-2")
    assert meta["status"] == "succeeded"
    assert meta["progress"] == 0.5  # preserved across updates
    assert meta["eval_score"] == 0.81
    assert meta["eval_passed"] is True
    assert "finished_at" in meta  # terminal status stamps a finish time


async def test_get_status_missing_returns_none(queue):
    assert await queue.get_status("nope") is None


async def test_requeue_resets_status_and_fronts_the_queue(queue):
    await queue.enqueue("job-3", {"base_model": "z"})
    await queue.dequeue(timeout=1)  # drains it off the queue
    await queue.update_status("job-3", status="running", progress=0.7)
    await queue.requeue("job-3")
    # back on the queue and reset to queued
    assert queue._redis.lists[QUEUE_KEY] == ["job-3"]
    assert (await queue.get_status("job-3"))["status"] == "queued"


async def test_requeue_goes_to_front(queue):
    queue._redis.lists[QUEUE_KEY] = ["existing"]
    await queue.enqueue("job-4", {})
    await queue.requeue("job-4")
    # requeued job is at the FRONT (picked up next), ahead of existing entries
    assert queue._redis.lists[QUEUE_KEY][0] == "job-4"


async def test_heartbeat_and_worker_alive(queue):
    assert await queue.worker_alive() is False
    await queue.heartbeat()
    assert await queue.worker_alive() is True


def test_queue_requires_connection():
    q = JobQueue("redis://fake:6379/0")
    with pytest.raises(RuntimeError):
        _ = q.redis
