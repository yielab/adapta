"""Episodic memory for structured events and experiences."""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import json

from brain.memory.memory_manager import MemoryEntry, MemoryTier

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """
    Episodic memory for structured agent experiences.

    Features:
    - Event-based storage
    - Temporal organization
    - Experience replay
    - Pattern recognition
    """

    def __init__(self, capacity: int = 1000):
        """
        Initialize episodic memory.

        Args:
            capacity: Maximum episodes to store
        """
        self.capacity = capacity
        self.episodes: Dict[str, List[MemoryEntry]] = {}  # Per agent
        self.event_patterns: Dict[str, int] = {}  # Track recurring patterns

    def record_episode(
        self,
        agent_id: str,
        event_type: str,
        context: Dict[str, Any],
        outcome: Optional[Dict[str, Any]] = None
    ) -> MemoryEntry:
        """
        Record a structured episode.

        Args:
            agent_id: Agent experiencing the episode
            event_type: Type of event
            context: Event context
            outcome: Event outcome/result

        Returns:
            Created episode memory
        """
        if agent_id not in self.episodes:
            self.episodes[agent_id] = []

        # Create episode entry
        episode = MemoryEntry(
            tier=MemoryTier.EPISODIC,
            content=f"Episode: {event_type}",
            agent_id=agent_id,
            metadata={
                "event_type": event_type,
                "context": context,
                "outcome": outcome,
                "timestamp": datetime.now().isoformat()
            },
            tags=[event_type, "episode"]
        )

        # Maintain capacity
        if len(self.episodes[agent_id]) >= self.capacity:
            self.episodes[agent_id].pop(0)

        self.episodes[agent_id].append(episode)

        # Track pattern
        pattern_key = f"{agent_id}:{event_type}"
        self.event_patterns[pattern_key] = self.event_patterns.get(pattern_key, 0) + 1

        return episode

    def get_similar_episodes(
        self,
        agent_id: str,
        event_type: str,
        limit: int = 5
    ) -> List[MemoryEntry]:
        """
        Get similar past episodes.

        Args:
            agent_id: Agent ID
            event_type: Event type to match
            limit: Maximum results

        Returns:
            Similar episodes
        """
        if agent_id not in self.episodes:
            return []

        similar = []
        for episode in self.episodes[agent_id]:
            if episode.metadata.get("event_type") == event_type:
                similar.append(episode)

        # Sort by recency
        similar.sort(key=lambda e: e.timestamp, reverse=True)
        return similar[:limit]

    def get_agent_history(
        self,
        agent_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[MemoryEntry]:
        """
        Get agent's episodic history.

        Args:
            agent_id: Agent ID
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Episodes in time range
        """
        if agent_id not in self.episodes:
            return []

        episodes = self.episodes[agent_id]

        if start_time or end_time:
            filtered = []
            for episode in episodes:
                if start_time and episode.timestamp < start_time:
                    continue
                if end_time and episode.timestamp > end_time:
                    continue
                filtered.append(episode)
            return filtered

        return episodes

    def identify_patterns(self, agent_id: str) -> Dict[str, Any]:
        """
        Identify patterns in agent's episodes.

        Args:
            agent_id: Agent ID

        Returns:
            Pattern analysis
        """
        patterns = {}

        # Count event types
        event_counts = {}
        for key, count in self.event_patterns.items():
            if key.startswith(f"{agent_id}:"):
                event_type = key.split(":", 1)[1]
                event_counts[event_type] = count

        patterns["event_frequency"] = event_counts

        # Analyze outcomes
        if agent_id in self.episodes:
            success_count = 0
            failure_count = 0

            for episode in self.episodes[agent_id]:
                outcome = episode.metadata.get("outcome", {})
                if outcome.get("success"):
                    success_count += 1
                elif outcome.get("error"):
                    failure_count += 1

            patterns["success_rate"] = success_count / max(len(self.episodes[agent_id]), 1)
            patterns["failure_rate"] = failure_count / max(len(self.episodes[agent_id]), 1)

        return patterns