"""
RAG service: per-project ChromaDB collections + hybrid cited retrieval.

Retrieval pipeline (D5):
  1. Vector search — fetch top_k × multiplier candidates from Chroma.
  2. BM25 score — keyword signal over the same candidates.
  3. Reciprocal Rank Fusion — merge the two ranked lists.
  4. Optional cross-encoder rerank over the top candidates.
  5. Return top_k chunks, best-first (§A4.3 pop() invariant preserved).
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import List, Optional

from adapta.config import settings
from adapta.services.embeddings import get_embedding_service, get_reranker_service

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float
    chunk_index: int


def _get_chroma_client():
    """Create a new ChromaDB HTTP client.  Called per-operation — no connection pool."""
    import chromadb

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def collection_name_for(project_id: str) -> str:
    """Return the Chroma collection name for a project.

    The convention ``proj_{project_id}`` is the value stored in
    ``Collection.chroma_collection_name``.  Changing this function without a
    migration would orphan all existing collections.
    """
    return f"proj_{project_id}"


# ---------------------------------------------------------------------------
# Hybrid retrieval helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _bm25_scores(
    query: str,
    docs: list[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """BM25 relevance score for *query* against each document in *docs*.

    Standard Robertson BM25 with k1=1.5 and b=0.75 on whitespace tokens.
    Returns one float per document; higher = more relevant.
    """
    if not docs:
        return []

    query_tokens = set(_tokenize(query))
    tokenized_docs = [_tokenize(d) for d in docs]
    dl = [len(td) for td in tokenized_docs]
    avgdl = sum(dl) / len(dl) if dl else 1.0
    n_docs = len(docs)

    scores: list[float] = []
    for i, doc_tokens in enumerate(tokenized_docs):
        tf_map: dict[str, int] = {}
        for t in doc_tokens:
            tf_map[t] = tf_map.get(t, 0) + 1

        score = 0.0
        for t in query_tokens:
            tf = tf_map.get(t, 0)
            if tf == 0:
                continue
            df = sum(1 for td in tokenized_docs if t in set(td))
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl[i] / avgdl))

        scores.append(score)

    return scores


def _rrf_fuse(*rank_lists: list[int], k: int = 60) -> list[int]:
    """Reciprocal Rank Fusion over multiple ranked index lists.

    Each list contains document indices ordered best-first.  Returns a merged
    list of indices ordered by descending RRF score.
    """
    rrf: dict[int, float] = {}
    for ranks in rank_lists:
        for rank, idx in enumerate(ranks):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(rrf, key=lambda i: rrf[i], reverse=True)


class RAGService:
    """Per-project ChromaDB collection management and hybrid cited retrieval.

    A new ChromaDB HTTP client is created on every call (``_client()`` →
    ``_get_chroma_client()``); there is no persistent connection held by
    this object.
    """

    def _client(self):
        return _get_chroma_client()

    def ensure_collection(self, project_id: str) -> str:
        """Create the Chroma collection if it doesn't exist; returns the name.

        Sets ``hnsw:space: cosine`` so the index uses cosine distance.  This
        metadata is applied only at creation — Chroma ignores it on
        ``get_or_create_collection`` calls for an existing collection, so the
        distance metric is locked in after the first call.
        """
        name = collection_name_for(project_id)
        client = self._client()
        client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
        return name

    def delete_collection(self, project_id: str) -> None:
        """Best-effort cleanup; silently swallows all errors.

        Called on project delete — a Chroma outage or already-absent collection
        must not block the project row from being removed from Postgres.
        """
        name = collection_name_for(project_id)
        client = self._client()
        try:
            client.delete_collection(name)
        except Exception:
            pass

    def index_chunks(
        self,
        project_id: str,
        file_id: str,
        chunks: list,  # List[Chunk] from documents.py
    ) -> int:
        """Embed and upsert chunks into the project collection; returns count.

        Uses ``upsert`` so re-indexing a file is idempotent — existing chunks
        for the same ``file_id`` are overwritten rather than duplicated.
        """
        if not chunks:
            return 0

        emb_service = get_embedding_service()
        texts = [c.text for c in chunks]
        embeddings = emb_service.embed(texts)

        name = collection_name_for(project_id)
        client = self._client()
        collection = client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

        ids = [f"{file_id}_{c.index}" for c in chunks]
        metadatas = [
            {"source": c.source, "chunk_index": c.index, "file_id": file_id} for c in chunks
        ]

        collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        return len(chunks)

    def delete_file_chunks(self, project_id: str, file_id: str) -> None:
        """Remove all chunks for a file from the Chroma collection.

        Two-step (``get`` then ``delete``) because Chroma's ``delete`` requires
        explicit IDs rather than accepting a ``where`` filter directly.
        """
        name = collection_name_for(project_id)
        client = self._client()
        try:
            collection = client.get_collection(name)
            results = collection.get(where={"file_id": file_id})
            if results["ids"]:
                collection.delete(ids=results["ids"])
        except Exception as exc:
            logger.warning("Failed to delete file chunks: %s", exc)

    def retrieve(
        self,
        project_id: str,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Hybrid retrieval: vector + BM25 fused via RRF, optional cross-encoder reranker.

        Pipeline (D5):
          1. Fetch fetch_k = top_k × multiplier candidates via Chroma vector search.
          2. BM25-score those candidates against the query.
          3. Reciprocal Rank Fusion of vector order + BM25 order.
          4. Optional cross-encoder reranker over the top rerank_n candidates.
          5. Return top_k, best-first (§A4.3 pop() invariant preserved).

        Citations reflect the final reranked scores (§A4.3 ordering).
        """
        top_k = top_k or settings.rag_top_k
        fetch_k = max(top_k * settings.rag_hybrid_fetch_multiplier, top_k + 1)

        emb_service = get_embedding_service()
        query_embedding = emb_service.embed_one(query)

        name = collection_name_for(project_id)
        client = self._client()
        try:
            collection = client.get_collection(name)
        except Exception:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=fetch_k,
            include=["documents", "metadatas", "distances"],
        )

        docs: list[str] = results["documents"][0]
        metas: list[dict] = results["metadatas"][0]
        dists: list[float] = results["distances"][0]

        if not docs:
            return []

        bm25 = _bm25_scores(query, docs)
        vec_order = list(range(len(docs)))
        bm25_order = sorted(range(len(docs)), key=lambda i: bm25[i], reverse=True)
        fused_order = _rrf_fuse(vec_order, bm25_order)

        candidates: List[RetrievedChunk] = [
            RetrievedChunk(
                text=docs[idx],
                source=metas[idx].get("source", "unknown"),
                score=1.0 - dists[idx],  # cosine distance → similarity
                chunk_index=metas[idx].get("chunk_index", 0),
            )
            for idx in fused_order
        ]

        reranker = get_reranker_service()
        if reranker is not None and len(candidates) > 1:
            rerank_n = min(top_k * 2, len(candidates))
            to_rerank = candidates[:rerank_n]
            raw_scores = reranker.rerank(query, [c.text for c in to_rerank])
            ranked = sorted(
                zip(raw_scores, to_rerank, strict=False),
                key=lambda x: x[0],
                reverse=True,
            )
            # Cross-encoder logits are unbounded; sigmoid maps them to (0, 1)
            # so the citation `score` field is comparable across requests.
            reranked = [
                RetrievedChunk(
                    text=c.text,
                    source=c.source,
                    score=round(1.0 / (1.0 + math.exp(-s)), 4),
                    chunk_index=c.chunk_index,
                )
                for s, c in ranked
            ]
            candidates = reranked + candidates[rerank_n:]

        return candidates[:top_k]

    def build_context_block(self, chunks: List[RetrievedChunk]) -> str:
        """Format retrieved chunks into a numbered context block for the system prompt.

        Produces the ``[N] (source: X)\\ntext`` format that the system-prompt
        template in ``chat.py`` references with "Cite sources by their [N]
        number."  The numbers here must stay consistent with the indices in
        ``format_citations`` — both iterate in the same order.
        """
        if not chunks:
            return ""
        parts = []
        for i, c in enumerate(chunks, 1):
            parts.append(f"[{i}] (source: {c.source})\n{c.text}")
        return "\n\n---\n\n".join(parts)

    def format_citations(self, chunks: List[RetrievedChunk]) -> list[dict]:
        return [
            {"index": i + 1, "source": c.source, "score": round(c.score, 4)}
            for i, c in enumerate(chunks)
        ]


_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Return the process-level RAGService singleton.

    Initialization is not protected by a lock.  In asyncio this is safe
    because coroutines yield at ``await`` points — the first call sets
    ``_rag_service`` before any other coroutine reaches this function.
    """
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
