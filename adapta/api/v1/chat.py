"""
OpenAI-compatible /v1/chat/completions endpoint.
Authenticates via scoped project API key (Authorization: Bearer adp_...).
Serving composes the project's artifacts: retrieval when documents are indexed,
the trained adapter when the endpoint has one — or both together.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.db.models import ApiKey, Collection, Endpoint, EndpointStatus, Project
from adapta.db.session import get_db
from adapta.domain.errors import Forbidden, InvalidRequest, NotFound, Unauthorized
from adapta.services.auth import verify_api_key
from adapta.services.chat import chat, chat_stream, has_image_parts
from adapta.services.usage import record_usage

router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------------
# OpenAI-compatible request / response schemas
# ---------------------------------------------------------------------------


class TextPart(BaseModel):
    type: Literal["text"]
    text: str


class ImageUrl(BaseModel):
    url: str  # data:image/...;base64, only — remote URLs rejected in the service


class ImagePart(BaseModel):
    type: Literal["image_url"]
    image_url: ImageUrl


ContentPart = Union[TextPart, ImagePart]


class ChatMessage(BaseModel):
    role: str
    # Plain text, or the OpenAI content-parts array (§V4: image_url parts on
    # vision endpoints; data: URLs only).
    content: Union[str, List[ContentPart]]


class ChatCompletionRequest(BaseModel):
    model: str  # endpoint slug
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stream: Optional[bool] = False


# ---------------------------------------------------------------------------
# Key auth dependency
# ---------------------------------------------------------------------------


async def _resolve_endpoint(
    request: Request, db: AsyncSession = Depends(get_db)
) -> tuple[Endpoint, Project]:
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
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.is_active.is_(True))
    )
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

    # Key-scoping: the `model` field must match the endpoint's slug. This makes
    # the scoping explicit — a key for endpoint A cannot drive endpoint B, even if
    # the caller sends B's slug. (Without this, the key would silently serve A.)
    if request_body.model != endpoint.slug:
        raise Forbidden(
            message=f"API key is not authorized for model '{request_body.model}'",
            internal_detail=f"key for endpoint slug={endpoint.slug!r} but model={request_body.model!r}",
        )

    # Plain dicts for the service; content-parts models dump to OpenAI-shaped
    # dicts (the same shape the multimodal chat handler consumes).
    messages = [
        {
            "role": m.role,
            "content": (
                m.content if isinstance(m.content, str) else [p.model_dump() for p in m.content]
            ),
        }
        for m in request_body.messages
    ]

    # Streaming with images is rejected HERE, before a StreamingResponse exists —
    # raised inside the stream generator it would surface as a broken body, not
    # a typed 422 (§V4).
    if request_body.stream and has_image_parts(messages):
        raise InvalidRequest(
            message="Streaming with image content is not supported; send stream=false."
        )

    # Serving composes the project's artifacts rather than switching on its type:
    # retrieval runs whenever the project has indexed chunks, and the adapter
    # (set at endpoint creation only for fine-tune projects, A3.1) is applied
    # whenever present. A fine-tune project with indexed documents gets both —
    # facts from its documents (with citations), behavior from its adapter.
    col_result = await db.execute(select(Collection).where(Collection.project_id == project.id))
    collection = col_result.scalar_one_or_none()
    has_knowledge = collection is not None and (collection.num_chunks or 0) > 0
    project_id_for_rag = str(project.id) if has_knowledge else None

    adapter_path = endpoint.adapter_path

    if request_body.stream:
        return StreamingResponse(
            chat_stream(
                model_name=endpoint.base_model,
                messages=messages,
                temperature=request_body.temperature,
                max_tokens=request_body.max_tokens,
                project_id=project_id_for_rag,
                endpoint_id=endpoint.id,
                adapter_path=adapter_path,
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
            adapter_path=adapter_path,
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
