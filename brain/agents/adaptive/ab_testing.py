"""
A/B testing for agent versions.

Enables controlled experiments with different agent configurations.
"""

import logging
import random
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import math
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TestVariant:
    """A variant in an A/B test."""
    variant_id: str
    agent_version: str
    weight: float  # Traffic percentage (0-1)
    metrics: Dict[str, List[float]] = field(default_factory=dict)
    session_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    def add_metric(self, metric_name: str, value: float):
        """Add a metric observation."""
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        self.metrics[metric_name].append(value)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a variant."""
    variant_id: str
    session_count: int
    avg_response_time: float
    success_rate: float
    user_satisfaction: float
    conversion_rate: float
    confidence_level: float
    is_winner: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "variant_id": self.variant_id,
            "session_count": self.session_count,
            "avg_response_time": self.avg_response_time,
            "success_rate": self.success_rate,
            "user_satisfaction": self.user_satisfaction,
            "conversion_rate": self.conversion_rate,
            "confidence_level": self.confidence_level,
            "is_winner": self.is_winner
        }


@dataclass
class TestResult:
    """Results of an A/B test."""
    test_id: str
    winner: Optional[str]  # Winning variant ID
    metrics: List[PerformanceMetrics]
    statistical_significance: float
    recommendation: str
    completed_at: datetime = field(default_factory=datetime.now)


class ABTestManager:
    """
    Manages A/B testing for agent versions.

    Features:
    - Multi-variant testing
    - Statistical significance calculation
    - Automatic winner selection
    - Gradual rollout
    """

    def __init__(
        self,
        min_sessions_per_variant: int = 100,
        confidence_threshold: float = 0.95
    ):
        """
        Initialize A/B test manager.

        Args:
            min_sessions_per_variant: Minimum sessions before evaluation
            confidence_threshold: Confidence level for winner selection
        """
        self.min_sessions = min_sessions_per_variant
        self.confidence_threshold = confidence_threshold

        # Active tests
        self.active_tests: Dict[str, Dict[str, Any]] = {}

        # Test history
        self.test_results: Dict[str, TestResult] = {}

    def create_test(
        self,
        test_id: str,
        agent_id: str,
        variants: List[Tuple[str, float]],
        metrics_to_track: List[str]
    ) -> Dict[str, Any]:
        """
        Create an A/B test.

        Args:
            test_id: Test identifier
            agent_id: Agent being tested
            variants: List of (version_id, weight) tuples
            metrics_to_track: Metrics to collect

        Returns:
            Test configuration
        """
        # Normalize weights
        total_weight = sum(w for _, w in variants)
        normalized_variants = [
            TestVariant(
                variant_id=f"{test_id}_{v}",
                agent_version=v,
                weight=w / total_weight
            )
            for v, w in variants
        ]

        test_config = {
            "test_id": test_id,
            "agent_id": agent_id,
            "variants": normalized_variants,
            "metrics": metrics_to_track,
            "started_at": datetime.now(),
            "status": "active"
        }

        self.active_tests[test_id] = test_config

        logger.info(f"Created A/B test {test_id} with {len(variants)} variants")

        return test_config

    def select_variant(
        self,
        test_id: str,
        session_id: Optional[str] = None
    ) -> str:
        """
        Select a variant for a session.

        Args:
            test_id: Test identifier
            session_id: Session ID for consistent assignment

        Returns:
            Selected agent version
        """
        test = self.active_tests.get(test_id)
        if not test:
            raise ValueError(f"Test {test_id} not found")

        # Use session ID for consistent assignment if provided
        if session_id:
            # Hash session ID for consistent assignment
            hash_value = hash(session_id) % 100 / 100.0
        else:
            hash_value = random.random()

        # Select variant based on weights
        cumulative = 0.0
        for variant in test["variants"]:
            cumulative += variant.weight
            if hash_value <= cumulative:
                variant.session_count += 1
                return variant.agent_version

        # Fallback to last variant
        return test["variants"][-1].agent_version

    def record_metric(
        self,
        test_id: str,
        variant_id: str,
        metric_name: str,
        value: float
    ):
        """
        Record a metric observation.

        Args:
            test_id: Test identifier
            variant_id: Variant identifier
            metric_name: Metric name
            value: Metric value
        """
        test = self.active_tests.get(test_id)
        if not test:
            logger.warning(f"Test {test_id} not found")
            return

        for variant in test["variants"]:
            if variant.agent_version == variant_id:
                variant.add_metric(metric_name, value)
                break

    def evaluate_test(
        self,
        test_id: str,
        primary_metric: str = "user_satisfaction"
    ) -> TestResult:
        """
        Evaluate test results and determine winner.

        Args:
            test_id: Test identifier
            primary_metric: Primary metric for winner selection

        Returns:
            Test results
        """
        test = self.active_tests.get(test_id)
        if not test:
            raise ValueError(f"Test {test_id} not found")

        # Calculate metrics for each variant
        variant_metrics = []
        for variant in test["variants"]:
            metrics = self._calculate_variant_metrics(variant)
            variant_metrics.append(metrics)

        # Determine winner based on primary metric
        winner = self._determine_winner(variant_metrics, primary_metric)

        # Calculate statistical significance
        significance = self._calculate_significance(variant_metrics, primary_metric)

        # Generate recommendation
        recommendation = self._generate_recommendation(
            variant_metrics,
            winner,
            significance
        )

        result = TestResult(
            test_id=test_id,
            winner=winner,
            metrics=variant_metrics,
            statistical_significance=significance,
            recommendation=recommendation
        )

        # Store result
        self.test_results[test_id] = result

        # Mark test as completed
        test["status"] = "completed"

        return result

    def _calculate_variant_metrics(
        self,
        variant: TestVariant
    ) -> PerformanceMetrics:
        """Calculate aggregated metrics for a variant."""
        def safe_mean(values):
            return sum(values) / len(values) if values else 0.0

        metrics = PerformanceMetrics(
            variant_id=variant.variant_id,
            session_count=variant.session_count,
            avg_response_time=safe_mean(variant.metrics.get("response_time", [])),
            success_rate=safe_mean(variant.metrics.get("success_rate", [])),
            user_satisfaction=safe_mean(variant.metrics.get("user_satisfaction", [])),
            conversion_rate=safe_mean(variant.metrics.get("conversion_rate", [])),
            confidence_level=self._calculate_confidence(variant)
        )

        return metrics

    def _calculate_confidence(self, variant: TestVariant) -> float:
        """Calculate confidence level for variant metrics."""
        if variant.session_count < self.min_sessions:
            return variant.session_count / self.min_sessions

        # Simple confidence based on sample size and variance
        satisfaction_scores = variant.metrics.get("user_satisfaction", [])
        if len(satisfaction_scores) < 2:
            return 0.0

        mean = sum(satisfaction_scores) / len(satisfaction_scores)
        variance = sum((x - mean) ** 2 for x in satisfaction_scores) / len(satisfaction_scores)
        std_error = math.sqrt(variance / len(satisfaction_scores))

        # Confidence increases as standard error decreases
        confidence = max(0.0, min(1.0, 1.0 - std_error))

        return confidence

    def _determine_winner(
        self,
        metrics: List[PerformanceMetrics],
        primary_metric: str
    ) -> Optional[str]:
        """Determine the winning variant."""
        if not metrics:
            return None

        # Check if all variants have enough data
        if any(m.session_count < self.min_sessions for m in metrics):
            return None  # Not enough data

        # Find best performer on primary metric
        metric_values = []
        for m in metrics:
            if primary_metric == "user_satisfaction":
                metric_values.append((m.user_satisfaction, m.variant_id))
            elif primary_metric == "conversion_rate":
                metric_values.append((m.conversion_rate, m.variant_id))
            elif primary_metric == "success_rate":
                metric_values.append((m.success_rate, m.variant_id))
            else:
                metric_values.append((m.user_satisfaction, m.variant_id))

        if metric_values:
            best_value, best_variant = max(metric_values)

            # Check if winner is statistically significant
            if self._is_significant_winner(metrics, best_variant, primary_metric):
                # Mark winner
                for m in metrics:
                    if m.variant_id == best_variant:
                        m.is_winner = True
                return best_variant

        return None

    def _is_significant_winner(
        self,
        metrics: List[PerformanceMetrics],
        candidate: str,
        primary_metric: str
    ) -> bool:
        """Check if a variant is a statistically significant winner."""
        # Simple significance test (in production, use proper statistical tests)
        candidate_metric = None
        other_metrics = []

        for m in metrics:
            if m.variant_id == candidate:
                candidate_metric = getattr(m, primary_metric)
            else:
                other_metrics.append(getattr(m, primary_metric))

        if candidate_metric is None or not other_metrics:
            return False

        # Check if candidate is better than all others by a margin
        margin = 0.1  # 10% improvement threshold
        return all(candidate_metric > (other * (1 + margin)) for other in other_metrics)

    def _calculate_significance(
        self,
        metrics: List[PerformanceMetrics],
        primary_metric: str
    ) -> float:
        """Calculate statistical significance of results."""
        if len(metrics) < 2:
            return 0.0

        # Simple confidence calculation based on sample size and consistency
        confidences = [m.confidence_level for m in metrics]
        avg_confidence = sum(confidences) / len(confidences)

        # Check variance in primary metric
        primary_values = [getattr(m, primary_metric) for m in metrics]
        if len(set(primary_values)) == 1:
            return 0.0  # No difference

        # Simple significance score
        significance = avg_confidence

        return min(1.0, significance)

    def _generate_recommendation(
        self,
        metrics: List[PerformanceMetrics],
        winner: Optional[str],
        significance: float
    ) -> str:
        """Generate recommendation based on test results."""
        if not winner:
            if any(m.session_count < self.min_sessions for m in metrics):
                return "Continue testing - insufficient data"
            else:
                return "No clear winner - variants perform similarly"

        if significance >= self.confidence_threshold:
            return f"Deploy variant {winner} - statistically significant improvement"
        elif significance >= 0.8:
            return f"Variant {winner} shows promise - consider gradual rollout"
        else:
            return "Continue testing - results not yet conclusive"

    def stop_test(self, test_id: str) -> TestResult:
        """
        Stop an active test and evaluate results.

        Args:
            test_id: Test identifier

        Returns:
            Final test results
        """
        test = self.active_tests.get(test_id)
        if not test:
            raise ValueError(f"Test {test_id} not found")

        # Evaluate test
        result = self.evaluate_test(test_id)

        # Remove from active tests
        del self.active_tests[test_id]

        return result

    def get_test_status(self, test_id: str) -> Dict[str, Any]:
        """Get current status of a test."""
        test = self.active_tests.get(test_id)
        if not test:
            # Check completed tests
            if test_id in self.test_results:
                result = self.test_results[test_id]
                return {
                    "status": "completed",
                    "result": result
                }
            raise ValueError(f"Test {test_id} not found")

        # Calculate current metrics
        variant_metrics = [
            self._calculate_variant_metrics(v)
            for v in test["variants"]
        ]

        return {
            "status": test["status"],
            "variants": [m.to_dict() for m in variant_metrics],
            "started_at": test["started_at"].isoformat(),
            "total_sessions": sum(v.session_count for v in test["variants"])
        }