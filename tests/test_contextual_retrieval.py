"""
Unit tests for contextual retrieval at index time (E5.1): the situating-sentence generator
(stubbed LLM), the context window, and that ``context`` changes what is embedded/indexed while
the stored text stays the raw chunk. No Chroma / DB / model needed.
"""

import asyncio

import pytest

from adapta.domain.errors import InternalError
from adapta.services import synthesis as syn
from adapta.services.documents import Chunk
from adapta.services.rag import build_chunk_rows, indexed_text


def _chunks(*texts, ctx=None):
    return [Chunk(text=t, source="doc.md", index=i, context=ctx) for i, t in enumerate(texts)]


def test_indexed_text_is_raw_without_context_and_prefixed_with_it():
    plain, with_ctx = _chunks("alpha"), _chunks("alpha", ctx="From the HR policy.")
    assert indexed_text(plain[0]) == "alpha"  # OFF path: the exact pre-E5.1 embedding input
    assert indexed_text(with_ctx[0]) == "From the HR policy.\n\nalpha"


def test_chunk_rows_keep_raw_text_and_hash_and_store_context():
    rows = build_chunk_rows("p", "f", _chunks("alpha", ctx="Situating."))
    assert rows[0].text == "alpha" and rows[0].context == "Situating."
    off = build_chunk_rows("p", "f", _chunks("alpha"))
    assert off[0].context is None and off[0].content_hash == rows[0].content_hash


def test_context_window_whole_doc_or_neighbours():
    texts = ["a" * 10, "b" * 10, "c" * 10, "d" * 10, "e" * 10]
    assert syn._context_window(texts, 2, 1000) == "\n\n".join(texts)
    win = syn._context_window(texts, 2, 32)  # room for the chunk plus its two neighbours
    assert win == "\n\n".join(texts[1:4])
    assert syn._context_window(texts, 0, 12) == texts[0]


def test_contextualize_sets_context_and_leaves_text(monkeypatch):
    seen = {}

    async def fake(system, user, *, model, teacher_base_url, teacher_model, max_tokens, temperature):
        seen.update(model=model, max_tokens=max_tokens, temperature=temperature)
        return "  Part of the\nvacation policy. "

    monkeypatch.setattr(syn, "_generate", fake)
    out = asyncio.run(syn.contextualize_chunks(_chunks("one", "two"), model="m"))
    assert [c.text for c in out] == ["one", "two"]
    assert [c.context for c in out] == ["Part of the vacation policy."] * 2
    assert seen["model"] == "m" and seen["temperature"] == 0.0


def test_contextualize_tolerates_partial_failure_but_not_total(monkeypatch):
    calls = {"n": 0}

    async def flaky(system, user, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return "ctx"

    monkeypatch.setattr(syn, "_generate", flaky)
    out = asyncio.run(syn.contextualize_chunks(_chunks("a", "b"), model="m"))
    assert [c.context for c in out] == [None, "ctx"]

    async def dead(system, user, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr(syn, "_generate", dead)
    with pytest.raises(InternalError):
        asyncio.run(syn.contextualize_chunks(_chunks("a", "b"), model="m"))
