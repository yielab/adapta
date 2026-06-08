"""Inference engine for generating responses"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from llama_cpp import Llama

from brain.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Chat message"""

    role: str
    content: str
    image_data: Optional[Dict[str, Any]] = None  # For vision models


@dataclass
class InferenceRequest:
    """Request for inference"""

    messages: List[Message]
    model_name: str
    temperature: float = settings.temperature
    top_p: float = settings.top_p
    top_k: int = settings.top_k
    max_tokens: int = settings.max_tokens
    stream: bool = True
    stop: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    is_vision_model: bool = False  # Flag for vision model inference


@dataclass
class InferenceResponse:
    """Response from inference"""

    content: str
    model: str
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class InferenceEngine:
    """Handles inference using loaded models"""

    def __init__(self):
        pass

    def _format_chat_prompt(self, request: InferenceRequest) -> str:
        """Format messages into a chat prompt"""
        # Qwen2.5 chat format
        prompt_parts = []

        # Add system prompt if provided
        if request.system_prompt:
            prompt_parts.append(f"<|im_start|>system\n{request.system_prompt}<|im_end|>")

        # Add conversation history
        for msg in request.messages:
            prompt_parts.append(f"<|im_start|>{msg.role}\n{msg.content}<|im_end|>")

        # Add assistant start token
        prompt_parts.append("<|im_start|>assistant\n")

        return "\n".join(prompt_parts)

    def _format_vision_prompt(self, request: InferenceRequest) -> str:
        """
        Format prompt for vision models (e.g., Moondream2).

        Vision models use a different format that includes image embeddings.
        For now, we use a simple text-based prompt that will be enhanced
        with image data at the model level.
        """
        prompt_parts = []

        # Add system prompt if provided
        if request.system_prompt:
            prompt_parts.append(f"System: {request.system_prompt}")

        # Add conversation with image markers
        for msg in request.messages:
            if msg.image_data:
                prompt_parts.append(f"{msg.role}: [Image provided] {msg.content}")
            else:
                prompt_parts.append(f"{msg.role}: {msg.content}")

        prompt_parts.append("assistant:")

        return "\n".join(prompt_parts)

    async def generate(
        self, model: Llama, request: InferenceRequest
    ) -> InferenceResponse:
        """Generate a complete response"""
        # Use vision prompt format if vision model
        if request.is_vision_model:
            prompt = self._format_vision_prompt(request)
            stop_tokens = request.stop or ["\n\n", "user:", "User:"]
        else:
            prompt = self._format_chat_prompt(request)
            stop_tokens = request.stop or ["<|im_end|>", "<|endoftext|>"]

        try:
            # Run inference in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: model(
                    prompt,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    top_p=request.top_p,
                    top_k=request.top_k,
                    stop=stop_tokens,
                    echo=False,
                ),
            )

            # Extract response
            choice = result["choices"][0]
            content = choice["text"].strip()
            finish_reason = choice["finish_reason"]

            # Token usage
            usage = result.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            return InferenceResponse(
                content=content,
                model=request.model_name,
                finish_reason=finish_reason,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )

        except Exception as e:
            logger.error(f"Inference error: {e}")
            raise

    async def generate_stream(
        self, model: Llama, request: InferenceRequest
    ) -> AsyncIterator[str]:
        """Generate a streaming response"""
        prompt = self._format_chat_prompt(request)

        # Prepare stop tokens
        stop_tokens = request.stop or ["<|im_end|>", "<|endoftext|>"]

        try:
            # Create generator
            loop = asyncio.get_event_loop()
            stream = await loop.run_in_executor(
                None,
                lambda: model(
                    prompt,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    top_p=request.top_p,
                    top_k=request.top_k,
                    stop=stop_tokens,
                    stream=True,
                    echo=False,
                ),
            )

            # Yield tokens
            for chunk in stream:
                if "choices" in chunk and len(chunk["choices"]) > 0:
                    delta = chunk["choices"][0].get("text", "")
                    if delta:
                        yield delta

        except Exception as e:
            logger.error(f"Streaming inference error: {e}")
            raise

    def count_tokens(self, model: Llama, text: str) -> int:
        """Count tokens in text"""
        try:
            tokens = model.tokenize(text.encode("utf-8"))
            return len(tokens)
        except Exception as e:
            logger.warning(f"Token counting error: {e}")
            # Rough estimate: 1 token ≈ 4 characters
            return len(text) // 4


# Global inference engine instance
inference_engine = InferenceEngine()
