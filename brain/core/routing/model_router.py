"""
Model router for intelligent task-based model selection.

Automatically selects the optimal model based on task requirements.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from brain.core.routing.task_classifier import TaskRequirements, TaskType, TaskComplexity
from brain.core import model_manager

logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """Routing strategies."""
    OPTIMAL = "optimal"  # Best model for task
    FAST = "fast"  # Fastest available model
    ACCURATE = "accurate"  # Most accurate model
    BALANCED = "balanced"  # Balance speed and accuracy
    ECONOMICAL = "economical"  # Minimize resource usage


@dataclass
class ModelCapabilities:
    """Model capabilities and characteristics."""
    model_name: str
    model_type: str  # chat, code, vision, reasoning
    size_category: str  # small, medium, large, xlarge
    context_length: int
    speed_rating: int  # 1-10 (10 is fastest)
    accuracy_rating: int  # 1-10 (10 is most accurate)
    supports_code: bool = False
    supports_vision: bool = False
    supports_reasoning: bool = False
    supports_math: bool = False
    supports_creativity: bool = False
    languages: List[str] = field(default_factory=lambda: ["en"])
    specialties: List[str] = field(default_factory=list)

    def matches_requirements(self, requirements: TaskRequirements) -> float:
        """
        Calculate how well this model matches task requirements.

        Returns:
            Match score (0-1)
        """
        score = 0.0
        factors = 0

        # Task type matching
        if requirements.task_type in self._get_supported_tasks():
            score += 1.0
        factors += 1

        # Capability matching
        if requirements.requires_code and self.supports_code:
            score += 1.0
        elif requirements.requires_code and not self.supports_code:
            score -= 0.5
        factors += 1

        if requirements.requires_vision and self.supports_vision:
            score += 1.0
        elif requirements.requires_vision and not self.supports_vision:
            return 0.0  # Can't do vision tasks without vision
        factors += 1

        if requirements.requires_reasoning and self.supports_reasoning:
            score += 1.0
        factors += 1

        if requirements.requires_math and self.supports_math:
            score += 1.0
        factors += 1

        # Context length check
        if requirements.context_length <= self.context_length:
            score += 0.5
        else:
            score -= 0.5  # Penalize if context too long
        factors += 1

        # Language support
        if requirements.language in self.languages:
            score += 0.5
        factors += 1

        # Complexity matching
        complexity_scores = {
            TaskComplexity.SIMPLE: {"small": 1.0, "medium": 0.8, "large": 0.6, "xlarge": 0.4},
            TaskComplexity.MODERATE: {"small": 0.6, "medium": 1.0, "large": 0.8, "xlarge": 0.7},
            TaskComplexity.COMPLEX: {"small": 0.3, "medium": 0.7, "large": 1.0, "xlarge": 0.9},
            TaskComplexity.VERY_COMPLEX: {"small": 0.1, "medium": 0.5, "large": 0.8, "xlarge": 1.0},
        }
        score += complexity_scores[requirements.complexity].get(self.size_category, 0.5)
        factors += 1

        return max(0.0, min(1.0, score / factors))

    def _get_supported_tasks(self) -> List[TaskType]:
        """Get supported task types based on model type."""
        if "code" in self.model_type:
            return [
                TaskType.CODE_GENERATION,
                TaskType.CODE_REVIEW,
                TaskType.CODE_EXPLANATION,
                TaskType.DEBUGGING
            ]
        elif "vision" in self.model_type:
            return [TaskType.VISION]
        elif "reasoning" in self.model_type:
            return [
                TaskType.REASONING,
                TaskType.ANALYSIS,
                TaskType.MATH
            ]
        else:  # General chat models
            return [
                TaskType.GENERAL_CHAT,
                TaskType.QUESTION_ANSWERING,
                TaskType.SUMMARIZATION,
                TaskType.TRANSLATION,
                TaskType.CREATIVE_WRITING
            ]


@dataclass
class RoutingDecision:
    """Routing decision result."""
    selected_model: str
    match_score: float
    strategy_used: RoutingStrategy
    alternatives: List[Tuple[str, float]]  # (model, score) pairs
    reasoning: str


class ModelRouter:
    """
    Routes tasks to optimal models.

    Features:
    - Task-based selection
    - Multi-model support
    - Performance optimization
    - Fallback handling
    """

    def __init__(self, strategy: RoutingStrategy = RoutingStrategy.BALANCED):
        """
        Initialize model router.

        Args:
            strategy: Default routing strategy
        """
        self.strategy = strategy
        self.model_registry = self._initialize_model_registry()

    def _initialize_model_registry(self) -> Dict[str, ModelCapabilities]:
        """Initialize model capability registry."""
        registry = {
            # Qwen models
            "qwen2.5-3b": ModelCapabilities(
                model_name="qwen2.5-3b",
                model_type="chat",
                size_category="small",
                context_length=32768,
                speed_rating=9,
                accuracy_rating=6,
                supports_reasoning=True,
                supports_math=True,
                languages=["en", "zh"]
            ),
            "qwen2.5-7b": ModelCapabilities(
                model_name="qwen2.5-7b",
                model_type="chat",
                size_category="medium",
                context_length=32768,
                speed_rating=7,
                accuracy_rating=8,
                supports_reasoning=True,
                supports_math=True,
                supports_creativity=True,
                languages=["en", "zh"]
            ),
            "qwen2.5-14b": ModelCapabilities(
                model_name="qwen2.5-14b",
                model_type="chat",
                size_category="large",
                context_length=32768,
                speed_rating=5,
                accuracy_rating=9,
                supports_reasoning=True,
                supports_math=True,
                supports_creativity=True,
                languages=["en", "zh"]
            ),
            "qwen2.5-coder-3b": ModelCapabilities(
                model_name="qwen2.5-coder-3b",
                model_type="code",
                size_category="small",
                context_length=32768,
                speed_rating=9,
                accuracy_rating=7,
                supports_code=True,
                specialties=["code", "debugging"]
            ),
            "qwen2.5-coder-7b": ModelCapabilities(
                model_name="qwen2.5-coder-7b",
                model_type="code",
                size_category="medium",
                context_length=32768,
                speed_rating=7,
                accuracy_rating=9,
                supports_code=True,
                supports_reasoning=True,
                specialties=["code", "debugging", "architecture"]
            ),

            # Vision models
            "moondream2": ModelCapabilities(
                model_name="moondream2",
                model_type="vision",
                size_category="small",
                context_length=4096,
                speed_rating=8,
                accuracy_rating=7,
                supports_vision=True,
                specialties=["vision", "image_analysis"]
            ),

            # Llama models
            "llama-3.2-1b": ModelCapabilities(
                model_name="llama-3.2-1b",
                model_type="chat",
                size_category="small",
                context_length=128000,
                speed_rating=10,
                accuracy_rating=5,
                languages=["en"]
            ),
            "llama-3.2-3b": ModelCapabilities(
                model_name="llama-3.2-3b",
                model_type="chat",
                size_category="small",
                context_length=128000,
                speed_rating=9,
                accuracy_rating=6,
                languages=["en"]
            ),

            # Mistral models
            "mistral-7b": ModelCapabilities(
                model_name="mistral-7b",
                model_type="chat",
                size_category="medium",
                context_length=8192,
                speed_rating=7,
                accuracy_rating=8,
                supports_reasoning=True,
                languages=["en", "fr"]
            ),

            # Phi models
            "phi-2": ModelCapabilities(
                model_name="phi-2",
                model_type="chat",
                size_category="small",
                context_length=2048,
                speed_rating=10,
                accuracy_rating=6,
                supports_reasoning=True,
                supports_math=True
            ),
        }

        return registry

    def route(
        self,
        requirements: TaskRequirements,
        available_models: Optional[List[str]] = None,
        strategy: Optional[RoutingStrategy] = None
    ) -> RoutingDecision:
        """
        Route task to optimal model.

        Args:
            requirements: Task requirements
            available_models: List of available models
            strategy: Override default strategy

        Returns:
            Routing decision
        """
        strategy = strategy or self.strategy

        # Get available models
        if not available_models:
            available_models = list(self.model_registry.keys())

        # Score each model
        model_scores = []
        for model_name in available_models:
            if model_name in self.model_registry:
                capabilities = self.model_registry[model_name]
                base_score = capabilities.matches_requirements(requirements)

                # Apply strategy modifiers
                final_score = self._apply_strategy_modifiers(
                    base_score,
                    capabilities,
                    requirements,
                    strategy
                )

                model_scores.append((model_name, final_score))

        # Sort by score
        model_scores.sort(key=lambda x: x[1], reverse=True)

        if not model_scores:
            # Fallback to default
            return RoutingDecision(
                selected_model="qwen2.5-7b",
                match_score=0.5,
                strategy_used=strategy,
                alternatives=[],
                reasoning="No suitable models found, using default"
            )

        # Select best model
        selected_model, score = model_scores[0]
        alternatives = model_scores[1:4]  # Top 3 alternatives

        # Generate reasoning
        reasoning = self._generate_reasoning(
            selected_model,
            score,
            requirements,
            strategy
        )

        return RoutingDecision(
            selected_model=selected_model,
            match_score=score,
            strategy_used=strategy,
            alternatives=alternatives,
            reasoning=reasoning
        )

    def _apply_strategy_modifiers(
        self,
        base_score: float,
        capabilities: ModelCapabilities,
        requirements: TaskRequirements,
        strategy: RoutingStrategy
    ) -> float:
        """Apply strategy-specific score modifiers."""
        if strategy == RoutingStrategy.FAST:
            # Prioritize speed
            speed_modifier = capabilities.speed_rating / 10.0
            return base_score * 0.5 + speed_modifier * 0.5

        elif strategy == RoutingStrategy.ACCURATE:
            # Prioritize accuracy
            accuracy_modifier = capabilities.accuracy_rating / 10.0
            return base_score * 0.5 + accuracy_modifier * 0.5

        elif strategy == RoutingStrategy.ECONOMICAL:
            # Prioritize smaller models
            size_scores = {"small": 1.0, "medium": 0.7, "large": 0.4, "xlarge": 0.2}
            size_modifier = size_scores.get(capabilities.size_category, 0.5)
            return base_score * 0.7 + size_modifier * 0.3

        elif strategy == RoutingStrategy.BALANCED:
            # Balance all factors
            speed_mod = capabilities.speed_rating / 10.0
            accuracy_mod = capabilities.accuracy_rating / 10.0
            return base_score * 0.6 + speed_mod * 0.2 + accuracy_mod * 0.2

        else:  # OPTIMAL
            # Pure task matching
            return base_score

    def _generate_reasoning(
        self,
        selected_model: str,
        score: float,
        requirements: TaskRequirements,
        strategy: RoutingStrategy
    ) -> str:
        """Generate explanation for routing decision."""
        capabilities = self.model_registry.get(selected_model)
        if not capabilities:
            return "Model selected based on availability"

        reasons = []

        # Task type match
        if requirements.task_type == TaskType.CODE_GENERATION and capabilities.supports_code:
            reasons.append("Specialized for code generation")
        elif requirements.task_type == TaskType.VISION and capabilities.supports_vision:
            reasons.append("Vision capabilities required")
        elif requirements.task_type == TaskType.REASONING and capabilities.supports_reasoning:
            reasons.append("Strong reasoning capabilities")

        # Strategy-based reasoning
        if strategy == RoutingStrategy.FAST:
            reasons.append(f"Fast inference (speed: {capabilities.speed_rating}/10)")
        elif strategy == RoutingStrategy.ACCURATE:
            reasons.append(f"High accuracy (rating: {capabilities.accuracy_rating}/10)")
        elif strategy == RoutingStrategy.ECONOMICAL:
            reasons.append(f"Resource efficient ({capabilities.size_category} model)")

        # Complexity match
        if requirements.complexity == TaskComplexity.SIMPLE and capabilities.size_category == "small":
            reasons.append("Appropriate size for simple task")
        elif requirements.complexity == TaskComplexity.VERY_COMPLEX and capabilities.size_category in ["large", "xlarge"]:
            reasons.append("Large model for complex task")

        return f"Selected {selected_model}: {', '.join(reasons)}"

    def update_model_registry(
        self,
        model_name: str,
        capabilities: ModelCapabilities
    ):
        """
        Update or add model to registry.

        Args:
            model_name: Model identifier
            capabilities: Model capabilities
        """
        self.model_registry[model_name] = capabilities
        logger.info(f"Updated model registry for {model_name}")

    def get_model_info(self, model_name: str) -> Optional[ModelCapabilities]:
        """Get model capabilities."""
        return self.model_registry.get(model_name)

    def recommend_models(
        self,
        requirements: TaskRequirements,
        top_k: int = 3
    ) -> List[Tuple[str, float, str]]:
        """
        Recommend top models for task.

        Args:
            requirements: Task requirements
            top_k: Number of recommendations

        Returns:
            List of (model, score, reasoning) tuples
        """
        recommendations = []

        for strategy in [
            RoutingStrategy.OPTIMAL,
            RoutingStrategy.FAST,
            RoutingStrategy.ACCURATE
        ]:
            decision = self.route(requirements, strategy=strategy)
            recommendations.append((
                decision.selected_model,
                decision.match_score,
                f"{strategy.value}: {decision.reasoning}"
            ))

        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec[0] not in seen:
                seen.add(rec[0])
                unique_recommendations.append(rec)

        return unique_recommendations[:top_k]