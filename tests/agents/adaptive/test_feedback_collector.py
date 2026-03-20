"""
Tests for feedback collection system.
"""

import pytest
import asyncio
from datetime import datetime, timedelta

from brain.agents.adaptive.feedback_collector import (
    FeedbackCollector,
    FeedbackType,
    FeedbackEntry,
    FeedbackAnalysis
)


class TestFeedbackCollector:
    """Test feedback collection functionality."""

    @pytest.fixture
    def collector(self):
        """Create a feedback collector."""
        return FeedbackCollector(
            min_feedback_for_training=10,
            negative_threshold=0.3
        )

    @pytest.mark.asyncio
    async def test_collect_feedback(self, collector):
        """Test collecting feedback."""
        # Collect thumbs up feedback
        entry = await collector.collect_feedback(
            agent_id="test-agent",
            session_id="session-1",
            feedback_type=FeedbackType.THUMBS_UP,
            value=True,
            input_text="How are you?",
            output_text="I'm doing great!"
        )

        assert entry is not None
        assert entry.agent_id == "test-agent"
        assert entry.feedback_type == FeedbackType.THUMBS_UP
        assert entry.value is True
        assert entry.context["input"] == "How are you?"
        assert entry.context["output"] == "I'm doing great!"

    @pytest.mark.asyncio
    async def test_collect_rating_feedback(self, collector):
        """Test collecting rating feedback."""
        entry = await collector.collect_feedback(
            agent_id="test-agent",
            session_id="session-1",
            feedback_type=FeedbackType.RATING,
            value=4,
            input_text="Explain Python",
            output_text="Python is a programming language..."
        )

        assert entry.feedback_type == FeedbackType.RATING
        assert entry.value == 4

    @pytest.mark.asyncio
    async def test_collect_correction_feedback(self, collector):
        """Test collecting correction feedback."""
        entry = await collector.collect_feedback(
            agent_id="test-agent",
            session_id="session-1",
            feedback_type=FeedbackType.CORRECTION,
            value="Python is a high-level programming language...",
            input_text="What is Python?",
            output_text="Python is a snake..."
        )

        assert entry.feedback_type == FeedbackType.CORRECTION
        assert "high-level" in entry.value

    @pytest.mark.asyncio
    async def test_implicit_feedback_positive(self, collector):
        """Test collecting positive implicit feedback."""
        interaction_data = {
            "engagement_duration_seconds": 120,
            "response_copied": True,
            "input": "Write a function",
            "output": "def hello(): ..."
        }

        entry = await collector.collect_implicit_feedback(
            agent_id="test-agent",
            session_id="session-1",
            interaction_data=interaction_data
        )

        assert entry is not None
        assert entry.feedback_type == FeedbackType.IMPLICIT
        assert "positive" in entry.value

    @pytest.mark.asyncio
    async def test_implicit_feedback_negative(self, collector):
        """Test collecting negative implicit feedback."""
        interaction_data = {
            "response_abandoned_quickly": True,
            "immediate_retry": True,
            "input": "Help me",
            "output": "I don't understand"
        }

        entry = await collector.collect_implicit_feedback(
            agent_id="test-agent",
            session_id="session-1",
            interaction_data=interaction_data
        )

        assert entry is not None
        assert entry.feedback_type == FeedbackType.IMPLICIT
        assert "negative" in entry.value

    @pytest.mark.asyncio
    async def test_analyze_feedback(self, collector):
        """Test analyzing collected feedback."""
        # Collect mixed feedback
        for i in range(15):
            if i < 10:
                # Positive feedback
                await collector.collect_feedback(
                    agent_id="test-agent",
                    session_id=f"session-{i}",
                    feedback_type=FeedbackType.THUMBS_UP if i % 2 == 0 else FeedbackType.RATING,
                    value=True if i % 2 == 0 else 5,
                    input_text=f"Question {i}",
                    output_text=f"Answer {i}"
                )
            else:
                # Negative feedback
                await collector.collect_feedback(
                    agent_id="test-agent",
                    session_id=f"session-{i}",
                    feedback_type=FeedbackType.THUMBS_DOWN,
                    value=False,
                    input_text=f"Question {i}",
                    output_text=f"Bad answer {i}"
                )

        # Analyze feedback
        analysis = await collector.analyze_feedback("test-agent")

        assert analysis.total_feedback == 15
        assert analysis.positive_ratio > 0.5
        assert analysis.negative_ratio < 0.5
        assert analysis.training_readiness is True  # Have enough feedback

    @pytest.mark.asyncio
    async def test_should_trigger_training(self, collector):
        """Test training trigger logic."""
        # Create analysis with high negative ratio
        analysis = FeedbackAnalysis(
            agent_id="test-agent",
            total_feedback=150,
            positive_ratio=0.6,
            negative_ratio=0.4,
            average_rating=3.2,
            common_issues=["accuracy"],
            improvement_areas=["Response accuracy"],
            training_readiness=True,
            confidence_score=0.9
        )

        assert analysis.should_trigger_training() is True

        # Test with low negative ratio
        analysis.negative_ratio = 0.1
        analysis.average_rating = 4.5
        assert analysis.should_trigger_training() is False

    @pytest.mark.asyncio
    async def test_get_training_data(self, collector):
        """Test extracting training data from feedback."""
        # Add corrections
        await collector.collect_feedback(
            agent_id="test-agent",
            session_id="session-1",
            feedback_type=FeedbackType.CORRECTION,
            value="Correct answer",
            input_text="What is 2+2?",
            output_text="5"
        )

        # Add high-rated responses
        await collector.collect_feedback(
            agent_id="test-agent",
            session_id="session-2",
            feedback_type=FeedbackType.RATING,
            value=5,
            input_text="Explain AI",
            output_text="AI is artificial intelligence..."
        )

        # Get training data
        training_data = await collector.get_training_data(
            agent_id="test-agent",
            include_corrections=True,
            min_rating=4
        )

        assert len(training_data) == 2
        assert training_data[0]["output"] == "Correct answer"  # Correction
        assert training_data[1]["output"] == "AI is artificial intelligence..."  # High rating

    @pytest.mark.asyncio
    async def test_export_feedback_json(self, collector):
        """Test exporting feedback as JSON."""
        # Add some feedback
        await collector.collect_feedback(
            agent_id="test-agent",
            session_id="session-1",
            feedback_type=FeedbackType.RATING,
            value=4,
            input_text="Test",
            output_text="Response"
        )

        # Export
        json_data = collector.export_feedback("test-agent", format="json")
        assert json_data is not None
        assert "test-agent" in json_data
        assert "RATING" in json_data

    @pytest.mark.asyncio
    async def test_clear_feedback(self, collector):
        """Test clearing feedback."""
        # Add feedback
        for i in range(5):
            await collector.collect_feedback(
                agent_id="test-agent",
                session_id=f"session-{i}",
                feedback_type=FeedbackType.RATING,
                value=4,
                input_text=f"Q{i}",
                output_text=f"A{i}"
            )

        # Clear all feedback
        collector.clear_feedback("test-agent")

        # Check it's empty
        analysis = await collector.analyze_feedback("test-agent")
        assert analysis.total_feedback == 0

    @pytest.mark.asyncio
    async def test_identify_common_issues(self, collector):
        """Test identifying common issues from feedback."""
        # Add corrections indicating accuracy issues
        for i in range(10):
            await collector.collect_feedback(
                agent_id="test-agent",
                session_id=f"session-{i}",
                feedback_type=FeedbackType.CORRECTION,
                value="Corrected answer",
                input_text=f"Question {i}",
                output_text=f"Wrong answer {i}"
            )

        analysis = await collector.analyze_feedback("test-agent")
        assert len(analysis.common_issues) > 0
        assert "Frequent corrections needed" in analysis.common_issues