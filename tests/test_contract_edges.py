"""Contract edges found by schemathesis (E1.11): the 405 `Allow` header and email
validity as a domain rule."""

import pytest

from adapta.domain.errors import InvalidRequest


@pytest.mark.parametrize(
    "path, allow",
    [
        ("/v1/projects", "GET, POST"),
        ("/v1/projects/p1", "DELETE, GET, PATCH"),
        ("/v1/projects/p1/datasets/synthesize", "POST"),  # literal beats /datasets/{id}
        ("/v1/settings", "GET, PUT"),
    ],
)
@pytest.mark.asyncio
async def test_405_allow_lists_every_method_of_the_resource(path, allow):
    """FastAPI registers one route per method; `Allow` must still be the union."""
    from httpx import ASGITransport, AsyncClient

    from adapta.api.app import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        resp = await c.request("OPTIONS", path)

    assert resp.status_code == 405
    assert resp.headers["allow"] == allow
    assert resp.json()["error"]["code"] == "method_not_allowed"


def test_email_is_a_domain_rule_not_a_schema_constraint():
    """A `format: email`-valid string that email-validator rejects (.test TLD) must
    pass the DTO and be answered 400 by the handler's helper."""
    from adapta.api.v1.auth import _valid_email
    from adapta.models.generated import LoginRequest, RegisterRequest

    LoginRequest(email="r=84@tj8p.wpkgt.test", password="x")
    RegisterRequest(org_name="o", email="a@b.test", password="x")
    with pytest.raises(InvalidRequest):
        _valid_email("a@b.test")
    assert _valid_email("Ann@Example.COM") == "Ann@example.com"
