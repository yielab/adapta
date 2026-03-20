"""
Feedback collection system for adaptive agents.

Collects and analyzes user feedback to drive agent improvement.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import asyncio
from collections import defaultdict

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    """Types of feedback that can be collected."""
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    RATING = "rating"  # 1-5 scale
    CORRECTION = "correction"  # User provides correct answer
    PREFERENCE = "preference"  # A/B preference
    IMPLICIT = "implicit"  # Based on user behavior
    EXPLICIT = "explicit"  # Direct feedback


@dataclass
class FeedbackEntry:
    """A single feedback entry."""
    id: str
    agent_id: str
    session_id: str
    feedback_type: FeedbackType
    value: Any  # Rating value, correction text, etc.
    context: Dict[str, Any]  # Input/output that led to feedback
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "feedback_type": self.feedback_type.value,
            "value": self.value,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class FeedbackAnalysis:
    """Analysis results for collected feedback."""
    agent_id: str
    total_feedback: int
    positive_ratio: float
    negative_ratio: float
    average_rating: Optional[float]
    common_issues: List[str]
    improvement_areas: List[str]
    training_readiness: bool
    confidence_score: float

    def should_trigger_training(self) -> bool:
        """Determine if training should be triggered."""
        return (
            self.training_readiness and
            self.total_feedback >= 100 and
            (self.negative_ratio > 0.3 or self.average_rating and self.average_rating < 3.5)
        )


class FeedbackCollector:
    """
    Collects and analyzes feedback for adaptive agent improvement.

    Features:
    - Multiple feedback types
    - Pattern recognition
    - Training trigger analysis
    - Feedback aggregation
    """

    def __init__(
        self,
        min_feedback_for_training: int = 100,
        negative_threshold: float = 0.3,
        analysis_window_hours: int = 24
    ):
        """
        Initialize feedback collector.

        Args:
            min_feedback_for_training: Minimum feedback entries before training
            negative_threshold: Threshold for negative feedback ratio
            analysis_window_hours: Time window for feedback analysis
        """
        self.min_feedback_for_training = min_feedback_for_training
        self.negative_threshold = negative_threshold
        self.analysis_window_hours = analysis_window_hours

        # Storage
        self.feedback_store: Dict[str, List[FeedbackEntry]] = defaultdict(list)
        self.feedback_counter = 0

        # Analysis cache
        self.analysis_cache: Dict[str, FeedbackAnalysis] = {}
        self.cache_ttl = 300  # 5 minutes

    async def collect_feedback(
        self,
        agent_id: str,
        session_id: str,
        feedback_type: FeedbackType,
        value: Any,
        input_text: str,
        output_text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> FeedbackEntry:
        """
        Collect feedback for an agent interaction.

        Args:
            agent_id: Agent identifier
            session_id: Session identifier
            feedback_type: Type of feedback
            value: Feedback value (rating, correction, etc.)
            input_text: User input
            output_text: Agent output
            metadata: Additional metadata

        Returns:
            Created feedback entry
        """
        self.feedback_counter += 1

        entry = FeedbackEntry(
            id=f"feedback_{self.feedback_counter}",
            agent_id=agent_id,
            session_id=session_id,
            feedback_type=feedback_type,
            value=value,
            context={
                "input": input_text,
                "output": output_text
            },
            metadata=metadata or {}
        )

        self.feedback_store[agent_id].append(entry)

        # Invalidate cache for this agent
        if agent_id in self.analysis_cache:
            del self.analysis_cache[agent_id]

        logger.info(f"Collected {feedback_type.value} feedback for agent {agent_id}")

        # Check if we should trigger analysis
        if len(self.feedback_store[agent_id]) % 10 == 0:
            asyncio.create_task(self._background_analysis(agent_id))

        return entry

    async def collect_implicit_feedback(
        self,
        agent_id: str,
        session_id: str,
        interaction_data: Dict[str, Any]
    ) -> Optional[FeedbackEntry]:
        """
        Collect implicit feedback based on user behavior.

        Args:
            agent_id: Agent identifier
            session_id: Session identifier
            interaction_data: Interaction metrics

        Returns:
            Feedback entry if patterns detected
        """
        # Analyze interaction patterns
        feedback_value = None

        # Quick response abandonment
        if interaction_data.get("response_abandoned_quickly"):
            feedback_value = "negative_implicit"

        # Long engagement
        elif interaction_data.get("engagement_duration_seconds", 0) > 60:
            feedback_value = "positive_implicit"

        # Copy/save action
        elif interaction_data.get("response_copied") or interaction_data.get("response_saved"):
            feedback_value = "positive_implicit"

        # Immediate retry
        elif interaction_data.get("immediate_retry"):
            feedback_value = "negative_implicit"

        if feedback_value:
            return await self.collect_feedback(
                agent_id=agent_id,
                session_id=session_id,
                feedback_type=FeedbackType.IMPLICIT,
                value=feedback_value,
                input_text=interaction_data.get("input", ""),
                output_text=interaction_data.get("output", ""),
                metadata={"behavior_signals": interaction_data}
            )

        return None

    async def analyze_feedback(
        self,
        agent_id: str,
        use_cache: bool = True
    ) -> FeedbackAnalysis:
        """
        Analyze collected feedback for an agent.

        Args:
            agent_id: Agent to analyze
            use_cache: Use cached analysis if available

        Returns:
            Feedback analysis results
        """
        # Check cache
        if use_cache and agent_id in self.analysis_cache:
            cached = self.analysis_cache[agent_id]
            if (datetime.now() - cached.timestamp).seconds < self.cache_ttl:
                return cached

        # Get feedback within analysis window
        cutoff = datetime.now() - timedelta(hours=self.analysis_window_hours)
        recent_feedback = [
            f for f in self.feedback_store.get(agent_id, [])
            if f.timestamp >= cutoff
        ]

        if not recent_feedback:
            return FeedbackAnalysis(
                agent_id=agent_id,
                total_feedback=0,
                positive_ratio=0.0,
                negative_ratio=0.0,
                average_rating=None,
                common_issues=[],
                improvement_areas=[],
                training_readiness=False,
                confidence_score=0.0
            )

        # Calculate metrics
        total = len(recent_feedback)
        positive = sum(1 for f in recent_feedback if self._is_positive(f))
        negative = sum(1 for f in recent_feedback if self._is_negative(f))

        # Calculate average rating
        ratings = [
            f.value for f in recent_feedback
            if f.feedback_type == FeedbackType.RATING and isinstance(f.value, (int, float))
        ]
        avg_rating = sum(ratings) / len(ratings) if ratings else None

        # Identify common issues
        issues = self._identify_common_issues(recent_feedback)

        # Identify improvement areas
        improvements = self._identify_improvement_areas(recent_feedback)

        # Calculate confidence
        confidence = min(1.0, total / self.min_feedback_for_training)

        analysis = FeedbackAnalysis(
            agent_id=agent_id,
            total_feedback=total,
            positive_ratio=positive / total if total > 0 else 0.0,
            negative_ratio=negative / total if total > 0 else 0.0,
            average_rating=avg_rating,
            common_issues=issues,
            improvement_areas=improvements,
            training_readiness=total >= self.min_feedback_for_training,
            confidence_score=confidence
        )

        # Cache result
        self.analysis_cache[agent_id] = analysis

        return analysis

    def _is_positive(self, feedback: FeedbackEntry) -> bool:
        """Check if feedback is positive."""
        if feedback.feedback_type == FeedbackType.THUMBS_UP:
            return True
        elif feedback.feedback_type == FeedbackType.THUMBS_DOWN:
            return False
        elif feedback.feedback_type == FeedbackType.RATING:
            return feedback.value >= 4
        elif feedback.feedback_type == FeedbackType.IMPLICIT:
            return "positive" in str(feedback.value)
        return False

    def _is_negative(self, feedback: FeedbackEntry) -> bool:
        """Check if feedback is negative."""
        if feedback.feedback_type == FeedbackType.THUMBS_DOWN:
            return True
        elif feedback.feedback_type == FeedbackType.THUMBS_UP:
            return False
        elif feedback.feedback_type == FeedbackType.RATING:
            return feedback.value <= 2
        elif feedback.feedback_type == FeedbackType.IMPLICIT:
            return "negative" in str(feedback.value)
        return False

    def _identify_common_issues(
        self,
        feedback: List[FeedbackEntry]
    ) -> List[str]:
        """Identify common issues from feedback."""
        issues = []

        # Look for correction patterns
        corrections = [
            f for f in feedback
            if f.feedback_type == FeedbackType.CORRECTION
        ]

        if len(corrections) > 5:
            # Analyze correction patterns
            # In production, use NLP to identify themes
            issues.append("Frequent corrections needed")

        # Check for specific negative patterns
        negative_feedback = [f for f in feedback if self._is_negative(f)]
        if len(negative_feedback) / len(feedback) > 0.3:
            issues.append("High negative feedback ratio")

        # Look for abandonment patterns
        abandonments = [
            f for f in feedback
            if f.metadata.get("response_abandoned_quickly")
        ]
        if len(abandonments) > 3:
            issues.append("Users frequently abandon responses")

        return issues

    def _identify_improvement_areas(
        self,
        feedback: List[FeedbackEntry]
    ) -> List[str]:
        """Identify areas for improvement."""
        areas = []

        # Analyze negative feedback context
        negative_feedback = [f for f in feedback if self._is_negative(f)]

        if negative_feedback:
            # Simple keyword analysis
            # In production, use more sophisticated NLP
            contexts = [f.context for f in negative_feedback]

            # Check for common patterns
            if any("code" in str(c).lower() for c in contexts):
                areas.append("Code generation quality")

            if any("explain" in str(c).lower() for c in contexts):
                areas.append("Explanation clarity")

            if any("accuracy" in str(c).lower() or "wrong" in str(c).lower() for c in contexts):
                areas.append("Response accuracy")

        return areas

    async def get_training_data(
        self,
        agent_id: str,
        include_corrections: bool = True,
        min_rating: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get training data from feedback.

        Args:
            agent_id: Agent identifier
            include_corrections: Include correction feedback
            min_rating: Minimum rating to include

        Returns:
            Training data entries
        """
        training_data = []

        feedback = self.feedback_store.get(agent_id, [])

        for entry in feedback:
            # Include corrections
            if include_corrections and entry.feedback_type == FeedbackType.CORRECTION:
                training_data.append({
                    "input": entry.context["input"],
                    "output": entry.value,  # Correction is the desired output
                    "metadata": {
                        "feedback_type": "correction",
                        "original_output": entry.context["output"]
                    }
                })

            # Include high-rated responses
            elif entry.feedback_type == FeedbackType.RATING:
                if min_rating is None or entry.value >= min_rating:
                    training_data.append({
                        "input": entry.context["input"],
                        "output": entry.context["output"],
                        "metadata": {
                            "feedback_type": "rating",
                            "rating": entry.value
                        }
                    })

        return training_data

    def export_feedback(
        self,
        agent_id: str,
        format: str = "json"
    ) -> str:
        """
        Export feedback data.

        Args:
            agent_id: Agent identifier
            format: Export format (json, csv)

        Returns:
            Exported data string
        """
        feedback = self.feedback_store.get(agent_id, [])

        if format == "json":
            return json.dumps(
                [f.to_dict() for f in feedback],
                indent=2
            )
        elif format == "csv":
            # Simple CSV export
            lines = ["timestamp,type,value,input,output"]
            for f in feedback:
                lines.append(
                    f"{f.timestamp},{f.feedback_type.value},{f.value},"
                    f'"{f.context.get("input", "")}","{f.context.get("output", "")}"'
                )
            return "\n".join(lines)

        raise ValueError(f"Unsupported format: {format}")

    def clear_feedback(
        self,
        agent_id: str,
        older_than: Optional[datetime] = None
    ):
        """
        Clear feedback for an agent.

        Args:
            agent_id: Agent identifier
            older_than: Clear only feedback older than this
        """
        if older_than:
            self.feedback_store[agent_id] = [
                f for f in self.feedback_store.get(agent_id, [])
                if f.timestamp >= older_than
            ]
        else:
            self.feedback_store[agent_id] = []

        # Clear cache
        if agent_id in self.analysis_cache:
            del self.analysis_cache[agent_id]