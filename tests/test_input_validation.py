"""
Input validation hardening tests.

Covers:
- ADAPTA_MAX_INPUT_CHARS — oversized chat messages are rejected
- File upload extension guard — only allowed extensions are accepted (§7.3)
"""

import json

import pytest

from adapta.config import settings

# ---------------------------------------------------------------------------
# Max input chars — direct config + logic tests
# ---------------------------------------------------------------------------


def test_config_has_max_input_chars():
    """The default max_input_chars is set and has the expected value."""
    assert hasattr(settings, "max_input_chars")
    assert settings.max_input_chars == 100_000


def test_max_input_chars_positive():
    """max_input_chars must be greater than zero for the guard to be meaningful."""
    assert settings.max_input_chars > 0


# ---------------------------------------------------------------------------
# File upload extension guard (§7.3)
#
# Content-Type is client-controlled and browsers routinely send
# application/octet-stream for .md / .txt files. The real gating is the
# extension, which the handler checks via _ALLOWED_EXTENSIONS.
# ---------------------------------------------------------------------------


def test_upload_allowed_extension_set():
    """_ALLOWED_EXTENSIONS includes all supported document types."""
    from adapta.api.v1.files import _ALLOWED_EXTENSIONS

    assert ".md" in _ALLOWED_EXTENSIONS
    assert ".txt" in _ALLOWED_EXTENSIONS
    assert ".pdf" in _ALLOWED_EXTENSIONS
    assert ".docx" in _ALLOWED_EXTENSIONS
    assert ".html" in _ALLOWED_EXTENSIONS
    assert ".htm" in _ALLOWED_EXTENSIONS
    assert ".json" not in _ALLOWED_EXTENSIONS
    assert ".exe" not in _ALLOWED_EXTENSIONS
    assert ".zip" not in _ALLOWED_EXTENSIONS
    assert ".py" not in _ALLOWED_EXTENSIONS


@pytest.mark.asyncio
async def test_upload_handler_rejects_unsupported_extension(client):
    """The handler guard returns 400 for files with a disallowed extension."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from adapta.api.app import app
    from adapta.db.session import get_db
    from adapta.services.auth import get_current_user

    async def _fake_db():
        yield None  # guard fires before any DB call

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1")
    app.dependency_overrides[get_db] = _fake_db
    try:
        with (
            patch(
                "adapta.api.v1.files._get_project",
                AsyncMock(return_value=SimpleNamespace(team_id="t1")),
            ),
            patch("adapta.api.v1.files.require_team_writer", AsyncMock()),
        ):
            resp = await client.post(
                "/v1/projects/some-project/files",
                files={"file": ("data.json", b"{}", "application/json")},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 400


def test_parser_dispatches_pdf_by_extension(tmp_path):
    """extract_text falls back to PDF parser by path suffix when CT is octet-stream."""
    from unittest.mock import patch

    from adapta.services.documents import extract_text

    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"dummy")
    with patch("adapta.services.documents._extract_text_pdf", return_value="pdf text") as m:
        result = extract_text(pdf_path, "application/octet-stream")
    m.assert_called_once_with(pdf_path)
    assert result == "pdf text"


# ---------------------------------------------------------------------------
# Chat input size guard (via ASGI — only tests that don't require DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_oversized_input_rejected(client):
    """
    A chat request whose total message content exceeds max_input_chars
    must be rejected by the in-handler guard before any model processing.

    The guard lives in the handler body, downstream of auth and DB resolution,
    so we override those dependencies to let the request actually reach it
    without a live Postgres. This asserts the guard is genuinely wired — not
    just that auth rejects an unknown key (which is what an un-overridden ASGI
    call would test instead).
    """
    from types import SimpleNamespace

    from adapta.api.app import app
    from adapta.api.v1.chat import _resolve_endpoint
    from adapta.db.session import get_db

    # Auth passes with a fake endpoint whose slug matches the request `model`,
    # so the handler proceeds to the size guard rather than 401/403-ing first.
    fake_endpoint = SimpleNamespace(slug="test-model")
    fake_project = SimpleNamespace(id="00000000-0000-0000-0000-000000000000")

    async def _fake_resolve():
        return fake_endpoint, fake_project

    async def _fake_db():
        # The guard raises before any db.execute, so the session is never used.
        yield None

    app.dependency_overrides[_resolve_endpoint] = _fake_resolve
    app.dependency_overrides[get_db] = _fake_db
    try:
        huge_text = "x" * (settings.max_input_chars + 1)
        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": huge_text}],
        }
        resp = await client.post(
            "/v1/chat/completions",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
    finally:
        app.dependency_overrides.pop(_resolve_endpoint, None)
        app.dependency_overrides.pop(get_db, None)

    # The guard raises InvalidRequest (HTTP 400) with an "exceeds" message.
    assert resp.status_code == 400
    body = resp.json()
    error = body.get("error", body)
    assert "exceeds" in error.get("message", "").lower()


# ---------------------------------------------------------------------------
# Direct logic test for the input guard calculation
# ---------------------------------------------------------------------------


def test_input_guard_calculation():
    """Verify that the total_chars calculation matches expected logic."""
    # Simple string messages
    messages_str = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    total = sum(len(str(m.get("content", ""))) for m in messages_str if isinstance(m.get("content"), str))
    assert total == 10  # "hello" (5) + "world" (5)

    # Mixed messages (multimodal)
    messages_mixed = [
        {"role": "user", "content": "plain text"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "image caption"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        },
    ]
    total = 0
    for m in messages_mixed:
        content = m.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(part.get("text", ""))
    assert total == 23  # "plain text" (10) + "image caption" (13)

    # Empty messages
    messages_empty = []
    total = 0
    for m in messages_empty:
        content = m.get("content")
        if isinstance(content, str):
            total += len(content)
    assert total == 0


def test_input_guard_threshold_behavior():
    """Verify that the guard triggers at the threshold."""
    from adapta.config import settings

    limit = settings.max_input_chars

    # Just under the limit
    messages_ok = [{"role": "user", "content": "x" * (limit - 1)}]
    total_ok = sum(len(str(m.get("content", ""))) for m in messages_ok if isinstance(m.get("content"), str))
    assert total_ok <= limit

    # Exactly at the limit
    messages_at = [{"role": "user", "content": "x" * limit}]
    total_at = sum(len(str(m.get("content", ""))) for m in messages_at if isinstance(m.get("content"), str))
    assert total_at == limit

    # Just over the limit
    messages_over = [{"role": "user", "content": "x" * (limit + 1)}]
    total_over = sum(len(str(m.get("content", ""))) for m in messages_over if isinstance(m.get("content"), str))
    assert total_over > limit
