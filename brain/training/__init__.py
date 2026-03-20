"""Training module for LoRA fine-tuning"""

from brain.training.models import (
    TrainingConfig,
    TrainingJob,
    TrainingStatus,
    TrainingMetrics,
    JobState,
)
from brain.training.trainer import trainer, LoRATrainer
from brain.training.job_manager import job_manager

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
