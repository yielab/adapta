"""
Feature flags API endpoints.

Provides runtime control over feature availability.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

from brain.core.feature_flags import (
    get_feature_flags,
    FeatureStatus,
    is_feature_enabled
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/features")


class FeatureStatusUpdate(BaseModel):
    """Feature status update request."""
    status: str = Field(..., description="Feature status (disabled/beta/stable)")
    rollout_percentage: Optional[float] = Field(None, description="Rollout percentage (0-100)")


class FeatureAgentUpdate(BaseModel):
    """Feature agent allowlist update."""
    action: str = Field(..., description="Action (add/remove)")
    agent_ids: List[str] = Field(..., description="Agent IDs to add/remove")


class FeatureCheckRequest(BaseModel):
    """Feature availability check request."""
    feature_name: str = Field(..., description="Feature name")
    agent_id: Optional[str] = Field(None, description="Agent ID")


@router.get("/")
async def list_features():
    """
    List all features and their status.

    Returns comprehensive feature information including:
    - Description
    - Current status
    - Rollout percentage
    - Dependencies
    """
    try:
        flags = get_feature_flags()
        return flags.get_feature_status()

    except Exception as e:
        logger.error(f"Error listing features: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{feature_name}")
async def get_feature(feature_name: str):
    """Get detailed information about a specific feature."""
    try:
        flags = get_feature_flags()

        if feature_name not in flags.features:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

        feature = flags.features[feature_name]
        return {
            "name": feature.name,
            "description": feature.description,
            "status": feature.status.value,
            "rollout_percentage": feature.rollout_percentage,
            "enabled_agents": list(feature.enabled_for_agents),
            "config": feature.config,
            "dependencies": list(feature.dependencies)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting feature {feature_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{feature_name}")
async def update_feature(feature_name: str, update: FeatureStatusUpdate):
    """
    Update feature status and rollout.

    Allows runtime changes to:
    - Feature status (disabled/beta/stable)
    - Rollout percentage
    """
    try:
        flags = get_feature_flags()

        if feature_name not in flags.features:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

        # Update status
        try:
            status = FeatureStatus(update.status)
            flags.features[feature_name].status = status
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

        # Update rollout percentage if provided
        if update.rollout_percentage is not None:
            flags.set_rollout_percentage(feature_name, update.rollout_percentage)

        return {
            "status": "Feature updated successfully",
            "feature": feature_name,
            "new_status": status.value,
            "rollout_percentage": flags.features[feature_name].rollout_percentage
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating feature {feature_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{feature_name}/agents")
async def update_feature_agents(feature_name: str, update: FeatureAgentUpdate):
    """
    Update agent allowlist for a feature.

    Add or remove specific agents from feature access.
    """
    try:
        flags = get_feature_flags()

        if feature_name not in flags.features:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

        if update.action == "add":
            for agent_id in update.agent_ids:
                flags.add_agent_to_feature(feature_name, agent_id)
            message = f"Added {len(update.agent_ids)} agents to feature"

        elif update.action == "remove":
            for agent_id in update.agent_ids:
                flags.remove_agent_from_feature(feature_name, agent_id)
            message = f"Removed {len(update.agent_ids)} agents from feature"

        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {update.action}")

        return {
            "status": message,
            "feature": feature_name,
            "enabled_agents": list(flags.features[feature_name].enabled_for_agents)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating feature agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check")
async def check_feature(request: FeatureCheckRequest):
    """
    Check if a feature is enabled for an agent.

    Takes into account:
    - Feature status
    - Rollout percentage
    - Agent-specific allowlist
    - Dependencies
    """
    try:
        enabled = is_feature_enabled(request.feature_name, request.agent_id)

        flags = get_feature_flags()
        feature = flags.features.get(request.feature_name)

        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature '{request.feature_name}' not found")

        return {
            "feature": request.feature_name,
            "agent_id": request.agent_id,
            "enabled": enabled,
            "status": feature.status.value,
            "reason": _get_enable_reason(feature, request.agent_id, enabled)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking feature: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/{agent_id}")
async def get_agent_features(agent_id: str):
    """Get all features enabled for a specific agent."""
    try:
        flags = get_feature_flags()
        enabled_features = flags.get_enabled_features(agent_id)

        # Get details for each enabled feature
        features = {}
        for name in enabled_features:
            feature = flags.features[name]
            features[name] = {
                "description": feature.description,
                "status": feature.status.value,
                "config": feature.config
            }

        return {
            "agent_id": agent_id,
            "enabled_features": features,
            "feature_count": len(enabled_features)
        }

    except Exception as e:
        logger.error(f"Error getting agent features: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rollout/{feature_name}")
async def set_rollout_percentage(
    feature_name: str,
    percentage: float = Body(..., ge=0, le=100, description="Rollout percentage")
):
    """
    Set gradual rollout percentage for a feature.

    Percentage determines how many agents get the feature randomly.
    """
    try:
        flags = get_feature_flags()

        if feature_name not in flags.features:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

        flags.set_rollout_percentage(feature_name, percentage)

        return {
            "status": "Rollout percentage updated",
            "feature": feature_name,
            "rollout_percentage": percentage
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting rollout percentage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enable/{feature_name}")
async def enable_feature(feature_name: str):
    """Enable a feature (set to BETA status)."""
    try:
        flags = get_feature_flags()

        if feature_name not in flags.features:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

        flags.enable_feature(feature_name, FeatureStatus.BETA)

        return {
            "status": "Feature enabled",
            "feature": feature_name,
            "new_status": "beta"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling feature: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disable/{feature_name}")
async def disable_feature(feature_name: str):
    """Disable a feature."""
    try:
        flags = get_feature_flags()

        if feature_name not in flags.features:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

        flags.disable_feature(feature_name)

        return {
            "status": "Feature disabled",
            "feature": feature_name,
            "new_status": "disabled"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling feature: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def save_configuration(path: str = Body(..., description="Path to save configuration")):
    """Save current feature configuration to file."""
    try:
        flags = get_feature_flags()
        flags.save_to_file(path)

        return {
            "status": "Configuration saved",
            "path": path
        }

    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_enable_reason(feature, agent_id: Optional[str], enabled: bool) -> str:
    """Get human-readable reason for feature enable status."""
    if feature.status == FeatureStatus.DISABLED:
        return "Feature is disabled globally"
    elif feature.status == FeatureStatus.STABLE:
        return "Feature is stable and enabled for all"
    elif agent_id in feature.enabled_for_agents:
        return f"Agent {agent_id} is in allowlist"
    elif enabled and feature.rollout_percentage > 0:
        return f"Agent included in {feature.rollout_percentage}% rollout"
    else:
        return "Agent not included in beta rollout"