"""
Fixtures for integration tests — these exercise the REAL running server
(uvicorn on :8000) against the live Postgres/Redis/Chroma stack.

Why a real server, not in-process ASGITransport: httpx's ASGITransport does not
execute FastAPI BackgroundTasks, so the async validation/indexing flows could
never complete. CI's full job starts uvicorn before this step; the dev stack
serves on :8000.

DB setup (truncate, team lookup) uses a one-off asyncpg connection rather than
the app's pooled async engine — pytest-asyncio gives each test a fresh event
loop, and reusing the shared engine's pooled connections across loops is a known
source of "event loop is closed" flakiness.

Run with the stack up:  pytest tests/ -m integration
Excluded from the offline `make ci` gate (no infra there).
"""

import os

import asyncpg
import httpx
import pytest
from httpx import AsyncClient

from brain.config import settings

BASE_URL = os.environ.get("BRAIN_BASE_URL", "http://localhost:8000")

_TABLES = (
    "orgs, teams, users, team_members, projects, project_files, "
    "collections, datasets, training_jobs, endpoints, api_keys, usage_events, invitations"
)

_ADMIN = {"email": "admin@itest.dev", "password": "itest-pass-123", "org_name": "ITest Org"}


def _dsn() -> str:
    # SQLAlchemy URL (postgresql+asyncpg://...) → plain asyncpg DSN.
    return settings.database_url.replace("+asyncpg", "")


def _require_server() -> None:
    try:
        httpx.get(f"{BASE_URL}/health", timeout=2).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"integration server not reachable at {BASE_URL}: {exc}")


async def _truncate() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()


async def _flush_rate_limits() -> None:
    """Clear auth rate-limit counters (A4.9) so the suite's many auth calls from
    one IP don't accumulate across tests and start returning 429."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        keys = await r.keys("ratelimit:*")
        if keys:
            await r.delete(*keys)
    finally:
        await r.aclose()


async def _first_team_id() -> str:
    conn = await asyncpg.connect(_dsn())
    try:
        return await conn.fetchval("SELECT id FROM teams LIMIT 1")
    finally:
        await conn.close()


@pytest.fixture
async def client():
    """Async client against the live server (background tasks run for real)."""
    _require_server()
    await _flush_rate_limits()  # fresh auth rate-limit budget per test (A4.9)
    async with AsyncClient(base_url=BASE_URL) as ac:
        yield ac


@pytest.fixture
async def admin(client):
    """Clean DB, bootstrap the org + first admin, return auth context.

    team_id is read straight from the DB because the bootstrap response does not
    surface it yet (team discovery is part of the §3.1 invite-flow backlog).
    """
    import asyncio

    await _truncate()
    reg = await client.post("/v1/auth/register", json=_ADMIN)
    assert reg.status_code == 201, reg.text

    # Brief retry: a login issued microseconds after register can fall inside a
    # read-your-write window on the server's connection pool (the row is durable
    # — an external connection sees it immediately — but a pooled connection may
    # lag a few ms). Real clients never hit this; see TODO §4.4.
    login = None
    for _ in range(10):
        login = await client.post(
            "/v1/auth/login", json={"email": _ADMIN["email"], "password": _ADMIN["password"]}
        )
        if login.status_code == 200:
            break
        await asyncio.sleep(0.1)
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    return {
        "token": token,
        "team_id": await _first_team_id(),
        "user_id": reg.json()["id"],
        "headers": {"Authorization": f"Bearer {token}"},
    }
