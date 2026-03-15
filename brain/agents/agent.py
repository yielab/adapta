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
        await self.rag_manager.add_document(content, metadata)

    async def add_knowledge_file(self, file_path: str, metadata: Optional[dict] = None):
        """Add knowledge from file"""
        await self.rag_manager.add_file(file_path, metadata)

    def delete(self):
        """Delete agent and all its data"""
        import shutil

        if self.agent_dir.exists():
            shutil.rmtree(self.agent_dir)
            logger.info(f"Deleted agent {self.id}")
