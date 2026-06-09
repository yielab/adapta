"""Integration tests for the team invitation flow + read-only role (§3.1)."""

import pytest

pytestmark = pytest.mark.integration


async def _invite(client, headers, team_id, email, role):
    return await client.post(
        "/v1/auth/invite",
        headers=headers,
        json={"email": email, "team_id": team_id, "role": role},
    )


async def _accept_and_login(client, token, email, password="newpass123"):
    acc = await client.post("/v1/auth/accept-invite", json={"token": token, "password": password})
    assert acc.status_code == 201, acc.text
    login = await client.post("/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_invite_accept_member_can_write(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    inv = await _invite(client, h, team_id, "member@itest.dev", "member")
    assert inv.status_code == 201, inv.text
    assert inv.json()["token"]  # token shown once at creation
    assert inv.json()["role"] == "member"

    member_h = await _accept_and_login(client, inv.json()["token"], "member@itest.dev")
    # member can read AND write
    assert (await client.get(f"/v1/projects?team_id={team_id}", headers=member_h)).status_code == 200
    created = await client.post(
        "/v1/projects",
        headers=member_h,
        json={"name": "by-member", "type": "rag", "base_model": "x", "team_id": team_id},
    )
    assert created.status_code == 201, created.text


async def test_viewer_is_read_only(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    inv = await _invite(client, h, team_id, "viewer@itest.dev", "viewer")
    assert inv.status_code == 201, inv.text
    viewer_h = await _accept_and_login(client, inv.json()["token"], "viewer@itest.dev")

    # viewer can read
    assert (await client.get(f"/v1/projects?team_id={team_id}", headers=viewer_h)).status_code == 200
    # ...but not mutate
    blocked = await client.post(
        "/v1/projects",
        headers=viewer_h,
        json={"name": "by-viewer", "type": "rag", "base_model": "x", "team_id": team_id},
    )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["error"]["code"] in ("forbidden", "insufficient_permissions")


async def test_invite_requires_admin(client, admin):
    # A plain member cannot issue invites.
    h, team_id = admin["headers"], admin["team_id"]
    inv = await _invite(client, h, team_id, "m2@itest.dev", "member")
    member_h = await _accept_and_login(client, inv.json()["token"], "m2@itest.dev")
    forbidden = await _invite(client, member_h, team_id, "x@itest.dev", "member")
    assert forbidden.status_code == 403, forbidden.text


async def test_list_invitations_hides_token(client, admin):
    h, team_id = admin["headers"], admin["team_id"]
    await _invite(client, h, team_id, "listed@itest.dev", "member")
    listed = await client.get(f"/v1/auth/invitations?team_id={team_id}", headers=h)
    assert listed.status_code == 200, listed.text
    assert any(i["email"] == "listed@itest.dev" for i in listed.json())
    assert all(i["token"] is None for i in listed.json())  # token never returned on list


async def test_accept_invalid_token_404(client):
    r = await client.post("/v1/auth/accept-invite", json={"token": "nope", "password": "longenough1"})
    assert r.status_code == 404
