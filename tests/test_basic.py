"""Basic smoke tests — do not require a running DB/Redis/Chroma."""

import json

import pytest

# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

def test_error_taxonomy():
    from brain.domain.errors import (
        EvalGateFailed,
        Forbidden,
        InferenceFailed,
        InvalidRequest,
        NotFound,
        TrainingFailed,
        Unauthorized,
    )
    assert InvalidRequest(message="x").status == 400
    assert Unauthorized(message="x").status == 401
    assert Forbidden(message="x").status == 403
    assert NotFound(message="x").status == 404
    assert TrainingFailed(message="x").status == 500
    assert EvalGateFailed(message="x").status == 422
    assert InferenceFailed(message="x").status == 500


def test_error_internal_detail_not_exposed():
    """internal_detail must not appear in the serialisable fields."""
    from brain.domain.errors import InternalError
    err = InternalError(message="oops", internal_detail="secret stack trace")
    assert err.internal_detail == "secret stack trace"
    # Only message, code, status are public-safe
    assert hasattr(err, "message")
    assert hasattr(err, "code")
    assert hasattr(err, "status")


# ---------------------------------------------------------------------------
# Document chunking
# ---------------------------------------------------------------------------

def test_chunk_text_splits_correctly():
    from brain.services.documents import chunk_text
    text = "Hello world. " * 200
    chunks = chunk_text(text, source="doc.txt", chunk_size=256, chunk_overlap=32)
    assert len(chunks) > 1
    for c in chunks:
        assert c.text.strip()
        assert c.source == "doc.txt"


def test_chunk_text_index_is_sequential():
    from brain.services.documents import chunk_text
    text = "Sentence one. Sentence two. " * 100
    chunks = chunk_text(text, source="s.txt", chunk_size=128, chunk_overlap=16)
    for i, c in enumerate(chunks):
        assert c.index == i


def test_chunk_text_short_text_single_chunk():
    from brain.services.documents import chunk_text
    text = "Short."
    chunks = chunk_text(text, source="s.txt", chunk_size=512, chunk_overlap=64)
    assert len(chunks) == 1
    assert chunks[0].text.strip() == "Short."


def test_extract_text_plaintext(tmp_path):
    from brain.services.documents import extract_text
    f = tmp_path / "note.txt"
    f.write_text("Hello plain text.")
    text = extract_text(f, "text/plain")
    assert "Hello plain text." in text


def test_extract_text_markdown(tmp_path):
    from brain.services.documents import extract_text
    f = tmp_path / "doc.md"
    f.write_text("# Title\n\nSome **bold** content.")
    text = extract_text(f, "text/markdown")
    assert "Title" in text
    assert "content" in text


def test_extract_text_html_strips_tags(tmp_path):
    from brain.services.documents import extract_text
    f = tmp_path / "page.html"
    f.write_text("<html><body><p>Hello <b>world</b></p></body></html>")
    text = extract_text(f, "text/html")
    assert "Hello" in text
    assert "<b>" not in text


# ---------------------------------------------------------------------------
# Dataset validation
# ---------------------------------------------------------------------------

def test_dataset_validation_valid(tmp_path):
    from brain.services.training import validate_dataset
    ds = tmp_path / "data.jsonl"
    ds.write_text(
        json.dumps({"prompt": "Hello?", "response": "Hi there."}) + "\n" +
        json.dumps({"prompt": "What is 2+2?", "response": "4"}) + "\n"
    )
    valid, error, count = validate_dataset(ds)
    assert valid
    assert error is None
    assert count == 2


def test_dataset_validation_with_optional_fields(tmp_path):
    from brain.services.training import validate_dataset
    ds = tmp_path / "data.jsonl"
    ds.write_text(
        json.dumps({"prompt": "Q?", "response": "A.", "system": "Be helpful.", "metadata": {"source": "web"}}) + "\n"
    )
    valid, error, count = validate_dataset(ds)
    assert valid
    assert count == 1


def test_dataset_validation_missing_response(tmp_path):
    from brain.services.training import validate_dataset
    ds = tmp_path / "bad.jsonl"
    ds.write_text(json.dumps({"prompt": "Hello?"}) + "\n")
    valid, error, count = validate_dataset(ds)
    assert not valid
    assert "response" in error


def test_dataset_validation_empty_prompt(tmp_path):
    from brain.services.training import validate_dataset
    ds = tmp_path / "bad.jsonl"
    ds.write_text(json.dumps({"prompt": "", "response": "A"}) + "\n")
    valid, error, count = validate_dataset(ds)
    assert not valid


def test_dataset_validation_empty(tmp_path):
    from brain.services.training import validate_dataset
    ds = tmp_path / "empty.jsonl"
    ds.write_text("")
    valid, error, count = validate_dataset(ds)
    assert not valid


def test_dataset_validation_bad_json(tmp_path):
    from brain.services.training import validate_dataset
    ds = tmp_path / "bad.jsonl"
    ds.write_text("not json\n")
    valid, error, count = validate_dataset(ds)
    assert not valid
    assert "invalid JSON" in error


# ---------------------------------------------------------------------------
# Synthesis pair extraction (unit — no LLM needed)
# ---------------------------------------------------------------------------

def test_synthesis_extract_pairs_valid():
    from brain.services.synthesis import _extract_pairs
    raw = '[{"question": "What is X?", "answer": "X is Y."}]'
    pairs = _extract_pairs(raw)
    assert len(pairs) == 1
    assert pairs[0]["question"] == "What is X?"
    assert pairs[0]["answer"] == "X is Y."


def test_synthesis_extract_pairs_with_fence():
    from brain.services.synthesis import _extract_pairs
    raw = '```json\n[{"question": "Q?", "answer": "A."}]\n```'
    pairs = _extract_pairs(raw)
    assert len(pairs) == 1


def test_synthesis_extract_pairs_empty_fields_skipped():
    from brain.services.synthesis import _extract_pairs
    raw = '[{"question": "", "answer": "A."}, {"question": "Q?", "answer": ""}]'
    pairs = _extract_pairs(raw)
    assert len(pairs) == 0


def test_synthesis_extract_pairs_malformed_returns_empty():
    from brain.services.synthesis import _extract_pairs
    assert _extract_pairs("not json at all") == []
    assert _extract_pairs("") == []


def test_synthesis_to_instruction_pair():
    from brain.services.synthesis import _to_instruction_pair
    record = _to_instruction_pair({"question": "Q?", "answer": "A."})
    assert record["prompt"] == "Q?"
    assert record["response"] == "A."
    assert "system" not in record


def test_synthesis_to_instruction_pair_with_system():
    from brain.services.synthesis import _to_instruction_pair
    record = _to_instruction_pair({"question": "Q?", "answer": "A."}, system="Be concise.")
    assert record["system"] == "Be concise."


# ---------------------------------------------------------------------------
# Health endpoint (in-process, no infra needed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_endpoint():
    from httpx import ASGITransport, AsyncClient

    from brain.api.app import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_unhandled_error_returns_correlation_id():
    """Global exception handler must return correlation_id, never a raw traceback."""
    from httpx import ASGITransport, AsyncClient

    from brain.api.app import create_app

    app = create_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("something exploded")

    # raise_app_exceptions=False: Starlette's ServerErrorMiddleware sends the 500
    # envelope AND re-raises so the ASGI server can log it; under ASGITransport we
    # want the response, not the propagated exception.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert "error" in body
    assert "correlation_id" in body["error"]
    # Raw error message must not leak
    assert "exploded" not in body["error"].get("message", "")


@pytest.mark.asyncio
async def test_domain_error_serialisation():
    """DomainError must serialise message + code, never internal_detail."""
    from httpx import ASGITransport, AsyncClient

    from brain.api.app import create_app
    from brain.domain.errors import InvalidRequest

    app = create_app()

    @app.get("/bad")
    async def bad():
        raise InvalidRequest(message="bad input", internal_detail="DB query: SELECT * FROM users")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/bad")

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["message"] == "bad input"
    assert "DB query" not in json.dumps(body)
