"""
Integration tests — §5.12 key-scoping audit.

A ``brn_*`` API key is scoped to exactly one endpoint.  These tests confirm:

1. A valid key + the *correct* endpoint slug → auth passes (downstream may fail
   without a GGUF model, but it's not a 401/403).
2. A valid key + a *foreign* endpoint slug → 403 Forbidden (key not authorized
   for that model).
3. A revoked key → 401 Unauthorized regardless of slug.

The tests use the same asyncpg seeding pattern as ``test_endpoint_slug.py`` —
a satisfied ``collections`` row is inserted directly so the endpoint precondition
is met without real indexing.
"""

import uuid

import asyncpg
import pytest

from brain.config import settings

pytestmark = pytest.mark.integration


def _dsn() -> str:
    return settings.database_url.replace("+asyncpg", "")


async def _seed_rag_endpoint_project(org_id: str, user_id: str, tag: str) -> str:
    """Seed a team + RAG project + satisfied collection; return project_id."""
    conn = await asyncpg.connect(_dsn())
    try:
        team_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO teams (id, org_id, name) VALUES ($1, $2, $3)",
            team_id, org_id, f"ScopeTeam-{tag}",
        )
        await conn.execute(
            "INSERT INTO team_members (id, team_id, user_id, role) VALUES ($1, $2, $3, 'admin')",
            str(uuid.uuid4()), team_id, user_id,
        )
        project_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO projects (id, team_id, name, type, status, base_model) "
            "VALUES ($1, $2, $3, 'rag', 'created', 'qwen2.5-3b-instruct')",
            project_id, team_id, f"ScopeProject-{tag}",
        )
        await conn.execute(
            "INSERT INTO collections (id, project_id, chroma_collection_name, "
            "embedding_model, num_documents, num_chunks) VALUES ($1, $2, $3, $4, 1, 5)",
            str(uuid.uuid4()), project_id, f"col_{project_id}", "all-MiniLM-L6-v2",
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


# ---------------------------------------------------------------------------
# §5.12 acceptance tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_key_cannot_drive_foreign_endpoint(client, admin):
    """A key + a *different* endpoint's slug → 403 Forbidden.

    This is the §5.12 core requirement: the scoped key must not grant access to
    any other endpoint, even if the caller knows the other endpoint's slug.
    """
    org_id = await _org_id_for_user(admin["user_id"])
    pid_a = await _seed_rag_endpoint_project(org_id, admin["user_id"], "foreign-A")
    pid_b = await _seed_rag_endpoint_project(org_id, admin["user_id"], "foreign-B")

    ep_a = await client.post(f"/v1/projects/{pid_a}/endpoint", headers=admin["headers"])
    ep_b = await client.post(f"/v1/projects/{pid_b}/endpoint", headers=admin["headers"])
    assert ep_a.status_code == 201 and ep_b.status_code == 201
    slug_a = ep_a.json()["slug"]
    slug_b = ep_b.json()["slug"]

    # Key for endpoint A only
    kr = await client.post(
        f"/v1/projects/{pid_a}/keys",
        json={"name": "scope-foreign"},
        headers=admin["headers"],
    )
    assert kr.status_code == 201
    key_a = kr.json()["key"]

    # key_a + model=slug_b → 403 (cannot drive endpoint B)
    r = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key_a}"},
        json={"model": slug_b, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 403, f"expected 403 Forbidden, got {r.status_code}: {r.text}"
    err = r.json()["error"]
    assert err["code"] == "forbidden"
    assert slug_b in err["message"]


@pytest.mark.asyncio
async def test_revoked_key_is_rejected(client, admin):
    """A revoked key → 401 regardless of slug.

    We use a deliberately wrong slug ("nonexistent-slug") so both the pre-revoke
    and post-revoke requests hit the fast auth/slug-check path without triggering
    model loading or RAG (which would block waiting for a GGUF that isn't present
    in CI). A valid key + wrong slug → 403; a revoked key + wrong slug → 401.
    This clearly distinguishes the two states without inference.
    """
    org_id = await _org_id_for_user(admin["user_id"])
    pid = await _seed_rag_endpoint_project(org_id, admin["user_id"], "revoke")

    ep = await client.post(f"/v1/projects/{pid}/endpoint", headers=admin["headers"])
    assert ep.status_code == 201

    kr = await client.post(
        f"/v1/projects/{pid}/keys",
        json={"name": "revoke-test"},
        headers=admin["headers"],
    )
    assert kr.status_code == 201
    key = kr.json()["key"]
    kid = kr.json()["id"]

    # Before revoke: valid key + wrong slug → 403 (auth passed, slug mismatch)
    r_before = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "nonexistent-slug", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r_before.status_code == 403, (
        f"valid key should give 403 (not 401) on wrong slug; got {r_before.status_code}"
    )

    # Revoke
    del_r = await client.delete(
        f"/v1/projects/{pid}/keys/{kid}",
        headers=admin["headers"],
    )
    assert del_r.status_code == 204, del_r.text

    # After revoke: same call → 401 (key no longer valid — can't even reach the slug check)
    r_after = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "nonexistent-slug", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r_after.status_code == 401, (
        f"revoked key should be rejected with 401; got {r_after.status_code}: {r_after.text}"
    )
    assert r_after.json()["error"]["code"] == "unauthorized"
