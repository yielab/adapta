"""
Pillar 3 — eval gate unit tests.

The product's safety promise: an unverified adapter NEVER serves.
These tests verify that EvalGateFailed fires and that a non-servable adapter
cannot bind an endpoint (enforced at the TrainingJob level via eval_passed=True guard).
"""

import json

import pytest

from brain.domain.errors import EvalGateFailed, NotFound
from brain.services.adapters import AdapterRegistry


@pytest.fixture
def registry(tmp_path):
    return AdapterRegistry(adapters_dir=tmp_path / "adapters")


# ---------------------------------------------------------------------------
# Threshold enforcement
# ---------------------------------------------------------------------------

def test_register_below_threshold_raises(registry):
    with pytest.raises(EvalGateFailed) as exc_info:
        registry.register(
            adapter_id="a1",
            project_id="p1",
            job_id="j1",
            adapter_path="/data/adapters/a1",
            eval_score=0.59,
            base_model="qwen2.5-3b",
        )
    err = exc_info.value
    assert err.status == 422
    assert err.code == "eval_gate_failed"


def test_register_at_exact_threshold_succeeds(registry):
    entry = registry.register(
        adapter_id="a2",
        project_id="p1",
        job_id="j2",
        adapter_path="/data/adapters/a2",
        eval_score=0.6,
        base_model="qwen2.5-3b",
    )
    assert entry["adapter_id"] == "a2"
    assert entry["eval_score"] == 0.6


def test_register_above_threshold_succeeds(registry):
    entry = registry.register(
        adapter_id="a3",
        project_id="p1",
        job_id="j3",
        adapter_path="/data/adapters/a3",
        eval_score=0.85,
        base_model="qwen2.5-3b",
    )
    assert entry["adapter_id"] == "a3"


def test_register_zero_score_raises(registry):
    with pytest.raises(EvalGateFailed):
        registry.register(
            adapter_id="a4",
            project_id="p1",
            job_id="j4",
            adapter_path="/data/adapters/a4",
            eval_score=0.0,
            base_model="qwen2.5-3b",
        )


def test_register_just_below_threshold_raises(registry):
    with pytest.raises(EvalGateFailed):
        registry.register(
            adapter_id="a5",
            project_id="p1",
            job_id="j5",
            adapter_path="/data/adapters/a5",
            eval_score=0.5999,
            base_model="qwen2.5-3b",
        )


# ---------------------------------------------------------------------------
# Persistence — registry survives across instances (filesystem-backed)
# ---------------------------------------------------------------------------

def test_registered_adapter_persists(tmp_path):
    reg1 = AdapterRegistry(adapters_dir=tmp_path / "adapters")
    reg1.register(
        adapter_id="a10",
        project_id="p10",
        job_id="j10",
        adapter_path="/data/adapters/a10",
        eval_score=0.75,
        base_model="qwen2.5-3b",
    )

    reg2 = AdapterRegistry(adapters_dir=tmp_path / "adapters")
    entry = reg2.get("a10")
    assert entry["eval_score"] == 0.75
    assert entry["project_id"] == "p10"


def test_failed_adapter_not_stored(registry):
    with pytest.raises(EvalGateFailed):
        registry.register(
            adapter_id="bad",
            project_id="p1",
            job_id="j_bad",
            adapter_path="/data/adapters/bad",
            eval_score=0.1,
            base_model="qwen2.5-3b",
        )
    with pytest.raises(NotFound):
        registry.get("bad")


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def test_get_unknown_adapter_raises_not_found(registry):
    with pytest.raises(NotFound):
        registry.get("does_not_exist")


def test_list_for_project_returns_only_that_project(registry):
    registry.register("x1", "proj_A", "j1", "/p/x1", 0.7, "qwen")
    registry.register("x2", "proj_A", "j2", "/p/x2", 0.8, "qwen")
    registry.register("x3", "proj_B", "j3", "/p/x3", 0.9, "qwen")

    results_a = registry.list_for_project("proj_A")
    results_b = registry.list_for_project("proj_B")

    assert len(results_a) == 2
    assert len(results_b) == 1
    assert all(e["project_id"] == "proj_A" for e in results_a)


def test_get_adapter_path(registry):
    registry.register("ap1", "p1", "j1", "/data/adapters/ap1", 0.65, "qwen")
    path = registry.get_adapter_path("ap1")
    assert str(path) == "/data/adapters/ap1"


# ---------------------------------------------------------------------------
# Dataset schema validation blocks job enqueue (Pillar 3 — dataset contract)
# ---------------------------------------------------------------------------

def test_invalid_dataset_rejected_before_enqueue(tmp_path):
    """A dataset that violates training_dataset.schema.json must be rejected."""
    from brain.services.training import validate_dataset

    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"question": "no response field"}) + "\n")

    valid, error, _ = validate_dataset(bad)
    assert not valid
    assert error is not None


def test_valid_dataset_passes_schema(tmp_path):
    from brain.services.training import validate_dataset

    good = tmp_path / "good.jsonl"
    good.write_text(json.dumps({"prompt": "Q?", "response": "A."}) + "\n")

    valid, error, count = validate_dataset(good)
    assert valid
    assert count == 1
