"""Tests for the observability surface — /metrics + JSON logging (§3.5)."""

from __future__ import annotations

import json
import logging

import pytest
from httpx import ASGITransport, AsyncClient

from brain.api.app import create_app
from brain.core.logging_config import JsonLogFormatter, configure_logging


@pytest.fixture
def app():
    return create_app()


async def test_metrics_endpoint_exposes_prometheus(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        # generate a couple of requests so counters move
        await ac.get("/health")
        await ac.get("/health")
        r = await ac.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    assert "brain_requests_total" in body
    assert "brain_request_duration_seconds" in body
    assert "# TYPE brain_request_duration_seconds histogram" in body


def test_json_log_formatter_emits_valid_json():
    rec = logging.LogRecord(
        name="brain.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    out = json.loads(JsonLogFormatter().format(rec))
    assert out["level"] == "INFO"
    assert out["logger"] == "brain.test"
    assert out["message"] == "hello world"


def test_configure_logging_text_is_default(monkeypatch):
    # Default (text) must not raise and installs a single root handler.
    configure_logging()
    assert logging.getLogger().handlers
