"""
LangChain Integration for Brain Platform.

Drop-in replacement for OpenAI LLM in LangChain with:
- Automatic RAG injection
- Memory recall
- Context optimization
- Compatible with existing chains
"""

import logging
from typing import Any, List, Dict, Optional, Mapping, Iterator, AsyncIterator
import asyncio
import json

try:
    from langchain.llms.base import LLM
    from langchain.chat_models.base import BaseChatModel
    from langchain.schema import (
        BaseMessage,
        HumanMessage,
        AIMessage,
        SystemMessage,
        ChatGeneration,
        Generation,
        LLMResult,
        ChatResult
    )
    from langchain.callbacks.manager import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    LLM = object
    BaseChatModel = object
    BaseMessage = object
    logging.warning("LangChain not installed. LangChain adapter will not be available.")

from brain.core import inference_engine, model_manager
from brain.core.inference import InferenceRequest, Message as BrainMessage
from brain.memory import get_memory_manager, MemoryQuery, MemoryTier
from brain.rag import rag_engine
from brain.core.context_manager import ContextManager
from brain.core.tracing import get_tracing_manager

logger = logging.getLogger(__name__)


class BrainLangChainLLM(LLM):
    """
    LangChain-compatible LLM using Brain platform.

    Features:
    - Drop-in replacement for OpenAI LLM
    - Automatic memory integration
    - RAG support
    - Context optimization
    """

    model_name: str = "qwen2.5-7b"
    temperature: float = 0.7
    max_tokens: int = 2048
    agent_id: Optional[str] = None
    use_memory: bool = True
    use_rag: bool = True
    memory_limit: int = 5
    rag_limit: int = 3

    def __init__(self, **kwargs):
        """Initialize Brain LLM for LangChain."""
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain is required for this adapter")
        super().__init__(**kwargs)
        self.memory_manager = get_memory_manager() if self.use_memory else None
        self.context_manager = ContextManager(model_name=self.model_name)
        self.tracer = get_tracing_manager()

    @property
    def _llm_type(self) -> str:
        """Return identifier for this LLM."""
        return "brain-llm"

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Return parameters for identification."""
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "use_memory": self.use_memory,
            "use_rag": self.use_rag
        }

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> str:
        """
        Execute LLM call with Brain platform.

        Args:
            prompt: Input prompt
            stop: Stop sequences
            run_manager: Callback manager
            **kwargs: Additional parameters

        Returns:
            Generated text
        """
        # Start tracing
        with self.tracer.trace_llm_call(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens
        ):
            # Enhance prompt with memory
            if self.use_memory and self.memory_manager:
                memories = asyncio.run(self._recall_memories(prompt))
                if memories:
                    memory_context = "\n".join([m.content for m in memories[:self.memory_limit]])
                    prompt = f"[Relevant Context]\n{memory_context}\n\n[Current Query]\n{prompt}"

            # Enhance prompt with RAG
            if self.use_rag:
                rag_results = asyncio.run(self._search_rag(prompt))
                if rag_results:
                    rag_context = "\n".join([r['content'] for r in rag_results[:self.rag_limit]])
                    prompt = f"[Retrieved Information]\n{rag_context}\n\n{prompt}"

            # Create inference request
            messages = [BrainMessage(role="user", content=prompt)]
            request = InferenceRequest(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stop_sequences=stop
            )

            # Run inference
            result = asyncio.run(inference_engine.generate(request))

            # Store in memory if agent_id is set
            if self.use_memory and self.memory_manager and self.agent_id:
                asyncio.run(self.memory_manager.store(
                    content=f"Q: {prompt}\nA: {result.content}",
                    tier=MemoryTier.SHORT_TERM,
                    agent_id=self.agent_id
                ))

            # Notify callbacks
            if run_manager:
                run_manager.on_llm_new_token(result.content)

            return result.content

    async def _acall(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> str:
        """Async version of _call."""
        # Similar implementation but with async/await
        with self.tracer.trace_llm_call(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens
        ):
            # Enhance with memory
            if self.use_memory and self.memory_manager:
                memories = await self._recall_memories(prompt)
                if memories:
                    memory_context = "\n".join([m.content for m in memories[:self.memory_limit]])
                    prompt = f"[Relevant Context]\n{memory_context}\n\n[Current Query]\n{prompt}"

            # Enhance with RAG
            if self.use_rag:
                rag_results = await self._search_rag(prompt)
                if rag_results:
                    rag_context = "\n".join([r['content'] for r in rag_results[:self.rag_limit]])
                    prompt = f"[Retrieved Information]\n{rag_context}\n\n{prompt}"

            messages = [BrainMessage(role="user", content=prompt)]
            request = InferenceRequest(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stop_sequences=stop
            )

            result = await inference_engine.generate(request)

            if self.use_memory and self.memory_manager and self.agent_id:
                await self.memory_manager.store(
                    content=f"Q: {prompt}\nA: {result.content}",
                    tier=MemoryTier.SHORT_TERM,
                    agent_id=self.agent_id
                )

            if run_manager:
                await run_manager.on_llm_new_token(result.content)

            return result.content

    async def _recall_memories(self, query: str) -> List[Any]:
        """Recall relevant memories."""
        if not self.memory_manager:
            return []

        query_obj = MemoryQuery(
            query=query,
            agent_id=self.agent_id,
            limit=self.memory_limit
        )
        return await self.memory_manager.recall(query_obj)

    async def _search_rag(self, query: str) -> List[Dict[str, Any]]:
        """Search RAG for relevant documents."""
        try:
            results = await rag_engine.search(query, k=self.rag_limit)
            return results
        except:
            return []


class BrainLangChainChat(BaseChatModel):
    """
    LangChain-compatible Chat model using Brain platform.

    Features:
    - Full chat model compatibility
    - Message history management
    - Context optimization
    - Streaming support
    """

    model_name: str = "qwen2.5-7b"
    temperature: float = 0.7
    max_tokens: int = 2048
    agent_id: Optional[str] = None
    use_memory: bool = True
    use_rag: bool = True
    streaming: bool = False

    def __init__(self, **kwargs):
        """Initialize Brain Chat model for LangChain."""
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain is required for this adapter")
        super().__init__(**kwargs)
        self.memory_manager = get_memory_manager() if self.use_memory else None
        self.context_manager = ContextManager(model_name=self.model_name)
        self.tracer = get_tracing_manager()

    @property
    def _llm_type(self) -> str:
        """Return identifier for this chat model."""
        return "brain-chat"

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Return parameters for identification."""
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "streaming": self.streaming
        }

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> ChatResult:
        """
        Generate chat response.

        Args:
            messages: Input messages
            stop: Stop sequences
            run_manager: Callback manager
            **kwargs: Additional parameters

        Returns:
            ChatResult with generation
        """
        # Convert LangChain messages to Brain messages
        brain_messages = self._convert_messages(messages)

        # Add to context manager
        for msg in brain_messages:
            self.context_manager.add_message(
                role=msg.role,
                content=msg.content
            )

        # Optimize context
        optimized_messages = self.context_manager.optimize_context()

        # Create request
        request = InferenceRequest(
            model=self.model_name,
            messages=[BrainMessage(**m) for m in optimized_messages],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop_sequences=stop,
            stream=self.streaming
        )

        # Generate response
        with self.tracer.trace_llm_call(
            model=self.model_name,
            messages=optimized_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        ):
            result = asyncio.run(inference_engine.generate(request))

        # Create chat generation
        generation = ChatGeneration(
            message=AIMessage(content=result.content),
            generation_info={
                "model": self.model_name,
                "usage": result.usage
            }
        )

        # Store in memory
        if self.use_memory and self.memory_manager and self.agent_id:
            asyncio.run(self.memory_manager.store(
                content=result.content,
                tier=MemoryTier.SHORT_TERM,
                agent_id=self.agent_id,
                metadata={"role": "assistant"}
            ))

        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> ChatResult:
        """Async version of _generate."""
        brain_messages = self._convert_messages(messages)

        for msg in brain_messages:
            self.context_manager.add_message(
                role=msg.role,
                content=msg.content
            )

        optimized_messages = self.context_manager.optimize_context()

        request = InferenceRequest(
            model=self.model_name,
            messages=[BrainMessage(**m) for m in optimized_messages],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop_sequences=stop,
            stream=self.streaming
        )

        with self.tracer.trace_llm_call(
            model=self.model_name,
            messages=optimized_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        ):
            result = await inference_engine.generate(request)

        generation = ChatGeneration(
            message=AIMessage(content=result.content),
            generation_info={
                "model": self.model_name,
                "usage": result.usage
            }
        )

        if self.use_memory and self.memory_manager and self.agent_id:
            await self.memory_manager.store(
                content=result.content,
                tier=MemoryTier.SHORT_TERM,
                agent_id=self.agent_id,
                metadata={"role": "assistant"}
            )

        return ChatResult(generations=[generation])

    def _convert_messages(self, messages: List[BaseMessage]) -> List[BrainMessage]:
        """Convert LangChain messages to Brain messages."""
        brain_messages = []

        for msg in messages:
            if isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            elif isinstance(msg, SystemMessage):
                role = "system"
            else:
                role = "user"

            brain_messages.append(BrainMessage(
                role=role,
                content=msg.content
            ))

        return brain_messages

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> Iterator[ChatGeneration]:
        """Stream chat responses."""
        brain_messages = self._convert_messages(messages)

        request = InferenceRequest(
            model=self.model_name,
            messages=brain_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop_sequences=stop,
            stream=True
        )

        # Stream tokens
        stream = asyncio.run(inference_engine.stream(request))
        for token in stream:
            yield ChatGeneration(
                message=AIMessage(content=token),
                generation_info={"streaming": True}
            )

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> AsyncIterator[ChatGeneration]:
        """Async stream chat responses."""
        brain_messages = self._convert_messages(messages)

        request = InferenceRequest(
            model=self.model_name,
            messages=brain_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop_sequences=stop,
            stream=True
        )

        async for token in await inference_engine.stream(request):
            yield ChatGeneration(
                message=AIMessage(content=token),
                generation_info={"streaming": True}
            )


# Factory functions for easy creation
def create_brain_llm(**kwargs) -> BrainLangChainLLM:
    """
    Create a Brain LLM for LangChain.

    Args:
        **kwargs: Configuration parameters

    Returns:
        Configured BrainLangChainLLM instance
    """
    return BrainLangChainLLM(**kwargs)


def create_brain_chat(**kwargs) -> BrainLangChainChat:
    """
    Create a Brain Chat model for LangChain.

    Args:
        **kwargs: Configuration parameters

    Returns:
        Configured BrainLangChainChat instance
    """
    return BrainLangChainChat(**kwargs)