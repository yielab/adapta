"""Tests for the observability surface — /metrics + JSON logging (§3.5)."""

from __future__ import annotations

import json
import logging

import pytest
from httpx import ASGITransport, AsyncClient

from adapta.api.app import create_app
from adapta.core.logging_config import JsonLogFormatter, configure_logging


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
    assert "adapta_requests_total" in body
    assert "adapta_request_duration_seconds" in body
    assert "# TYPE adapta_request_duration_seconds histogram" in body
    # E3.7 retrieval + ingestion series are always exported (zero until observed)
    for name in (
        "adapta_rag_retrieval_seconds",
        "adapta_rag_chunks_returned",
        "adapta_rag_reranker_seconds",
        "adapta_index_seconds_per_page",
    ):
        assert f"# TYPE {name} histogram" in body, name
        assert f"{name}_count" in body, name


def test_retrieval_histograms_record_observations():
    from adapta.core.metrics import MetricsCollector

    mc = MetricsCollector()
    mc.rag_retrieval_seconds.observe(0.2)
    mc.rag_chunks_returned.observe(5)
    out = mc.export_prometheus()
    assert "adapta_rag_retrieval_seconds_count 1" in out
    assert 'adapta_rag_chunks_returned_bucket{le="5"} 1' in out


def test_json_log_formatter_emits_valid_json():
    rec = logging.LogRecord(
        name="adapta.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    out = json.loads(JsonLogFormatter().format(rec))
    assert out["level"] == "INFO"
    assert out["logger"] == "adapta.test"
    assert out["message"] == "hello world"


def test_configure_logging_text_is_default(monkeypatch):
    # Default (text) must not raise and installs a single root handler.
    configure_logging()
    assert logging.getLogger().handlers
