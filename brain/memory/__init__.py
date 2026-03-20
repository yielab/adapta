"""
Memory module for Brain platform.

Provides multi-tier memory system for agents:
- Short-term memory: Recent conversations
- Working memory: Current task context
- Long-term memory: Persistent vector storage
- Episodic memory: Structured events and experiences
"""

from brain.memory.memory_manager import (
    MemoryManager,
    MemoryTier,
    MemoryEntry,
    MemoryQuery,
    MemoryConfig,
    get_memory_manager
)

from brain.memory.short_term import ShortTermMemory
from brain.memory.working import WorkingMemory
from brain.memory.long_term import LongTermMemory
from brain.memory.episodic import EpisodicMemory

__all__ = [
    "MemoryManager",
    "MemoryTier",
    "MemoryEntry",
    "MemoryQuery",
    "MemoryConfig",
    "get_memory_manager",
    "ShortTermMemory",
    "WorkingMemory",
    "LongTermMemory",
    "EpisodicMemory",
]