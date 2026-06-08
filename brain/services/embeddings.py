"""
Real sentence-transformers embeddings service.
Replaces the placeholder vectors in the old memory_manager / hybrid_search.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import List

from brain.config import settings
from brain.domain.errors import EmbeddingFailed

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Wraps sentence-transformers; lazily loaded on first use."""

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None

    def _load(self):
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
        """Embed a list of strings; returns list of float vectors."""
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
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        self._load()
        assert self._model is not None
        return self._model.get_sentence_embedding_dimension()  # type: ignore[return-value]


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(settings.embedding_model)
