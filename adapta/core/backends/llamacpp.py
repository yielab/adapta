"""llama-cpp serving backend — the default (D3).

Wraps the existing model_manager + inference_engine without touching their
internals (hard constraint #1). One loaded Llama instance per (base, adapter)
key, bounded by the LRU in model_manager (§A4.8), serialized per-instance
to avoid KV-cache races (§A4.1).

This backend handles all request types: text base, text LoRA, vision base,
vision LoRA.  The vLLM backend replaces this for TEXT LoRA only when opted in.
"""

from __future__ import annotations

from typing import AsyncIterator, List, Optional

from llama_cpp import Llama

from adapta.core import inference_engine, model_manager
from adapta.core.backends.base import BackendHandle, ServingBackend
from adapta.core.inference import InferenceRequest, InferenceResponse, Message
from adapta.domain.errors import ModelNotFound


class LlamaCppHandle(BackendHandle):
    """Holds a loaded Llama instance + its per-model serialization lock."""

    def __init__(self, model: Llama, lock, engine) -> None:
        self._model = model
        self._lock = lock
        self._engine = engine

    def context_size(self) -> int:
        return int(self._engine.context_size(self._model))

    def count_prompt_tokens(
        self, messages: List[Message], system_prompt: Optional[str]
    ) -> int:
        return int(self._engine.count_prompt_tokens(self._model, messages, system_prompt))


class LlamaCppBackend(ServingBackend):
    """Default backend: llama-cpp in-process (identical to pre-D3 chat.py)."""

    async def prepare(
        self, model_name: str, adapter_path: Optional[str]
    ) -> LlamaCppHandle:
        try:
            model = await model_manager.ensure_model_loaded(
                model_name, adapter_path=adapter_path
            )
        except Exception as exc:
            raise ModelNotFound(
                message=f"Model '{model_name}' could not be loaded",
                internal_detail=str(exc),
            ) from exc
        lock = model_manager.get_inference_lock(model_name, adapter_path)
        return LlamaCppHandle(model, lock, inference_engine)

    async def generate(
        self, handle: BackendHandle, request: InferenceRequest
    ) -> InferenceResponse:
        assert isinstance(handle, LlamaCppHandle)
        return await inference_engine.generate(handle._model, request, lock=handle._lock)

    async def generate_stream(
        self, handle: BackendHandle, request: InferenceRequest
    ) -> AsyncIterator[str]:
        assert isinstance(handle, LlamaCppHandle)
        async for token in inference_engine.generate_stream(
            handle._model, request, lock=handle._lock
        ):
            yield token
