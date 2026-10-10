"""E4.3 eval gate — metric math, the pass rule, the eval-set contract (offline)."""

import json

import pytest

from adapta.config import settings
from adapta.domain.errors import InvalidRequest
from adapta.services import eval_gate
from adapta.services.datasets import check_eval_set_size, check_task, validate_dataset
from adapta.services.eval_gate import aggregate, passes, token_f1

# ── metrics ─────────────────────────────────────────────────────────────────


def test_classify_is_strip_lower_accuracy():
    score, per_row, _ = aggregate(
        "classify",
        [" Billing\n", "technical", "account", "x"],
        ["billing", "Technical", "billing", "y"],
    )
    assert per_row == [1.0, 1.0, 0.0, 0.0]
    assert score == 0.5


def test_extract_is_parse_rate_times_key_match():
    refs = [json.dumps({"a": 1, "b": "x"})] * 4
    preds = [
        json.dumps({"a": 1, "b": "x"}),  # 2/2
        json.dumps({"a": 1, "b": "nope"}),  # 1/2
        "not json at all",  # unparsed
        "```json\n" + json.dumps({"a": 1, "b": "x"}) + "\n```",  # fenced, 2/2
    ]
    score, per_row, extras = aggregate("extract", preds, refs)
    assert extras["parse_rate"] == 0.75
    assert extras["key_match"] == pytest.approx((1 + 0.5 + 1) / 3)
    assert score == pytest.approx(0.75 * (2.5 / 3))
    assert per_row == [1.0, 0.5, 0.0, 1.0]


def test_extract_non_object_is_unparsed():
    score, _, extras = aggregate("extract", ["[1, 2]"], ['{"a": 1}'])
    assert score == 0.0 and extras["parse_rate"] == 0.0


def test_token_f1():
    assert token_f1("the cat sat", "the cat sat") == 1.0
    assert token_f1("dog", "cat") == 0.0
    # 2 common of 3 predicted / 2 reference -> P=2/3, R=1 -> F1=0.8
    assert token_f1("the cat sat", "The cat") == pytest.approx(0.8)
    assert token_f1("", "") == 1.0 and token_f1("", "x") == 0.0
    # repeated tokens only count as often as the reference has them
    assert token_f1("a a a", "a") == pytest.approx(0.5)


def test_freeform_aggregate_and_unknown_task():
    score, _, _ = aggregate("freeform", ["a b", "c"], ["a b", "d"])
    assert score == 0.5
    with pytest.raises(ValueError):
        aggregate("perplexity", ["a"], ["a"])


# ── rule ────────────────────────────────────────────────────────────────────


def test_rule_improvement_path():
    d = passes(0.65, 0.60)  # exactly +0.05
    assert d.passed and d.rule == "improvement"
    assert d.delta == pytest.approx(0.05)


def test_rule_absolute_floor_path():
    d = passes(0.85, 0.83)  # +0.02 only, but strong and not worse
    assert d.passed and d.rule == "absolute_floor"
    assert passes(0.85, 0.85).rule == "absolute_floor"


def test_rule_fails():
    assert not passes(0.62, 0.60).passed  # small gain, below floor
    assert not passes(0.79, 0.79).passed  # just under the floor, no gain
    d = passes(0.85, 0.95)  # strong but worse than base
    assert not d.passed and d.rule == "failed"
    assert not passes(0.0, 0.0).passed


def test_rule_uses_settings(monkeypatch):
    monkeypatch.setattr(settings, "eval_min_improvement", 0.2)
    assert not passes(0.65, 0.60).passed
    monkeypatch.setattr(settings, "eval_absolute_floor", 0.5)
    assert passes(0.55, 0.55).rule == "absolute_floor"


def test_build_metrics_shape():
    rows = [{"prompt": f"p{i}", "response": f"r{i}"} for i in range(20)]
    base = eval_gate.TaskScore("freeform", 0.1, 20, 4.0, ["x"] * 20, [0.1] * 20)
    ad = eval_gate.TaskScore("freeform", 0.9, 20, 5.0, ["r"] * 20, [0.9] * 20)
    m = eval_gate.build_metrics(rows, ad, base, passes(ad.score, base.score))
    json.dumps(m)  # JSON-serializable
    assert m["passed"] and m["rule"] == "improvement" and len(m["samples"]) == 5
    assert m["delta"] == pytest.approx(0.8) and m["adapter_seconds_per_row"] == 0.25
    assert set(m["samples"][0]) == {"prompt", "reference", "base", "adapter"}


# ── eval-set contract ───────────────────────────────────────────────────────


def _write(path, n):
    path.write_text(
        "\n".join(json.dumps({"prompt": f"q{i}", "response": f"a{i}"}) for i in range(n)) + "\n"
    )
    return path


@pytest.mark.parametrize("n", [10, 19, 201])
def test_eval_set_size_rejected(tmp_path, n):
    with pytest.raises(InvalidRequest) as exc:
        check_eval_set_size(_write(tmp_path / "e.jsonl", n))
    assert str(n) in exc.value.message and exc.value.status == 400


@pytest.mark.parametrize("n", [20, 200])
def test_eval_set_size_accepted(tmp_path, n):
    assert check_eval_set_size(_write(tmp_path / "e.jsonl", n)) == n


def test_task_must_be_known():
    for t in ("classify", "extract", "freeform"):
        assert check_task(t) == t
    with pytest.raises(InvalidRequest):
        check_task("perplexity")


def test_extract_dataset_needs_json_responses(tmp_path):
    p = _write(tmp_path / "e.jsonl", 3)  # responses are "a0", "a1", ...
    ok, err, _ = validate_dataset(p, "extract")
    assert not ok and "JSON object" in err
    assert validate_dataset(p, "classify")[0]
    p.write_text(json.dumps({"prompt": "q", "response": '{"k": 1}'}) + "\n")
    assert validate_dataset(p, "extract") == (True, None, 1)
