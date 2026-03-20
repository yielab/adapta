"""
Tests for hybrid search functionality.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch

from brain.rag.advanced.hybrid_search import (
    HybridSearchEngine,
    BM25,
    SearchResult,
    SearchStrategy
)


class TestBM25:
    """Test BM25 keyword search."""

    @pytest.fixture
    def documents(self):
        """Sample documents for testing."""
        return [
            "Python is a programming language",
            "Machine learning with Python",
            "Data science and analytics",
            "Python for web development",
            "Natural language processing"
        ]

    @pytest.fixture
    def bm25(self, documents):
        """Create BM25 instance."""
        bm25 = BM25()
        bm25.fit(documents)
        return bm25

    def test_fit_documents(self, bm25, documents):
        """Test fitting documents."""
        assert bm25.corpus_size == len(documents)
        assert len(bm25.doc_lengths) == len(documents)
        assert bm25.avgdl > 0
        assert len(bm25.idf) > 0

    def test_score_calculation(self, bm25):
        """Test BM25 score calculation."""
        # Query matching first document
        score = bm25.score("Python programming", 0)
        assert score > 0

        # Query not matching
        score = bm25.score("JavaScript", 0)
        assert score == 0

    def test_search(self, bm25):
        """Test BM25 search."""
        results = bm25.search("Python", top_k=3)

        assert len(results) <= 3
        assert all(score > 0 for _, score in results)
        # Results should be sorted by score
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)

    def test_idf_calculation(self, bm25):
        """Test IDF calculation."""
        # "Python" appears in 3 out of 5 documents
        assert "python" in bm25.idf

        # Rare words should have higher IDF
        common_word_idf = bm25.idf.get("python", 0)
        rare_word_idf = bm25.idf.get("analytics", 0)
        assert rare_word_idf > common_word_idf


class TestHybridSearchEngine:
    """Test hybrid search engine."""

    @pytest.fixture
    def documents(self):
        """Sample documents."""
        return [
            "Introduction to machine learning algorithms",
            "Deep learning neural networks",
            "Natural language processing with transformers",
            "Computer vision and image recognition",
            "Reinforcement learning for robotics"
        ]

    @pytest.fixture
    def metadata(self):
        """Sample metadata."""
        return [
            {"category": "ml", "difficulty": "beginner"},
            {"category": "dl", "difficulty": "advanced"},
            {"category": "nlp", "difficulty": "intermediate"},
            {"category": "cv", "difficulty": "intermediate"},
            {"category": "rl", "difficulty": "advanced"}
        ]

    @pytest.fixture
    def engine(self, documents, metadata):
        """Create hybrid search engine."""
        engine = HybridSearchEngine(
            strategy=SearchStrategy.HYBRID_RRF,
            semantic_weight=0.5
        )
        engine.index_documents(documents, metadata)
        return engine

    def test_index_documents(self, engine, documents):
        """Test document indexing."""
        assert len(engine.documents) == len(documents)
        assert len(engine.doc_ids) == len(documents)
        assert engine.bm25.corpus_size == len(documents)

    def test_keyword_only_search(self, engine):
        """Test keyword-only search."""
        results = engine.search(
            "machine learning",
            top_k=3,
            strategy=SearchStrategy.KEYWORD_ONLY
        )

        assert len(results) <= 3
        assert all(isinstance(r, SearchResult) for r in results)
        assert results[0].keyword_score is not None

    def test_semantic_only_search(self, engine):
        """Test semantic-only search."""
        results = engine.search(
            "AI and ML",
            top_k=3,
            strategy=SearchStrategy.SEMANTIC_ONLY
        )

        assert len(results) <= 3
        assert all(isinstance(r, SearchResult) for r in results)
        assert results[0].semantic_score is not None

    def test_hybrid_linear_search(self, engine):
        """Test hybrid linear combination search."""
        results = engine.search(
            "deep learning",
            top_k=3,
            strategy=SearchStrategy.HYBRID_LINEAR
        )

        assert len(results) <= 3
        for result in results:
            assert result.semantic_score is not None
            assert result.keyword_score is not None
            assert result.score > 0

    def test_hybrid_rrf_search(self, engine):
        """Test hybrid RRF search."""
        results = engine.search(
            "neural networks",
            top_k=3,
            strategy=SearchStrategy.HYBRID_RRF
        )

        assert len(results) <= 3
        assert all(r.score > 0 for r in results)

    def test_adaptive_strategy_selection(self, engine):
        """Test adaptive strategy selection."""
        # Short query - should use keyword
        strategy = engine._select_adaptive_strategy("ML")
        assert strategy == SearchStrategy.KEYWORD_ONLY

        # Long query - should use semantic
        long_query = "How can I implement a convolutional neural network for image classification"
        strategy = engine._select_adaptive_strategy(long_query)
        assert strategy == SearchStrategy.SEMANTIC_ONLY

        # Medium query - should use hybrid
        medium_query = "machine learning algorithms"
        strategy = engine._select_adaptive_strategy(medium_query)
        assert strategy == SearchStrategy.HYBRID_RRF

    def test_metadata_filtering(self, engine):
        """Test search with metadata filters."""
        results = engine.search(
            "learning",
            top_k=5,
            filter_metadata={"difficulty": "advanced"}
        )

        # Should only return advanced difficulty documents
        for result in results:
            assert result.metadata.get("difficulty") == "advanced"

    def test_update_weights(self, engine):
        """Test updating search weights."""
        engine.update_weights(0.8)

        assert engine.semantic_weight == 0.8
        assert engine.keyword_weight == 0.2

        # Test bounds
        engine.update_weights(1.5)
        assert engine.semantic_weight == 1.0
        assert engine.keyword_weight == 0.0

    def test_search_result_format(self, engine):
        """Test search result format."""
        results = engine.search("learning", top_k=1)

        if results:
            result = results[0]
            result_dict = result.to_dict()

            assert "doc_id" in result_dict
            assert "content" in result_dict
            assert "score" in result_dict
            assert "metadata" in result_dict

    def test_empty_query(self, engine):
        """Test search with empty query."""
        results = engine.search("", top_k=3)
        # Should handle empty query gracefully
        assert isinstance(results, list)

    def test_no_matching_documents(self, engine):
        """Test search with no matches."""
        results = engine.search(
            "quantum computing blockchain",
            top_k=3,
            strategy=SearchStrategy.KEYWORD_ONLY
        )
        # Should return empty or low-scoring results
        assert isinstance(results, list)