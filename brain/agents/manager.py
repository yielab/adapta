"""Agent manager"""

import logging
import uuid
from typing import Dict, List, Optional

from brain.agents.agent import Agent, AgentConfig
from brain.agents.templates import get_template
from brain.shared_models import AgentInfo
from brain.config import settings

logger = logging.getLogger(__name__)


class AgentManager:
    """Manages all agents"""

    def __init__(self):
        self._agents: Dict[str, Agent] = {}

    async def load_agents(self):
        """Load all agents from disk"""
        agents_dir = settings.agents_dir

        if not agents_dir.exists():
            logger.info("No agents directory found, creating...")
            return

        for agent_dir in agents_dir.iterdir():
            if agent_dir.is_dir():
                agent = Agent.load(agent_dir.name)
                if agent:
                    self._agents[agent.id] = agent
                    logger.info(f"Loaded agent: {agent.config.name} ({agent.id})")

        logger.info(f"Loaded {len(self._agents)} agents")

    async def create_agent(
        self,
        name: str,
        description: Optional[str] = None,
        template: Optional[str] = "general",
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AgentInfo:
        """Create a new agent"""

        # Get template if specified
        template_config = {}
        if template:
            try:
                template_config = get_template(template)
            except ValueError as e:
                logger.warning(f"Unknown template {template}, using defaults: {e}")

        # Merge configurations (explicit params override template)
        config = AgentConfig(
            name=name,
            description=description or template_config.get("description"),
            model=model or template_config.get("model", "qwen2.5-3b-instruct"),
            system_prompt=system_prompt or template_config.get("system_prompt"),
            capabilities=capabilities or template_config.get("capabilities", []),
            temperature=temperature if temperature is not None else template_config.get("temperature", 0.7),
            max_tokens=max_tokens if max_tokens is not None else template_config.get("max_tokens", 512),
        )

        # Generate agent ID
        agent_id = f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}"

        # Create agent
        agent = Agent(agent_id, config)
        agent.save()

        # Store in memory
        self._agents[agent_id] = agent

        logger.info(f"Created agent: {name} ({agent_id})")

        return AgentInfo(
            id=agent.id,
            name=agent.config.name,
            description=agent.config.description,
            model=agent.config.model,
            capabilities=agent.config.capabilities,
            created=agent.created,
            active=True,
            temperature=agent.config.temperature,
            max_tokens=agent.config.max_tokens,
            system_prompt=agent.config.system_prompt,
        )

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID"""
        return self._agents.get(agent_id)

    def list_agents(self) -> List[AgentInfo]:
        """List all agents"""
        return [
            AgentInfo(
                id=agent.id,
                name=agent.config.name,
                description=agent.config.description,
                model=agent.config.model,
                capabilities=agent.config.capabilities,
                created=agent.created,
                active=True,
            )
            for agent in self._agents.values()
        ]

    async def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        agent.delete()
        del self._agents[agent_id]
        logger.info(f"Deleted agent: {agent_id}")
        return True


# Global agent manager instance
agent_manager = AgentManager()
