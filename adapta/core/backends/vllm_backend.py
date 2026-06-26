"""vLLM serving backend — opt-in alternative for text LoRA density.

Connects to a separately-running vLLM server (the ``vllm-server`` compose
service, ``profiles: [vllm]``) via its OpenAI-compatible HTTP API.  This
closes the density gap: N text LoRA adapters share one vLLM GPU process via
continuous batching, instead of the llama-cpp model where each (base, adapter)
pair is a separate GPU-resident instance.

**Routing rules (enforced by _registry.py):**
- Vision endpoints → always llama-cpp (vLLM does not support VLM LoRA layers)
- RAG-only / base-only → always llama-cpp (CPU; no adapter involved)
- Text LoRA + ADAPTA_SERVING_BACKEND=vllm → this backend

**vLLM server prerequisites (see OPERATIONS.md §9):**
- Start with: ``docker compose --profile vllm up -d``
- vLLM loads the base model once; adapters are registered dynamically via
  ``POST /v1/load_lora_adapter`` and reused across requests.
- The ``data/`` volume is shared so adapter paths resolve inside the container.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Dict, List, Optional

import httpx

from adapta.config import settings
from adapta.core.backends.base import BackendHandle, ServingBackend
from adapta.core.inference import InferenceRequest, InferenceResponse, Message
from adapta.domain.errors import InferenceFailed, ModelNotFound, Timeout

logger = logging.getLogger(__name__)


def _prompt_text(messages: List[Message], system_prompt: Optional[str]) -> str:
    parts = [system_prompt or ""]
    for m in messages:
        parts.append(m.content if isinstance(m.content, str) else "")
    return " ".join(filter(None, parts))


class VLLMHandle(BackendHandle):
    """Lightweight per-request handle: resolved model / adapter name + context."""

    def __init__(
        self,
        *,
        base_model_name: str,
        adapter_name: Optional[str],
        n_ctx: int,
    ) -> None:
        self.base_model_name = base_model_name
        self.adapter_name = adapter_name  # registered lora name, or None for base serving
        self._n_ctx = n_ctx

    @property
    def vllm_model(self) -> str:
        return self.adapter_name or self.base_model_name

    def context_size(self) -> int:
        return self._n_ctx

    def count_prompt_tokens(
        self, messages: List[Message], system_prompt: Optional[str]
    ) -> int:
        # Approximate (char // 4): vLLM manages context internally; this guides
        # RAG-chunk dropping in _fit_context, not a hard guard. A slight undercount
        # keeps more chunks (safe: vLLM will truncate excess internally if needed).
        return len(_prompt_text(messages, system_prompt)) // 4


class VLLMBackend(ServingBackend):
    """HTTP client to the vllm-server OpenAI-compatible API (ADAPTA_SERVING_BACKEND=vllm).

    Adapter lifecycle:
    1. First request for a new adapter → POST /v1/load_lora_adapter (idempotent)
    2. Subsequent requests → use the registered ``lora_name`` as the ``model``
    3. Base-only requests → ``model`` = catalog base model name
    """

    def __init__(self) -> None:
        # adapter directory path → registered lora name
        self._registered: Dict[str, str] = {}
        self._register_lock = asyncio.Lock()
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ HTTP

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.vllm_base_url,
                timeout=settings.inference_timeout_seconds,
            )
        return self._client

    # ---------------------------------------------------------- LoRA registry

    @staticmethod
    def _lora_name(peft_dir: str) -> str:
        import hashlib

        return "lora-" + hashlib.sha1(peft_dir.encode()).hexdigest()[:12]

    async def _ensure_registered(self, adapter_path: str) -> str:
        """Register the PEFT adapter with the vLLM server if not already done.

        ``adapter_path`` is the GGUF file path (what the registry stores).
        The PEFT directory is its parent, which holds ``adapter_model.safetensors``
        and ``adapter_config.json`` — what vLLM needs directly (no GGUF involved).
        The vllm-server container mounts the same ``data/`` volume as the app."""
        from pathlib import Path

        peft_dir = str(Path(adapter_path).parent)
        if peft_dir in self._registered:
            return self._registered[peft_dir]

        async with self._register_lock:
            if peft_dir in self._registered:
                return self._registered[peft_dir]

            lora_name = self._lora_name(peft_dir)
            try:
                resp = await self._http().post(
                    "/v1/load_lora_adapter",
                    json={"lora_name": lora_name, "lora_path": peft_dir},
                )
            except httpx.HTTPError as exc:
                raise ModelNotFound(
                    message=(
                        "Cannot reach the vLLM server. "
                        "Is ``docker compose --profile vllm up -d`` running? "
                        "See OPERATIONS.md §9."
                    ),
                    internal_detail=str(exc),
                ) from exc

            if resp.status_code not in (200, 409):
                # 409 = already registered (idempotent OK)
                raise InferenceFailed(
                    message="Failed to register LoRA adapter with the vLLM server.",
                    internal_detail=(
                        f"POST /v1/load_lora_adapter → HTTP {resp.status_code}: "
                        f"{resp.text[:400]}"
                    ),
                )
            self._registered[peft_dir] = lora_name
            logger.info(
                "vLLM: registered adapter '%s' from %s", lora_name, peft_dir
            )
            return lora_name

    # ---------------------------------------------------------------- prepare

    async def prepare(
        self, model_name: str, adapter_path: Optional[str]
    ) -> VLLMHandle:
        from adapta.core.model_catalog import resolve as resolve_catalog
        from adapta.core.model_catalog import resolve_serving_name
        from adapta.core.model_manager import model_manager as mm

        serving = resolve_serving_name(model_name)
        cfg = mm.get_model_config(serving)
        n_ctx = cfg.context_length if cfg else settings.max_context_length

        entry = resolve_catalog(model_name)
        base_name = entry.name if entry else model_name

        adapter_name: Optional[str] = None
        if adapter_path:
            adapter_name = await self._ensure_registered(adapter_path)

        return VLLMHandle(
            base_model_name=base_name,
            adapter_name=adapter_name,
            n_ctx=n_ctx,
        )

    # --------------------------------------------------------------- generate

    def _build_messages(
        self, request: InferenceRequest
    ) -> List[Dict]:
        msgs = []
        if request.system_prompt:
            msgs.append({"role": "system", "content": request.system_prompt})
        for m in request.messages:
            msgs.append({"role": m.role, "content": m.content})
        return msgs

    async def generate(
        self, handle: BackendHandle, request: InferenceRequest
    ) -> InferenceResponse:
        assert isinstance(handle, VLLMHandle)
        payload = {
            "model": handle.vllm_model,
            "messages": self._build_messages(request),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": False,
        }
        client = self._http()
        try:
            resp = await asyncio.wait_for(
                client.post("/v1/chat/completions", json=payload),
                timeout=settings.inference_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise Timeout(
                message="vLLM inference timed out", internal_detail=str(exc)
            ) from exc
        except httpx.HTTPError as exc:
            raise InferenceFailed(
                message="vLLM server request failed", internal_detail=str(exc)
            ) from exc

        if resp.status_code != 200:
            raise InferenceFailed(
                message="vLLM inference returned an error.",
                internal_detail=f"HTTP {resp.status_code}: {resp.text[:400]}",
            )

        data = resp.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return InferenceResponse(
            content=(choice["message"].get("content") or "").strip(),
            model=handle.base_model_name,
            finish_reason=choice.get("finish_reason") or "stop",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

    async def generate_stream(
        self, handle: BackendHandle, request: InferenceRequest
    ) -> AsyncIterator[str]:
        assert isinstance(handle, VLLMHandle)
        payload = {
            "model": handle.vllm_model,
            "messages": self._build_messages(request),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": True,
        }
        client = self._http()
        deadline = asyncio.get_event_loop().time() + settings.inference_timeout_seconds
        try:
            async with client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise InferenceFailed(
                        message="vLLM streaming returned an error.",
                        internal_detail=(
                            f"HTTP {resp.status_code}: "
                            + body.decode("utf-8", errors="replace")[:400]
                        ),
                    )
                async for line in resp.aiter_lines():
                    if asyncio.get_event_loop().time() > deadline:
                        raise Timeout(message="vLLM streaming timed out")
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk["choices"][0].get("delta", {}).get("content", "")
                    if delta:
                        yield delta
        except (Timeout, InferenceFailed):
            raise
        except httpx.HTTPError as exc:
            raise InferenceFailed(
                message="vLLM streaming request failed", internal_detail=str(exc)
            ) from exc
