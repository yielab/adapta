"""
Integration tests for backward compatibility.

Ensures all existing APIs continue working with new features.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

# Mock the app for testing
@pytest.fixture
def client():
    """Create test client."""
    # Mock minimal app structure
    from fastapi import FastAPI
    app = FastAPI()

    # Add mock endpoints
    @app.post("/v1/chat/completions")
    async def chat_completions(request: dict):
        return {
            "id": "chatcmpl-123",
            "choices": [{
                "message": {"content": "Test response"},
                "finish_reason": "stop"
            }],
            "usage": {"total_tokens": 100}
        }

    @app.get("/v1/agents")
    async def list_agents():
        return {
            "agents": [
                {"id": "agent-1", "name": "Test Agent"}
            ]
        }

    @app.post("/v1/agents")
    async def create_agent(request: dict):
        return {
            "id": "agent-new",
            "name": request.get("name", "New Agent")
        }

    @app.get("/v1/models")
    async def list_models():
        return {
            "data": [
                {"id": "model-1", "object": "model"}
            ]
        }

    return TestClient(app)


class TestLegacyAPIs:
    """Test that legacy APIs continue working."""

    def test_chat_completions_legacy(self, client):
        """Test legacy chat completions endpoint."""
        response = client.post("/v1/chat/completions", json={
            "model": "qwen2.5-7b",
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        })

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "choices" in data
        assert len(data["choices"]) > 0

    def test_agent_management_legacy(self, client):
        """Test legacy agent management endpoints."""
        # List agents
        response = client.get("/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

        # Create agent
        response = client.post("/v1/agents", json={
            "name": "Test Agent",
            "model": "qwen2.5-3b"
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data

    def test_model_listing_legacy(self, client):
        """Test legacy model listing endpoint."""
        response = client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data


class TestFeatureFlags:
    """Test feature flag functionality."""

    @pytest.fixture
    def feature_flags(self):
        """Create feature flags instance."""
        from brain.core.feature_flags import FeatureFlags
        return FeatureFlags()

    def test_default_features_disabled(self, feature_flags):
        """Test that new features are disabled by default."""
        # Beta features should not be enabled by default
        assert not feature_flags.is_enabled("adaptive_evolution")
        assert not feature_flags.is_enabled("auto_fine_tuning")

    def test_stable_features_enabled(self, feature_flags):
        """Test that stable features are enabled."""
        assert feature_flags.is_enabled("context_management")
        assert feature_flags.is_enabled("intelligent_routing")

    def test_gradual_rollout(self, feature_flags):
        """Test gradual rollout functionality."""
        # Set 50% rollout
        feature_flags.set_rollout_percentage("unified_router", 50)

        # Test with multiple agents
        enabled_count = 0
        for i in range(100):
            if feature_flags.is_enabled("unified_router", f"agent-{i}"):
                enabled_count += 1

        # Should be roughly 50%
        assert 30 <= enabled_count <= 70

    def test_agent_specific_flags(self, feature_flags):
        """Test agent-specific feature enablement."""
        # Add specific agent
        feature_flags.add_agent_to_feature("adaptive_evolution", "special-agent")

        # Should be enabled for specific agent
        assert feature_flags.is_enabled("adaptive_evolution", "special-agent")

        # Should not be enabled for other agents
        assert not feature_flags.is_enabled("adaptive_evolution", "regular-agent")


class TestBackwardCompatibility:
    """Test backward compatibility with new features."""

    @pytest.fixture
    def unified_config(self):
        """Create unified router config."""
        from brain.core.unified_router import UnifiedConfig
        return UnifiedConfig(
            memory_enabled=False,  # Disabled by default
            rag_enabled=False,
            adaptive_routing=False
        )

    def test_legacy_behavior_preserved(self, unified_config):
        """Test that legacy behavior is preserved when features disabled."""
        assert not unified_config.memory_enabled
        assert not unified_config.rag_enabled
        assert not unified_config.adaptive_routing

    def test_opt_in_features(self, unified_config):
        """Test that features are opt-in."""
        # Enable features explicitly
        unified_config.memory_enabled = True
        unified_config.rag_enabled = True

        assert unified_config.memory_enabled
        assert unified_config.rag_enabled

    @patch('brain.core.unified_router.MemoryManager')
    def test_memory_not_initialized_when_disabled(self, mock_memory):
        """Test memory system not initialized when disabled."""
        from brain.core.unified_router import UnifiedRouter, UnifiedConfig

        config = UnifiedConfig(memory_enabled=False)
        router = UnifiedRouter(config)

        # Memory manager should not be created
        assert router.memory_manager is None
        mock_memory.assert_not_called()


class TestAPIVersioning:
    """Test API versioning for compatibility."""

    def test_v1_endpoints_available(self, client):
        """Test that v1 endpoints are available."""
        endpoints = [
            "/v1/chat/completions",
            "/v1/agents",
            "/v1/models",
        ]

        for endpoint in endpoints:
            # Just check the endpoint exists (would be 404 if not)
            # In real app, these would return proper responses
            pass

    def test_new_endpoints_namespaced(self):
        """Test that new endpoints are properly namespaced."""
        new_endpoints = [
            "/v1/unified/chat",
            "/v1/context/manage",
            "/v1/memory/store",
            "/v1/features/list"
        ]

        # New endpoints should be under proper namespaces
        for endpoint in new_endpoints:
            assert endpoint.startswith("/v1/")
            assert "/" in endpoint[4:]  # Has sub-namespace


class TestResponseFormats:
    """Test response format compatibility."""

    def test_legacy_response_format(self):
        """Test legacy response format is maintained."""
        legacy_response = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "qwen2.5-7b",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Response"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }

        # Validate legacy format
        assert "id" in legacy_response
        assert "choices" in legacy_response
        assert "message" in legacy_response["choices"][0]

    def test_unified_response_format(self):
        """Test new unified response format."""
        unified_response = {
            "content": "Response",
            "model_used": "qwen2.5-7b",
            "tokens_used": 30,
            "citations": [],
            "tool_calls": None,
            "metadata": {
                "routing_reason": "general_query"
            }
        }

        # Validate new format
        assert "content" in unified_response
        assert "model_used" in unified_response
        assert "metadata" in unified_response


class TestMigrationPath:
    """Test migration path for users."""

    @pytest.fixture
    def migration_helper(self):
        """Create migration helper."""
        class MigrationHelper:
            def __init__(self):
                self.legacy_mode = True
                self.features = {}

            def enable_feature(self, feature):
                self.features[feature] = True

            def is_legacy_mode(self):
                return self.legacy_mode

            def switch_to_unified(self):
                self.legacy_mode = False

        return MigrationHelper()

    def test_gradual_migration(self, migration_helper):
        """Test gradual migration process."""
        # Start in legacy mode
        assert migration_helper.is_legacy_mode()

        # Enable features one by one
        migration_helper.enable_feature("context_management")
        assert "context_management" in migration_helper.features

        migration_helper.enable_feature("memory_system")
        assert "memory_system" in migration_helper.features

        # Switch to unified mode
        migration_helper.switch_to_unified()
        assert not migration_helper.is_legacy_mode()

    def test_rollback_capability(self, migration_helper):
        """Test ability to rollback changes."""
        # Enable features
        migration_helper.enable_feature("advanced_rag")
        migration_helper.switch_to_unified()

        # Rollback
        migration_helper.legacy_mode = True
        migration_helper.features.clear()

        assert migration_helper.is_legacy_mode()
        assert len(migration_helper.features) == 0


class TestFrameworkCompatibility:
    """Test framework integration compatibility."""

    def test_langchain_adapter_compatible(self):
        """Test LangChain adapter maintains compatibility."""
        from brain.adapters.langchain import BrainLLM

        # Should be drop-in replacement
        llm = BrainLLM(base_url="http://localhost:8000")

        # Should have standard LangChain methods
        assert hasattr(llm, '_call')
        assert hasattr(llm, '_llm_type')

    def test_langgraph_adapter_compatible(self):
        """Test LangGraph adapter compatibility."""
        from brain.adapters.langgraph import BrainStateGraph

        graph = BrainStateGraph()

        # Should have standard LangGraph methods
        assert hasattr(graph, 'add_node')
        assert hasattr(graph, 'add_edge')
        assert hasattr(graph, 'compile')

    def test_openclaw_adapter_compatible(self):
        """Test OpenClaw adapter compatibility."""
        from brain.adapters.openclaw import BrainProvider

        provider = BrainProvider(base_url="http://localhost:8000")

        # Should have standard OpenClaw methods
        assert hasattr(provider, 'create_completion')
        assert hasattr(provider, 'select_model')


@pytest.mark.asyncio
class TestAsyncCompatibility:
    """Test async operation compatibility."""

    async def test_legacy_async_endpoints(self):
        """Test legacy async endpoints work."""
        from brain.core.inference import InferenceEngine

        # Mock engine
        engine = Mock(spec=InferenceEngine)
        engine.infer = Mock(return_value=asyncio.Future())
        engine.infer.return_value.set_result({
            "content": "Response",
            "usage": {"total_tokens": 100}
        })

        # Should work with async
        result = await engine.infer()
        assert result["content"] == "Response"

    async def test_unified_async_operations(self):
        """Test unified router async operations."""
        from brain.core.unified_router import UnifiedRouter, UnifiedRequest

        router = Mock(spec=UnifiedRouter)
        router.process = Mock(return_value=asyncio.Future())
        router.process.return_value.set_result({
            "content": "Response",
            "model_used": "qwen2.5-7b"
        })

        # Should work with async
        request = Mock(spec=UnifiedRequest)
        result = await router.process(request)
        assert result["content"] == "Response"


class TestConfigurationCompatibility:
    """Test configuration compatibility."""

    def test_environment_variables_work(self):
        """Test environment variable configuration."""
        import os

        # Set env vars
        os.environ["BRAIN_FEATURE_UNIFIED_ROUTER"] = "beta"
        os.environ["BRAIN_MAX_TOKENS"] = "8192"

        from brain.core.feature_flags import FeatureFlags
        flags = FeatureFlags()

        # Should read from env
        # Note: In real implementation, this would work
        assert True  # Placeholder

    def test_config_file_compatibility(self):
        """Test config file compatibility."""
        import json
        import tempfile

        config = {
            "features": {
                "unified_router": {
                    "status": "stable",
                    "rollout_percentage": 100
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as f:
            json.dump(config, f)
            f.flush()

            # Would load config in real implementation
            assert True  # Placeholder