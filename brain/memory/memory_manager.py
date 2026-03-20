"""
Memory Manager for coordinating multi-tier memory system.

This module orchestrates:
- Short-term memory (conversation buffer)
- Working memory (task context)
- Long-term memory (vector store)
- Episodic memory (structured events)
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import uuid
from collections import deque

logger = logging.getLogger(__name__)


class MemoryTier(Enum):
    """Memory tier types."""
    SHORT_TERM = "short_term"
    WORKING = "working"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    ALL = "all"  # Search all tiers


@dataclass
class MemoryEntry:
    """A single memory entry."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tier: MemoryTier = MemoryTier.SHORT_TERM
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None
    embedding: Optional[List[float]] = None
    relevance_score: float = 1.0
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "tier": self.tier.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
            "relevance_score": self.relevance_score,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "tags": self.tags
        }


@dataclass
class MemoryQuery:
    """Query for retrieving memories."""
    query: str
    tier: MemoryTier = MemoryTier.ALL
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None
    limit: int = 10
    time_range: Optional[Tuple[datetime, datetime]] = None
    tags: List[str] = field(default_factory=list)
    min_relevance: float = 0.0
    include_embeddings: bool = False


@dataclass
class MemoryConfig:
    """Configuration for memory system."""
    # Short-term memory
    short_term_capacity: int = 10  # Number of recent messages
    short_term_ttl_minutes: int = 30  # Time to live

    # Working memory
    working_capacity: int = 5  # Task context items
    working_ttl_minutes: int = 60  # Clear after task completion

    # Long-term memory
    long_term_capacity: int = 10000  # Max entries
    long_term_embedding_model: str = "all-MiniLM-L6-v2"
    long_term_similarity_threshold: float = 0.7

    # Episodic memory
    episodic_capacity: int = 1000  # Max episodes
    episodic_consolidation_interval: int = 300  # 5 minutes

    # General settings
    enable_auto_consolidation: bool = True
    consolidation_batch_size: int = 50
    memory_persistence_path: Optional[str] = None


class MemoryManager:
    """
    Coordinates multi-tier memory system for agents.

    Features:
    - Automatic memory routing based on type and importance
    - Cross-tier search capabilities
    - Memory consolidation and compression
    - Relevance-based retrieval
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        """
        Initialize memory manager.

        Args:
            config: Memory system configuration
        """
        self.config = config or MemoryConfig()

        # Initialize memory stores
        self.short_term_store: Dict[str, deque] = {}  # Per agent/conversation
        self.working_store: Dict[str, List[MemoryEntry]] = {}
        self.long_term_store: List[MemoryEntry] = []
        self.episodic_store: Dict[str, List[MemoryEntry]] = {}

        # Consolidation task
        self.consolidation_task: Optional[asyncio.Task] = None

        # Statistics
        self.stats = {
            "total_memories": 0,
            "consolidations": 0,
            "retrievals": 0,
            "tier_distribution": {tier.value: 0 for tier in MemoryTier}
        }

    async def initialize(self):
        """Initialize memory system and start background tasks."""
        logger.info("Initializing memory system...")

        # Load persisted memories if configured
        if self.config.memory_persistence_path:
            await self._load_persisted_memories()

        # Start consolidation task if enabled
        if self.config.enable_auto_consolidation:
            self.consolidation_task = asyncio.create_task(
                self._consolidation_loop()
            )

        logger.info("Memory system initialized")

    async def shutdown(self):
        """Shutdown memory system and save state."""
        logger.info("Shutting down memory system...")

        # Stop consolidation task
        if self.consolidation_task:
            self.consolidation_task.cancel()
            try:
                await self.consolidation_task
            except asyncio.CancelledError:
                pass

        # Persist memories if configured
        if self.config.memory_persistence_path:
            await self._persist_memories()

        logger.info("Memory system shutdown complete")

    async def store(
        self,
        content: str,
        tier: MemoryTier,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> MemoryEntry:
        """
        Store a memory in the specified tier.

        Args:
            content: Memory content
            tier: Target memory tier
            agent_id: Associated agent ID
            conversation_id: Associated conversation ID
            metadata: Additional metadata
            tags: Memory tags

        Returns:
            Created memory entry
        """
        # Create memory entry
        memory = MemoryEntry(
            tier=tier,
            content=content,
            agent_id=agent_id,
            conversation_id=conversation_id,
            metadata=metadata or {},
            tags=tags or []
        )

        # Route to appropriate tier
        if tier == MemoryTier.SHORT_TERM:
            await self._store_short_term(memory)
        elif tier == MemoryTier.WORKING:
            await self._store_working(memory)
        elif tier == MemoryTier.LONG_TERM:
            await self._store_long_term(memory)
        elif tier == MemoryTier.EPISODIC:
            await self._store_episodic(memory)

        # Update statistics
        self.stats["total_memories"] += 1
        self.stats["tier_distribution"][tier.value] += 1

        logger.debug(f"Stored memory {memory.id} in {tier.value}")
        return memory

    async def recall(
        self,
        query: Union[str, MemoryQuery],
        **kwargs
    ) -> List[MemoryEntry]:
        """
        Recall memories based on query.

        Args:
            query: Search query or MemoryQuery object
            **kwargs: Additional query parameters

        Returns:
            List of relevant memories
        """
        # Convert string to MemoryQuery if needed
        if isinstance(query, str):
            memory_query = MemoryQuery(query=query, **kwargs)
        else:
            memory_query = query

        # Search appropriate tiers
        results = []

        if memory_query.tier in [MemoryTier.ALL, MemoryTier.SHORT_TERM]:
            results.extend(await self._search_short_term(memory_query))

        if memory_query.tier in [MemoryTier.ALL, MemoryTier.WORKING]:
            results.extend(await self._search_working(memory_query))

        if memory_query.tier in [MemoryTier.ALL, MemoryTier.LONG_TERM]:
            results.extend(await self._search_long_term(memory_query))

        if memory_query.tier in [MemoryTier.ALL, MemoryTier.EPISODIC]:
            results.extend(await self._search_episodic(memory_query))

        # Sort by relevance and apply limit
        results.sort(key=lambda m: m.relevance_score, reverse=True)
        results = results[:memory_query.limit]

        # Update access statistics
        for memory in results:
            memory.access_count += 1
            memory.last_accessed = datetime.now()

        self.stats["retrievals"] += 1

        return results

    async def consolidate(
        self,
        agent_id: Optional[str] = None,
        force: bool = False
    ) -> int:
        """
        Consolidate memories from short-term to long-term.

        Args:
            agent_id: Specific agent to consolidate (None for all)
            force: Force consolidation regardless of thresholds

        Returns:
            Number of memories consolidated
        """
        consolidated_count = 0

        # Get candidates for consolidation
        candidates = await self._get_consolidation_candidates(agent_id, force)

        for memory in candidates:
            # Generate embedding if moving to long-term
            if not memory.embedding:
                memory.embedding = await self._generate_embedding(memory.content)

            # Move to long-term storage
            await self._store_long_term(memory)

            # Remove from short-term
            await self._remove_from_short_term(memory)

            consolidated_count += 1

        self.stats["consolidations"] += 1

        logger.info(f"Consolidated {consolidated_count} memories")
        return consolidated_count

    async def _store_short_term(self, memory: MemoryEntry):
        """Store in short-term memory."""
        key = memory.conversation_id or memory.agent_id or "global"

        if key not in self.short_term_store:
            self.short_term_store[key] = deque(maxlen=self.config.short_term_capacity)

        self.short_term_store[key].append(memory)

    async def _store_working(self, memory: MemoryEntry):
        """Store in working memory."""
        key = memory.agent_id or "global"

        if key not in self.working_store:
            self.working_store[key] = []

        # Maintain capacity limit
        if len(self.working_store[key]) >= self.config.working_capacity:
            self.working_store[key].pop(0)

        self.working_store[key].append(memory)

    async def _store_long_term(self, memory: MemoryEntry):
        """Store in long-term memory."""
        # Generate embedding if not present
        if not memory.embedding:
            memory.embedding = await self._generate_embedding(memory.content)

        # Check capacity
        if len(self.long_term_store) >= self.config.long_term_capacity:
            # Remove least relevant/oldest
            self.long_term_store.sort(key=lambda m: (m.relevance_score, m.timestamp))
            self.long_term_store.pop(0)

        self.long_term_store.append(memory)

    async def _store_episodic(self, memory: MemoryEntry):
        """Store in episodic memory."""
        key = memory.agent_id or "global"

        if key not in self.episodic_store:
            self.episodic_store[key] = []

        # Maintain capacity limit
        if len(self.episodic_store[key]) >= self.config.episodic_capacity:
            self.episodic_store[key].pop(0)

        self.episodic_store[key].append(memory)

    async def _search_short_term(self, query: MemoryQuery) -> List[MemoryEntry]:
        """Search short-term memory."""
        results = []

        # Determine which stores to search
        keys_to_search = []
        if query.conversation_id:
            keys_to_search.append(query.conversation_id)
        elif query.agent_id:
            keys_to_search.append(query.agent_id)
        else:
            keys_to_search = list(self.short_term_store.keys())

        for key in keys_to_search:
            if key in self.short_term_store:
                for memory in self.short_term_store[key]:
                    # Apply filters
                    if query.time_range:
                        if not (query.time_range[0] <= memory.timestamp <= query.time_range[1]):
                            continue

                    if query.tags:
                        if not any(tag in memory.tags for tag in query.tags):
                            continue

                    # Simple text matching for relevance
                    if query.query.lower() in memory.content.lower():
                        memory.relevance_score = 1.0
                    else:
                        memory.relevance_score = 0.5

                    if memory.relevance_score >= query.min_relevance:
                        results.append(memory)

        return results

    async def _search_working(self, query: MemoryQuery) -> List[MemoryEntry]:
        """Search working memory."""
        results = []
        key = query.agent_id or "global"

        if key in self.working_store:
            for memory in self.working_store[key]:
                # Apply filters similar to short-term
                if query.time_range:
                    if not (query.time_range[0] <= memory.timestamp <= query.time_range[1]):
                        continue

                if query.tags:
                    if not any(tag in memory.tags for tag in query.tags):
                        continue

                # Relevance scoring
                if query.query.lower() in memory.content.lower():
                    memory.relevance_score = 0.9
                else:
                    memory.relevance_score = 0.4

                if memory.relevance_score >= query.min_relevance:
                    results.append(memory)

        return results

    async def _search_long_term(self, query: MemoryQuery) -> List[MemoryEntry]:
        """Search long-term memory using embeddings."""
        if not self.long_term_store:
            return []

        # Generate query embedding
        query_embedding = await self._generate_embedding(query.query)

        results = []
        for memory in self.long_term_store:
            # Apply filters
            if query.agent_id and memory.agent_id != query.agent_id:
                continue

            if query.time_range:
                if not (query.time_range[0] <= memory.timestamp <= query.time_range[1]):
                    continue

            if query.tags:
                if not any(tag in memory.tags for tag in query.tags):
                    continue

            # Calculate similarity if embeddings available
            if memory.embedding and query_embedding:
                similarity = await self._calculate_similarity(
                    query_embedding,
                    memory.embedding
                )
                memory.relevance_score = similarity
            else:
                # Fallback to text matching
                if query.query.lower() in memory.content.lower():
                    memory.relevance_score = 0.6
                else:
                    memory.relevance_score = 0.2

            if memory.relevance_score >= query.min_relevance:
                results.append(memory)

        return results

    async def _search_episodic(self, query: MemoryQuery) -> List[MemoryEntry]:
        """Search episodic memory."""
        results = []
        key = query.agent_id or "global"

        if key in self.episodic_store:
            for memory in self.episodic_store[key]:
                # Episodes are usually structured events
                # Search in metadata and content
                if query.query.lower() in json.dumps(memory.metadata).lower():
                    memory.relevance_score = 0.8
                elif query.query.lower() in memory.content.lower():
                    memory.relevance_score = 0.7
                else:
                    memory.relevance_score = 0.3

                if memory.relevance_score >= query.min_relevance:
                    results.append(memory)

        return results

    async def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text.

        TODO: Integrate with actual embedding model.
        For now, returns a placeholder.
        """
        # Placeholder - integrate with sentence-transformers or similar
        import hashlib
        hash_obj = hashlib.md5(text.encode())
        hash_hex = hash_obj.hexdigest()
        # Convert to simple vector (placeholder)
        embedding = [float(int(hash_hex[i:i+2], 16)) / 255.0 for i in range(0, 32, 2)]
        return embedding

    async def _calculate_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Similarity score (0-1)
        """
        # Simple dot product for normalized vectors
        if len(embedding1) != len(embedding2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))

        # Normalize to 0-1 range
        # For proper cosine similarity, would need vector magnitudes
        return min(max(dot_product / len(embedding1), 0.0), 1.0)

    async def _get_consolidation_candidates(
        self,
        agent_id: Optional[str] = None,
        force: bool = False
    ) -> List[MemoryEntry]:
        """Get memories ready for consolidation."""
        candidates = []
        now = datetime.now()

        for key, memories in self.short_term_store.items():
            # Filter by agent if specified
            if agent_id and key != agent_id:
                continue

            for memory in memories:
                # Check if memory is old enough
                age_minutes = (now - memory.timestamp).total_seconds() / 60

                if force or age_minutes > self.config.short_term_ttl_minutes:
                    candidates.append(memory)

        return candidates

    async def _remove_from_short_term(self, memory: MemoryEntry):
        """Remove memory from short-term storage."""
        key = memory.conversation_id or memory.agent_id or "global"

        if key in self.short_term_store:
            try:
                self.short_term_store[key].remove(memory)
            except ValueError:
                pass  # Memory not in deque

    async def _consolidation_loop(self):
        """Background task for automatic memory consolidation."""
        while True:
            try:
                await asyncio.sleep(self.config.episodic_consolidation_interval)
                await self.consolidate()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consolidation error: {e}")

    async def _load_persisted_memories(self):
        """Load memories from persistent storage."""
        # TODO: Implement persistence loading
        pass

    async def _persist_memories(self):
        """Save memories to persistent storage."""
        # TODO: Implement persistence saving
        pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get memory system statistics.

        Returns:
            Statistics dictionary
        """
        return {
            **self.stats,
            "tier_sizes": {
                "short_term": sum(len(m) for m in self.short_term_store.values()),
                "working": sum(len(m) for m in self.working_store.values()),
                "long_term": len(self.long_term_store),
                "episodic": sum(len(m) for m in self.episodic_store.values())
            }
        }

    async def clear(
        self,
        tier: Optional[MemoryTier] = None,
        agent_id: Optional[str] = None
    ):
        """
        Clear memories.

        Args:
            tier: Specific tier to clear (None for all)
            agent_id: Specific agent memories to clear (None for all)
        """
        if tier in [None, MemoryTier.ALL, MemoryTier.SHORT_TERM]:
            if agent_id:
                if agent_id in self.short_term_store:
                    self.short_term_store[agent_id].clear()
            else:
                self.short_term_store.clear()

        if tier in [None, MemoryTier.ALL, MemoryTier.WORKING]:
            if agent_id:
                if agent_id in self.working_store:
                    self.working_store[agent_id].clear()
            else:
                self.working_store.clear()

        if tier in [None, MemoryTier.ALL, MemoryTier.LONG_TERM]:
            if agent_id:
                self.long_term_store = [
                    m for m in self.long_term_store
                    if m.agent_id != agent_id
                ]
            else:
                self.long_term_store.clear()

        if tier in [None, MemoryTier.ALL, MemoryTier.EPISODIC]:
            if agent_id:
                if agent_id in self.episodic_store:
                    self.episodic_store[agent_id].clear()
            else:
                self.episodic_store.clear()

        logger.info(f"Cleared memories - tier: {tier}, agent: {agent_id}")


# Global memory manager instance
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """
    Get the global memory manager instance.

    Returns:
        MemoryManager instance
    """
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager