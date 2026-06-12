"""Training data models and schemas"""

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def score_from_loss(avg_loss: float) -> float:
    """Map an average cross-entropy loss to an eval score in [0, 1] (higher = better).

    ``score = 1 / perplexity = exp(-avg_loss)``. A perfect next-token predictor
    (loss → 0) scores 1.0; the score decays as loss grows. This is the intrinsic
    language-model signal the evaluator can compute without a task-specific metric,
    and it is what the eval **gate** (``eval_score_threshold``, default 0.6) tests:
    0.6 ⇔ perplexity ≤ ~1.67. Clamped to [0, 1] to be safe against tiny negatives.

    METRIC SEMANTICS (the gate's meaning — see also specs/schemas/training_dataset.schema.json):
    The loss this score is built from is the **response-only** cross-entropy on a
    **held-out** split (rows the model never trained on), with prompt tokens masked
    out. So ``score`` measures how well the fine-tune *generalizes* at producing the
    target responses, not how well it memorized the training rows. The evaluator also
    scores the **base** model on the same held-out split and reports the
    adapter-minus-base delta (``score_delta``) so an operator can see whether the
    fine-tune actually helped; the 0.6 gate itself remains an absolute floor on the
    adapter's response-only score.
    """
    if not math.isfinite(avg_loss):
        return 0.0
    return max(0.0, min(1.0, math.exp(-avg_loss)))


def passes_eval_gate(
    score: float,
    base_score: Optional[float] = None,
    score_delta: Optional[float] = None,
    *,
    threshold: Optional[float] = None,
    min_improvement: Optional[float] = None,
    min_floor: Optional[float] = None,
) -> bool:
    """The eval gate: may this adapter back an endpoint?

    Two ways to pass (the moat verifies the fine-tune is *good*, not just that it
    hit one strict number):

    1. **Absolute** — ``score >= threshold`` (a strong adapter), the original gate.
    2. **Improvement** — the adapter clears a low sanity floor AND beats the base
       model on the same held-out split by ``min_improvement``. ``score`` here is
       ``exp(-held_out_response_perplexity)``, which a small base model can't push
       to 0.6 even on an ideal task; an adapter that reliably out-scores its base by
       a clear margin has demonstrably learned the target behavior (§A3.2).

    A non-improving or garbage adapter passes neither and stays blocked.
    """
    from brain.config import settings

    threshold = settings.eval_score_threshold if threshold is None else threshold
    min_improvement = settings.eval_min_improvement if min_improvement is None else min_improvement
    min_floor = settings.eval_min_floor if min_floor is None else min_floor

    if score >= threshold:
        return True
    if base_score is not None and score_delta is not None:
        return score >= min_floor and score_delta >= min_improvement
    return False


def split_holdout(n: int, holdout_fraction: float = 0.2, min_holdout: int = 1) -> int:
    """Return the number of trailing rows to hold out for evaluation.

    The eval gate must measure **generalization**, so the model is scored on rows it
    never trained on. We hold out the **last** ``holdout_fraction`` of the dataset
    (deterministic, no shuffling needed — order is the operator's) and train on the
    rest. Guarantees at least ``min_holdout`` eval row and at least one training row
    whenever ``n >= 2``; for a degenerate ``n == 1`` dataset there is nothing to hold
    out, so it returns 0 (the caller falls back to evaluating on the single row and
    the absolute floor still applies).
    """
    if n <= 1:
        return 0
    k = int(round(n * holdout_fraction))
    k = max(min_holdout, k)
    k = min(k, n - 1)  # always leave at least one training row
    return k


@dataclass
class TrainingConfig:
    """Configuration for LoRA training"""

    # LoRA parameters
    lora_r: int = 16  # Rank
    lora_alpha: int = 32  # Scaling factor
    lora_dropout: float = 0.05
    target_modules: List[str] = field(
        default_factory=lambda: ["q_proj", "v_proj", "k_proj", "o_proj"]
    )

    # Training parameters
    num_epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 2e-4
    warmup_steps: int = 100
    gradient_accumulation_steps: int = 4
    max_seq_length: int = 2048

    # Determinism / reproducibility (A4.7) — recorded into the training provenance.
    seed: int = 42

    # Optimizer
    optimizer: str = "adamw_torch"
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0

    # Advanced options
    use_qlora: bool = True  # 4-bit quantization for memory efficiency
    gradient_checkpointing: bool = True
    logging_steps: int = 10
    eval_steps: int = 100
    save_steps: int = 500

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingConfig":
        """Create from dictionary"""
        return cls(**data)


@dataclass
class EvaluationMetrics:
    """Evaluation metrics for a trained adapter"""

    # Core metrics — RESPONSE-ONLY cross-entropy on the HELD-OUT split (prompt
    # tokens masked). This is the signal the eval gate scores; see score_from_loss.
    loss: float
    perplexity: float

    # Accuracy metrics
    accuracy: Optional[float] = None
    exact_match: Optional[float] = None

    # Token-level metrics
    token_accuracy: Optional[float] = None
    bleu_score: Optional[float] = None

    # Quality metrics
    coherence_score: Optional[float] = None
    fluency_score: Optional[float] = None

    # Base-vs-adapter comparison on the SAME held-out split (relative signal).
    # base_loss/base_perplexity are the un-adapted base model's response-only loss;
    # loss_improvement = base_loss - loss (positive ⇒ the fine-tune helped).
    base_loss: Optional[float] = None
    base_perplexity: Optional[float] = None
    loss_improvement: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class EvaluationResult:
    """Complete evaluation result for an adapter"""

    eval_id: str
    job_id: str
    agent_id: str
    adapter_name: str
    adapter_path: str

    # Dataset info
    dataset_path: str
    num_examples: int

    # Metrics
    metrics: EvaluationMetrics

    # Overall eval score in [0, 1] (higher = better), derived from the RESPONSE-ONLY
    # held-out loss via score_from_loss(). This is the value the eval gate compares to
    # the threshold (the absolute floor).
    score: float = 0.0

    # The base (un-adapted) model's score on the SAME held-out split, and the delta.
    # score_delta = score - base_score; positive ⇒ the fine-tune improved over base.
    # Reported for operator insight; the gate still uses the absolute `score`.
    base_score: Optional[float] = None
    score_delta: Optional[float] = None

    # Whether the eval ran on a held-out split (vs. fell back to the full dataset for
    # a degenerate single-row dataset). Lets the gate's meaning be read honestly.
    held_out: bool = True

    # Sample predictions (for debugging/inspection)
    sample_predictions: List[Dict[str, str]] = field(default_factory=list)

    # Metadata
    created_at: float = field(default_factory=time.time)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "eval_id": self.eval_id,
            "job_id": self.job_id,
            "agent_id": self.agent_id,
            "adapter_name": self.adapter_name,
            "adapter_path": self.adapter_path,
            "dataset_path": self.dataset_path,
            "num_examples": self.num_examples,
            "metrics": self.metrics.to_dict(),
            "score": self.score,
            "base_score": self.base_score,
            "score_delta": self.score_delta,
            "held_out": self.held_out,
            "sample_predictions": self.sample_predictions,
            "created_at": self.created_at,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationResult":
        """Create from dictionary"""
        data = data.copy()
        data["metrics"] = EvaluationMetrics(**data["metrics"])
        return cls(**data)
