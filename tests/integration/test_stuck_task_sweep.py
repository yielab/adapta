"""
Integration test — §A4.10 startup stuck-task sweeper.

A crash mid-index/mid-validate leaves a file at `processing` / a dataset at
`validating` forever. ``sweep_stuck_tasks`` (run at app startup) must drive those
orphans to a terminal state with a clear message.
"""

import uuid

import asyncpg
import pytest

from brain.config import settings
from brain.services.maintenance import sweep_stuck_tasks

pytestmark = pytest.mark.integration

_TABLES = (
    "orgs, teams, users, team_members, projects, project_files, "
    "collections, datasets, training_jobs, endpoints, api_keys, usage_events, invitations"
)


def _dsn() -> str:
    return settings.database_url.replace("+asyncpg", "")


@pytest.fixture
async def clean_db():
    from brain.db.session import engine
    await engine.dispose()  # fresh pool in this test's loop (see conftest note)
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()
    yield


async def _seed_project() -> str:
    conn = await asyncpg.connect(_dsn())
    try:
        sfx = uuid.uuid4().hex[:8]
        org_id, team_id, project_id = (str(uuid.uuid4()) for _ in range(3))
        await conn.execute("INSERT INTO orgs (id, name) VALUES ($1, $2)", org_id, f"SweepOrg-{sfx}")
        await conn.execute(
            "INSERT INTO teams (id, org_id, name) VALUES ($1, $2, 'SweepTeam')", team_id, org_id
        )
        await conn.execute(
            "INSERT INTO projects (id, team_id, name, type, status, base_model) "
            "VALUES ($1, $2, 'SweepProject', 'rag', 'created', 'qwen2.5-3b-instruct')",
            project_id, team_id,
        )
        return project_id
    finally:
        await conn.close()


async def test_sweep_fails_stuck_file_and_dataset(clean_db):
    project_id = await _seed_project()
    file_id, ds_id = str(uuid.uuid4()), str(uuid.uuid4())

    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(
            "INSERT INTO project_files (id, project_id, filename, content_type, size_bytes, "
            "storage_path, status) VALUES ($1, $2, 'doc.pdf', 'application/pdf', 10, '/tmp/d.pdf', 'processing')",
            file_id, project_id,
        )
        await conn.execute(
            "INSERT INTO datasets (id, project_id, name, storage_path, status) "
            "VALUES ($1, $2, 'd.jsonl', '/tmp/d.jsonl', 'validating')",
            ds_id, project_id,
        )
    finally:
        await conn.close()

    files, datasets = await sweep_stuck_tasks()
    assert files >= 1 and datasets >= 1

    conn = await asyncpg.connect(_dsn())
    try:
        frow = await conn.fetchrow(
            "SELECT status, error_message FROM project_files WHERE id = $1", file_id
        )
        drow = await conn.fetchrow(
            "SELECT status, validation_error FROM datasets WHERE id = $1", ds_id
        )
    finally:
        await conn.close()

    assert frow["status"] == "failed"
    assert "interrupted" in (frow["error_message"] or "")
    assert drow["status"] == "invalid"
    assert "interrupted" in (drow["validation_error"] or "")
