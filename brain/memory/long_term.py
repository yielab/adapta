"""Long-term memory with vector storage."""

from typing import List, Dict, Any, Optional
import logging
import numpy as np

from brain.memory.memory_manager import MemoryEntry, MemoryTier

logger = logging.getLogger(__name__)


class LongTermMemory:
    """
    Long-term memory with embedding-based retrieval.

    Features:
    - Vector similarity search
    - Persistent storage
    - Semantic retrieval
    - Large capacity storage
    """

    def __init__(self, capacity: int = 10000, similarity_threshold: float = 0.7):
        """
        Initialize long-term memory.

        Args:
            capacity: Maximum memories to store
            similarity_threshold: Minimum similarity for retrieval
        """
        self.capacity = capacity
        self.similarity_threshold = similarity_threshold
        self.store: List[MemoryEntry] = []
        self.embeddings: List[np.ndarray] = []

    def add(self, memory: MemoryEntry):
        """Add memory to long-term storage."""
        # Check capacity
        if len(self.store) >= self.capacity:
            # Remove oldest/least relevant
            self.store.pop(0)
            if self.embeddings:
                self.embeddings.pop(0)

        self.store.append(memory)

        # Store embedding if available
        if memory.embedding:
            self.embeddings.append(np.array(memory.embedding))

    def search_by_similarity(
        self,
        query_embedding: List[float],
        limit: int = 10
    ) -> List[MemoryEntry]:
        """
        Search memories by embedding similarity.

        Args:
            query_embedding: Query vector
            limit: Maximum results

        Returns:
            Similar memories ranked by relevance
        """
        if not self.embeddings:
            return []

        query_vec = np.array(query_embedding)
        similarities = []

        for i, embedding in enumerate(self.embeddings):
            # Cosine similarity
            similarity = np.dot(query_vec, embedding) / (
                np.linalg.norm(query_vec) * np.linalg.norm(embedding)
            )
            if similarity >= self.similarity_threshold:
                similarities.append((i, similarity))

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Get top memories
        results = []
        for idx, sim in similarities[:limit]:
            memory = self.store[idx]
            memory.relevance_score = sim
            results.append(memory)

        return results

    def search_by_text(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """
        Fallback text-based search.

        Args:
            query: Search text
            limit: Maximum results

        Returns:
            Matching memories
        """
        results = []

        for memory in self.store:
            if query.lower() in memory.content.lower():
                memory.relevance_score = 0.8
                results.append(memory)

        return results[:limit]