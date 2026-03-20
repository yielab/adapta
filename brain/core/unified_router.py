"""
Unified Smart Router integrating all Brain components.

Orchestrates context management, memory, RAG, routing, and adaptive features.
"""

import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from brain.core.context_manager import ContextManager, Message, MessagePriority
from brain.core.structured_output import StructuredOutputHandler
from brain.core.tracing import TracingManager
from brain.core.router import SmartRouter
from brain.memory.memory_manager import MemoryManager
from brain.agents.adaptive.feedback_collector import FeedbackCollector
from brain.agents.adaptive.evolution_manager import EvolutionManager
from brain.agents.adaptive.ab_testing import ABTestManager
from brain.agents.workspace import WorkspaceManager
from brain.rag.advanced.hybrid_search import HybridSearchEngine, SearchStrategy
from brain.rag.advanced.reranking import HybridReranker
from brain.rag.advanced.query_expansion import AdaptiveQueryExpander
from brain.rag.advanced.citations import CitationTracker, AutoCitationInjector

logger = logging.getLogger(__name__)


@dataclass
class UnifiedConfig:
    """Configuration for unified router."""
    # Context settings
    max_tokens: int = 8192
    context_budget_ratio: float = 0.8

    # Memory settings
    memory_enabled: bool = True
    auto_consolidation: bool = True

    # Workspace settings
    workspace_enabled: bool = True
    auto_checkpoint: bool = True
    checkpoint_interval: int = 3600  # seconds

    # RAG settings
    rag_enabled: bool = True
    rag_top_k: int = 5
    use_query_expansion: bool = True
    use_reranking: bool = True
    use_citations: bool = True

    # Routing settings
    adaptive_routing: bool = True
    fallback_model: str = "qwen2.5-3b-instruct"

    # Tracing settings
    tracing_enabled: bool = True
    trace_export: str = "console"  # console, jaeger, zipkin

    # Adaptive settings
    collect_feedback: bool = True
    enable_ab_testing: bool = True
    auto_evolution: bool = False


@dataclass
class UnifiedRequest:
    """Unified request structure."""
    messages: List[Message]
    agent_id: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None
    stream: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedResponse:
    """Unified response structure."""
    content: str
    model_used: str
    tokens_used: int
    citations: Optional[List[Dict[str, Any]]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class UnifiedRouter:
    """
    Unified router orchestrating all Brain components.

    Features:
    - Intelligent context management
    - Multi-tier memory system
    - Advanced RAG with citations
    - Adaptive model routing
    - Feedback and evolution
    - Full observability
    """

    def __init__(self, config: Optional[UnifiedConfig] = None):
        """
        Initialize unified router.

        Args:
            config: Unified configuration
        """
        self.config = config or UnifiedConfig()

        # Initialize core components
        self._init_context_manager()
        self._init_memory_system()
        self._init_rag_system()
        self._init_routing()
        self._init_adaptive_features()
        self._init_tracing()

        logger.info("Unified Router initialized with all components")

    def _init_context_manager(self):
        """Initialize context management."""
        self.context_manager = ContextManager(
            max_tokens=self.config.max_tokens,
            model="gpt-4"  # For token counting
        )
        self.structured_output = StructuredOutputHandler()

    def _init_memory_system(self):
        """Initialize memory system."""
        if self.config.memory_enabled:
            self.memory_manager = MemoryManager()
            if self.config.auto_consolidation:
                # Start consolidation task
                asyncio.create_task(self._periodic_consolidation())
        else:
            self.memory_manager = None

        # Initialize workspace system
        if self.config.workspace_enabled:
            self.workspace_manager = WorkspaceManager()
            if self.config.auto_checkpoint:
                # Start checkpoint task
                asyncio.create_task(self._periodic_checkpoint())
        else:
            self.workspace_manager = None

    def _init_rag_system(self):
        """Initialize RAG components."""
        if self.config.rag_enabled:
            self.search_engine = HybridSearchEngine()
            self.query_expander = AdaptiveQueryExpander() if self.config.use_query_expansion else None
            self.reranker = HybridReranker() if self.config.use_reranking else None
            self.citation_tracker = CitationTracker() if self.config.use_citations else None
            self.citation_injector = AutoCitationInjector(self.citation_tracker) if self.config.use_citations else None
        else:
            self.search_engine = None

    def _init_routing(self):
        """Initialize model routing."""
        self.router = SmartRouter()

    def _init_adaptive_features(self):
        """Initialize adaptive features."""
        if self.config.collect_feedback:
            self.feedback_collector = FeedbackCollector()
        else:
            self.feedback_collector = None

        if self.config.auto_evolution:
            self.evolution_manager = EvolutionManager()
        else:
            self.evolution_manager = None

        if self.config.enable_ab_testing:
            self.ab_testing = ABTestManager()
        else:
            self.ab_testing = None

    def _init_tracing(self):
        """Initialize tracing."""
        if self.config.tracing_enabled:
            self.tracing = TracingManager(
                service_name="brain-unified",
                export_to=self.config.trace_export
            )
        else:
            self.tracing = None

    async def process(self, request: UnifiedRequest) -> UnifiedResponse:
        """
        Process a unified request through all components.

        Args:
            request: Unified request

        Returns:
            Unified response
        """
        # Start trace
        trace_context = None
        if self.tracing:
            trace_context = self.tracing.start_trace("unified_process")

        try:
            # 1. Workspace notes recall
            if self.workspace_manager and request.agent_id:
                notes = await self._recall_workspace_notes(request, trace_context)
                request = self._inject_notes(request, notes)

            # 2. Memory recall
            if self.memory_manager and request.agent_id:
                memories = await self._recall_memories(request, trace_context)
                request = self._inject_memories(request, memories)

            # 2. RAG enhancement
            if self.search_engine and self._should_use_rag(request):
                request = await self._enhance_with_rag(request, trace_context)

            # 3. Context optimization
            optimized_messages = self._optimize_context(request, trace_context)

            # 4. Model selection
            model = self._select_model(request, trace_context)

            # 5. Generate response
            response = await self._generate_response(
                optimized_messages,
                model,
                request,
                trace_context
            )

            # 6. Handle tool calls
            if request.tools and response.tool_calls:
                response = await self._handle_tool_calls(response, trace_context)

            # 7. Add citations
            if self.citation_tracker and self.config.use_citations:
                response = self._add_citations(response, trace_context)

            # 8. Store in memory
            if self.memory_manager and request.agent_id:
                await self._store_memory(request, response, trace_context)

            # 9. Update workspace notes
            if self.workspace_manager and request.agent_id:
                await self._update_workspace(request, response, trace_context)

            # 10. Collect feedback
            if self.feedback_collector:
                self._collect_feedback(request, response)

            return response

        finally:
            if self.tracing and trace_context:
                self.tracing.end_trace(trace_context)

    async def _recall_memories(
        self,
        request: UnifiedRequest,
        trace_context: Any
    ) -> List[Dict[str, Any]]:
        """Recall relevant memories."""
        if self.tracing:
            span = self.tracing.start_span("memory_recall", trace_context)

        try:
            # Get last user message for context
            user_message = next(
                (m for m in reversed(request.messages) if m.role == "user"),
                None
            )

            if user_message:
                memories = await self.memory_manager.recall(
                    agent_id=request.agent_id,
                    query=user_message.content,
                    top_k=5
                )
                return memories
            return []

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    def _inject_memories(
        self,
        request: UnifiedRequest,
        memories: List[Dict[str, Any]]
    ) -> UnifiedRequest:
        """Inject memories into request."""
        if not memories:
            return request

        # Create memory context message
        memory_text = "\n".join([
            f"- {m.get('content', '')}" for m in memories[:3]
        ])

        memory_message = Message(
            role="system",
            content=f"Relevant memories:\n{memory_text}",
            priority=MessagePriority.HIGH
        )

        # Insert after system message
        request.messages.insert(1, memory_message)
        return request

    def _should_use_rag(self, request: UnifiedRequest) -> bool:
        """Determine if RAG should be used."""
        # Check for question patterns
        user_message = next(
            (m for m in reversed(request.messages) if m.role == "user"),
            None
        )

        if not user_message:
            return False

        # Question indicators
        question_words = ["what", "how", "why", "when", "where", "who", "which"]
        content_lower = user_message.content.lower()

        return any(content_lower.startswith(w) for w in question_words) or "?" in content_lower

    async def _enhance_with_rag(
        self,
        request: UnifiedRequest,
        trace_context: Any
    ) -> UnifiedRequest:
        """Enhance request with RAG."""
        if self.tracing:
            span = self.tracing.start_span("rag_enhancement", trace_context)

        try:
            user_message = next(
                (m for m in reversed(request.messages) if m.role == "user"),
                None
            )

            if not user_message:
                return request

            query = user_message.content

            # Query expansion
            if self.query_expander:
                expanded = self.query_expander.expand(query)
                queries = expanded.get_all_queries()[:3]
            else:
                queries = [query]

            # Search
            all_results = []
            for q in queries:
                results = self.search_engine.search(q, top_k=self.config.rag_top_k)
                all_results.extend(results)

            # Re-rank if enabled
            if self.reranker and all_results:
                all_results = self.reranker.rerank(query, all_results, top_k=self.config.rag_top_k)

            # Create RAG context
            if all_results:
                rag_text = "\n".join([
                    f"- {r.content}" for r in all_results[:self.config.rag_top_k]
                ])

                rag_message = Message(
                    role="system",
                    content=f"Relevant information:\n{rag_text}",
                    priority=MessagePriority.HIGH,
                    metadata={"sources": [r.to_dict() for r in all_results]}
                )

                # Insert after system message
                request.messages.insert(1, rag_message)
                request.metadata["rag_sources"] = [r.to_dict() for r in all_results]

            return request

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    def _optimize_context(
        self,
        request: UnifiedRequest,
        trace_context: Any
    ) -> List[Message]:
        """Optimize context for window."""
        if self.tracing:
            span = self.tracing.start_span("context_optimization", trace_context)

        try:
            # Set budget
            budget = int(self.config.max_tokens * self.config.context_budget_ratio)
            self.context_manager.set_budget(budget)

            # Add messages
            for message in request.messages:
                self.context_manager.add_message(message)

            # Optimize
            optimized = self.context_manager.get_optimized_context()

            return optimized

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    def _select_model(
        self,
        request: UnifiedRequest,
        trace_context: Any
    ) -> str:
        """Select optimal model."""
        if self.tracing:
            span = self.tracing.start_span("model_selection", trace_context)

        try:
            # Use specified model if provided
            if request.model:
                return request.model

            # Get last user message
            user_message = next(
                (m for m in reversed(request.messages) if m.role == "user"),
                None
            )

            if not user_message:
                return self.config.fallback_model

            # Route based on task
            result = self.router.route(
                task=user_message.content,
                context={
                    "has_tools": bool(request.tools),
                    "requires_vision": False,  # Could detect image URLs
                    "max_tokens": request.max_tokens
                }
            )

            return result.model

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    async def _generate_response(
        self,
        messages: List[Message],
        model: str,
        request: UnifiedRequest,
        trace_context: Any
    ) -> UnifiedResponse:
        """Generate response from model."""
        if self.tracing:
            span = self.tracing.start_span("generate_response", trace_context)

        try:
            # Convert messages for API
            api_messages = [
                {"role": m.role, "content": m.content}
                for m in messages
            ]

            # Add tools if present
            api_request = {
                "model": model,
                "messages": api_messages,
                "temperature": request.temperature,
                "stream": request.stream
            }

            if request.tools:
                api_request["tools"] = request.tools
                api_request["tool_choice"] = "auto"

            if request.max_tokens:
                api_request["max_tokens"] = request.max_tokens

            # Call model (mock for now - would integrate with actual inference)
            # In production, this would call brain.core.inference
            response_text = f"[Generated response using {model}]"
            tool_calls = None

            # Handle structured output if tools present
            if request.tools:
                result = self.structured_output.extract(
                    response_text,
                    request.tools[0] if request.tools else None
                )
                if result.success:
                    tool_calls = [result.data]

            return UnifiedResponse(
                content=response_text,
                model_used=model,
                tokens_used=len(response_text.split()),  # Rough estimate
                tool_calls=tool_calls,
                metadata={
                    "routing_reason": self.router.get_last_routing_reason()
                }
            )

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    async def _handle_tool_calls(
        self,
        response: UnifiedResponse,
        trace_context: Any
    ) -> UnifiedResponse:
        """Handle tool calls in response."""
        if self.tracing:
            span = self.tracing.start_span("handle_tools", trace_context)

        try:
            # Tool execution would happen here
            # For now, just mark as handled
            response.metadata["tools_executed"] = True
            return response

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    def _add_citations(
        self,
        response: UnifiedResponse,
        trace_context: Any
    ) -> UnifiedResponse:
        """Add citations to response."""
        if self.tracing:
            span = self.tracing.start_span("add_citations", trace_context)

        try:
            # Get sources from metadata
            sources = response.metadata.get("rag_sources", [])

            if sources and self.citation_injector:
                # Inject citations
                cited_text = self.citation_injector.inject_citations(
                    response.content,
                    sources,
                    style="inline"
                )

                response.content = cited_text

                # Add citation list
                citations = self.citation_tracker.extract_citations(
                    response.content,
                    sources
                )

                response.citations = [
                    c.to_dict() for c in citations.citations
                ]

            return response

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    async def _store_memory(
        self,
        request: UnifiedRequest,
        response: UnifiedResponse,
        trace_context: Any
    ):
        """Store interaction in memory."""
        if self.tracing:
            span = self.tracing.start_span("store_memory", trace_context)

        try:
            # Store user message
            user_message = next(
                (m for m in reversed(request.messages) if m.role == "user"),
                None
            )

            if user_message:
                await self.memory_manager.store(
                    agent_id=request.agent_id,
                    content=user_message.content,
                    memory_type="short_term",
                    metadata={
                        "role": "user",
                        "timestamp": datetime.now().isoformat()
                    }
                )

            # Store assistant response
            await self.memory_manager.store(
                agent_id=request.agent_id,
                content=response.content,
                memory_type="short_term",
                metadata={
                    "role": "assistant",
                    "model": response.model_used,
                    "timestamp": datetime.now().isoformat()
                }
            )

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    def _collect_feedback(
        self,
        request: UnifiedRequest,
        response: UnifiedResponse
    ):
        """Collect feedback for improvement."""
        if not self.feedback_collector:
            return

        # Record interaction
        self.feedback_collector.record_interaction(
            agent_id=request.agent_id or "default",
            input_text=request.messages[-1].content if request.messages else "",
            output_text=response.content,
            metadata={
                "model": response.model_used,
                "tokens": response.tokens_used
            }
        )

    async def _periodic_consolidation(self):
        """Periodic memory consolidation task."""
        while True:
            try:
                await asyncio.sleep(3600)  # Every hour

                if self.memory_manager:
                    agents = await self.memory_manager.list_agents()
                    for agent_id in agents:
                        await self.memory_manager.consolidate(agent_id)
                        logger.info(f"Consolidated memory for agent {agent_id}")

            except Exception as e:
                logger.error(f"Error in periodic consolidation: {e}")

    async def _periodic_checkpoint(self):
        """Periodic workspace checkpoint task."""
        while True:
            try:
                await asyncio.sleep(self.config.checkpoint_interval)

                if self.workspace_manager:
                    for agent_id in self.workspace_manager.list_agents():
                        workspace = self.workspace_manager.get_workspace(agent_id)
                        checkpoint_id = workspace.create_session_checkpoint()
                        workspace.cleanup_old_checkpoints(keep_last=5)
                        logger.info(f"Created checkpoint {checkpoint_id} for agent {agent_id}")

            except Exception as e:
                logger.error(f"Error in periodic checkpoint: {e}")

    async def _recall_workspace_notes(
        self,
        request: UnifiedRequest,
        trace_context: Any
    ) -> List[str]:
        """Recall relevant notes from workspace."""
        if self.tracing:
            span = self.tracing.start_span("workspace_recall", trace_context)

        try:
            workspace = self.workspace_manager.get_workspace(request.agent_id)

            # Get last user message for context
            user_message = next(
                (m for m in reversed(request.messages) if m.role == "user"),
                None
            )

            if user_message:
                # Get relevant notes
                notes = workspace.get_relevant_notes(
                    query=user_message.content,
                    max_notes=3
                )
                return notes
            return []

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    def _inject_notes(
        self,
        request: UnifiedRequest,
        notes: List[str]
    ) -> UnifiedRequest:
        """Inject workspace notes into request."""
        if not notes:
            return request

        # Create notes context message
        notes_text = "\n".join([f"- {note}" for note in notes])

        notes_message = Message(
            role="system",
            content=f"Relevant workspace notes:\n{notes_text}",
            priority=MessagePriority.HIGH
        )

        # Insert after system message
        request.messages.insert(1, notes_message)
        return request

    async def _update_workspace(
        self,
        request: UnifiedRequest,
        response: UnifiedResponse,
        trace_context: Any
    ):
        """Update workspace with interaction details."""
        if self.tracing:
            span = self.tracing.start_span("workspace_update", trace_context)

        try:
            workspace = self.workspace_manager.get_workspace(request.agent_id)

            # Get user message
            user_message = next(
                (m for m in reversed(request.messages) if m.role == "user"),
                None
            )

            if user_message:
                # Write interaction note
                note_content = (
                    f"User: {user_message.content[:200]}...\n"
                    f"Assistant: {response.content[:200]}...\n"
                    f"Model: {response.model_used}"
                )
                workspace.write_note(note_content, category="interaction")

                # Update summary if significant
                if "decision" in user_message.content.lower() or "architecture" in user_message.content.lower():
                    workspace.append_decision(
                        decision=response.content[:100],
                        rationale="User query about architecture/decision"
                    )

                # Track task if mentioned
                if "todo" in user_message.content.lower() or "task" in user_message.content.lower():
                    workspace.track_task(user_message.content[:100], status="in_progress")

        except Exception as e:
            logger.error(f"Error updating workspace: {e}")

        finally:
            if self.tracing:
                self.tracing.end_span(span)

    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics."""
        stats = {
            "router": self.router.get_stats() if self.router else {},
            "memory": self.memory_manager.get_stats() if self.memory_manager else {},
            "context": self.context_manager.get_stats() if self.context_manager else {}
        }

        if self.feedback_collector:
            stats["feedback"] = {
                "total_interactions": len(self.feedback_collector.feedback_store)
            }

        if self.ab_testing:
            stats["ab_testing"] = self.ab_testing.get_all_results()

        return stats


# Global instance
_unified_router: Optional[UnifiedRouter] = None


def get_unified_router(config: Optional[UnifiedConfig] = None) -> UnifiedRouter:
    """
    Get or create unified router instance.

    Args:
        config: Configuration (used only on first call)

    Returns:
        Unified router instance
    """
    global _unified_router
    if _unified_router is None:
        _unified_router = UnifiedRouter(config)
    return _unified_router