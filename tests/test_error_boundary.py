"""
Error-boundary tests — every DomainError subclass must serialize correctly
and internal_detail must never appear in the response body.
"""

import json

import pytest

from brain.domain.errors import (
    Conflict,
    EmbeddingFailed,
    EvalGateFailed,
    Forbidden,
    InferenceFailed,
    InternalError,
    InvalidRequest,
    ModelNotFound,
    NotFound,
    ProjectNotFound,
    RateLimited,
    Timeout,
    TrainingFailed,
    Unauthorized,
)

ALL_DOMAIN_ERRORS = [
    (InvalidRequest,    400, "invalid_request"),
    (Unauthorized,      401, "unauthorized"),
    (Forbidden,         403, "forbidden"),
    (NotFound,          404, "not_found"),
    (Conflict,          409, "conflict"),
    (ModelNotFound,     404, "model_not_found"),
    (ProjectNotFound,   404, "project_not_found"),
    (TrainingFailed,    500, "training_failed"),
    (InferenceFailed,   500, "inference_failed"),
    (EmbeddingFailed,   500, "embedding_failed"),
    (EvalGateFailed,    422, "eval_gate_failed"),
    (RateLimited,       429, "rate_limited"),
    (Timeout,           504, "timeout"),
    (InternalError,     500, "internal_error"),
]


@pytest.mark.parametrize("error_cls, expected_status, expected_code", ALL_DOMAIN_ERRORS)
@pytest.mark.asyncio
async def test_domain_error_http_status_and_code(error_cls, expected_status, expected_code):
    """Each DomainError subclass must produce the correct HTTP status + code envelope."""
    from httpx import ASGITransport, AsyncClient

    from brain.api.app import create_app

    app = create_app()

    @app.get("/test-error")
    async def trigger():
        raise error_cls(
            message="test message",
            internal_detail="this must not leak: secret=abc",
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/test-error")

    assert resp.status_code == expected_status, (
        f"{error_cls.__name__}: expected {expected_status}, got {resp.status_code}"
    )
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == expected_code
    assert body["error"]["message"] == "test message"
    assert "correlation_id" in body["error"]


@pytest.mark.parametrize("error_cls, expected_status, expected_code", ALL_DOMAIN_ERRORS)
@pytest.mark.asyncio
async def test_internal_detail_never_in_response(error_cls, expected_status, expected_code):
    """internal_detail must NEVER appear in the serialized response."""
    from httpx import ASGITransport, AsyncClient

    from brain.api.app import create_app

    app = create_app()

    @app.get("/test-leak")
    async def trigger():
        raise error_cls(
            message="safe message",
            internal_detail="SENSITIVE: db_password=hunter2",
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/test-leak")

    raw = json.dumps(resp.json())
    assert "SENSITIVE" not in raw
    assert "hunter2" not in raw
    assert "db_password" not in raw


@pytest.mark.asyncio
async def test_correlation_id_header_echoed():
    """X-Correlation-ID header must be present and consistent in the response."""
    from httpx import ASGITransport, AsyncClient

    from brain.api.app import create_app

    app = create_app()

    @app.get("/stable")
    async def stable():
        raise InvalidRequest(message="oops")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/stable")

    assert "x-correlation-id" in resp.headers
    cid = resp.headers["x-correlation-id"]
    assert len(cid) > 0
    assert cid == resp.json()["error"]["correlation_id"]


@pytest.mark.asyncio
async def test_unhandled_exception_returns_generic_message():
    """RuntimeError (not a DomainError) must return 500 with a generic message."""
    from httpx import ASGITransport, AsyncClient

    from brain.api.app import create_app

    app = create_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("raw internal detail")

    # raise_app_exceptions=False: ServerErrorMiddleware sends the 500 envelope and
    # re-raises for server-side logging; under ASGITransport we assert the response.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert "raw internal detail" not in json.dumps(body)
    assert "correlation_id" in body["error"]
