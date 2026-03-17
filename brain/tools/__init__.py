"""
Tool/Function calling system for Brain From Cero.

This module provides:
- Tool registry and management
- Built-in tools (calculator, web search, file operations)
- Tool execution engine
- OpenAI-compatible function calling API
"""

from brain.tools.base import Tool, ToolParameter, ToolResult
from brain.tools.registry import ToolRegistry, get_tool_registry
from brain.tools.executor import ToolExecutor, get_tool_executor

__all__ = [
    "Tool",
    "ToolParameter",
    "ToolResult",
    "ToolRegistry",
    "get_tool_registry",
    "ToolExecutor",
    "get_tool_executor",
]
