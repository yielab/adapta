"""Context management API endpoints."""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from brain.core.context_manager import ContextManager, MessagePriority
from brain.api.auth import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter()

# Store context managers per conversation ID
context_managers: Dict[str, ContextManager] = {}


class ContextMessage(BaseModel):
    """Message for context management."""
    role: str = Field(..., description="Message role (system/user/assistant)")
    content: str = Field(..., description="Message content")
    priority: Optional[str] = Field(None, description="Message priority")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ContextManageRequest(BaseModel):
    """Request to manage context."""
    conversation_id: str = Field(..., description="Unique conversation identifier")
    messages: List[ContextMessage] = Field(..., description="Messages to add to context")
    model_name: Optional[str] = Field("gpt-3.5-turbo", description="Model name for token counting")
    max_tokens: Optional[int] = Field(None, description="Maximum context tokens")
    optimize: bool = Field(True, description="Whether to optimize context")
    preserve_recent: int = Field(5, description="Number of recent messages to preserve")
    summarize_old: bool = Field(True, description="Whether to summarize old messages")


class ContextManageResponse(BaseModel):
    """Response from context management."""
    conversation_id: str
    optimized_messages: List[Dict[str, Any]]
    token_usage: Dict[str, int]
    messages_removed: int = 0
    messages_summarized: int = 0


class ContextSummarizeRequest(BaseModel):
    """Request to summarize messages."""
    messages: List[ContextMessage]
    target_tokens: int = Field(200, description="Target token count for summary")


class ContextSummarizeResponse(BaseModel):
    """Response from summarization."""
    summary: str
    original_tokens: int
    summary_tokens: int


class ContextStatsRequest(BaseModel):
    """Request for context statistics."""
    conversation_id: str


class ContextStatsResponse(BaseModel):
    """Context statistics response."""
    conversation_id: str
    token_usage: Dict[str, int]
    message_count: int
    has_context: bool


@router.post("/v1/context/manage", dependencies=[Depends(require_api_key)])
async def manage_context(request: ContextManageRequest) -> ContextManageResponse:
    """
    Manage conversation context to optimize token usage.

    This endpoint:
    - Adds new messages to the context
    - Optimizes the context to fit within token limits
    - Summarizes old messages if needed
    - Returns the optimized message list
    """
    try:
        # Get or create context manager for this conversation
        if request.conversation_id not in context_managers:
            context_managers[request.conversation_id] = ContextManager(
                model_name=request.model_name,
                max_tokens=request.max_tokens
            )

        ctx_mgr = context_managers[request.conversation_id]

        # Add new messages to context
        for msg in request.messages:
            priority = None
            if msg.priority:
                try:
                    priority = MessagePriority[msg.priority.upper()]
                except KeyError:
                    logger.warning(f"Invalid priority: {msg.priority}")

            ctx_mgr.add_message(
                role=msg.role,
                content=msg.content,
                priority=priority,
                metadata=msg.metadata
            )

        # Get initial token usage
        initial_usage = ctx_mgr.get_token_usage()
        initial_message_count = initial_usage["message_count"]

        # Optimize context if requested
        if request.optimize:
            optimized_messages = ctx_mgr.optimize_context(
                preserve_recent=request.preserve_recent,
                summarize_old=request.summarize_old
            )
        else:
            # Just return messages as-is
            optimized_messages = [msg.to_dict() for msg in ctx_mgr.messages]

        # Get final token usage
        final_usage = ctx_mgr.get_token_usage()

        # Calculate statistics
        messages_removed = max(0, initial_message_count - len(optimized_messages))
        messages_summarized = final_usage["summarized_count"]

        return ContextManageResponse(
            conversation_id=request.conversation_id,
            optimized_messages=optimized_messages,
            token_usage=final_usage,
            messages_removed=messages_removed,
            messages_summarized=messages_summarized
        )

    except Exception as e:
        logger.error(f"Context management error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/context/summarize", dependencies=[Depends(require_api_key)])
async def summarize_context(request: ContextSummarizeRequest) -> ContextSummarizeResponse:
    """
    Summarize a list of messages to reduce token count.

    Useful for:
    - Summarizing conversation history
    - Creating context for new sessions
    - Reducing token usage
    """
    try:
        # Create temporary context manager for token counting
        temp_mgr = ContextManager()

        # Convert messages to Message objects
        messages = []
        original_tokens = 0

        for msg in request.messages:
            m = temp_mgr.add_message(
                role=msg.role,
                content=msg.content,
                metadata=msg.metadata
            )
            messages.append(m)
            original_tokens += m.tokens

        # Summarize messages
        summary = temp_mgr.summarize_messages(messages, request.target_tokens)
        summary_tokens = temp_mgr.count_tokens(summary)

        return ContextSummarizeResponse(
            summary=summary,
            original_tokens=original_tokens,
            summary_tokens=summary_tokens
        )

    except Exception as e:
        logger.error(f"Summarization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/context/stats", dependencies=[Depends(require_api_key)])
async def get_context_stats(conversation_id: str) -> ContextStatsResponse:
    """
    Get token usage statistics for a conversation.

    Returns:
    - Token counts by message type
    - Available tokens
    - Budget allocation
    """
    if conversation_id not in context_managers:
        return ContextStatsResponse(
            conversation_id=conversation_id,
            token_usage={},
            message_count=0,
            has_context=False
        )

    ctx_mgr = context_managers[conversation_id]
    token_usage = ctx_mgr.get_token_usage()

    return ContextStatsResponse(
        conversation_id=conversation_id,
        token_usage=token_usage,
        message_count=token_usage.get("message_count", 0),
        has_context=True
    )


@router.delete("/v1/context/{conversation_id}", dependencies=[Depends(require_api_key)])
async def clear_context(conversation_id: str) -> Dict[str, Any]:
    """
    Clear the context for a conversation.

    This removes all stored messages and resets the context manager.
    """
    if conversation_id in context_managers:
        del context_managers[conversation_id]
        return {
            "conversation_id": conversation_id,
            "status": "cleared"
        }

    return {
        "conversation_id": conversation_id,
        "status": "not_found"
    }


@router.post("/v1/context/{conversation_id}/export", dependencies=[Depends(require_api_key)])
async def export_context(conversation_id: str) -> Dict[str, Any]:
    """
    Export the full context state for a conversation.

    Useful for:
    - Backing up conversations
    - Transferring context between sessions
    - Debugging token usage
    """
    if conversation_id not in context_managers:
        raise HTTPException(status_code=404, detail="Conversation not found")

    ctx_mgr = context_managers[conversation_id]
    return ctx_mgr.export_context()


@router.post("/v1/context/{conversation_id}/import", dependencies=[Depends(require_api_key)])
async def import_context(conversation_id: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Import a previously exported context state.

    This allows resuming conversations from a saved state.
    """
    try:
        # Create new context manager
        ctx_mgr = ContextManager()
        ctx_mgr.import_context(context_data)

        # Store it
        context_managers[conversation_id] = ctx_mgr

        return {
            "conversation_id": conversation_id,
            "status": "imported",
            "message_count": len(ctx_mgr.messages),
            "token_usage": ctx_mgr.get_token_usage()
        }

    except Exception as e:
        logger.error(f"Context import error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/v1/context/conversations", dependencies=[Depends(require_api_key)])
async def list_conversations() -> Dict[str, Any]:
    """
    List all active conversations with context managers.

    Returns basic stats for each conversation.
    """
    conversations = []

    for conv_id, ctx_mgr in context_managers.items():
        usage = ctx_mgr.get_token_usage()
        conversations.append({
            "conversation_id": conv_id,
            "message_count": usage["message_count"],
            "total_tokens": usage["total_tokens"],
            "available_tokens": usage["available_tokens"]
        })

    return {
        "conversations": conversations,
        "total_conversations": len(conversations)
    }