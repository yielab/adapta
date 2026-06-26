"""Serving backend registry (D3).

``get_backend()`` returns the appropriate ServingBackend for a given request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from adapta.core.backends.base import ServingBackend

# Module-level singletons — created lazily on first use.
_llamacpp_instance: Optional["ServingBackend"] = None
_vllm_instance: Optional["ServingBackend"] = None


def _llamacpp() -> "ServingBackend":
    global _llamacpp_instance
    if _llamacpp_instance is None:
        from adapta.core.backends.llamacpp import LlamaCppBackend

        _llamacpp_instance = LlamaCppBackend()
    return _llamacpp_instance


def _vllm() -> "ServingBackend":
    global _vllm_instance
    if _vllm_instance is None:
        from adapta.core.backends.vllm_backend import VLLMBackend

        _vllm_instance = VLLMBackend()
    return _vllm_instance


def _is_text_model(model_name: str) -> bool:
    """True when the catalog entry's modality is 'text'."""
    from adapta.core.model_catalog import resolve

    entry = resolve(model_name)
    return (entry.modality if entry else "text") == "text"


def get_backend(
    model_name: str, adapter_path: Optional[str] = None
) -> "ServingBackend":
    """Return the appropriate serving backend for a text-path request.

    vLLM is selected only when:
    - ``ADAPTA_SERVING_BACKEND=vllm``
    - A LoRA adapter is present (text LoRA endpoint, not base/RAG)
    - The base model is text-modal (not vision — vLLM cannot serve VLM LoRAs)

    All other requests use the default llama-cpp backend.
    """
    from adapta.config import settings

    if (
        getattr(settings, "serving_backend", "llamacpp") == "vllm"
        and adapter_path is not None
        and _is_text_model(model_name)
    ):
        return _vllm()
    return _llamacpp()


__all__ = ["get_backend"]
