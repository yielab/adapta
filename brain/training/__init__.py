"""Training module for LoRA fine-tuning"""

from brain.training.job_manager import job_manager
from brain.training.models import (
    JobState,
    TrainingConfig,
    TrainingJob,
    TrainingMetrics,
    TrainingStatus,
)
from brain.training.trainer import LoRATrainer, trainer

# Alias for compatibility
training_manager = job_manager

__all__ = [
    "TrainingConfig",
    "TrainingJob",
    "TrainingStatus",
    "TrainingMetrics",
    "JobState",
    "trainer",
    "LoRATrainer",
    "job_manager",
    "training_manager",
]
