"""
A4.8 — the loaded-model cache is LRU-bounded.

Since the cache key includes the adapter (A3.1), N fine-tune endpoints would pin
N full models in RAM and OOM the app. These tests drive the eviction bookkeeping
with sentinel objects (no real GGUF): access reorders LRU, and inserting past the
cap evicts the least-recently-used entry and drops its inference lock.
"""

import asyncio

from brain.config import settings
from brain.core.model_manager import ModelManager


def test_lru_eviction_drops_least_recently_used(monkeypatch):
    monkeypatch.setattr(settings, "max_loaded_models", 2)
    mgr = ModelManager()

    # Two distinct loaded models + their inference locks.
    mgr._models["a"] = object()
    mgr._models["b"] = object()
    mgr._infer_locks["a"] = asyncio.Lock()
    mgr._infer_locks["b"] = asyncio.Lock()

    # Touch "a" so "b" becomes the LRU.
    mgr._models.move_to_end("a")

    # Simulate inserting a third, new model: evict down to make room.
    mgr._evict_lru_if_needed()

    assert "b" not in mgr._models          # LRU evicted
    assert "a" in mgr._models              # recently used kept
    assert "b" not in mgr._infer_locks     # its lock dropped too
    assert len(mgr._models) < settings.max_loaded_models


def test_under_cap_evicts_nothing(monkeypatch):
    monkeypatch.setattr(settings, "max_loaded_models", 3)
    mgr = ModelManager()
    mgr._models["a"] = object()
    mgr._evict_lru_if_needed()
    assert "a" in mgr._models  # one loaded, cap 3 → nothing evicted
