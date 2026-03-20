"""
Structured Output module for reliable JSON generation and tool calling.

This module provides:
- JSON schema enforcement using Pydantic
- Retry logic for malformed outputs
- Multiple extraction strategies
- Validation and error recovery
- Target: 99%+ success rate for structured outputs
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Type, Union, Callable
from dataclasses import dataclass
from enum import Enum
import time

from pydantic import BaseModel, Field, ValidationError, create_model
from pydantic.json_schema import JsonSchemaValue

logger = logging.getLogger(__name__)


class ExtractionStrategy(Enum):
    """Strategies for extracting structured output from LLM responses."""
    JSON_BLOCK = "json_block"  # Extract from ```json blocks
    JSON_DETECT = "json_detect"  # Detect JSON anywhere in text
    GUIDED = "guided"  # Use guided generation (grammar-based)
    FUNCTION_CALL = "function_call"  # Use function calling API
    PROMPT_ENGINEERING = "prompt_engineering"  # Careful prompt design
    REGEX = "regex"  # Regex-based extraction


@dataclass
class ExtractionResult:
    """Result of a structured extraction attempt."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    strategy_used: Optional[ExtractionStrategy] = None
    attempts: int = 0
    raw_output: Optional[str] = None


class StructuredOutputHandler:
    """
    Handles structured output generation with high reliability.

    Features:
    - Multiple extraction strategies
    - Automatic retry with different approaches
    - Schema validation
    - Error recovery
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 0.5,
        strict_mode: bool = False
    ):
        """
        Initialize the structured output handler.

        Args:
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries (seconds)
            strict_mode: If True, fail fast on validation errors
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.strict_mode = strict_mode
        self.extraction_strategies = [
            ExtractionStrategy.JSON_BLOCK,
            ExtractionStrategy.JSON_DETECT,
            ExtractionStrategy.REGEX,
            ExtractionStrategy.PROMPT_ENGINEERING
        ]

    def extract_json(
        self,
        text: str,
        schema: Optional[Type[BaseModel]] = None,
        validate: bool = True
    ) -> ExtractionResult:
        """
        Extract JSON from text using multiple strategies.

        Args:
            text: Text potentially containing JSON
            schema: Pydantic model for validation
            validate: Whether to validate against schema

        Returns:
            ExtractionResult with extracted data or error
        """
        attempts = 0

        for strategy in self.extraction_strategies:
            attempts += 1

            try:
                # Try extraction with current strategy
                json_data = self._extract_with_strategy(text, strategy)

                if json_data is None:
                    continue

                # Validate if schema provided
                if validate and schema:
                    validated_data = self._validate_against_schema(json_data, schema)
                    if validated_data:
                        return ExtractionResult(
                            success=True,
                            data=validated_data,
                            strategy_used=strategy,
                            attempts=attempts,
                            raw_output=text
                        )
                else:
                    # No validation requested
                    return ExtractionResult(
                        success=True,
                        data=json_data,
                        strategy_used=strategy,
                        attempts=attempts,
                        raw_output=text
                    )

            except Exception as e:
                logger.debug(f"Strategy {strategy.value} failed: {e}")
                continue

        # All strategies failed
        return ExtractionResult(
            success=False,
            error="Failed to extract valid JSON from text",
            attempts=attempts,
            raw_output=text
        )

    def _extract_with_strategy(
        self,
        text: str,
        strategy: ExtractionStrategy
    ) -> Optional[Dict[str, Any]]:
        """
        Extract JSON using a specific strategy.

        Args:
            text: Input text
            strategy: Extraction strategy to use

        Returns:
            Extracted JSON data or None
        """
        if strategy == ExtractionStrategy.JSON_BLOCK:
            return self._extract_json_block(text)

        elif strategy == ExtractionStrategy.JSON_DETECT:
            return self._extract_json_detect(text)

        elif strategy == ExtractionStrategy.REGEX:
            return self._extract_with_regex(text)

        elif strategy == ExtractionStrategy.PROMPT_ENGINEERING:
            return self._extract_with_prompt_hints(text)

        return None

    def _extract_json_block(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from ```json blocks."""
        # Look for ```json blocks
        pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # Try without json marker
        pattern = r'```\s*(.*?)\s*```'
        matches = re.findall(pattern, text, re.DOTALL)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        return None

    def _extract_json_detect(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect and extract JSON from anywhere in text."""
        # Try to find JSON-like structures
        json_candidates = []

        # Look for objects
        object_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(object_pattern, text)

        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, dict):
                    json_candidates.append(data)
            except json.JSONDecodeError:
                continue

        # Return the largest valid JSON object
        if json_candidates:
            return max(json_candidates, key=lambda x: len(json.dumps(x)))

        # Try parsing the entire text
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        return None

    def _extract_with_regex(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract structured data using regex patterns."""
        # Common patterns for tool calls
        patterns = [
            # Function call pattern
            r'"function":\s*"([^"]+)",\s*"arguments":\s*(\{[^}]+\})',
            # Tool call pattern
            r'"tool":\s*"([^"]+)",\s*"parameters":\s*(\{[^}]+\})',
            # Action pattern
            r'"action":\s*"([^"]+)",\s*"action_input":\s*(\{[^}]+\})',
        ]

        for pattern in patterns:
            matches = re.search(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    function_name = matches.group(1)
                    arguments = json.loads(matches.group(2))
                    return {
                        "function": function_name,
                        "arguments": arguments
                    }
                except (json.JSONDecodeError, IndexError):
                    continue

        return None

    def _extract_with_prompt_hints(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract using prompt engineering hints."""
        # Look for structured markers
        markers = [
            ("OUTPUT:", "\n"),
            ("RESULT:", "\n"),
            ("JSON:", "\n"),
            ("Response:", "\n"),
        ]

        for start_marker, end_marker in markers:
            if start_marker in text:
                start_idx = text.index(start_marker) + len(start_marker)
                if end_marker:
                    end_idx = text.find(end_marker, start_idx)
                    if end_idx != -1:
                        candidate = text[start_idx:end_idx].strip()
                    else:
                        candidate = text[start_idx:].strip()
                else:
                    candidate = text[start_idx:].strip()

                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

        return None

    def _validate_against_schema(
        self,
        data: Dict[str, Any],
        schema: Type[BaseModel]
    ) -> Optional[Dict[str, Any]]:
        """
        Validate data against a Pydantic schema.

        Args:
            data: Data to validate
            schema: Pydantic model class

        Returns:
            Validated data or None if validation fails
        """
        try:
            validated = schema(**data)
            return validated.model_dump()
        except ValidationError as e:
            logger.debug(f"Schema validation failed: {e}")
            if self.strict_mode:
                raise
            return None

    def generate_with_schema(
        self,
        generate_fn: Callable[[str], str],
        prompt: str,
        schema: Type[BaseModel],
        examples: Optional[List[Dict[str, Any]]] = None,
        max_attempts: Optional[int] = None
    ) -> ExtractionResult:
        """
        Generate structured output with a schema.

        Args:
            generate_fn: Function that generates text from a prompt
            prompt: Base prompt
            schema: Pydantic model for output structure
            examples: Example outputs for few-shot learning
            max_attempts: Override max retry attempts

        Returns:
            ExtractionResult with generated structured data
        """
        max_attempts = max_attempts or self.max_retries

        # Create schema-aware prompt
        enhanced_prompt = self._create_schema_prompt(prompt, schema, examples)

        for attempt in range(max_attempts):
            try:
                # Generate response
                response = generate_fn(enhanced_prompt)

                # Extract and validate
                result = self.extract_json(response, schema, validate=True)

                if result.success:
                    return result

                # If failed, enhance prompt with error feedback
                if attempt < max_attempts - 1:
                    enhanced_prompt = self._add_error_feedback(
                        enhanced_prompt,
                        result.error,
                        response
                    )
                    time.sleep(self.retry_delay)

            except Exception as e:
                logger.error(f"Generation attempt {attempt + 1} failed: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(self.retry_delay)
                continue

        # All attempts failed
        return ExtractionResult(
            success=False,
            error=f"Failed to generate valid output after {max_attempts} attempts",
            attempts=max_attempts
        )

    def _create_schema_prompt(
        self,
        base_prompt: str,
        schema: Type[BaseModel],
        examples: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Create an enhanced prompt with schema information.

        Args:
            base_prompt: Original prompt
            schema: Pydantic model
            examples: Example outputs

        Returns:
            Enhanced prompt with schema guidance
        """
        # Get JSON schema
        json_schema = schema.model_json_schema()

        # Build enhanced prompt
        prompt_parts = [base_prompt]

        # Add schema information
        prompt_parts.append("\n\nYour response MUST be valid JSON matching this schema:")
        prompt_parts.append(f"```json\n{json.dumps(json_schema, indent=2)}\n```")

        # Add examples if provided
        if examples:
            prompt_parts.append("\n\nExamples of valid responses:")
            for i, example in enumerate(examples[:3], 1):
                prompt_parts.append(f"\nExample {i}:")
                prompt_parts.append(f"```json\n{json.dumps(example, indent=2)}\n```")

        # Add format instructions
        prompt_parts.append("\n\nIMPORTANT: Respond ONLY with valid JSON, no other text.")

        return "\n".join(prompt_parts)

    def _add_error_feedback(
        self,
        prompt: str,
        error: str,
        previous_response: str
    ) -> str:
        """
        Add error feedback to prompt for retry.

        Args:
            prompt: Current prompt
            error: Error message
            previous_response: Previous failed response

        Returns:
            Enhanced prompt with error feedback
        """
        feedback = f"\n\nYour previous response was invalid: {error}"
        feedback += f"\n\nPrevious response: {previous_response[:500]}"
        feedback += "\n\nPlease correct the errors and provide valid JSON."

        return prompt + feedback


class ToolCallValidator:
    """
    Validates and fixes tool/function calls.

    Specifically designed to improve reliability of function calling.
    """

    def __init__(self):
        """Initialize the tool call validator."""
        self.common_errors = {
            "missing_quotes": r'(\w+):\s*([^",\}\]]+)(?=[,\}])',
            "trailing_comma": r',\s*[\}\]]',
            "single_quotes": r"'([^']*)'",
        }

    def validate_tool_call(
        self,
        tool_call: Dict[str, Any],
        tool_schema: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate a tool call against its schema.

        Args:
            tool_call: Tool call to validate
            tool_schema: Expected schema

        Returns:
            Tuple of (is_valid, fixed_call, error_message)
        """
        # Check required fields
        if "function" not in tool_call and "name" not in tool_call:
            return False, None, "Missing function/tool name"

        function_name = tool_call.get("function") or tool_call.get("name")

        # Check arguments
        arguments = tool_call.get("arguments") or tool_call.get("parameters")
        if arguments is None:
            fixed_call = tool_call.copy()
            fixed_call["arguments"] = {}
            return True, fixed_call, None

        # Ensure arguments is a dict
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                # Try to fix common JSON errors
                fixed_args = self._fix_json_errors(arguments)
                try:
                    arguments = json.loads(fixed_args)
                except json.JSONDecodeError:
                    return False, None, "Invalid JSON in arguments"

        # Validate against schema if provided
        if tool_schema:
            validation_result = self._validate_against_tool_schema(
                arguments,
                tool_schema
            )
            if not validation_result[0]:
                return validation_result

        # Create cleaned tool call
        fixed_call = {
            "function": function_name,
            "arguments": arguments
        }

        return True, fixed_call, None

    def _fix_json_errors(self, json_str: str) -> str:
        """
        Fix common JSON formatting errors.

        Args:
            json_str: Malformed JSON string

        Returns:
            Fixed JSON string
        """
        fixed = json_str

        # Fix missing quotes around keys
        fixed = re.sub(r'(\w+):', r'"\1":', fixed)

        # Fix single quotes to double quotes
        fixed = fixed.replace("'", '"')

        # Remove trailing commas
        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)

        # Fix boolean values
        fixed = re.sub(r'\btrue\b', 'true', fixed, flags=re.IGNORECASE)
        fixed = re.sub(r'\bfalse\b', 'false', fixed, flags=re.IGNORECASE)
        fixed = re.sub(r'\bnull\b', 'null', fixed, flags=re.IGNORECASE)

        return fixed

    def _validate_against_tool_schema(
        self,
        arguments: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate arguments against tool schema.

        Args:
            arguments: Tool arguments
            schema: Tool schema

        Returns:
            Tuple of (is_valid, fixed_arguments, error_message)
        """
        required_params = schema.get("required", [])
        properties = schema.get("properties", {})

        fixed_args = arguments.copy()

        # Check required parameters
        for param in required_params:
            if param not in arguments:
                # Try to provide a default if possible
                param_schema = properties.get(param, {})
                if "default" in param_schema:
                    fixed_args[param] = param_schema["default"]
                else:
                    return False, None, f"Missing required parameter: {param}"

        # Validate and coerce types
        for param, value in fixed_args.items():
            if param in properties:
                param_schema = properties[param]
                expected_type = param_schema.get("type")

                # Try to coerce to expected type
                coerced_value = self._coerce_type(value, expected_type)
                if coerced_value is not None:
                    fixed_args[param] = coerced_value
                elif expected_type:
                    return False, None, f"Invalid type for {param}: expected {expected_type}"

        return True, fixed_args, None

    def _coerce_type(self, value: Any, expected_type: str) -> Any:
        """
        Coerce value to expected type.

        Args:
            value: Value to coerce
            expected_type: Expected type name

        Returns:
            Coerced value or None if coercion fails
        """
        if expected_type == "string":
            return str(value)
        elif expected_type == "number":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        elif expected_type == "integer":
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        elif expected_type == "boolean":
            if isinstance(value, str):
                return value.lower() in ["true", "1", "yes"]
            return bool(value)
        elif expected_type == "array":
            if not isinstance(value, list):
                return [value]
            return value
        elif expected_type == "object":
            if isinstance(value, dict):
                return value
            return None

        return value


class OutputFormatter:
    """
    Formats outputs for different response types.

    Ensures consistent, parseable outputs.
    """

    @staticmethod
    def format_tool_response(
        tool_name: str,
        result: Any,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Format a tool execution response.

        Args:
            tool_name: Name of the tool
            result: Tool execution result
            error: Error message if execution failed

        Returns:
            Formatted response
        """
        response = {
            "tool": tool_name,
            "success": error is None,
            "timestamp": time.time()
        }

        if error:
            response["error"] = error
        else:
            response["result"] = result

        return response

    @staticmethod
    def format_function_call(
        function_name: str,
        arguments: Dict[str, Any],
        call_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Format a function call for OpenAI compatibility.

        Args:
            function_name: Function name
            arguments: Function arguments
            call_id: Optional call ID

        Returns:
            Formatted function call
        """
        function_call = {
            "name": function_name,
            "arguments": json.dumps(arguments) if isinstance(arguments, dict) else arguments
        }

        if call_id:
            function_call["id"] = call_id

        return function_call

    @staticmethod
    def format_tool_call(
        tool_name: str,
        arguments: Dict[str, Any],
        call_id: Optional[str] = None,
        tool_type: str = "function"
    ) -> Dict[str, Any]:
        """
        Format a tool call for OpenAI tools API.

        Args:
            tool_name: Tool name
            arguments: Tool arguments
            call_id: Optional call ID
            tool_type: Type of tool (usually "function")

        Returns:
            Formatted tool call
        """
        tool_call = {
            "type": tool_type,
            "function": {
                "name": tool_name,
                "arguments": json.dumps(arguments) if isinstance(arguments, dict) else arguments
            }
        }

        if call_id:
            tool_call["id"] = call_id

        return tool_call