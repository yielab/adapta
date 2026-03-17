"""Training data models and schemas"""

import time
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json


class JobState(str, Enum):
    """Training job states"""

    QUEUED = "queued"
    PREPARING = "preparing"
    TRAINING = "training"
    EVALUATING = "evaluating"
    SAVING = "saving"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
class TrainingMetrics:
    """Training metrics at a point in time"""

    step: int
    epoch: int
    loss: float
    learning_rate: float
    grad_norm: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    # Optional evaluation metrics
    eval_loss: Optional[float] = None
    perplexity: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class TrainingStatus:
    """Current status of training job"""

    job_id: str
    state: JobState
    progress: float  # 0.0 to 1.0

    # Progress details
    current_step: int = 0
    total_steps: int = 0
    current_epoch: int = 0
    total_epochs: int = 0

    # Latest metrics
    current_loss: Optional[float] = None
    current_lr: Optional[float] = None

    # Timing
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    estimated_time_remaining: Optional[float] = None

    # Error info if failed
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = asdict(self)
        result["state"] = self.state.value
        return result

    @property
    def is_active(self) -> bool:
        """Check if job is actively running"""
        return self.state in [JobState.PREPARING, JobState.TRAINING, JobState.EVALUATING]

    @property
    def is_finished(self) -> bool:
        """Check if job is finished (completed, failed, or cancelled)"""
        return self.state in [JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED]


@dataclass
class TrainingJob:
    """Training job configuration and metadata"""

    job_id: str
    agent_id: str
    base_model: str
    dataset_path: Path
    adapter_name: str
    config: TrainingConfig

    # Metadata
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Status
    state: JobState = JobState.QUEUED
    progress: float = 0.0

    # Metrics history
    metrics: List[TrainingMetrics] = field(default_factory=list)

    # Output paths
    output_dir: Optional[Path] = None
    adapter_path: Optional[Path] = None

    # Error tracking
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "job_id": self.job_id,
            "agent_id": self.agent_id,
            "base_model": self.base_model,
            "dataset_path": str(self.dataset_path),
            "adapter_name": self.adapter_name,
            "config": self.config.to_dict(),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "state": self.state.value,
            "progress": self.progress,
            "metrics": [m.to_dict() for m in self.metrics],
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "adapter_path": str(self.adapter_path) if self.adapter_path else None,
            "error_message": self.error_message,
            "error_traceback": self.error_traceback,
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingJob":
        """Create from dictionary"""
        data = data.copy()
        data["dataset_path"] = Path(data["dataset_path"])
        data["config"] = TrainingConfig.from_dict(data["config"])
        data["state"] = JobState(data["state"])
        data["metrics"] = [TrainingMetrics(**m) for m in data.get("metrics", [])]
        if data.get("output_dir"):
            data["output_dir"] = Path(data["output_dir"])
        if data.get("adapter_path"):
            data["adapter_path"] = Path(data["adapter_path"])
        return cls(**data)

    def save(self, path: Path):
        """Save job to disk"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "TrainingJob":
        """Load job from disk"""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)

    def get_status(self) -> TrainingStatus:
        """Get current status"""
        total_steps = (
            (len(self.metrics) // self.config.logging_steps) * self.config.num_epochs
            if self.metrics
            else self.config.num_epochs * 100  # Estimate
        )

        current_step = len(self.metrics)
        current_epoch = current_step // (total_steps // self.config.num_epochs) if total_steps > 0 else 0

        # Get latest metrics
        current_loss = self.metrics[-1].loss if self.metrics else None
        current_lr = self.metrics[-1].learning_rate if self.metrics else None

        # Estimate time remaining
        estimated_time_remaining = None
        if self.started_at and current_step > 0 and total_steps > 0:
            elapsed = time.time() - self.started_at
            time_per_step = elapsed / current_step
            remaining_steps = total_steps - current_step
            estimated_time_remaining = time_per_step * remaining_steps

        return TrainingStatus(
            job_id=self.job_id,
            state=self.state,
            progress=self.progress,
            current_step=current_step,
            total_steps=total_steps,
            current_epoch=current_epoch,
            total_epochs=self.config.num_epochs,
            current_loss=current_loss,
            current_lr=current_lr,
            started_at=self.started_at,
            completed_at=self.completed_at,
            estimated_time_remaining=estimated_time_remaining,
            error_message=self.error_message,
        )

    def add_metrics(self, metrics: TrainingMetrics):
        """Add training metrics"""
        self.metrics.append(metrics)

        # Update progress
        if self.config.num_epochs > 0:
            self.progress = metrics.epoch / self.config.num_epochs


@dataclass
class TrainingDataset:
    """Training dataset metadata"""

    name: str
    agent_id: str
    file_path: Path
    created_at: float = field(default_factory=time.time)

    # Dataset stats
    num_examples: int = 0
    num_tokens: int = 0
    avg_tokens_per_example: float = 0.0

    # Validation
    is_valid: bool = False
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "agent_id": self.agent_id,
            "file_path": str(self.file_path),
            "created_at": self.created_at,
            "num_examples": self.num_examples,
            "num_tokens": self.num_tokens,
            "avg_tokens_per_example": self.avg_tokens_per_example,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
        }


@dataclass
class EvaluationMetrics:
    """Evaluation metrics for a trained adapter"""

    # Core metrics
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
