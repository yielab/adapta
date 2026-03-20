"""
Context Manager for handling token limits and conversation context optimization.

This module provides functionality to:
- Count tokens accurately using tiktoken
- Manage sliding context windows
- Summarize old messages to preserve context
- Prioritize message retention (system > recent > RAG)
- Allocate token budgets per component
"""

import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime

try:
    import tiktoken
except ImportError:
    tiktoken = None
    logging.warning("tiktoken not installed. Token counting will use approximation.")

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    """Priority levels for message retention."""
    SYSTEM = 100  # System messages have highest priority
    USER_RECENT = 80  # Recent user messages
    ASSISTANT_RECENT = 75  # Recent assistant responses
    RAG_CONTEXT = 60  # Retrieved context from RAG
    USER_OLD = 40  # Older user messages
    ASSISTANT_OLD = 35  # Older assistant messages
    SUMMARIZED = 20  # Already summarized content


@dataclass
class Message:
    """Enhanced message with metadata for context management."""
    role: str  # 'system', 'user', 'assistant', 'function'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tokens: int = 0
    priority: MessagePriority = MessagePriority.USER_RECENT
    metadata: Dict[str, Any] = field(default_factory=dict)
    summarized: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI API format."""
        base_msg = {"role": self.role, "content": self.content}

        # Add function call information if present
        if "function_call" in self.metadata:
            base_msg["function_call"] = self.metadata["function_call"]
        if "tool_calls" in self.metadata:
            base_msg["tool_calls"] = self.metadata["tool_calls"]
        if "name" in self.metadata:
            base_msg["name"] = self.metadata["name"]

        return base_msg


@dataclass
class ContextBudget:
    """Token budget allocation for different components."""
    total_tokens: int = 4096  # Default context window
    system_tokens: int = 500  # Reserved for system prompt
    rag_tokens: int = 1000  # Reserved for RAG context
    history_tokens: int = 2000  # For conversation history
    output_tokens: int = 596  # Reserved for response generation

    @property
    def available_tokens(self) -> int:
        """Calculate available tokens for conversation."""
        return self.total_tokens - self.output_tokens

    def adjust_for_model(self, model_name: str) -> None:
        """Adjust budget based on model's context window."""
        model_windows = {
            # Common model context windows
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-3.5-turbo": 4096,
            "gpt-3.5-turbo-16k": 16384,
            "claude-2": 100000,
            "claude-instant": 100000,
            # Local models
            "llama-2-7b": 4096,
            "llama-2-13b": 4096,
            "llama-2-70b": 4096,
            "mistral-7b": 8192,
            "mixtral-8x7b": 32768,
            "qwen2.5-7b": 32768,
            "qwen2.5-3b": 32768,
            "qwen2.5-coder-7b": 32768,
            "qwen2.5-coder-3b": 32768,
        }

        # Check for partial matches
        for model_key, window_size in model_windows.items():
            if model_key in model_name.lower():
                self.total_tokens = window_size
                # Adjust allocations proportionally
                self.system_tokens = min(500, window_size // 8)
                self.rag_tokens = min(2000, window_size // 4)
                self.history_tokens = window_size - self.system_tokens - self.rag_tokens - self.output_tokens
                break


class ContextManager:
    """Manages conversation context within token limits."""

    def __init__(
        self,
        model_name: str = "gpt-3.5-turbo",
        max_tokens: Optional[int] = None,
        encoding_name: Optional[str] = None
    ):
        """
        Initialize the context manager.

        Args:
            model_name: Name of the model for token counting
            max_tokens: Override for maximum context tokens
            encoding_name: Specific tokenizer encoding to use
        """
        self.model_name = model_name
        self.encoding = None
        self.encoding_name = encoding_name or self._get_encoding_name(model_name)

        # Initialize tokenizer
        if tiktoken:
            try:
                self.encoding = tiktoken.get_encoding(self.encoding_name)
            except Exception as e:
                logger.warning(f"Could not load tiktoken encoding: {e}")
                self.encoding = None

        # Initialize budget
        self.budget = ContextBudget()
        self.budget.adjust_for_model(model_name)

        if max_tokens:
            self.budget.total_tokens = max_tokens

        # Message storage
        self.messages: List[Message] = []
        self.summarization_cache: Dict[str, str] = {}

    def _get_encoding_name(self, model_name: str) -> str:
        """Get the appropriate encoding for a model."""
        # OpenAI models
        if "gpt-4" in model_name:
            return "cl100k_base"
        elif "gpt-3.5" in model_name:
            return "cl100k_base"
        # Default for other models
        return "cl100k_base"

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception as e:
                logger.warning(f"Token counting failed: {e}")

        # Fallback: approximate 4 chars per token
        return len(text) // 4

    def count_message_tokens(self, message: Union[Dict, Message]) -> int:
        """
        Count tokens in a message, including overhead.

        Args:
            message: Message dict or Message object

        Returns:
            Total tokens including formatting overhead
        """
        if isinstance(message, Message):
            message_dict = message.to_dict()
        else:
            message_dict = message

        # Token overhead per message (role, separators, etc.)
        tokens = 3  # Base overhead

        # Count content tokens
        tokens += self.count_tokens(message_dict.get("content", ""))

        # Count role tokens
        tokens += self.count_tokens(message_dict.get("role", ""))

        # Handle function/tool calls
        if "function_call" in message_dict:
            fc = message_dict["function_call"]
            tokens += self.count_tokens(fc.get("name", ""))
            tokens += self.count_tokens(fc.get("arguments", ""))

        if "tool_calls" in message_dict:
            for tool in message_dict.get("tool_calls", []):
                tokens += self.count_tokens(tool.get("function", {}).get("name", ""))
                tokens += self.count_tokens(tool.get("function", {}).get("arguments", ""))

        return tokens

    def add_message(
        self,
        role: str,
        content: str,
        priority: Optional[MessagePriority] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        Add a message to the context.

        Args:
            role: Message role (system, user, assistant)
            content: Message content
            priority: Message priority for retention
            metadata: Additional message metadata

        Returns:
            Created Message object
        """
        # Determine priority based on role if not specified
        if priority is None:
            if role == "system":
                priority = MessagePriority.SYSTEM
            elif role == "user":
                priority = MessagePriority.USER_RECENT
            elif role == "assistant":
                priority = MessagePriority.ASSISTANT_RECENT
            else:
                priority = MessagePriority.USER_OLD

        message = Message(
            role=role,
            content=content,
            priority=priority,
            metadata=metadata or {},
            tokens=self.count_tokens(content)
        )

        self.messages.append(message)

        # Update priorities of older messages
        self._update_message_priorities()

        return message

    def _update_message_priorities(self) -> None:
        """Update priorities of messages based on age."""
        # Keep last N messages as recent
        recent_threshold = 10

        for i, msg in enumerate(self.messages):
            if msg.role == "system":
                continue  # System messages keep their priority

            # Messages beyond threshold become "old"
            if i < len(self.messages) - recent_threshold:
                if msg.role == "user":
                    msg.priority = MessagePriority.USER_OLD
                elif msg.role == "assistant":
                    msg.priority = MessagePriority.ASSISTANT_OLD

    def summarize_messages(
        self,
        messages: List[Message],
        target_tokens: int = 200
    ) -> str:
        """
        Summarize a list of messages to reduce tokens.

        Args:
            messages: Messages to summarize
            target_tokens: Target token count for summary

        Returns:
            Summarized content
        """
        # Create a cache key
        cache_key = json.dumps([m.content[:50] for m in messages])

        if cache_key in self.summarization_cache:
            return self.summarization_cache[cache_key]

        # Simple summarization strategy (in production, use LLM)
        summary_parts = []

        # Group by role
        user_messages = [m.content for m in messages if m.role == "user"]
        assistant_messages = [m.content for m in messages if m.role == "assistant"]

        if user_messages:
            summary_parts.append(f"User discussed: {'; '.join(user_messages[:3])[:200]}...")

        if assistant_messages:
            summary_parts.append(f"Assistant provided: {'; '.join(assistant_messages[:3])[:200]}...")

        summary = " ".join(summary_parts)

        # Trim to target tokens
        while self.count_tokens(summary) > target_tokens and len(summary) > 50:
            summary = summary[:int(len(summary) * 0.9)] + "..."

        self.summarization_cache[cache_key] = summary
        return summary

    def optimize_context(
        self,
        target_tokens: Optional[int] = None,
        preserve_recent: int = 5,
        summarize_old: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Optimize message context to fit within token budget.

        Args:
            target_tokens: Target token count (uses budget if not specified)
            preserve_recent: Number of recent messages to always preserve
            summarize_old: Whether to summarize old messages

        Returns:
            Optimized list of messages in API format
        """
        if not target_tokens:
            target_tokens = self.budget.available_tokens

        # Always include system messages
        system_messages = [m for m in self.messages if m.role == "system"]
        other_messages = [m for m in self.messages if m.role != "system"]

        # Calculate current token usage
        current_tokens = sum(m.tokens for m in system_messages)

        # Sort other messages by priority and recency
        sorted_messages = sorted(
            other_messages,
            key=lambda m: (m.priority.value, m.timestamp.timestamp()),
            reverse=True
        )

        # Build optimized message list
        optimized: List[Message] = system_messages.copy()
        messages_to_summarize: List[Message] = []

        for msg in sorted_messages:
            # Check if we have room for this message
            if current_tokens + msg.tokens <= target_tokens:
                optimized.append(msg)
                current_tokens += msg.tokens
            elif summarize_old and not msg.summarized:
                messages_to_summarize.append(msg)

        # Summarize old messages if needed
        if messages_to_summarize and summarize_old:
            summary_tokens = min(200, target_tokens - current_tokens)
            if summary_tokens > 50:
                summary = self.summarize_messages(messages_to_summarize, summary_tokens)
                summary_msg = Message(
                    role="system",
                    content=f"[Previous conversation summary: {summary}]",
                    priority=MessagePriority.SUMMARIZED,
                    tokens=self.count_tokens(summary),
                    summarized=True
                )
                optimized.insert(1, summary_msg)  # After main system message

        # Sort by timestamp to maintain conversation order
        optimized.sort(key=lambda m: m.timestamp)

        # Convert to API format
        return [msg.to_dict() for msg in optimized]

    def get_token_usage(self) -> Dict[str, int]:
        """
        Get current token usage statistics.

        Returns:
            Dictionary with token usage information
        """
        system_tokens = sum(m.tokens for m in self.messages if m.role == "system")
        user_tokens = sum(m.tokens for m in self.messages if m.role == "user")
        assistant_tokens = sum(m.tokens for m in self.messages if m.role == "assistant")
        total_tokens = sum(m.tokens for m in self.messages)

        return {
            "total_tokens": total_tokens,
            "system_tokens": system_tokens,
            "user_tokens": user_tokens,
            "assistant_tokens": assistant_tokens,
            "available_tokens": self.budget.total_tokens - total_tokens,
            "budget": {
                "total": self.budget.total_tokens,
                "system": self.budget.system_tokens,
                "rag": self.budget.rag_tokens,
                "history": self.budget.history_tokens,
                "output": self.budget.output_tokens
            },
            "message_count": len(self.messages),
            "summarized_count": sum(1 for m in self.messages if m.summarized)
        }

    def clear_old_messages(self, keep_recent: int = 10) -> int:
        """
        Clear old messages while preserving recent ones.

        Args:
            keep_recent: Number of recent messages to keep

        Returns:
            Number of messages removed
        """
        # Keep system messages and recent messages
        system_messages = [m for m in self.messages if m.role == "system"]
        other_messages = [m for m in self.messages if m.role != "system"]

        # Sort by timestamp and keep recent
        other_messages.sort(key=lambda m: m.timestamp, reverse=True)
        keep_messages = other_messages[:keep_recent]

        removed_count = len(self.messages) - len(system_messages) - len(keep_messages)

        self.messages = system_messages + keep_messages
        self.messages.sort(key=lambda m: m.timestamp)

        # Clear summarization cache for removed messages
        self.summarization_cache.clear()

        return removed_count

    def export_context(self) -> Dict[str, Any]:
        """
        Export the current context state.

        Returns:
            Dictionary with full context state
        """
        return {
            "model_name": self.model_name,
            "encoding_name": self.encoding_name,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                    "tokens": m.tokens,
                    "priority": m.priority.name,
                    "metadata": m.metadata,
                    "summarized": m.summarized
                }
                for m in self.messages
            ],
            "token_usage": self.get_token_usage(),
            "budget": {
                "total_tokens": self.budget.total_tokens,
                "system_tokens": self.budget.system_tokens,
                "rag_tokens": self.budget.rag_tokens,
                "history_tokens": self.budget.history_tokens,
                "output_tokens": self.budget.output_tokens
            }
        }

    def import_context(self, context_data: Dict[str, Any]) -> None:
        """
        Import a previously exported context state.

        Args:
            context_data: Exported context data
        """
        self.model_name = context_data.get("model_name", self.model_name)
        self.encoding_name = context_data.get("encoding_name", self.encoding_name)

        # Restore messages
        self.messages = []
        for msg_data in context_data.get("messages", []):
            message = Message(
                role=msg_data["role"],
                content=msg_data["content"],
                timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                tokens=msg_data["tokens"],
                priority=MessagePriority[msg_data["priority"]],
                metadata=msg_data.get("metadata", {}),
                summarized=msg_data.get("summarized", False)
            )
            self.messages.append(message)

        # Restore budget if provided
        if "budget" in context_data:
            budget = context_data["budget"]
            self.budget.total_tokens = budget.get("total_tokens", self.budget.total_tokens)
            self.budget.system_tokens = budget.get("system_tokens", self.budget.system_tokens)
            self.budget.rag_tokens = budget.get("rag_tokens", self.budget.rag_tokens)
            self.budget.history_tokens = budget.get("history_tokens", self.budget.history_tokens)
            self.budget.output_tokens = budget.get("output_tokens", self.budget.output_tokens)