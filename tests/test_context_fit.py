"""
A4.3 — context-window fitting: drop low-relevance chunks, then reject; cap max_tokens.

llama-cpp silently truncates an over-long prompt, and RAG injects context BEFORE
the question, so the question is what gets cut. `_fit_context` instead drops the
lowest-relevance chunks first and rejects with a typed 422 if the prompt can't
leave room to answer even with no chunks. These are pure tests (no model).
"""

import pytest

from adapta.domain.errors import InvalidRequest
from adapta.services.chat import _build_system, _fit_context


class FakeRag:
    def build_context_block(self, chunks):
        return "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(chunks))


def test_build_system_variants():
    assert _build_system(None, None, []) is None
    assert _build_system("base", None, []) == "base"
    s = _build_system("base", FakeRag(), ["a", "b"])
    assert "base" in s and "[1] a" in s and "[2] b" in s


def test_fits_without_dropping_and_clamps_max_tokens():
    # prompt=80, n_ctx=100 → fits (80+16≤100); max_tokens clamped to 100−80=20
    system, chunks, mx = _fit_context(
        count_fn=lambda sp: 80,
        n_ctx=100,
        base_system="b",
        rag_service=FakeRag(),
        rag_chunks=["a", "b"],
        max_tokens=50,
    )
    assert chunks == ["a", "b"]
    assert mx == 20


def test_drops_lowest_relevance_chunks_until_fit():
    import re

    # cost = 50 + 30 per retained chunk (counted via the [n] citation markers; the
    # instruction's literal "[N]" is not a \d marker, so it doesn't inflate the count)
    def count_fn(sp):
        return 50 + 30 * len(re.findall(r"\[\d+\]", sp or ""))

    system, chunks, mx = _fit_context(
        count_fn=count_fn,
        n_ctx=100,
        base_system="b",
        rag_service=FakeRag(),
        rag_chunks=["a", "b", "c"],
        max_tokens=20,
    )
    # 3 chunks=140, 2=110, 1=80 (+16 reserve =96 ≤100) → keep exactly 1
    assert len(chunks) == 1
    assert mx == 20  # min(20, 100−80)


def test_rejects_when_prompt_cannot_fit_even_without_chunks():
    with pytest.raises(InvalidRequest) as exc:
        _fit_context(
            count_fn=lambda sp: 200,
            n_ctx=100,
            base_system="b",
            rag_service=FakeRag(),
            rag_chunks=["a"],
            max_tokens=20,
        )
    assert "too long" in exc.value.message


# ---------------------------------------------------------------------------
# E3.5 — system-prompt assembly order, abstention, client system merge
# ---------------------------------------------------------------------------


def test_build_system_order_project_rag_abstention_client():
    from adapta.services.chat import ABSTENTION_LINE

    s = _build_system("PROJECT", FakeRag(), ["a"], abstain=True, client_system="CLIENT")
    assert s.index("PROJECT") < s.index("[1] a") < s.index(ABSTENTION_LINE) < s.index("CLIENT")


def test_build_system_zero_chunks_keeps_abstention_line():
    from adapta.services.chat import ABSTENTION_LINE

    s = _build_system("PROJECT", FakeRag(), [], abstain=True, client_system="CLIENT")
    assert "Use the following context" not in s
    assert s.index("PROJECT") < s.index(ABSTENTION_LINE) < s.index("CLIENT")
    assert "I can't find that in the documents." in s


def test_build_system_without_knowledge_has_no_abstention():
    assert _build_system("P", None, [], client_system="C") == "P\n\nC"
    assert _build_system(None, None, []) is None


def test_split_client_system_merges_system_turns_into_one_paragraph():
    from adapta.services.chat import split_client_system

    msgs = [
        {"role": "system", "content": "Be terse."},
        {"role": "user", "content": "hi"},
        {"role": "system", "content": [{"type": "text", "text": "Use Spanish."}]},
    ]
    turns, system = split_client_system(msgs)
    assert [m["role"] for m in turns] == ["user"]
    assert system == "Be terse.\n\nUse Spanish."
    assert split_client_system([{"role": "user", "content": "x"}])[1] is None


# ---------------------------------------------------------------------------
# E5.3 - condense the conversation into a standalone retrieval query
# ---------------------------------------------------------------------------


class _CondenseBackend:
    """Records the condensation call; returns a canned one-line question."""

    def __init__(self, content="How many vacation days do employees get?", boom=False):
        self.calls = []
        self.content = content
        self.boom = boom

    async def prepare(self, model_name, adapter_path):
        return object()

    async def generate(self, handle, req):
        from adapta.core.inference import InferenceResponse

        self.calls.append(req)
        if self.boom:
            raise RuntimeError("engine down")
        return InferenceResponse(
            content=self.content, model="m", prompt_tokens=30, completion_tokens=9
        )


_TWO_TURNS = [
    {"role": "user", "content": "What is the vacation policy?"},
    {"role": "assistant", "content": "Employees accrue vacation monthly [1]."},
    {"role": "user", "content": "and how many days for that?"},
]


async def _plan(monkeypatch, backend, messages, condense=True):
    from adapta.services import chat

    monkeypatch.setattr(chat, "get_backend", lambda model_name, adapter_path: backend)
    return await chat._retrieval_queries(
        model_name="m", adapter_path=None, messages=messages, condense=condense
    )


async def test_single_turn_skips_condensation(monkeypatch):
    backend = _CondenseBackend()
    q, pt, ct, b, _h = await _plan(monkeypatch, backend, _TWO_TURNS[2:])
    assert q == "and how many days for that?" and (pt, ct) == (0, 0)
    assert backend.calls == [] and b is None


async def test_two_turns_condense_once_and_keep_the_original(monkeypatch):
    backend = _CondenseBackend()
    q, pt, ct, _, _ = await _plan(monkeypatch, backend, _TWO_TURNS)
    assert q == ["How many vacation days do employees get?", "and how many days for that?"]
    assert (pt, ct) == (30, 9)
    assert len(backend.calls) == 1
    req = backend.calls[0]
    assert req.temperature == 0.0 and req.max_tokens == 40
    assert "vacation policy" in req.messages[0].content  # history reaches the condenser


async def test_condense_opt_out(monkeypatch):
    backend = _CondenseBackend()
    q, *_ = await _plan(monkeypatch, backend, _TWO_TURNS, condense=False)
    assert q == "and how many days for that?" and backend.calls == []


async def test_condense_failure_falls_back_to_raw_message(monkeypatch):
    backend = _CondenseBackend(boom=True)
    q, pt, ct, _, _ = await _plan(monkeypatch, backend, _TWO_TURNS)
    assert q == "and how many days for that?" and (pt, ct) == (0, 0)


async def test_condense_empty_or_identical_output_uses_raw_message(monkeypatch):
    for content in ("", "  and how many days for that?  "):
        q, *_ = await _plan(monkeypatch, _CondenseBackend(content=content), _TWO_TURNS)
        assert q == "and how many days for that?"


async def test_chat_counts_condensation_tokens_and_retrieves_on_both(monkeypatch):
    from adapta.core.inference import InferenceResponse
    from adapta.services import chat
    from adapta.services.rag import RetrievedChunk

    seen = {}

    class Rag(FakeRag):
        def retrieve(self, project_id, query, top_k, **kw):
            seen["query"] = query
            return [
                RetrievedChunk(
                    text="t", source="s", score=0.9, chunk_index=0, score_kind="vector"
                )
            ]

        def format_citations(self, chunks):
            return [{"index": 1}]

    class Handle:
        def count_prompt_tokens(self, msgs, sp):
            return 10

        def context_size(self):
            return 4096

    class Backend(_CondenseBackend):
        async def prepare(self, model_name, adapter_path):
            return Handle()

        async def generate(self, handle, req):
            if req.max_tokens == 40:
                return await super().generate(handle, req)
            return InferenceResponse(
                content="30 days [1]", model="m", prompt_tokens=100, completion_tokens=5
            )

    async def top_k(*a, **k):
        return 3

    monkeypatch.setattr(chat, "get_rag_service", lambda: Rag())
    monkeypatch.setattr(chat, "get_backend", lambda m, a: Backend())
    monkeypatch.setattr(chat, "_resolve_rag_top_k", top_k)
    out = await chat.chat(model_name="m", messages=_TWO_TURNS, project_id="p")
    assert seen["query"] == [
        "How many vacation days do employees get?",
        "and how many days for that?",
    ]
    assert out["usage"] == {"prompt_tokens": 130, "completion_tokens": 14, "total_tokens": 144}
    assert out["citations"] == [{"index": 1}]
