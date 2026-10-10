"""Ollama serving backend (E2.1) — adapter-less text requests only.

Talks to an Ollama host over its native ``/api/chat`` (NDJSON), which — unlike the
OpenAI-compatible route — takes the structured-output ``format`` and reports the
engine's own ``prompt_eval_count`` / ``eval_count`` (exact token counts). Ollama
applies the model's own prompt template, so no chat template is rendered here.

Routing lives in ``backends/__init__.py``; adapters and vision never reach this class.
"""

from __future__ import annotations

import json
import math
from typing import Any, AsyncIterator, List, Optional

import httpx

from adapta.config import settings
from adapta.core.backends.base import BackendHandle, ServingBackend
from adapta.core.inference import InferenceRequest, InferenceResponse, Message
from adapta.domain.errors import InferenceFailed, InvalidRequest, ModelNotFound, Timeout

# Ollama exposes no tokenizer endpoint, so the context-fit guard (chat.py) works from
# a deliberately pessimistic estimate (3 chars/token + per-message framing). Billing
# and usage use the engine's exact counts after generation, never this estimate.
_CHARS_PER_TOKEN = 3
_PER_MESSAGE_OVERHEAD = 4


def format_for(response_format: Optional[dict]) -> Optional[Any]:
    """Map an OpenAI-shape ``response_format`` to Ollama's native ``format``.

    ``json_object`` -> ``"json"``; ``json_schema`` -> the schema dict itself.
    ``text``/None -> None (omit the field)."""
    if not response_format:
        return None
    kind = response_format.get("type")
    if kind == "json_object":
        return "json"
    if kind == "json_schema":
        try:
            return response_format["json_schema"]["schema"]
        except (KeyError, TypeError) as exc:
            raise InvalidRequest(
                message="response_format.json_schema.schema is required",
                internal_detail=str(exc),
            ) from exc
    return None


def _wire_messages(request: InferenceRequest) -> list[dict]:
    msgs: list[dict] = []
    if request.system_prompt:
        msgs.append({"role": "system", "content": request.system_prompt})
    msgs.extend({"role": m.role, "content": m.content} for m in request.messages)
    return msgs


def _payload(handle: "OllamaHandle", request: InferenceRequest, stream: bool) -> dict:
    options: dict[str, Any] = {
        "temperature": request.temperature,
        "top_p": request.top_p,
        "top_k": request.top_k,
        "num_predict": request.max_tokens,
        "num_ctx": handle.context_size(),
    }
    if request.stop:
        options["stop"] = request.stop
    body: dict[str, Any] = {
        "model": handle.tag,
        "messages": _wire_messages(request),
        "stream": stream,
        "options": options,
    }
    fmt = format_for(request.response_format)
    if fmt is not None:
        body["format"] = fmt
    return body


class OllamaHandle(BackendHandle):
    """The resolved Ollama tag. Holds no HTTP client: each call opens and closes its own,
    so a handle that never reaches generation leaks nothing."""

    def __init__(self, tag: str, n_ctx: int) -> None:
        self.tag = tag
        self._n_ctx = n_ctx

    def context_size(self) -> int:
        return self._n_ctx

    def count_prompt_tokens(
        self, messages: List[Message], system_prompt: Optional[str]
    ) -> int:
        chars = len(system_prompt or "") + sum(len(m.content) for m in messages)
        framing = _PER_MESSAGE_OVERHEAD * (len(messages) + (1 if system_prompt else 0))
        return math.ceil(chars / _CHARS_PER_TOKEN) + framing


def _failed(exc: Exception) -> Exception:
    if isinstance(exc, httpx.TimeoutException):
        return Timeout(message="Inference timed out", internal_detail=str(exc))
    return InferenceFailed(message="Inference failed", internal_detail=str(exc))


class OllamaBackend(ServingBackend):
    """Serving backend for adapter-less text requests, via an Ollama host."""

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        # A client per call, always used as `async with`: closed on every path, and never
        # shared across event loops (tests, reload).
        return httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(settings.inference_timeout_seconds, connect=10.0),
            transport=self._transport,
        )

    async def prepare(
        self, model_name: str, adapter_path: Optional[str]
    ) -> OllamaHandle:
        if adapter_path is not None:  # routing prevents this; fail loud if bypassed
            raise InvalidRequest(
                message="Adapters are served by llama-cpp, not Ollama",
                internal_detail=f"adapter_path={adapter_path!r}",
            )
        tag = settings.ollama_model_map.get(model_name)
        if tag is None:
            raise ModelNotFound(
                message=f"Model '{model_name}' has no Ollama mapping",
                internal_detail="not in ADAPTA_OLLAMA_MODEL_MAP",
            )
        async with self._client() as client:
            try:
                resp = await client.post("/api/show", json={"model": tag})
            except httpx.HTTPError as exc:
                raise _failed(exc) from exc
        if resp.status_code == 404:
            raise ModelNotFound(
                message=f"Model '{model_name}' is not available on the Ollama host",
                internal_detail=f"ollama pull {tag}",
            )
        if resp.status_code >= 400:
            raise InferenceFailed(
                message="Inference failed",
                internal_detail=f"ollama /api/show {resp.status_code}: {resp.text[:200]}",
            )
        return OllamaHandle(tag, settings.max_context_length)

    async def generate(
        self, handle: BackendHandle, request: InferenceRequest
    ) -> InferenceResponse:
        assert isinstance(handle, OllamaHandle)
        async with self._client() as client:
            try:
                resp = await client.post("/api/chat", json=_payload(handle, request, False))
                if resp.status_code >= 400:
                    raise InferenceFailed(
                        message="Inference failed",
                        internal_detail=f"ollama /api/chat {resp.status_code}: {resp.text[:200]}",
                    )
                data = resp.json()
            except httpx.HTTPError as exc:
                raise _failed(exc) from exc
        prompt = int(data.get("prompt_eval_count") or 0)
        completion = int(data.get("eval_count") or 0)
        handle.usage = (prompt, completion)
        return InferenceResponse(
            content=data.get("message", {}).get("content", ""),
            model=request.model_name,
            finish_reason="length" if data.get("done_reason") == "length" else "stop",
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        )

    async def generate_stream(
        self, handle: BackendHandle, request: InferenceRequest
    ) -> AsyncIterator[str]:
        assert isinstance(handle, OllamaHandle)
        async with self._client() as client:
            try:
                async with client.stream(
                    "POST", "/api/chat", json=_payload(handle, request, True)
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode(errors="replace")[:200]
                        raise InferenceFailed(
                            message="Inference failed",
                            internal_detail=f"ollama /api/chat {resp.status_code}: {body}",
                        )
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        frame = json.loads(line)
                        if frame.get("error"):
                            raise InferenceFailed(
                                message="Inference failed", internal_detail=str(frame["error"])
                            )
                        if frame.get("done"):
                            handle.usage = (
                                int(frame.get("prompt_eval_count") or 0),
                                int(frame.get("eval_count") or 0),
                            )
                            break
                        token = frame.get("message", {}).get("content", "")
                        if token:
                            yield token
            except httpx.HTTPError as exc:
                raise _failed(exc) from exc
