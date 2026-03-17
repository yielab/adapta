"""
Agent-to-agent communication system for multi-agent workflows.

Enables agents to collaborate by sending messages, delegating tasks,
and aggregating results.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from brain.agents import agent_manager

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Types of inter-agent messages"""
    TASK = "task"  # Delegate a task
    QUERY = "query"  # Ask for information
    RESPONSE = "response"  # Response to task/query
    NOTIFICATION = "notification"  # One-way notification
    BROADCAST = "broadcast"  # Message to multiple agents


class MessagePriority(str, Enum):
    """Message priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class AgentMessage:
    """Message between agents"""
    id: str
    from_agent: str
    to_agent: str
    message_type: MessageType
    priority: MessagePriority
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    reply_to: Optional[str] = None  # ID of message this is replying to
    requires_response: bool = False
    timeout: Optional[float] = None  # Timeout for response (seconds)


@dataclass
class AgentConversation:
    """A conversation between multiple agents"""
    id: str
    participants: List[str]
    messages: List[AgentMessage] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentCommunicationHub:
    """
    Central hub for agent-to-agent communication.

    Features:
    - Message routing between agents
    - Conversation tracking
    - Async message delivery
    - Response waiting with timeout
    - Message history
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize communication hub.

        Args:
            max_history: Maximum messages to keep in history
        """
        self.max_history = max_history
        self._conversations: Dict[str, AgentConversation] = {}
        self._message_queues: Dict[str, asyncio.Queue] = {}
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._message_handlers: Dict[str, Callable] = {}

    def register_agent(self, agent_id: str):
        """
        Register an agent for communication.

        Args:
            agent_id: Agent ID to register
        """
        if agent_id not in self._message_queues:
            self._message_queues[agent_id] = asyncio.Queue()
            logger.info(f"Registered agent {agent_id} for communication")

    def unregister_agent(self, agent_id: str):
        """
        Unregister an agent from communication.

        Args:
            agent_id: Agent ID to unregister
        """
        if agent_id in self._message_queues:
            del self._message_queues[agent_id]
            logger.info(f"Unregistered agent {agent_id} from communication")

    def register_message_handler(
        self,
        agent_id: str,
        handler: Callable[[AgentMessage], Any]
    ):
        """
        Register a message handler for an agent.

        Args:
            agent_id: Agent ID
            handler: Async function to handle messages
        """
        self._message_handlers[agent_id] = handler
        logger.info(f"Registered message handler for agent {agent_id}")

    async def send_message(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        message_type: MessageType = MessageType.TASK,
        priority: MessagePriority = MessagePriority.NORMAL,
        requires_response: bool = False,
        timeout: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        reply_to: Optional[str] = None,
    ) -> Optional[AgentMessage]:
        """
        Send a message from one agent to another.

        Args:
            from_agent: Source agent ID
            to_agent: Destination agent ID
            content: Message content
            message_type: Type of message
            priority: Message priority
            requires_response: Whether a response is required
            timeout: Timeout for response (seconds)
            metadata: Additional metadata
            reply_to: ID of message this is replying to

        Returns:
            Response message if requires_response=True, None otherwise
        """
        # Create message
        message = AgentMessage(
            id=str(uuid.uuid4()),
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            priority=priority,
            content=content,
            metadata=metadata or {},
            reply_to=reply_to,
            requires_response=requires_response,
            timeout=timeout,
        )

        # Check if destination agent is registered
        if to_agent not in self._message_queues:
            logger.warning(f"Agent {to_agent} not registered for communication")
            # Auto-register if agent exists
            agent = agent_manager.get_agent(to_agent)
            if agent:
                self.register_agent(to_agent)
            else:
                raise ValueError(f"Agent {to_agent} not found")

        # Store message in conversation
        self._store_message(message)

        # If response required, create future
        response_future = None
        if requires_response:
            response_future = asyncio.Future()
            self._pending_responses[message.id] = response_future

        # Deliver message
        await self._message_queues[to_agent].put(message)
        logger.info(
            f"Message {message.id} sent from {from_agent} to {to_agent} "
            f"(type: {message_type}, priority: {priority})"
        )

        # If response required, wait for it
        if requires_response:
            try:
                response = await asyncio.wait_for(
                    response_future,
                    timeout=timeout or 60.0
                )
                return response
            except asyncio.TimeoutError:
                logger.error(
                    f"Timeout waiting for response to message {message.id} "
                    f"from {to_agent}"
                )
                if message.id in self._pending_responses:
                    del self._pending_responses[message.id]
                return None

        return None

    async def broadcast_message(
        self,
        from_agent: str,
        to_agents: List[str],
        content: str,
        priority: MessagePriority = MessagePriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Broadcast a message to multiple agents.

        Args:
            from_agent: Source agent ID
            to_agents: List of destination agent IDs
            content: Message content
            priority: Message priority
            metadata: Additional metadata

        Returns:
            List of message IDs sent
        """
        message_ids = []
        tasks = []

        for to_agent in to_agents:
            task = self.send_message(
                from_agent=from_agent,
                to_agent=to_agent,
                content=content,
                message_type=MessageType.BROADCAST,
                priority=priority,
                metadata=metadata,
                requires_response=False,
            )
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(
            f"Broadcast message from {from_agent} to {len(to_agents)} agents"
        )
        return message_ids

    async def receive_message(
        self,
        agent_id: str,
        timeout: Optional[float] = None
    ) -> Optional[AgentMessage]:
        """
        Receive a message for an agent.

        Args:
            agent_id: Agent ID to receive message for
            timeout: Timeout in seconds

        Returns:
            AgentMessage or None if timeout
        """
        if agent_id not in self._message_queues:
            raise ValueError(f"Agent {agent_id} not registered for communication")

        try:
            if timeout:
                message = await asyncio.wait_for(
                    self._message_queues[agent_id].get(),
                    timeout=timeout
                )
            else:
                message = await self._message_queues[agent_id].get()

            logger.info(f"Agent {agent_id} received message {message.id}")

            # If handler registered, call it
            if agent_id in self._message_handlers:
                try:
                    await self._message_handlers[agent_id](message)
                except Exception as e:
                    logger.error(
                        f"Error in message handler for {agent_id}: {e}",
                        exc_info=True
                    )

            return message

        except asyncio.TimeoutError:
            return None

    async def send_response(
        self,
        original_message: AgentMessage,
        response_content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Send a response to a message.

        Args:
            original_message: The message to respond to
            response_content: Response content
            metadata: Additional metadata
        """
        response = AgentMessage(
            id=str(uuid.uuid4()),
            from_agent=original_message.to_agent,
            to_agent=original_message.from_agent,
            message_type=MessageType.RESPONSE,
            priority=original_message.priority,
            content=response_content,
            metadata=metadata or {},
            reply_to=original_message.id,
            requires_response=False,
        )

        # Store response
        self._store_message(response)

        # If there's a pending future, resolve it
        if original_message.id in self._pending_responses:
            future = self._pending_responses[original_message.id]
            if not future.done():
                future.set_result(response)
            del self._pending_responses[original_message.id]

        logger.info(
            f"Response sent from {response.from_agent} to {response.to_agent} "
            f"(reply to: {original_message.id})"
        )

    def _store_message(self, message: AgentMessage):
        """Store message in conversation history"""
        # Find or create conversation
        conv_id = self._get_conversation_id(message.from_agent, message.to_agent)

        if conv_id not in self._conversations:
            self._conversations[conv_id] = AgentConversation(
                id=conv_id,
                participants=[message.from_agent, message.to_agent],
            )

        conv = self._conversations[conv_id]
        conv.messages.append(message)

        # Limit history
        if len(conv.messages) > self.max_history:
            conv.messages = conv.messages[-self.max_history:]

    def _get_conversation_id(self, agent1: str, agent2: str) -> str:
        """Get conversation ID for two agents (order-independent)"""
        agents = sorted([agent1, agent2])
        return f"{agents[0]}_{agents[1]}"

    def get_conversation(
        self,
        agent1: str,
        agent2: str
    ) -> Optional[AgentConversation]:
        """
        Get conversation between two agents.

        Args:
            agent1: First agent ID
            agent2: Second agent ID

        Returns:
            AgentConversation or None if not found
        """
        conv_id = self._get_conversation_id(agent1, agent2)
        return self._conversations.get(conv_id)

    def get_agent_conversations(self, agent_id: str) -> List[AgentConversation]:
        """
        Get all conversations involving an agent.

        Args:
            agent_id: Agent ID

        Returns:
            List of conversations
        """
        return [
            conv for conv in self._conversations.values()
            if agent_id in conv.participants
        ]

    def get_pending_messages_count(self, agent_id: str) -> int:
        """
        Get number of pending messages for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Number of pending messages
        """
        if agent_id not in self._message_queues:
            return 0
        return self._message_queues[agent_id].qsize()

    def clear_conversation(self, agent1: str, agent2: str):
        """
        Clear conversation history between two agents.

        Args:
            agent1: First agent ID
            agent2: Second agent ID
        """
        conv_id = self._get_conversation_id(agent1, agent2)
        if conv_id in self._conversations:
            del self._conversations[conv_id]
            logger.info(f"Cleared conversation {conv_id}")


# Global communication hub instance
_communication_hub: Optional[AgentCommunicationHub] = None


def get_communication_hub() -> AgentCommunicationHub:
    """Get the global communication hub"""
    global _communication_hub
    if _communication_hub is None:
        _communication_hub = AgentCommunicationHub()
    return _communication_hub
