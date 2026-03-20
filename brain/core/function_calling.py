"""
Function calling integration for chat completions.

Handles automatic function/tool calling for LLMs.
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple

from brain.tools import get_tool_executor, get_tool_registry
from brain.tools.base import ToolResult
from brain.core.structured_output import (
    StructuredOutputHandler,
    ToolCallValidator,
    OutputFormatter,
    ExtractionStrategy
)

logger = logging.getLogger(__name__)


class FunctionCallingHandler:
    """
    Handles function calling for chat completions.

    Supports both legacy function calling and new tool calling APIs.
    """

    def __init__(self):
        """Initialize function calling handler"""
        self.executor = get_tool_executor()
        self.registry = get_tool_registry()
        self.structured_handler = StructuredOutputHandler(max_retries=3, strict_mode=False)
        self.tool_validator = ToolCallValidator()
        self.formatter = OutputFormatter()

    def should_use_tools(
        self,
        tools: Optional[List[Dict[str, Any]]] = None,
        functions: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str | Dict] = None,
        function_call: Optional[str | Dict] = None,
    ) -> bool:
        """
        Determine if tools should be used.

        Args:
            tools: Tool definitions
            functions: Function definitions (legacy)
            tool_choice: Tool choice setting
            function_call: Function call setting (legacy)

        Returns:
            True if tools should be used
        """
        # Check if any tools/functions are defined
        has_tools = (tools and len(tools) > 0) or (functions and len(functions) > 0)
        if not has_tools:
            return False

        # Check if tool calling is disabled
        if tool_choice == "none" or function_call == "none":
            return False

        return True

    def get_available_tools(
        self,
        tools: Optional[List[Dict[str, Any]]] = None,
        functions: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get available tools in OpenAI format.

        Args:
            tools: Tool definitions
            functions: Function definitions (legacy)

        Returns:
            List of tool definitions
        """
        available_tools = []

        # Add tools from request
        if tools:
            available_tools.extend(tools)

        # Add functions from request (convert to tool format)
        if functions:
            for func in functions:
                tool = {
                    "type": "function",
                    "function": func
                }
                available_tools.append(tool)

        return available_tools

    def create_tool_prompt(
        self,
        tools: List[Dict[str, Any]],
        tool_choice: Optional[str | Dict] = None,
    ) -> str:
        """
        Create a prompt that instructs the LLM about available tools.

        Args:
            tools: Available tools
            tool_choice: Tool choice setting

        Returns:
            Tool calling instruction prompt
        """
        if not tools:
            return ""

        # Extract function definitions
        functions = []
        for tool in tools:
            if tool.get("type") == "function":
                functions.append(tool["function"])

        if not functions:
            return ""

        # Create tool instruction
        tool_list = []
        for func in functions:
            params_str = json.dumps(func.get("parameters", {}), indent=2)
            tool_list.append(f"- {func['name']}: {func['description']}\n  Parameters: {params_str}")

        tools_str = "\n".join(tool_list)

        prompt = f"""
You have access to the following tools/functions:

{tools_str}

To use a tool, respond with a JSON object in this format:
{{
  "tool_calls": [
    {{
      "name": "tool_name",
      "arguments": {{
        "param1": "value1",
        "param2": "value2"
      }}
    }}
  ]
}}

You can call multiple tools at once by including multiple objects in the tool_calls array.

If you don't need to use any tools, respond normally with text."""

        # Add tool choice instruction
        if tool_choice == "required":
            prompt += "\n\nIMPORTANT: You MUST use at least one tool to answer this question."
        elif isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
            required_tool = tool_choice.get("function", {}).get("name")
            prompt += f"\n\nIMPORTANT: You MUST use the {required_tool} tool to answer this question."

        return prompt

    def extract_tool_calls(self, response_text: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Extract tool calls from LLM response using enhanced strategies.

        Args:
            response_text: LLM response text

        Returns:
            (tool_calls, remaining_text) tuple
        """
        # Use structured handler for robust extraction
        extraction_result = self.structured_handler.extract_json(
            response_text,
            validate=False  # We'll validate tool calls separately
        )

        if extraction_result.success and extraction_result.data:
            data = extraction_result.data
            tool_calls = None

            # Check for various tool call formats
            if "tool_calls" in data:
                tool_calls = data["tool_calls"]
            elif "function_calls" in data:
                tool_calls = data["function_calls"]
            elif "tools" in data:
                tool_calls = data["tools"]
            elif "functions" in data:
                tool_calls = data["functions"]
            elif "name" in data and ("arguments" in data or "parameters" in data):
                # Single tool call
                tool_calls = [data]

            if tool_calls and isinstance(tool_calls, list):
                formatted_calls = []

                for i, call in enumerate(tool_calls):
                    # Validate and fix the tool call
                    is_valid, fixed_call, error = self.tool_validator.validate_tool_call(call)

                    if is_valid and fixed_call:
                        # Format for OpenAI compatibility
                        formatted_call = {
                            "id": call.get("id", f"call_{i}"),
                            "type": "function",
                            "function": {
                                "name": fixed_call["function"],
                                "arguments": json.dumps(fixed_call["arguments"]) if isinstance(fixed_call["arguments"], dict) else fixed_call["arguments"]
                            }
                        }
                        formatted_calls.append(formatted_call)
                    else:
                        logger.warning(f"Invalid tool call skipped: {error}")

                if formatted_calls:
                    # Remove JSON from response text to get remaining content
                    remaining_text = response_text
                    if extraction_result.raw_output:
                        # Try to remove the JSON part
                        for strategy in [ExtractionStrategy.JSON_BLOCK, ExtractionStrategy.JSON_DETECT]:
                            if extraction_result.strategy_used == strategy:
                                # Remove the extracted JSON from the text
                                json_str = json.dumps(extraction_result.data)
                                if json_str in response_text:
                                    remaining_text = response_text.replace(json_str, "").strip()
                                break

                    return formatted_calls, remaining_text

        # Fallback to original regex method if structured extraction fails
        return self._extract_tool_calls_fallback(response_text)

    def _extract_tool_calls_fallback(self, response_text: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Fallback extraction using simple regex patterns.

        Args:
            response_text: LLM response text

        Returns:
            (tool_calls, remaining_text) tuple
        """
        # Try to find JSON in the response
        json_pattern = r'\{[^{}]*"(?:tool_calls?|function_calls?|tools?|functions?)"[^{}]*\[[^\]]*\][^{}]*\}'

        match = re.search(json_pattern, response_text, re.DOTALL | re.IGNORECASE)
        if not match:
            # Try single tool call pattern
            single_pattern = r'\{[^{}]*"(?:name|function)"[^{}]*"(?:arguments?|parameters?)"[^{}]*\}'
            match = re.search(single_pattern, response_text, re.DOTALL | re.IGNORECASE)
            if not match:
                return None, response_text

        try:
            # Parse JSON (with error correction)
            json_str = match.group(0)
            json_str_fixed = self.tool_validator._fix_json_errors(json_str)
            data = json.loads(json_str_fixed)

            # Extract tool calls
            if "tool_calls" in data:
                tool_calls = data["tool_calls"]
            elif "function_calls" in data:
                tool_calls = data["function_calls"]
            elif "tools" in data:
                tool_calls = data["tools"]
            elif "functions" in data:
                tool_calls = data["functions"]
            elif "name" in data:
                tool_calls = [data]
            else:
                return None, response_text

            if not isinstance(tool_calls, list):
                tool_calls = [tool_calls]

            # Remove JSON from response text
            remaining_text = response_text.replace(match.group(0), "").strip()

            # Convert to OpenAI format
            formatted_calls = []
            for i, call in enumerate(tool_calls):
                is_valid, fixed_call, error = self.tool_validator.validate_tool_call(call)

                if is_valid and fixed_call:
                    formatted_call = {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": fixed_call["function"],
                            "arguments": json.dumps(fixed_call["arguments"]) if isinstance(fixed_call["arguments"], dict) else fixed_call["arguments"]
                        }
                    }
                    formatted_calls.append(formatted_call)

            return (formatted_calls if formatted_calls else None), remaining_text

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Fallback extraction failed: {e}")
            return None, response_text

    async def execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute tool calls and return results.

        Args:
            tool_calls: Tool calls to execute

        Returns:
            List of tool results in message format
        """
        results = []

        for call in tool_calls:
            call_id = call.get("id", "")
            function = call.get("function", {})
            function_name = function.get("name", "")

            try:
                # Parse arguments
                arguments_str = function.get("arguments", "{}")
                arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str

                # Execute tool
                logger.info(f"Executing tool: {function_name} with args: {arguments}")
                result = await self.executor.execute(function_name, arguments)

                # Format result as message
                result_message = {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": function_name,
                    "content": json.dumps({
                        "success": result.success,
                        "result": result.result,
                        "error": result.error,
                    })
                }
                results.append(result_message)

            except Exception as e:
                logger.error(f"Tool execution failed: {e}", exc_info=True)
                # Return error as tool result
                error_message = {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": function_name,
                    "content": json.dumps({
                        "success": False,
                        "result": None,
                        "error": str(e),
                    })
                }
                results.append(error_message)

        return results

    def format_tool_results_for_llm(
        self,
        tool_results: List[Dict[str, Any]]
    ) -> str:
        """
        Format tool results for the LLM.

        Args:
            tool_results: Tool result messages

        Returns:
            Formatted string for LLM
        """
        if not tool_results:
            return ""

        formatted = "Tool Results:\n\n"
        for result in tool_results:
            tool_name = result.get("name", "unknown")
            content_str = result.get("content", "{}")
            try:
                content = json.loads(content_str) if isinstance(content_str, str) else content_str
                formatted += f"Tool: {tool_name}\n"
                formatted += f"Success: {content.get('success', False)}\n"
                if content.get('error'):
                    formatted += f"Error: {content['error']}\n"
                else:
                    formatted += f"Result: {json.dumps(content.get('result'), indent=2)}\n"
                formatted += "\n"
            except:
                formatted += f"Tool: {tool_name}\nRaw result: {content_str}\n\n"

        return formatted


# Global handler instance
_function_calling_handler: Optional[FunctionCallingHandler] = None


def get_function_calling_handler() -> FunctionCallingHandler:
    """Get the global function calling handler"""
    global _function_calling_handler
    if _function_calling_handler is None:
        _function_calling_handler = FunctionCallingHandler()
    return _function_calling_handler
