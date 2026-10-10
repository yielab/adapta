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
