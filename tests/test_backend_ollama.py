"""Ollama serving backend (E2.1): routing, request mapping, usage, streaming.

A mocked httpx transport stands in for the Ollama host; the live run is
OPERATIONS §9."""

from __future__ import annotations

import json

import httpx
import pytest

from adapta.config import settings
from adapta.core.backends import get_backend
from adapta.core.backends.llamacpp import LlamaCppBackend
from adapta.core.backends.ollama_backend import OllamaBackend, format_for
from adapta.core.inference import InferenceRequest, Message
from adapta.domain.errors import InferenceFailed, InvalidRequest, ModelNotFound

MODEL = "qwen2.5-1.5b-instruct"
TAG = "qwen2.5:1.5b-instruct"


@pytest.fixture
def ollama_on(monkeypatch):
    monkeypatch.setattr(settings, "serving_backend", "ollama")


def _backend(handler, seen=None):
    def wrapped(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append((request.url.path, json.loads(request.content)))
        return handler(request)

    return OllamaBackend(transport=httpx.MockTransport(wrapped))


def _req(**kw):
    return InferenceRequest(
        messages=[Message(role="user", content="hola")],
        model_name=MODEL,
        system_prompt="ctx",
        stream=False,
        **kw,
    )


def _ok_show_then(chat):
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={})
        return chat(request)

    return handler


# ── routing ──────────────────────────────────────────────────────────────


def test_default_backend_is_llamacpp():
    assert isinstance(get_backend(MODEL, None), LlamaCppBackend)


def test_ollama_serves_adapterless_mapped_text(ollama_on):
    assert isinstance(get_backend(MODEL, None), OllamaBackend)


def test_adapter_stays_on_llamacpp(ollama_on):
    assert isinstance(get_backend(MODEL, "/data/adapters/x/adapter.gguf"), LlamaCppBackend)


def test_unmapped_and_vision_models_stay_on_llamacpp(ollama_on):
    assert isinstance(get_backend("qwen2.5-vl-7b-instruct", None), LlamaCppBackend)
    assert isinstance(get_backend("not-in-map", None), LlamaCppBackend)


def test_default_map_covers_only_commercial_catalog_entries():
    from adapta.core.model_catalog import resolve

    for name in settings.ollama_model_map:
        entry = resolve(name)
        assert entry is not None and entry.commercial_use


# ── format mapping ───────────────────────────────────────────────────────


def test_format_for():
    assert format_for(None) is None
    assert format_for({"type": "text"}) is None
    assert format_for({"type": "json_object"}) == "json"
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    rf = {"type": "json_schema", "json_schema": {"name": "x", "schema": schema}}
    assert format_for(rf) == schema
    with pytest.raises(InvalidRequest):
        format_for({"type": "json_schema", "json_schema": {}})


# ── non-streaming ────────────────────────────────────────────────────────


async def test_generate_maps_request_and_exact_usage():
    seen: list = []

    def chat(request):
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "hi"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 31,
                "eval_count": 7,
            },
        )

    backend = _backend(_ok_show_then(chat), seen)
    handle = await backend.prepare(MODEL, None)
    resp = await backend.generate(
        handle, _req(response_format={"type": "json_object"}, stop=["END"])
    )

    assert (resp.prompt_tokens, resp.completion_tokens, resp.total_tokens) == (31, 7, 38)
    assert resp.content == "hi" and resp.finish_reason == "stop"
    assert handle.usage == (31, 7)
    assert seen[0] == ("/api/show", {"model": TAG})
    path, body = seen[1]
    assert path == "/api/chat"
    assert body["model"] == TAG and body["stream"] is False
    assert body["format"] == "json"
    assert body["messages"][0] == {"role": "system", "content": "ctx"}
    assert body["messages"][1] == {"role": "user", "content": "hola"}
    assert body["options"]["num_predict"] == settings.max_tokens
    assert body["options"]["stop"] == ["END"]


async def test_length_finish_reason():
    def chat(request):
        return httpx.Response(
            200, json={"message": {"content": "x"}, "done": True, "done_reason": "length"}
        )

    backend = _backend(_ok_show_then(chat))
    resp = await backend.generate(await backend.prepare(MODEL, None), _req())
    assert resp.finish_reason == "length"


async def test_unpulled_model_is_model_not_found():
    backend = _backend(lambda r: httpx.Response(404, json={"error": "not found"}))
    with pytest.raises(ModelNotFound) as exc:
        await backend.prepare(MODEL, None)
    assert TAG in exc.value.internal_detail


async def test_host_down_is_inference_failed():
    def boom(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(InferenceFailed):
        await _backend(boom).prepare(MODEL, None)


async def test_chat_http_error_is_typed():
    backend = _backend(_ok_show_then(lambda r: httpx.Response(500, text="oom")))
    handle = await backend.prepare(MODEL, None)
    with pytest.raises(InferenceFailed):
        await backend.generate(handle, _req())


async def test_adapter_is_rejected_if_routing_is_bypassed():
    with pytest.raises(InvalidRequest):
        await _backend(lambda r: httpx.Response(200, json={})).prepare(MODEL, "/a.gguf")


# ── streaming ────────────────────────────────────────────────────────────


async def test_stream_yields_tokens_and_records_usage():
    frames = [
        {"message": {"content": "Hel"}, "done": False},
        {"message": {"content": ""}, "done": False},
        {"message": {"content": "lo"}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 12, "eval_count": 2},
    ]

    def chat(request):
        return httpx.Response(200, content="\n".join(json.dumps(f) for f in frames).encode())

    seen: list = []
    backend = _backend(_ok_show_then(chat), seen)
    handle = await backend.prepare(MODEL, None)
    tokens = [t async for t in backend.generate_stream(handle, _req())]

    assert tokens == ["Hel", "lo"]
    assert handle.usage == (12, 2)
    assert seen[1][1]["stream"] is True


async def test_stream_error_frame_is_typed():
    def chat(request):
        return httpx.Response(200, content=b'{"error": "boom"}\n')

    backend = _backend(_ok_show_then(chat))
    handle = await backend.prepare(MODEL, None)
    with pytest.raises(InferenceFailed):
        _ = [t async for t in backend.generate_stream(handle, _req())]


# ── context-fit estimate ────────────────────────────────────────────────


async def test_prompt_estimate_is_pessimistic_and_context_is_configured():
    backend = _backend(_ok_show_then(lambda r: httpx.Response(200, json={})))
    handle = await backend.prepare(MODEL, None)
    assert handle.context_size() == settings.max_context_length
    n = handle.count_prompt_tokens([Message(role="user", content="a" * 300)], "b" * 30)
    assert n >= 330 // 4
