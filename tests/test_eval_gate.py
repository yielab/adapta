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


# ---------------------------------------------------------------------------
# Minimum dataset size (A4.6) — a too-small set can't be split into a held-out
# eval set, so the gate would only measure memorization. Reject before enqueue.
# ---------------------------------------------------------------------------

def test_below_min_samples_rejected():
    import pytest

    from brain.config import settings
    from brain.domain.errors import InvalidRequest
    from brain.services.training import check_min_training_samples

    with pytest.raises(InvalidRequest) as exc:
        check_min_training_samples(settings.min_training_samples - 1)
    assert str(settings.min_training_samples) in exc.value.message


def test_at_min_samples_allowed():
    from brain.config import settings
    from brain.services.training import check_min_training_samples

    # exactly the floor (and None → 0) — floor passes, None rejected
    check_min_training_samples(settings.min_training_samples)
    import pytest

    from brain.domain.errors import InvalidRequest
    with pytest.raises(InvalidRequest):
        check_min_training_samples(None)


# ---------------------------------------------------------------------------
# Hyperparameter bounds (A4.12) — reject runaway configs before they tie up a GPU.
# ---------------------------------------------------------------------------

def test_training_config_bounds():
    import pytest

    from brain.domain.errors import InvalidRequest
    from brain.services.training import validate_training_config

    validate_training_config(None)            # no config → ok
    validate_training_config({})              # empty → ok
    validate_training_config({"num_epochs": 3, "learning_rate": 2e-4})  # in range → ok

    for bad in (
        {"num_epochs": 1000},                 # way over the cap
        {"learning_rate": 1.0},               # divergent
        {"batch_size": 100000},               # OOM
        {"lora_dropout": 5},                  # nonsensical
        {"num_epochs": "lots"},               # wrong type
    ):
        with pytest.raises(InvalidRequest):
            validate_training_config(bad)


# ---------------------------------------------------------------------------
# Eval score computation — the value the gate actually tests (regression: the
# worker used getattr(result, "score", 0.0), which was ALWAYS 0.0 because
# EvaluationResult had no `score` — so no adapter could ever pass the gate).
# ---------------------------------------------------------------------------

import math  # noqa: E402

from brain.training.models import (  # noqa: E402
    EvaluationMetrics,
    EvaluationResult,
    score_from_loss,
    split_holdout,
)


def test_score_from_loss_bounds_and_anchors():
    # Perfect prediction (loss 0) → 1.0; loss grows → score decays toward 0.
    assert score_from_loss(0.0) == 1.0
    assert 0.0 <= score_from_loss(10.0) < 0.001
    # 1/perplexity == exp(-loss).
    assert score_from_loss(1.0) == pytest.approx(math.exp(-1.0))


def test_score_from_loss_is_monotonic_decreasing():
    losses = [0.0, 0.25, 0.5, 1.0, 2.0, 5.0]
    scores = [score_from_loss(x) for x in losses]
    assert scores == sorted(scores, reverse=True)


def test_score_from_loss_clamps_nonfinite():
    assert score_from_loss(float("inf")) == 0.0
    assert score_from_loss(float("nan")) == 0.0


def test_threshold_maps_to_perplexity_167():
    # The 0.6 gate ⇔ perplexity ≤ ~1.67 ⇔ loss ≤ ~0.51.
    boundary_loss = -math.log(0.6)
    assert score_from_loss(boundary_loss) == pytest.approx(0.6)
    assert score_from_loss(boundary_loss - 0.01) > 0.6  # better loss passes
    assert score_from_loss(boundary_loss + 0.01) < 0.6  # worse loss is blocked


def test_evaluation_result_carries_real_score_not_zero():
    """The regression guard: a finished eval produces a real score the gate reads."""
    avg_loss = 0.3
    result = EvaluationResult(
        eval_id="e1", job_id="j1", agent_id="a1", adapter_name="ad1",
        adapter_path="/p", dataset_path="/d", num_examples=4,
        metrics=EvaluationMetrics(loss=avg_loss, perplexity=math.exp(avg_loss)),
        score=score_from_loss(avg_loss),
    )
    assert result.score > 0.0
    assert result.score == pytest.approx(math.exp(-avg_loss))
    # Round-trips through serialization (Redis/disk) without losing the score.
    assert EvaluationResult.from_dict(result.to_dict()).score == pytest.approx(result.score)


# ---------------------------------------------------------------------------
# A3.2 — generalization, not memorization:
#   (1) held-out split is non-overlapping with training rows,
#   (2) response-only (prompt-masked) loss,
#   (3) base-vs-adapter delta is computed + persisted.
# ---------------------------------------------------------------------------


class TestHeldOutSplit:
    """The eval gate must score rows the model did NOT train on (split_holdout)."""

    def test_split_holds_out_last_fraction(self):
        # 10 rows, default 20% → 2 held out.
        assert split_holdout(10) == 2
        assert split_holdout(100) == 20

    def test_split_always_leaves_a_training_row(self):
        # Small datasets still get a non-empty train set and a non-empty eval set.
        assert split_holdout(2) == 1  # 1 train, 1 eval
        for n in range(2, 50):
            k = split_holdout(n)
            assert 1 <= k <= n - 1
            assert n - k >= 1  # at least one training row remains

    def test_split_holds_out_at_least_one(self):
        # 3 rows × 20% rounds to 1 → still hold out one (never zero) when n>=2.
        assert split_holdout(3) >= 1
        assert split_holdout(4) >= 1

    def test_single_row_dataset_holds_out_nothing(self):
        # Degenerate: nothing to hold out; caller falls back to the single row.
        assert split_holdout(1) == 0
        assert split_holdout(0) == 0

    def test_train_and_eval_slices_do_not_overlap(self):
        rows = list(range(20))
        k = split_holdout(len(rows))
        train, ev = rows[:-k], rows[-k:]
        assert set(train).isdisjoint(set(ev))
        assert train and ev
        assert train + ev == rows  # full coverage, no duplication


class TestResponseOnlyMasking:
    """Loss must be computed on response tokens only — prompt tokens masked to -100."""

    class _FakeTokenizer:
        """A whitespace tokenizer with stable integer ids; enough to assert masking."""

        def __init__(self):
            self._vocab = {}

        def _ids(self, text):
            out = []
            for tok in text.split():
                out.append(self._vocab.setdefault(tok, len(self._vocab) + 1))
            return out

        def __call__(self, text, return_tensors=None, truncation=False,
                     max_length=None, add_special_tokens=True):
            import torch
            ids = self._ids(text)
            if return_tensors == "pt":
                return {"input_ids": torch.tensor([ids])}
            return {"input_ids": ids}

    def test_render_prompt_ends_with_assistant_cue_without_answer(self):
        from brain.training.evaluator import ModelEvaluator
        messages = [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello there"},
        ]
        prompt, target = ModelEvaluator._render_prompt_and_target(messages)
        assert prompt.endswith("Assistant: ")
        assert "hello there" not in prompt  # the answer is NOT in the prompt
        assert target == "hello there"

    def test_prompt_tokens_are_masked_response_tokens_are_kept(self):
        import torch

        from brain.training.evaluator import ModelEvaluator
        ev = ModelEvaluator()
        tok = self._FakeTokenizer()
        messages = [
            {"role": "user", "content": "what is two plus two"},
            {"role": "assistant", "content": "four"},
        ]
        prompt, target = ev._render_prompt_and_target(messages)
        prompt_len = len(tok(prompt, add_special_tokens=False)["input_ids"])

        row = ev._tokenize_with_response_mask(tok, messages)
        labels = row["labels"][0]
        input_ids = row["input_ids"][0]

        assert input_ids.shape == labels.shape
        # Every prompt-position label is masked (-100); response positions are kept.
        assert torch.all(labels[:prompt_len] == -100)
        assert int((labels != -100).sum().item()) > 0  # some response tokens scored
        # Unmasked labels equal the underlying input ids (the response tokens).
        kept = labels != -100
        assert torch.all(labels[kept] == input_ids[kept])


class TestBaseVsAdapterDelta:
    """The result must carry the base-vs-adapter comparison (relative signal)."""

    def test_result_persists_base_score_and_delta(self):
        adapter_loss, base_loss = 0.3, 0.9
        score = score_from_loss(adapter_loss)
        base_score = score_from_loss(base_loss)
        result = EvaluationResult(
            eval_id="e2", job_id="j2", agent_id="a2", adapter_name="ad2",
            adapter_path="/p", dataset_path="/eval", num_examples=4,
            metrics=EvaluationMetrics(
                loss=adapter_loss, perplexity=math.exp(adapter_loss),
                base_loss=base_loss, base_perplexity=math.exp(base_loss),
                loss_improvement=base_loss - adapter_loss,
            ),
            score=score, base_score=base_score, score_delta=score - base_score,
            held_out=True,
        )
        # Fine-tune helped (lower loss → higher score → positive delta).
        assert result.score > result.base_score
        assert result.score_delta == pytest.approx(score - base_score)
        assert result.score_delta > 0
        assert result.metrics.loss_improvement == pytest.approx(base_loss - adapter_loss)

        # Round-trips through serialization without losing the comparison.
        rt = EvaluationResult.from_dict(result.to_dict())
        assert rt.base_score == pytest.approx(base_score)
        assert rt.score_delta == pytest.approx(result.score_delta)
        assert rt.held_out is True
        assert rt.metrics.base_loss == pytest.approx(base_loss)

    def test_gate_uses_absolute_score_not_delta(self, registry):
        # Even if the fine-tune improved over a terrible base, the ABSOLUTE floor holds:
        # a 0.5 adapter score that beats a 0.2 base still fails the 0.6 gate.
        adapter_loss = -math.log(0.5)  # → score 0.5
        score = score_from_loss(adapter_loss)
        assert score == pytest.approx(0.5)
        with pytest.raises(EvalGateFailed):
            registry.register(
                adapter_id="d1", project_id="p1", job_id="jd1",
                adapter_path="/data/adapters/d1", eval_score=score,
                base_model="qwen2.5-3b",
            )
