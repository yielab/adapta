"""E3.5 — deterministic abstention: no surviving chunk -> canned answer, no model call;
a model answer that is itself the abstention sentence carries no citations."""

import json

from adapta.core.backends.base import BackendHandle, ServingBackend
from adapta.core.inference import InferenceResponse
from adapta.services import chat as chat_mod
from adapta.services.chat import ABSTENTION_ANSWER, chat, chat_stream, is_abstention
from adapta.services.rag import RetrievedChunk

MSGS = [{"role": "user", "content": "Who won the 1998 World Cup?"}]


class _Handle(BackendHandle):
    def context_size(self):
        return 4096

    def count_prompt_tokens(self, messages, system_prompt):
        return 10


class _Backend(ServingBackend):
    def __init__(self, answer="France"):
        self.answer = answer
        self.calls = 0

    async def prepare(self, model_name, adapter_path):
        return _Handle()

    async def generate(self, handle, request):
        self.calls += 1
        return InferenceResponse(
            content=self.answer, model="m", prompt_tokens=10, completion_tokens=2
        )

    async def generate_stream(self, handle, request):
        self.calls += 1
        for tok in self.answer.split(" "):
            yield tok + " "


class _Rag:
    def build_context_block(self, chunks):
        return "ctx"

    def format_citations(self, chunks):
        return [{"index": i + 1, "text": c.text} for i, c in enumerate(chunks)]


def _setup(monkeypatch, chunks, backend):
    async def fake_retrieve(*a, **k):
        return chunks

    async def fake_top_k(*a, **k):
        return 5

    monkeypatch.setattr(chat_mod, "_retrieve", fake_retrieve)
    monkeypatch.setattr(chat_mod, "_resolve_rag_top_k", fake_top_k)
    monkeypatch.setattr(chat_mod, "get_rag_service", lambda: _Rag())
    monkeypatch.setattr(chat_mod, "get_backend", lambda *a, **k: backend)


def _chunk():
    return RetrievedChunk(text="t", source="s", score=0.9, chunk_index=0, score_kind="vector")


def test_is_abstention():
    assert is_abstention("  I can't find that in the documents. Sorry.")
    assert is_abstention("i CAN'T find that in the documents")
    assert not is_abstention("France won. I can't find that in the documents.")


async def test_no_chunks_answers_without_model_call(monkeypatch):
    backend = _Backend()
    _setup(monkeypatch, [], backend)
    out = await chat(model_name="qwen2.5-3b-instruct", messages=MSGS, project_id="p")
    assert out["choices"][0]["message"]["content"] == ABSTENTION_ANSWER
    assert out["citations"] == []
    assert out["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    assert backend.calls == 0


async def test_model_abstention_drops_citations(monkeypatch):
    _setup(monkeypatch, [_chunk()], _Backend(answer=ABSTENTION_ANSWER))
    out = await chat(model_name="qwen2.5-3b-instruct", messages=MSGS, project_id="p")
    assert out["citations"] == []


async def test_grounded_answer_keeps_citations(monkeypatch):
    _setup(monkeypatch, [_chunk()], _Backend(answer="France [1]"))
    out = await chat(model_name="qwen2.5-3b-instruct", messages=MSGS, project_id="p")
    assert len(out["citations"]) == 1


def _frames(raw):
    return [json.loads(f[6:]) for f in raw if f.startswith("data: {")]


async def _collect(**kw):
    return [f async for f in chat_stream(model_name="qwen2.5-3b-instruct", messages=MSGS, **kw)]


async def test_stream_no_chunks_single_content_frame_then_final(monkeypatch):
    backend = _Backend()
    _setup(monkeypatch, [], backend)
    raw = await _collect(project_id="p")
    frames = _frames(raw)
    assert len(frames) == 2
    assert frames[0]["choices"][0]["delta"]["content"] == ABSTENTION_ANSWER
    assert frames[1]["citations"] == []
    assert frames[1]["usage"]["total_tokens"] == 0
    assert raw[-1] == "data: [DONE]\n\n"
    assert backend.calls == 0


async def test_stream_model_abstention_drops_citations(monkeypatch):
    _setup(monkeypatch, [_chunk()], _Backend(answer=ABSTENTION_ANSWER))
    final = _frames(await _collect(project_id="p"))[-1]
    assert final["citations"] == []


async def test_stream_grounded_keeps_citations(monkeypatch):
    _setup(monkeypatch, [_chunk()], _Backend(answer="France [1]"))
    final = _frames(await _collect(project_id="p"))[-1]
    assert len(final["citations"]) == 1
