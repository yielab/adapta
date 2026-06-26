"""sentence-transformers embedding and cross-encoder reranking services.

Both services are lazily loaded on first use so the model weights are not
downloaded at import time — only when an actual embed/rerank call is made.
Both are cached as process-level singletons via ``lru_cache``; the first
call's model name is locked in for the lifetime of the process, so a config
change requires a restart.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional

from adapta.config import settings
from adapta.domain.errors import EmbeddingFailed

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Bi-encoder sentence-transformers model, lazily loaded on first use.

    Not thread-safe at load time: if two coroutines race the first call
    before the model is loaded, both see ``_model is None`` and both load.
    In practice the asyncio event loop serializes the first call, but the
    double-load is harmless (the second assignment overwrites with an
    identical model object).
    """

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            logger.info("Embedding model loaded")
        except Exception as exc:
            raise EmbeddingFailed(
                message="Failed to load embedding model",
                internal_detail=str(exc),
            ) from exc

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of strings.  Returns one float vector per input."""
        if not texts:
            return []
        self._load()
        assert self._model is not None
        try:
            vectors = self._model.encode(texts, show_progress_bar=False)
            return [v.tolist() for v in vectors]
        except Exception as exc:
            raise EmbeddingFailed(
                message="Embedding generation failed",
                internal_detail=str(exc),
            ) from exc

    def embed_one(self, text: str) -> List[float]:
        """Embed a single string.  Equivalent to ``embed([text])[0]``.

        Not a separate model call — just a convenience wrapper around ``embed``.
        Use ``embed`` directly for batches to avoid per-call overhead.
        """
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        """Embedding vector dimension.  Triggers model load on first access."""
        self._load()
        assert self._model is not None
        return self._model.get_sentence_embedding_dimension()  # type: ignore[return-value]


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """Return the process-level EmbeddingService singleton.

    ``lru_cache(maxsize=1)`` means the first call determines the model name
    for the process lifetime; subsequent calls return the cached instance
    regardless of any config change.  Restart the process to pick up a new
    ``ADAPTA_EMBEDDING_MODEL``.
    """
    return EmbeddingService(settings.embedding_model)


class RerankerService:
    """Cross-encoder reranker, lazily loaded on first use (D5).

    A cross-encoder takes ``(query, passage)`` pairs and scores them jointly —
    unlike bi-encoders (EmbeddingService) which encode query and passage
    independently.  Scores are raw logits (unbounded, may be negative) and are
    not comparable to cosine-similarity scores; callers that expose them should
    normalize first (e.g. via sigmoid — see ``rag.py``).
    """

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading reranker model: %s", self._model_name)
            self._model = CrossEncoder(self._model_name)
            logger.info("Reranker model loaded")
        except Exception as exc:
            raise EmbeddingFailed(
                message="Failed to load reranker model",
                internal_detail=str(exc),
            ) from exc

    def rerank(self, query: str, passages: List[str]) -> List[float]:
        """Score each passage against the query.  Returns raw logits (higher = more relevant).

        Scores are unbounded floats from the cross-encoder — NOT cosine
        similarities.  Apply ``sigmoid`` to normalize to (0, 1) before
        exposing them in API responses.
        """
        if not passages:
            return []
        self._load()
        assert self._model is not None
        try:
            pairs = [(query, p) for p in passages]
            scores = self._model.predict(pairs, show_progress_bar=False)
            return [float(s) for s in scores]
        except Exception as exc:
            raise EmbeddingFailed(
                message="Reranking failed",
                internal_detail=str(exc),
            ) from exc


@lru_cache(maxsize=1)
def get_reranker_service() -> Optional[RerankerService]:
    """Return the process-level RerankerService singleton, or None if disabled.

    Returns None when ``ADAPTA_RAG_RERANKER_MODEL`` is empty — this disables
    reranking in ``rag.py`` and falls back to RRF-fused vector+BM25 order.
    Same ``lru_cache`` process-lifetime lock-in as ``get_embedding_service``.
    """
    model = settings.rag_reranker_model
    if not model:
        return None
    return RerankerService(model)
