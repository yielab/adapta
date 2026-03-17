"""
Base classes for the tool/function calling system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ParameterType(str, Enum):
    """Parameter types for tool parameters"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    """
    Tool parameter definition.

    Follows OpenAI function calling schema.
    """
    name: str
    type: ParameterType
    description: str
    required: bool = False
    enum: Optional[List[str]] = None
    items: Optional[Dict[str, Any]] = None  # For array types
    properties: Optional[Dict[str, Any]] = None  # For object types

    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI function parameter format"""
        param_dict = {
            "type": self.type.value,
            "description": self.description,
        }

        if self.enum:
            param_dict["enum"] = self.enum
        if self.items:
            param_dict["items"] = self.items
        if self.properties:
            param_dict["properties"] = self.properties

        return param_dict


@dataclass
class ToolResult:
    """Result from tool execution"""
    success: bool
    result: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class Tool(ABC):
    """
    Base class for all tools.

    Tools are functions that can be called by agents to perform
    actions or retrieve information.
    """

    def __init__(self):
        """Initialize tool"""
        self._name = self.__class__.__name__.lower().replace("tool", "")

    @property
    def name(self) -> str:
        """Tool name"""
        return self._name

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for LLM"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> List[ToolParameter]:
        """Tool parameters"""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            **kwargs: Tool parameters

        Returns:
            ToolResult with execution result
        """
        pass

    def to_openai_function(self) -> Dict[str, Any]:
        """
        Convert tool to OpenAI function calling format.

        Returns:
            OpenAI function definition
        """
        required_params = [p.name for p in self.parameters if p.required]
        properties = {
            p.name: p.to_dict() for p in self.parameters
        }

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_params,
            }
        }

    def validate_parameters(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate parameters before execution.

        Args:
            params: Parameters to validate

        Returns:
            (is_valid, error_message)
        """
        # Check required parameters
        for param in self.parameters:
            if param.required and param.name not in params:
                return False, f"Missing required parameter: {param.name}"

        # Check parameter types (basic validation)
        for param_name, param_value in params.items():
            param_def = next((p for p in self.parameters if p.name == param_name), None)
            if not param_def:
                return False, f"Unknown parameter: {param_name}"

            # Type checking
            if param_def.type == ParameterType.STRING and not isinstance(param_value, str):
                return False, f"Parameter {param_name} must be a string"
            elif param_def.type == ParameterType.INTEGER and not isinstance(param_value, int):
                return False, f"Parameter {param_name} must be an integer"
            elif param_def.type == ParameterType.NUMBER and not isinstance(param_value, (int, float)):
                return False, f"Parameter {param_name} must be a number"
            elif param_def.type == ParameterType.BOOLEAN and not isinstance(param_value, bool):
                return False, f"Parameter {param_name} must be a boolean"
            elif param_def.type == ParameterType.ARRAY and not isinstance(param_value, list):
                return False, f"Parameter {param_name} must be an array"
            elif param_def.type == ParameterType.OBJECT and not isinstance(param_value, dict):
                return False, f"Parameter {param_name} must be an object"

        return True, None
