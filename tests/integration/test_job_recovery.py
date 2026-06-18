"""
Integration tests — §A4.2 crashed-job recovery.

A hard worker crash (OOM-kill, power loss, segfault) pops a job off the Redis
queue but never drives it to a terminal state, so it sits ``running`` in Postgres
forever with no live worker. ``recover_orphaned_jobs`` (run at worker startup)
must find such jobs and either requeue them once or fail them after they've burned
their retries.

These seed rows directly via asyncpg (the same pattern as test_key_scoping) and
drive the service function, so no GPU/model is needed.

The live worker container is BLPOP-ing the real queue, so each test points the
queue at a unique key the worker doesn't watch — otherwise the worker would steal
the jobs we enqueue and the queue would always look empty.
"""

import uuid

import asyncpg
import pytest

from adapta.config import settings
from adapta.services import jobs as jobs_mod
from adapta.services.training import recover_orphaned_jobs

pytestmark = pytest.mark.integration


_TABLES = (
    "orgs, teams, users, team_members, projects, project_files, "
    "collections, datasets, training_jobs, endpoints, api_keys, usage_events, invitations"
)


def _dsn() -> str:
    return settings.database_url.replace("+asyncpg", "")


async def _truncate() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()


async def _seed_running_job(tag: str, *, status: str = "running", attempts: int = 0) -> str:
    """Seed org→team→project(finetune)→dataset→training_job; return job_id."""
    sfx = uuid.uuid4().hex[:8]  # orgs.name is unique; these tests don't truncate
    conn = await asyncpg.connect(_dsn())
    try:
        org_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO orgs (id, name) VALUES ($1, $2)", org_id, f"RecOrg-{tag}-{sfx}"
        )
        team_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO teams (id, org_id, name) VALUES ($1, $2, $3)",
            team_id,
            org_id,
            f"RecTeam-{tag}",
        )
        project_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO projects (id, team_id, name, type, status, base_model) "
            "VALUES ($1, $2, $3, 'finetune', 'created', 'qwen2.5-3b-instruct')",
            project_id,
            team_id,
            f"RecProject-{tag}",
        )
        dataset_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO datasets (id, project_id, name, storage_path, num_samples, status) "
            "VALUES ($1, $2, $3, $4, 5, 'valid')",
            dataset_id,
            project_id,
            "rec.jsonl",
            "/tmp/rec.jsonl",
        )
        job_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO training_jobs (id, project_id, dataset_id, status, progress, attempts) "
            "VALUES ($1, $2, $3, $4, 0.5, $5)",
            job_id,
            project_id,
            dataset_id,
            status,
            attempts,
        )
        return job_id
    finally:
        await conn.close()


async def _job_row(job_id: str) -> asyncpg.Record:
    conn = await asyncpg.connect(_dsn())
    try:
        return await conn.fetchrow(
            "SELECT status, attempts, error_message FROM training_jobs WHERE id = $1", job_id
        )
    finally:
        await conn.close()


async def _set_status(job_id: str, status: str) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("UPDATE training_jobs SET status = $1 WHERE id = $2", status, job_id)
    finally:
        await conn.close()


@pytest.fixture
async def queue(monkeypatch):
    # pytest-asyncio gives each test a fresh event loop; both the app's pooled DB
    # engine and a reused Redis connection are bound to the loop that created them,
    # so reusing the singletons across tests raises "event loop is closed" (see the
    # conftest note). Dispose the engine and install a fresh JobQueue bound to THIS
    # loop, pointing the module singleton at it so recover_orphaned_jobs uses it.
    from adapta.db.session import engine

    await engine.dispose()

    # recover_orphaned_jobs scans ALL running/queued jobs in Postgres, so each test
    # needs a clean slate (otherwise rows from earlier runs get recovered too).
    await _truncate()

    # Unique queue key so the live worker (BLPOP-ing the real key) can't steal our
    # jobs. recover_orphaned_jobs reads the module constant at call time, so the
    # monkeypatch reaches it too.
    test_key = f"adapta:training_queue:test:{uuid.uuid4().hex}"
    monkeypatch.setattr(jobs_mod, "QUEUE_KEY", test_key)

    q = jobs_mod.JobQueue(settings.redis_url)
    await q.connect()
    monkeypatch.setattr(jobs_mod, "_queue", q)  # get_job_queue() returns this
    await q.redis.delete(test_key)  # start from a clean queue
    yield q
    await q.redis.delete(test_key)
    await q.close()


async def test_running_job_is_requeued_then_failed(queue):
    """First crash → requeued (attempts=1, back in the queue). Second crash → failed."""
    job_id = await _seed_running_job("crash")

    requeued, failed = await recover_orphaned_jobs(max_attempts=1)
    assert (requeued, failed) == (1, 0)

    row = await _job_row(job_id)
    assert row["status"] == "queued"
    assert row["attempts"] == 1
    assert job_id in await queue.queued_job_ids()

    # Simulate a worker re-picking the job (out of the queue) and crashing again.
    await queue.redis.delete(jobs_mod.QUEUE_KEY)
    await _set_status(job_id, "running")

    requeued2, failed2 = await recover_orphaned_jobs(max_attempts=1)
    assert (requeued2, failed2) == (0, 1)

    row2 = await _job_row(job_id)
    assert row2["status"] == "failed"
    assert "exhausted retries" in (row2["error_message"] or "")


async def test_queued_job_in_queue_is_left_alone(queue):
    """A `queued` job that is still in the Redis queue is legitimately waiting —
    recovery must not touch it (no spurious requeue, no attempt burned)."""
    job_id = await _seed_running_job("waiting", status="queued", attempts=0)
    await queue.redis.rpush(jobs_mod.QUEUE_KEY, job_id)  # it IS in the queue

    requeued, failed = await recover_orphaned_jobs(max_attempts=1)
    assert (requeued, failed) == (0, 0)

    row = await _job_row(job_id)
    assert row["status"] == "queued"
    assert row["attempts"] == 0
