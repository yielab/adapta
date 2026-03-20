"""
LangGraph Integration for Brain Platform.

State graph compatibility with:
- Automatic context optimization
- Checkpointing support
- Node creation helpers
- Memory integration
"""

import logging
from typing import Any, Dict, List, Optional, TypedDict, Annotated, Sequence
from dataclasses import dataclass
import asyncio
import json
from enum import Enum

try:
    from langgraph.graph import StateGraph, END
    from langgraph.graph.graph import CompiledGraph
    from langgraph.checkpoint import MemorySaver
    from langgraph.prebuilt import ToolExecutor, ToolInvocation
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = object
    logging.warning("LangGraph not installed. LangGraph adapter will not be available.")

from brain.core import inference_engine
from brain.core.inference import InferenceRequest, Message as BrainMessage
from brain.memory import get_memory_manager, MemoryTier
from brain.core.context_manager import ContextManager
from brain.tools import get_tool_executor
from brain.core.tracing import get_tracing_manager

logger = logging.getLogger(__name__)


class BrainAgentState(TypedDict):
    """
    Standard state for Brain-powered LangGraph agents.

    Includes:
    - Message history
    - Current context
    - Memory references
    - Tool results
    """
    messages: Annotated[Sequence[BaseMessage], "Message history"]
    context: Annotated[Dict[str, Any], "Current context"]
    memory_ids: Annotated[List[str], "Active memory IDs"]
    tool_results: Annotated[List[Dict], "Tool execution results"]
    current_task: Annotated[str, "Current task description"]
    agent_id: Annotated[str, "Agent identifier"]


class BrainLangGraphNode:
    """
    LangGraph node powered by Brain platform.

    Features:
    - Automatic state management
    - Memory integration
    - Context optimization
    - Tool execution
    """

    def __init__(
        self,
        model_name: str = "qwen2.5-7b",
        agent_id: Optional[str] = None,
        use_memory: bool = True,
        use_tools: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ):
        """
        Initialize Brain-powered LangGraph node.

        Args:
            model_name: Model to use for inference
            agent_id: Agent identifier for memory
            use_memory: Enable memory integration
            use_tools: Enable tool execution
            temperature: Sampling temperature
            max_tokens: Maximum generation tokens
        """
        if not LANGGRAPH_AVAILABLE:
            raise ImportError("LangGraph is required for this adapter")

        self.model_name = model_name
        self.agent_id = agent_id or "langgraph-agent"
        self.use_memory = use_memory
        self.use_tools = use_tools
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Initialize components
        self.memory_manager = get_memory_manager() if use_memory else None
        self.context_manager = ContextManager(model_name=model_name)
        self.tool_executor = get_tool_executor() if use_tools else None
        self.tracer = get_tracing_manager()

    async def __call__(self, state: BrainAgentState) -> BrainAgentState:
        """
        Execute node logic on state.

        Args:
            state: Current agent state

        Returns:
            Updated state
        """
        with self.tracer.trace_agent_action(
            agent_id=self.agent_id,
            action="langgraph_node",
            task=state.get("current_task", "")
        ):
            # Extract messages
            messages = state.get("messages", [])

            # Recall relevant memories
            if self.use_memory and self.memory_manager:
                memories = await self._recall_memories(state)
                if memories:
                    # Add memories as context
                    memory_content = "\n".join([m.content for m in memories])
                    context_msg = SystemMessage(
                        content=f"[Relevant Memories]\n{memory_content}"
                    )
                    messages = [context_msg] + messages

            # Convert to Brain messages
            brain_messages = self._convert_messages(messages)

            # Optimize context
            for msg in brain_messages:
                self.context_manager.add_message(
                    role=msg.role,
                    content=msg.content,
                    metadata={"agent_id": self.agent_id}
                )

            optimized = self.context_manager.optimize_context()

            # Generate response
            request = InferenceRequest(
                model=self.model_name,
                messages=[BrainMessage(**m) for m in optimized],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            result = await inference_engine.generate(request)

            # Parse for tool calls if enabled
            tool_results = []
            if self.use_tools and self.tool_executor:
                tool_calls = self._extract_tool_calls(result.content)
                if tool_calls:
                    tool_results = await self._execute_tools(tool_calls)

            # Store in memory
            if self.use_memory and self.memory_manager:
                memory_entry = await self.memory_manager.store(
                    content=result.content,
                    tier=MemoryTier.SHORT_TERM,
                    agent_id=self.agent_id,
                    metadata={
                        "task": state.get("current_task"),
                        "tool_results": tool_results
                    }
                )
                state["memory_ids"].append(memory_entry.id)

            # Update state
            state["messages"].append(AIMessage(content=result.content))
            if tool_results:
                state["tool_results"].extend(tool_results)

            return state

    async def _recall_memories(self, state: BrainAgentState) -> List[Any]:
        """Recall relevant memories based on state."""
        if not self.memory_manager:
            return []

        # Use current task as query
        query = state.get("current_task", "")
        if not query and state.get("messages"):
            # Use last message as query
            last_msg = state["messages"][-1]
            query = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)

        memories = await self.memory_manager.recall(
            query=query,
            agent_id=self.agent_id,
            limit=5
        )

        return memories

    def _convert_messages(self, messages: Sequence[BaseMessage]) -> List[BrainMessage]:
        """Convert LangGraph messages to Brain messages."""
        brain_messages = []

        for msg in messages:
            if isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            else:
                role = "system"

            brain_messages.append(BrainMessage(
                role=role,
                content=msg.content if hasattr(msg, 'content') else str(msg)
            ))

        return brain_messages

    def _extract_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """Extract tool calls from generated content."""
        # Simple pattern matching for tool calls
        # In production, use structured output handler
        tool_calls = []

        if "Tool:" in content or "Function:" in content:
            # Parse tool calls from content
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("Tool:") or line.startswith("Function:"):
                    tool_name = line.split(":", 1)[1].strip()
                    # Look for arguments in next line
                    if i + 1 < len(lines):
                        args_line = lines[i + 1]
                        if "Args:" in args_line or "Arguments:" in args_line:
                            try:
                                args_str = args_line.split(":", 1)[1].strip()
                                args = json.loads(args_str) if args_str.startswith("{") else {}
                            except:
                                args = {}

                            tool_calls.append({
                                "name": tool_name,
                                "arguments": args
                            })

        return tool_calls

    async def _execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute tool calls and return results."""
        results = []

        for call in tool_calls:
            try:
                result = await self.tool_executor.execute(
                    call["name"],
                    call.get("arguments", {})
                )
                results.append({
                    "tool": call["name"],
                    "success": result.success,
                    "result": result.result,
                    "error": result.error
                })
            except Exception as e:
                results.append({
                    "tool": call["name"],
                    "success": False,
                    "error": str(e)
                })

        return results


class BrainStateGraph:
    """
    Helper for creating Brain-powered state graphs.

    Simplifies creation of LangGraph workflows with Brain integration.
    """

    def __init__(
        self,
        model_name: str = "qwen2.5-7b",
        checkpointer: Optional[Any] = None
    ):
        """
        Initialize Brain state graph helper.

        Args:
            model_name: Default model for nodes
            checkpointer: Checkpointing implementation
        """
        if not LANGGRAPH_AVAILABLE:
            raise ImportError("LangGraph is required for this adapter")

        self.model_name = model_name
        self.checkpointer = checkpointer or MemorySaver()
        self.nodes = {}

    def create_graph(self, state_class: type = BrainAgentState) -> StateGraph:
        """
        Create a new state graph.

        Args:
            state_class: State class to use

        Returns:
            StateGraph instance
        """
        return StateGraph(state_class)

    def create_node(
        self,
        name: str,
        agent_id: Optional[str] = None,
        **kwargs
    ) -> BrainLangGraphNode:
        """
        Create a Brain-powered node.

        Args:
            name: Node name
            agent_id: Agent identifier
            **kwargs: Node configuration

        Returns:
            BrainLangGraphNode instance
        """
        node = BrainLangGraphNode(
            model_name=self.model_name,
            agent_id=agent_id or name,
            **kwargs
        )
        self.nodes[name] = node
        return node

    def add_reasoning_chain(
        self,
        graph: StateGraph,
        steps: List[str]
    ):
        """
        Add a reasoning chain to the graph.

        Args:
            graph: StateGraph to modify
            steps: List of reasoning step names
        """
        for i, step in enumerate(steps):
            # Create node for each step
            node = self.create_node(
                name=step,
                agent_id=f"reasoning-{step}"
            )

            # Add to graph
            graph.add_node(step, node)

            # Connect to next step or END
            if i < len(steps) - 1:
                graph.add_edge(step, steps[i + 1])
            else:
                graph.add_edge(step, END)

        # Set entry point
        graph.set_entry_point(steps[0])

    def add_conditional_routing(
        self,
        graph: StateGraph,
        node_name: str,
        condition_fn: callable,
        routes: Dict[str, str]
    ):
        """
        Add conditional routing to a node.

        Args:
            graph: StateGraph to modify
            node_name: Node to add routing to
            condition_fn: Function to determine route
            routes: Mapping of condition results to node names
        """
        graph.add_conditional_edges(
            node_name,
            condition_fn,
            routes
        )

    def compile(
        self,
        graph: StateGraph,
        **kwargs
    ) -> CompiledGraph:
        """
        Compile the graph with checkpointing.

        Args:
            graph: Graph to compile
            **kwargs: Compilation options

        Returns:
            Compiled graph
        """
        return graph.compile(
            checkpointer=self.checkpointer,
            **kwargs
        )


# Example workflow creators
def create_research_workflow(
    model_name: str = "qwen2.5-7b"
) -> CompiledGraph:
    """
    Create a research workflow using Brain and LangGraph.

    Steps:
    1. Query understanding
    2. Information gathering
    3. Analysis
    4. Summary generation

    Args:
        model_name: Model to use

    Returns:
        Compiled research workflow
    """
    helper = BrainStateGraph(model_name=model_name)
    graph = helper.create_graph()

    # Add research steps
    helper.add_reasoning_chain(
        graph,
        steps=[
            "understand_query",
            "gather_information",
            "analyze_results",
            "generate_summary"
        ]
    )

    return helper.compile(graph)


def create_task_workflow(
    model_name: str = "qwen2.5-7b",
    with_tools: bool = True
) -> CompiledGraph:
    """
    Create a task execution workflow.

    Steps:
    1. Task planning
    2. Execution (with tools)
    3. Result validation
    4. Response generation

    Args:
        model_name: Model to use
        with_tools: Enable tool execution

    Returns:
        Compiled task workflow
    """
    helper = BrainStateGraph(model_name=model_name)
    graph = helper.create_graph()

    # Create nodes
    planner = helper.create_node("plan", use_tools=False)
    executor = helper.create_node("execute", use_tools=with_tools)
    validator = helper.create_node("validate", use_tools=False)
    responder = helper.create_node("respond", use_tools=False)

    # Add nodes to graph
    graph.add_node("plan", planner)
    graph.add_node("execute", executor)
    graph.add_node("validate", validator)
    graph.add_node("respond", responder)

    # Connect nodes
    graph.set_entry_point("plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "validate")

    # Conditional routing from validator
    def check_validation(state):
        # Check if validation passed
        if state.get("tool_results"):
            # Check for errors
            has_error = any(r.get("error") for r in state["tool_results"])
            return "execute" if has_error else "respond"
        return "respond"

    helper.add_conditional_routing(
        graph,
        "validate",
        check_validation,
        {"execute": "execute", "respond": "respond"}
    )

    graph.add_edge("respond", END)

    return helper.compile(graph)