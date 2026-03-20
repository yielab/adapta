"""
Tests for query expansion functionality.
"""

import pytest
from unittest.mock import Mock, patch

from brain.rag.advanced.query_expansion import (
    QueryExpander,
    DomainSpecificExpander,
    AdaptiveQueryExpander,
    ExpandedQuery,
    ExpansionStrategy
)


class TestQueryExpander:
    """Test basic query expander."""

    @pytest.fixture
    def expander(self):
        """Create query expander."""
        return QueryExpander(
            enable_synonyms=True,
            enable_semantic=True,
            enable_reformulation=True,
            max_expansions=5
        )

    def test_synonym_expansion(self, expander):
        """Test synonym-based expansion."""
        expanded = expander.expand("create function", ExpansionStrategy.SYNONYM)

        assert expanded.original == "create function"
        assert len(expanded.expansions) > 0

        # Check for expected synonyms
        all_queries = expanded.get_all_queries()
        assert any("method" in q for q in all_queries)

    def test_semantic_expansion(self, expander):
        """Test semantic expansion."""
        expanded = expander.expand("how to debug code", ExpansionStrategy.SEMANTIC)

        assert expanded.original == "how to debug code"
        assert len(expanded.expansions) > 0

        # Check for semantic alternatives
        all_queries = expanded.get_all_queries()
        assert any("tutorial" in q or "guide" in q for q in all_queries)

    def test_reformulation_expansion(self, expander):
        """Test query reformulation."""
        expanded = expander.expand("what is Python?", ExpansionStrategy.REFORMULATION)

        assert expanded.original == "what is Python?"
        assert len(expanded.expansions) > 0

        # Check for reformulation
        all_queries = expanded.get_all_queries()
        assert any("definition" in q.lower() for q in all_queries)

    def test_hybrid_expansion(self, expander):
        """Test hybrid expansion strategy."""
        expanded = expander.expand("how to fix error", ExpansionStrategy.HYBRID)

        assert expanded.strategy == ExpansionStrategy.HYBRID
        assert len(expanded.expansions) > 0

        # Should have multiple types of expansions
        metadata = expanded.metadata
        total = metadata.get("synonym_count", 0) + \
                metadata.get("semantic_count", 0) + \
                metadata.get("reformulation_count", 0)
        assert total > 0

    def test_max_expansions_limit(self, expander):
        """Test maximum expansions limit."""
        expander.max_expansions = 3
        expanded = expander.expand("create update delete get set", ExpansionStrategy.HYBRID)

        assert len(expanded.expansions) <= 3

    def test_duplicate_removal(self, expander):
        """Test duplicate expansion removal."""
        # Use a query that might generate duplicates
        expanded = expander.expand("function function", ExpansionStrategy.SYNONYM)

        # Check no duplicates in expansions
        expansions = expanded.expansions
        assert len(expansions) == len(set(exp.lower() for exp in expansions))

    def test_get_unique_terms(self, expander):
        """Test getting unique terms from expansions."""
        expanded = expander.expand("machine learning", ExpansionStrategy.HYBRID)

        unique_terms = expanded.get_unique_terms()
        assert isinstance(unique_terms, set)
        assert "machine" in unique_terms
        assert "learning" in unique_terms

    def test_empty_query(self, expander):
        """Test expansion with empty query."""
        expanded = expander.expand("", ExpansionStrategy.HYBRID)

        assert expanded.original == ""
        # Empty query should not crash

    def test_batch_expansion(self, expander):
        """Test batch query expansion."""
        queries = [
            "create function",
            "fix error",
            "how to optimize"
        ]

        expanded_list = expander.expand_batch(queries)

        assert len(expanded_list) == len(queries)
        assert all(isinstance(e, ExpandedQuery) for e in expanded_list)

    def test_disable_strategies(self):
        """Test disabling specific strategies."""
        expander = QueryExpander(
            enable_synonyms=False,
            enable_semantic=True,
            enable_reformulation=False
        )

        expanded = expander.expand("create function", ExpansionStrategy.HYBRID)

        # Should only have semantic expansions
        assert expanded.metadata.get("synonym_count", 0) == 0
        assert expanded.metadata.get("reformulation_count", 0) == 0


class TestDomainSpecificExpander:
    """Test domain-specific expander."""

    def test_technical_domain(self):
        """Test technical domain expansion."""
        expander = DomainSpecificExpander(domain="technical")

        expanded = expander.expand("deploy cache", ExpansionStrategy.SYNONYM)

        all_queries = expanded.get_all_queries()
        # Should include technical synonyms
        assert any("release" in q or "buffer" in q for q in all_queries)

    def test_medical_domain(self):
        """Test medical domain expansion."""
        expander = DomainSpecificExpander(domain="medical")

        expanded = expander.expand("patient symptom", ExpansionStrategy.SYNONYM)

        all_queries = expanded.get_all_queries()
        # Should include medical synonyms
        assert any("sign" in q or "subject" in q for q in all_queries)

    def test_legal_domain(self):
        """Test legal domain expansion."""
        expander = DomainSpecificExpander(domain="legal")

        expanded = expander.expand("contract clause", ExpansionStrategy.SYNONYM)

        all_queries = expanded.get_all_queries()
        # Should include legal synonyms
        assert any("agreement" in q or "provision" in q for q in all_queries)

    def test_general_domain(self):
        """Test general domain (default)."""
        expander = DomainSpecificExpander(domain="general")

        # Should still have base synonyms
        expanded = expander.expand("create function", ExpansionStrategy.SYNONYM)
        assert len(expanded.expansions) > 0


class TestAdaptiveQueryExpander:
    """Test adaptive query expander."""

    @pytest.fixture
    def adaptive_expander(self):
        """Create adaptive expander."""
        return AdaptiveQueryExpander()

    def test_basic_expansion(self, adaptive_expander):
        """Test basic adaptive expansion."""
        expanded = adaptive_expander.expand("machine learning")

        assert expanded.original == "machine learning"
        assert isinstance(expanded, ExpandedQuery)

    def test_record_successful_feedback(self, adaptive_expander):
        """Test recording successful expansion feedback."""
        query = "test query"
        expansion = "test query expansion"

        adaptive_expander.record_feedback(query, expansion, successful=True)

        assert query in adaptive_expander.successful_expansions
        assert expansion in adaptive_expander.successful_expansions[query]

    def test_record_failed_feedback(self, adaptive_expander):
        """Test recording failed expansion feedback."""
        query = "test query"
        expansion = "bad expansion"

        adaptive_expander.record_feedback(query, expansion, successful=False)

        assert query in adaptive_expander.failed_expansions
        assert expansion in adaptive_expander.failed_expansions[query]

    def test_filter_failed_expansions(self, adaptive_expander):
        """Test filtering out failed expansions."""
        query = "machine learning"

        # First expansion without feedback
        expanded1 = adaptive_expander.expand(query)
        initial_count = len(expanded1.expansions)

        # Mark some expansions as failed
        if expanded1.expansions:
            failed_expansion = expanded1.expansions[0]
            adaptive_expander.record_feedback(query, failed_expansion, successful=False)

        # Second expansion should filter out failed
        expanded2 = adaptive_expander.expand(query)
        assert failed_expansion not in expanded2.expansions

    def test_prioritize_successful_expansions(self, adaptive_expander):
        """Test prioritizing successful expansions."""
        query = "test query"
        successful_expansion = "good expansion"

        # Record successful expansion
        adaptive_expander.record_feedback(query, successful_expansion, successful=True)

        # Next expansion should include it first
        expanded = adaptive_expander.expand(query)
        if expanded.expansions:
            assert expanded.expansions[0] == successful_expansion

    def test_feedback_overwrite(self, adaptive_expander):
        """Test that feedback can be updated."""
        query = "test"
        expansion = "test expansion"

        # First mark as failed
        adaptive_expander.record_feedback(query, expansion, successful=False)
        assert expansion in adaptive_expander.failed_expansions.get(query, set())

        # Then mark as successful
        adaptive_expander.record_feedback(query, expansion, successful=True)
        assert expansion in adaptive_expander.successful_expansions.get(query, set())
        assert expansion not in adaptive_expander.failed_expansions.get(query, set())

    def test_expansion_history(self, adaptive_expander):
        """Test expansion history tracking."""
        query = "test query"

        expanded = adaptive_expander.expand(query)

        assert query in adaptive_expander.expansion_history
        assert all(
            exp in adaptive_expander.expansion_history[query]
            for exp in expanded.expansions
        )

    def test_with_context(self, adaptive_expander):
        """Test expansion with context."""
        context = {
            "domain": "technical",
            "user_preference": "concise"
        }

        expanded = adaptive_expander.expand("deploy application", context=context)

        assert isinstance(expanded, ExpandedQuery)
        # Context should be processed (even if not used in basic implementation)