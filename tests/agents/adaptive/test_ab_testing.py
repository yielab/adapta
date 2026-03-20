"""
Tests for A/B testing functionality.
"""

import pytest
from datetime import datetime

from brain.agents.adaptive.ab_testing import (
    ABTestManager,
    TestVariant,
    PerformanceMetrics,
    TestResult
)


class TestABTestManager:
    """Test A/B testing manager."""

    @pytest.fixture
    def ab_manager(self):
        """Create an A/B test manager."""
        return ABTestManager(
            min_sessions_per_variant=10,
            confidence_threshold=0.95
        )

    def test_create_test(self, ab_manager):
        """Test creating an A/B test."""
        test_config = ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[
                ("version-a", 0.5),
                ("version-b", 0.5)
            ],
            metrics_to_track=["response_time", "user_satisfaction"]
        )

        assert test_config["test_id"] == "test-1"
        assert test_config["agent_id"] == "agent-1"
        assert len(test_config["variants"]) == 2
        assert test_config["status"] == "active"

        # Check weight normalization
        total_weight = sum(v.weight for v in test_config["variants"])
        assert abs(total_weight - 1.0) < 0.01

    def test_select_variant_random(self, ab_manager):
        """Test variant selection with random distribution."""
        ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[
                ("version-a", 0.7),
                ("version-b", 0.3)
            ],
            metrics_to_track=["user_satisfaction"]
        )

        # Select variants multiple times
        selections = {"version-a": 0, "version-b": 0}
        for _ in range(1000):
            variant = ab_manager.select_variant("test-1")
            selections[variant] += 1

        # Check distribution roughly matches weights (with tolerance)
        ratio_a = selections["version-a"] / 1000
        assert 0.6 < ratio_a < 0.8  # 70% ± 10%

    def test_select_variant_consistent(self, ab_manager):
        """Test consistent variant selection for same session."""
        ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[
                ("version-a", 0.5),
                ("version-b", 0.5)
            ],
            metrics_to_track=["user_satisfaction"]
        )

        # Same session should get same variant
        session_id = "session-123"
        variant1 = ab_manager.select_variant("test-1", session_id)
        variant2 = ab_manager.select_variant("test-1", session_id)
        variant3 = ab_manager.select_variant("test-1", session_id)

        assert variant1 == variant2 == variant3

    def test_record_metric(self, ab_manager):
        """Test recording metrics."""
        ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[("version-a", 1.0)],
            metrics_to_track=["response_time", "user_satisfaction"]
        )

        # Record metrics
        ab_manager.record_metric("test-1", "version-a", "response_time", 0.5)
        ab_manager.record_metric("test-1", "version-a", "response_time", 0.6)
        ab_manager.record_metric("test-1", "version-a", "user_satisfaction", 4.5)

        test = ab_manager.active_tests["test-1"]
        variant = test["variants"][0]

        assert len(variant.metrics["response_time"]) == 2
        assert len(variant.metrics["user_satisfaction"]) == 1
        assert variant.metrics["response_time"][0] == 0.5

    def test_evaluate_test_insufficient_data(self, ab_manager):
        """Test evaluation with insufficient data."""
        ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[
                ("version-a", 0.5),
                ("version-b", 0.5)
            ],
            metrics_to_track=["user_satisfaction"]
        )

        # Add minimal data
        for _ in range(5):  # Less than min_sessions (10)
            ab_manager.select_variant("test-1")
            ab_manager.record_metric("test-1", "version-a", "user_satisfaction", 4.0)

        result = ab_manager.evaluate_test("test-1")

        assert result.winner is None
        assert "insufficient data" in result.recommendation.lower()

    def test_evaluate_test_with_winner(self, ab_manager):
        """Test evaluation with clear winner."""
        ab_manager.min_sessions = 5  # Lower for testing

        ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[
                ("version-a", 0.5),
                ("version-b", 0.5)
            ],
            metrics_to_track=["user_satisfaction", "success_rate"]
        )

        # Simulate sessions for version-a (better performance)
        test = ab_manager.active_tests["test-1"]
        variant_a = test["variants"][0]
        variant_a.session_count = 10
        for _ in range(10):
            variant_a.add_metric("user_satisfaction", 4.8)
            variant_a.add_metric("success_rate", 0.95)

        # Simulate sessions for version-b (worse performance)
        variant_b = test["variants"][1]
        variant_b.session_count = 10
        for _ in range(10):
            variant_b.add_metric("user_satisfaction", 3.2)
            variant_b.add_metric("success_rate", 0.70)

        result = ab_manager.evaluate_test("test-1", primary_metric="user_satisfaction")

        # Version-a should win
        assert result.winner is not None
        assert "version-a" in result.winner

        # Check metrics
        assert len(result.metrics) == 2
        winner_metrics = next(m for m in result.metrics if m.is_winner)
        assert winner_metrics.user_satisfaction > 4.0

    def test_evaluate_test_no_winner(self, ab_manager):
        """Test evaluation with no clear winner."""
        ab_manager.min_sessions = 5

        ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[
                ("version-a", 0.5),
                ("version-b", 0.5)
            ],
            metrics_to_track=["user_satisfaction"]
        )

        # Simulate similar performance
        test = ab_manager.active_tests["test-1"]

        for variant in test["variants"]:
            variant.session_count = 10
            for _ in range(10):
                variant.add_metric("user_satisfaction", 4.0)
                variant.add_metric("success_rate", 0.85)

        result = ab_manager.evaluate_test("test-1")

        assert result.winner is None
        assert "no clear winner" in result.recommendation.lower()

    def test_stop_test(self, ab_manager):
        """Test stopping an active test."""
        ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[("version-a", 1.0)],
            metrics_to_track=["user_satisfaction"]
        )

        # Add some data
        test = ab_manager.active_tests["test-1"]
        variant = test["variants"][0]
        variant.session_count = 15
        for _ in range(15):
            variant.add_metric("user_satisfaction", 4.5)

        # Stop test
        result = ab_manager.stop_test("test-1")

        assert result is not None
        assert "test-1" not in ab_manager.active_tests
        assert "test-1" in ab_manager.test_results

    def test_get_test_status_active(self, ab_manager):
        """Test getting status of active test."""
        ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[("version-a", 1.0)],
            metrics_to_track=["user_satisfaction"]
        )

        # Add some metrics
        ab_manager.record_metric("test-1", "version-a", "user_satisfaction", 4.0)

        status = ab_manager.get_test_status("test-1")

        assert status["status"] == "active"
        assert "variants" in status
        assert "started_at" in status
        assert status["total_sessions"] >= 0

    def test_get_test_status_completed(self, ab_manager):
        """Test getting status of completed test."""
        ab_manager.create_test(
            test_id="test-1",
            agent_id="agent-1",
            variants=[("version-a", 1.0)],
            metrics_to_track=["user_satisfaction"]
        )

        # Stop test
        result = ab_manager.stop_test("test-1")

        status = ab_manager.get_test_status("test-1")

        assert status["status"] == "completed"
        assert "result" in status
        assert status["result"] == result

    def test_calculate_confidence(self, ab_manager):
        """Test confidence calculation."""
        variant = TestVariant(
            variant_id="test",
            agent_version="v1",
            weight=1.0
        )

        # Low session count - low confidence
        variant.session_count = 5
        metrics = ab_manager._calculate_variant_metrics(variant)
        assert metrics.confidence_level < 0.5

        # High session count with consistent data - high confidence
        variant.session_count = 100
        for _ in range(100):
            variant.add_metric("user_satisfaction", 4.5)

        metrics = ab_manager._calculate_variant_metrics(variant)
        assert metrics.confidence_level > 0.5

    def test_performance_metrics_calculation(self, ab_manager):
        """Test performance metrics calculation."""
        variant = TestVariant(
            variant_id="test",
            agent_version="v1",
            weight=1.0
        )

        # Add various metrics
        variant.session_count = 10
        variant.add_metric("response_time", 0.5)
        variant.add_metric("response_time", 0.7)
        variant.add_metric("success_rate", 0.9)
        variant.add_metric("success_rate", 0.85)
        variant.add_metric("user_satisfaction", 4.5)
        variant.add_metric("user_satisfaction", 4.2)
        variant.add_metric("conversion_rate", 0.3)

        metrics = ab_manager._calculate_variant_metrics(variant)

        assert metrics.session_count == 10
        assert metrics.avg_response_time == pytest.approx(0.6, rel=0.01)
        assert metrics.success_rate == pytest.approx(0.875, rel=0.01)
        assert metrics.user_satisfaction == pytest.approx(4.35, rel=0.01)
        assert metrics.conversion_rate == pytest.approx(0.3, rel=0.01)