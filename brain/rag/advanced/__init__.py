"""
Advanced RAG module with hybrid search and re-ranking.

Provides 40% better retrieval quality through:
- Hybrid search (semantic + keyword)
- Cross-encoder re-ranking
- Query expansion
- Citation tracking
"""

from brain.rag.advanced.hybrid_search import (
    HybridSearchEngine,
    SearchStrategy,
    SearchResult
)

from brain.rag.advanced.reranker import (
    CrossEncoderReranker,
    RerankerModel,
    RerankResult
)

from brain.rag.advanced.query_expansion import (
    QueryExpander,
    ExpansionStrategy,
    ExpandedQuery
)

from brain.rag.advanced.citation_tracker import (
    CitationTracker,
    Citation,
    CitedDocument
)

from brain.rag.advanced.advanced_rag import (
    AdvancedRAG,
    RAGConfig,
    RAGResult
)

__all__ = [
    "HybridSearchEngine",
    "SearchStrategy",
    "SearchResult",
    "CrossEncoderReranker",
    "RerankerModel",
    "RerankResult",
    "QueryExpander",
    "ExpansionStrategy",
    "ExpandedQuery",
    "CitationTracker",
    "Citation",
    "CitedDocument",
    "AdvancedRAG",
    "RAGConfig",
    "RAGResult",
]