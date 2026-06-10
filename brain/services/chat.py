"""
Real ChatService — single serving path for both RAG and base (LoRA) endpoints.
Replaces the mock in the deleted unified_router.py.

Does NOT touch brain/core/inference.py or brain/core/model_manager.py internals.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import AsyncIterator, List, Optional

from brain.config import settings
from brain.core import inference_engine, model_manager
from brain.core.inference import InferenceRequest, InferenceResponse, Message
from brain.domain.errors import DomainError, InferenceFailed, InvalidRequest, ModelNotFound, Timeout
from brain.services.rag import get_rag_service


async def _retrieve(rag_service, project_id: str, query: str, top_k: int) -> list:
    """RAG retrieval off the event loop with a timeout (A4.12). A hung Chroma must
    degrade to a typed 504, not block every chat request — and the blocking client
    call must not run on the event loop thread."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(rag_service.retrieve, project_id, query, top_k=top_k),
            timeout=settings.rag_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise Timeout(message="Document retrieval timed out", internal_detail=str(exc)) from exc

logger = logging.getLogger(__name__)

# Minimum tokens reserved for the answer when fitting a prompt to the context
# window (A4.3): we never let the prompt consume so much of n_ctx that there's no
# room left to generate.
_MIN_GEN_RESERVE = 16


async def _load_model(model_name: str, adapter_path: Optional[str] = None):
    try:
        return await model_manager.ensure_model_loaded(model_name, adapter_path=adapter_path)
    except Exception as exc:
        raise ModelNotFound(
            message=f"Model '{model_name}' could not be loaded",
            internal_detail=str(exc),
        ) from exc


def _build_system(base_system: Optional[str], rag_service, rag_chunks: list) -> Optional[str]:
    """Assemble the system prompt, injecting the RAG context block when present.
    Centralizes the wording shared by the streaming and non-streaming paths."""
    base = base_system or ""
    if not rag_chunks or rag_service is None:
        return base or None
    context_block = rag_service.build_context_block(rag_chunks)
    combined = (
        f"{base}\n\nUse the following context to answer. "
        f"Cite sources by their [N] number.\n\n{context_block}"
    ).strip()
    return combined or None


def _fit_context(*, count_fn, n_ctx: int, base_system: Optional[str], rag_service,
                 rag_chunks: list, max_tokens: int):
    """Fit the prompt into the model's context window (A4.3).

    llama-cpp silently truncates an over-long prompt — and since RAG context is
    injected BEFORE the user's question, the question is what gets cut. So instead
    we: drop the lowest-relevance RAG chunks first (retrieval returns them
    most-relevant-first), then, if the prompt still doesn't leave room for an
    answer even with zero chunks, reject with a typed 422 rather than truncate
    silently. Finally clamp ``max_tokens`` to what's left of n_ctx.

    ``count_fn(system_prompt) -> int`` returns the real tokenized prompt length.
    Returns ``(system_prompt, kept_chunks, capped_max_tokens)``.
    """
    chunks = list(rag_chunks)
    while True:
        system_prompt = _build_system(base_system, rag_service, chunks)
        n_prompt = count_fn(system_prompt)
        if n_prompt + min(_MIN_GEN_RESERVE, max_tokens) <= n_ctx:
            return system_prompt, chunks, max(1, min(max_tokens, n_ctx - n_prompt))
        if chunks:
            chunks.pop()  # drop the least-relevant retrieved chunk and retry
            continue
        raise InvalidRequest(
            message=(
                f"Prompt is too long ({n_prompt} tokens) for the model's {n_ctx}-token "
                "context window — even with no retrieved context there's no room to "
                "answer. Shorten your input."
            )
        )


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
    # Fine-tune serving (A3.1): GGUF LoRA applied on top of the base model
    adapter_path: Optional[str] = None,
) -> dict:
    """
    Non-streaming chat completion.
    Returns an OpenAI-compatible response dict with optional citations.
    """
    temperature = temperature if temperature is not None else settings.temperature
    # Cap the client's max_tokens at the configured ceiling (A4.3) — an uncapped
    # request (e.g. max_tokens=999999) could OOM or hang the engine.
    max_tokens = min(max_tokens or settings.max_tokens, settings.max_tokens)
    top_p = top_p or settings.top_p

    rag_chunks: list = []
    rag_service = None
    if project_id:
        rag_service = get_rag_service()
        query = messages[-1].get("content", "") if messages else ""
        rag_chunks = await _retrieve(rag_service, project_id, query, top_k_rag or settings.rag_top_k)

    inference_messages = [Message(role=m["role"], content=m["content"]) for m in messages]

    model_obj = await _load_model(model_name, adapter_path=adapter_path)
    lock = model_manager.get_inference_lock(model_name, adapter_path)

    # Fit prompt + answer into the model's context window before dispatch.
    full_system, rag_chunks, max_tokens = _fit_context(
        count_fn=lambda sp: inference_engine.count_prompt_tokens(model_obj, inference_messages, sp),
        n_ctx=inference_engine.context_size(model_obj),
        base_system=system_prompt,
        rag_service=rag_service,
        rag_chunks=rag_chunks,
        max_tokens=max_tokens,
    )

    req = InferenceRequest(
        messages=inference_messages,
        model_name=model_name,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stream=False,
        system_prompt=full_system,
        adapter_path=adapter_path,
    )
    try:
        response: InferenceResponse = await inference_engine.generate(model_obj, req, lock=lock)
    except DomainError:
        raise  # Timeout (504) and other typed errors keep their status — don't mask as 500.
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
    endpoint_id: Optional[str] = None,
    adapter_path: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Streaming chat — yields SSE-formatted strings.
    RAG context is injected before streaming starts (non-streaming retrieval).
    """
    import json

    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = min(max_tokens or settings.max_tokens, settings.max_tokens)  # cap (A4.3)

    rag_chunks: list = []
    rag_service = None
    if project_id:
        rag_service = get_rag_service()
        query = messages[-1].get("content", "") if messages else ""
        rag_chunks = await _retrieve(rag_service, project_id, query, top_k_rag or settings.rag_top_k)

    inference_messages = [Message(role=m["role"], content=m["content"]) for m in messages]

    model_obj = await _load_model(model_name, adapter_path=adapter_path)
    lock = model_manager.get_inference_lock(model_name, adapter_path)

    # Fit prompt + answer into the context window before streaming (A4.3).
    full_system, rag_chunks, max_tokens = _fit_context(
        count_fn=lambda sp: inference_engine.count_prompt_tokens(model_obj, inference_messages, sp),
        n_ctx=inference_engine.context_size(model_obj),
        base_system=system_prompt,
        rag_service=rag_service,
        rag_chunks=rag_chunks,
        max_tokens=max_tokens,
    )

    req = InferenceRequest(
        messages=inference_messages,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        system_prompt=full_system,
        adapter_path=adapter_path,
    )
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

    # Count the prompt tokens once up front (A4.11) — the same real tokenizer used
    # for the context-fit check — so streaming usage is no longer recorded with
    # prompt_tokens=0 (which systematically undercounted every streaming consumer).
    prompt_tokens = inference_engine.count_prompt_tokens(model_obj, inference_messages, full_system)

    # The engine yields one model token per iteration, so counting yields is the
    # real completion-token count — no need for the old ~4-chars/token estimate.
    completion_tokens = 0
    try:
        async for token in inference_engine.generate_stream(model_obj, req, lock=lock):
            completion_tokens += 1
            chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_name,
                "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"

        finish = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
        yield f"data: {json.dumps(finish)}\n\n"
        yield "data: [DONE]\n\n"

        # Meter streaming usage once the stream completes (off the client path —
        # this runs after the last byte is yielded). §3.2 / A4.11.
        if endpoint_id:
            from brain.services.usage import record_usage
            await record_usage(endpoint_id, prompt_tokens, completion_tokens)

    except DomainError:
        raise  # Timeout (504) and other typed errors keep their status — don't mask as 500.
    except Exception as exc:
        raise InferenceFailed(message="Streaming inference failed", internal_detail=str(exc)) from exc
