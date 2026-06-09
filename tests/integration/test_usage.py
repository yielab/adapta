"""Integration test for usage metering read path (§3.2).

Seeds an endpoint + two daily usage rows via a one-off asyncpg connection (the
write path proper runs off a served completion, which needs a GGUF model), then
asserts the GET /usage aggregation.
"""

import uuid

import asyncpg
import pytest

from .conftest import _dsn

pytestmark = pytest.mark.integration


async def _seed_endpoint_with_usage(project_id: str) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        ep_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO endpoints (id, project_id, slug, status, base_model, created_at, updated_at) "
            "VALUES ($1, $2, $3, 'active', 'x', now(), now())",
            ep_id, project_id, f"slug-{ep_id[:8]}",
        )
        # two distinct days
        await conn.execute(
            "INSERT INTO usage_events (id, endpoint_id, day, prompt_tokens, completion_tokens, request_count) "
            "VALUES ($1, $2, CURRENT_DATE, 100, 200, 3)",
            str(uuid.uuid4()), ep_id,
        )
        await conn.execute(
            "INSERT INTO usage_events (id, endpoint_id, day, prompt_tokens, completion_tokens, request_count) "
            "VALUES ($1, $2, CURRENT_DATE - 1, 10, 20, 1)",
            str(uuid.uuid4()), ep_id,
        )
    finally:
        await conn.close()


async def test_usage_aggregation(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={"name": "U", "type": "finetune", "base_model": "x", "team_id": team_id},
    )
    pid = proj.json()["id"]

    # No usage yet → zeros and empty days.
    empty = await client.get(f"/v1/projects/{pid}/usage", headers=h)
    assert empty.status_code == 200
    assert empty.json()["total_tokens"] == 0
    assert empty.json()["days"] == []

    await _seed_endpoint_with_usage(pid)

    got = await client.get(f"/v1/projects/{pid}/usage", headers=h)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["total_prompt_tokens"] == 110
    assert body["total_completion_tokens"] == 220
    assert body["total_tokens"] == 330
    assert body["total_requests"] == 4
    assert len(body["days"]) == 2
    # newest first
    assert body["days"][0]["day"] >= body["days"][1]["day"]


async def test_usage_requires_auth(client):
    r = await client.get("/v1/projects/whatever/usage")
    assert r.status_code == 401
