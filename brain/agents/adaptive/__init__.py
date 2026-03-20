"""
Adaptive Agent Evolution module.

Provides self-improving agents with:
- Feedback collection
- Auto-triggered fine-tuning
- A/B testing
- Seamless version switching
"""

from brain.agents.adaptive.feedback_collector import (
    FeedbackCollector,
    FeedbackType,
    FeedbackEntry,
    FeedbackAnalysis
)

from brain.agents.adaptive.evolution_manager import (
    EvolutionManager,
    EvolutionStrategy,
    VersionManager,
    AdaptiveAgent
)

from brain.agents.adaptive.ab_testing import (
    ABTestManager,
    TestVariant,
    TestResult,
    PerformanceMetrics
)

__all__ = [
    "FeedbackCollector",
    "FeedbackType",
    "FeedbackEntry",
    "FeedbackAnalysis",
    "EvolutionManager",
    "EvolutionStrategy",
    "VersionManager",
    "AdaptiveAgent",
    "ABTestManager",
    "TestVariant",
    "TestResult",
    "PerformanceMetrics",
]