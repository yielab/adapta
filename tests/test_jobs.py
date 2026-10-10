"""
Unit tests for the Redis-backed job queue (adapta/services/jobs.py).

Infrastructure is mocked at the boundary with an in-memory fake Redis so these
run in the offline gate. Notably covers the idle-poll path: an idle BLPOP that
raises redis TimeoutError must be treated as an empty poll, not an error
(regression guard for the worker log-flood fix).
"""

import json

import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from adapta.domain.errors import UnknownJobKind
from adapta.services.jobs import JOB_KEY_PREFIX, JOB_RESULT_TTL_SECONDS, QUEUE_KEY, JobQueue
from adapta.worker import main as worker


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
        self.ttls: dict[str, int | None] = {}
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
        self.ttls[key] = ex  # None = no expiry (SET without EX clears it, as in Redis)

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
    await queue.enqueue("job-1", "probe", {"base_model": "x", "dataset_path": "/tmp/d.jsonl"})
    # metadata stored + id on the queue
    assert QUEUE_KEY in queue._redis.lists
    assert json.loads(queue._redis.store[f"{JOB_KEY_PREFIX}job-1"])["status"] == "queued"

    meta = await queue.dequeue(timeout=1)
    assert meta is not None
    assert meta["job_id"] == "job-1"
    assert meta["kind"] == "probe"
    assert meta["payload"]["base_model"] == "x"


async def test_dequeue_empty_queue_returns_none(queue):
    assert await queue.dequeue(timeout=1) is None


async def test_dequeue_timeout_is_empty_poll_not_error(queue):
    # The redis-py asyncio BLPOP read-timeout must surface as an empty poll.
    queue._redis.blpop_should_timeout = True
    assert await queue.dequeue(timeout=1) is None


async def test_update_status_merges_fields(queue):
    await queue.enqueue("job-2", "probe", {"base_model": "y"})
    await queue.dequeue(timeout=1)
    await queue.update_status("job-2", status="running", progress=0.5)
    await queue.update_status("job-2", status="succeeded", logs="done")
    meta = await queue.get_status("job-2")
    assert meta["status"] == "succeeded"
    assert meta["progress"] == 0.5  # preserved across updates
    assert meta["logs"] == "done"
    assert "finished_at" in meta  # terminal status stamps a finish time


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
async def test_terminal_job_key_expires_within_seven_days(queue, status):
    await queue.enqueue("job-t", "probe", {})
    await queue.update_status("job-t", status="running")
    key = f"{JOB_KEY_PREFIX}job-t"
    assert queue._redis.ttls[key] is None  # in-flight keys never expire
    await queue.update_status("job-t", status=status)
    assert 0 < queue._redis.ttls[key] <= 7 * 24 * 3600
    assert queue._redis.ttls[key] == JOB_RESULT_TTL_SECONDS


async def test_requeue_clears_ttl_so_the_job_is_not_lost(queue):
    await queue.enqueue("job-r", "probe", {})
    await queue.update_status("job-r", status="failed", error="boom")
    key = f"{JOB_KEY_PREFIX}job-r"
    assert queue._redis.ttls[key] is not None
    await queue.requeue("job-r")
    assert queue._redis.ttls[key] is None


async def test_get_status_missing_returns_none(queue):
    assert await queue.get_status("nope") is None


async def test_requeue_resets_status_and_fronts_the_queue(queue):
    await queue.enqueue("job-3", "probe", {"base_model": "z"})
    await queue.dequeue(timeout=1)  # drains it off the queue
    await queue.update_status("job-3", status="running", progress=0.7)
    await queue.requeue("job-3")
    # back on the queue and reset to queued
    assert queue._redis.lists[QUEUE_KEY] == ["job-3"]
    assert (await queue.get_status("job-3"))["status"] == "queued"


async def test_requeue_goes_to_front(queue):
    queue._redis.lists[QUEUE_KEY] = ["existing"]
    await queue.enqueue("job-4", "probe", {})
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


# Worker dispatch (adapta/worker/main.py): jobs run through the HANDLERS table,
# keyed by meta["kind"]; a kind with no handler fails with a typed error.


async def test_run_job_unknown_kind_raises_typed_error():
    with pytest.raises(UnknownJobKind) as exc:
        await worker._run_job({"job_id": "j", "kind": "nope", "payload": {}})
    assert exc.value.code == "unknown_job_kind"
    assert "nope" in (exc.value.internal_detail or "")
    assert "nope" not in exc.value.message  # internal detail never reaches the client text


async def test_run_job_missing_kind_raises_typed_error():
    with pytest.raises(UnknownJobKind):
        await worker._run_job({"job_id": "j", "payload": {}})


async def test_run_job_dispatches_to_registered_handler(monkeypatch):
    seen = []

    async def handler(meta):
        seen.append(meta["job_id"])

    monkeypatch.setitem(worker.HANDLERS, "probe", handler)
    await worker._run_job({"job_id": "j-1", "kind": "probe", "payload": {}})
    assert seen == ["j-1"]


def test_handler_table_holds_the_adapter_index_rag_eval_and_extract_jobs():
    assert set(worker.HANDLERS) == {"adapter", "index", "rag_eval", "extract"}
    assert worker.HANDLERS["index"] is worker._run_index_job


async def test_adapter_handler_passes_the_payload_id_and_marks_the_job(monkeypatch):
    from adapta.services import adapters

    calls = []

    class Q:
        async def update_status(self, job_id, **kw):
            calls.append(("status", job_id, kw["status"]))

    async def fake_process(adapter_id):
        calls.append(("process", adapter_id))

    monkeypatch.setattr(worker, "get_job_queue", lambda: Q())
    monkeypatch.setattr(adapters, "process_adapter", fake_process)
    await worker._run_job({"job_id": "ad-1", "kind": "adapter", "payload": {"id": "ad-1"}})
    assert calls == [
        ("status", "ad-1", "running"),
        ("process", "ad-1"),
        ("status", "ad-1", "succeeded"),
    ]


# `index` job (E3.7): payload {"id": file_id}; one retry on a transient failure.


def _index_harness(monkeypatch, outcomes):
    from adapta.api.v1 import files as files_mod

    calls = []

    class Q:
        async def update_status(self, job_id, **kw):
            calls.append(("status", job_id, kw["status"]))

    async def fake_index(file_id, *, final=True):
        calls.append(("index", file_id, final))
        return outcomes.pop(0)

    monkeypatch.setattr(worker, "get_job_queue", lambda: Q())
    monkeypatch.setattr(files_mod, "index_file_by_id", fake_index)
    return calls


async def test_index_handler_runs_once_when_it_succeeds(monkeypatch):
    calls = _index_harness(monkeypatch, [False])
    await worker._run_job({"job_id": "f-1", "kind": "index", "payload": {"id": "f-1"}})
    assert calls == [
        ("status", "f-1", "running"),
        ("index", "f-1", False),
        ("status", "f-1", "succeeded"),
    ]


async def test_index_handler_retries_once_on_a_transient_failure(monkeypatch):
    calls = _index_harness(monkeypatch, [True, False])
    await worker._run_job({"job_id": "f-2", "kind": "index", "payload": {"id": "f-2"}})
    assert [c for c in calls if c[0] == "index"] == [("index", "f-2", False), ("index", "f-2", True)]
    assert calls[-1] == ("status", "f-2", "succeeded")
