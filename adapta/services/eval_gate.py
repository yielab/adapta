"""CPU eval gate: task metrics through the serving path, adapter vs base (E4.3).

An imported adapter is scored on a held-out eval set by *generating* with it through the
same path the endpoint serves with (``LlamaCppBackend``: the model_manager load, the
catalog chat template, greedy decoding) and comparing the output with the reference using
a task metric. The base model is scored on the same rows; :func:`passes` decides.

Pure scoring only: nothing here touches the DB or the job queue (the worker runs it, E4.4).
``model_manager`` and the inference engine are used, never changed.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from adapta.config import settings

TASKS = ("classify", "extract", "freeform")

# Which rule decided a verdict (persisted in eval_metrics["rule"]).
RULE_IMPROVEMENT = "improvement"
RULE_ABSOLUTE_FLOOR = "absolute_floor"
RULE_FAILED = "failed"

SAMPLES_KEPT = 5
_SAMPLE_CHARS = 200
_EPS = 1e-9


# ---------------------------------------------------------------------------
# Metrics (pure)
# ---------------------------------------------------------------------------


def _norm_label(text: str) -> str:
    return text.strip().lower()


def classify_score(prediction: str, reference: str) -> float:
    """Label accuracy after strip/lower: 1.0 on a match, else 0.0."""
    return 1.0 if _norm_label(prediction) == _norm_label(reference) else 0.0


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_json_object(text: str) -> Optional[dict]:
    """Parse ``text`` as a JSON object (tolerating one ``` fence); None if it is not one."""
    body = text.strip()
    m = _FENCE.match(body)
    if m:
        body = m.group(1)
    try:
        value = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def key_match(prediction: dict, reference: dict) -> float:
    """Fraction of the reference's keys whose value the prediction reproduces exactly."""
    if not reference:
        return 1.0
    hits = sum(1 for k, v in reference.items() if k in prediction and prediction[k] == v)
    return hits / len(reference)


def token_f1(prediction: str, reference: str) -> float:
    """Bag-of-tokens F1 (lower-cased word tokens), the usual QA-style overlap score."""
    pred = re.findall(r"\w+", prediction.lower())
    ref = re.findall(r"\w+", reference.lower())
    if not pred or not ref:
        return 1.0 if not pred and not ref else 0.0
    ref_counts: dict[str, int] = {}
    for t in ref:
        ref_counts[t] = ref_counts.get(t, 0) + 1
    common = 0
    for t in pred:
        if ref_counts.get(t, 0) > 0:
            ref_counts[t] -= 1
            common += 1
    if common == 0:
        return 0.0
    precision = common / len(pred)
    recall = common / len(ref)
    return 2 * precision * recall / (precision + recall)


def aggregate(task: str, predictions: Sequence[str], references: Sequence[str]) -> tuple[float, list[float], dict]:
    """Aggregate score for a task, per-row scores, and task-specific extras.

    * ``classify``: mean label accuracy.
    * ``extract``: JSON-parse rate x mean per-key exact match over the rows that parsed.
    * ``freeform``: mean token F1.
    """
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {TASKS}")
    n = len(references)
    if n == 0:
        return 0.0, [], {}

    if task == "classify":
        per_row = [classify_score(p, r) for p, r in zip(predictions, references, strict=True)]
        return sum(per_row) / n, per_row, {}

    if task == "freeform":
        per_row = [token_f1(p, r) for p, r in zip(predictions, references, strict=True)]
        return sum(per_row) / n, per_row, {}

    per_row = []
    matches: list[float] = []
    for pred, ref in zip(predictions, references, strict=True):
        ref_obj = parse_json_object(ref) or {}
        pred_obj = parse_json_object(pred)
        if pred_obj is None:
            per_row.append(0.0)
            continue
        m = key_match(pred_obj, ref_obj)
        matches.append(m)
        per_row.append(m)
    parse_rate = len(matches) / n
    mean_match = sum(matches) / len(matches) if matches else 0.0
    return parse_rate * mean_match, per_row, {"parse_rate": parse_rate, "key_match": mean_match}


# ---------------------------------------------------------------------------
# Scoring through the serving path
# ---------------------------------------------------------------------------


@dataclass
class TaskScore:
    """One model variant's result on an eval set."""

    task: str
    score: float
    n_rows: int
    seconds: float
    predictions: list[str] = field(default_factory=list)
    row_scores: list[float] = field(default_factory=list)
    extras: dict[str, float] = field(default_factory=dict)

    @property
    def seconds_per_row(self) -> float:
        return self.seconds / self.n_rows if self.n_rows else 0.0


async def score(
    base_model: str,
    gguf_lora_path: Optional[str],
    rows: Sequence[dict],
    task: str,
) -> TaskScore:
    """Score ``base_model`` (+ the GGUF LoRA at ``gguf_lora_path``, or None for the bare
    base) on SFT ``rows`` (``prompt``/``response``/optional ``system``).

    Greedy generation through :class:`LlamaCppBackend`, so the prompt is rendered by the
    model's catalog chat template and the model is loaded by ``model_manager`` exactly as
    when the endpoint serves it. Raises ``ModelNotFound`` if the model or adapter cannot
    be loaded.
    """
    from adapta.core.backends.llamacpp import LlamaCppBackend
    from adapta.core.inference import InferenceRequest, Message

    backend = LlamaCppBackend()
    handle = await backend.prepare(base_model, gguf_lora_path)

    predictions: list[str] = []
    started = time.perf_counter()
    for row in rows:
        request = InferenceRequest(
            messages=[Message(role="user", content=row["prompt"])],
            model_name=base_model,
            temperature=0.0,
            top_p=1.0,
            top_k=1,
            max_tokens=settings.eval_max_new_tokens,
            stream=False,
            system_prompt=row.get("system") or None,
            adapter_path=gguf_lora_path,
        )
        response = await backend.generate(handle, request)
        predictions.append(response.content)
    seconds = time.perf_counter() - started

    value, per_row, extras = aggregate(task, predictions, [r["response"] for r in rows])
    return TaskScore(
        task=task,
        score=value,
        n_rows=len(rows),
        seconds=seconds,
        predictions=predictions,
        row_scores=per_row,
        extras=extras,
    )


# ---------------------------------------------------------------------------
# The gate rule
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    passed: bool
    rule: str  # RULE_IMPROVEMENT | RULE_ABSOLUTE_FLOOR | RULE_FAILED
    adapter_score: float
    base_score: float
    delta: float


def passes(adapter: float, base: float) -> Decision:
    """The gate rule: adapter >= base + ``eval_min_improvement`` **or**
    (adapter >= ``eval_absolute_floor`` **and** adapter >= base)."""
    delta = adapter - base
    if delta >= settings.eval_min_improvement - _EPS:
        rule = RULE_IMPROVEMENT
    elif adapter >= settings.eval_absolute_floor - _EPS and delta >= -_EPS:
        rule = RULE_ABSOLUTE_FLOOR
    else:
        rule = RULE_FAILED
    return Decision(
        passed=rule != RULE_FAILED,
        rule=rule,
        adapter_score=adapter,
        base_score=base,
        delta=delta,
    )


def _clip(text: str) -> str:
    return text if len(text) <= _SAMPLE_CHARS else text[:_SAMPLE_CHARS] + "..."


def build_metrics(
    rows: Sequence[dict], adapter: TaskScore, base: TaskScore, decision: Decision
) -> dict[str, Any]:
    """The persisted ``eval_metrics`` document (JSON-serializable).

    ``{task, n_rows, adapter_score, base_score, delta, rule, passed, min_improvement,
    absolute_floor, adapter_extras, base_extras, adapter_seconds_per_row,
    base_seconds_per_row, samples: [{prompt, reference, base, adapter} x5]}``
    """
    n = len(rows)
    step = max(n // SAMPLES_KEPT, 1)
    picked = list(range(0, n, step))[:SAMPLES_KEPT]
    samples = [
        {
            "prompt": _clip(rows[i]["prompt"]),
            "reference": _clip(rows[i]["response"]),
            "base": _clip(base.predictions[i]),
            "adapter": _clip(adapter.predictions[i]),
        }
        for i in picked
    ]
    return {
        "task": adapter.task,
        "n_rows": n,
        "adapter_score": decision.adapter_score,
        "base_score": decision.base_score,
        "delta": decision.delta,
        "rule": decision.rule,
        "passed": decision.passed,
        "min_improvement": settings.eval_min_improvement,
        "absolute_floor": settings.eval_absolute_floor,
        "adapter_extras": adapter.extras,
        "base_extras": base.extras,
        "adapter_seconds_per_row": adapter.seconds_per_row,
        "base_seconds_per_row": base.seconds_per_row,
        "samples": samples,
    }


async def evaluate(
    base_model: str, gguf_lora_path: str, rows: Sequence[dict], task: str
) -> dict[str, Any]:
    """Score base and adapter on the same rows and return the ``eval_metrics`` document."""
    base = await score(base_model, None, rows, task)
    adapter = await score(base_model, gguf_lora_path, rows, task)
    decision = passes(adapter.score, base.score)
    return build_metrics(rows, adapter, base, decision)


__all__ = [
    "TASKS",
    "TaskScore",
    "Decision",
    "score",
    "passes",
    "evaluate",
    "build_metrics",
    "aggregate",
]
