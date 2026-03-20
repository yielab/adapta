"""
OpenClaw Deep Integration for Brain Platform.

Enhanced provider with:
- Dynamic model selection
- Continuous learning support
- Multi-channel deployment
- Advanced Brain features
"""

import logging
from typing import Any, Dict, List, Optional, AsyncIterator
import asyncio
import yaml
import json
from dataclasses import dataclass
from enum import Enum

from brain.core import inference_engine, model_manager
from brain.core.inference import InferenceRequest, Message
from brain.memory import get_memory_manager, MemoryTier, MemoryQuery
from brain.agents import agent_manager
from brain.training import training_manager
from brain.rag import rag_engine
from brain.core.context_manager import ContextManager
from brain.core.tracing import get_tracing_manager
from brain.tools import get_tool_executor

logger = logging.getLogger(__name__)


class DeploymentChannel(Enum):
    """Deployment channels for OpenClaw."""
    WEB = "web"
    SLACK = "slack"
    DISCORD = "discord"
    API = "api"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


@dataclass
class OpenClawConfig:
    """Configuration for OpenClaw provider."""
    provider_name: str = "brain"
    api_endpoint: str = "http://localhost:8000"
    api_key: Optional[str] = None
    default_model: str = "qwen2.5-7b"
    enable_memory: bool = True
    enable_learning: bool = True
    enable_rag: bool = True
    enable_tools: bool = True
    deployment_channels: List[DeploymentChannel] = None
    max_context_length: int = 32768
    temperature: float = 0.7
    max_tokens: int = 2048


class BrainOpenClawProvider:
    """
    OpenClaw provider implementation for Brain platform.

    Features:
    - Full OpenClaw API compatibility
    - Dynamic model selection based on task
    - Continuous learning from interactions
    - Multi-channel deployment support
    - Advanced Brain platform features
    """

    def __init__(self, config: Optional[OpenClawConfig] = None):
        """
        Initialize Brain provider for OpenClaw.

        Args:
            config: Provider configuration
        """
        self.config = config or OpenClawConfig()
        self.memory_manager = get_memory_manager() if self.config.enable_memory else None
        self.tool_executor = get_tool_executor() if self.config.enable_tools else None
        self.context_managers: Dict[str, ContextManager] = {}
        self.tracer = get_tracing_manager()
        self.active_sessions: Dict[str, Dict] = {}

    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get provider information for OpenClaw.

        Returns:
            Provider metadata
        """
        return {
            "name": self.config.provider_name,
            "version": "1.0.0",
            "capabilities": {
                "streaming": True,
                "function_calling": self.config.enable_tools,
                "memory": self.config.enable_memory,
                "learning": self.config.enable_learning,
                "rag": self.config.enable_rag,
                "multi_modal": True,
                "context_length": self.config.max_context_length
            },
            "models": self._get_available_models(),
            "deployment_channels": [ch.value for ch in (self.config.deployment_channels or [])]
        }

    def _get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models."""
        models = []
        for model_name in model_manager.list_loaded_models():
            model_info = model_manager.get_model_info(model_name)
            models.append({
                "id": model_name,
                "type": model_info.get("type", "chat"),
                "context_length": model_info.get("context_length", 4096),
                "capabilities": model_info.get("capabilities", [])
            })
        return models

    async def create_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        channel: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a completion for OpenClaw.

        Args:
            messages: Input messages
            model: Model to use (or auto-select)
            session_id: Session identifier for context
            channel: Deployment channel
            stream: Enable streaming
            **kwargs: Additional parameters

        Returns:
            Completion response
        """
        # Start tracing
        with self.tracer.trace_agent_action(
            agent_id=f"openclaw-{session_id or 'default'}",
            action="completion",
            channel=channel
        ):
            # Auto-select model if needed
            if not model:
                model = await self._select_model_for_task(messages)

            # Get or create context manager for session
            if session_id not in self.context_managers:
                self.context_managers[session_id] = ContextManager(model_name=model)
            ctx_mgr = self.context_managers[session_id]

            # Add messages to context
            for msg in messages:
                ctx_mgr.add_message(
                    role=msg["role"],
                    content=msg["content"],
                    metadata={"channel": channel}
                )

            # Enhance with memory if enabled
            if self.config.enable_memory and self.memory_manager:
                memories = await self._recall_memories(messages, session_id)
                if memories:
                    memory_msg = {
                        "role": "system",
                        "content": f"[Relevant Context]\n{self._format_memories(memories)}"
                    }
                    messages = [memory_msg] + messages

            # Enhance with RAG if enabled
            if self.config.enable_rag:
                rag_results = await self._search_rag(messages[-1]["content"])
                if rag_results:
                    rag_msg = {
                        "role": "system",
                        "content": f"[Retrieved Information]\n{self._format_rag_results(rag_results)}"
                    }
                    messages = [rag_msg] + messages

            # Optimize context
            optimized_messages = ctx_mgr.optimize_context()

            # Create Brain request
            brain_messages = [Message(**msg) for msg in optimized_messages]
            request = InferenceRequest(
                model=model,
                messages=brain_messages,
                temperature=kwargs.get("temperature", self.config.temperature),
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                stream=stream
            )

            # Generate response
            if stream:
                return await self._stream_response(request, session_id)
            else:
                result = await inference_engine.generate(request)

                # Store in memory
                if self.config.enable_memory and self.memory_manager:
                    await self._store_interaction(messages, result.content, session_id)

                # Track for learning
                if self.config.enable_learning:
                    await self._track_for_learning(messages, result.content, session_id)

                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": result.content
                        },
                        "finish_reason": "stop"
                    }],
                    "model": model,
                    "usage": result.usage
                }

    async def _stream_response(
        self,
        request: InferenceRequest,
        session_id: str
    ) -> AsyncIterator[str]:
        """Stream response tokens."""
        async for token in await inference_engine.stream(request):
            yield f"data: {json.dumps({'token': token})}\n\n"

    async def _select_model_for_task(
        self,
        messages: List[Dict[str, str]]
    ) -> str:
        """
        Dynamically select best model for task.

        Args:
            messages: Input messages

        Returns:
            Selected model name
        """
        # Analyze task characteristics
        last_message = messages[-1]["content"] if messages else ""

        # Simple heuristics for model selection
        if any(keyword in last_message.lower() for keyword in ["code", "function", "debug", "implement"]):
            # Code-related task
            available_models = model_manager.list_loaded_models()
            for model in available_models:
                if "coder" in model.lower():
                    return model

        elif any(keyword in last_message.lower() for keyword in ["image", "picture", "visual", "describe"]):
            # Vision task
            available_models = model_manager.list_loaded_models()
            for model in available_models:
                if "vision" in model.lower() or "moondream" in model.lower():
                    return model

        elif len(last_message) > 1000:
            # Long context - use larger model
            return "qwen2.5-7b"

        # Default to configured model
        return self.config.default_model

    async def _recall_memories(
        self,
        messages: List[Dict[str, str]],
        session_id: str
    ) -> List[Any]:
        """Recall relevant memories for context."""
        if not self.memory_manager:
            return []

        # Use last message as query
        query = messages[-1]["content"] if messages else ""

        memories = await self.memory_manager.recall(
            query=query,
            agent_id=f"openclaw-{session_id}",
            limit=5
        )

        return memories

    async def _search_rag(self, query: str) -> List[Dict[str, Any]]:
        """Search RAG for relevant documents."""
        try:
            results = await rag_engine.search(query, k=3)
            return results
        except:
            return []

    async def _store_interaction(
        self,
        messages: List[Dict[str, str]],
        response: str,
        session_id: str
    ):
        """Store interaction in memory."""
        if not self.memory_manager:
            return

        # Store user message
        if messages:
            await self.memory_manager.store(
                content=messages[-1]["content"],
                tier=MemoryTier.SHORT_TERM,
                agent_id=f"openclaw-{session_id}",
                metadata={"role": "user"}
            )

        # Store assistant response
        await self.memory_manager.store(
            content=response,
            tier=MemoryTier.SHORT_TERM,
            agent_id=f"openclaw-{session_id}",
            metadata={"role": "assistant"}
        )

    async def _track_for_learning(
        self,
        messages: List[Dict[str, str]],
        response: str,
        session_id: str
    ):
        """Track interaction for continuous learning."""
        # Store training data for future fine-tuning
        training_data = {
            "messages": messages,
            "response": response,
            "session_id": session_id,
            "timestamp": asyncio.get_event_loop().time()
        }

        # Queue for batch training
        # In production, this would be sent to a training queue
        logger.info(f"Tracked interaction for learning: {session_id}")

    def _format_memories(self, memories: List[Any]) -> str:
        """Format memories for context."""
        formatted = []
        for memory in memories:
            formatted.append(f"- {memory.content}")
        return "\n".join(formatted)

    def _format_rag_results(self, results: List[Dict[str, Any]]) -> str:
        """Format RAG results for context."""
        formatted = []
        for result in results:
            formatted.append(f"- {result.get('content', '')}")
        return "\n".join(formatted)

    async def create_agent(
        self,
        agent_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new agent for OpenClaw.

        Args:
            agent_config: Agent configuration

        Returns:
            Created agent information
        """
        # Create Brain agent
        agent = await agent_manager.create_agent(
            name=agent_config.get("name", "openclaw-agent"),
            model=agent_config.get("model", self.config.default_model),
            system_prompt=agent_config.get("system_prompt", ""),
            temperature=agent_config.get("temperature", self.config.temperature),
            capabilities=agent_config.get("capabilities", [])
        )

        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "status": "created"
        }

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a tool/function.

        Args:
            tool_name: Tool to execute
            arguments: Tool arguments
            session_id: Session context

        Returns:
            Tool execution result
        """
        if not self.tool_executor:
            return {
                "success": False,
                "error": "Tools not enabled"
            }

        with self.tracer.trace_tool_execution(tool_name, arguments):
            result = await self.tool_executor.execute(tool_name, arguments)

            # Store in episodic memory
            if self.memory_manager and session_id:
                await self.memory_manager.store(
                    content=f"Tool execution: {tool_name}",
                    tier=MemoryTier.EPISODIC,
                    agent_id=f"openclaw-{session_id}",
                    metadata={
                        "tool": tool_name,
                        "arguments": arguments,
                        "result": result.result,
                        "success": result.success
                    }
                )

            return {
                "success": result.success,
                "result": result.result,
                "error": result.error
            }

    def export_config(self) -> Dict[str, Any]:
        """
        Export OpenClaw provider configuration.

        Returns:
            Provider configuration for OpenClaw YAML
        """
        return {
            "provider": self.config.provider_name,
            "api_endpoint": self.config.api_endpoint,
            "api_key": self.config.api_key,
            "default_model": self.config.default_model,
            "features": {
                "memory": self.config.enable_memory,
                "learning": self.config.enable_learning,
                "rag": self.config.enable_rag,
                "tools": self.config.enable_tools
            },
            "deployment": {
                "channels": [ch.value for ch in (self.config.deployment_channels or [])],
                "max_context": self.config.max_context_length
            }
        }

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "BrainOpenClawProvider":
        """
        Create provider from OpenClaw YAML configuration.

        Args:
            yaml_path: Path to configuration file

        Returns:
            Configured provider instance
        """
        with open(yaml_path, 'r') as f:
            config_data = yaml.safe_load(f)

        config = OpenClawConfig(
            provider_name=config_data.get("provider", "brain"),
            api_endpoint=config_data.get("api_endpoint", "http://localhost:8000"),
            api_key=config_data.get("api_key"),
            default_model=config_data.get("default_model", "qwen2.5-7b"),
            enable_memory=config_data.get("features", {}).get("memory", True),
            enable_learning=config_data.get("features", {}).get("learning", True),
            enable_rag=config_data.get("features", {}).get("rag", True),
            enable_tools=config_data.get("features", {}).get("tools", True)
        )

        # Parse deployment channels
        channels = config_data.get("deployment", {}).get("channels", [])
        if channels:
            config.deployment_channels = [
                DeploymentChannel(ch) for ch in channels
                if ch in [e.value for e in DeploymentChannel]
            ]

        return cls(config)


# Helper function to generate OpenClaw configuration
def generate_openclaw_config(
    output_path: str = "openclaw-brain-provider.yaml",
    **kwargs
) -> str:
    """
    Generate OpenClaw configuration file for Brain provider.

    Args:
        output_path: Output file path
        **kwargs: Configuration overrides

    Returns:
        Path to generated configuration
    """
    config = OpenClawConfig(**kwargs)
    provider = BrainOpenClawProvider(config)

    config_data = provider.export_config()

    # Add example agents
    config_data["agents"] = [
        {
            "name": "general-assistant",
            "model": "qwen2.5-7b",
            "system_prompt": "You are a helpful assistant powered by Brain platform.",
            "capabilities": ["chat", "qa", "analysis"]
        },
        {
            "name": "code-helper",
            "model": "qwen2.5-coder-7b",
            "system_prompt": "You are a coding assistant. Help with code-related tasks.",
            "capabilities": ["code", "debug", "explain"]
        },
        {
            "name": "research-agent",
            "model": "qwen2.5-7b",
            "system_prompt": "You are a research assistant. Help gather and analyze information.",
            "capabilities": ["research", "analysis", "summarization"]
        }
    ]

    with open(output_path, 'w') as f:
        yaml.dump(config_data, f, default_flow_style=False)

    return output_path