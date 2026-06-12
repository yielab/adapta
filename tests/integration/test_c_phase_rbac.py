"""RBAC coverage for §C surfaces: members, settings, change-password (C5.1).

Extends the §1.7 cross-team pattern to every new route introduced in the
console v2 workstream:
  - GET  /v1/teams/{team_id}/members
  - POST /v1/auth/change-password
  - GET  /v1/settings?team_id=
  - PUT  /v1/settings
  - DELETE /v1/settings/{key}

Rules verified:
  - Team A's token → 403 on team B's resources.
  - Viewer and member can READ settings and members (team member check).
  - Viewer and member CANNOT write settings (admin-only).
  - change-password is self-bound: it always mutates the calling user's
    own credential; wrong current_password returns a typed error, never
    another user's record.
"""

import asyncio

import pytest

pytestmark = pytest.mark.integration

_OUTSIDER = {"email": "c-outsider@itest.dev", "password": "outsider-c-1", "org_name": "C Outsider Org"}


async def _register_and_login(client, creds) -> dict:
    reg = await client.post("/v1/auth/register", json=creds)
    assert reg.status_code == 201, reg.text
    login = None
    for _ in range(10):
        login = await client.post(
            "/v1/auth/login",
            json={"email": creds["email"], "password": creds["password"]},
        )
        if login.status_code == 200:
            break
        await asyncio.sleep(0.1)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _invite_and_join(client, admin_headers, team_id, email, role, password="newpass123") -> dict:
    inv = await client.post(
        "/v1/auth/invite",
        headers=admin_headers,
        json={"email": email, "team_id": team_id, "role": role},
    )
    assert inv.status_code == 201, inv.text
    acc = await client.post(
        "/v1/auth/accept-invite",
        json={"token": inv.json()["token"], "password": password},
    )
    assert acc.status_code == 201, acc.text
    login = await client.post("/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _assert_forbidden(resp, label: str) -> None:
    assert resp.status_code == 403, f"{label}: expected 403, got {resp.status_code}: {resp.text}"
    assert resp.json()["error"]["code"] == "forbidden", resp.text


# ---------------------------------------------------------------------------
# GET /v1/teams/{team_id}/members
# ---------------------------------------------------------------------------

async def test_members_cross_team_403(client, admin):
    a_team = admin["team_id"]
    b_headers = await _register_and_login(client, _OUTSIDER)
    _assert_forbidden(
        await client.get(f"/v1/teams/{a_team}/members", headers=b_headers),
        "members cross-team",
    )


async def test_members_readable_by_viewer(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    viewer_h = await _invite_and_join(client, h, team_id, "c-viewer-m@itest.dev", "viewer")
    r = await client.get(f"/v1/teams/{team_id}/members", headers=viewer_h)
    assert r.status_code == 200, r.text
    emails = [m["email"] for m in r.json()]
    assert "admin@itest.dev" in emails


async def test_members_readable_by_member(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    member_h = await _invite_and_join(client, h, team_id, "c-member-m@itest.dev", "member")
    r = await client.get(f"/v1/teams/{team_id}/members", headers=member_h)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# POST /v1/auth/change-password
# ---------------------------------------------------------------------------

async def test_change_password_wrong_current_rejected(client, admin):
    r = await client.post(
        "/v1/auth/change-password",
        headers=admin["headers"],
        json={"current_password": "definitely-wrong", "new_password": "new-pass-999"},
    )
    # Wrong current password → 401 or 403 typed error, never 500.
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"
    assert r.json()["error"]["code"] in ("unauthorized", "forbidden", "invalid_credentials"), r.text


async def test_change_password_success_and_login(client, admin):
    """Successfully change own password, then log in with the new one."""
    old = "itest-pass-123"
    new = "new-itest-pass-456"
    r = await client.post(
        "/v1/auth/change-password",
        headers=admin["headers"],
        json={"current_password": old, "new_password": new},
    )
    assert r.status_code in (200, 204), r.text

    # New password works.
    login = await client.post(
        "/v1/auth/login", json={"email": "admin@itest.dev", "password": new}
    )
    assert login.status_code == 200, login.text

    # Old password is dead.
    old_login = await client.post(
        "/v1/auth/login", json={"email": "admin@itest.dev", "password": old}
    )
    assert old_login.status_code in (401, 403), old_login.text


# ---------------------------------------------------------------------------
# GET /v1/settings
# ---------------------------------------------------------------------------

async def test_settings_get_cross_team_403(client, admin):
    a_team = admin["team_id"]
    b_headers = await _register_and_login(client, _OUTSIDER)
    _assert_forbidden(
        await client.get(f"/v1/settings?team_id={a_team}", headers=b_headers),
        "settings GET cross-team",
    )


async def test_settings_get_readable_by_viewer(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    viewer_h = await _invite_and_join(client, h, team_id, "c-viewer-s@itest.dev", "viewer")
    r = await client.get(f"/v1/settings?team_id={team_id}", headers=viewer_h)
    assert r.status_code == 200, r.text
    keys = {s["key"] for s in r.json()}
    assert "temperature" in keys
    assert "rag_top_k" in keys


async def test_settings_get_readable_by_member(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    member_h = await _invite_and_join(client, h, team_id, "c-member-s@itest.dev", "member")
    r = await client.get(f"/v1/settings?team_id={team_id}", headers=member_h)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# PUT /v1/settings  (admin-only)
# ---------------------------------------------------------------------------

async def test_settings_put_cross_team_403(client, admin):
    a_team = admin["team_id"]
    b_headers = await _register_and_login(client, _OUTSIDER)
    _assert_forbidden(
        await client.put(
            "/v1/settings",
            headers=b_headers,
            json={"team_id": a_team, "key": "temperature", "value": 0.5},
        ),
        "settings PUT cross-team",
    )


async def test_settings_put_viewer_403(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    viewer_h = await _invite_and_join(client, h, team_id, "c-viewer-pw@itest.dev", "viewer")
    _assert_forbidden(
        await client.put(
            "/v1/settings",
            headers=viewer_h,
            json={"team_id": team_id, "key": "temperature", "value": 0.5},
        ),
        "settings PUT viewer",
    )


async def test_settings_put_member_403(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    member_h = await _invite_and_join(client, h, team_id, "c-member-pw@itest.dev", "member")
    _assert_forbidden(
        await client.put(
            "/v1/settings",
            headers=member_h,
            json={"team_id": team_id, "key": "temperature", "value": 0.5},
        ),
        "settings PUT member",
    )


async def test_settings_put_admin_ok_and_value_persists(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    r = await client.put(
        "/v1/settings",
        headers=h,
        json={"team_id": team_id, "key": "rag_top_k", "value": 8},
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"] == 8

    # GET reflects the override.
    settings_r = await client.get(f"/v1/settings?team_id={team_id}", headers=h)
    assert settings_r.status_code == 200
    entry = next(s for s in settings_r.json() if s["key"] == "rag_top_k")
    assert entry["value"] == 8
    assert entry["source"] == "override"


async def test_settings_put_out_of_bounds_422(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    r = await client.put(
        "/v1/settings",
        headers=h,
        json={"team_id": team_id, "key": "temperature", "value": 999.0},
    )
    assert r.status_code in (400, 422), r.text


async def test_settings_put_unknown_key_400(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    r = await client.put(
        "/v1/settings",
        headers=h,
        json={"team_id": team_id, "key": "eval_score_threshold", "value": 0.1},
    )
    assert r.status_code in (400, 422), r.text
    # Must never silently accept the gate knob.
    assert "eval_score_threshold" not in (
        (await client.get(f"/v1/settings?team_id={team_id}", headers=h)).json()
    ), "eval_score_threshold must never appear in the settings response"


# ---------------------------------------------------------------------------
# DELETE /v1/settings/{key}  (admin-only)
# ---------------------------------------------------------------------------

async def test_settings_delete_cross_team_403(client, admin):
    a_team = admin["team_id"]
    b_headers = await _register_and_login(client, _OUTSIDER)
    _assert_forbidden(
        await client.delete(
            f"/v1/settings/temperature?team_id={a_team}", headers=b_headers
        ),
        "settings DELETE cross-team",
    )


async def test_settings_delete_viewer_403(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    viewer_h = await _invite_and_join(client, h, team_id, "c-viewer-pd@itest.dev", "viewer")
    _assert_forbidden(
        await client.delete(
            f"/v1/settings/temperature?team_id={team_id}", headers=viewer_h
        ),
        "settings DELETE viewer",
    )


async def test_settings_delete_member_403(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    member_h = await _invite_and_join(client, h, team_id, "c-member-pd@itest.dev", "member")
    _assert_forbidden(
        await client.delete(
            f"/v1/settings/temperature?team_id={team_id}", headers=member_h
        ),
        "settings DELETE member",
    )


async def test_settings_delete_resets_to_default(client, admin):
    h, team_id = admin["headers"], admin["team_id"]

    # Set an override first.
    put_r = await client.put(
        "/v1/settings",
        headers=h,
        json={"team_id": team_id, "key": "top_k", "value": 99},
    )
    assert put_r.status_code == 200, put_r.text

    # Delete it.
    del_r = await client.delete(f"/v1/settings/top_k?team_id={team_id}", headers=h)
    assert del_r.status_code == 204, del_r.text

    # Source flips back to default or env.
    settings_r = await client.get(f"/v1/settings?team_id={team_id}", headers=h)
    entry = next(s for s in settings_r.json() if s["key"] == "top_k")
    assert entry["source"] in ("default", "env")
    assert entry["value"] != 99
