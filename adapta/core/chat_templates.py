"""Chat prompt templates — the mechanism that turns chat turns into the exact
prompt string a base model was trained to expect.

This lives OUTSIDE the inference engine on purpose: the engine stays a pure
execution wrapper (hard constraint #1), and adding a base model with a
different template (Llama-3, Mistral, …) is a *data* change — one catalog
entry naming its template, plus one small render function here — not an edit to
a hardcoded formatter buried in the engine.

Which template a model uses is declared once, on its catalog entry
(``CatalogEntry.chat_template``). The default is ChatML, which every Qwen2.5
base currently in the catalog was trained with.

A template captures the two things that actually vary between model families:
its *render* (how system/user/assistant turns wrap into a single string ending
at the assistant cue) and its *default stop strings* (the turn/end sentinels
the sampler must halt on when the caller didn't override ``stop``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Protocol, Sequence, Tuple


class _Turn(Protocol):
    """Structural view of a chat turn — anything with ``role`` and ``content``.

    Declared structurally (not as an import of ``inference.Message``) so this
    module has no dependency on the engine; the engine depends on it, never the
    reverse."""

    role: str
    content: str


# A render function takes the optional system prompt and the ordered turns and
# returns the full prompt string, ending at the point the model should begin
# generating the assistant reply.
RenderFn = Callable[[Optional[str], Sequence[_Turn]], str]


@dataclass(frozen=True)
class ChatTemplate:
    """One model family's prompt format."""

    name: str
    render: RenderFn
    default_stops: Tuple[str, ...]


def _render_chatml(system: Optional[str], messages: Sequence[_Turn]) -> str:
    """ChatML (``<|im_start|>role\\n…<|im_end|>``) — Qwen2.5, and the default."""
    parts = []
    if system:
        parts.append(f"<|im_start|>system\n{system}<|im_end|>")
    for msg in messages:
        parts.append(f"<|im_start|>{msg.role}\n{msg.content}<|im_end|>")
    parts.append("<|im_start|>assistant\n")
    return "\n".join(parts)


# The registry. Keyed by the name a ``CatalogEntry.chat_template`` declares.
# To onboard a non-ChatML base: add its ChatTemplate here, then point the
# catalog entry at it — nothing in the engine changes.
_TEMPLATES: Dict[str, ChatTemplate] = {
    "chatml": ChatTemplate(
        name="chatml",
        render=_render_chatml,
        default_stops=("<|im_end|>", "<|endoftext|>"),
    ),
}

DEFAULT_TEMPLATE = "chatml"


def _get(name: str) -> ChatTemplate:
    template = _TEMPLATES.get(name)
    if template is None:
        # A server-side configuration error (a catalog entry named a template
        # that was never registered), not a client error — surfaces as a
        # logged 500 via the boundary handler, never as a malformed prompt.
        raise ValueError(
            f"Unknown chat template '{name}'. Registered: "
            f"{', '.join(sorted(_TEMPLATES))}."
        )
    return template


def render(name: str, system: Optional[str], messages: Sequence[_Turn]) -> str:
    """Format ``system`` + ``messages`` into the prompt string for template ``name``."""
    return _get(name).render(system, messages)


def default_stops(name: str) -> list[str]:
    """Default stop strings for template ``name`` (used when the caller passes no ``stop``)."""
    return list(_get(name).default_stops)


def is_registered(name: str) -> bool:
    """Whether ``name`` names a registered template."""
    return name in _TEMPLATES
