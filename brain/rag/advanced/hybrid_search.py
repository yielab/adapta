"""
Hybrid search engine combining semantic and keyword search.

Provides superior retrieval by combining:
- Semantic search using embeddings
- BM25 keyword search
- Reciprocal rank fusion
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


class SearchStrategy(Enum):
    """Search strategies for hybrid search."""
    SEMANTIC_ONLY = "semantic_only"
    KEYWORD_ONLY = "keyword_only"
    HYBRID_LINEAR = "hybrid_linear"  # Linear combination
    HYBRID_RRF = "hybrid_rrf"  # Reciprocal rank fusion
    ADAPTIVE = "adaptive"  # Automatically choose based on query


@dataclass
class SearchResult:
    """A search result with metadata."""
    doc_id: str
    content: str
    score: float
    semantic_score: Optional[float] = None
    keyword_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: Optional[str] = None
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "score": self.score,
            "semantic_score": self.semantic_score,
            "keyword_score": self.keyword_score,
            "metadata": self.metadata,
            "chunk_id": self.chunk_id,
            "source": self.source
        }


class BM25:
    """
    BM25 implementation for keyword search.

    BM25 is a probabilistic ranking function used for information retrieval.
    """

    def __init__(
        self,
        k1: float = 1.2,
        b: float = 0.75,
        epsilon: float = 0.25
    ):
        """
        Initialize BM25.

        Args:
            k1: Term frequency saturation parameter
            b: Length normalization parameter
            epsilon: Floor value for IDF
        """
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon

        self.corpus_size = 0
        self.doc_lengths = []
        self.avgdl = 0
        self.doc_freqs = []  # Document frequencies
        self.idf = {}  # Inverse document frequencies
        self.documents = []
        self.tokenized_docs = []

    def fit(self, documents: List[str]):
        """
        Fit BM25 to a corpus of documents.

        Args:
            documents: List of document texts
        """
        self.documents = documents
        self.corpus_size = len(documents)

        # Tokenize documents
        self.tokenized_docs = [self._tokenize(doc) for doc in documents]

        # Calculate document lengths
        self.doc_lengths = [len(doc) for doc in self.tokenized_docs]
        self.avgdl = sum(self.doc_lengths) / self.corpus_size if self.corpus_size > 0 else 0

        # Calculate document frequencies
        doc_freqs = defaultdict(int)
        for doc in self.tokenized_docs:
            unique_tokens = set(doc)
            for token in unique_tokens:
                doc_freqs[token] += 1

        # Calculate IDF for each term
        self.idf = {}
        for token, freq in doc_freqs.items():
            self.idf[token] = self._calc_idf(freq)

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization (can be improved with proper NLP)."""
        return text.lower().split()

    def _calc_idf(self, doc_freq: int) -> float:
        """
        Calculate inverse document frequency.

        Args:
            doc_freq: Document frequency of term

        Returns:
            IDF value
        """
        return math.log(
            (self.corpus_size - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0
        )

    def score(self, query: str, doc_idx: int) -> float:
        """
        Calculate BM25 score for a query-document pair.

        Args:
            query: Query text
            doc_idx: Document index

        Returns:
            BM25 score
        """
        query_tokens = self._tokenize(query)
        doc_tokens = self.tokenized_docs[doc_idx]
        doc_len = self.doc_lengths[doc_idx]

        score = 0.0
        doc_token_counts = defaultdict(int)
        for token in doc_tokens:
            doc_token_counts[token] += 1

        for token in query_tokens:
            if token not in self.idf:
                continue

            term_freq = doc_token_counts.get(token, 0)
            idf = self.idf[token]

            # BM25 formula
            numerator = idf * term_freq * (self.k1 + 1)
            denominator = term_freq + self.k1 * (
                1 - self.b + self.b * doc_len / self.avgdl
            )

            score += numerator / denominator

        return score

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        Search for top-k documents.

        Args:
            query: Query text
            top_k: Number of results

        Returns:
            List of (doc_idx, score) tuples
        """
        scores = []
        for idx in range(self.corpus_size):
            score = self.score(query, idx)
            if score > 0:
                scores.append((idx, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores[:top_k]


class HybridSearchEngine:
    """
    Hybrid search engine combining semantic and keyword search.

    Features:
    - Semantic search with embeddings
    - BM25 keyword search
    - Multiple fusion strategies
    - Adaptive strategy selection
    """

    def __init__(
        self,
        embedding_model: Optional[Any] = None,
        strategy: SearchStrategy = SearchStrategy.HYBRID_RRF,
        semantic_weight: float = 0.5
    ):
        """
        Initialize hybrid search engine.

        Args:
            embedding_model: Model for generating embeddings
            strategy: Search strategy to use
            semantic_weight: Weight for semantic search (0-1)
        """
        self.embedding_model = embedding_model
        self.strategy = strategy
        self.semantic_weight = semantic_weight
        self.keyword_weight = 1 - semantic_weight

        # Search components
        self.bm25 = BM25()
        self.embeddings = []
        self.documents = []
        self.metadata = []

    def index_documents(
        self,
        documents: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        doc_ids: Optional[List[str]] = None
    ):
        """
        Index documents for hybrid search.

        Args:
            documents: List of document texts
            metadata: Optional metadata for each document
            doc_ids: Optional document IDs
        """
        self.documents = documents
        self.metadata = metadata or [{} for _ in documents]

        # Generate doc IDs if not provided
        if not doc_ids:
            doc_ids = [f"doc_{i}" for i in range(len(documents))]
        self.doc_ids = doc_ids

        # Index for BM25
        self.bm25.fit(documents)

        # Generate embeddings for semantic search
        if self.embedding_model:
            self.embeddings = self._generate_embeddings(documents)

        logger.info(f"Indexed {len(documents)} documents for hybrid search")

    def _generate_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for texts.

        Args:
            texts: List of texts

        Returns:
            List of embedding vectors
        """
        # Placeholder - integrate with actual embedding model
        # In production, use sentence-transformers or similar
        embeddings = []
        for text in texts:
            # Simple hash-based embedding (replace with real embeddings)
            import hashlib
            hash_obj = hashlib.md5(text.encode())
            hash_hex = hash_obj.hexdigest()
            embedding = np.array([
                float(int(hash_hex[i:i+2], 16)) / 255.0
                for i in range(0, min(32, len(hash_hex)), 2)
            ])
            # Normalize
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            embeddings.append(embedding)

        return embeddings

    def search(
        self,
        query: str,
        top_k: int = 10,
        strategy: Optional[SearchStrategy] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Perform hybrid search.

        Args:
            query: Search query
            top_k: Number of results
            strategy: Override default strategy
            filter_metadata: Metadata filters

        Returns:
            List of search results
        """
        strategy = strategy or self.strategy

        # Adaptive strategy selection
        if strategy == SearchStrategy.ADAPTIVE:
            strategy = self._select_adaptive_strategy(query)

        # Get candidate documents
        candidates = self._get_candidates(filter_metadata)

        # Perform search based on strategy
        if strategy == SearchStrategy.SEMANTIC_ONLY:
            results = self._semantic_search(query, candidates, top_k)
        elif strategy == SearchStrategy.KEYWORD_ONLY:
            results = self._keyword_search(query, candidates, top_k)
        elif strategy == SearchStrategy.HYBRID_LINEAR:
            results = self._hybrid_linear_search(query, candidates, top_k)
        else:  # HYBRID_RRF
            results = self._hybrid_rrf_search(query, candidates, top_k)

        return results

    def _select_adaptive_strategy(self, query: str) -> SearchStrategy:
        """
        Select strategy based on query characteristics.

        Args:
            query: Search query

        Returns:
            Selected strategy
        """
        # Simple heuristics (can be improved with ML)
        query_length = len(query.split())

        if query_length <= 2:
            # Short queries benefit from keyword search
            return SearchStrategy.KEYWORD_ONLY
        elif query_length >= 10:
            # Long queries benefit from semantic search
            return SearchStrategy.SEMANTIC_ONLY
        else:
            # Medium queries benefit from hybrid
            return SearchStrategy.HYBRID_RRF

    def _get_candidates(
        self,
        filter_metadata: Optional[Dict[str, Any]]
    ) -> List[int]:
        """Get candidate document indices based on filters."""
        if not filter_metadata:
            return list(range(len(self.documents)))

        candidates = []
        for idx, meta in enumerate(self.metadata):
            match = all(
                meta.get(key) == value
                for key, value in filter_metadata.items()
            )
            if match:
                candidates.append(idx)

        return candidates

    def _semantic_search(
        self,
        query: str,
        candidates: List[int],
        top_k: int
    ) -> List[SearchResult]:
        """Perform semantic search using embeddings."""
        if not self.embeddings:
            return []

        # Generate query embedding
        query_embedding = self._generate_embeddings([query])[0]

        # Calculate cosine similarities
        scores = []
        for idx in candidates:
            doc_embedding = self.embeddings[idx]
            similarity = np.dot(query_embedding, doc_embedding)
            scores.append((idx, similarity))

        # Sort by score
        scores.sort(key=lambda x: x[1], reverse=True)

        # Create results
        results = []
        for idx, score in scores[:top_k]:
            results.append(SearchResult(
                doc_id=self.doc_ids[idx],
                content=self.documents[idx],
                score=score,
                semantic_score=score,
                metadata=self.metadata[idx]
            ))

        return results

    def _keyword_search(
        self,
        query: str,
        candidates: List[int],
        top_k: int
    ) -> List[SearchResult]:
        """Perform keyword search using BM25."""
        # Get BM25 scores for all documents
        all_scores = []
        for idx in range(len(self.documents)):
            score = self.bm25.score(query, idx)
            all_scores.append((idx, score))

        # Filter by candidates and sort
        filtered_scores = [
            (idx, score) for idx, score in all_scores
            if idx in candidates and score > 0
        ]
        filtered_scores.sort(key=lambda x: x[1], reverse=True)

        # Create results
        results = []
        for idx, score in filtered_scores[:top_k]:
            results.append(SearchResult(
                doc_id=self.doc_ids[idx],
                content=self.documents[idx],
                score=score,
                keyword_score=score,
                metadata=self.metadata[idx]
            ))

        return results

    def _hybrid_linear_search(
        self,
        query: str,
        candidates: List[int],
        top_k: int
    ) -> List[SearchResult]:
        """
        Hybrid search with linear combination of scores.

        Final score = α * semantic_score + (1-α) * keyword_score
        """
        # Get semantic results
        semantic_results = self._semantic_search(query, candidates, len(candidates))
        semantic_scores = {r.doc_id: r.semantic_score for r in semantic_results}

        # Get keyword results
        keyword_results = self._keyword_search(query, candidates, len(candidates))
        keyword_scores = {r.doc_id: r.keyword_score for r in keyword_results}

        # Combine scores
        all_doc_ids = set(semantic_scores.keys()) | set(keyword_scores.keys())
        combined_scores = []

        for doc_id in all_doc_ids:
            # Normalize scores to [0, 1]
            sem_score = semantic_scores.get(doc_id, 0)
            key_score = keyword_scores.get(doc_id, 0)

            # Linear combination
            combined_score = (
                self.semantic_weight * sem_score +
                self.keyword_weight * key_score
            )

            combined_scores.append((doc_id, combined_score, sem_score, key_score))

        # Sort by combined score
        combined_scores.sort(key=lambda x: x[1], reverse=True)

        # Create results
        results = []
        for doc_id, score, sem_score, key_score in combined_scores[:top_k]:
            idx = self.doc_ids.index(doc_id)
            results.append(SearchResult(
                doc_id=doc_id,
                content=self.documents[idx],
                score=score,
                semantic_score=sem_score,
                keyword_score=key_score,
                metadata=self.metadata[idx]
            ))

        return results

    def _hybrid_rrf_search(
        self,
        query: str,
        candidates: List[int],
        top_k: int,
        k_param: int = 60
    ) -> List[SearchResult]:
        """
        Hybrid search with Reciprocal Rank Fusion.

        RRF combines rankings from different methods without
        requiring score normalization.
        """
        # Get semantic results
        semantic_results = self._semantic_search(query, candidates, top_k * 2)
        semantic_ranks = {r.doc_id: i + 1 for i, r in enumerate(semantic_results)}

        # Get keyword results
        keyword_results = self._keyword_search(query, candidates, top_k * 2)
        keyword_ranks = {r.doc_id: i + 1 for i, r in enumerate(keyword_results)}

        # Calculate RRF scores
        all_doc_ids = set(semantic_ranks.keys()) | set(keyword_ranks.keys())
        rrf_scores = []

        for doc_id in all_doc_ids:
            # RRF formula: 1 / (k + rank)
            sem_rank = semantic_ranks.get(doc_id, top_k * 2 + 1)
            key_rank = keyword_ranks.get(doc_id, top_k * 2 + 1)

            rrf_score = (
                1 / (k_param + sem_rank) +
                1 / (k_param + key_rank)
            )

            # Get original scores for reference
            sem_score = next((r.semantic_score for r in semantic_results if r.doc_id == doc_id), 0)
            key_score = next((r.keyword_score for r in keyword_results if r.doc_id == doc_id), 0)

            rrf_scores.append((doc_id, rrf_score, sem_score, key_score))

        # Sort by RRF score
        rrf_scores.sort(key=lambda x: x[1], reverse=True)

        # Create results
        results = []
        for doc_id, score, sem_score, key_score in rrf_scores[:top_k]:
            idx = self.doc_ids.index(doc_id)
            results.append(SearchResult(
                doc_id=doc_id,
                content=self.documents[idx],
                score=score,
                semantic_score=sem_score,
                keyword_score=key_score,
                metadata=self.metadata[idx]
            ))

        return results

    def update_weights(
        self,
        semantic_weight: float
    ):
        """
        Update search weights.

        Args:
            semantic_weight: Weight for semantic search (0-1)
        """
        self.semantic_weight = max(0, min(1, semantic_weight))
        self.keyword_weight = 1 - self.semantic_weight