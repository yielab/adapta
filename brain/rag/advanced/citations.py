"""
Citation tracking for RAG-generated content.

Tracks sources and provides proper attribution for generated responses.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import re

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """A citation reference."""
    citation_id: str
    source_id: str
    source_title: str
    content: str
    url: Optional[str] = None
    author: Optional[str] = None
    date: Optional[datetime] = None
    page: Optional[int] = None
    section: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "citation_id": self.citation_id,
            "source_id": self.source_id,
            "source_title": self.source_title,
            "content": self.content,
            "url": self.url,
            "author": self.author,
            "date": self.date.isoformat() if self.date else None,
            "page": self.page,
            "section": self.section,
            "confidence": self.confidence,
            "metadata": self.metadata
        }

    def format_inline(self, style: str = "number") -> str:
        """
        Format as inline citation.

        Args:
            style: Citation style ("number", "author", "title")

        Returns:
            Formatted citation
        """
        if style == "number":
            return f"[{self.citation_id}]"
        elif style == "author" and self.author:
            year = f", {self.date.year}" if self.date else ""
            return f"({self.author}{year})"
        elif style == "title":
            return f"[{self.source_title}]"
        else:
            return f"[{self.citation_id}]"

    def format_reference(self, style: str = "apa") -> str:
        """
        Format as reference entry.

        Args:
            style: Reference style ("apa", "mla", "chicago")

        Returns:
            Formatted reference
        """
        if style == "apa":
            # APA style
            author_str = f"{self.author}. " if self.author else ""
            date_str = f"({self.date.year}). " if self.date else ""
            title_str = f"{self.source_title}. "
            url_str = f"Retrieved from {self.url}" if self.url else ""
            return f"{author_str}{date_str}{title_str}{url_str}"

        elif style == "mla":
            # MLA style
            author_str = f"{self.author}. " if self.author else ""
            title_str = f'"{self.source_title}." '
            date_str = f"{self.date.strftime('%d %b %Y')}. " if self.date else ""
            url_str = f"Web. <{self.url}>." if self.url else ""
            return f"{author_str}{title_str}{date_str}{url_str}"

        else:
            # Default simple format
            return f"{self.citation_id}. {self.source_title}"


@dataclass
class CitedResponse:
    """A response with citations."""
    content: str
    citations: List[Citation]
    citation_map: Dict[str, Citation]  # Maps citation ID to Citation

    def get_unique_sources(self) -> Set[str]:
        """Get unique source IDs."""
        return {c.source_id for c in self.citations}

    def format_with_citations(
        self,
        inline_style: str = "number",
        include_references: bool = True,
        reference_style: str = "apa"
    ) -> str:
        """
        Format response with citations.

        Args:
            inline_style: Style for inline citations
            include_references: Whether to include reference list
            reference_style: Style for references

        Returns:
            Formatted text with citations
        """
        # Add inline citations
        formatted = self.content
        for citation in self.citations:
            inline = citation.format_inline(inline_style)
            formatted = formatted.replace(f"{{cite:{citation.citation_id}}}", inline)

        # Add reference list
        if include_references and self.citations:
            formatted += "\n\nReferences:\n"
            for citation in self.citations:
                ref = citation.format_reference(reference_style)
                formatted += f"\n{ref}"

        return formatted


class CitationTracker:
    """
    Tracks citations for RAG-generated content.

    Features:
    - Source attribution
    - Citation formatting
    - Duplicate detection
    - Confidence scoring
    """

    def __init__(
        self,
        min_confidence: float = 0.5,
        max_citations_per_response: int = 10,
        deduplication: bool = True
    ):
        """
        Initialize citation tracker.

        Args:
            min_confidence: Minimum confidence for citations
            max_citations_per_response: Maximum citations per response
            deduplication: Whether to deduplicate citations
        """
        self.min_confidence = min_confidence
        self.max_citations = max_citations_per_response
        self.deduplication = deduplication

        # Citation storage
        self.citations: Dict[str, Citation] = {}
        self.source_index: Dict[str, List[str]] = {}  # source_id -> citation_ids

    def extract_citations(
        self,
        response: str,
        sources: List[Dict[str, Any]],
        threshold: Optional[float] = None
    ) -> CitedResponse:
        """
        Extract citations from a response.

        Args:
            response: Generated response text
            sources: Source documents used
            threshold: Confidence threshold

        Returns:
            Response with citations
        """
        threshold = threshold or self.min_confidence
        citations = []
        citation_map = {}

        # Find citation points in response
        citation_points = self._find_citation_points(response, sources)

        # Create citations for each point
        for point in citation_points:
            if point["confidence"] >= threshold:
                citation = self._create_citation(point, sources)
                if citation:
                    citations.append(citation)
                    citation_map[citation.citation_id] = citation

        # Deduplicate if enabled
        if self.deduplication:
            citations = self._deduplicate_citations(citations)

        # Limit citations
        if len(citations) > self.max_citations:
            citations = self._rank_citations(citations)[:self.max_citations]

        return CitedResponse(
            content=response,
            citations=citations,
            citation_map=citation_map
        )

    def _find_citation_points(
        self,
        response: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find points in response that need citations.

        Args:
            response: Response text
            sources: Source documents

        Returns:
            List of citation points
        """
        citation_points = []

        # Split response into sentences
        sentences = self._split_sentences(response)

        for sent_idx, sentence in enumerate(sentences):
            # Find best matching source for each sentence
            best_match = None
            best_score = 0

            for source in sources:
                score = self._calculate_similarity(sentence, source.get("content", ""))
                if score > best_score:
                    best_score = score
                    best_match = source

            if best_match and best_score > self.min_confidence:
                citation_points.append({
                    "sentence": sentence,
                    "sentence_idx": sent_idx,
                    "source": best_match,
                    "confidence": best_score
                })

        return citation_points

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitting (can be improved with NLP)
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        # Simple word overlap similarity (can be improved with embeddings)
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        # Jaccard similarity
        similarity = len(intersection) / len(union) if union else 0

        # Boost for longer matches
        if len(intersection) > 3:
            similarity *= 1.2

        return min(1.0, similarity)

    def _create_citation(
        self,
        citation_point: Dict[str, Any],
        sources: List[Dict[str, Any]]
    ) -> Optional[Citation]:
        """
        Create a citation from a citation point.

        Args:
            citation_point: Citation point data
            sources: Source documents

        Returns:
            Citation object or None
        """
        source = citation_point["source"]

        # Generate citation ID
        citation_id = self._generate_citation_id(
            citation_point["sentence"],
            source.get("id", "")
        )

        # Create citation
        citation = Citation(
            citation_id=citation_id,
            source_id=source.get("id", "unknown"),
            source_title=source.get("title", "Untitled"),
            content=citation_point["sentence"],
            url=source.get("url"),
            author=source.get("author"),
            date=source.get("date"),
            page=source.get("page"),
            section=source.get("section"),
            confidence=citation_point["confidence"],
            metadata={
                "sentence_idx": citation_point["sentence_idx"],
                "source_metadata": source.get("metadata", {})
            }
        )

        # Store citation
        self.citations[citation_id] = citation
        self.source_index.setdefault(citation.source_id, []).append(citation_id)

        return citation

    def _generate_citation_id(self, content: str, source_id: str) -> str:
        """Generate unique citation ID."""
        hash_input = f"{content}:{source_id}"
        hash_obj = hashlib.md5(hash_input.encode())
        return hash_obj.hexdigest()[:8]

    def _deduplicate_citations(self, citations: List[Citation]) -> List[Citation]:
        """Remove duplicate citations."""
        seen_sources = set()
        unique = []

        for citation in citations:
            if citation.source_id not in seen_sources:
                unique.append(citation)
                seen_sources.add(citation.source_id)
            else:
                # Merge metadata if same source
                for existing in unique:
                    if existing.source_id == citation.source_id:
                        existing.confidence = max(existing.confidence, citation.confidence)
                        break

        return unique

    def _rank_citations(self, citations: List[Citation]) -> List[Citation]:
        """Rank citations by importance."""
        # Sort by confidence and relevance
        return sorted(citations, key=lambda c: c.confidence, reverse=True)

    def format_citations(
        self,
        citations: List[Citation],
        style: str = "apa"
    ) -> str:
        """
        Format citations as reference list.

        Args:
            citations: List of citations
            style: Citation style

        Returns:
            Formatted reference list
        """
        references = []
        for i, citation in enumerate(citations, 1):
            ref = citation.format_reference(style)
            references.append(f"{i}. {ref}")

        return "\n".join(references)

    def get_citation_stats(self) -> Dict[str, Any]:
        """Get citation statistics."""
        total_citations = len(self.citations)
        unique_sources = len(self.source_index)

        # Calculate average confidence
        avg_confidence = 0
        if total_citations > 0:
            avg_confidence = sum(c.confidence for c in self.citations.values()) / total_citations

        # Find most cited source
        most_cited_source = None
        max_citations = 0
        for source_id, citation_ids in self.source_index.items():
            if len(citation_ids) > max_citations:
                max_citations = len(citation_ids)
                most_cited_source = source_id

        return {
            "total_citations": total_citations,
            "unique_sources": unique_sources,
            "average_confidence": avg_confidence,
            "most_cited_source": most_cited_source,
            "citations_per_source": {
                source_id: len(citation_ids)
                for source_id, citation_ids in self.source_index.items()
            }
        }


class AutoCitationInjector:
    """
    Automatically injects citations into generated text.

    Analyzes text and sources to add citations where appropriate.
    """

    def __init__(self, tracker: Optional[CitationTracker] = None):
        """
        Initialize auto-injector.

        Args:
            tracker: Citation tracker to use
        """
        self.tracker = tracker or CitationTracker()

    def inject_citations(
        self,
        text: str,
        sources: List[Dict[str, Any]],
        style: str = "inline"
    ) -> str:
        """
        Inject citations into text.

        Args:
            text: Text to add citations to
            sources: Source documents
            style: Citation style

        Returns:
            Text with citations
        """
        # Extract citations
        cited_response = self.tracker.extract_citations(text, sources)

        if style == "inline":
            # Add inline citations after relevant sentences
            sentences = self.tracker._split_sentences(text)
            result = []

            for i, sentence in enumerate(sentences):
                # Find citations for this sentence
                sentence_citations = [
                    c for c in cited_response.citations
                    if c.metadata.get("sentence_idx") == i
                ]

                if sentence_citations:
                    # Add citations
                    cite_text = " ".join(
                        c.format_inline("number") for c in sentence_citations
                    )
                    result.append(f"{sentence} {cite_text}")
                else:
                    result.append(sentence)

            return ". ".join(result)

        elif style == "footnote":
            # Add as footnotes
            return cited_response.format_with_citations(
                inline_style="number",
                include_references=True
            )

        else:
            return text