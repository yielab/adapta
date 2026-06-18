"""
Regression for TODO §A3.4 — endpoint slug collision across teams.

Two projects named the same in *different* teams must both get servable
endpoints. The slug was globally ``unique=True`` and derived from the bare
project name, so the second create hit an IntegrityError → generic 500.

The fix disambiguates the slug with a short project-id suffix (collision is
now structurally impossible) and, as a defensive net, maps any IntegrityError
to a typed Conflict(409) — never a 500.

These tests hit the REAL running server + live Postgres (see conftest), seeding
the RAG prerequisites (a satisfied Collection) directly via asyncpg so we don't
need real indexing.
"""

import uuid

import asyncpg
import pytest

from adapta.config import settings

pytestmark = pytest.mark.integration


def _dsn() -> str:
    return settings.database_url.replace("+asyncpg", "")


async def _seed_team_with_rag_project(
    org_id: str, user_id: str, team_name: str, project_name: str
) -> str:
    """Create a team in the org, make the user a writer, add a RAG project
    with an indexed collection. Returns the project id."""
    conn = await asyncpg.connect(_dsn())
    try:
        team_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO teams (id, org_id, name) VALUES ($1, $2, $3)",
            team_id,
            org_id,
            team_name,
        )
        await conn.execute(
            "INSERT INTO team_members (id, team_id, user_id, role) VALUES ($1, $2, $3, 'admin')",
            str(uuid.uuid4()),
            team_id,
            user_id,
        )
        project_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO projects (id, team_id, name, type, status, base_model) "
            "VALUES ($1, $2, $3, 'rag', 'created', 'qwen2.5-3b-instruct')",
            project_id,
            team_id,
            project_name,
        )
        # Satisfy the RAG endpoint precondition: a collection with chunks.
        await conn.execute(
            "INSERT INTO collections (id, project_id, chroma_collection_name, "
            "embedding_model, num_documents, num_chunks) VALUES ($1, $2, $3, $4, 1, 5)",
            str(uuid.uuid4()),
            project_id,
            f"col_{project_id}",
            "all-MiniLM-L6-v2",
        )
        return project_id
    finally:
        await conn.close()


async def _org_id_for_user(user_id: str) -> str:
    conn = await asyncpg.connect(_dsn())
    try:
        return await conn.fetchval("SELECT org_id FROM users WHERE id = $1", user_id)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_same_name_projects_in_different_teams_both_get_endpoints(client, admin):
    """The §A3.4 regression: identical project names across teams → two
    servable endpoints, distinct slugs, no 500 and no Conflict."""
    org_id = await _org_id_for_user(admin["user_id"])

    p1 = await _seed_team_with_rag_project(org_id, admin["user_id"], "TeamAlpha", "Support")
    p2 = await _seed_team_with_rag_project(org_id, admin["user_id"], "TeamBravo", "Support")

    r1 = await client.post(f"/v1/projects/{p1}/endpoint", headers=admin["headers"])
    r2 = await client.post(f"/v1/projects/{p2}/endpoint", headers=admin["headers"])

    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text

    slug1 = r1.json()["slug"]
    slug2 = r2.json()["slug"]
    assert slug1 != slug2, "slugs must be unique across same-named projects"
    assert slug1.startswith("support-")
    assert slug2.startswith("support-")


@pytest.mark.asyncio
async def test_endpoint_slug_is_url_safe(client, admin):
    """Messy project names still yield a clean, suffixed slug."""
    org_id = await _org_id_for_user(admin["user_id"])
    pid = await _seed_team_with_rag_project(
        org_id, admin["user_id"], "TeamMessy", "My Support / Bot!!"
    )
    r = await client.post(f"/v1/projects/{pid}/endpoint", headers=admin["headers"])
    assert r.status_code == 201, r.text
    slug = r.json()["slug"]
    # only lowercase alnum + hyphen, and carries the disambiguating suffix
    assert all(c.islower() or c.isdigit() or c == "-" for c in slug)
    assert slug.startswith("my-support---bot")
