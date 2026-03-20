"""Working memory for current task context."""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from brain.memory.memory_manager import MemoryEntry, MemoryTier

logger = logging.getLogger(__name__)


class WorkingMemory:
    """
    Working memory for active task context.

    Features:
    - Task-specific context storage
    - Priority-based retention
    - Quick access to relevant information
    - Auto-clear on task completion
    """

    def __init__(self, capacity: int = 5):
        """
        Initialize working memory.

        Args:
            capacity: Maximum items in working memory
        """
        self.capacity = capacity
        self.store: Dict[str, List[MemoryEntry]] = {}  # Per agent/task
        self.task_context: Dict[str, Dict[str, Any]] = {}

    def set_task_context(self, agent_id: str, context: Dict[str, Any]):
        """Set the current task context for an agent."""
        self.task_context[agent_id] = context

    def add_to_context(self, memory: MemoryEntry, agent_id: str):
        """Add memory to working context."""
        if agent_id not in self.store:
            self.store[agent_id] = []

        # Maintain capacity
        if len(self.store[agent_id]) >= self.capacity:
            self.store[agent_id].pop(0)

        self.store[agent_id].append(memory)

    def get_context(self, agent_id: str) -> List[MemoryEntry]:
        """Get current working context."""
        return self.store.get(agent_id, [])

    def clear_context(self, agent_id: str):
        """Clear working memory for an agent."""
        if agent_id in self.store:
            self.store[agent_id].clear()
        if agent_id in self.task_context:
            del self.task_context[agent_id]