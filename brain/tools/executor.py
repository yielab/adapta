"""
Tool executor for running tools with safety and monitoring.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from brain.tools.base import Tool, ToolResult
from brain.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)


@dataclass
class ToolExecution:
    """Record of a tool execution"""
    tool_name: str
    parameters: Dict[str, Any]
    result: ToolResult
    duration_ms: float
    timestamp: float


class ToolExecutor:
    """
    Tool executor with safety, monitoring, and rate limiting.

    Features:
    - Parameter validation
    - Execution timeout
    - Error handling
    - Execution history
    - Rate limiting (optional)
    """

    def __init__(
        self,
        default_timeout: float = 30.0,
        max_history: int = 1000,
    ):
        """
        Initialize tool executor.

        Args:
            default_timeout: Default execution timeout in seconds
            max_history: Maximum execution history to keep
        """
        self.default_timeout = default_timeout
        self.max_history = max_history
        self._history: List[ToolExecution] = []
        self._registry = get_tool_registry()

    async def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """
        Execute a tool with given parameters.

        Args:
            tool_name: Name of tool to execute
            parameters: Tool parameters
            timeout: Execution timeout (uses default if not provided)

        Returns:
            ToolResult with execution result
        """
        start_time = time.time()
        timeout = timeout or self.default_timeout

        # Get tool from registry
        tool = self._registry.get_tool(tool_name)
        if not tool:
            logger.error(f"Tool not found: {tool_name}")
            return ToolResult(
                success=False,
                result=None,
                error=f"Tool not found: {tool_name}"
            )

        # Validate parameters
        is_valid, error = tool.validate_parameters(parameters)
        if not is_valid:
            logger.error(f"Parameter validation failed for {tool_name}: {error}")
            return ToolResult(
                success=False,
                result=None,
                error=f"Parameter validation failed: {error}"
            )

        # Execute with timeout
        try:
            logger.info(f"Executing tool: {tool_name} with params: {parameters}")
            result = await asyncio.wait_for(
                tool.execute(**parameters),
                timeout=timeout
            )

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"Tool {tool_name} completed in {duration_ms:.2f}ms")

            # Record execution
            execution = ToolExecution(
                tool_name=tool_name,
                parameters=parameters,
                result=result,
                duration_ms=duration_ms,
                timestamp=start_time,
            )
            self._add_to_history(execution)

            return result

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Tool {tool_name} timed out after {timeout}s")

            result = ToolResult(
                success=False,
                result=None,
                error=f"Tool execution timed out after {timeout}s"
            )

            execution = ToolExecution(
                tool_name=tool_name,
                parameters=parameters,
                result=result,
                duration_ms=duration_ms,
                timestamp=start_time,
            )
            self._add_to_history(execution)

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Tool {tool_name} failed with error: {e}", exc_info=True)

            result = ToolResult(
                success=False,
                result=None,
                error=f"Tool execution failed: {str(e)}"
            )

            execution = ToolExecution(
                tool_name=tool_name,
                parameters=parameters,
                result=result,
                duration_ms=duration_ms,
                timestamp=start_time,
            )
            self._add_to_history(execution)

            return result

    async def execute_multiple(
        self,
        tool_calls: List[Dict[str, Any]],
        concurrent: bool = False,
    ) -> List[ToolResult]:
        """
        Execute multiple tool calls.

        Args:
            tool_calls: List of tool calls with format:
                        [{"name": "tool_name", "parameters": {...}}, ...]
            concurrent: Whether to execute concurrently

        Returns:
            List of ToolResults
        """
        if concurrent:
            # Execute all tools concurrently
            tasks = [
                self.execute(call["name"], call["parameters"])
                for call in tool_calls
            ]
            return await asyncio.gather(*tasks, return_exceptions=False)
        else:
            # Execute sequentially
            results = []
            for call in tool_calls:
                result = await self.execute(call["name"], call["parameters"])
                results.append(result)
            return results

    def _add_to_history(self, execution: ToolExecution):
        """Add execution to history"""
        self._history.append(execution)
        # Keep only last N executions
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

    def get_history(
        self,
        tool_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[ToolExecution]:
        """
        Get execution history.

        Args:
            tool_name: Filter by tool name (optional)
            limit: Maximum number of records to return

        Returns:
            List of ToolExecution records
        """
        history = self._history
        if tool_name:
            history = [e for e in history if e.tool_name == tool_name]

        return history[-limit:]

    def get_statistics(self, tool_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get execution statistics.

        Args:
            tool_name: Filter by tool name (optional)

        Returns:
            Statistics dictionary
        """
        history = self._history
        if tool_name:
            history = [e for e in history if e.tool_name == tool_name]

        if not history:
            return {
                "total_executions": 0,
                "successful": 0,
                "failed": 0,
                "avg_duration_ms": 0.0,
            }

        successful = sum(1 for e in history if e.result.success)
        failed = len(history) - successful
        avg_duration = sum(e.duration_ms for e in history) / len(history)

        return {
            "total_executions": len(history),
            "successful": successful,
            "failed": failed,
            "success_rate": successful / len(history),
            "avg_duration_ms": avg_duration,
        }

    def clear_history(self):
        """Clear execution history"""
        self._history.clear()
        logger.info("Cleared tool execution history")


# Global executor instance
_tool_executor: Optional[ToolExecutor] = None


def get_tool_executor() -> ToolExecutor:
    """Get the global tool executor"""
    global _tool_executor
    if _tool_executor is None:
        _tool_executor = ToolExecutor()
    return _tool_executor
