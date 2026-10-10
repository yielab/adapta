"""Single serving path for RAG and fine-tune (LoRA) endpoints.

Composes retrieval, context fitting, and inference.  Does NOT modify
``adapta/core/inference.py`` or ``adapta/core/model_manager.py`` internals —
those are called via their public interfaces only (hard constraint #1 in CLAUDE.md).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import AsyncIterator, List, Optional

from adapta.config import settings
from adapta.core import inference_engine, model_manager
from adapta.core.backends import get_backend
from adapta.core.inference import InferenceRequest, InferenceResponse, Message
from adapta.domain.errors import (
    DomainError,
    InferenceFailed,
    InvalidRequest,
    ModelNotFound,
    Timeout,
)
from adapta.services.rag import RetrievalFilters, apply_min_score, get_rag_service


async def _resolve_rag_top_k(project_id: Optional[str], top_k_rag: Optional[int]) -> int:
    """Effective RAG top-k for a request: explicit arg → org app-settings
    override (E1.6) → env default. Opens its own short-lived session (same
    self-contained pattern as `services/usage.py`'s `record_usage`) since
    `chat()`/`chat_stream()` don't otherwise take a DB session.
    """
    if top_k_rag is not None:
        return top_k_rag
    if not project_id:
        return settings.rag_top_k

    from sqlalchemy import select

    from adapta.db.models import Project
    from adapta.db.session import AsyncSessionLocal
    from adapta.services.app_settings import resolve_setting

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Project.team_id).where(Project.id == project_id))
        team_id = result.scalar_one_or_none()
        if team_id is None:
            return settings.rag_top_k
        return int(await resolve_setting(db, team_id, "rag_top_k"))


async def _retrieve(
    rag_service,
    project_id: str,
    query: str,
    top_k: int,
    filters: Optional[RetrievalFilters] = None,
) -> list:
    """RAG retrieval off the event loop with a timeout (A4.12). A hung Chroma must
    degrade to a typed 504, not block every chat request — and the blocking client
    call must not run on the event loop thread.

    Chunks under ``rag_min_score`` are dropped here (E3.5), not inside ``retrieve()``."""
    kwargs = {"filters": filters} if filters is not None else {}
    try:
        chunks = await asyncio.wait_for(
            asyncio.to_thread(rag_service.retrieve, project_id, query, top_k=top_k, **kwargs),
            timeout=settings.rag_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise Timeout(message="Document retrieval timed out", internal_detail=str(exc)) from exc
    return apply_min_score(chunks, settings.rag_min_score)


def split_client_system(messages: List[dict]) -> tuple[List[dict], Optional[str]]:
    """Pull `system` turns out of the conversation (E3.5).

    Returns (remaining turns, their text joined as one paragraph). They are merged into
    the single system message after the project prompt and RAG block, instead of landing
    as a later turn the model weighs less than the retrieved context.
    """
    turns = [m for m in messages if m.get("role") != "system"]
    texts = [flatten_text(m.get("content", "")).strip() for m in messages if m.get("role") == "system"]
    joined = "\n\n".join(t for t in texts if t)
    return turns, (joined or None)


logger = logging.getLogger(__name__)

# Minimum tokens reserved for the answer when fitting a prompt to the context
# window (A4.3): we never let the prompt consume so much of n_ctx that there's no
# room left to generate.
_MIN_GEN_RESERVE = 16

# ---------------------------------------------------------------------------
# Image content-parts (§V4) — validation, decoding, token estimation
# ---------------------------------------------------------------------------

_ALLOWED_IMAGE_MEDIA = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


def flatten_text(content) -> str:
    """The text of a message whose content may be a string or a parts array.
    Used for RAG queries and text-path serving (image parts contribute nothing)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
        ).strip()
    return ""


def has_image_parts(messages: List[dict]) -> bool:
    """True if any message carries an image_url content-part. The router uses
    this BEFORE building a StreamingResponse — a typed error must be raised
    pre-stream, not mid-stream."""
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for p in content:
                if isinstance(p, dict) and p.get("type") == "image_url":
                    return True
    return False


def _decode_data_url(url: str) -> bytes:
    """Decode an inline data:image/...;base64, URL. Remote URLs are rejected —
    a self-hosted server must never be induced to fetch external content (SSRF)."""
    import base64

    if not isinstance(url, str) or not url.startswith("data:"):
        raise InvalidRequest(
            message=(
                "Image parts must be inline data URLs (data:image/...;base64,...) — "
                "remote image URLs are not fetched."
            )
        )
    header, sep, payload = url.partition(",")
    media = header[5:].split(";", 1)[0].lower()
    if not sep or ";base64" not in header or media not in _ALLOWED_IMAGE_MEDIA:
        raise InvalidRequest(
            message=(
                "Unsupported image data URL. Use data:<media>;base64,<payload> with "
                f"media one of: {', '.join(sorted(_ALLOWED_IMAGE_MEDIA))}."
            )
        )
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise InvalidRequest(message="Image data URL payload is not valid base64.") from exc
    if len(raw) > settings.max_image_mb * 1024 * 1024:
        raise InvalidRequest(
            message=f"Image exceeds the {settings.max_image_mb} MB per-image limit."
        )
    return raw


def _estimate_image_tokens(width: int, height: int) -> int:
    """Conservative context-budget estimate for one image (§V4.3).

    Qwen2.5-VL consumes ~one token per 28×28 patch after 2×2 spatial merge —
    ≈ ceil(w/56)·ceil(h/56) — plus a few vision delimiter tokens. This is a
    guard against clearly-unfittable inputs, not an exact count (the runtime
    may rescale); the small constant keeps it on the safe side."""
    return -(-width // 56) * -(-height // 56) + 8


def validate_image_parts(messages: List[dict]) -> int:
    """Validate every image content-part (count cap, data-URL form, base64,
    size, decodable image, dimension cap) and return the total estimated image
    token cost. Raises typed 422s — image input must never 500 (§V4.2)."""
    import io

    from PIL import Image

    count = 0
    est_tokens = 0
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for p in content:
            if not (isinstance(p, dict) and p.get("type") == "image_url"):
                continue
            count += 1
            if count > settings.max_images_per_request:
                raise InvalidRequest(
                    message=(
                        f"Too many images: at most {settings.max_images_per_request} "
                        "per request."
                    )
                )
            url = (p.get("image_url") or {}).get("url", "")
            raw = _decode_data_url(url)
            try:
                with Image.open(io.BytesIO(raw)) as img:
                    width, height = img.size
            except Exception as exc:
                raise InvalidRequest(
                    message="Image payload could not be decoded as an image."
                ) from exc
            if max(width, height) > settings.max_image_side_px:
                raise InvalidRequest(
                    message=(
                        f"Image side {max(width, height)}px exceeds the "
                        f"{settings.max_image_side_px}px limit."
                    )
                )
            est_tokens += _estimate_image_tokens(width, height)
    return est_tokens


def _base_modality(model_name: str) -> str:
    """Modality of the endpoint's base model, from the single catalog (A3.3)."""
    from adapta.core.model_catalog import resolve as resolve_catalog

    entry = resolve_catalog(model_name)
    return entry.modality if entry else "text"


async def _load_model(model_name: str, adapter_path: Optional[str] = None):
    try:
        return await model_manager.ensure_model_loaded(model_name, adapter_path=adapter_path)
    except Exception as exc:
        raise ModelNotFound(
            message=f"Model '{model_name}' could not be loaded",
            internal_detail=str(exc),
        ) from exc


ABSTENTION_LINE = (
    'If the answer is not in the context, say "I can\'t find that in the documents." '
    "translated into the language the user wrote in, and do not guess or use outside knowledge."
)
_NO_CONTEXT_LINE = "No passage in the project's documents matched this question."


def _build_system(
    base_system: Optional[str],
    rag_service,
    rag_chunks: list,
    *,
    abstain: bool = False,
    client_system: Optional[str] = None,
) -> Optional[str]:
    """Assemble the system prompt. Order (E3.5): project prompt -> RAG block -> abstention
    line -> the client's own `system` text as a trailing paragraph.

    ``abstain`` is True when the project has indexed documents: the abstention line is
    then present even when no chunk survived retrieval. Shared by the streaming and
    non-streaming paths."""
    parts: list[str] = []
    if base_system:
        parts.append(base_system)
    if rag_chunks and rag_service is not None:
        context_block = rag_service.build_context_block(rag_chunks)
        parts.append(
            f"Use the following context to answer. Cite sources by their [N] number.\n\n"
            f"{context_block}"
        )
    elif abstain:
        parts.append(_NO_CONTEXT_LINE)
    if abstain:
        parts.append(ABSTENTION_LINE)
    if client_system:
        parts.append(client_system)
    return "\n\n".join(parts).strip() or None


def _fit_context(
    *,
    count_fn,
    n_ctx: int,
    base_system: Optional[str],
    rag_service,
    rag_chunks: list,
    max_tokens: int,
    abstain: bool = False,
    client_system: Optional[str] = None,
):
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
        system_prompt = _build_system(
            base_system, rag_service, chunks, abstain=abstain, client_system=client_system
        )
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
    rag_filters: Optional[RetrievalFilters] = None,
    # Fine-tune serving (A3.1): GGUF LoRA applied on top of the base model
    adapter_path: Optional[str] = None,
    # JSON mode: OpenAI-shape response_format dict (None = unconstrained)
    response_format: Optional[dict] = None,
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

    # Image content-parts (§V4): only on a vision base, validated + capped, and
    # served through the chat handler. v1 design decision: requests carrying
    # images skip document retrieval (no RAG composition with image input yet) —
    # text-only requests on the same endpoint still compose RAG as usual.
    if has_image_parts(messages):
        if _base_modality(model_name) != "vision":
            raise InvalidRequest(
                message=(
                    "This endpoint's base model is text-only and cannot accept image "
                    "content. Create the project on a vision base model "
                    "(e.g. qwen2.5-vl-3b-instruct)."
                )
            )
        image_tokens = validate_image_parts(messages)
        return await _chat_vision(
            model_name=model_name,
            messages=messages,
            image_tokens=image_tokens,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            adapter_path=adapter_path,
            response_format=response_format,
        )

    messages, client_system = split_client_system(messages)
    rag_chunks: list = []
    rag_service = None
    if project_id:
        rag_service = get_rag_service()
        query = flatten_text(messages[-1].get("content", "")) if messages else ""
        effective_top_k = await _resolve_rag_top_k(project_id, top_k_rag)
        rag_chunks = await _retrieve(
            rag_service, project_id, query, effective_top_k, rag_filters
        )

    # Content may be a parts array (all-text on the text path); flatten to the
    # plain string the manual prompt formatter expects.
    inference_messages = [
        Message(role=m["role"], content=flatten_text(m["content"])) for m in messages
    ]

    backend = get_backend(model_name, adapter_path)
    handle = await backend.prepare(model_name, adapter_path)

    # Fit prompt + answer into the model's context window before dispatch.
    # count_prompt_tokens / context_size are synchronous (llama-cpp: C call); run the whole fit off the event loop so a large
    # prompt never stalls other requests (e.g. /health).
    def _fit():
        return _fit_context(
            count_fn=lambda sp: handle.count_prompt_tokens(inference_messages, sp),
            n_ctx=handle.context_size(),
            base_system=system_prompt,
            abstain=project_id is not None,
            client_system=client_system,
            rag_service=rag_service,
            rag_chunks=rag_chunks,
            max_tokens=max_tokens,
        )

    full_system, rag_chunks, max_tokens = await asyncio.to_thread(_fit)

    req = InferenceRequest(
        messages=inference_messages,
        model_name=model_name,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stream=False,
        system_prompt=full_system,
        adapter_path=adapter_path,
        response_format=response_format,
    )
    try:
        response: InferenceResponse = await backend.generate(handle, req)
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

    if project_id:  # [] when nothing cleared the threshold: the model was told to abstain
        rag_service = get_rag_service()
        result["citations"] = rag_service.format_citations(rag_chunks)

    return result


async def _chat_vision(
    *,
    model_name: str,
    messages: List[dict],
    image_tokens: int,
    temperature: float,
    max_tokens: int,
    top_p: float,
    adapter_path: Optional[str],
    response_format: Optional[dict] = None,
) -> dict:
    """Non-streaming vision completion (§V4): image content-parts through the
    multimodal chat handler, with the fine-tune adapter applied as usual."""
    model_obj = await _load_model(model_name, adapter_path=adapter_path)
    lock = model_manager.get_inference_lock(model_name, adapter_path)

    # Context fit (§V4.3): text tokens via the real tokenizer + a conservative
    # per-image estimate. An unfittable image+prompt is a typed 422, never a
    # silent truncation.
    text_messages = [Message(role=m["role"], content=flatten_text(m["content"])) for m in messages]
    # Off the event loop — synchronous llama-cpp calls must not stall other requests.
    n_ctx, text_prompt = await asyncio.to_thread(
        lambda: (
            inference_engine.context_size(model_obj),
            inference_engine.count_prompt_tokens(model_obj, text_messages, None),
        )
    )
    n_prompt = text_prompt + image_tokens
    if n_prompt + min(_MIN_GEN_RESERVE, max_tokens) > n_ctx:
        raise InvalidRequest(
            message=(
                f"Prompt is too long (~{n_prompt} tokens including ~{image_tokens} "
                f"image tokens) for the model's {n_ctx}-token context window. "
                "Use smaller images or shorten your input."
            )
        )
    max_tokens = max(1, min(max_tokens, n_ctx - n_prompt))

    try:
        response: InferenceResponse = await inference_engine.generate_chat(
            model_obj,
            messages,
            model_name=model_name,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            lock=lock,
            response_format=response_format,
        )
    except DomainError:
        raise
    except Exception as exc:
        raise InferenceFailed(message="Inference failed", internal_detail=str(exc)) from exc

    # llama-cpp's chat-handler usage counts text tokens; image patches consume
    # context but aren't in the reported prompt_tokens — meter the estimate so
    # image-heavy traffic isn't systematically undercounted.
    prompt_tokens = response.prompt_tokens + image_tokens
    return {
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
            "prompt_tokens": prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": prompt_tokens + response.completion_tokens,
        },
    }


async def chat_stream(
    *,
    model_name: str,
    messages: List[dict],
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    project_id: Optional[str] = None,
    top_k_rag: Optional[int] = None,
    rag_filters: Optional[RetrievalFilters] = None,
    endpoint_id: Optional[str] = None,
    adapter_path: Optional[str] = None,
    response_format: Optional[dict] = None,
) -> AsyncIterator[str]:
    """
    Streaming chat — yields SSE-formatted strings.
    RAG context is injected before streaming starts (non-streaming retrieval).
    """
    import json

    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = min(max_tokens or settings.max_tokens, settings.max_tokens)  # cap (A4.3)

    # Defensive (§V4): the router rejects stream+images BEFORE building the
    # StreamingResponse (a typed error here would surface mid-stream as a broken
    # body, not a 422). This guard only protects direct callers.
    if has_image_parts(messages):
        raise InvalidRequest(
            message="Streaming with image content is not supported; send stream=false."
        )

    messages, client_system = split_client_system(messages)
    rag_chunks: list = []
    rag_service = None
    if project_id:
        rag_service = get_rag_service()
        query = flatten_text(messages[-1].get("content", "")) if messages else ""
        effective_top_k = await _resolve_rag_top_k(project_id, top_k_rag)
        rag_chunks = await _retrieve(
            rag_service, project_id, query, effective_top_k, rag_filters
        )

    inference_messages = [
        Message(role=m["role"], content=flatten_text(m["content"])) for m in messages
    ]

    # Backend selection (D3): same routing as non-streaming chat().
    backend = get_backend(model_name, adapter_path)
    handle = await backend.prepare(model_name, adapter_path)

    # Fit prompt + answer into the context window before streaming (A4.3).
    full_system, rag_chunks, max_tokens = _fit_context(
        count_fn=lambda sp: handle.count_prompt_tokens(inference_messages, sp),
        n_ctx=handle.context_size(),
        base_system=system_prompt,
        abstain=project_id is not None,
        client_system=client_system,
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
        response_format=response_format,
    )
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

    # llama-cpp: exact tokenizer count.
    prompt_tokens = handle.count_prompt_tokens(inference_messages, full_system)
    # Each iteration is one generated token, so counting iterations is exact.
    completion_tokens = 0
    try:
        async for token in backend.generate_stream(handle, req):
            completion_tokens += 1
            chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_name,
                "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"

        engine_usage = getattr(handle, "usage", None)
        if engine_usage:  # engine-reported exact counts (Ollama) beat our own
            prompt_tokens, completion_tokens = engine_usage
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
        # Citations can only be known once retrieval has happened — same
        # shape as chat()'s non-streaming response, carried on the final
        # frame (E1.7) since the model prompt (with [N] markers) is what
        # the SSE tokens are being streamed for.
        if project_id:
            if rag_service is None:
                raise InvalidRequest(message="RAG service not configured")
            finish["citations"] = rag_service.format_citations(rag_chunks)
        yield f"data: {json.dumps(finish)}\n\n"
        yield "data: [DONE]\n\n"

        # Metered off the client path — runs after the last byte is yielded.
        if endpoint_id:
            from adapta.services.usage import record_usage

            await record_usage(endpoint_id, prompt_tokens, completion_tokens)

    except DomainError:
        raise  # Timeout (504) and other typed errors keep their status — don't mask as 500.
    except Exception as exc:
        raise InferenceFailed(
            message="Streaming inference failed", internal_detail=str(exc)
        ) from exc
