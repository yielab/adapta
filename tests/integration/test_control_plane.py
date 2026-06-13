"""
Integration tests — control plane against the live Postgres/Redis/Chroma stack.

Covers the API + DB + auth layers end-to-end (no GGUF model / GPU needed). The
full RAG-answer and LoRA-training flows are exercised separately where a model
is available; the inference/training steps are noted in TODO §1.7.
"""

import asyncio
import io
import json

import pytest

pytestmark = pytest.mark.integration


async def _retry(make_request, ok, tries=15, delay=0.1):
    """Retry an immediate read-after-write until `ok` — works around the server's
    brief read-your-write window under connection pooling (TODO §4.4). The write
    is already durable; a pooled connection can lag a few ms."""
    r = await make_request()
    for _ in range(tries):
        if ok(r):
            return r
        await asyncio.sleep(delay)
        r = await make_request()
    return r


# --- Auth ------------------------------------------------------------------


async def test_unauthenticated_is_401(client):
    r = await client.get("/v1/projects", params={"team_id": "whatever"})
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] == "unauthorized"
    assert "correlation_id" in body["error"]


async def test_bad_token_is_401(client):
    r = await client.get("/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


async def test_me_returns_current_user(client, admin):
    r = await client.get("/v1/auth/me", headers=admin["headers"])
    assert r.status_code == 200
    assert r.json()["email"] == "admin@itest.dev"


async def test_register_is_open_per_org(client, admin):
    # Registration is open: a new email creates a NEW org with its own admin.
    r = await client.post(
        "/v1/auth/register",
        json={"email": "second@itest.dev", "password": "another-pass-123", "org_name": "SecondOrg"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["teams"][0]["role"] == "admin"
    # The new admin can sign in and sees their own org, isolated from the first.
    login = await client.post(
        "/v1/auth/login", json={"email": "second@itest.dev", "password": "another-pass-123"}
    )
    assert login.status_code == 200, login.text
    me = await client.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["org_id"] == body["org_id"]


async def test_register_duplicate_email_is_409(client, admin):
    # The only register conflict: an email that already has an account.
    r = await client.post(
        "/v1/auth/register",
        json={"email": "admin@itest.dev", "password": "another-pass-123", "org_name": "X"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


async def test_register_short_password_is_400(client, admin):
    r = await client.post(
        "/v1/auth/register",
        json={"email": "short@itest.dev", "password": "short", "org_name": "X"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"


# --- Projects (persistence + team scoping) ---------------------------------


async def test_project_lifecycle(client, admin):
    h, team_id = admin["headers"], admin["team_id"]

    created = await client.post(
        "/v1/projects",
        headers=h,
        json={
            "name": "Docs RAG",
            "type": "rag",
            "base_model": "qwen2.5-3b-instruct",
            "team_id": team_id,
        },
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["type"] == "rag"

    got = await _retry(
        lambda: client.get(f"/v1/projects/{pid}", headers=h),
        lambda r: r.status_code == 200,
    )
    assert got.status_code == 200
    assert got.json()["name"] == "Docs RAG"

    listed = await client.get("/v1/projects", headers=h, params={"team_id": team_id})
    assert listed.status_code == 200
    assert any(p["id"] == pid for p in listed.json())

    deleted = await client.delete(f"/v1/projects/{pid}", headers=h)
    assert deleted.status_code == 204

    gone = await _retry(
        lambda: client.get(f"/v1/projects/{pid}", headers=h),
        lambda r: r.status_code == 404,
    )
    assert gone.status_code == 404


async def test_get_unknown_project_is_404(client, admin):
    r = await client.get("/v1/projects/does-not-exist", headers=admin["headers"])
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_create_project_validation_error_is_422_envelope(client, admin):
    # Missing required fields -> normalized 422 envelope, not FastAPI's {detail:[...]}.
    r = await client.post("/v1/projects", headers=admin["headers"], json={"name": "x"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


async def test_create_project_unknown_base_model_rejected(client, admin):
    # A base_model not in the catalog (A3.3) is rejected with a typed InvalidRequest
    # that lists the allowed values, instead of a project that can't train or serve.
    team_id = admin["team_id"]
    r = await client.post(
        "/v1/projects",
        headers=admin["headers"],
        json={"name": "Bad", "type": "rag", "base_model": "not-a-real-model", "team_id": team_id},
    )
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "invalid_request"
    # The allowed list must be surfaced so the operator (and console dropdown) can recover.
    assert "qwen2.5-3b-instruct" in err["message"]


# --- Datasets (upload + background validation, finetune project) -----------


async def _upload_dataset(client, headers, project_id, lines):
    payload = "\n".join(json.dumps(x) for x in lines).encode()
    files = {"file": ("data.jsonl", io.BytesIO(payload), "application/jsonl")}
    return await client.post(f"/v1/projects/{project_id}/datasets", headers=headers, files=files)


async def _await_terminal(client, headers, pid, did, terminals=("valid", "invalid")):
    """Poll a dataset until its background validation reaches a terminal state."""
    r = await _retry(
        lambda: client.get(f"/v1/projects/{pid}/datasets/{did}", headers=headers),
        lambda r: r.status_code == 200 and r.json().get("status") in terminals,
        tries=40,
        delay=0.1,
    )
    return r


async def test_dataset_upload_validates_to_terminal_state(client, admin):
    # Full path: upload (202 → validating) → the FastAPI BackgroundTask validates
    # the file → terminal `valid` with the sample count. Regression guard for the
    # §4.4 bug where the task raced the request commit and datasets stuck forever.
    h, team_id = admin["headers"], admin["team_id"]
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={
            "name": "FT",
            "type": "finetune",
            "base_model": "qwen2.5-3b-instruct",
            "team_id": team_id,
        },
    )
    pid = proj.json()["id"]

    good = await _retry(
        lambda: _upload_dataset(
            client,
            h,
            pid,
            [{"prompt": "Hi", "response": "Hello"}, {"prompt": "Bye", "response": "Goodbye"}],
        ),
        lambda r: r.status_code == 202,
    )
    assert good.status_code == 202, good.text
    did = good.json()["id"]
    assert good.json()["status"] == "validating"

    got = await _await_terminal(client, h, pid, did)
    assert got.json()["status"] == "valid", got.text
    assert got.json()["num_samples"] == 2

    listed = await _retry(
        lambda: client.get(f"/v1/projects/{pid}/datasets", headers=h),
        lambda r: any(d["id"] == did for d in r.json()),
    )
    assert any(d["id"] == did for d in listed.json())


async def test_dataset_invalid_reaches_invalid_state(client, admin):
    # A schema-violating line must reach terminal `invalid` with an error message,
    # not hang at `validating`.
    h, team_id = admin["headers"], admin["team_id"]
    proj = await client.post(
        "/v1/projects",
        headers=h,
        json={
            "name": "FT2",
            "type": "finetune",
            "base_model": "qwen2.5-3b-instruct",
            "team_id": team_id,
        },
    )
    pid = proj.json()["id"]

    bad = await _retry(
        lambda: _upload_dataset(client, h, pid, [{"prompt": "no response here"}]),
        lambda r: r.status_code == 202,
    )
    did = bad.json()["id"]
    got = await _await_terminal(client, h, pid, did)
    assert got.json()["status"] == "invalid", got.text
    assert got.json()["validation_error"]


async def test_create_then_immediate_get_no_retry(client, admin):
    # Regression guard for the read-your-write window (§4.4): a create followed by
    # an IMMEDIATE get (no retry/sleep) must succeed now that write handlers commit
    # before returning. Repeat to make a residual race statistically visible.
    h, team_id = admin["headers"], admin["team_id"]
    for i in range(25):
        created = await client.post(
            "/v1/projects",
            headers=h,
            json={
                "name": f"rw{i}",
                "type": "rag",
                "base_model": "qwen2.5-3b-instruct",
                "team_id": team_id,
            },
        )
        assert created.status_code == 201, created.text
        pid = created.json()["id"]
        got = await client.get(f"/v1/projects/{pid}", headers=h)
        assert (
            got.status_code == 200
        ), f"immediate read missed just-created {pid}: {got.status_code}"


# --- Scoped key auth on the serving endpoint -------------------------------


async def test_chat_completions_rejects_missing_and_bad_key(client):
    # No key
    r = await client.post(
        "/v1/chat/completions",
        json={"model": "anything", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401
    # Bogus brn_ key
    r2 = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer brn_not_a_real_key"},
        json={"model": "anything", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r2.status_code == 401
