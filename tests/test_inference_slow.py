"""Slow test: real llama-cpp inference through ChatService (§1.8).

Pins the inference contract — a completion comes back non-empty with populated
usage — without depending on a large model. Marked `slow` (opt-in) and skipped
unless a GGUF is present under the default model dir, so the offline `make ci`
gate (which ships no model) skips it cleanly.

Run with a model downloaded:
    docker compose exec app pytest -m slow tests/test_inference_slow.py
"""

from __future__ import annotations

import pytest

from brain.config import settings

pytestmark = pytest.mark.slow

_MODEL_NAME = "qwen2.5-3b-instruct"  # config key; dir is models_dir/qwen2.5-3b
_MODEL_DIR = settings.models_dir / "qwen2.5-3b"
_HAS_MODEL = _MODEL_DIR.exists() and any(_MODEL_DIR.glob("*.gguf"))

skip_no_model = pytest.mark.skipif(not _HAS_MODEL, reason="no GGUF model present")


@skip_no_model
async def test_chat_returns_completion_with_usage():
    from brain.services.chat import chat

    result = await chat(
        model_name=_MODEL_NAME,
        messages=[{"role": "user", "content": "Reply with a single short greeting."}],
        max_tokens=32,
    )

    content = result["choices"][0]["message"]["content"]
    assert isinstance(content, str) and content.strip(), "completion must be non-empty"

    usage = result["usage"]
    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert result["choices"][0]["finish_reason"]


@skip_no_model
async def test_chat_stream_yields_tokens_and_usage():
    from brain.services.chat import chat_stream

    chunks = []
    async for sse in chat_stream(
        model_name=_MODEL_NAME,
        messages=[{"role": "user", "content": "Count: one two three."}],
        max_tokens=32,
    ):
        chunks.append(sse)

    assert any("chat.completion.chunk" in c for c in chunks)
    assert chunks[-1].strip() == "data: [DONE]"
    # the penultimate frame carries the real (counted) completion-token usage
    assert any('"completion_tokens"' in c for c in chunks)
