"""Serving backend registry.

``get_backend()`` returns the appropriate ServingBackend for a given request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from adapta.core.backends.base import ServingBackend

# Module-level singletons — created lazily on first use.
_llamacpp_instance: Optional["ServingBackend"] = None


def _llamacpp() -> "ServingBackend":
    global _llamacpp_instance
    if _llamacpp_instance is None:
        from adapta.core.backends.llamacpp import LlamaCppBackend

        _llamacpp_instance = LlamaCppBackend()
    return _llamacpp_instance


_ollama_instance: Optional["ServingBackend"] = None


def _ollama() -> "ServingBackend":
    global _ollama_instance
    if _ollama_instance is None:
        from adapta.core.backends.ollama_backend import OllamaBackend

        _ollama_instance = OllamaBackend()
    return _ollama_instance


def get_backend(
    model_name: str, adapter_path: Optional[str] = None
) -> "ServingBackend":
    """Return the serving backend for a text-path request.

    Routing rule (E2.1): with ``ADAPTA_SERVING_BACKEND=ollama``, an adapter-less
    request for a model in ``ollama_model_map`` goes to Ollama. Anything with an
    adapter (``endpoint.adapter`` -> ``adapter_path``), vision (never routed through
    here) and models without a mapping stay on llama-cpp."""
    from adapta.config import settings

    if (
        settings.serving_backend == "ollama"
        and not adapter_path
        and model_name in settings.ollama_model_map
    ):
        return _ollama()
    return _llamacpp()


__all__ = ["get_backend"]
