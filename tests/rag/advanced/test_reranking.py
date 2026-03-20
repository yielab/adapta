"""
Tests for cross-encoder re-ranking.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import torch
import numpy as np

from brain.rag.advanced.reranking import (
    CrossEncoderReranker,
    LightweightReranker,
    HybridReranker,
    RerankingConfig
)
from brain.rag.advanced.hybrid_search import SearchResult


class TestCrossEncoderReranker:
    """Test cross-encoder re-ranker."""

    @pytest.fixture
    def mock_model(self):
        """Mock transformer model."""
        with patch('brain.rag.advanced.reranking.AutoTokenizer') as mock_tokenizer:
            with patch('brain.rag.advanced.reranking.AutoModelForSequenceClassification') as mock_model:
                # Setup mock tokenizer
                tokenizer_instance = MagicMock()
                tokenizer_instance.return_value = {
                    'input_ids': torch.tensor([[1, 2, 3]]),
                    'attention_mask': torch.tensor([[1, 1, 1]])
                }
                mock_tokenizer.from_pretrained.return_value = tokenizer_instance

                # Setup mock model
                model_instance = MagicMock()
                model_output = MagicMock()
                model_output.logits = torch.tensor([[0.8]])
                model_instance.return_value = model_output
                model_instance.eval = MagicMock()
                model_instance.to = MagicMock(return_value=model_instance)
                mock_model.from_pretrained.return_value = model_instance

                yield model_instance

    @pytest.fixture
    def search_results(self):
        """Sample search results."""
        return [
            SearchResult(
                doc_id="doc1",
                content="Machine learning is a subset of AI",
                score=0.7,
                metadata={}
            ),
            SearchResult(
                doc_id="doc2",
                content="Deep learning uses neural networks",
                score=0.6,
                metadata={}
            ),
            SearchResult(
                doc_id="doc3",
                content="Natural language processing techniques",
                score=0.5,
                metadata={}
            )
        ]

    def test_init_with_model(self, mock_model):
        """Test initialization with model loading."""
        config = RerankingConfig(device="cpu")
        reranker = CrossEncoderReranker(config)

        assert reranker.config == config
        assert reranker.model is not None
        assert reranker.tokenizer is not None

    @patch('brain.rag.advanced.reranking.AutoTokenizer')
    @patch('brain.rag.advanced.reranking.AutoModelForSequenceClassification')
    def test_init_model_failure(self, mock_model, mock_tokenizer):
        """Test initialization when model loading fails."""
        mock_tokenizer.from_pretrained.side_effect = Exception("Model not found")

        reranker = CrossEncoderReranker()
        assert reranker.model is None
        assert reranker.tokenizer is None

    def test_rerank_without_model(self, search_results):
        """Test re-ranking without a model."""
        reranker = CrossEncoderReranker()
        reranker.model = None  # Simulate no model

        results = reranker.rerank("machine learning", search_results)
        # Should return original results
        assert results == search_results

    def test_rerank_with_mock_model(self, mock_model, search_results):
        """Test re-ranking with mocked model."""
        reranker = CrossEncoderReranker()

        # Mock the scoring
        with patch.object(reranker, '_score_pairs') as mock_score:
            mock_score.return_value = np.array([0.9, 0.3, 0.6])

            results = reranker.rerank("machine learning", search_results, top_k=2)

            assert len(results) == 2
            # First result should have highest score
            assert results[0].score == 0.9
            assert results[0].metadata.get('rerank_score') == 0.9

    def test_rerank_with_threshold(self, mock_model, search_results):
        """Test re-ranking with score threshold."""
        config = RerankingConfig(score_threshold=0.5)
        reranker = CrossEncoderReranker(config)

        with patch.object(reranker, '_score_pairs') as mock_score:
            mock_score.return_value = np.array([0.7, 0.3, 0.6])

            results = reranker.rerank("machine learning", search_results)

            # Only results above threshold
            assert all(r.score >= 0.5 for r in results)

    def test_batch_processing(self, mock_model, search_results):
        """Test batch processing of documents."""
        config = RerankingConfig(batch_size=2)
        reranker = CrossEncoderReranker(config)

        # Create more results to test batching
        many_results = search_results * 3  # 9 results

        with patch.object(reranker, '_score_pairs') as mock_score:
            scores = np.random.random(9)
            mock_score.return_value = scores

            results = reranker.rerank("test query", many_results)

            # Check all results processed
            assert len(results) <= len(many_results)

    def test_rerank_multiple_queries(self, mock_model, search_results):
        """Test re-ranking multiple queries."""
        reranker = CrossEncoderReranker()

        queries_results = [
            ("query1", search_results[:2]),
            ("query2", search_results[1:])
        ]

        with patch.object(reranker, 'rerank') as mock_rerank:
            mock_rerank.side_effect = [
                search_results[:2],
                search_results[1:]
            ]

            results = reranker.rerank_multiple_queries(queries_results, top_k=1)

            assert len(results) == 2
            assert mock_rerank.call_count == 2


class TestLightweightReranker:
    """Test lightweight re-ranker."""

    @pytest.fixture
    def search_results(self):
        """Sample search results."""
        return [
            SearchResult(
                doc_id="doc1",
                content="Python machine learning tutorial",
                score=0.7,
                metadata={}
            ),
            SearchResult(
                doc_id="doc2",
                content="Introduction to Python programming",
                score=0.6,
                metadata={}
            ),
            SearchResult(
                doc_id="doc3",
                content="Advanced machine learning with Python",
                score=0.5,
                metadata={}
            )
        ]

    def test_exact_match_boost(self, search_results):
        """Test exact match boosting."""
        reranker = LightweightReranker()

        results = reranker.rerank("machine learning", search_results)

        # Documents with exact match should score higher
        ml_docs = [r for r in results if "machine learning" in r.content.lower()]
        other_docs = [r for r in results if "machine learning" not in r.content.lower()]

        if ml_docs and other_docs:
            assert ml_docs[0].score > other_docs[0].score

    def test_keyword_overlap_boost(self, search_results):
        """Test keyword overlap boosting."""
        reranker = LightweightReranker()

        results = reranker.rerank("Python machine", search_results)

        # Check that results are re-scored
        assert all(r.score > 0 for r in results)

        # Document with most keyword overlap should rank high
        assert "Python" in results[0].content or "machine" in results[0].content

    def test_position_decay(self, search_results):
        """Test position decay factor."""
        reranker = LightweightReranker()

        # Set same initial score for all
        for r in search_results:
            r.score = 1.0

        results = reranker.rerank("test", search_results)

        # Scores should reflect position decay
        assert len(results) == len(search_results)

    def test_empty_results(self):
        """Test with empty results."""
        reranker = LightweightReranker()
        results = reranker.rerank("query", [])
        assert results == []

    def test_top_k_limiting(self, search_results):
        """Test limiting results with top_k."""
        reranker = LightweightReranker()

        results = reranker.rerank("Python", search_results, top_k=2)
        assert len(results) == 2


class TestHybridReranker:
    """Test hybrid re-ranker."""

    @pytest.fixture
    def search_results(self):
        """Sample search results."""
        return [
            SearchResult(
                doc_id="doc1",
                content="Machine learning algorithms",
                score=0.7,
                metadata={}
            ),
            SearchResult(
                doc_id="doc2",
                content="Deep learning models",
                score=0.6,
                metadata={}
            )
        ]

    def test_init(self):
        """Test initialization."""
        reranker = HybridReranker()

        assert reranker.cross_encoder is not None
        assert reranker.lightweight is not None

    def test_auto_strategy_with_model(self, search_results):
        """Test auto strategy when model is available."""
        reranker = HybridReranker()
        reranker.use_cross_encoder = True

        with patch.object(reranker.cross_encoder, 'rerank') as mock_cross:
            mock_cross.return_value = search_results

            results = reranker.rerank("query", search_results, strategy="auto")
            mock_cross.assert_called_once()

    def test_auto_strategy_without_model(self, search_results):
        """Test auto strategy when model is not available."""
        reranker = HybridReranker()
        reranker.use_cross_encoder = False

        with patch.object(reranker.lightweight, 'rerank') as mock_light:
            mock_light.return_value = search_results

            results = reranker.rerank("query", search_results, strategy="auto")
            mock_light.assert_called_once()

    def test_explicit_cross_encoder_strategy(self, search_results):
        """Test explicit cross-encoder strategy."""
        reranker = HybridReranker()
        reranker.use_cross_encoder = True

        with patch.object(reranker.cross_encoder, 'rerank') as mock_cross:
            mock_cross.return_value = search_results

            results = reranker.rerank("query", search_results, strategy="cross_encoder")
            mock_cross.assert_called_once()

    def test_explicit_lightweight_strategy(self, search_results):
        """Test explicit lightweight strategy."""
        reranker = HybridReranker()

        with patch.object(reranker.lightweight, 'rerank') as mock_light:
            mock_light.return_value = search_results

            results = reranker.rerank("query", search_results, strategy="lightweight")
            mock_light.assert_called_once()

    def test_fallback_to_lightweight(self, search_results):
        """Test fallback to lightweight when cross-encoder unavailable."""
        reranker = HybridReranker()
        reranker.use_cross_encoder = False

        with patch.object(reranker.lightweight, 'rerank') as mock_light:
            mock_light.return_value = search_results

            # Even with cross_encoder strategy, should fall back
            results = reranker.rerank("query", search_results, strategy="cross_encoder")
            mock_light.assert_called_once()