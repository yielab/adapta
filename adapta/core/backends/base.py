"""Abstract serving backend interface.

llama-cpp is the default (always available, handles RAG/CPU and VLM mmproj).
vLLM is an opt-in second backend for text LoRA density: many adapters share
one GPU via continuous batching (ADAPTA_SERVING_BACKEND=vllm, requires the
vllm-server compose service). Vision endpoints always use llama-cpp — vLLM
does not support LoRA on vision layers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional

from adapta.core.inference import InferenceRequest, InferenceResponse, Message


class BackendHandle(ABC):
    """Synchronous, per-request model reference returned by ServingBackend.prepare().

    The sync methods (context_size / count_prompt_tokens) may be called from
    asyncio.to_thread() by the context-fit logic — they must not block on
    async I/O."""

    @abstractmethod
    def context_size(self) -> int:
        """The model's context window (tokens)."""

    @abstractmethod
    def count_prompt_tokens(
        self, messages: List[Message], system_prompt: Optional[str]
    ) -> int:
        """Token count of the full assembled prompt."""


class ServingBackend(ABC):
    """Dispatch interface between chat.py and the underlying inference engine."""

    @abstractmethod
    async def prepare(
        self, model_name: str, adapter_path: Optional[str]
    ) -> BackendHandle:
        """Load or resolve the model (and adapter) and return a sync handle."""

    @abstractmethod
    async def generate(
        self, handle: BackendHandle, request: InferenceRequest
    ) -> InferenceResponse:
        """Non-streaming generation."""

    async def generate_stream(
        self, handle: BackendHandle, request: InferenceRequest
    ) -> AsyncIterator[str]:
        """Token-by-token streaming; yields one model token per iteration.

        Implemented as an async generator in subclasses — declared here as a
        regular async method returning AsyncIterator so @abstractmethod works
        without fighting Python's abstract-async-generator mechanics."""
        raise NotImplementedError("generate_stream must be implemented by subclass")
        # Make type-checkers happy that this is an async generator:
        yield  # type: ignore[misc]  # pragma: no cover
