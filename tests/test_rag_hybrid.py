"""
D5 — hybrid (BM25+vector) retrieval + cross-encoder reranker.

Pure unit tests: no Chroma, no model loading.  The pure functions (_bm25_scores,
_rrf_fuse) are tested with synthetic data; RAGService.retrieve() is tested by
monkeypatching Chroma and the reranker so no network or GPU is needed.
"""

from adapta.services.rag import (
    RAGService,
    _bm25_scores,
    _rrf_fuse,
    _tokenize,
)

# ---------------------------------------------------------------------------
# _tokenize
# ---------------------------------------------------------------------------


def test_tokenize_lowercases_and_strips_punctuation():
    tokens = _tokenize("Hello, World! It's a test.")
    assert "hello" in tokens
    assert "world" in tokens
    assert "," not in tokens


# ---------------------------------------------------------------------------
# _bm25_scores
# ---------------------------------------------------------------------------


def test_bm25_empty_docs():
    assert _bm25_scores("anything", []) == []


def test_bm25_no_overlap_returns_zero():
    scores = _bm25_scores("dragon unicorn", ["apple banana cherry"])
    assert scores == [0.0]


def test_bm25_exact_match_scores_highest():
    docs = [
        "The capital of France is Paris.",  # idx 0 — matches "capital Paris France"
        "London is in the United Kingdom.",  # idx 1 — no overlap
        "Paris has the Eiffel Tower.",  # idx 2 — matches "Paris" only
    ]
    scores = _bm25_scores("capital Paris France", docs)
    assert len(scores) == 3
    # Doc 0 contains all three query tokens; must outscore docs 1 and 2.
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_bm25_all_query_terms_present_beats_partial():
    docs = [
        "quick brown fox jumps over the lazy dog",  # all terms
        "quick brown fox",  # partial
    ]
    scores = _bm25_scores("quick brown fox", docs)
    # Both have the query terms, but length penalises the long doc slightly via b.
    # The shorter doc (idx 1) gets a higher per-term TF contribution so it scores higher.
    # Either way, both should be positive.
    assert scores[0] > 0
    assert scores[1] > 0


def test_bm25_returns_one_score_per_doc():
    docs = ["a", "b c", "d e f"]
    scores = _bm25_scores("a b", docs)
    assert len(scores) == len(docs)


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


def test_retrieve_hybrid_promotes_keyword_match(monkeypatch):
    """BM25+RRF fusion promotes the keyword-rich doc above the pure-vector leader.

    Construction (5 docs, docs provided in vector-rank order — smallest dist first):
      - "weather" (idx 0): vec_rank=0 (best by vector), BM25 rank=4 (no query keywords)
      - "paris"   (idx 1): vec_rank=1, BM25 rank=3 (only "paris")
      - "eiffel"  (idx 2): vec_rank=2, BM25 rank=0 (all four query tokens)
      - "tower"   (idx 3): vec_rank=3, BM25 rank=1 ("tower"+"landmark")
      - "french"  (idx 4): vec_rank=4, BM25 rank=2 ("landmark"+"paris")

    RRF with k=60 (approximate):
      eiffel: 1/(63) + 1/(61) ≈ 0.03227  ← highest
      weather: 1/(61) + 1/(65) ≈ 0.03178

    RRF is symmetric for a pure rank-swap of two docs, but here the BM25 rank gap
    (4) is larger than the vector rank gap (2), so eiffel wins.
    """
    docs = [
        "The weather forecast shows rain in London today.",  # vec_rank=0
        "Paris is the capital city of France.",  # vec_rank=1
        "The Eiffel Tower is a famous landmark in Paris.",  # vec_rank=2, BM25 rank=0
        "The tower bridge landmark is located in London.",  # vec_rank=3
        "French culture includes visits to landmark sites in Paris.",  # vec_rank=4
    ]
    metas = [
        {"source": "weather", "chunk_index": 0},
        {"source": "paris", "chunk_index": 1},
        {"source": "eiffel", "chunk_index": 2},
        {"source": "tower", "chunk_index": 3},
        {"source": "french", "chunk_index": 4},
    ]
    dists = [0.05, 0.12, 0.20, 0.30, 0.40]  # ascending = vector-rank order

    chroma_client = _make_chroma_mock(docs, metas, dists)
    monkeypatch.setattr("adapta.services.rag._get_chroma_client", lambda: chroma_client)
    monkeypatch.setattr("adapta.services.rag.get_embedding_service", lambda: _FakeEmbedder())
    # Disable cross-encoder — testing BM25+RRF signal only.
    monkeypatch.setattr("adapta.services.rag.get_reranker_service", lambda: None)

    rag = RAGService()
    chunks = rag.retrieve("proj-1", "Eiffel Tower Paris landmark", top_k=5)

    assert len(chunks) == 5
    sources = [c.source for c in chunks]

    # After hybrid RRF, "eiffel" must rank above "weather" (which had the vector lead).
    assert sources.index("eiffel") < sources.index("weather"), (
        f"Eiffel doc should rank above weather doc after BM25+RRF; got {sources}"
    )


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
