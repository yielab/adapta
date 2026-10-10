"""F1.1 — a model ``null`` is an absent field; a hung vision call ends the extract job `failed`."""

from __future__ import annotations

import asyncio

import pytest

from adapta.domain.errors import Timeout
from adapta.services import extraction

_SCHEMA = {"properties": {"vendor": {"type": "string"}, "total": {"type": "string"}, "date": {"type": "string"}}}


def test_parse_fields_omits_null_and_null_like_strings():
    assert extraction.parse_fields('{"total": null, "vendor": "ACME"}', _SCHEMA) == {"vendor": "ACME"}
    raw = '{"total": "null", "vendor": "ACME", "date": " None "}'
    assert extraction.parse_fields(raw, _SCHEMA) == {"vendor": "ACME"}
    assert extraction.parse_fields('{"total": "NULL", "vendor": "none", "date": ""}', _SCHEMA) is None
    assert extraction.parse_fields('{"vendor": "Nullarbor Ltd"}', _SCHEMA) == {"vendor": "Nullarbor Ltd"}


def test_extract_job_exceeding_its_deadline_raises_a_typed_timeout(monkeypatch, tmp_path):
    from adapta.config import settings
    from adapta.db import session as db_session
    from adapta.worker import main as worker

    class Row:
        page, needs_review = 1, True

    class FakeFile:
        storage_path, project_id, filename = str(tmp_path / "a.pdf"), "p1", "a.pdf"

    class FakeProject:
        extraction_schema = _SCHEMA

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

        def scalar_one(self):
            return self.value

        def all(self):
            return [Row()]

    results = [FakeFile(), FakeProject(), None]

    class FakeDb:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *a, **k):
            return Result(results.pop(0))

    slow_calls = []

    async def slow_ask(png, text, *, model):
        slow_calls.append(1)
        await asyncio.sleep(30)

    statuses = []

    class Q:
        async def update_status(self, job_id, **k):
            statuses.append(k.get("status"))

    monkeypatch.setattr(db_session, "AsyncSessionLocal", FakeDb)
    monkeypatch.setattr(extraction, "render_page", lambda path, page: b"png")
    monkeypatch.setattr(extraction, "_ask", slow_ask)
    monkeypatch.setattr(settings, "extract_page_timeout_seconds", 0.05)
    monkeypatch.setattr(worker, "get_job_queue", lambda: Q())

    with pytest.raises(Timeout) as err:
        asyncio.run(worker._extract_job({"job_id": "j", "payload": {"id": "f1"}}))
    assert "timed out" in err.value.message
    assert slow_calls == [1]  # the hung page ended the job
    assert statuses == ["running"]  # the worker loop turns the raised DomainError into `failed`
