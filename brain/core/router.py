"""
Smart Router - Main interface for intelligent model routing.

This module provides the main interface for the routing system as specified in the roadmap.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from brain.core.routing import (
    TaskClassifier,
    TaskType,
    TaskComplexity,
    ModelRouter,
    RoutingStrategy,
    RoutingDecision
)
from brain.core import model_manager

logger = logging.getLogger(__name__)


class SmartRouter:
    """
    Smart router for automatic model selection.

    As specified in the roadmap:
    - Task classification
    - Automatic model selection
    - Code → qwen2.5-coder-3b
    - Complex → qwen2.5-7b
    - Vision → moondream2
    - Fast → qwen2.5-3b

    Success: Optimal model for every task
    """

    def __init__(self, default_strategy: RoutingStrategy = RoutingStrategy.BALANCED):
        """
        Initialize smart router.

        Args:
            default_strategy: Default routing strategy
        """
        self.classifier = TaskClassifier()
        self.router = ModelRouter(strategy=default_strategy)
        self.routing_history: List[Dict[str, Any]] = []
        self.performance_stats: Dict[str, Dict[str, float]] = {}

    async def route_task(
        self,
        text: str,
        context: Optional[List[Dict[str, str]]] = None,
        strategy: Optional[RoutingStrategy] = None,
        prefer_local: bool = True
    ) -> Dict[str, Any]:
        """
        Route a task to the optimal model.

        Args:
            text: Task text
            context: Conversation context
            strategy: Override routing strategy
            prefer_local: Prefer locally available models

        Returns:
            Routing result with selected model and metadata
        """
        # Classify the task
        requirements = self.classifier.classify(text, context)

        # Get available models
        available_models = None
        if prefer_local:
            available_models = await self._get_available_local_models()

        # Route to optimal model
        decision = self.router.route(requirements, available_models, strategy)

        # Record routing decision
        routing_record = {
            "text": text[:200],  # Truncate for storage
            "requirements": requirements.to_dict(),
            "decision": {
                "model": decision.selected_model,
                "score": decision.match_score,
                "strategy": decision.strategy_used.value,
                "reasoning": decision.reasoning
            },
            "alternatives": decision.alternatives
        }

        self.routing_history.append(routing_record)

        # Update performance tracking
        self._update_performance_stats(decision.selected_model, requirements.task_type)

        logger.info(f"Routed task to {decision.selected_model}: {decision.reasoning}")

        return {
            "model": decision.selected_model,
            "task_type": requirements.task_type.value,
            "complexity": requirements.complexity.value,
            "reasoning": decision.reasoning,
            "confidence": decision.match_score,
            "alternatives": [
                {"model": m, "score": s}
                for m, s in decision.alternatives
            ]
        }

    async def _get_available_local_models(self) -> List[str]:
        """Get list of locally available models."""
        try:
            # Get loaded models from model manager
            loaded_models = model_manager.list_loaded_models()

            # Get available models from catalog
            from brain.core.model_catalog import ModelCatalog
            from brain.config import settings
            catalog = ModelCatalog(settings.models_dir)
            installed_models = [m["id"] for m in catalog.get_installed_models()]

            # Combine and deduplicate
            all_models = list(set(loaded_models + installed_models))

            return all_models
        except Exception as e:
            logger.warning(f"Could not get local models: {e}")
            return []

    def _update_performance_stats(self, model: str, task_type: TaskType):
        """Update performance statistics."""
        if model not in self.performance_stats:
            self.performance_stats[model] = {}

        task_key = task_type.value
        if task_key not in self.performance_stats[model]:
            self.performance_stats[model][task_key] = 0

        self.performance_stats[model][task_key] += 1

    def get_routing_stats(self) -> Dict[str, Any]:
        """
        Get routing statistics.

        Returns:
            Statistics about routing decisions
        """
        total_routes = len(self.routing_history)

        # Model usage distribution
        model_usage = {}
        for record in self.routing_history:
            model = record["decision"]["model"]
            model_usage[model] = model_usage.get(model, 0) + 1

        # Task type distribution
        task_distribution = {}
        for record in self.routing_history:
            task_type = record["requirements"]["task_type"]
            task_distribution[task_type] = task_distribution.get(task_type, 0) + 1

        # Average confidence
        if self.routing_history:
            avg_confidence = sum(
                r["decision"]["score"] for r in self.routing_history
            ) / total_routes
        else:
            avg_confidence = 0

        return {
            "total_routes": total_routes,
            "model_usage": model_usage,
            "task_distribution": task_distribution,
            "average_confidence": avg_confidence,
            "performance_by_model": self.performance_stats
        }

    def get_model_recommendations(
        self,
        text: str,
        context: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get model recommendations for a task.

        Args:
            text: Task text
            context: Conversation context

        Returns:
            List of model recommendations with scores
        """
        # Classify task
        requirements = self.classifier.classify(text, context)

        # Get recommendations
        recommendations = self.router.recommend_models(requirements)

        return [
            {
                "model": model,
                "score": score,
                "reasoning": reasoning
            }
            for model, score, reasoning in recommendations
        ]

    def update_model_capabilities(
        self,
        model_name: str,
        capabilities: Dict[str, Any]
    ):
        """
        Update model capabilities in the router.

        Args:
            model_name: Model to update
            capabilities: New capabilities
        """
        from brain.core.routing.model_router import ModelCapabilities

        model_cap = ModelCapabilities(
            model_name=model_name,
            **capabilities
        )

        self.router.update_model_registry(model_name, model_cap)

    def clear_history(self):
        """Clear routing history."""
        self.routing_history.clear()
        self.performance_stats.clear()


# Global router instance
_smart_router: Optional[SmartRouter] = None


def get_smart_router() -> SmartRouter:
    """
    Get the global smart router instance.

    Returns:
        SmartRouter instance
    """
    global _smart_router
    if _smart_router is None:
        _smart_router = SmartRouter()
    return _smart_router


# Convenience functions as specified in roadmap
async def route_to_optimal_model(
    text: str,
    context: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Route task to optimal model (convenience function).

    Args:
        text: Task text
        context: Conversation context

    Returns:
        Selected model name
    """
    router = get_smart_router()
    result = await router.route_task(text, context)
    return result["model"]