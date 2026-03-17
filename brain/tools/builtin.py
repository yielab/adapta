"""
Built-in tools for common operations.
"""

import os
import json
import math
from datetime import datetime
from typing import Any, Dict, List
import logging
import aiohttp

from brain.tools.base import Tool, ToolParameter, ToolResult, ParameterType

logger = logging.getLogger(__name__)


class CalculatorTool(Tool):
    """Tool for performing mathematical calculations"""

    @property
    def description(self) -> str:
        return "Evaluate mathematical expressions. Supports basic arithmetic, trigonometry, and common functions."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="expression",
                type=ParameterType.STRING,
                description="Mathematical expression to evaluate (e.g., '2 + 2', 'sin(pi/2)', 'sqrt(16)')",
                required=True,
            )
        ]

    async def execute(self, expression: str) -> ToolResult:
        """Execute calculator tool"""
        try:
            # Safe eval with math functions
            safe_dict = {
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "sum": sum,
                "pow": pow,
                "sqrt": math.sqrt,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "pi": math.pi,
                "e": math.e,
                "log": math.log,
                "log10": math.log10,
                "exp": math.exp,
                "floor": math.floor,
                "ceil": math.ceil,
            }

            # Evaluate expression
            result = eval(expression, {"__builtins__": {}}, safe_dict)

            return ToolResult(
                success=True,
                result=result,
                metadata={"expression": expression}
            )

        except Exception as e:
            logger.error(f"Calculator error: {e}")
            return ToolResult(
                success=False,
                result=None,
                error=f"Failed to evaluate expression: {str(e)}"
            )


class WebSearchTool(Tool):
    """Tool for searching the web"""

    @property
    def description(self) -> str:
        return "Search the web for information using DuckDuckGo search API."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ParameterType.STRING,
                description="Search query",
                required=True,
            ),
            ToolParameter(
                name="max_results",
                type=ParameterType.INTEGER,
                description="Maximum number of results to return (1-10)",
                required=False,
            ),
        ]

    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        """Execute web search"""
        try:
            max_results = min(max(1, max_results), 10)  # Clamp to 1-10

            # Use DuckDuckGo Instant Answer API (free, no API key)
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 202:
                        # DuckDuckGo returned "processing" status, return basic result
                        return ToolResult(
                            success=True,
                            result=[{
                                "title": "Search Results",
                                "snippet": f"Search for '{query}' returned limited results. Try a more specific query.",
                                "url": f"https://duckduckgo.com/?q={query}",
                            }],
                            metadata={"query": query, "status": 202}
                        )

                    if response.status != 200:
                        return ToolResult(
                            success=False,
                            result=None,
                            error=f"Search failed with status {response.status}"
                        )

                    data = await response.json()

                    # Extract results
                    results = []

                    # Abstract/instant answer
                    if data.get("Abstract"):
                        results.append({
                            "title": data.get("Heading", "Answer"),
                            "snippet": data["Abstract"],
                            "url": data.get("AbstractURL", ""),
                        })

                    # Related topics
                    for topic in data.get("RelatedTopics", [])[:max_results]:
                        if isinstance(topic, dict) and "Text" in topic:
                            results.append({
                                "title": topic.get("Text", "")[:100],
                                "snippet": topic.get("Text", ""),
                                "url": topic.get("FirstURL", ""),
                            })

                    if not results:
                        results.append({
                            "title": "No results found",
                            "snippet": f"No instant answer found for: {query}",
                            "url": "",
                        })

                    return ToolResult(
                        success=True,
                        result=results[:max_results],
                        metadata={"query": query, "count": len(results)}
                    )

        except Exception as e:
            logger.error(f"Web search error: {e}")
            return ToolResult(
                success=False,
                result=None,
                error=f"Search failed: {str(e)}"
            )


class ReadFileTool(Tool):
    """Tool for reading files from the filesystem"""

    @property
    def description(self) -> str:
        return "Read contents of a file from the filesystem."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=ParameterType.STRING,
                description="Path to the file to read (relative or absolute)",
                required=True,
            ),
            ToolParameter(
                name="max_bytes",
                type=ParameterType.INTEGER,
                description="Maximum number of bytes to read (default: 100000)",
                required=False,
            ),
        ]

    async def execute(self, file_path: str, max_bytes: int = 100000) -> ToolResult:
        """Execute file read"""
        try:
            # Security: only allow reading from current directory and subdirectories
            abs_path = os.path.abspath(file_path)
            cwd = os.getcwd()

            if not abs_path.startswith(cwd):
                return ToolResult(
                    success=False,
                    result=None,
                    error="Access denied: can only read files in current directory"
                )

            # Check if file exists
            if not os.path.exists(abs_path):
                return ToolResult(
                    success=False,
                    result=None,
                    error=f"File not found: {file_path}"
                )

            # Read file
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read(max_bytes)

            # Check if file was truncated
            file_size = os.path.getsize(abs_path)
            truncated = file_size > max_bytes

            return ToolResult(
                success=True,
                result=content,
                metadata={
                    "file_path": file_path,
                    "size_bytes": file_size,
                    "truncated": truncated,
                }
            )

        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                result=None,
                error="File is not a text file or uses unsupported encoding"
            )
        except Exception as e:
            logger.error(f"File read error: {e}")
            return ToolResult(
                success=False,
                result=None,
                error=f"Failed to read file: {str(e)}"
            )


class WriteFileTool(Tool):
    """Tool for writing files to the filesystem"""

    @property
    def description(self) -> str:
        return "Write content to a file on the filesystem."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=ParameterType.STRING,
                description="Path to the file to write (relative or absolute)",
                required=True,
            ),
            ToolParameter(
                name="content",
                type=ParameterType.STRING,
                description="Content to write to the file",
                required=True,
            ),
            ToolParameter(
                name="append",
                type=ParameterType.BOOLEAN,
                description="Whether to append to existing file (default: false)",
                required=False,
            ),
        ]

    async def execute(self, file_path: str, content: str, append: bool = False) -> ToolResult:
        """Execute file write"""
        try:
            # Security: only allow writing to current directory and subdirectories
            abs_path = os.path.abspath(file_path)
            cwd = os.getcwd()

            if not abs_path.startswith(cwd):
                return ToolResult(
                    success=False,
                    result=None,
                    error="Access denied: can only write files in current directory"
                )

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            # Write file
            mode = 'a' if append else 'w'
            with open(abs_path, mode, encoding='utf-8') as f:
                f.write(content)

            file_size = os.path.getsize(abs_path)

            return ToolResult(
                success=True,
                result=f"Successfully wrote {len(content)} bytes to {file_path}",
                metadata={
                    "file_path": file_path,
                    "size_bytes": file_size,
                    "appended": append,
                }
            )

        except Exception as e:
            logger.error(f"File write error: {e}")
            return ToolResult(
                success=False,
                result=None,
                error=f"Failed to write file: {str(e)}"
            )


class GetTimeTool(Tool):
    """Tool for getting current time and date"""

    @property
    def description(self) -> str:
        return "Get the current date and time in various formats."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="format",
                type=ParameterType.STRING,
                description="Time format: 'iso' (ISO 8601), 'unix' (timestamp), or 'human' (human-readable)",
                required=False,
                enum=["iso", "unix", "human"],
            )
        ]

    async def execute(self, format: str = "iso") -> ToolResult:
        """Execute get time tool"""
        try:
            now = datetime.now()

            if format == "unix":
                result = now.timestamp()
            elif format == "human":
                result = now.strftime("%A, %B %d, %Y at %I:%M:%S %p")
            else:  # iso
                result = now.isoformat()

            return ToolResult(
                success=True,
                result=result,
                metadata={
                    "format": format,
                    "timestamp": now.timestamp(),
                }
            )

        except Exception as e:
            logger.error(f"Get time error: {e}")
            return ToolResult(
                success=False,
                result=None,
                error=f"Failed to get time: {str(e)}"
            )


class GetWeatherTool(Tool):
    """Tool for getting weather information"""

    @property
    def description(self) -> str:
        return "Get current weather information for a location using wttr.in API."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="location",
                type=ParameterType.STRING,
                description="Location (city name, coordinates, or IP address)",
                required=True,
            )
        ]

    async def execute(self, location: str) -> ToolResult:
        """Execute weather tool"""
        try:
            # Use wttr.in API (free, no API key)
            url = f"https://wttr.in/{location}"
            params = {"format": "j1"}  # JSON format

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status != 200:
                        return ToolResult(
                            success=False,
                            result=None,
                            error=f"Weather API failed with status {response.status}"
                        )

                    data = await response.json()

                    # Extract current conditions
                    current = data["current_condition"][0]
                    location_info = data["nearest_area"][0]

                    weather_info = {
                        "location": f"{location_info['areaName'][0]['value']}, {location_info['country'][0]['value']}",
                        "temperature_c": current["temp_C"],
                        "temperature_f": current["temp_F"],
                        "feels_like_c": current["FeelsLikeC"],
                        "feels_like_f": current["FeelsLikeF"],
                        "condition": current["weatherDesc"][0]["value"],
                        "humidity": current["humidity"],
                        "wind_speed_kmh": current["windspeedKmph"],
                        "wind_direction": current["winddir16Point"],
                        "precipitation_mm": current["precipMM"],
                    }

                    return ToolResult(
                        success=True,
                        result=weather_info,
                        metadata={"location": location}
                    )

        except Exception as e:
            logger.error(f"Weather error: {e}")
            return ToolResult(
                success=False,
                result=None,
                error=f"Failed to get weather: {str(e)}"
            )
