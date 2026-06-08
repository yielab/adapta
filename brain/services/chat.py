"""
Real ChatService — single serving path for both RAG and base (LoRA) endpoints.
Replaces the mock in the deleted unified_router.py.

Does NOT touch brain/core/inference.py or brain/core/model_manager.py internals.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import AsyncIterator, List, Optional

from brain.config import settings
from brain.core import inference_engine, model_manager
from brain.core.inference import InferenceRequest, InferenceResponse, Message
from brain.domain.errors import InferenceFailed, ModelNotFound
from brain.services.rag import get_rag_service

logger = logging.getLogger(__name__)


async def _load_model(model_name: str):
    try:
        return await model_manager.ensure_model_loaded(model_name)
    except Exception as exc:
        raise ModelNotFound(
            message=f"Model '{model_name}' could not be loaded",
            internal_detail=str(exc),
        ) from exc


async def chat(
    *,
    model_name: str,
    messages: List[dict],
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    stream: bool = False,
    # RAG
    project_id: Optional[str] = None,
    top_k_rag: Optional[int] = None,
) -> dict:
    """
    Non-streaming chat completion.
    Returns an OpenAI-compatible response dict with optional citations.
    """
    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = max_tokens or settings.max_tokens
    top_p = top_p or settings.top_p

    rag_chunks = []
    full_system = system_prompt or ""

    if project_id:
        rag_service = get_rag_service()
        query = messages[-1].get("content", "") if messages else ""
        rag_chunks = rag_service.retrieve(project_id, query, top_k=top_k_rag or settings.rag_top_k)
        if rag_chunks:
            context_block = rag_service.build_context_block(rag_chunks)
            full_system = (
                f"{full_system}\n\nUse the following context to answer. "
                f"Cite sources by their [N] number.\n\n{context_block}"
            ).strip()

    inference_messages = [Message(role=m["role"], content=m["content"]) for m in messages]

    req = InferenceRequest(
        messages=inference_messages,
        model_name=model_name,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stream=False,
        system_prompt=full_system or None,
    )

    model_obj = await _load_model(model_name)
    try:
        response: InferenceResponse = await inference_engine.generate(model_obj, req)
    except Exception as exc:
        raise InferenceFailed(
            message="Inference failed",
            internal_detail=str(exc),
        ) from exc

    result = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response.content},
                "finish_reason": response.finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
        },
    }

    if rag_chunks:
        rag_service = get_rag_service()
        result["citations"] = rag_service.format_citations(rag_chunks)

    return result


async def chat_stream(
    *,
    model_name: str,
    messages: List[dict],
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    project_id: Optional[str] = None,
    top_k_rag: Optional[int] = None,
) -> AsyncIterator[str]:
    """
    Streaming chat — yields SSE-formatted strings.
    RAG context is injected before streaming starts (non-streaming retrieval).
    """
    import json

    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = max_tokens or settings.max_tokens

    full_system = system_prompt or ""
    if project_id:
        rag_service = get_rag_service()
        query = messages[-1].get("content", "") if messages else ""
        rag_chunks = rag_service.retrieve(project_id, query, top_k=top_k_rag or settings.rag_top_k)
        if rag_chunks:
            context_block = rag_service.build_context_block(rag_chunks)
            full_system = (
                f"{full_system}\n\nUse the following context to answer. "
                f"Cite sources by their [N] number.\n\n{context_block}"
            ).strip()

    inference_messages = [Message(role=m["role"], content=m["content"]) for m in messages]
    req = InferenceRequest(
        messages=inference_messages,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        system_prompt=full_system or None,
    )

    model_obj = await _load_model(model_name)
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

    completion_chars = 0
    try:
        async for token in inference_engine.generate_stream(model_obj, req):
            completion_chars += len(token)
            chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_name,
                "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"

        # Rough token estimate: ~4 chars per token
        completion_tokens_est = max(1, completion_chars // 4)
        finish = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": completion_tokens_est, "total_tokens": completion_tokens_est},
        }
        yield f"data: {json.dumps(finish)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as exc:
        raise InferenceFailed(message="Streaming inference failed", internal_detail=str(exc)) from exc
