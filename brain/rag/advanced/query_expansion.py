"""
Query expansion for improved search coverage.

Expands user queries with synonyms, related terms, and reformulations.
"""

import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from enum import Enum
import re

logger = logging.getLogger(__name__)


class ExpansionStrategy(Enum):
    """Query expansion strategies."""
    SYNONYM = "synonym"
    SEMANTIC = "semantic"
    REFORMULATION = "reformulation"
    HYBRID = "hybrid"
    ADAPTIVE = "adaptive"  # Automatically choose best strategy


@dataclass
class ExpandedQuery:
    """Expanded query with multiple variations."""
    original: str
    expansions: List[str]
    strategy: ExpansionStrategy
    metadata: Dict[str, Any]

    def get_all_queries(self) -> List[str]:
        """Get all query variations including original."""
        return [self.original] + self.expansions

    def get_unique_terms(self) -> Set[str]:
        """Get all unique terms across all variations."""
        terms = set()
        for query in self.get_all_queries():
            terms.update(query.lower().split())
        return terms


class QueryExpander:
    """
    Query expansion for improved retrieval.

    Features:
    - Synonym expansion
    - Semantic expansion
    - Query reformulation
    - Domain-specific expansion
    """

    def __init__(
        self,
        enable_synonyms: bool = True,
        enable_semantic: bool = True,
        enable_reformulation: bool = True,
        max_expansions: int = 5
    ):
        """
        Initialize query expander.

        Args:
            enable_synonyms: Enable synonym expansion
            enable_semantic: Enable semantic expansion
            enable_reformulation: Enable query reformulation
            max_expansions: Maximum number of expansions
        """
        self.enable_synonyms = enable_synonyms
        self.enable_semantic = enable_semantic
        self.enable_reformulation = enable_reformulation
        self.max_expansions = max_expansions

        # Initialize expansion databases
        self._init_synonym_db()
        self._init_semantic_patterns()
        self._init_reformulation_rules()

    def _init_synonym_db(self):
        """Initialize synonym database."""
        # Common synonyms for various domains
        self.synonyms = {
            # Programming
            "function": ["method", "procedure", "routine", "subroutine"],
            "variable": ["parameter", "argument", "field", "attribute"],
            "error": ["exception", "bug", "issue", "problem", "fault"],
            "fix": ["repair", "resolve", "patch", "correct", "debug"],
            "create": ["make", "build", "generate", "construct", "implement"],
            "delete": ["remove", "drop", "erase", "clear", "destroy"],
            "update": ["modify", "change", "alter", "edit", "revise"],
            "get": ["fetch", "retrieve", "obtain", "acquire", "read"],
            "set": ["assign", "configure", "define", "establish", "write"],

            # General
            "fast": ["quick", "rapid", "speedy", "swift"],
            "slow": ["sluggish", "delayed", "lagging"],
            "big": ["large", "huge", "massive", "enormous"],
            "small": ["tiny", "minor", "little", "compact"],
            "good": ["excellent", "great", "superior", "optimal"],
            "bad": ["poor", "inferior", "faulty", "suboptimal"],

            # Data/ML
            "train": ["fit", "learn", "tune"],
            "predict": ["infer", "classify", "forecast"],
            "model": ["algorithm", "network", "classifier"],
            "data": ["dataset", "samples", "examples", "records"],
            "feature": ["attribute", "characteristic", "dimension"],
            "accuracy": ["performance", "precision", "correctness"],
        }

    def _init_semantic_patterns(self):
        """Initialize semantic expansion patterns."""
        # Patterns for semantic expansion
        self.semantic_patterns = {
            "how to": ["tutorial", "guide", "steps to", "process of"],
            "what is": ["definition of", "meaning of", "explanation of"],
            "why does": ["reason for", "cause of", "purpose of"],
            "when to": ["best time to", "timing of", "schedule for"],
            "where to": ["location of", "place to", "site for"],
            "best practices": ["guidelines", "recommendations", "standards"],
            "troubleshoot": ["debug", "diagnose", "fix issues", "solve problems"],
            "optimize": ["improve", "enhance", "tune", "boost performance"],
            "configure": ["setup", "set up", "install", "initialize"],
            "integrate": ["connect", "combine", "merge", "interface with"],
        }

    def _init_reformulation_rules(self):
        """Initialize query reformulation rules."""
        self.reformulation_rules = [
            # Question to statement
            (r"^what is (.+)\?*$", r"\1 definition"),
            (r"^how to (.+)\?*$", r"\1 tutorial"),
            (r"^why (.+)\?*$", r"\1 reason"),

            # Add context
            (r"^(\w+) error$", r"\1 error solution"),
            (r"^(\w+) not working$", r"fix \1 issue"),
            (r"^(\w+) slow$", r"optimize \1 performance"),

            # Expand abbreviations
            (r"\bAPI\b", "Application Programming Interface"),
            (r"\bUI\b", "User Interface"),
            (r"\bDB\b", "Database"),
            (r"\bML\b", "Machine Learning"),
            (r"\bAI\b", "Artificial Intelligence"),
        ]

    def expand(
        self,
        query: str,
        strategy: ExpansionStrategy = ExpansionStrategy.HYBRID
    ) -> ExpandedQuery:
        """
        Expand a query.

        Args:
            query: Original query
            strategy: Expansion strategy

        Returns:
            Expanded query with variations
        """
        expansions = []
        metadata = {"strategy": strategy.value}

        if strategy == ExpansionStrategy.SYNONYM or strategy == ExpansionStrategy.HYBRID:
            if self.enable_synonyms:
                syn_expansions = self._expand_synonyms(query)
                expansions.extend(syn_expansions)
                metadata["synonym_count"] = len(syn_expansions)

        if strategy == ExpansionStrategy.SEMANTIC or strategy == ExpansionStrategy.HYBRID:
            if self.enable_semantic:
                sem_expansions = self._expand_semantic(query)
                expansions.extend(sem_expansions)
                metadata["semantic_count"] = len(sem_expansions)

        if strategy == ExpansionStrategy.REFORMULATION or strategy == ExpansionStrategy.HYBRID:
            if self.enable_reformulation:
                ref_expansions = self._reformulate_query(query)
                expansions.extend(ref_expansions)
                metadata["reformulation_count"] = len(ref_expansions)

        # Remove duplicates and limit expansions
        unique_expansions = []
        seen = {query.lower()}
        for exp in expansions:
            if exp.lower() not in seen:
                unique_expansions.append(exp)
                seen.add(exp.lower())
                if len(unique_expansions) >= self.max_expansions:
                    break

        return ExpandedQuery(
            original=query,
            expansions=unique_expansions,
            strategy=strategy,
            metadata=metadata
        )

    def _expand_synonyms(self, query: str) -> List[str]:
        """
        Expand query using synonyms.

        Args:
            query: Original query

        Returns:
            List of synonym-based expansions
        """
        expansions = []
        words = query.lower().split()

        # Find synonyms for each word
        for i, word in enumerate(words):
            if word in self.synonyms:
                for synonym in self.synonyms[word][:2]:  # Limit synonyms per word
                    # Create new query with synonym
                    new_words = words.copy()
                    new_words[i] = synonym
                    expansion = " ".join(new_words)
                    expansions.append(expansion)

        return expansions

    def _expand_semantic(self, query: str) -> List[str]:
        """
        Expand query using semantic patterns.

        Args:
            query: Original query

        Returns:
            List of semantic expansions
        """
        expansions = []
        query_lower = query.lower()

        # Check for pattern matches
        for pattern, alternatives in self.semantic_patterns.items():
            if pattern in query_lower:
                for alt in alternatives[:2]:  # Limit alternatives
                    expansion = query_lower.replace(pattern, alt)
                    if expansion != query_lower:
                        expansions.append(expansion)

        return expansions

    def _reformulate_query(self, query: str) -> List[str]:
        """
        Reformulate query using rules.

        Args:
            query: Original query

        Returns:
            List of reformulated queries
        """
        reformulations = []

        for pattern, replacement in self.reformulation_rules:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                reformulated = re.sub(pattern, replacement, query, flags=re.IGNORECASE)
                if reformulated != query:
                    reformulations.append(reformulated)

        return reformulations

    def expand_batch(
        self,
        queries: List[str],
        strategy: ExpansionStrategy = ExpansionStrategy.HYBRID
    ) -> List[ExpandedQuery]:
        """
        Expand multiple queries.

        Args:
            queries: List of queries
            strategy: Expansion strategy

        Returns:
            List of expanded queries
        """
        return [self.expand(q, strategy) for q in queries]


class DomainSpecificExpander(QueryExpander):
    """
    Domain-specific query expansion.

    Extends base expander with domain knowledge.
    """

    def __init__(
        self,
        domain: str = "general",
        **kwargs
    ):
        """
        Initialize domain-specific expander.

        Args:
            domain: Domain (e.g., "medical", "legal", "technical")
            **kwargs: Base expander arguments
        """
        super().__init__(**kwargs)
        self.domain = domain
        self._load_domain_knowledge()

    def _load_domain_knowledge(self):
        """Load domain-specific knowledge."""
        if self.domain == "technical":
            # Add technical synonyms
            self.synonyms.update({
                "deploy": ["release", "launch", "publish", "rollout"],
                "scale": ["expand", "grow", "increase capacity"],
                "cache": ["buffer", "store", "memory"],
                "latency": ["delay", "lag", "response time"],
                "throughput": ["bandwidth", "capacity", "rate"],
                "debug": ["troubleshoot", "diagnose", "trace"],
            })

        elif self.domain == "medical":
            # Add medical synonyms
            self.synonyms.update({
                "symptom": ["sign", "indication", "manifestation"],
                "treatment": ["therapy", "intervention", "remedy"],
                "diagnosis": ["assessment", "evaluation", "identification"],
                "patient": ["subject", "individual", "case"],
            })

        elif self.domain == "legal":
            # Add legal synonyms
            self.synonyms.update({
                "contract": ["agreement", "covenant", "pact"],
                "clause": ["provision", "article", "section"],
                "liability": ["responsibility", "obligation", "accountability"],
                "jurisdiction": ["authority", "domain", "territory"],
            })


class AdaptiveQueryExpander:
    """
    Adaptive query expansion based on context and feedback.

    Learns from user interactions to improve expansions.
    """

    def __init__(self, base_expander: Optional[QueryExpander] = None):
        """
        Initialize adaptive expander.

        Args:
            base_expander: Base expander to adapt
        """
        self.base_expander = base_expander or QueryExpander()
        self.expansion_history: Dict[str, List[str]] = {}
        self.successful_expansions: Dict[str, Set[str]] = {}
        self.failed_expansions: Dict[str, Set[str]] = {}

    def expand(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ExpandedQuery:
        """
        Adaptively expand query.

        Args:
            query: Original query
            context: Additional context

        Returns:
            Expanded query
        """
        # Get base expansions
        expanded = self.base_expander.expand(query)

        # Filter based on history
        if query in self.failed_expansions:
            failed = self.failed_expansions[query]
            expanded.expansions = [
                e for e in expanded.expansions
                if e not in failed
            ]

        # Add successful expansions
        if query in self.successful_expansions:
            successful = self.successful_expansions[query]
            for exp in successful:
                if exp not in expanded.expansions:
                    expanded.expansions.insert(0, exp)

        # Record in history
        self.expansion_history.setdefault(query, []).extend(expanded.expansions)

        return expanded

    def record_feedback(
        self,
        query: str,
        expansion: str,
        successful: bool
    ):
        """
        Record feedback on an expansion.

        Args:
            query: Original query
            expansion: The expansion used
            successful: Whether it was successful
        """
        if successful:
            self.successful_expansions.setdefault(query, set()).add(expansion)
            # Remove from failed if present
            if query in self.failed_expansions:
                self.failed_expansions[query].discard(expansion)
        else:
            self.failed_expansions.setdefault(query, set()).add(expansion)
            # Remove from successful if present
            if query in self.successful_expansions:
                self.successful_expansions[query].discard(expansion)