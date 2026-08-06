"""llama-cpp-python inference engine wrapper.

Wraps the ``Llama`` object for async, serialized, timeout-bounded inference.
Do NOT rewrite the llama-cpp internals here — this module calls the library;
it does not replace it (hard constraint #1 in CLAUDE.md).

Chat format is NOT hardcoded here: prompts are rendered by the named template
carried on the request (``InferenceRequest.chat_template``), resolved from the
model's catalog entry. The engine is a pure execution wrapper; which template a
model uses — and how to onboard a non-ChatML family — lives in
``adapta/core/chat_templates.py``.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import AsyncIterator, List, Optional

from llama_cpp import Llama

from adapta.config import settings
from adapta.core import chat_templates
from adapta.domain.errors import Timeout

logger = logging.getLogger(__name__)

# Bounded pool for the blocking llama-cpp calls (A4.1). The default executor is
# unbounded (min(32, cpu+4) threads), so a burst of generations could spawn
# dozens of concurrent forward passes and thrash the box. Per-model correctness
# is enforced by the caller's lock; this pool just caps total in-flight work.
_inference_executor = ThreadPoolExecutor(
    max_workers=settings.inference_max_workers,
    thread_name_prefix="inference",
)


def _close_stream(stream) -> None:
    """Best-effort close of a llama-cpp streaming generator (frees its context)."""
    try:
        stream.close()
    except Exception:  # pragma: no cover - close is advisory
        pass


@dataclass
class Message:
    """Single chat turn.

    ``role`` must be one of the OpenAI roles (``user``, ``assistant``,
    ``system``) — the active chat template embeds it literally into the turn
    wrapper, so an unrecognized role produces malformed output silently.
    """

    role: str
    content: str


@dataclass
class InferenceRequest:
    """Parameters for one inference call.

    Messages are formatted via ``_format_chat_prompt`` using the named
    ``chat_template`` before being passed to llama-cpp.  ``chat_template`` is a
    key into ``adapta.core.chat_templates`` (default ChatML); the serving
    backend sets it from the model's catalog entry so the prompt matches what
    the base was trained on.

    ``adapter_path`` is the GGUF LoRA path produced by the fine-tune
    pipeline (not the PEFT directory).  None means base/RAG serving.
    """

    messages: List[Message]
    model_name: str
    temperature: float = settings.temperature
    top_p: float = settings.top_p
    top_k: int = settings.top_k
    max_tokens: int = settings.max_tokens
    stream: bool = True
    stop: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    adapter_path: Optional[str] = None
    chat_template: str = chat_templates.DEFAULT_TEMPLATE


@dataclass
class InferenceResponse:
    """Result of one inference call.

    ``prompt_tokens`` / ``completion_tokens`` come from llama-cpp's ``usage``
    dict and are accurate for text-only calls.  Vision calls add image-patch
    tokens via a separate estimate in ``chat.py`` — the counts here undercount
    image-heavy traffic.
    """

    content: str
    model: str
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class InferenceEngine:
    """Async wrapper around llama-cpp's ``Llama`` object.

    Key invariants:
    - All public methods are async; blocking C calls run on ``_inference_executor``.
    - A ``Llama`` object is NOT safe for concurrent calls — callers must pass the
      per-model serialization lock from ``ModelManager.get_inference_lock``.
    - The lock is held until the underlying C call completes, even on timeout,
      because a llama-cpp call cannot be cancelled mid-flight.
    """

    def __init__(self):
        pass

    def _format_chat_prompt(self, request: InferenceRequest) -> str:
        """Render the request into the prompt string for its ``chat_template``.

        The engine holds no template literals — it delegates to the named
        template in ``chat_templates`` (default ChatML). Onboarding a model with
        a different format is a change there + a catalog entry, never here.
        """
        return chat_templates.render(
            request.chat_template, request.system_prompt, request.messages
        )

    async def generate(
        self,
        model: Llama,
        request: InferenceRequest,
        *,
        lock: Optional[asyncio.Lock] = None,
    ) -> InferenceResponse:
        """Generate a complete response.

        `lock` (from ``model_manager.get_inference_lock``) serializes calls on
        this Llama instance (A4.1). It is held until the underlying C call truly
        returns — even on timeout — because a llama-cpp call cannot be cancelled
        and must never run concurrently with the next request on the same model.
        """
        prompt = self._format_chat_prompt(request)
        stop_tokens = request.stop or chat_templates.default_stops(request.chat_template)
        loop = asyncio.get_event_loop()

        def _call():
            return model(
                prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                top_k=request.top_k,
                stop=stop_tokens,
                echo=False,
            )

        try:
            result = await self._run_locked(loop, _call, lock)
        except Timeout:
            raise
        except Exception as e:
            logger.error(f"Inference error: {e}")
            raise

        choice = result["choices"][0]
        content = choice["text"].strip()
        finish_reason = choice["finish_reason"]
        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        return InferenceResponse(
            content=content,
            model=request.model_name,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    async def generate_chat(
        self,
        model: Llama,
        messages: List[dict],
        *,
        model_name: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        lock: Optional[asyncio.Lock] = None,
    ) -> InferenceResponse:
        """Generate via the model's chat handler (``create_chat_completion``).

        The vision path (§V4): a multimodal model is loaded with a chat handler
        that routes ``image_url`` content-parts through the vision projector —
        something the text path's manual prompt formatting cannot express. Same
        serialization-lock and timeout semantics as ``generate`` (A4.1).
        """
        loop = asyncio.get_event_loop()

        def _call():
            return model.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )

        try:
            result = await self._run_locked(loop, _call, lock)
        except Timeout:
            raise
        except Exception as e:
            logger.error(f"Chat-handler inference error: {e}")
            raise

        choice = result["choices"][0]
        content = (choice["message"].get("content") or "").strip()
        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        return InferenceResponse(
            content=content,
            model=model_name,
            finish_reason=choice.get("finish_reason") or "stop",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    async def _run_locked(self, loop, fn, lock: Optional[asyncio.Lock]):
        """Run a blocking llama-cpp call serialized by `lock` and bounded by the
        inference timeout (A4.1).

        On timeout the call cannot be interrupted (Python can't kill the thread),
        so we never abandon it while another request might start: the model lock
        is released only when the thread actually finishes (via the done-callback),
        and `shield` keeps the future alive past the client-facing 504."""
        timeout = settings.inference_timeout_seconds
        if lock is None:
            fut = loop.run_in_executor(_inference_executor, fn)
            try:
                return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise Timeout(message="Inference timed out", internal_detail=str(exc)) from exc

        await lock.acquire()
        fut = loop.run_in_executor(_inference_executor, fn)
        # Release the model lock only when the C call truly returns — not when the
        # client times out — so the next same-model request can't race it.
        fut.add_done_callback(lambda _f: lock.release())
        try:
            return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise Timeout(message="Inference timed out", internal_detail=str(exc)) from exc

    async def generate_stream(
        self,
        model: Llama,
        request: InferenceRequest,
        *,
        lock: Optional[asyncio.Lock] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response.

        Two safety properties over the naive version (A4.1):
        - The model `lock` is held for the *entire* stream — every token mutates
          the same Llama context, so no other request may touch this model until
          the stream is fully drained.
        - Each token is pulled on the bounded pool (not iterated synchronously in
          the event loop), so streaming no longer blocks the whole server, and a
          wall-clock deadline is checked *between* tokens. The check is between
          tokens (never mid-call) so stopping is race-free: there is no in-flight
          C call when we close the generator and release the lock.
        """
        prompt = self._format_chat_prompt(request)
        stop_tokens = request.stop or chat_templates.default_stops(request.chat_template)
        loop = asyncio.get_event_loop()

        def _create_stream():
            return model(
                prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                top_k=request.top_k,
                stop=stop_tokens,
                stream=True,
                echo=False,
            )

        _SENTINEL = object()

        if lock is not None:
            await lock.acquire()
        try:
            deadline = time.monotonic() + settings.inference_timeout_seconds
            stream = await loop.run_in_executor(_inference_executor, _create_stream)

            def _next():
                try:
                    return next(stream)
                except StopIteration:
                    return _SENTINEL

            while True:
                if time.monotonic() > deadline:
                    # No `_next` is in flight here (the previous one returned), so
                    # closing + releasing the lock cannot race a live C call.
                    _close_stream(stream)
                    raise Timeout(message="Streaming inference timed out")
                chunk = await loop.run_in_executor(_inference_executor, _next)
                if chunk is _SENTINEL:
                    break
                if "choices" in chunk and len(chunk["choices"]) > 0:
                    delta = chunk["choices"][0].get("text", "")
                    if delta:
                        yield delta
        except Timeout:
            raise
        except Exception as e:
            logger.error(f"Streaming inference error: {e}")
            raise
        finally:
            if lock is not None:
                lock.release()

    def count_tokens(self, model: Llama, text: str) -> int:
        """Count tokens in ``text`` using the model's real tokenizer.

        Falls back to ``len(text) // 4`` on tokenizer error.  Callers using
        this for context budgeting should be aware the fallback may under- or
        over-count for non-ASCII text.
        """
        try:
            tokens = model.tokenize(text.encode("utf-8"))
            return len(tokens)
        except Exception as e:
            logger.warning("Token counting error: %s", e)
            return len(text) // 4

    def count_prompt_tokens(
        self,
        model: Llama,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        chat_template: str = chat_templates.DEFAULT_TEMPLATE,
    ) -> int:
        """Token count of the FINAL formatted prompt, via the model's real tokenizer.

        This is the exact text the model will be conditioned on, so it's the number
        to budget against ``n_ctx`` (A4.3) — not a char/4 estimate.  ``chat_template``
        must match the one generation will use, or the count omits that family's
        turn-wrapper tokens; callers resolve it from the model's catalog entry."""
        req = InferenceRequest(
            messages=messages,
            model_name="",
            system_prompt=system_prompt,
            chat_template=chat_template,
        )
        return self.count_tokens(model, self._format_chat_prompt(req))

    def context_size(self, model: Llama) -> int:
        """Return the model's active context window (n_ctx).

        Falls back to ``settings.max_context_length`` on error.  If the GGUF
        was loaded with a different ``n_ctx`` than the config default, this
        returns the actual value; the fallback may not match, causing the
        context-fit guard in ``chat.py`` to use an incorrect ceiling.
        """
        try:
            return int(model.n_ctx())
        except Exception:  # pragma: no cover - defensive
            return settings.max_context_length


inference_engine = InferenceEngine()
