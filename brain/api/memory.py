"""Memory service API endpoints."""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

from brain.api.auth import require_api_key
from brain.memory import (
    get_memory_manager,
    MemoryTier,
    MemoryEntry,
    MemoryQuery,
    MemoryConfig
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Global memory manager
memory_manager = get_memory_manager()


class MemoryStoreRequest(BaseModel):
    """Request to store a memory."""
    content: str = Field(..., description="Memory content")
    tier: str = Field("short_term", description="Memory tier (short_term, working, long_term, episodic)")
    agent_id: Optional[str] = Field(None, description="Associated agent ID")
    conversation_id: Optional[str] = Field(None, description="Associated conversation ID")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    tags: Optional[List[str]] = Field(default_factory=list, description="Memory tags")


class MemoryStoreResponse(BaseModel):
    """Response from memory storage."""
    memory_id: str
    tier: str
    timestamp: str
    status: str = "stored"


class MemoryRecallRequest(BaseModel):
    """Request to recall memories."""
    query: str = Field(..., description="Search query")
    tier: str = Field("all", description="Memory tier to search")
    agent_id: Optional[str] = Field(None, description="Filter by agent ID")
    conversation_id: Optional[str] = Field(None, description="Filter by conversation ID")
    limit: int = Field(10, description="Maximum results")
    min_relevance: float = Field(0.0, description="Minimum relevance score")
    tags: Optional[List[str]] = Field(default_factory=list, description="Filter by tags")


class MemoryRecallResponse(BaseModel):
    """Response from memory recall."""
    memories: List[Dict[str, Any]]
    total_results: int
    query_tier: str


class MemoryConsolidateRequest(BaseModel):
    """Request to consolidate memories."""
    agent_id: Optional[str] = Field(None, description="Agent to consolidate (None for all)")
    force: bool = Field(False, description="Force consolidation regardless of age")


class MemoryClearRequest(BaseModel):
    """Request to clear memories."""
    tier: Optional[str] = Field(None, description="Tier to clear (None for all)")
    agent_id: Optional[str] = Field(None, description="Agent memories to clear")


@router.post("/v1/memory/store", dependencies=[Depends(require_api_key)])
async def store_memory(request: MemoryStoreRequest) -> MemoryStoreResponse:
    """
    Store a memory in the specified tier.

    Memory tiers:
    - short_term: Recent conversation buffer
    - working: Current task context
    - long_term: Persistent vector storage
    - episodic: Structured events and experiences
    """
    try:
        # Convert tier string to enum
        tier = MemoryTier(request.tier)

        # Store memory
        memory = await memory_manager.store(
            content=request.content,
            tier=tier,
            agent_id=request.agent_id,
            conversation_id=request.conversation_id,
            metadata=request.metadata,
            tags=request.tags
        )

        return MemoryStoreResponse(
            memory_id=memory.id,
            tier=tier.value,
            timestamp=memory.timestamp.isoformat()
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {request.tier}")
    except Exception as e:
        logger.error(f"Memory store error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/memory/recall", dependencies=[Depends(require_api_key)])
async def recall_memories(request: MemoryRecallRequest) -> MemoryRecallResponse:
    """
    Recall relevant memories based on query.

    Searches across specified memory tiers and returns
    memories ranked by relevance.
    """
    try:
        # Convert tier string to enum
        tier = MemoryTier(request.tier) if request.tier != "all" else MemoryTier.ALL

        # Create memory query
        query = MemoryQuery(
            query=request.query,
            tier=tier,
            agent_id=request.agent_id,
            conversation_id=request.conversation_id,
            limit=request.limit,
            min_relevance=request.min_relevance,
            tags=request.tags
        )

        # Recall memories
        memories = await memory_manager.recall(query)

        return MemoryRecallResponse(
            memories=[m.to_dict() for m in memories],
            total_results=len(memories),
            query_tier=tier.value
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {request.tier}")
    except Exception as e:
        logger.error(f"Memory recall error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/memory/consolidate", dependencies=[Depends(require_api_key)])
async def consolidate_memories(
    request: MemoryConsolidateRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Consolidate memories from short-term to long-term storage.

    This process:
    - Identifies old short-term memories
    - Generates embeddings if needed
    - Moves them to long-term storage
    - Frees up short-term capacity
    """
    try:
        # Run consolidation in background
        background_tasks.add_task(
            memory_manager.consolidate,
            agent_id=request.agent_id,
            force=request.force
        )

        return {
            "status": "consolidation_started",
            "agent_id": request.agent_id,
            "force": request.force
        }

    except Exception as e:
        logger.error(f"Consolidation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/v1/memory/clear", dependencies=[Depends(require_api_key)])
async def clear_memories(request: MemoryClearRequest) -> Dict[str, Any]:
    """
    Clear memories from specified tier.

    Use with caution as this permanently removes memories.
    """
    try:
        # Convert tier string to enum if specified
        tier = MemoryTier(request.tier) if request.tier else None

        # Clear memories
        await memory_manager.clear(tier=tier, agent_id=request.agent_id)

        return {
            "status": "cleared",
            "tier": request.tier,
            "agent_id": request.agent_id
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {request.tier}")
    except Exception as e:
        logger.error(f"Memory clear error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/memory/stats", dependencies=[Depends(require_api_key)])
async def get_memory_stats() -> Dict[str, Any]:
    """
    Get memory system statistics.

    Returns:
    - Total memories across all tiers
    - Tier distribution
    - Consolidation and retrieval counts
    """
    try:
        stats = memory_manager.get_statistics()
        return stats

    except Exception as e:
        logger.error(f"Stats retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/memory/search/{agent_id}", dependencies=[Depends(require_api_key)])
async def search_agent_memories(
    agent_id: str,
    query: str,
    tier: str = "all",
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search memories for a specific agent.

    Convenience endpoint for agent-specific memory retrieval.
    """
    try:
        # Convert tier
        memory_tier = MemoryTier(tier) if tier != "all" else MemoryTier.ALL

        # Create query
        memory_query = MemoryQuery(
            query=query,
            tier=memory_tier,
            agent_id=agent_id,
            limit=limit
        )

        # Search
        memories = await memory_manager.recall(memory_query)

        return {
            "agent_id": agent_id,
            "memories": [m.to_dict() for m in memories],
            "count": len(memories)
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {e}")
    except Exception as e:
        logger.error(f"Agent memory search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/memory/batch/store", dependencies=[Depends(require_api_key)])
async def batch_store_memories(memories: List[MemoryStoreRequest]) -> Dict[str, Any]:
    """
    Store multiple memories at once.

    Useful for importing conversation history or bulk operations.
    """
    try:
        stored_ids = []

        for memory_req in memories:
            tier = MemoryTier(memory_req.tier)

            memory = await memory_manager.store(
                content=memory_req.content,
                tier=tier,
                agent_id=memory_req.agent_id,
                conversation_id=memory_req.conversation_id,
                metadata=memory_req.metadata,
                tags=memory_req.tags
            )

            stored_ids.append(memory.id)

        return {
            "status": "stored",
            "count": len(stored_ids),
            "memory_ids": stored_ids
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid data: {e}")
    except Exception as e:
        logger.error(f"Batch store error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/memory/conversation/{conversation_id}", dependencies=[Depends(require_api_key)])
async def get_conversation_memories(
    conversation_id: str,
    tier: str = "short_term",
    limit: int = 50
) -> Dict[str, Any]:
    """
    Get all memories for a conversation.

    Useful for conversation history and context.
    """
    try:
        memory_tier = MemoryTier(tier)

        # Query for conversation
        query = MemoryQuery(
            query="",  # Empty query to get all
            tier=memory_tier,
            conversation_id=conversation_id,
            limit=limit
        )

        memories = await memory_manager.recall(query)

        return {
            "conversation_id": conversation_id,
            "memories": [m.to_dict() for m in memories],
            "count": len(memories),
            "tier": tier
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}")
    except Exception as e:
        logger.error(f"Conversation memory retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Initialize memory manager on module load
async def initialize_memory_system():
    """Initialize the memory system on startup."""
    await memory_manager.initialize()


async def shutdown_memory_system():
    """Shutdown memory system on application stop."""
    await memory_manager.shutdown()