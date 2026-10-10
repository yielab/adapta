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

import asyncio
import hashlib
import json
import logging
import math
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Literal, Mapping, Optional, Sequence

from sqlalchemy.exc import SQLAlchemyError

from adapta.config import settings
from adapta.core.metrics import get_metrics_collector
from adapta.db.models import ProjectChunk
from adapta.domain.errors import DomainError, EmbeddingModelMismatch, VectorStoreFailed
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
    # (E3.4) Provenance, hydrated from Postgres `chunks` by chunk_id after the final cut.
    file_id: Optional[str] = None
    page: Optional[int] = None
    ocr: bool = False
    ocr_confidence: Optional[float] = None
    # (E3.5) Keyword-only hit: the vector leg never returned it, so `score` is a 0.0
    # placeholder, not a cosine, and must not be compared to a relevance threshold.
    lexical_only: bool = False
    # (E5.4) One-line header from the chunk's extracted fields ("Invoice · Acme · 2026-03-01 · 1,250").
    fields_header: str = ""


@dataclass(frozen=True)
class RetrievalFilters:
    """(E3.5) Request-level restriction of retrieval. All fields optional (AND-ed)."""

    file_ids: Optional[List[str]] = None
    page_min: Optional[int] = None
    page_max: Optional[int] = None
    needs_review: Optional[bool] = None
    # (E5.4) Exact match on extracted fields (``chunks.fields ->> key``), AND-ed.
    fields: Optional[dict] = None

    @property
    def sql_only(self) -> bool:
        """Filters Chroma metadata cannot express (it carries no page / review flag / fields)."""
        return (
            self.page_min is not None
            or self.page_max is not None
            or self.needs_review is not None
            or bool(self.fields)
        )

    def sql_clauses(self) -> tuple[str, dict]:
        """``AND ...`` fragment over alias ``c`` (chunks) plus its bind params."""
        parts: list[str] = []
        params: dict = {}
        if self.file_ids:
            parts.append("c.file_id = ANY(:f_file_ids)")
            params["f_file_ids"] = list(self.file_ids)
        if self.page_min is not None:
            parts.append("c.page >= :f_page_min")
            params["f_page_min"] = self.page_min
        if self.page_max is not None:
            parts.append("c.page <= :f_page_max")
            params["f_page_max"] = self.page_max
        if self.needs_review is not None:
            parts.append("c.needs_review = :f_needs_review")
            params["f_needs_review"] = self.needs_review
        for i, (key, value) in enumerate((self.fields or {}).items()):
            parts.append(f"c.fields ->> :f_fk{i} = :f_fv{i}")
            params[f"f_fk{i}"] = str(key)
            params[f"f_fv{i}"] = str(value)
        return "".join(f" AND {p}" for p in parts), params


def apply_min_score(chunks: List["RetrievedChunk"], min_score: float) -> List["RetrievedChunk"]:
    """Drop chunks whose relevance score is under ``min_score`` (0 disables).

    ``score`` is the reranker sigmoid or the vector cosine, depending on ``score_kind`` —
    both in [0, 1] and both thresholded as-is. Keyword-only hits are kept: FTS already
    discards statistical stopwords, so a hit is exact-term evidence the cosine cannot judge.
    """
    if min_score <= 0:
        return chunks
    return [c for c in chunks if c.lexical_only or c.score >= min_score]


def content_hash(text: str) -> str:
    """sha256 hex digest of a chunk's text — the dedup key (64 chars)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _needs_review(c: object) -> bool:
    """OCR text whose mean line confidence is under ``ocr_review_threshold`` (E3.3b)."""
    conf = getattr(c, "ocr_confidence", None)
    ocr = bool(getattr(c, "ocr", False))
    return ocr and conf is not None and conf < settings.ocr_review_threshold


def indexed_text(chunk: object) -> str:
    """What gets embedded for a chunk: ``context + text`` when it has a situating sentence."""
    ctx = getattr(chunk, "context", None)
    text = chunk.text  # type: ignore[attr-defined]
    return f"{ctx}\n\n{text}" if ctx else text


def build_chunk_rows(project_id: str, file_id: str, chunks: list) -> List[ProjectChunk]:
    """ORM rows for a file's chunks; ids match the Chroma ids (``{file_id}_{index}``)."""
    return [
        ProjectChunk(
            id=f"{file_id}_{c.index}",
            file_id=file_id,
            project_id=project_id,
            chunk_index=c.index,
            text=c.text,
            context=getattr(c, "context", None),
            content_hash=content_hash(c.text),
            page=getattr(c, "page", None),
            section=getattr(c, "section", None),
            ocr=bool(getattr(c, "ocr", False)),
            ocr_confidence=getattr(c, "ocr_confidence", None),
            needs_review=_needs_review(c),
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


async def count_project_chunks(db: "AsyncSession", project_id: str) -> int:
    """Chunk count for a project, read from Postgres (the source of truth)."""
    from sqlalchemy import func, select

    return (
        await db.scalar(select(func.count()).select_from(ProjectChunk).where(
            ProjectChunk.project_id == project_id
        ))
    ) or 0


_chroma_client = None
_chroma_lock = threading.Lock()


def _get_chroma_client():
    """The process-wide Chroma HTTP client, built once and shared by every thread (E1.15).

    ``chromadb.HttpClient()`` opens sockets (and makes a tenant/database validation request)
    on construction and has no close; building one per call leaked ~3 file descriptors per
    index job until the worker hit ``[Errno 24] Too many open files``. The underlying
    ``httpx.Client`` is thread-safe and reconnects after a Chroma restart. chromadb 1.5.9
    exposes no timeout setting (its session is built with ``timeout=None``), so the
    ``chroma_timeout_seconds`` bound is applied to that session here; a hung Chroma then
    raises ``httpx.TimeoutException`` instead of blocking the caller forever.
    """
    global _chroma_client
    client = _chroma_client
    if client is not None:
        return client
    with _chroma_lock:
        if _chroma_client is None:
            import chromadb
            import httpx

            built = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
            session = getattr(getattr(built, "_server", None), "_session", None)
            if isinstance(session, httpx.Client):
                session.timeout = httpx.Timeout(settings.chroma_timeout_seconds)
            else:  # chromadb internals moved: do not run unbounded without saying so
                logger.error("Chroma client has no httpx session; request timeout NOT applied")
            _chroma_client = built
        return _chroma_client


def _reset_chroma_client() -> None:
    """Drop the cached client (tests; a changed ``chroma_host``)."""
    global _chroma_client
    with _chroma_lock:
        _chroma_client = None


@contextmanager
def _vector_store(action: str):
    """Map any Chroma failure inside the block to a typed ``VectorStoreFailed``.

    A timeout says so in the client-safe message (it ends up in ``ProjectFile.error_message``);
    ``VectorStoreFailed`` is in the indexer's transient set, so the first attempt retries.
    """
    import httpx

    try:
        yield
    except DomainError:
        raise
    except httpx.TimeoutException as exc:
        raise VectorStoreFailed(
            message=(
                f"The vector index (Chroma) did not answer within "
                f"{settings.chroma_timeout_seconds} s while trying to {action}."
            ),
            internal_detail=f"chroma timeout during {action}: {exc!r}",
        ) from exc
    except Exception as exc:
        raise VectorStoreFailed(
            message=f"The vector index (Chroma) failed while trying to {action}.",
            internal_detail=f"chroma error during {action}: {exc!r}",
        ) from exc


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


# Sparse leg SQL. websearch_to_tsquery ANDs every term, so a natural-language question
# would match no chunk; instead each query lexeme is its own quoted tsquery (quoting keeps
# urls/paths/emails from breaking the parser). ts_rank_cd has no IDF, so with OR semantics
# stopwords drown the content words. Language-agnostic fix, no stopword lists:
#   * df = how many of the project's chunks contain the lexeme (GIN-backed count);
#   * lexemes present in more than :max_df of the chunks are dropped (statistical
#     stopwords), but never when df <= 3, so tiny corpora keep their terms;
#   * chunks are ranked by the summed BM25-style idf of the lexemes they contain (rounded
#     so float summation order cannot split a tie), ties broken by (filename, chunk_index,
#     content_hash) -- never by chunks.id, which embeds a per-upload random file uuid (F1.4).
# No surviving lexeme -> no rows (not an error).
_FTS_SQL = """
WITH lex AS (
  SELECT l, CAST(quote_literal(l) AS tsquery) AS tq
  FROM unnest(tsvector_to_array(to_tsvector(CAST(:cfg AS regconfig), :q))) AS l
),
n AS (SELECT count(*) AS n FROM chunks WHERE project_id = :p),
df AS (
  SELECT lex.tq,
         (SELECT count(*) FROM chunks c WHERE c.project_id = :p AND c.tsv @@ lex.tq) AS df
  FROM lex
),
w AS (
  SELECT df.tq, ln((n.n - df.df + 0.5) / (df.df + 0.5) + 1) AS idf
  FROM df, n
  WHERE df.df > 0 AND df.df <= GREATEST(:max_df * n.n, 3)
)
SELECT c.id, c.text, c.chunk_index, f.filename
FROM w
JOIN chunks c ON c.project_id = :p AND c.tsv @@ w.tq{filters}
JOIN project_files f ON f.id = c.file_id
GROUP BY c.id, c.text, c.chunk_index, f.filename
ORDER BY round(CAST(sum(w.idf) AS numeric), 9) DESC, f.filename, c.chunk_index, c.content_hash, c.id
LIMIT :n
"""

_fts_loop: Optional[asyncio.AbstractEventLoop] = None
_fts_engine = None
_fts_lock = threading.Lock()


def _fts_runtime() -> asyncio.AbstractEventLoop:
    """A long-lived daemon thread owning one event loop and one pooled async engine.

    ``retrieve()`` is synchronous and called from worker threads and scripts, which cannot
    share the app's loop-bound engine. Keeping a single private loop lets the sparse leg
    reuse pooled Postgres connections instead of paying a connect + auth handshake per
    query; callers submit coroutines with ``run_coroutine_threadsafe``.
    """
    global _fts_loop, _fts_engine
    with _fts_lock:
        if _fts_loop is None:
            from sqlalchemy.ext.asyncio import create_async_engine

            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, name="rag-fts-loop", daemon=True).start()
            # Connections are opened lazily, inside the loop thread, on first use.
            _fts_engine = create_async_engine(
                settings.database_url, pool_size=4, max_overflow=4, pool_pre_ping=True
            )
            _fts_loop = loop
        return _fts_loop


def _fts_search(
    project_id: str, query: str, limit: int, filters: Optional["RetrievalFilters"] = None
) -> List[_FtsHit]:
    """Sparse leg: ranked Postgres full-text hits over the project's whole corpus."""
    from sqlalchemy import text as sql_text

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "RAGService.retrieve() is blocking; inside an event loop call it via asyncio.to_thread"
        )

    loop = _fts_runtime()
    # Filters go on the final join only: idf statistics stay project-wide so a filtered
    # query ranks exactly as it would unfiltered, restricted to the allowed chunks.
    filter_sql, filter_params = filters.sql_clauses() if filters else ("", {})
    statement = _FTS_SQL.replace("{filters}", filter_sql)

    async def _run() -> List[_FtsHit]:
        assert _fts_engine is not None
        async with _fts_engine.connect() as conn:
            rows = await conn.execute(
                sql_text(statement),
                {
                    **filter_params,
                    "p": project_id,
                    "cfg": settings.rag_fts_config,
                    "q": query,
                    "n": limit,
                    "max_df": settings.rag_sparse_max_df,
                },
            )
            return [_FtsHit(r.id, r.text, r.filename, r.chunk_index) for r in rows]

    fut = asyncio.run_coroutine_threadsafe(_run(), loop)
    try:
        return fut.result(timeout=settings.rag_timeout_seconds)
    except BaseException:
        fut.cancel()
        raise


def _filter_vector_ids(ids: List[str], filters: "RetrievalFilters") -> set:
    """Subset of the vector candidates passing the page / review filters (one query).

    Chroma metadata has no page or review flag, so those filters run in Postgres over the
    candidate ids. A Postgres failure here must not silently drop the filter: it raises.
    """
    from sqlalchemy import text as sql_text

    if not ids:
        return set()
    clause, params = filters.sql_clauses()
    statement = sql_text(f"SELECT c.id FROM chunks c WHERE c.id = ANY(:ids){clause}")
    loop = _fts_runtime()

    async def _run() -> set:
        assert _fts_engine is not None
        async with _fts_engine.connect() as conn:
            rows = await conn.execute(statement, {"ids": ids, **params})
            return {r.id for r in rows}

    fut = asyncio.run_coroutine_threadsafe(_run(), loop)
    try:
        return fut.result(timeout=settings.rag_timeout_seconds)
    except BaseException:
        fut.cancel()
        raise


_PROVENANCE_SQL = """
SELECT c.id, c.file_id, c.page, c.ocr, c.ocr_confidence, c.fields, p.extraction_schema
FROM chunks c JOIN projects p ON p.id = c.project_id WHERE c.id = ANY(:ids)
"""


def _header_of(row: object) -> str:
    """(E5.4) Chunk header from a provenance row's ``fields`` + its project's schema."""
    from adapta.services.extraction import fields_header

    fields = getattr(row, "fields", None)
    schema = getattr(row, "extraction_schema", None)
    if isinstance(fields, str):  # raw SQL may hand JSON back undecoded
        fields = json.loads(fields)
    if isinstance(schema, str):
        schema = json.loads(schema)
    return fields_header(fields, schema)


def _hydrate_provenance(chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
    """Fill file_id / page / OCR fields from Postgres for the final top_k (one query).

    Best-effort like the sparse leg: a Postgres failure leaves the defaults (a citation
    without provenance is still a valid citation).
    """
    from dataclasses import replace

    from sqlalchemy import text as sql_text

    ids = [c.chunk_id for c in chunks if c.chunk_id]
    if not ids:
        return chunks
    loop = _fts_runtime()

    async def _run() -> dict:
        assert _fts_engine is not None
        async with _fts_engine.connect() as conn:
            rows = await conn.execute(sql_text(_PROVENANCE_SQL), {"ids": ids})
            return {r.id: r for r in rows}

    fut = asyncio.run_coroutine_threadsafe(_run(), loop)
    try:
        rows = fut.result(timeout=settings.rag_timeout_seconds)
    except (SQLAlchemyError, OSError, asyncio.TimeoutError, TimeoutError) as exc:
        fut.cancel()
        logger.warning("rag provenance lookup failed, citations without page/OCR: %r", exc)
        return chunks
    return [
        replace(
            c,
            file_id=r.file_id,
            page=r.page,
            ocr=bool(r.ocr),
            ocr_confidence=r.ocr_confidence,
            fields_header=_header_of(r),
        )
        if (r := rows.get(c.chunk_id)) is not None
        else c
        for c in chunks
    ]


def _chunk_tie_key(meta: dict, chunk_id: str) -> tuple:
    """Content-derived tie-break: (filename, chunk_index). Chunk ids embed a random per-upload
    file uuid, so they differ between identically built projects and must not decide ties."""
    return (str(meta.get("source", "")), int(meta.get("chunk_index", 0) or 0))


def _rrf_fuse(*rank_lists: list, k: int = 60, tie_key: Optional[Mapping] = None) -> list:
    """Reciprocal Rank Fusion over multiple ranked id lists.

    Each list contains chunk ids ordered best-first.  Returns the union ordered by
    descending RRF score.  Ties (scores rounded to 12 places, so float summation order
    cannot split them) are broken by ``tie_key[id]`` when given -- a content-derived key
    that is identical across identically built projects (F1.4) -- then by id.  Without a
    ``tie_key`` ties fall back to the id alone, never to list/dict order.
    """
    rrf: dict = {}
    for ranks in rank_lists:
        for rank, idx in enumerate(ranks):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (k + rank + 1)
    key = tie_key or {}
    return sorted(rrf, key=lambda i: (-round(rrf[i], 12), key.get(i, ()), i))


class RAGService:
    """Per-project ChromaDB collection management and hybrid cited retrieval.

    Every call goes through the one process-wide Chroma client
    (``_client()`` → ``_get_chroma_client()``); this object holds no connection itself.
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
        with _vector_store("create the project collection"):
            self._client().get_or_create_collection(
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
        try:
            self._client().delete_collection(name)
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
        # (E5.1) The vector covers context + text; the stored document stays the raw text so
        # citations quote the source. No context -> the exact pre-E5.1 input.
        embeddings = emb_service.embed([indexed_text(c) for c in chunks])

        name = collection_name_for(project_id)
        ids = [f"{file_id}_{c.index}" for c in chunks]
        metadatas = [
            {"source": c.source, "chunk_index": c.index, "file_id": file_id} for c in chunks
        ]
        with _vector_store("store the file's vectors"):
            collection = self._client().get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine", "embedding_model": settings.embedding_model},
            )
            collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        return len(chunks)

    def delete_file_chunks(self, project_id: str, file_id: str) -> None:
        """Remove all vectors for a file from the Chroma collection.

        Raises ``VectorStoreFailed`` on any Chroma error (the Postgres rows go by CASCADE).

        Two-step (``get`` then ``delete``) because Chroma's ``delete`` requires
        explicit IDs rather than accepting a ``where`` filter directly.
        """
        name = collection_name_for(project_id)
        try:
            collection = self._client().get_collection(name)
            results = collection.get(where={"file_id": file_id})
            if results["ids"]:
                collection.delete(ids=results["ids"])
        except Exception as exc:
            raise VectorStoreFailed(
                message="Could not remove the file's vectors from the index; nothing was deleted.",
                internal_detail=f"chroma delete failed for file {file_id}: {exc!r}",
            ) from exc

    def delete_chunk_ids(self, project_id: str, ids: List[str]) -> None:
        """(E5.4) Remove specific vectors (ids are ``{file_id}_{index}``); raises ``VectorStoreFailed``."""
        if not ids:
            return
        with _vector_store("remove replaced chunk vectors"):
            self._client().get_collection(collection_name_for(project_id)).delete(ids=ids)

    def retrieve(
        self,
        project_id: str,
        query: str | Sequence[str],
        top_k: Optional[int] = None,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[RetrievedChunk]:
        """Hybrid retrieval: Chroma vector leg + Postgres FTS leg fused via RRF, then rerank.

        Pipeline:
          1. Dense: fetch top_k × rag_hybrid_fetch_multiplier candidates from Chroma.
          2. Sparse: Postgres FTS over chunks.tsv, top_k × rag_sparse_fetch_multiplier.
          3. RRF over the two independent ranked lists (union by chunk id).
          4. Optional cross-encoder reranker over the top rerank_n candidates.
          5. Return top_k, best-first (§A4.3 pop() invariant preserved); log one line.

        Citations reflect the final reranked scores (§A4.3 ordering).

        ``query`` is one string or a list of queries (E5.3: the condensed standalone question
        plus the original). Each query runs both legs; one RRF fuses all the lists. The first
        query is the primary one (the reranker scores against it). A plain string is the
        single-query case, unchanged.

        ``filters`` (E3.5) restricts both legs: ``file_ids`` as a Chroma ``where`` and SQL
        ``WHERE`` on the FTS leg; page / review filters in SQL on the FTS leg and over the
        vector candidates (over-fetched 4x to leave survivors). ``None`` changes nothing.
        """
        t0 = time.perf_counter()
        query_list = [query] if isinstance(query, str) else list(query)
        top_k = top_k or settings.rag_top_k
        fetch_k = max(top_k * settings.rag_hybrid_fetch_multiplier, top_k + 1)
        if filters is not None and filters.sql_only:
            fetch_k *= 4

        name = collection_name_for(project_id)
        client = self._client()
        try:
            collection = client.get_collection(name)
        except Exception as exc:
            logger.warning("retrieve: no usable Chroma collection %s (%r); returning no hits", name, exc)
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
        query_kwargs: dict = {}
        if filters is not None and filters.file_ids:
            query_kwargs["where"] = {"file_id": {"$in": list(filters.file_ids)}}

        # One vector list and one FTS list per query (E5.3). A chunk seen under several
        # queries keeps its best cosine score; RRF below fuses every list at once.
        by_id: dict[str, RetrievedChunk] = {}
        vec_lists: list[list[str]] = []
        fts_lists: list[list[str]] = []
        n_vec = n_fts = 0
        for q in query_list:
            q_emb = emb_service.embed_one(q)
            results = collection.query(
                query_embeddings=[q_emb],
                n_results=fetch_k,
                include=["documents", "metadatas", "distances"],
                **query_kwargs,
            )
            # Chroma leaves exact-distance ties in arbitrary order: pin them by content (F1.4).
            order = sorted(
                range(len(results["ids"][0])),
                key=lambda j: (
                    results["distances"][0][j],
                    _chunk_tie_key(results["metadatas"][0][j], results["ids"][0][j]),
                ),
            )
            ids: list[str] = [results["ids"][0][j] for j in order]
            docs: list[str] = [results["documents"][0][j] for j in order]
            metas: list[dict] = [results["metadatas"][0][j] for j in order]
            dists: list[float] = [results["distances"][0][j] for j in order]
            if filters is not None and filters.sql_only:
                keep = _filter_vector_ids(ids, filters)
                kept = [i for i, cid in enumerate(ids) if cid in keep]
                ids = [ids[i] for i in kept]
                docs = [docs[i] for i in kept]
                metas = [metas[i] for i in kept]
                dists = [dists[i] for i in kept]
            for i, cid in enumerate(ids):
                score = 1.0 - dists[i]  # cosine distance -> similarity
                prev = by_id.get(cid)
                if prev is None or score > prev.score:
                    by_id[cid] = RetrievedChunk(
                        text=docs[i],
                        source=metas[i].get("source", "unknown"),
                        score=score,
                        chunk_index=metas[i].get("chunk_index", 0),
                        score_kind="vector",
                        chunk_id=cid,
                    )
            vec_lists.append(ids)
            n_vec += len(ids)

            # Sparse leg over the whole corpus. A Postgres failure degrades to vector-only
            # rather than failing the request (the dense leg is still a valid answer).
            try:
                fts_kwargs = {"filters": filters} if filters is not None else {}
                fts_hits = _fts_search(
                    project_id, q, top_k * settings.rag_sparse_fetch_multiplier, **fts_kwargs
                )
            except (SQLAlchemyError, OSError, asyncio.TimeoutError) as exc:
                logger.warning("rag fts leg failed, vector-only: %r", exc)
                fts_hits = []
            for h in fts_hits:
                # Keyword-only hit the embedder missed: no cosine score exists for it.
                by_id.setdefault(
                    h.id,
                    RetrievedChunk(
                        text=h.text, source=h.source, score=0.0,
                        chunk_index=h.chunk_index, score_kind="vector", chunk_id=h.id,
                        lexical_only=True,
                    ),
                )
            fts_lists.append([h.id for h in fts_hits])
            n_fts += len(fts_hits)

        if not by_id:
            return []

        fused_ids = _rrf_fuse(
            *vec_lists,
            *fts_lists,
            tie_key={cid: _chunk_tie_key({"source": c.source, "chunk_index": c.chunk_index}, cid)
                     for cid, c in by_id.items()},
        )
        candidates: List[RetrievedChunk] = [by_id[cid] for cid in fused_ids]

        reranker = get_reranker_service()
        if reranker is not None and len(candidates) > 1:
            rerank_n = min(top_k * 2, len(candidates))
            to_rerank = candidates[:rerank_n]
            t_rerank = time.perf_counter()
            raw_scores = reranker.rerank(query_list[0], [c.text for c in to_rerank])
            get_metrics_collector().rag_reranker_seconds.observe(time.perf_counter() - t_rerank)
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

        final = _hydrate_provenance(candidates[:top_k])
        fused_rank = {cid: r for r, cid in enumerate(fused_ids)}
        mc = get_metrics_collector()
        mc.rag_retrieval_seconds.observe(time.perf_counter() - t0)
        mc.rag_chunks_returned.observe(len(final))
        logger.info(
            "rag.retrieve q=%s project=%s vec=%d fts=%d fused=%d ids=%s scores=%s ms=%d",
            "+".join(hashlib.sha256(q.encode("utf-8")).hexdigest()[:12] for q in query_list),
            project_id,
            n_vec,
            n_fts,
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
            head = f"{c.fields_header}\n" if c.fields_header else ""
            parts.append(f"[{i}] (source: {c.source})\n{head}{c.text}")
        return "\n\n---\n\n".join(parts)

    def format_citations(self, chunks: List[RetrievedChunk]) -> list[dict]:
        return [
            {
                "index": i + 1,
                "source": c.source,
                "score": round(c.score, 4),
                "score_kind": c.score_kind,
                "text": c.text,
                "file_id": c.file_id,
                "page": c.page,
                "ocr": c.ocr,
                "confidence": c.ocr_confidence,
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
