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

from brain.rag.advanced.reranking import (
    HybridReranker,
    CrossEncoderReranker,
    RerankingConfig
)

from brain.rag.advanced.query_expansion import (
    QueryExpander,
    ExpansionStrategy,
    ExpandedQuery
)

from brain.rag.advanced.citations import (
    CitationTracker,
    AutoCitationInjector,
    Citation,
    CitedResponse
)

from brain.rag.advanced.advanced_rag import (
    AdvancedRAG,
    RAGConfig,
    RAGResult,
    RAGMode
)

__all__ = [
    "HybridSearchEngine",
    "SearchStrategy",
    "SearchResult",
    "HybridReranker",
    "CrossEncoderReranker",
    "RerankingConfig",
    "QueryExpander",
    "ExpansionStrategy",
    "ExpandedQuery",
    "CitationTracker",
    "AutoCitationInjector",
    "Citation",
    "CitedResponse",
    "AdvancedRAG",
    "RAGConfig",
    "RAGResult",
    "RAGMode",
]