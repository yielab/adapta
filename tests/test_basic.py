"""Basic tests for Brain"""

import pytest
from brain import __version__
from brain.config import settings


def test_version():
    """Test version is set"""
    assert __version__ == "0.1.0"


def test_settings():
    """Test settings are loaded"""
    assert settings.host is not None
    assert settings.port > 0
    assert settings.data_dir.exists()


@pytest.mark.asyncio
async def test_model_manager():
    """Test model manager initialization"""
    from brain.core import model_manager

    models = model_manager.list_models()
    assert len(models) > 0
    assert any(m.name == "qwen2.5-3b-instruct" for m in models)


@pytest.mark.asyncio
async def test_agent_manager():
    """Test agent manager initialization"""
    from brain.agents import agent_manager

    await agent_manager.load_agents()
    agents = agent_manager.list_agents()
    assert isinstance(agents, list)
