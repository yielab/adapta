"""Agent implementation"""

import time
import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field
import yaml

from brain.rag import RAGManager
from brain.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Agent configuration"""

    name: str
    description: Optional[str] = None
    model: str = "qwen2.5-3b-instruct"
    system_prompt: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    rag_sources: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 512

    # Adapter configuration
    use_adapter: bool = False  # Whether to use a trained adapter
    adapter_id: Optional[str] = None  # ID of the adapter to use


class Agent:
    """AI Agent with dedicated configuration and knowledge base"""

    def __init__(self, agent_id: str, config: AgentConfig):
        self.id = agent_id
        self.config = config
        self.created = int(time.time())
        self.agent_dir = settings.agents_dir / agent_id
        self.agent_dir.mkdir(parents=True, exist_ok=True)

        # Initialize RAG manager
        self.rag_manager = RAGManager(agent_id)

    def save(self):
        """Save agent configuration to disk"""
        config_path = self.agent_dir / "config.yaml"

        config_dict = {
            "id": self.id,
            "name": self.config.name,
            "description": self.config.description,
            "model": self.config.model,
            "system_prompt": self.config.system_prompt,
            "capabilities": self.config.capabilities,
            "rag_sources": self.config.rag_sources,
            "tools": self.config.tools,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "use_adapter": self.config.use_adapter,
            "adapter_id": self.config.adapter_id,
            "created": self.created,
        }

        with open(config_path, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False)

        logger.info(f"Saved agent {self.id} configuration")

    @classmethod
    def load(cls, agent_id: str) -> Optional["Agent"]:
        """Load agent from disk"""
        config_path = settings.agents_dir / agent_id / "config.yaml"

        if not config_path.exists():
            return None

        try:
            with open(config_path) as f:
                config_dict = yaml.safe_load(f)

            config = AgentConfig(
                name=config_dict["name"],
                description=config_dict.get("description"),
                model=config_dict["model"],
                system_prompt=config_dict.get("system_prompt"),
                capabilities=config_dict.get("capabilities", []),
                rag_sources=config_dict.get("rag_sources", []),
                tools=config_dict.get("tools", []),
                temperature=config_dict.get("temperature", 0.7),
                max_tokens=config_dict.get("max_tokens", 512),
                use_adapter=config_dict.get("use_adapter", False),
                adapter_id=config_dict.get("adapter_id"),
            )

            agent = cls(agent_id, config)
            agent.created = config_dict.get("created", int(time.time()))

            logger.info(f"Loaded agent {agent_id}")
            return agent

        except Exception as e:
            logger.error(f"Failed to load agent {agent_id}: {e}")
            return None

    async def add_knowledge(self, content: str, metadata: Optional[dict] = None):
        """Add knowledge to agent's RAG database"""
        return await self.rag_manager.add_document(content, metadata)

    async def add_knowledge_file(self, file_path: str, metadata: Optional[dict] = None):
        """Add knowledge from file"""
        return await self.rag_manager.add_file(file_path, metadata)

    def set_adapter(self, adapter_id: Optional[str] = None):
        """
        Set the adapter to use for this agent

        Args:
            adapter_id: ID of the adapter to use, or None to use base model
        """
        from brain.core.adapter_manager import adapter_manager

        if adapter_id:
            # Verify adapter exists and belongs to this agent
            adapter = adapter_manager.get_adapter(adapter_id)
            if not adapter:
                raise ValueError(f"Adapter not found: {adapter_id}")
            if adapter.agent_id != self.id:
                raise ValueError(f"Adapter {adapter_id} does not belong to agent {self.id}")

            self.config.use_adapter = True
            self.config.adapter_id = adapter_id
            logger.info(f"Agent {self.id} will use adapter: {adapter_id}")
        else:
            self.config.use_adapter = False
            self.config.adapter_id = None
            logger.info(f"Agent {self.id} will use base model (no adapter)")

        self.save()

    def get_active_adapter(self):
        """Get information about the currently active adapter"""
        from brain.core.adapter_manager import adapter_manager

        if not self.config.use_adapter or not self.config.adapter_id:
            return None

        return adapter_manager.get_adapter(self.config.adapter_id)

    def get_model_name(self) -> str:
        """
        Get the model name to use for inference

        If the agent has a trained adapter that's been merged,
        use the merged model. Otherwise, use the base model.
        """
        adapter = self.get_active_adapter()

        if adapter and adapter.is_merged and adapter.merged_model_path:
            # Use the merged model
            return f"{self.id}_merged"

        # Use base model
        return self.config.model

    def delete(self):
        """Delete agent and all its data"""
        import shutil

        if self.agent_dir.exists():
            shutil.rmtree(self.agent_dir)
            logger.info(f"Deleted agent {self.id}")
