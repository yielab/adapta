"""Cross-team RBAC isolation (§1.7) — team A's data is invisible to org/team B.

Two separate registrations create two orgs, each with its own team. Every
team-scoped surface must refuse B's (valid, authenticated) token on A's
resources with a typed 403 — Forbidden, not Unauthorized: the token is fine,
the rights are missing. Self-hosted multi-user means this boundary IS the
tenant boundary.
"""

import asyncio

import pytest

pytestmark = pytest.mark.integration

_OUTSIDER = {"email": "outsider@itest.dev", "password": "outsider-pass-1", "org_name": "Other Org"}


async def _register_and_login(client, creds) -> dict:
    reg = await client.post("/v1/auth/register", json=creds)
    assert reg.status_code == 201, reg.text
    # Same read-your-write retry as the admin fixture (TODO §4.4).
    login = None
    for _ in range(10):
        login = await client.post(
            "/v1/auth/login", json={"email": creds["email"], "password": creds["password"]}
        )
        if login.status_code == 200:
            break
        await asyncio.sleep(0.1)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _make_project(client, headers, team_id) -> str:
    r = await client.post(
        "/v1/projects",
        headers=headers,
        json={"name": "team-a secret", "type": "finetune",
              "base_model": "qwen2.5-3b-instruct", "team_id": team_id},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _assert_forbidden(resp, what: str):
    assert resp.status_code == 403, f"{what}: expected 403, got {resp.status_code}: {resp.text}"
    assert resp.json()["error"]["code"] == "forbidden", resp.text


async def test_cross_team_isolation(client, admin):
    a_headers, a_team = admin["headers"], admin["team_id"]
    a_pid = await _make_project(client, a_headers, a_team)
    b_headers = await _register_and_login(client, _OUTSIDER)

    # B cannot enumerate A's team...
    _assert_forbidden(
        await client.get(f"/v1/projects?team_id={a_team}", headers=b_headers), "list projects"
    )
    # ...create into it...
    _assert_forbidden(
        await client.post(
            "/v1/projects",
            headers=b_headers,
            json={"name": "intruder", "type": "rag",
                  "base_model": "qwen2.5-3b-instruct", "team_id": a_team},
        ),
        "create project in foreign team",
    )
    # ...or read/delete A's project even knowing its id.
    _assert_forbidden(await client.get(f"/v1/projects/{a_pid}", headers=b_headers), "get project")
    _assert_forbidden(
        await client.delete(f"/v1/projects/{a_pid}", headers=b_headers), "delete project"
    )

    # Every sub-resource surface refuses too: files, datasets, jobs, endpoint,
    # keys, usage — both reads and writes.
    for what, resp in [
        ("list files", await client.get(f"/v1/projects/{a_pid}/files", headers=b_headers)),
        ("list datasets", await client.get(f"/v1/projects/{a_pid}/datasets", headers=b_headers)),
        ("list jobs", await client.get(f"/v1/projects/{a_pid}/jobs", headers=b_headers)),
        ("get endpoint", await client.get(f"/v1/projects/{a_pid}/endpoint", headers=b_headers)),
        ("list keys", await client.get(f"/v1/projects/{a_pid}/keys", headers=b_headers)),
        ("get usage", await client.get(f"/v1/projects/{a_pid}/usage", headers=b_headers)),
        ("create endpoint", await client.post(f"/v1/projects/{a_pid}/endpoint", headers=b_headers)),
        ("create key", await client.post(
            f"/v1/projects/{a_pid}/keys", headers=b_headers, json={"name": "stolen"})),
        ("enqueue job", await client.post(
            f"/v1/projects/{a_pid}/jobs", headers=b_headers, json={"dataset_id": "x"})),
        ("synthesize", await client.post(
            f"/v1/projects/{a_pid}/datasets/synthesize", headers=b_headers, json={})),
    ]:
        _assert_forbidden(resp, what)

    # And the refusals left A's world untouched.
    still = await client.get(f"/v1/projects/{a_pid}", headers=a_headers)
    assert still.status_code == 200, still.text
    listed = await client.get(f"/v1/projects?team_id={a_team}", headers=a_headers)
    assert [p["id"] for p in listed.json()] == [a_pid]


async def test_membership_refusal_is_403_not_401(client, admin):
    """403 (rights), never 401 (authentication): a 401 would tell well-behaved
    clients to drop their session and re-login, which cannot help."""
    b_headers = await _register_and_login(client, _OUTSIDER)
    r = await client.get(f"/v1/projects?team_id={admin['team_id']}", headers=b_headers)
    assert r.status_code == 403, r.text
    body = r.json()["error"]
    assert body["code"] == "forbidden"
    assert "member" in body["message"].lower()
    assert body["correlation_id"]
