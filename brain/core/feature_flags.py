"""
Feature flags for gradual rollout of new capabilities.

Allows enabling/disabling features at runtime without code changes.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class FeatureStatus(Enum):
    """Feature availability status."""
    DISABLED = "disabled"
    BETA = "beta"
    STABLE = "stable"
    DEPRECATED = "deprecated"


@dataclass
class Feature:
    """Feature definition."""
    name: str
    description: str
    status: FeatureStatus = FeatureStatus.DISABLED
    rollout_percentage: float = 0.0  # 0-100
    enabled_for_agents: Set[str] = field(default_factory=set)
    config: Dict[str, Any] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set)

    def is_enabled_for(self, agent_id: Optional[str] = None) -> bool:
        """
        Check if feature is enabled for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            True if feature is enabled
        """
        # Disabled features are never enabled
        if self.status == FeatureStatus.DISABLED:
            return False

        # Stable features are always enabled
        if self.status == FeatureStatus.STABLE:
            return True

        # Check specific agent allowlist
        if agent_id and agent_id in self.enabled_for_agents:
            return True

        # Check rollout percentage (simple hash-based)
        if agent_id and self.rollout_percentage > 0:
            hash_value = abs(hash(f"{self.name}:{agent_id}")) % 100
            return hash_value < self.rollout_percentage

        # Beta features without specific rules are disabled
        return False


class FeatureFlags:
    """
    Centralized feature flag management.

    Features:
    - Runtime enable/disable
    - Gradual rollout
    - Agent-specific flags
    - Configuration management
    """

    # Default feature definitions
    DEFAULT_FEATURES = {
        # Context Management
        "context_management": Feature(
            name="context_management",
            description="Advanced context window optimization",
            status=FeatureStatus.STABLE,
            rollout_percentage=100
        ),

        # Memory System
        "memory_system": Feature(
            name="memory_system",
            description="Multi-tier memory with consolidation",
            status=FeatureStatus.STABLE,
            rollout_percentage=100
        ),

        # RAG Features
        "advanced_rag": Feature(
            name="advanced_rag",
            description="Hybrid search with re-ranking",
            status=FeatureStatus.STABLE,
            rollout_percentage=100
        ),

        "query_expansion": Feature(
            name="query_expansion",
            description="Automatic query expansion for better retrieval",
            status=FeatureStatus.BETA,
            rollout_percentage=50,
            dependencies={"advanced_rag"}
        ),

        "citation_tracking": Feature(
            name="citation_tracking",
            description="Automatic citation generation",
            status=FeatureStatus.BETA,
            rollout_percentage=30,
            dependencies={"advanced_rag"}
        ),

        # Adaptive Features
        "adaptive_evolution": Feature(
            name="adaptive_evolution",
            description="Self-improving agents through feedback",
            status=FeatureStatus.BETA,
            rollout_percentage=20,
            config={"min_interactions": 100}
        ),

        "ab_testing": Feature(
            name="ab_testing",
            description="A/B testing for model comparison",
            status=FeatureStatus.BETA,
            rollout_percentage=25
        ),

        # Routing
        "intelligent_routing": Feature(
            name="intelligent_routing",
            description="Task-based model selection",
            status=FeatureStatus.STABLE,
            rollout_percentage=100
        ),

        # Framework Integration
        "langchain_integration": Feature(
            name="langchain_integration",
            description="LangChain framework compatibility",
            status=FeatureStatus.STABLE,
            rollout_percentage=100
        ),

        "langgraph_integration": Feature(
            name="langgraph_integration",
            description="LangGraph state management",
            status=FeatureStatus.BETA,
            rollout_percentage=40
        ),

        "openclaw_integration": Feature(
            name="openclaw_integration",
            description="OpenClaw deep integration",
            status=FeatureStatus.BETA,
            rollout_percentage=30
        ),

        # Tracing
        "distributed_tracing": Feature(
            name="distributed_tracing",
            description="OpenTelemetry distributed tracing",
            status=FeatureStatus.STABLE,
            rollout_percentage=100
        ),

        # Unified Router
        "unified_router": Feature(
            name="unified_router",
            description="Orchestrated intelligence layer",
            status=FeatureStatus.BETA,
            rollout_percentage=50,
            dependencies={
                "context_management",
                "memory_system",
                "intelligent_routing"
            }
        ),

        # Experimental
        "auto_fine_tuning": Feature(
            name="auto_fine_tuning",
            description="Automatic model fine-tuning",
            status=FeatureStatus.DISABLED,
            rollout_percentage=0,
            dependencies={"adaptive_evolution"}
        ),

        "federated_learning": Feature(
            name="federated_learning",
            description="Privacy-preserving distributed learning",
            status=FeatureStatus.DISABLED,
            rollout_percentage=0
        )
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize feature flags.

        Args:
            config_path: Path to feature configuration file
        """
        self.features: Dict[str, Feature] = self.DEFAULT_FEATURES.copy()
        self.config_path = config_path

        # Load from environment variables
        self._load_from_env()

        # Load from config file
        if config_path and Path(config_path).exists():
            self._load_from_file(config_path)

        logger.info(f"Feature flags initialized with {len(self.features)} features")

    def _load_from_env(self):
        """Load feature flags from environment variables."""
        # Format: BRAIN_FEATURE_<NAME>=enabled|disabled|beta|stable
        for key, value in os.environ.items():
            if key.startswith("BRAIN_FEATURE_"):
                feature_name = key[14:].lower()
                if feature_name in self.features:
                    try:
                        status = FeatureStatus(value.lower())
                        self.features[feature_name].status = status
                        logger.info(f"Feature {feature_name} set to {status} from env")
                    except ValueError:
                        logger.warning(f"Invalid status {value} for feature {feature_name}")

    def _load_from_file(self, path: str):
        """Load feature flags from configuration file."""
        try:
            with open(path, 'r') as f:
                config = json.load(f)

            for name, settings in config.items():
                if name in self.features:
                    feature = self.features[name]

                    # Update status
                    if "status" in settings:
                        feature.status = FeatureStatus(settings["status"])

                    # Update rollout
                    if "rollout_percentage" in settings:
                        feature.rollout_percentage = float(settings["rollout_percentage"])

                    # Update agent list
                    if "enabled_for_agents" in settings:
                        feature.enabled_for_agents = set(settings["enabled_for_agents"])

                    # Update config
                    if "config" in settings:
                        feature.config.update(settings["config"])

                    logger.info(f"Feature {name} updated from config file")

        except Exception as e:
            logger.error(f"Error loading feature config from {path}: {e}")

    def is_enabled(self, feature_name: str, agent_id: Optional[str] = None) -> bool:
        """
        Check if a feature is enabled.

        Args:
            feature_name: Name of the feature
            agent_id: Optional agent identifier

        Returns:
            True if feature is enabled
        """
        if feature_name not in self.features:
            logger.warning(f"Unknown feature: {feature_name}")
            return False

        feature = self.features[feature_name]

        # Check dependencies
        for dep in feature.dependencies:
            if not self.is_enabled(dep, agent_id):
                return False

        return feature.is_enabled_for(agent_id)

    def get_config(self, feature_name: str) -> Dict[str, Any]:
        """
        Get feature configuration.

        Args:
            feature_name: Name of the feature

        Returns:
            Feature configuration dictionary
        """
        if feature_name in self.features:
            return self.features[feature_name].config
        return {}

    def enable_feature(self, feature_name: str, status: FeatureStatus = FeatureStatus.BETA):
        """
        Enable a feature.

        Args:
            feature_name: Name of the feature
            status: New status
        """
        if feature_name in self.features:
            self.features[feature_name].status = status
            logger.info(f"Feature {feature_name} enabled with status {status}")

    def disable_feature(self, feature_name: str):
        """
        Disable a feature.

        Args:
            feature_name: Name of the feature
        """
        if feature_name in self.features:
            self.features[feature_name].status = FeatureStatus.DISABLED
            logger.info(f"Feature {feature_name} disabled")

    def set_rollout_percentage(self, feature_name: str, percentage: float):
        """
        Set rollout percentage for a feature.

        Args:
            feature_name: Name of the feature
            percentage: Rollout percentage (0-100)
        """
        if feature_name in self.features:
            self.features[feature_name].rollout_percentage = max(0, min(100, percentage))
            logger.info(f"Feature {feature_name} rollout set to {percentage}%")

    def add_agent_to_feature(self, feature_name: str, agent_id: str):
        """
        Add an agent to feature allowlist.

        Args:
            feature_name: Name of the feature
            agent_id: Agent identifier
        """
        if feature_name in self.features:
            self.features[feature_name].enabled_for_agents.add(agent_id)
            logger.info(f"Agent {agent_id} added to feature {feature_name}")

    def remove_agent_from_feature(self, feature_name: str, agent_id: str):
        """
        Remove an agent from feature allowlist.

        Args:
            feature_name: Name of the feature
            agent_id: Agent identifier
        """
        if feature_name in self.features:
            self.features[feature_name].enabled_for_agents.discard(agent_id)
            logger.info(f"Agent {agent_id} removed from feature {feature_name}")

    def get_enabled_features(self, agent_id: Optional[str] = None) -> Set[str]:
        """
        Get all enabled features for an agent.

        Args:
            agent_id: Optional agent identifier

        Returns:
            Set of enabled feature names
        """
        return {
            name for name, feature in self.features.items()
            if feature.is_enabled_for(agent_id)
        }

    def get_feature_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all features.

        Returns:
            Dictionary with feature status information
        """
        return {
            name: {
                "description": feature.description,
                "status": feature.status.value,
                "rollout_percentage": feature.rollout_percentage,
                "enabled_agents_count": len(feature.enabled_for_agents),
                "dependencies": list(feature.dependencies)
            }
            for name, feature in self.features.items()
        }

    def save_to_file(self, path: str):
        """
        Save current feature configuration to file.

        Args:
            path: Path to save configuration
        """
        try:
            config = {}
            for name, feature in self.features.items():
                config[name] = {
                    "status": feature.status.value,
                    "rollout_percentage": feature.rollout_percentage,
                    "enabled_for_agents": list(feature.enabled_for_agents),
                    "config": feature.config
                }

            with open(path, 'w') as f:
                json.dump(config, f, indent=2)

            logger.info(f"Feature configuration saved to {path}")

        except Exception as e:
            logger.error(f"Error saving feature config to {path}: {e}")


# Global instance
_feature_flags: Optional[FeatureFlags] = None


def get_feature_flags(config_path: Optional[str] = None) -> FeatureFlags:
    """
    Get or create feature flags instance.

    Args:
        config_path: Optional path to configuration file

    Returns:
        FeatureFlags instance
    """
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlags(config_path)
    return _feature_flags


def is_feature_enabled(feature_name: str, agent_id: Optional[str] = None) -> bool:
    """
    Quick check if a feature is enabled.

    Args:
        feature_name: Name of the feature
        agent_id: Optional agent identifier

    Returns:
        True if feature is enabled
    """
    flags = get_feature_flags()
    return flags.is_enabled(feature_name, agent_id)