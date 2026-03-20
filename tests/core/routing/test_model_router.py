"""
Tests for model routing system.
"""

import pytest

from brain.core.routing.model_router import (
    ModelRouter,
    RoutingStrategy,
    ModelCapabilities,
    RoutingDecision
)
from brain.core.routing.task_classifier import (
    TaskRequirements,
    TaskType,
    TaskComplexity
)


class TestModelCapabilities:
    """Test model capabilities functionality."""

    def test_capability_matching(self):
        """Test capability matching with requirements."""
        # Create a code model
        code_model = ModelCapabilities(
            model_name="test-coder",
            model_type="code",
            size_category="medium",
            context_length=8192,
            speed_rating=7,
            accuracy_rating=8,
            supports_code=True
        )

        # Code task requirements
        code_requirements = TaskRequirements(
            task_type=TaskType.CODE_GENERATION,
            complexity=TaskComplexity.MODERATE,
            estimated_tokens=500,
            requires_code=True,
            context_length=1000
        )

        score = code_model.matches_requirements(code_requirements)
        assert score > 0.7  # Should be a good match

        # Vision task requirements (should not match)
        vision_requirements = TaskRequirements(
            task_type=TaskType.VISION,
            complexity=TaskComplexity.SIMPLE,
            estimated_tokens=200,
            requires_vision=True,
            context_length=500
        )

        score = code_model.matches_requirements(vision_requirements)
        assert score == 0.0  # Can't do vision without vision support

    def test_complexity_matching(self):
        """Test complexity-based matching."""
        # Small model
        small_model = ModelCapabilities(
            model_name="small-model",
            model_type="chat",
            size_category="small",
            context_length=4096,
            speed_rating=9,
            accuracy_rating=6
        )

        # Simple task - should match well
        simple_req = TaskRequirements(
            task_type=TaskType.GENERAL_CHAT,
            complexity=TaskComplexity.SIMPLE,
            estimated_tokens=100,
            context_length=500
        )

        score = small_model.matches_requirements(simple_req)
        assert score > 0.5

        # Complex task - should not match well
        complex_req = TaskRequirements(
            task_type=TaskType.REASONING,
            complexity=TaskComplexity.VERY_COMPLEX,
            estimated_tokens=2000,
            context_length=3000
        )

        score = small_model.matches_requirements(complex_req)
        assert score < 0.5


class TestModelRouter:
    """Test model routing functionality."""

    @pytest.fixture
    def router(self):
        """Create a model router."""
        return ModelRouter(strategy=RoutingStrategy.BALANCED)

    def test_route_code_task(self, router):
        """Test routing for code generation task."""
        requirements = TaskRequirements(
            task_type=TaskType.CODE_GENERATION,
            complexity=TaskComplexity.MODERATE,
            estimated_tokens=500,
            requires_code=True,
            context_length=1000
        )

        decision = router.route(requirements)

        # Should select a code model
        assert "coder" in decision.selected_model.lower() or decision.match_score > 0
        assert decision.reasoning is not None

    def test_route_vision_task(self, router):
        """Test routing for vision task."""
        requirements = TaskRequirements(
            task_type=TaskType.VISION,
            complexity=TaskComplexity.SIMPLE,
            estimated_tokens=200,
            requires_vision=True,
            context_length=500
        )

        decision = router.route(requirements)

        # Should select moondream2 or indicate vision requirement
        assert "moondream" in decision.selected_model.lower() or "vision" in decision.reasoning.lower()

    def test_route_simple_task_fast_strategy(self, router):
        """Test routing with FAST strategy."""
        requirements = TaskRequirements(
            task_type=TaskType.GENERAL_CHAT,
            complexity=TaskComplexity.SIMPLE,
            estimated_tokens=100,
            context_length=200
        )

        decision = router.route(requirements, strategy=RoutingStrategy.FAST)

        # Should prioritize speed
        assert decision.strategy_used == RoutingStrategy.FAST
        # Small models are typically faster
        model_cap = router.get_model_info(decision.selected_model)
        if model_cap:
            assert model_cap.speed_rating >= 7

    def test_route_complex_task_accurate_strategy(self, router):
        """Test routing with ACCURATE strategy."""
        requirements = TaskRequirements(
            task_type=TaskType.REASONING,
            complexity=TaskComplexity.COMPLEX,
            estimated_tokens=1500,
            requires_reasoning=True,
            context_length=3000
        )

        decision = router.route(requirements, strategy=RoutingStrategy.ACCURATE)

        assert decision.strategy_used == RoutingStrategy.ACCURATE
        # Should select a model with good accuracy
        model_cap = router.get_model_info(decision.selected_model)
        if model_cap:
            assert model_cap.accuracy_rating >= 7

    def test_route_economical_strategy(self, router):
        """Test routing with ECONOMICAL strategy."""
        requirements = TaskRequirements(
            task_type=TaskType.GENERAL_CHAT,
            complexity=TaskComplexity.MODERATE,
            estimated_tokens=300,
            context_length=500
        )

        decision = router.route(requirements, strategy=RoutingStrategy.ECONOMICAL)

        assert decision.strategy_used == RoutingStrategy.ECONOMICAL
        # Should prefer smaller models
        model_cap = router.get_model_info(decision.selected_model)
        if model_cap:
            assert model_cap.size_category in ["small", "medium"]

    def test_route_with_limited_models(self, router):
        """Test routing with limited available models."""
        requirements = TaskRequirements(
            task_type=TaskType.CODE_GENERATION,
            complexity=TaskComplexity.MODERATE,
            estimated_tokens=500,
            requires_code=True,
            context_length=1000
        )

        # Limit to specific models
        available = ["qwen2.5-3b", "qwen2.5-7b"]
        decision = router.route(requirements, available_models=available)

        assert decision.selected_model in available

    def test_fallback_routing(self, router):
        """Test fallback when no suitable models."""
        requirements = TaskRequirements(
            task_type=TaskType.VISION,
            complexity=TaskComplexity.SIMPLE,
            estimated_tokens=200,
            requires_vision=True,
            context_length=500
        )

        # No vision models available
        available = ["qwen2.5-3b"]
        decision = router.route(requirements, available_models=available)

        # Should still return a model
        assert decision.selected_model is not None

    def test_alternatives_provided(self, router):
        """Test that alternatives are provided."""
        requirements = TaskRequirements(
            task_type=TaskType.GENERAL_CHAT,
            complexity=TaskComplexity.MODERATE,
            estimated_tokens=500,
            context_length=1000
        )

        decision = router.route(requirements)

        # Should have alternatives
        assert isinstance(decision.alternatives, list)
        # Each alternative should be (model, score) tuple
        for alt in decision.alternatives:
            assert len(alt) == 2
            assert isinstance(alt[0], str)  # model name
            assert isinstance(alt[1], float)  # score

    def test_model_recommendations(self, router):
        """Test getting model recommendations."""
        requirements = TaskRequirements(
            task_type=TaskType.CODE_GENERATION,
            complexity=TaskComplexity.MODERATE,
            estimated_tokens=500,
            requires_code=True,
            context_length=1000
        )

        recommendations = router.recommend_models(requirements, top_k=3)

        assert len(recommendations) <= 3
        for model, score, reasoning in recommendations:
            assert isinstance(model, str)
            assert 0 <= score <= 1
            assert isinstance(reasoning, str)

    def test_update_model_registry(self, router):
        """Test updating model registry."""
        new_model = ModelCapabilities(
            model_name="custom-model",
            model_type="chat",
            size_category="large",
            context_length=16384,
            speed_rating=5,
            accuracy_rating=9,
            supports_reasoning=True
        )

        router.update_model_registry("custom-model", new_model)

        # Should be able to route to new model
        requirements = TaskRequirements(
            task_type=TaskType.REASONING,
            complexity=TaskComplexity.COMPLEX,
            estimated_tokens=2000,
            requires_reasoning=True,
            context_length=5000
        )

        decision = router.route(requirements, available_models=["custom-model"])
        assert decision.selected_model == "custom-model"

    def test_reasoning_generation(self, router):
        """Test reasoning explanation generation."""
        requirements = TaskRequirements(
            task_type=TaskType.CODE_GENERATION,
            complexity=TaskComplexity.MODERATE,
            estimated_tokens=500,
            requires_code=True,
            context_length=1000
        )

        decision = router.route(requirements)

        assert decision.reasoning is not None
        assert len(decision.reasoning) > 0
        # Should mention relevant aspects
        if "coder" in decision.selected_model:
            assert "code" in decision.reasoning.lower()

    def test_qwen_models_in_registry(self, router):
        """Test that Qwen models are in registry."""
        qwen_models = [
            "qwen2.5-3b",
            "qwen2.5-7b",
            "qwen2.5-coder-3b",
            "qwen2.5-coder-7b"
        ]

        for model in qwen_models:
            info = router.get_model_info(model)
            assert info is not None
            assert info.model_name == model

    def test_context_length_consideration(self, router):
        """Test that context length is considered."""
        # Long context requirement
        requirements = TaskRequirements(
            task_type=TaskType.GENERAL_CHAT,
            complexity=TaskComplexity.MODERATE,
            estimated_tokens=500,
            context_length=50000  # Very long context
        )

        decision = router.route(requirements)

        # Should select a model with large context window
        model_cap = router.get_model_info(decision.selected_model)
        if model_cap:
            # Should penalize models with insufficient context
            if model_cap.context_length < 50000:
                assert decision.match_score < 0.7