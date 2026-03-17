"""
Tool/Function calling API routes.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from brain.tools import get_tool_registry, get_tool_executor

logger = logging.getLogger(__name__)

router = APIRouter()


class ToolExecuteRequest(BaseModel):
    """Tool execution request"""

    tool_name: str
    parameters: Dict[str, Any]
    timeout: Optional[float] = None


class ToolExecuteResponse(BaseModel):
    """Tool execution response"""

    success: bool
    result: Any
    error: Optional[str] = None
    metadata: Dict[str, Any]
    duration_ms: float


class ToolInfo(BaseModel):
    """Tool information"""

    name: str
    description: str
    parameters: List[Dict[str, Any]]


class ToolListResponse(BaseModel):
    """List of available tools"""

    object: str = "list"
    data: List[ToolInfo]


class ToolStatsResponse(BaseModel):
    """Tool execution statistics"""

    total_executions: int
    successful: int
    failed: int
    success_rate: float
    avg_duration_ms: float


@router.get("/tools")
async def list_tools() -> ToolListResponse:
    """
    List all available tools.

    Returns:
        List of tool definitions
    """
    registry = get_tool_registry()
    tools = registry.get_all_tools()

    tool_infos = []
    for tool in tools:
        tool_info = ToolInfo(
            name=tool.name,
            description=tool.description,
            parameters=[p.to_dict() for p in tool.parameters],
        )
        tool_infos.append(tool_info)

    return ToolListResponse(data=tool_infos)


@router.get("/tools/openai")
async def list_tools_openai() -> List[Dict[str, Any]]:
    """
    List all tools in OpenAI function calling format.

    Returns:
        List of OpenAI-compatible function definitions
    """
    registry = get_tool_registry()
    return registry.to_openai_functions()


@router.post("/tools/execute")
async def execute_tool(request: ToolExecuteRequest) -> ToolExecuteResponse:
    """
    Execute a tool with given parameters.

    Args:
        request: Tool execution request

    Returns:
        Tool execution result
    """
    import time

    executor = get_tool_executor()
    start_time = time.time()

    result = await executor.execute(
        tool_name=request.tool_name,
        parameters=request.parameters,
        timeout=request.timeout,
    )

    duration_ms = (time.time() - start_time) * 1000

    return ToolExecuteResponse(
        success=result.success,
        result=result.result,
        error=result.error,
        metadata=result.metadata,
        duration_ms=duration_ms,
    )


@router.get("/tools/stats")
async def get_tool_stats(tool_name: Optional[str] = None) -> ToolStatsResponse:
    """
    Get tool execution statistics.

    Args:
        tool_name: Optional tool name filter

    Returns:
        Execution statistics
    """
    executor = get_tool_executor()
    stats = executor.get_statistics(tool_name=tool_name)

    return ToolStatsResponse(**stats)


@router.post("/tools/stats/clear")
async def clear_tool_stats():
    """Clear tool execution statistics"""
    executor = get_tool_executor()
    executor.clear_history()
    return {"message": "Tool statistics cleared"}


@router.get("/tools/{tool_name}")
async def get_tool_info(tool_name: str) -> ToolInfo:
    """
    Get information about a specific tool.

    Args:
        tool_name: Name of the tool

    Returns:
        Tool information
    """
    registry = get_tool_registry()
    tool = registry.get_tool(tool_name)

    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    return ToolInfo(
        name=tool.name,
        description=tool.description,
        parameters=[p.to_dict() for p in tool.parameters],
    )
