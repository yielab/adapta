"""
Tests for citation tracking functionality.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from brain.rag.advanced.citations import (
    Citation,
    CitedResponse,
    CitationTracker,
    AutoCitationInjector
)


class TestCitation:
    """Test Citation class."""

    def test_create_citation(self):
        """Test creating a citation."""
        citation = Citation(
            citation_id="cite_001",
            source_id="source_001",
            source_title="Test Source",
            content="This is test content",
            url="https://example.com",
            author="John Doe",
            date=datetime(2024, 1, 1),
            confidence=0.9
        )

        assert citation.citation_id == "cite_001"
        assert citation.source_title == "Test Source"
        assert citation.confidence == 0.9

    def test_citation_to_dict(self):
        """Test converting citation to dictionary."""
        citation = Citation(
            citation_id="cite_001",
            source_id="source_001",
            source_title="Test Source",
            content="Test content",
            date=datetime(2024, 1, 1)
        )

        citation_dict = citation.to_dict()

        assert citation_dict["citation_id"] == "cite_001"
        assert citation_dict["source_title"] == "Test Source"
        assert citation_dict["date"] == "2024-01-01T00:00:00"

    def test_format_inline_number(self):
        """Test inline citation formatting with numbers."""
        citation = Citation(
            citation_id="001",
            source_id="s1",
            source_title="Test",
            content="Content"
        )

        inline = citation.format_inline("number")
        assert inline == "[001]"

    def test_format_inline_author(self):
        """Test inline citation formatting with author."""
        citation = Citation(
            citation_id="001",
            source_id="s1",
            source_title="Test",
            content="Content",
            author="Smith",
            date=datetime(2024, 1, 1)
        )

        inline = citation.format_inline("author")
        assert inline == "(Smith, 2024)"

    def test_format_inline_title(self):
        """Test inline citation formatting with title."""
        citation = Citation(
            citation_id="001",
            source_id="s1",
            source_title="Important Paper",
            content="Content"
        )

        inline = citation.format_inline("title")
        assert inline == "[Important Paper]"

    def test_format_reference_apa(self):
        """Test APA reference formatting."""
        citation = Citation(
            citation_id="001",
            source_id="s1",
            source_title="Test Article",
            content="Content",
            author="Smith, J",
            date=datetime(2024, 1, 1),
            url="https://example.com"
        )

        reference = citation.format_reference("apa")
        assert "Smith, J" in reference
        assert "2024" in reference
        assert "Test Article" in reference
        assert "https://example.com" in reference

    def test_format_reference_mla(self):
        """Test MLA reference formatting."""
        citation = Citation(
            citation_id="001",
            source_id="s1",
            source_title="Test Article",
            content="Content",
            author="Smith, John",
            date=datetime(2024, 1, 15)
        )

        reference = citation.format_reference("mla")
        assert "Smith, John" in reference
        assert '"Test Article."' in reference
        assert "15 Jan 2024" in reference


class TestCitedResponse:
    """Test CitedResponse class."""

    @pytest.fixture
    def citations(self):
        """Sample citations."""
        return [
            Citation(
                citation_id="001",
                source_id="source1",
                source_title="Source One",
                content="Content 1"
            ),
            Citation(
                citation_id="002",
                source_id="source2",
                source_title="Source Two",
                content="Content 2"
            ),
            Citation(
                citation_id="003",
                source_id="source1",  # Duplicate source
                source_title="Source One",
                content="Content 3"
            )
        ]

    def test_create_cited_response(self, citations):
        """Test creating a cited response."""
        citation_map = {c.citation_id: c for c in citations}
        response = CitedResponse(
            content="This is the response text",
            citations=citations,
            citation_map=citation_map
        )

        assert response.content == "This is the response text"
        assert len(response.citations) == 3
        assert len(response.citation_map) == 3

    def test_get_unique_sources(self, citations):
        """Test getting unique source IDs."""
        citation_map = {c.citation_id: c for c in citations}
        response = CitedResponse(
            content="Text",
            citations=citations,
            citation_map=citation_map
        )

        unique = response.get_unique_sources()
        assert len(unique) == 2  # source1 and source2
        assert "source1" in unique
        assert "source2" in unique

    def test_format_with_citations(self, citations):
        """Test formatting response with citations."""
        citation_map = {c.citation_id: c for c in citations}
        response = CitedResponse(
            content="This is {cite:001} and this is {cite:002}.",
            citations=citations[:2],
            citation_map=citation_map
        )

        formatted = response.format_with_citations(
            inline_style="number",
            include_references=True,
            reference_style="apa"
        )

        assert "[001]" in formatted
        assert "[002]" in formatted
        assert "References:" in formatted
        assert "Source One" in formatted
        assert "Source Two" in formatted


class TestCitationTracker:
    """Test CitationTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create citation tracker."""
        return CitationTracker(
            min_confidence=0.5,
            max_citations_per_response=10,
            deduplication=True
        )

    @pytest.fixture
    def sources(self):
        """Sample source documents."""
        return [
            {
                "id": "doc1",
                "title": "Machine Learning Basics",
                "content": "Machine learning is a subset of artificial intelligence.",
                "author": "Smith, J.",
                "url": "https://ml-basics.com"
            },
            {
                "id": "doc2",
                "title": "Deep Learning Guide",
                "content": "Deep learning uses neural networks with multiple layers.",
                "author": "Johnson, A.",
                "url": "https://dl-guide.com"
            },
            {
                "id": "doc3",
                "title": "NLP Fundamentals",
                "content": "Natural language processing enables computers to understand text.",
                "author": "Williams, B.",
                "url": "https://nlp-fund.com"
            }
        ]

    def test_extract_citations(self, tracker, sources):
        """Test extracting citations from response."""
        response = "Machine learning is important. Neural networks are powerful."

        cited_response = tracker.extract_citations(response, sources)

        assert isinstance(cited_response, CitedResponse)
        assert cited_response.content == response
        assert len(cited_response.citations) >= 0

    def test_find_citation_points(self, tracker, sources):
        """Test finding citation points."""
        response = "Machine learning is a subset of AI. Deep learning is advanced."

        points = tracker._find_citation_points(response, sources)

        assert isinstance(points, list)
        # Should find matches for content similarity

    def test_split_sentences(self, tracker):
        """Test sentence splitting."""
        text = "First sentence. Second sentence! Third sentence? Fourth."

        sentences = tracker._split_sentences(text)

        assert len(sentences) == 4
        assert sentences[0] == "First sentence"
        assert sentences[1] == "Second sentence"
        assert sentences[2] == "Third sentence"

    def test_calculate_similarity(self, tracker):
        """Test similarity calculation."""
        text1 = "machine learning algorithms"
        text2 = "machine learning models and algorithms"

        similarity = tracker._calculate_similarity(text1, text2)

        assert 0 <= similarity <= 1
        assert similarity > 0.5  # Should have high similarity

        # Test dissimilar texts
        text3 = "completely different content"
        similarity2 = tracker._calculate_similarity(text1, text3)
        assert similarity2 < similarity

    def test_create_citation(self, tracker, sources):
        """Test creating a citation."""
        citation_point = {
            "sentence": "Test sentence",
            "sentence_idx": 0,
            "source": sources[0],
            "confidence": 0.8
        }

        citation = tracker._create_citation(citation_point, sources)

        assert isinstance(citation, Citation)
        assert citation.source_id == "doc1"
        assert citation.source_title == "Machine Learning Basics"
        assert citation.confidence == 0.8

    def test_deduplicate_citations(self, tracker):
        """Test citation deduplication."""
        citations = [
            Citation("001", "source1", "Title 1", "Content", confidence=0.8),
            Citation("002", "source1", "Title 1", "Content", confidence=0.9),
            Citation("003", "source2", "Title 2", "Content", confidence=0.7)
        ]

        deduplicated = tracker._deduplicate_citations(citations)

        assert len(deduplicated) == 2  # Only unique sources
        # Should keep highest confidence for duplicates
        source1_citation = next(c for c in deduplicated if c.source_id == "source1")
        assert source1_citation.confidence == 0.9

    def test_rank_citations(self, tracker):
        """Test citation ranking."""
        citations = [
            Citation("001", "s1", "T1", "C", confidence=0.5),
            Citation("002", "s2", "T2", "C", confidence=0.9),
            Citation("003", "s3", "T3", "C", confidence=0.7)
        ]

        ranked = tracker._rank_citations(citations)

        assert ranked[0].confidence == 0.9
        assert ranked[1].confidence == 0.7
        assert ranked[2].confidence == 0.5

    def test_format_citations(self, tracker):
        """Test formatting citation list."""
        citations = [
            Citation("001", "s1", "First Paper", "Content", author="Smith"),
            Citation("002", "s2", "Second Paper", "Content", author="Jones")
        ]

        formatted = tracker.format_citations(citations, style="apa")

        assert "1. " in formatted
        assert "2. " in formatted
        assert "First Paper" in formatted
        assert "Second Paper" in formatted

    def test_get_citation_stats(self, tracker):
        """Test getting citation statistics."""
        # Add some citations
        tracker.citations = {
            "001": Citation("001", "source1", "T1", "C", confidence=0.8),
            "002": Citation("002", "source1", "T1", "C", confidence=0.9),
            "003": Citation("003", "source2", "T2", "C", confidence=0.7)
        }
        tracker.source_index = {
            "source1": ["001", "002"],
            "source2": ["003"]
        }

        stats = tracker.get_citation_stats()

        assert stats["total_citations"] == 3
        assert stats["unique_sources"] == 2
        assert stats["most_cited_source"] == "source1"
        assert 0.7 < stats["average_confidence"] < 0.9


class TestAutoCitationInjector:
    """Test AutoCitationInjector class."""

    @pytest.fixture
    def injector(self):
        """Create auto-citation injector."""
        return AutoCitationInjector()

    @pytest.fixture
    def sources(self):
        """Sample sources."""
        return [
            {
                "id": "doc1",
                "title": "Source 1",
                "content": "Machine learning is powerful"
            },
            {
                "id": "doc2",
                "title": "Source 2",
                "content": "Neural networks learn patterns"
            }
        ]

    def test_inject_inline_citations(self, injector, sources):
        """Test injecting inline citations."""
        text = "Machine learning is powerful. Neural networks are amazing."

        with patch.object(injector.tracker, 'extract_citations') as mock_extract:
            # Mock citation extraction
            citations = [
                Citation("001", "doc1", "Source 1", "Machine learning is powerful",
                        metadata={"sentence_idx": 0}),
                Citation("002", "doc2", "Source 2", "Neural networks are amazing",
                        metadata={"sentence_idx": 1})
            ]
            citation_map = {c.citation_id: c for c in citations}
            mock_extract.return_value = CitedResponse(text, citations, citation_map)

            result = injector.inject_citations(text, sources, style="inline")

            assert "[001]" in result or "[1]" in result
            # Should have citations added

    def test_inject_footnote_citations(self, injector, sources):
        """Test injecting footnote citations."""
        text = "Test text with information."

        with patch.object(injector.tracker, 'extract_citations') as mock_extract:
            citations = [Citation("001", "doc1", "Source 1", "Test content")]
            citation_map = {c.citation_id: c for c in citations}
            cited_response = CitedResponse(text, citations, citation_map)
            cited_response.format_with_citations = Mock(return_value="Text with footnotes")
            mock_extract.return_value = cited_response

            result = injector.inject_citations(text, sources, style="footnote")

            assert result == "Text with footnotes"

    def test_inject_unsupported_style(self, injector, sources):
        """Test injection with unsupported style."""
        text = "Test text"

        result = injector.inject_citations(text, sources, style="unsupported")

        # Should return original text
        assert result == text