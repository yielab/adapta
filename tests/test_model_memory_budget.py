"""F1.6 — models are evicted by memory budget BEFORE loading, and one that can never fit is
refused with a typed error. Fake files only: no GGUF is ever loaded."""

import asyncio

import pytest

from adapta.config import settings
from adapta.core import memory_budget
from adapta.core.model_manager import ModelManager
from adapta.domain.errors import ModelTooLargeForMemory

MIB = 1024 * 1024


def _gguf(tmp_path, name, size_mb):
    p = tmp_path / name
    with open(p, "wb") as f:
        f.truncate(size_mb * MIB)  # sparse: no real disk use
    return p


def test_cgroup_limit_parsing(tmp_path):
    f = tmp_path / "memory.max"
    f.write_text("4294967296\n")
    assert memory_budget.cgroup_limit_mb(f) == 4096
    f.write_text("max\n")
    assert memory_budget.cgroup_limit_mb(f) is None
    assert memory_budget.cgroup_limit_mb(tmp_path / "missing") is None


def test_budget_from_cgroup_minus_reserve_and_explicit_override(tmp_path, monkeypatch):
    f = tmp_path / "memory.max"
    f.write_text(str(4096 * MIB))
    monkeypatch.setattr(settings, "model_memory_budget_mb", 0)
    monkeypatch.setattr(settings, "model_memory_reserve_mb", 1024)
    assert memory_budget.budget_mb(f) == 3072
    monkeypatch.setattr(settings, "model_memory_budget_mb", 1500)
    assert memory_budget.budget_mb(f) == 1500
    monkeypatch.setattr(settings, "model_memory_budget_mb", 0)
    f.write_text("max")
    assert memory_budget.budget_mb(f) is None


def test_cost_scales_with_file_and_context(tmp_path):
    small = _gguf(tmp_path, "s.gguf", 1000)
    big = _gguf(tmp_path, "b.gguf", 2000)
    assert memory_budget.estimate_cost_mb(big, 2048) > memory_budget.estimate_cost_mb(small, 2048)
    assert memory_budget.estimate_cost_mb(small, 8192) > memory_budget.estimate_cost_mb(small, 2048)
    assert memory_budget.estimate_cost_mb(small, 2048) > 1000  # weights alone are a floor


def test_f1_6_sequence_1_5b_then_3b_evicts_the_1_5b(tmp_path, monkeypatch):
    """The F2.1 live sequence on a 4 GB container (budget 3072 MiB)."""
    monkeypatch.setattr(settings, "model_memory_budget_mb", 3072)
    monkeypatch.setattr(settings, "max_loaded_models", 5)  # count cap must not be what saves us
    mgr = ModelManager()
    small = _gguf(tmp_path, "1.5b.gguf", 1066)
    big = _gguf(tmp_path, "3b.gguf", 2007)

    mgr._make_room_for("small", small, 2048, None)
    mgr._models["small"] = object()
    mgr._infer_locks["small"] = object()
    assert "small" in mgr._models

    mgr._make_room_for("big", big, 2048, None)  # runs BEFORE the allocation
    assert "small" not in mgr._models  # evicted to make room
    assert "small" not in mgr._infer_locks
    mgr._models["big"] = object()


def test_models_that_fit_together_are_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "model_memory_budget_mb", 4000)
    monkeypatch.setattr(settings, "max_loaded_models", 5)
    mgr = ModelManager()
    a = _gguf(tmp_path, "a.gguf", 500)
    mgr._make_room_for("a", a, 2048, None)
    mgr._models["a"] = object()
    mgr._make_room_for("b", a, 2048, None)
    assert "a" in mgr._models


def test_model_that_can_never_fit_raises_typed_503(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "model_memory_budget_mb", 3072)
    mgr = ModelManager()
    huge = _gguf(tmp_path, "q8.gguf", 3449)  # a 3B Q8_0
    mgr._models["keep"] = object()
    with pytest.raises(ModelTooLargeForMemory) as exc:
        mgr._make_room_for("huge", huge, 2048, None)
    assert exc.value.status == 503 and exc.value.code == "model_too_large_for_memory"
    assert "keep" in mgr._models  # nothing was evicted for a load that cannot succeed


def test_no_budget_keeps_count_only_behaviour(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "model_memory_budget_mb", 0)
    monkeypatch.setattr(memory_budget, "CGROUP_MEMORY_MAX", tmp_path / "absent")
    monkeypatch.setattr(settings, "max_loaded_models", 1)
    mgr = ModelManager()
    mgr._models["a"] = object()
    mgr._make_room_for("b", _gguf(tmp_path, "b.gguf", 100), 2048, None)
    assert "a" not in mgr._models  # count cap applied, now before the load


def test_evicted_model_is_actually_freed(tmp_path, monkeypatch):
    """F1.6 live finding: with the real Llama the executor Future kept every loaded model alive
    after eviction (~0.7 GB anon each; only reproducible live, see OPERATIONS). This pins that
    nothing in the manager itself holds an evicted model."""
    import gc
    import sys
    import weakref

    import adapta.core.model_manager  # noqa: F401

    mm = sys.modules["adapta.core.model_manager"]  # the package re-exports the singleton

    class FakeLlama:
        def __init__(self, **kw):
            pass

    monkeypatch.setattr(mm, "Llama", FakeLlama)
    monkeypatch.setattr(settings, "model_memory_budget_mb", 0)
    monkeypatch.setattr(memory_budget, "CGROUP_MEMORY_MAX", tmp_path / "absent")
    monkeypatch.setattr(settings, "max_loaded_models", 1)
    mgr = ModelManager()
    for name in ("a", "b"):
        mgr._configs[name] = mm.ModelConfig(
            name=name, model_type=next(iter(mm.ModelType)), path=_gguf(tmp_path, f"{name}.gguf", 1)
        )
    monkeypatch.setattr(mgr, "_resolve_serving_name", lambda n: n)

    async def run():
        first = await mgr.load_model("a")
        ref = weakref.ref(first)
        del first
        await mgr.load_model("b")  # evicts "a"
        gc.collect()
        return ref() is None  # checked while the loop and executor are still alive

    assert asyncio.run(run())
