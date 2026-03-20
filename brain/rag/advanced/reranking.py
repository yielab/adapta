"""
Cross-encoder re-ranking for improved search relevance.

Uses cross-encoder models to re-rank search results for better relevance.
Cross-encoders jointly encode query and document for superior accuracy.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

from brain.rag.advanced.hybrid_search import SearchResult

logger = logging.getLogger(__name__)


@dataclass
class RerankingConfig:
    """Configuration for re-ranking."""
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    batch_size: int = 32
    max_length: int = 512
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    score_threshold: Optional[float] = None
    top_k_ratio: float = 0.5  # Keep top 50% after re-ranking


class CrossEncoderReranker:
    """
    Cross-encoder based re-ranker for search results.

    Features:
    - Uses pre-trained cross-encoder models
    - Batch processing for efficiency
    - Score normalization
    - Configurable filtering
    """

    def __init__(self, config: Optional[RerankingConfig] = None):
        """
        Initialize the re-ranker.

        Args:
            config: Re-ranking configuration
        """
        self.config = config or RerankingConfig()
        self.model = None
        self.tokenizer = None
        self._load_model()

    def _load_model(self):
        """Load the cross-encoder model and tokenizer."""
        try:
            logger.info(f"Loading cross-encoder model: {self.config.model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.config.model_name
            )
            self.model.to(self.config.device)
            self.model.eval()
            logger.info("Cross-encoder model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load cross-encoder model: {e}")
            logger.info("Re-ranking will be skipped")

    def rerank(
        self,
        query: str,
        results: List[SearchResult],
        top_k: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Re-rank search results using cross-encoder.

        Args:
            query: Search query
            results: Initial search results
            top_k: Number of results to return

        Returns:
            Re-ranked search results
        """
        if not self.model or not results:
            return results

        # Determine how many results to keep
        if top_k is None:
            top_k = max(1, int(len(results) * self.config.top_k_ratio))
        else:
            top_k = min(top_k, len(results))

        # Score all query-document pairs
        scores = self._score_pairs(query, results)

        # Sort by score and update results
        scored_results = list(zip(scores, results))
        scored_results.sort(key=lambda x: x[0], reverse=True)

        # Update scores and filter
        reranked = []
        for score, result in scored_results[:top_k]:
            # Apply threshold if configured
            if self.config.score_threshold and score < self.config.score_threshold:
                continue

            # Update result with re-ranking score
            result.score = float(score)
            if not hasattr(result, 'metadata'):
                result.metadata = {}
            result.metadata['rerank_score'] = float(score)
            result.metadata['original_score'] = result.score

            reranked.append(result)

        logger.info(f"Re-ranked {len(results)} results to {len(reranked)}")
        return reranked

    def _score_pairs(
        self,
        query: str,
        results: List[SearchResult]
    ) -> np.ndarray:
        """
        Score query-document pairs using cross-encoder.

        Args:
            query: Search query
            results: Search results

        Returns:
            Array of scores
        """
        all_scores = []

        # Process in batches
        for i in range(0, len(results), self.config.batch_size):
            batch_results = results[i:i + self.config.batch_size]
            batch_texts = [r.content for r in batch_results]

            # Create query-document pairs
            pairs = [[query, text] for text in batch_texts]

            # Tokenize
            with torch.no_grad():
                inputs = self.tokenizer(
                    pairs,
                    padding=True,
                    truncation=True,
                    max_length=self.config.max_length,
                    return_tensors="pt"
                )

                # Move to device
                inputs = {k: v.to(self.config.device) for k, v in inputs.items()}

                # Get scores
                outputs = self.model(**inputs)
                scores = outputs.logits.squeeze(-1)

                # Apply sigmoid for probability scores
                scores = torch.sigmoid(scores)

                # Convert to numpy
                batch_scores = scores.cpu().numpy()
                all_scores.extend(batch_scores)

        return np.array(all_scores)

    def rerank_multiple_queries(
        self,
        queries_results: List[Tuple[str, List[SearchResult]]],
        top_k: Optional[int] = None
    ) -> List[List[SearchResult]]:
        """
        Re-rank results for multiple queries.

        Args:
            queries_results: List of (query, results) tuples
            top_k: Number of results per query

        Returns:
            List of re-ranked results for each query
        """
        reranked_all = []

        for query, results in queries_results:
            reranked = self.rerank(query, results, top_k)
            reranked_all.append(reranked)

        return reranked_all


class LightweightReranker:
    """
    Lightweight re-ranker using simpler scoring methods.

    Fallback when cross-encoder models are not available.
    """

    def __init__(self):
        """Initialize lightweight re-ranker."""
        self.keyword_boost = 1.5
        self.exact_match_boost = 2.0
        self.position_decay = 0.95

    def rerank(
        self,
        query: str,
        results: List[SearchResult],
        top_k: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Re-rank using lightweight scoring.

        Args:
            query: Search query
            results: Search results
            top_k: Number of results to return

        Returns:
            Re-ranked results
        """
        if not results:
            return results

        query_lower = query.lower()
        query_words = set(query_lower.split())

        # Score each result
        scored = []
        for i, result in enumerate(results):
            content_lower = result.content.lower()

            # Base score from original ranking
            score = result.score * (self.position_decay ** i)

            # Boost for exact query match
            if query_lower in content_lower:
                score *= self.exact_match_boost

            # Boost for keyword matches
            content_words = set(content_lower.split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                score *= (1 + (overlap / len(query_words)) * self.keyword_boost)

            # Update result
            result.score = score
            scored.append((score, result))

        # Sort and return top k
        scored.sort(key=lambda x: x[0], reverse=True)

        if top_k:
            scored = scored[:top_k]

        return [result for _, result in scored]


class HybridReranker:
    """
    Combines multiple re-ranking strategies.

    Uses cross-encoder when available, falls back to lightweight.
    """

    def __init__(self, config: Optional[RerankingConfig] = None):
        """
        Initialize hybrid re-ranker.

        Args:
            config: Re-ranking configuration
        """
        self.cross_encoder = CrossEncoderReranker(config)
        self.lightweight = LightweightReranker()
        self.use_cross_encoder = self.cross_encoder.model is not None

    def rerank(
        self,
        query: str,
        results: List[SearchResult],
        top_k: Optional[int] = None,
        strategy: str = "auto"
    ) -> List[SearchResult]:
        """
        Re-rank search results.

        Args:
            query: Search query
            results: Search results
            top_k: Number of results
            strategy: "cross_encoder", "lightweight", or "auto"

        Returns:
            Re-ranked results
        """
        if strategy == "auto":
            if self.use_cross_encoder:
                strategy = "cross_encoder"
            else:
                strategy = "lightweight"

        if strategy == "cross_encoder" and self.use_cross_encoder:
            return self.cross_encoder.rerank(query, results, top_k)
        else:
            return self.lightweight.rerank(query, results, top_k)