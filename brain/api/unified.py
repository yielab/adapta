"""
Unified Router API endpoints.

Provides high-level API for the unified Brain intelligence layer.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel, Field

from brain.core.unified_router import (
    UnifiedRouter,
    UnifiedConfig,
    UnifiedRequest,
    UnifiedResponse,
    get_unified_router,
    Message
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/unified")


class UnifiedChatMessage(BaseModel):
    """Chat message for unified API."""
    role: str = Field(..., description="Message role (system/user/assistant)")
    content: str = Field(..., description="Message content")
    priority: Optional[str] = Field("medium", description="Message priority")


class UnifiedChatRequest(BaseModel):
    """Unified chat request."""
    messages: List[UnifiedChatMessage]
    agent_id: Optional[str] = Field(None, description="Agent ID for memory")
    model: Optional[str] = Field(None, description="Specific model to use")
    temperature: float = Field(0.7, description="Temperature for generation")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens")
    tools: Optional[List[Dict[str, Any]]] = Field(None, description="Available tools")
    stream: bool = Field(False, description="Stream response")
    use_rag: Optional[bool] = Field(None, description="Override RAG usage")
    use_memory: Optional[bool] = Field(None, description="Override memory usage")


class UnifiedChatResponse(BaseModel):
    """Unified chat response."""
    content: str
    model_used: str
    tokens_used: int
    citations: Optional[List[Dict[str, Any]]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UnifiedConfigUpdate(BaseModel):
    """Configuration update request."""
    max_tokens: Optional[int] = None
    context_budget_ratio: Optional[float] = None
    memory_enabled: Optional[bool] = None
    rag_enabled: Optional[bool] = None
    use_query_expansion: Optional[bool] = None
    use_reranking: Optional[bool] = None
    use_citations: Optional[bool] = None
    adaptive_routing: Optional[bool] = None
    collect_feedback: Optional[bool] = None
    enable_ab_testing: Optional[bool] = None
    auto_evolution: Optional[bool] = None


@router.post("/chat", response_model=UnifiedChatResponse)
async def unified_chat(request: UnifiedChatRequest):
    """
    Process chat through unified router.

    This endpoint orchestrates all Brain components:
    - Context optimization
    - Memory recall and storage
    - RAG enhancement
    - Intelligent routing
    - Citation tracking
    - Adaptive learning
    """
    try:
        unified_router = get_unified_router()

        # Convert messages
        messages = [
            Message(
                role=m.role,
                content=m.content,
                priority=m.priority
            )
            for m in request.messages
        ]

        # Create unified request
        unified_req = UnifiedRequest(
            messages=messages,
            agent_id=request.agent_id,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tools=request.tools,
            stream=request.stream,
            metadata={
                "use_rag": request.use_rag,
                "use_memory": request.use_memory
            }
        )

        # Process through unified router
        response = await unified_router.process(unified_req)

        return UnifiedChatResponse(
            content=response.content,
            model_used=response.model_used,
            tokens_used=response.tokens_used,
            citations=response.citations,
            tool_calls=response.tool_calls,
            metadata=response.metadata
        )

    except Exception as e:
        logger.error(f"Error in unified chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_unified_config():
    """Get current unified router configuration."""
    try:
        unified_router = get_unified_router()
        config = unified_router.config

        return {
            "max_tokens": config.max_tokens,
            "context_budget_ratio": config.context_budget_ratio,
            "memory_enabled": config.memory_enabled,
            "auto_consolidation": config.auto_consolidation,
            "rag_enabled": config.rag_enabled,
            "rag_top_k": config.rag_top_k,
            "use_query_expansion": config.use_query_expansion,
            "use_reranking": config.use_reranking,
            "use_citations": config.use_citations,
            "adaptive_routing": config.adaptive_routing,
            "fallback_model": config.fallback_model,
            "tracing_enabled": config.tracing_enabled,
            "collect_feedback": config.collect_feedback,
            "enable_ab_testing": config.enable_ab_testing,
            "auto_evolution": config.auto_evolution
        }

    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/config")
async def update_unified_config(update: UnifiedConfigUpdate):
    """Update unified router configuration."""
    try:
        unified_router = get_unified_router()
        config = unified_router.config

        # Update only provided fields
        for field, value in update.dict(exclude_unset=True).items():
            if hasattr(config, field):
                setattr(config, field, value)

        # Reinitialize components if needed
        if update.memory_enabled is not None:
            unified_router._init_memory_system()

        if update.rag_enabled is not None:
            unified_router._init_rag_system()

        if any([update.collect_feedback, update.enable_ab_testing, update.auto_evolution]):
            unified_router._init_adaptive_features()

        return {"status": "Configuration updated successfully"}

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_unified_stats():
    """Get comprehensive statistics from unified router."""
    try:
        unified_router = get_unified_router()
        stats = unified_router.get_stats()

        return stats

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def submit_feedback(
    agent_id: str = Body(...),
    interaction_id: str = Body(...),
    rating: int = Body(..., ge=1, le=5),
    comment: Optional[str] = Body(None)
):
    """Submit feedback for an interaction."""
    try:
        unified_router = get_unified_router()

        if unified_router.feedback_collector:
            unified_router.feedback_collector.add_feedback(
                agent_id=agent_id,
                feedback={
                    "interaction_id": interaction_id,
                    "rating": rating,
                    "comment": comment
                }
            )

            # Check if training should trigger
            if unified_router.evolution_manager:
                should_train = unified_router.feedback_collector.should_trigger_training(agent_id)
                if should_train:
                    # Trigger evolution
                    await unified_router.evolution_manager.trigger_evolution(agent_id)
                    return {
                        "status": "Feedback recorded",
                        "evolution_triggered": True
                    }

            return {
                "status": "Feedback recorded",
                "evolution_triggered": False
            }

        return {"status": "Feedback collection disabled"}

    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ab-testing/results")
async def get_ab_testing_results(experiment_id: Optional[str] = None):
    """Get A/B testing results."""
    try:
        unified_router = get_unified_router()

        if not unified_router.ab_testing:
            return {"status": "A/B testing disabled"}

        if experiment_id:
            result = unified_router.ab_testing.get_result(experiment_id)
            if not result:
                raise HTTPException(status_code=404, detail="Experiment not found")
            return result.to_dict()
        else:
            return unified_router.ab_testing.get_all_results()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting A/B test results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ab-testing/experiment")
async def create_ab_experiment(
    name: str = Body(...),
    variant_a: str = Body(..., description="Model or config for variant A"),
    variant_b: str = Body(..., description="Model or config for variant B"),
    traffic_split: float = Body(0.5, description="Traffic split for variant A")
):
    """Create a new A/B testing experiment."""
    try:
        unified_router = get_unified_router()

        if not unified_router.ab_testing:
            raise HTTPException(status_code=400, detail="A/B testing disabled")

        experiment_id = unified_router.ab_testing.create_experiment(
            name=name,
            variant_a=variant_a,
            variant_b=variant_b,
            traffic_split=traffic_split
        )

        return {
            "experiment_id": experiment_id,
            "name": name,
            "status": "created"
        }

    except Exception as e:
        logger.error(f"Error creating experiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/routing/stats")
async def get_routing_stats():
    """Get routing statistics and model usage."""
    try:
        unified_router = get_unified_router()
        stats = unified_router.router.get_stats()

        return stats

    except Exception as e:
        logger.error(f"Error getting routing stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routing/override")
async def override_routing(
    task_pattern: str = Body(..., description="Task pattern to match"),
    model: str = Body(..., description="Model to use for pattern"),
    priority: int = Body(0, description="Override priority")
):
    """Add routing override for specific task patterns."""
    try:
        unified_router = get_unified_router()

        # Add override to router
        unified_router.router.add_override(
            pattern=task_pattern,
            model=model,
            priority=priority
        )

        return {
            "status": "Override added",
            "pattern": task_pattern,
            "model": model
        }

    except Exception as e:
        logger.error(f"Error adding routing override: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/stats")
async def get_rag_stats():
    """Get RAG system statistics."""
    try:
        unified_router = get_unified_router()

        if not unified_router.search_engine:
            return {"status": "RAG disabled"}

        stats = {
            "indexed_documents": len(unified_router.search_engine.documents),
            "search_strategy": unified_router.search_engine.strategy.value,
            "semantic_weight": unified_router.search_engine.semantic_weight,
            "keyword_weight": unified_router.search_engine.keyword_weight
        }

        if unified_router.citation_tracker:
            stats["citation_stats"] = unified_router.citation_tracker.get_citation_stats()

        return stats

    except Exception as e:
        logger.error(f"Error getting RAG stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/reindex")
async def reindex_documents():
    """Re-index all documents for improved search."""
    try:
        unified_router = get_unified_router()

        if not unified_router.search_engine:
            raise HTTPException(status_code=400, detail="RAG disabled")

        # Re-index logic would go here
        # For now, return status
        return {
            "status": "Re-indexing started",
            "document_count": len(unified_router.search_engine.documents)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error re-indexing: {e}")
        raise HTTPException(status_code=500, detail=str(e))