"""
Tool registry for managing available tools.
"""

import logging
from typing import Dict, List, Optional

from brain.tools.base import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing available tools.

    Provides:
    - Tool registration and lookup
    - Tool listing and discovery
    - Tool validation
    """

    def __init__(self):
        """Initialize tool registry"""
        self._tools: Dict[str, Tool] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """Register built-in tools"""
        from brain.tools.builtin import (
            CalculatorTool,
            WebSearchTool,
            ReadFileTool,
            WriteFileTool,
            GetTimeTool,
            GetWeatherTool,
        )

        # Register all built-in tools
        builtin_tools = [
            CalculatorTool(),
            WebSearchTool(),
            ReadFileTool(),
            WriteFileTool(),
            GetTimeTool(),
            GetWeatherTool(),
        ]

        for tool in builtin_tools:
            self.register_tool(tool)
            logger.info(f"Registered built-in tool: {tool.name}")

    def register_tool(self, tool: Tool):
        """
        Register a tool.

        Args:
            tool: Tool to register
        """
        if tool.name in self._tools:
            logger.warning(f"Tool {tool.name} already registered, overwriting")

        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def unregister_tool(self, name: str):
        """
        Unregister a tool.

        Args:
            name: Tool name to unregister
        """
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
        else:
            logger.warning(f"Tool {name} not found in registry")

    def get_tool(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_all_tools(self) -> List[Tool]:
        """
        Get all registered tools.

        Returns:
            List of Tool instances
        """
        return list(self._tools.values())

    def to_openai_functions(self) -> List[Dict]:
        """
        Get all tools in OpenAI function calling format.

        Returns:
            List of OpenAI function definitions
        """
        return [tool.to_openai_function() for tool in self._tools.values()]

    def get_tools_by_category(self, category: str) -> List[Tool]:
        """
        Get tools by category.

        Args:
            category: Tool category (e.g., 'file', 'web', 'math')

        Returns:
            List of tools matching category
        """
        # This is a simple implementation - could be extended with
        # actual category support in Tool base class
        return [
            tool for tool in self._tools.values()
            if category.lower() in tool.name.lower()
        ]

    def clear(self):
        """Clear all registered tools"""
        self._tools.clear()
        logger.info("Cleared all tools from registry")


# Global registry instance
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry"""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry
