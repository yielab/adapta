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


def get_backend(
    model_name: str, adapter_path: Optional[str] = None
) -> "ServingBackend":
    """Return the serving backend for a text-path request (llama-cpp)."""
    return _llamacpp()


__all__ = ["get_backend"]
