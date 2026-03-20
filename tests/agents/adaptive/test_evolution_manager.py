"""
Tests for evolution manager and adaptive agents.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from brain.agents.adaptive.evolution_manager import (
    EvolutionManager,
    EvolutionStrategy,
    VersionManager,
    AdaptiveAgent,
    AgentVersion
)
from brain.agents.adaptive.feedback_collector import FeedbackAnalysis


class TestVersionManager:
    """Test version management functionality."""

    @pytest.fixture
    def version_manager(self):
        """Create a version manager."""
        return VersionManager()

    def test_create_version(self, version_manager):
        """Test creating a new version."""
        version = version_manager.create_version(
            agent_id="test-agent",
            adapter_id="adapter-123",
            model_name="qwen2.5-7b",
            training_data_count=100
        )

        assert version is not None
        assert version.agent_id == "test-agent"
        assert version.adapter_id == "adapter-123"
        assert version.model_name == "qwen2.5-7b"
        assert version.training_data_count == 100
        assert version.parent_version is None

    def test_create_child_version(self, version_manager):
        """Test creating a child version."""
        # Create parent
        parent = version_manager.create_version(
            agent_id="test-agent",
            adapter_id="adapter-1",
            model_name="qwen2.5-7b"
        )

        # Create child
        child = version_manager.create_version(
            agent_id="test-agent",
            adapter_id="adapter-2",
            model_name="qwen2.5-7b",
            parent_version=parent.version_id
        )

        assert child.parent_version == parent.version_id

    def test_activate_version(self, version_manager):
        """Test activating a version."""
        version = version_manager.create_version(
            agent_id="test-agent",
            adapter_id="adapter-1",
            model_name="qwen2.5-7b"
        )

        version_manager.activate_version(
            agent_id="test-agent",
            version_id=version.version_id
        )

        active = version_manager.get_active_version("test-agent")
        assert active is not None
        assert active.version_id == version.version_id
        assert active.is_active is True

    def test_gradual_rollout(self, version_manager):
        """Test gradual version rollout."""
        version = version_manager.create_version(
            agent_id="test-agent",
            adapter_id="adapter-1",
            model_name="qwen2.5-7b"
        )

        version_manager.activate_version(
            agent_id="test-agent",
            version_id=version.version_id,
            gradual=True,
            percentage=25.0
        )

        active = version_manager.get_active_version("test-agent")
        assert active.metadata["rollout_percentage"] == 25.0

    def test_rollback(self, version_manager):
        """Test rolling back to previous version."""
        # Create versions
        v1 = version_manager.create_version(
            agent_id="test-agent",
            adapter_id="adapter-1",
            model_name="qwen2.5-7b"
        )

        v2 = version_manager.create_version(
            agent_id="test-agent",
            adapter_id="adapter-2",
            model_name="qwen2.5-7b",
            parent_version=v1.version_id
        )

        # Activate v2
        version_manager.activate_version("test-agent", v2.version_id)

        # Rollback
        version_manager.rollback("test-agent")

        # Check v1 is active
        active = version_manager.get_active_version("test-agent")
        assert active.version_id == v1.version_id


class TestAdaptiveAgent:
    """Test adaptive agent functionality."""

    @pytest.fixture
    def adaptive_agent(self):
        """Create an adaptive agent."""
        return AdaptiveAgent(
            agent_id="test-agent",
            base_model="qwen2.5-7b",
            evolution_strategy=EvolutionStrategy.BALANCED
        )

    def test_should_evolve_conservative(self, adaptive_agent):
        """Test conservative evolution strategy."""
        adaptive_agent.evolution_strategy = EvolutionStrategy.CONSERVATIVE

        # Low negative feedback - should not evolve
        analysis = FeedbackAnalysis(
            agent_id="test-agent",
            total_feedback=200,
            positive_ratio=0.7,
            negative_ratio=0.3,
            average_rating=4.0,
            common_issues=[],
            improvement_areas=[],
            training_readiness=True,
            confidence_score=0.9
        )

        assert adaptive_agent.should_evolve(analysis) is False

        # High negative feedback - should evolve
        analysis.negative_ratio = 0.5
        assert adaptive_agent.should_evolve(analysis) is True

    def test_should_evolve_aggressive(self, adaptive_agent):
        """Test aggressive evolution strategy."""
        adaptive_agent.evolution_strategy = EvolutionStrategy.AGGRESSIVE

        # Minimal negative feedback - should evolve
        analysis = FeedbackAnalysis(
            agent_id="test-agent",
            total_feedback=50,
            positive_ratio=0.7,
            negative_ratio=0.3,
            average_rating=3.8,
            common_issues=[],
            improvement_areas=[],
            training_readiness=True,
            confidence_score=0.5
        )

        assert adaptive_agent.should_evolve(analysis) is True

    def test_should_evolve_experimental(self, adaptive_agent):
        """Test experimental evolution strategy."""
        adaptive_agent.evolution_strategy = EvolutionStrategy.EXPERIMENTAL

        # Very little feedback - should still evolve
        analysis = FeedbackAnalysis(
            agent_id="test-agent",
            total_feedback=25,
            positive_ratio=0.8,
            negative_ratio=0.2,
            average_rating=4.5,
            common_issues=[],
            improvement_areas=[],
            training_readiness=False,
            confidence_score=0.3
        )

        assert adaptive_agent.should_evolve(analysis) is True

    @pytest.mark.asyncio
    async def test_evolve_with_mock_training(self, adaptive_agent):
        """Test agent evolution with mocked training."""
        with patch('brain.training.training_manager.start_training') as mock_start:
            with patch('brain.training.training_manager.wait_for_completion') as mock_wait:
                mock_start.return_value = "job-123"
                mock_wait.return_value = "adapter-456"

                training_data = [
                    {"input": "Q1", "output": "A1"},
                    {"input": "Q2", "output": "A2"}
                ]

                new_version = await adaptive_agent.evolve(training_data)

                assert new_version is not None
                assert new_version.adapter_id == "adapter-456"
                assert new_version.training_data_count == 2
                assert adaptive_agent.current_version == new_version


class TestEvolutionManager:
    """Test evolution manager functionality."""

    @pytest.fixture
    def evolution_manager(self):
        """Create an evolution manager."""
        return EvolutionManager(check_interval_seconds=1)

    def test_register_agent(self, evolution_manager):
        """Test registering an agent."""
        agent = evolution_manager.register_agent(
            agent_id="test-agent",
            base_model="qwen2.5-7b",
            evolution_strategy=EvolutionStrategy.BALANCED
        )

        assert agent is not None
        assert agent.agent_id == "test-agent"
        assert agent.base_model == "qwen2.5-7b"
        assert agent.evolution_strategy == EvolutionStrategy.BALANCED

        # Check initial version created
        versions = evolution_manager.get_agent_versions("test-agent")
        assert len(versions) == 1

    @pytest.mark.asyncio
    async def test_manual_evolution_trigger(self, evolution_manager):
        """Test manually triggering evolution."""
        # Register agent
        agent = evolution_manager.register_agent(
            agent_id="test-agent",
            base_model="qwen2.5-7b"
        )

        # Mock training
        with patch.object(agent, 'evolve') as mock_evolve:
            mock_version = AgentVersion(
                version_id="v_new",
                agent_id="test-agent",
                adapter_id="adapter-new",
                model_name="qwen2.5-7b",
                created_at=datetime.now()
            )
            mock_evolve.return_value = mock_version

            training_data = [{"input": "Q", "output": "A"}]
            new_version = await evolution_manager.trigger_manual_evolution(
                agent_id="test-agent",
                training_data=training_data
            )

            assert new_version.version_id == "v_new"
            mock_evolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_evolution_monitoring(self, evolution_manager):
        """Test automatic evolution monitoring."""
        # Register agent
        agent = evolution_manager.register_agent(
            agent_id="test-agent",
            base_model="qwen2.5-7b",
            evolution_strategy=EvolutionStrategy.EXPERIMENTAL
        )

        # Mock feedback analysis
        with patch.object(evolution_manager.feedback_collector, 'analyze_feedback') as mock_analyze:
            # Create analysis that triggers evolution
            analysis = FeedbackAnalysis(
                agent_id="test-agent",
                total_feedback=30,
                positive_ratio=0.5,
                negative_ratio=0.5,
                average_rating=3.0,
                common_issues=[],
                improvement_areas=[],
                training_readiness=True,
                confidence_score=0.5
            )
            mock_analyze.return_value = analysis

            # Mock get_training_data
            with patch.object(evolution_manager.feedback_collector, 'get_training_data') as mock_training:
                mock_training.return_value = [{"input": "Q", "output": "A"}]

                # Mock evolve
                with patch.object(agent, 'evolve') as mock_evolve:
                    mock_version = AgentVersion(
                        version_id="v_auto",
                        agent_id="test-agent",
                        adapter_id="adapter-auto",
                        model_name="qwen2.5-7b",
                        created_at=datetime.now()
                    )
                    mock_evolve.return_value = mock_version

                    # Run check
                    await evolution_manager._check_agents_for_evolution()

                    # Verify evolution was triggered
                    mock_evolve.assert_called_once()

    def test_rollback_agent(self, evolution_manager):
        """Test rolling back an agent."""
        # Register agent
        agent = evolution_manager.register_agent(
            agent_id="test-agent",
            base_model="qwen2.5-7b"
        )

        # Create new version
        v1_id = agent.current_version.version_id
        new_version = evolution_manager.version_manager.create_version(
            agent_id="test-agent",
            adapter_id="adapter-2",
            model_name="qwen2.5-7b",
            parent_version=v1_id
        )

        # Activate new version
        evolution_manager.version_manager.activate_version(
            "test-agent",
            new_version.version_id
        )

        # Rollback
        evolution_manager.rollback_agent("test-agent")

        # Check original version is active
        active = evolution_manager.version_manager.get_active_version("test-agent")
        assert active.version_id == v1_id