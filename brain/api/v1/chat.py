"""
OpenAI-compatible /v1/chat/completions endpoint.
Authenticates via scoped project API key (Authorization: Bearer brn_...).
Routes to RAG or base+adapter serving depending on the endpoint type.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import ApiKey, Endpoint, EndpointStatus, Project
from brain.db.session import get_db
from brain.domain.errors import InvalidRequest, NotFound, Unauthorized
from brain.services.auth import verify_api_key
from brain.services.chat import chat, chat_stream
from brain.services.usage import record_usage

router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------------
# OpenAI-compatible request / response schemas
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str                          # endpoint slug
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stream: Optional[bool] = False


# ---------------------------------------------------------------------------
# Key auth dependency
# ---------------------------------------------------------------------------

async def _resolve_endpoint(request: Request, db: AsyncSession = Depends(get_db)) -> tuple[Endpoint, Project]:
    """
    Validate scoped API key from Authorization header.
    Returns (endpoint, project).
    """
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise Unauthorized(message="Bearer token required")
    raw_key = auth[7:]

    # Find matching key by prefix
    prefix = raw_key[:8]
    result = await db.execute(select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.is_active.is_(True)))
    keys = result.scalars().all()

    matched: Optional[ApiKey] = None
    for k in keys:
        if verify_api_key(raw_key, k.key_hash):
            matched = k
            break

    if not matched:
        raise Unauthorized(message="Invalid or revoked API key")

    # Update last_used
    matched.last_used_at = datetime.now(timezone.utc)

    ep_result = await db.execute(select(Endpoint).where(Endpoint.id == matched.endpoint_id))
    endpoint = ep_result.scalar_one_or_none()
    if not endpoint or endpoint.status != EndpointStatus.active:
        raise InvalidRequest(message="Endpoint is not active")

    proj_result = await db.execute(select(Project).where(Project.id == endpoint.project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise NotFound(message="Project not found")

    return endpoint, project


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@router.post("/chat/completions")
async def chat_completions(
    request_body: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    auth: tuple = Depends(_resolve_endpoint),
    db: AsyncSession = Depends(get_db),
):
    endpoint, project = auth

    messages = [{"role": m.role, "content": m.content} for m in request_body.messages]

    # RAG projects: inject project_id so retrieval runs
    project_id_for_rag = str(project.id) if project.type.value == "rag" else None

    if request_body.stream:
        return StreamingResponse(
            chat_stream(
                model_name=endpoint.base_model,
                messages=messages,
                temperature=request_body.temperature,
                max_tokens=request_body.max_tokens,
                project_id=project_id_for_rag,
                endpoint_id=endpoint.id,
            ),
            media_type="text/event-stream",
        )
    else:
        result = await chat(
            model_name=endpoint.base_model,
            messages=messages,
            temperature=request_body.temperature,
            max_tokens=request_body.max_tokens,
            top_p=request_body.top_p,
            project_id=project_id_for_rag,
        )
        # Meter usage off the response path (§3.2).
        u = result.get("usage", {})
        background_tasks.add_task(
            record_usage,
            endpoint.id,
            int(u.get("prompt_tokens", 0)),
            int(u.get("completion_tokens", 0)),
        )
        return result
