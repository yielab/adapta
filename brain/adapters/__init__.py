"""
Framework adapters for Brain platform integration.

Provides seamless integration with popular frameworks:
- LangChain: Drop-in LLM replacement
- LangGraph: State management integration
- OpenClaw: Deep provider integration
"""

from brain.adapters.langchain import BrainLangChainLLM, BrainLangChainChat
from brain.adapters.langgraph import BrainLangGraphNode, BrainStateGraph
from brain.adapters.openclaw import BrainOpenClawProvider

__all__ = [
    "BrainLangChainLLM",
    "BrainLangChainChat",
    "BrainLangGraphNode",
    "BrainStateGraph",
    "BrainOpenClawProvider",
]