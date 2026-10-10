"""
RAG service: per-project ChromaDB collections + hybrid cited retrieval.

Retrieval pipeline (D5):
  1. Dense leg — top top_k × multiplier candidates from Chroma.
  2. Sparse leg — Postgres full-text search over ``chunks.tsv`` (whole corpus, E3.2).
  3. Reciprocal Rank Fusion of the two independent ranked lists.
  4. Optional cross-encoder rerank over the top candidates.
  5. Return top_k chunks, best-first (§A4.3 pop() invariant preserved).
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Literal, Optional

from adapta.config import settings
from adapta.db.models import ProjectChunk
from adapta.domain.errors import EmbeddingModelMismatch, VectorStoreFailed
from adapta.services.embeddings import get_embedding_service, get_reranker_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float
    chunk_index: int
    # (E1.7) `score` means two different things depending on the retrieval path —
    # a cross-encoder sigmoid or 1 − cosine distance. Callers (citations) need to
    # know which, so both construction sites below fill this explicitly.
    score_kind: Literal["reranker", "vector"]
    chunk_id: str = ""  # "{file_id}_{index}" — for the retrieval log line


def content_hash(text: str) -> str:
    """sha256 hex digest of a chunk's text — the dedup key (64 chars)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_chunk_rows(project_id: str, file_id: str, chunks: list) -> List[ProjectChunk]:
    """ORM rows for a file's chunks; ids match the Chroma ids (``{file_id}_{index}``)."""
    return [
        ProjectChunk(
            id=f"{file_id}_{c.index}",
            file_id=file_id,
            project_id=project_id,
            chunk_index=c.index,
            text=c.text,
            content_hash=content_hash(c.text),
        )
        for c in chunks
    ]


async def persist_chunks(
    db: "AsyncSession", project_id: str, file_id: str, chunks: list
) -> int:
    """Insert a file's chunk rows in ``db`` (flushed, not committed); returns the count.

    Call this *before* the Chroma upsert: if the upsert fails the caller's rollback
    discards the rows, so Postgres never records chunks that have no vectors.
    """
    rows = build_chunk_rows(project_id, file_id, chunks)
    db.add_all(rows)
    await db.flush()
    return len(rows)


async def all_chunks_known(db: "AsyncSession", project_id: str, chunks: list) -> bool:
    """True when every chunk's hash already exists in the project (duplicate document)."""
    from sqlalchemy import func, select

    hashes = {content_hash(c.text) for c in chunks}
    if not hashes:
        return False
    found = await db.scalar(
        select(func.count(func.distinct(ProjectChunk.content_hash))).where(
            ProjectChunk.project_id == project_id, ProjectChunk.content_hash.in_(hashes)
        )
    )
    return (found or 0) == len(hashes)


async def count_project_chunks(db: "AsyncSession", project_id: str) -> int:
    """Chunk count for a project, read from Postgres (the source of truth)."""
    from sqlalchemy import func, select

    return (
        await db.scalar(select(func.count()).select_from(ProjectChunk).where(
            ProjectChunk.project_id == project_id
        ))
    ) or 0


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


@dataclass
class _FtsHit:
    id: str
    text: str
    source: str
    chunk_index: int


_FTS_SQL = """
SELECT c.id, c.text, c.chunk_index, f.filename
FROM chunks c JOIN project_files f ON f.id = c.file_id
WHERE c.project_id = :p AND c.tsv @@ websearch_to_tsquery(CAST(:cfg AS regconfig), :q)
ORDER BY ts_rank_cd(c.tsv, websearch_to_tsquery(CAST(:cfg AS regconfig), :q)) DESC, c.id
LIMIT :n
"""

_fts_engine = None


def _get_fts_engine():
    """Lazy NullPool engine for the sparse leg.

    ``retrieve()`` is synchronous and runs in worker threads (``chat._retrieve``) or
    plain scripts, so it cannot borrow the app's loop-bound async engine. NullPool opens
    each connection inside the loop ``asyncio.run`` creates for the call, so the engine
    is safe to share across threads and loops.
    """
    global _fts_engine
    if _fts_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        _fts_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return _fts_engine


def _fts_search(project_id: str, query: str, limit: int) -> List[_FtsHit]:
    """Sparse leg: ranked Postgres full-text hits over the project's whole corpus."""
    import asyncio

    from sqlalchemy import text as sql_text

    async def _run() -> List[_FtsHit]:
        async with _get_fts_engine().connect() as conn:
            rows = await conn.execute(
                sql_text(_FTS_SQL),
                {"p": project_id, "cfg": settings.rag_fts_config, "q": query, "n": limit},
            )
            return [_FtsHit(r.id, r.text, r.filename, r.chunk_index) for r in rows]

    return asyncio.run(_run())


def _rrf_fuse(*rank_lists: list, k: int = 60) -> list:
    """Reciprocal Rank Fusion over multiple ranked id lists.

    Each list contains chunk ids ordered best-first.  Returns the union ordered by
    descending RRF score (ties keep first-seen order).
    """
    rrf: dict = {}
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

        Sets ``hnsw:space: cosine`` so the index uses cosine distance, and
        records the embedding model active right now as ``embedding_model``.
        This metadata is applied only at creation — Chroma ignores it on
        ``get_or_create_collection`` calls for an existing collection, so both
        the distance metric and the embedding-model record are locked in
        after the first call. ``retrieve()`` reads the latter back to detect
        ``ADAPTA_EMBEDDING_MODEL`` drift.
        """
        name = collection_name_for(project_id)
        client = self._client()
        client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "embedding_model": settings.embedding_model},
        )
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

        Vectors only — the Postgres rows are written by ``persist_chunks`` before this.

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
        collection = client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "embedding_model": settings.embedding_model},
        )

        ids = [f"{file_id}_{c.index}" for c in chunks]
        metadatas = [
            {"source": c.source, "chunk_index": c.index, "file_id": file_id} for c in chunks
        ]

        collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        return len(chunks)

    def delete_file_chunks(self, project_id: str, file_id: str) -> None:
        """Remove all vectors for a file from the Chroma collection.

        Raises ``VectorStoreFailed`` on any Chroma error (the Postgres rows go by CASCADE).

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
            raise VectorStoreFailed(
                message="Could not remove the file's vectors from the index; nothing was deleted.",
                internal_detail=f"chroma delete failed for file {file_id}: {exc!r}",
            ) from exc

    def retrieve(
        self,
        project_id: str,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Hybrid retrieval: Chroma vector leg + Postgres FTS leg fused via RRF, then rerank.

        Pipeline:
          1. Dense: fetch top_k × rag_hybrid_fetch_multiplier candidates from Chroma.
          2. Sparse: Postgres FTS over chunks.tsv, top_k × rag_sparse_fetch_multiplier.
          3. RRF over the two independent ranked lists (union by chunk id).
          4. Optional cross-encoder reranker over the top rerank_n candidates.
          5. Return top_k, best-first (§A4.3 pop() invariant preserved); log one line.

        Citations reflect the final reranked scores (§A4.3 ordering).
        """
        t0 = time.perf_counter()
        top_k = top_k or settings.rag_top_k
        fetch_k = max(top_k * settings.rag_hybrid_fetch_multiplier, top_k + 1)

        name = collection_name_for(project_id)
        client = self._client()
        try:
            collection = client.get_collection(name)
        except Exception:
            return []

        # Config-drift guard: the collection's Chroma metadata records the
        # embedding model it was actually built with (set once, at creation —
        # see ensure_collection). If ADAPTA_EMBEDDING_MODEL changed since, a
        # query embedded with the new model would search the wrong vector
        # space — or blow up Chroma on a dimension mismatch — either way not
        # a signal a caller should have to decode from a Chroma error. `None`
        # (a collection indexed before this guard existed) is unknown
        # provenance, not treated as a mismatch.
        stored_model = (getattr(collection, "metadata", None) or {}).get("embedding_model")
        if stored_model and stored_model != settings.embedding_model:
            raise EmbeddingModelMismatch(
                message=(
                    f"This project's documents were indexed with '{stored_model}' "
                    f"but the server is now configured for '{settings.embedding_model}'. "
                    f"Re-index the project's files, or restore ADAPTA_EMBEDDING_MODEL={stored_model}."
                )
            )

        emb_service = get_embedding_service()
        query_embedding = emb_service.embed_one(query)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=fetch_k,
            include=["documents", "metadatas", "distances"],
        )

        ids: list[str] = results["ids"][0]
        docs: list[str] = results["documents"][0]
        metas: list[dict] = results["metadatas"][0]
        dists: list[float] = results["distances"][0]

        # Sparse leg over the whole corpus. A Postgres failure degrades to vector-only
        # rather than failing the request (the dense leg is still a valid answer).
        try:
            fts_hits = _fts_search(project_id, query, top_k * settings.rag_sparse_fetch_multiplier)
        except Exception as exc:
            logger.warning("rag fts leg failed, vector-only: %r", exc)
            fts_hits = []

        if not docs and not fts_hits:
            return []

        by_id: dict[str, RetrievedChunk] = {
            cid: RetrievedChunk(
                text=docs[i],
                source=metas[i].get("source", "unknown"),
                score=1.0 - dists[i],  # cosine distance → similarity
                chunk_index=metas[i].get("chunk_index", 0),
                score_kind="vector",
                chunk_id=cid,
            )
            for i, cid in enumerate(ids)
        }
        for h in fts_hits:
            # Keyword-only hit the embedder missed: no cosine score exists for it.
            by_id.setdefault(
                h.id,
                RetrievedChunk(
                    text=h.text, source=h.source, score=0.0,
                    chunk_index=h.chunk_index, score_kind="vector", chunk_id=h.id,
                ),
            )
        fused_ids = _rrf_fuse(ids, [h.id for h in fts_hits])
        candidates: List[RetrievedChunk] = [by_id[cid] for cid in fused_ids]

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
                    score_kind="reranker",
                    chunk_id=c.chunk_id,
                )
                for s, c in ranked
            ]
            candidates = reranked + candidates[rerank_n:]

        final = candidates[:top_k]
        fused_rank = {cid: r for r, cid in enumerate(fused_ids)}
        logger.info(
            "rag.retrieve q=%s project=%s vec=%d fts=%d fused=%d ids=%s scores=%s ms=%d",
            hashlib.sha256(query.encode("utf-8")).hexdigest()[:12],
            project_id,
            len(ids),
            len(fts_hits),
            len(fused_ids),
            [f"{c.chunk_id}@{fused_rank[c.chunk_id]}" for c in final],
            [round(c.score, 4) for c in final],
            int((time.perf_counter() - t0) * 1000),
        )
        return final

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
            {
                "index": i + 1,
                "source": c.source,
                "score": round(c.score, 4),
                "score_kind": c.score_kind,
            }
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
