"""
A4.1 — inference is concurrency-safe and time-bounded.

llama-cpp's ``Llama`` object is not safe for concurrent calls on one instance.
These in-process tests use a fake model (no GGUF, no infra) to prove:

1. N concurrent ``generate`` calls sharing one lock never overlap on the model.
2. The same for ``generate_stream`` (the lock is held across the whole drain).
3. A generation that exceeds ``inference_timeout_seconds`` raises ``Timeout`` (504),
   not a hang — for both the blocking and streaming paths.
"""

import asyncio
import time

import pytest

from brain.config import settings
from brain.core.inference import InferenceEngine, InferenceRequest, Message
from brain.domain.errors import Timeout


class FakeLlama:
    """Stands in for ``llama_cpp.Llama``. Asserts it is never entered concurrently,
    so a broken lock surfaces as an error instead of silently racing."""

    def __init__(self, *, delay: float = 0.02, n_tokens: int = 4):
        self.delay = delay
        self.n_tokens = n_tokens
        self._active = 0
        self.max_active = 0

    def _enter(self) -> None:
        self._active += 1
        self.max_active = max(self.max_active, self._active)
        if self._active > 1:
            raise AssertionError("concurrent call on a single Llama instance")

    def _exit(self) -> None:
        self._active -= 1

    def __call__(self, prompt, *, stream: bool = False, **kwargs):
        if stream:
            return self._stream()
        self._enter()
        try:
            time.sleep(self.delay)
            return {
                "choices": [{"text": "hello world", "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            }
        finally:
            self._exit()

    def _stream(self):
        self._enter()
        try:
            for i in range(self.n_tokens):
                time.sleep(self.delay)
                yield {"choices": [{"text": f"t{i} "}]}
        finally:
            self._exit()


def _req(stream: bool) -> InferenceRequest:
    return InferenceRequest(
        messages=[Message(role="user", content="hi")],
        model_name="fake",
        max_tokens=16,
        stream=stream,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

async def test_generate_serialized_under_concurrency():
    fake = FakeLlama(delay=0.02)
    lock = asyncio.Lock()
    engine = InferenceEngine()

    results = await asyncio.gather(
        *[engine.generate(fake, _req(stream=False), lock=lock) for _ in range(8)]
    )

    assert len(results) == 8
    assert all(r.content == "hello world" for r in results)
    assert fake.max_active == 1  # the lock kept calls from ever overlapping
    assert not lock.locked()


async def test_stream_serialized_under_concurrency():
    fake = FakeLlama(delay=0.01, n_tokens=4)
    lock = asyncio.Lock()
    engine = InferenceEngine()

    async def drain() -> str:
        out = []
        async for tok in engine.generate_stream(fake, _req(stream=True), lock=lock):
            out.append(tok)
        return "".join(out)

    outs = await asyncio.gather(*[drain() for _ in range(5)])

    assert all(o == "t0 t1 t2 t3 " for o in outs)
    assert fake.max_active == 1
    assert not lock.locked()


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

async def test_generate_times_out(monkeypatch):
    monkeypatch.setattr(settings, "inference_timeout_seconds", 0.05)
    fake = FakeLlama(delay=0.3)  # the C call outlasts the deadline
    lock = asyncio.Lock()
    engine = InferenceEngine()

    with pytest.raises(Timeout):
        await engine.generate(fake, _req(stream=False), lock=lock)

    # The lock is held until the (uncancellable) thread finishes — never released
    # mid-call — then freed by the done-callback. Drain it so the next request is
    # not permanently blocked.
    await asyncio.sleep(0.4)
    assert not lock.locked()


async def test_stream_times_out(monkeypatch):
    monkeypatch.setattr(settings, "inference_timeout_seconds", 0.03)
    fake = FakeLlama(delay=0.05, n_tokens=100)  # deadline trips between tokens
    lock = asyncio.Lock()
    engine = InferenceEngine()

    with pytest.raises(Timeout):
        async for _ in engine.generate_stream(fake, _req(stream=True), lock=lock):
            pass

    # Streaming stops between tokens (no in-flight call), so the lock releases cleanly.
    assert not lock.locked()
