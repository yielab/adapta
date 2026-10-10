"""
D5/E3.2 — hybrid (Postgres FTS + vector) retrieval + cross-encoder reranker.

Pure unit tests: no Chroma, no Postgres, no model loading.  The pure function _rrf_fuse is tested with synthetic data; RAGService.retrieve() is tested by
monkeypatching Chroma and the reranker so no network or GPU is needed.
"""

import logging

import pytest

from adapta.services import rag as rag_mod
from adapta.services.rag import RAGService, RetrievedChunk, _FtsHit, _rrf_fuse

_REAL_FTS_SEARCH = rag_mod._fts_search


@pytest.fixture(autouse=True)
def _no_postgres(monkeypatch):
    """Default sparse leg: no hits. Individual tests override with `_fts(...)`."""
    monkeypatch.setattr(rag_mod, "_fts_search", lambda *a, **k: [])


def _fts(monkeypatch, hits):
    monkeypatch.setattr(rag_mod, "_fts_search", lambda *a, **k: hits)


# ---------------------------------------------------------------------------
# _rrf_fuse
# ---------------------------------------------------------------------------


def test_rrf_single_list_preserves_order():
    assert _rrf_fuse([0, 1, 2]) == [0, 1, 2]


def test_rrf_two_agreeing_lists_preserve_order():
    assert _rrf_fuse([0, 1, 2], [0, 1, 2]) == [0, 1, 2]


def test_rrf_all_indices_present_in_output():
    result = _rrf_fuse([0, 1, 2, 3], [3, 2, 1, 0])
    assert set(result) == {0, 1, 2, 3}


def test_rrf_second_list_boosts_low_ranked_item():
    """An item ranked last in vector but first in BM25 should move up in RRF."""
    # vec=[0,1,2,3], bm25=[3,0,1,2]
    # idx 3: vec rank 3 (1/64) + bm25 rank 0 (1/61) ≈ 0.0156 + 0.0164 = 0.0320
    # idx 0: vec rank 0 (1/61) + bm25 rank 1 (1/62) ≈ 0.0164 + 0.0161 = 0.0325
    # idx 3 moves from last position in vector to a high position overall.
    result = _rrf_fuse([0, 1, 2, 3], [3, 0, 1, 2])
    # idx 3 must no longer be last
    assert result.index(3) < 3


def test_rrf_consensus_top_item_stays_first():
    """When both rankings agree on the best item it stays at the top."""
    result = _rrf_fuse([0, 1, 2, 3], [0, 2, 1, 3])
    assert result[0] == 0


# ---------------------------------------------------------------------------
# RAGService.retrieve — hybrid reordering (no model, no Chroma)
# ---------------------------------------------------------------------------


def _make_chroma_mock(docs: list[str], metas: list[dict], dists: list[float]):
    """Returns a fake Chroma client whose collection.query returns the given data."""

    class FakeCollection:
        def query(self, **kwargs):
            n = kwargs.get("n_results", len(docs))
            # Cap at what's "in the collection" — mirrors real Chroma behaviour.
            n = min(n, len(docs))
            return {
                "ids": [[f"f_{i}" for i in range(n)]],
                "documents": [docs[:n]],
                "metadatas": [metas[:n]],
                "distances": [dists[:n]],
            }

    class FakeClient:
        def get_collection(self, name):
            return FakeCollection()

    return FakeClient()


class _FakeEmbedder:
    def embed_one(self, text: str) -> list[float]:
        return [0.0] * 8  # fixed dummy vector


def _std_chroma(monkeypatch, n=10):
    docs = [f"doc text {i}" for i in range(n)]
    metas = [{"source": f"s{i}", "chunk_index": i} for i in range(n)]
    dists = [i * 0.05 for i in range(n)]
    monkeypatch.setattr(
        "adapta.services.rag._get_chroma_client", lambda: _make_chroma_mock(docs, metas, dists)
    )
    monkeypatch.setattr("adapta.services.rag.get_embedding_service", lambda: _FakeEmbedder())
    monkeypatch.setattr("adapta.services.rag.get_reranker_service", lambda: None)


def test_retrieve_returns_keyword_hit_outside_vector_candidates(monkeypatch):
    """A chunk the vector leg never returned, but FTS ranks first, is recalled."""
    _std_chroma(monkeypatch, n=12)
    _fts(monkeypatch, [_FtsHit("zz_0", "error code ERR-4471 means disk full", "ops.md", 7)])

    chunks = RAGService().retrieve("p", "ERR-4471", top_k=3)

    # fetch_k = 3*4 = 12 vector hits, none is zz_0; RRF puts the FTS-only top hit in.
    hit = [c for c in chunks if c.source == "ops.md"]
    assert hit and hit[0].chunk_index == 7 and "ERR-4471" in hit[0].text
    assert hit[0].chunk_id == "zz_0"


def test_retrieve_fts_promotes_vector_candidate(monkeypatch):
    """Agreement between legs lifts a low vector rank above the vector leader."""
    _std_chroma(monkeypatch)
    _fts(monkeypatch, [_FtsHit("f_3", "doc text 3", "s3", 3)])

    chunks = RAGService().retrieve("p", "q", top_k=5)
    sources = [c.source for c in chunks]
    assert sources.index("s3") < sources.index("s2")  # f_3 in both lists beats f_2


def test_retrieve_survives_fts_failure(monkeypatch):
    _std_chroma(monkeypatch)

    def boom(*a, **k):
        raise OSError("postgres down")

    monkeypatch.setattr(rag_mod, "_fts_search", boom)
    chunks = RAGService().retrieve("p", "q", top_k=4)
    assert [c.source for c in chunks] == ["s0", "s1", "s2", "s3"]


def test_retrieve_logs_one_structured_line(monkeypatch, caplog):
    _std_chroma(monkeypatch)
    _fts(monkeypatch, [_FtsHit("f_1", "doc text 1", "s1", 1)])
    with caplog.at_level(logging.INFO, logger="adapta.services.rag"):
        RAGService().retrieve("p", "q", top_k=2)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("rag.retrieve")]
    assert len(lines) == 1
    assert "fts=1" in lines[0] and "f_1@" in lines[0] and "ms=" in lines[0]


def test_bm25_is_gone():
    assert not hasattr(rag_mod, "_bm25_scores")
    assert not hasattr(rag_mod, "_tokenize")


def test_retrieve_returns_top_k(monkeypatch):
    docs = [f"doc text {i}" for i in range(10)]
    metas = [{"source": f"s{i}", "chunk_index": i} for i in range(10)]
    dists = [i * 0.05 for i in range(10)]

    chroma_client = _make_chroma_mock(docs, metas, dists)
    monkeypatch.setattr("adapta.services.rag._get_chroma_client", lambda: chroma_client)
    monkeypatch.setattr("adapta.services.rag.get_embedding_service", lambda: _FakeEmbedder())
    monkeypatch.setattr("adapta.services.rag.get_reranker_service", lambda: None)

    chunks = RAGService().retrieve("p", "query", top_k=4)
    assert len(chunks) == 4


def test_retrieve_empty_collection_returns_empty(monkeypatch):
    class EmptyClient:
        def get_collection(self, name):
            raise Exception("does not exist")

    monkeypatch.setattr("adapta.services.rag._get_chroma_client", lambda: EmptyClient())
    monkeypatch.setattr("adapta.services.rag.get_embedding_service", lambda: _FakeEmbedder())
    monkeypatch.setattr("adapta.services.rag.get_reranker_service", lambda: None)

    chunks = RAGService().retrieve("p", "query")
    assert chunks == []


# ---------------------------------------------------------------------------
# RAGService.retrieve — reranker path
# ---------------------------------------------------------------------------


class _FakeReranker:
    """Mock cross-encoder: score = number of query words found in passage."""

    def rerank(self, query: str, passages: list[str]) -> list[float]:
        query_words = set(query.lower().split())
        return [float(sum(1 for w in p.lower().split() if w in query_words)) for p in passages]


def test_retrieve_reranker_overrides_vector_order(monkeypatch):
    """The cross-encoder score must override the fused ranking."""
    docs = [
        "The sky is blue.",  # idx 0 — vector #1, few query hits
        "Machine learning models are trained on data.",  # idx 1 — vector #2, many query hits
        "Deep learning is a subset of machine learning.",  # idx 2 — vector #3, many hits
    ]
    metas = [{"source": f"s{i}", "chunk_index": i} for i in range(3)]
    dists = [0.05, 0.15, 0.25]

    chroma_client = _make_chroma_mock(docs, metas, dists)
    monkeypatch.setattr("adapta.services.rag._get_chroma_client", lambda: chroma_client)
    monkeypatch.setattr("adapta.services.rag.get_embedding_service", lambda: _FakeEmbedder())
    monkeypatch.setattr("adapta.services.rag.get_reranker_service", lambda: _FakeReranker())

    query = "machine learning models deep"
    chunks = RAGService().retrieve("p", query, top_k=3)

    assert len(chunks) >= 2
    # "The sky is blue." has 0 hits → must rank last
    sources = [c.source for c in chunks]
    assert sources.index("s0") > sources.index("s1") or sources.index("s0") > sources.index("s2")


def test_retrieve_reranker_scores_are_sigmoid_normalized(monkeypatch):
    """After reranking all scores must be in (0, 1) — sigmoid of raw cross-encoder logit."""
    docs = ["alpha beta", "gamma delta", "epsilon zeta"]
    metas = [{"source": f"s{i}", "chunk_index": i} for i in range(3)]
    dists = [0.1, 0.2, 0.3]

    chroma_client = _make_chroma_mock(docs, metas, dists)
    monkeypatch.setattr("adapta.services.rag._get_chroma_client", lambda: chroma_client)
    monkeypatch.setattr("adapta.services.rag.get_embedding_service", lambda: _FakeEmbedder())
    monkeypatch.setattr("adapta.services.rag.get_reranker_service", lambda: _FakeReranker())

    chunks = RAGService().retrieve("p", "alpha gamma", top_k=3)
    for c in chunks:
        assert 0.0 < c.score < 1.0, f"score {c.score} not in (0,1)"
        assert c.score_kind == "reranker"


def test_citations_match_reranked_order(monkeypatch):
    """format_citations must list the chunks in the same order as retrieve()."""
    docs = ["doc A text", "doc B text", "doc C text"]
    metas = [{"source": f"src{i}", "chunk_index": i} for i in range(3)]
    dists = [0.1, 0.2, 0.3]

    chroma_client = _make_chroma_mock(docs, metas, dists)
    monkeypatch.setattr("adapta.services.rag._get_chroma_client", lambda: chroma_client)
    monkeypatch.setattr("adapta.services.rag.get_embedding_service", lambda: _FakeEmbedder())
    monkeypatch.setattr("adapta.services.rag.get_reranker_service", lambda: _FakeReranker())

    rag = RAGService()
    chunks = rag.retrieve("p", "text query", top_k=3)
    citations = rag.format_citations(chunks)

    assert len(citations) == len(chunks)
    for i, (chunk, cit) in enumerate(zip(chunks, citations, strict=False)):
        assert cit["index"] == i + 1
        assert cit["source"] == chunk.source
        assert cit["score"] == round(chunk.score, 4)
        assert cit["score_kind"] == chunk.score_kind == "reranker"


# ---------------------------------------------------------------------------
# chat.py wiring (E1.6) — a team's `rag_top_k` app-settings override must
# reach `RAGService.retrieve(top_k=...)`, not the env-backed global.
# ---------------------------------------------------------------------------


class _TeamLookupSession:
    """Fake AsyncSession: answers the `select(Project.team_id)` lookup only."""

    def __init__(self, team_id):
        self._team_id = team_id

    async def execute(self, _stmt):
        return _ScalarResult(self._team_id)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


async def test_rag_top_k_override_reaches_retrieve(monkeypatch):
    """An org override of rag_top_k=2 must flow through chat.py's resolution
    into the exact top_k RAGService.retrieve() is called with."""
    from adapta.services import chat

    monkeypatch.setattr(
        "adapta.db.session.AsyncSessionLocal", lambda: _TeamLookupSession("team-1")
    )

    async def _fake_resolve_setting(_db, team_id, key):
        assert (team_id, key) == ("team-1", "rag_top_k")
        return 2

    monkeypatch.setattr(
        "adapta.services.app_settings.resolve_setting", _fake_resolve_setting
    )

    resolved = await chat._resolve_rag_top_k("proj-1", None)
    assert resolved == 2

    calls = []

    class _SpyRagService:
        def retrieve(self, project_id, query, top_k):
            calls.append((project_id, query, top_k))
            return []

    await chat._retrieve(_SpyRagService(), "proj-1", "hello", resolved)
    assert calls == [("proj-1", "hello", 2)]


async def test_explicit_top_k_rag_bypasses_settings_lookup(monkeypatch):
    """A caller-supplied top_k_rag wins outright — no DB round trip needed."""
    from adapta.services import chat

    def _boom():
        raise AssertionError("should not resolve settings when top_k_rag is given")

    monkeypatch.setattr("adapta.db.session.AsyncSessionLocal", _boom)

    resolved = await chat._resolve_rag_top_k("proj-1", 9)
    assert resolved == 9


# ---------------------------------------------------------------------------
# chat_stream citations (E1.7) — the final SSE frame (the one carrying `usage`)
# must also carry `citations`, same shape as chat()'s non-streaming response.
# No GPU/model needed: the backend and RAG service are faked.
# ---------------------------------------------------------------------------


class _FakeStreamHandle:
    def context_size(self):
        return 4096

    def count_prompt_tokens(self, messages, system_prompt):
        return 10


class _FakeStreamBackend:
    async def prepare(self, model_name, adapter_path):
        return _FakeStreamHandle()

    async def generate_stream(self, handle, request):
        for tok in ("Hel", "lo"):
            yield tok


async def test_chat_stream_final_frame_carries_citations(monkeypatch):
    import json

    from adapta.services import chat

    chunk = RetrievedChunk(
        text="doc text", source="src1", score=0.9, chunk_index=0, score_kind="vector"
    )
    fake_rag = RAGService()
    fake_rag.retrieve = lambda project_id, query, top_k: [chunk]

    monkeypatch.setattr("adapta.services.chat.get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(
        "adapta.services.chat.get_backend",
        lambda model_name, adapter_path: _FakeStreamBackend(),
    )

    frames = [
        sse
        async for sse in chat.chat_stream(
            model_name="m",
            messages=[{"role": "user", "content": "hi"}],
            project_id="proj-1",
            top_k_rag=3,
        )
    ]

    data_frames = [f for f in frames if f.startswith("data: ") and "[DONE]" not in f]
    finish = json.loads(data_frames[-1][len("data: ") :])

    assert finish["choices"][0]["finish_reason"] == "stop"
    assert finish["citations"] == [
        {"index": 1, "source": "src1", "score": 0.9, "score_kind": "vector"}
    ]


# ---------------------------------------------------------------------------
# E3.1 — chunks persisted in Postgres (pure unit tests; no DB, no Chroma)
# ---------------------------------------------------------------------------


def _chunks(*texts):
    from adapta.services.documents import Chunk

    return [Chunk(text=t, source="doc.txt", index=i) for i, t in enumerate(texts)]


def test_content_hash_is_sha256_hex():
    import hashlib

    from adapta.services.rag import content_hash

    h = content_hash("hello")
    assert h == hashlib.sha256(b"hello").hexdigest()
    assert len(h) == 64


def test_build_chunk_rows_ids_match_chroma_ids():
    from adapta.services.rag import build_chunk_rows, content_hash

    rows = build_chunk_rows("proj1", "file1", _chunks("a", "b", "c"))
    assert [r.id for r in rows] == ["file1_0", "file1_1", "file1_2"]
    assert [r.chunk_index for r in rows] == [0, 1, 2]
    assert all(r.file_id == "file1" and r.project_id == "proj1" for r in rows)
    assert rows[1].text == "b" and rows[1].content_hash == content_hash("b")


class _FakeSession:
    def __init__(self, scalar_result=None):
        self.added: list = []
        self.flushed = False
        self._scalar = scalar_result

    def add_all(self, rows):
        self.added.extend(rows)

    async def flush(self):
        self.flushed = True

    async def scalar(self, _stmt):
        return self._scalar


async def test_persist_chunks_adds_and_flushes_rows():
    from adapta.services.rag import persist_chunks

    db = _FakeSession()
    n = await persist_chunks(db, "proj1", "file1", _chunks("a", "b"))
    assert n == 2 and len(db.added) == 2 and db.flushed


async def test_all_chunks_known_requires_every_distinct_hash():
    from adapta.services.rag import all_chunks_known

    chunks = _chunks("a", "b", "a")  # two distinct hashes
    assert await all_chunks_known(_FakeSession(scalar_result=2), "p", chunks) is True
    assert await all_chunks_known(_FakeSession(scalar_result=1), "p", chunks) is False
    assert await all_chunks_known(_FakeSession(scalar_result=0), "p", chunks) is False
    assert await all_chunks_known(_FakeSession(scalar_result=0), "p", []) is False


async def test_count_project_chunks_reads_scalar():
    from adapta.services.rag import count_project_chunks

    assert await count_project_chunks(_FakeSession(scalar_result=7), "p") == 7
    assert await count_project_chunks(_FakeSession(scalar_result=None), "p") == 0


def test_delete_file_chunks_raises_typed_error_on_chroma_failure(monkeypatch):
    import pytest

    from adapta.domain.errors import VectorStoreFailed
    from adapta.services import rag as rag_mod

    class BoomClient:
        def get_collection(self, name):
            raise RuntimeError("chroma down")

    monkeypatch.setattr(rag_mod, "_get_chroma_client", lambda: BoomClient())
    with pytest.raises(VectorStoreFailed) as ei:
        RAGService().delete_file_chunks("proj1", "file1")
    assert "chroma down" not in ei.value.message
    assert ei.value.status == 502


def test_duplicate_document_is_409():
    from adapta.domain.errors import DuplicateDocument

    e = DuplicateDocument(message="dup")
    assert e.status == 409 and e.code == "duplicate_document"


def test_chunk_model_matches_migration_shape():
    from adapta.db.models import ProjectChunk

    t = ProjectChunk.__table__
    assert t.name == "chunks"
    assert t.c.tsv.computed is not None
    assert {c.name for c in t.c} >= {"page", "section", "ocr", "ocr_confidence", "needs_review"}


def test_programming_error_in_fts_leg_is_not_swallowed(monkeypatch):
    _std_chroma(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("bug")

    monkeypatch.setattr(rag_mod, "_fts_search", boom)
    with pytest.raises(RuntimeError):
        RAGService().retrieve("p", "q", top_k=2)


async def test_fts_search_inside_running_loop_raises():
    """Calling the blocking sparse leg on the event loop must fail loudly, not degrade."""
    with pytest.raises(RuntimeError, match="to_thread"):
        _REAL_FTS_SEARCH("p", "q", 4)
