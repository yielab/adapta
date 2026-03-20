"""
Evolution manager for adaptive agents.

Handles automatic fine-tuning and version management.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import uuid
from pathlib import Path

from brain.agents import agent_manager
from brain.training import training_manager
from brain.agents.adaptive.feedback_collector import FeedbackCollector, FeedbackAnalysis

logger = logging.getLogger(__name__)


class EvolutionStrategy(Enum):
    """Strategies for agent evolution."""
    CONSERVATIVE = "conservative"  # Only evolve on significant negative feedback
    AGGRESSIVE = "aggressive"  # Evolve frequently for improvement
    BALANCED = "balanced"  # Balance between stability and improvement
    EXPERIMENTAL = "experimental"  # Test new approaches frequently


@dataclass
class AgentVersion:
    """A version of an agent."""
    version_id: str
    agent_id: str
    adapter_id: Optional[str]
    model_name: str
    created_at: datetime
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    training_data_count: int = 0
    parent_version: Optional[str] = None
    is_active: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version_id": self.version_id,
            "agent_id": self.agent_id,
            "adapter_id": self.adapter_id,
            "model_name": self.model_name,
            "created_at": self.created_at.isoformat(),
            "performance_metrics": self.performance_metrics,
            "training_data_count": self.training_data_count,
            "parent_version": self.parent_version,
            "is_active": self.is_active,
            "metadata": self.metadata
        }


class VersionManager:
    """
    Manages agent versions and seamless switching.

    Features:
    - Version tracking
    - Performance comparison
    - Rollback capability
    - Gradual rollout
    """

    def __init__(self):
        """Initialize version manager."""
        self.versions: Dict[str, List[AgentVersion]] = {}
        self.active_versions: Dict[str, str] = {}  # agent_id -> version_id

    def create_version(
        self,
        agent_id: str,
        adapter_id: Optional[str],
        model_name: str,
        parent_version: Optional[str] = None,
        training_data_count: int = 0
    ) -> AgentVersion:
        """
        Create a new agent version.

        Args:
            agent_id: Agent identifier
            adapter_id: Fine-tuned adapter ID
            model_name: Base model name
            parent_version: Parent version ID
            training_data_count: Number of training samples

        Returns:
            Created version
        """
        version = AgentVersion(
            version_id=f"v_{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            adapter_id=adapter_id,
            model_name=model_name,
            created_at=datetime.now(),
            training_data_count=training_data_count,
            parent_version=parent_version
        )

        if agent_id not in self.versions:
            self.versions[agent_id] = []

        self.versions[agent_id].append(version)

        logger.info(f"Created version {version.version_id} for agent {agent_id}")

        return version

    def activate_version(
        self,
        agent_id: str,
        version_id: str,
        gradual: bool = False,
        percentage: float = 100.0
    ):
        """
        Activate a specific version.

        Args:
            agent_id: Agent identifier
            version_id: Version to activate
            gradual: Use gradual rollout
            percentage: Percentage of traffic for new version
        """
        # Deactivate current version
        if agent_id in self.active_versions:
            current = self._get_version(agent_id, self.active_versions[agent_id])
            if current:
                current.is_active = False

        # Activate new version
        new_version = self._get_version(agent_id, version_id)
        if new_version:
            new_version.is_active = True
            self.active_versions[agent_id] = version_id

            if gradual:
                new_version.metadata["rollout_percentage"] = percentage

            logger.info(f"Activated version {version_id} for agent {agent_id}")

    def _get_version(
        self,
        agent_id: str,
        version_id: str
    ) -> Optional[AgentVersion]:
        """Get a specific version."""
        versions = self.versions.get(agent_id, [])
        for v in versions:
            if v.version_id == version_id:
                return v
        return None

    def get_active_version(self, agent_id: str) -> Optional[AgentVersion]:
        """Get the active version for an agent."""
        version_id = self.active_versions.get(agent_id)
        if version_id:
            return self._get_version(agent_id, version_id)
        return None

    def rollback(self, agent_id: str):
        """
        Rollback to previous version.

        Args:
            agent_id: Agent identifier
        """
        current = self.get_active_version(agent_id)
        if current and current.parent_version:
            self.activate_version(agent_id, current.parent_version)
            logger.info(f"Rolled back agent {agent_id} to version {current.parent_version}")


class AdaptiveAgent:
    """
    An agent that can evolve and improve over time.

    Features:
    - Automatic fine-tuning
    - Version management
    - Performance tracking
    """

    def __init__(
        self,
        agent_id: str,
        base_model: str,
        evolution_strategy: EvolutionStrategy = EvolutionStrategy.BALANCED
    ):
        """
        Initialize adaptive agent.

        Args:
            agent_id: Agent identifier
            base_model: Base model name
            evolution_strategy: Evolution strategy
        """
        self.agent_id = agent_id
        self.base_model = base_model
        self.evolution_strategy = evolution_strategy
        self.current_version: Optional[AgentVersion] = None
        self.training_in_progress = False

    async def evolve(
        self,
        training_data: List[Dict[str, Any]],
        validation_split: float = 0.1
    ) -> AgentVersion:
        """
        Evolve the agent with new training data.

        Args:
            training_data: Training samples
            validation_split: Validation data ratio

        Returns:
            New agent version
        """
        if self.training_in_progress:
            logger.warning(f"Training already in progress for agent {self.agent_id}")
            return self.current_version

        self.training_in_progress = True

        try:
            # Trigger fine-tuning
            job_id = await training_manager.start_training(
                agent_id=self.agent_id,
                training_data=training_data,
                validation_split=validation_split,
                base_model=self.base_model
            )

            # Wait for training completion
            adapter_id = await training_manager.wait_for_completion(job_id)

            # Create new version
            parent_version = self.current_version.version_id if self.current_version else None
            new_version = AgentVersion(
                version_id=f"v_{uuid.uuid4().hex[:8]}",
                agent_id=self.agent_id,
                adapter_id=adapter_id,
                model_name=self.base_model,
                created_at=datetime.now(),
                training_data_count=len(training_data),
                parent_version=parent_version
            )

            self.current_version = new_version

            logger.info(f"Agent {self.agent_id} evolved to version {new_version.version_id}")

            return new_version

        finally:
            self.training_in_progress = False

    def should_evolve(
        self,
        feedback_analysis: FeedbackAnalysis
    ) -> bool:
        """
        Determine if the agent should evolve.

        Args:
            feedback_analysis: Feedback analysis results

        Returns:
            True if evolution should occur
        """
        if self.evolution_strategy == EvolutionStrategy.CONSERVATIVE:
            # Only evolve on significant negative feedback
            return (
                feedback_analysis.negative_ratio > 0.4 and
                feedback_analysis.total_feedback >= 200
            )

        elif self.evolution_strategy == EvolutionStrategy.AGGRESSIVE:
            # Evolve frequently
            return (
                feedback_analysis.total_feedback >= 50 and
                (feedback_analysis.negative_ratio > 0.2 or
                 feedback_analysis.average_rating and feedback_analysis.average_rating < 4.0)
            )

        elif self.evolution_strategy == EvolutionStrategy.BALANCED:
            # Default balanced approach
            return feedback_analysis.should_trigger_training()

        elif self.evolution_strategy == EvolutionStrategy.EXPERIMENTAL:
            # Always ready to evolve
            return feedback_analysis.total_feedback >= 25

        return False


class EvolutionManager:
    """
    Manages evolution for all adaptive agents.

    Features:
    - Automatic training triggers
    - Version management
    - Performance tracking
    - Rollback capability
    """

    def __init__(
        self,
        feedback_collector: Optional[FeedbackCollector] = None,
        check_interval_seconds: int = 3600  # 1 hour
    ):
        """
        Initialize evolution manager.

        Args:
            feedback_collector: Feedback collection system
            check_interval_seconds: Interval for evolution checks
        """
        self.feedback_collector = feedback_collector or FeedbackCollector()
        self.version_manager = VersionManager()
        self.adaptive_agents: Dict[str, AdaptiveAgent] = {}
        self.check_interval = check_interval_seconds
        self.evolution_task: Optional[asyncio.Task] = None

    def register_agent(
        self,
        agent_id: str,
        base_model: str,
        evolution_strategy: EvolutionStrategy = EvolutionStrategy.BALANCED
    ) -> AdaptiveAgent:
        """
        Register an agent for adaptive evolution.

        Args:
            agent_id: Agent identifier
            base_model: Base model name
            evolution_strategy: Evolution strategy

        Returns:
            Adaptive agent instance
        """
        agent = AdaptiveAgent(
            agent_id=agent_id,
            base_model=base_model,
            evolution_strategy=evolution_strategy
        )

        self.adaptive_agents[agent_id] = agent

        # Create initial version
        initial_version = self.version_manager.create_version(
            agent_id=agent_id,
            adapter_id=None,
            model_name=base_model
        )
        agent.current_version = initial_version
        self.version_manager.activate_version(agent_id, initial_version.version_id)

        logger.info(f"Registered adaptive agent {agent_id} with strategy {evolution_strategy.value}")

        return agent

    async def start_evolution_monitoring(self):
        """Start background evolution monitoring."""
        if self.evolution_task:
            logger.warning("Evolution monitoring already running")
            return

        self.evolution_task = asyncio.create_task(self._evolution_loop())
        logger.info("Started evolution monitoring")

    async def stop_evolution_monitoring(self):
        """Stop background evolution monitoring."""
        if self.evolution_task:
            self.evolution_task.cancel()
            try:
                await self.evolution_task
            except asyncio.CancelledError:
                pass
            self.evolution_task = None
            logger.info("Stopped evolution monitoring")

    async def _evolution_loop(self):
        """Background task for automatic evolution."""
        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_agents_for_evolution()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Evolution check error: {e}")

    async def _check_agents_for_evolution(self):
        """Check all agents for evolution triggers."""
        for agent_id, agent in self.adaptive_agents.items():
            try:
                # Get feedback analysis
                analysis = await self.feedback_collector.analyze_feedback(agent_id)

                # Check if evolution should occur
                if agent.should_evolve(analysis):
                    logger.info(f"Triggering evolution for agent {agent_id}")

                    # Get training data
                    training_data = await self.feedback_collector.get_training_data(
                        agent_id=agent_id,
                        include_corrections=True,
                        min_rating=4
                    )

                    if training_data:
                        # Trigger evolution
                        new_version = await agent.evolve(training_data)

                        # Activate new version
                        self.version_manager.activate_version(
                            agent_id=agent_id,
                            version_id=new_version.version_id,
                            gradual=True,
                            percentage=50.0  # Start with 50% traffic
                        )

                        # Clear old feedback
                        self.feedback_collector.clear_feedback(
                            agent_id=agent_id,
                            older_than=datetime.now() - timedelta(days=7)
                        )

            except Exception as e:
                logger.error(f"Evolution check failed for agent {agent_id}: {e}")

    async def trigger_manual_evolution(
        self,
        agent_id: str,
        training_data: Optional[List[Dict[str, Any]]] = None
    ) -> AgentVersion:
        """
        Manually trigger agent evolution.

        Args:
            agent_id: Agent identifier
            training_data: Training data (uses feedback if not provided)

        Returns:
            New version
        """
        agent = self.adaptive_agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not registered for evolution")

        if not training_data:
            training_data = await self.feedback_collector.get_training_data(agent_id)

        if not training_data:
            raise ValueError("No training data available")

        return await agent.evolve(training_data)

    def get_agent_versions(self, agent_id: str) -> List[AgentVersion]:
        """Get all versions for an agent."""
        return self.version_manager.versions.get(agent_id, [])

    def rollback_agent(self, agent_id: str):
        """Rollback an agent to previous version."""
        self.version_manager.rollback(agent_id)