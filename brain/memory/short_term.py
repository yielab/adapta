"""Short-term memory implementation for recent conversations."""

from typing import List, Dict, Any, Optional
from collections import deque
from datetime import datetime, timedelta
import logging

from brain.memory.memory_manager import MemoryEntry, MemoryTier

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """
    Short-term memory for recent conversation history.

    Features:
    - FIFO queue with configurable capacity
    - TTL-based expiration
    - Fast retrieval of recent messages
    - Automatic overflow to consolidation
    """

    def __init__(self, capacity: int = 10, ttl_minutes: int = 30):
        """
        Initialize short-term memory.

        Args:
            capacity: Maximum number of messages to retain
            ttl_minutes: Time-to-live for messages
        """
        self.capacity = capacity
        self.ttl_minutes = ttl_minutes
        self.store: Dict[str, deque] = {}  # Per conversation/agent

    def add(self, memory: MemoryEntry, key: str):
        """Add a memory to short-term storage."""
        if key not in self.store:
            self.store[key] = deque(maxlen=self.capacity)

        self.store[key].append(memory)

    def get_recent(self, key: str, count: int = 10) -> List[MemoryEntry]:
        """Get recent memories for a key."""
        if key not in self.store:
            return []

        memories = list(self.store[key])
        return memories[-count:]

    def expire_old(self) -> List[MemoryEntry]:
        """Remove and return expired memories."""
        expired = []
        now = datetime.now()

        for key in self.store:
            for memory in list(self.store[key]):
                age_minutes = (now - memory.timestamp).total_seconds() / 60
                if age_minutes > self.ttl_minutes:
                    self.store[key].remove(memory)
                    expired.append(memory)

        return expired