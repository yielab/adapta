"""API request/response models (OpenAI-compatible)"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# Chat completion models
class ChatMessage(BaseModel):
    """Chat message"""

    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request"""

    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    top_k: Optional[int] = 40
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None
    # Extra fields for our features
    use_rag: Optional[bool] = False
    rag_sources: Optional[List[str]] = None
    rag_top_k: Optional[int] = 3


class ChatCompletionResponseChoice(BaseModel):
    """Chat completion choice"""

    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionResponseUsage(BaseModel):
    """Token usage"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response"""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionResponseChoice]
    usage: ChatCompletionResponseUsage


class ChatCompletionStreamChoice(BaseModel):
    """Streaming chat completion choice"""

    index: int
    delta: Dict[str, Any]
    finish_reason: Optional[str] = None


class ChatCompletionStreamResponse(BaseModel):
    """Streaming chat completion response"""

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChatCompletionStreamChoice]


# Model listing models
class ModelInfo(BaseModel):
    """Model information"""

    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "brain"
    description: Optional[str] = None
    type: Optional[str] = None


class ModelListResponse(BaseModel):
    """List of models"""

    object: str = "list"
    data: List[ModelInfo]


# Agent models
class AgentConfig(BaseModel):
    """Agent configuration"""

    name: str
    description: Optional[str] = None
    template: Optional[str] = None
    model: str
    system_prompt: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    rag_sources: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)


class AgentInfo(BaseModel):
    """Agent information"""

    id: str
    name: str
    description: Optional[str] = None
    model: str
    capabilities: List[str]
    created: int
    active: bool = True


class AgentListResponse(BaseModel):
    """List of agents"""

    object: str = "list"
    data: List[AgentInfo]


class AgentCreateRequest(BaseModel):
    """Create agent request"""

    name: str
    description: Optional[str] = None
    template: Optional[str] = "general"
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)


class DocumentAddRequest(BaseModel):
    """Add document to agent RAG"""

    content: Optional[str] = None
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StatusResponse(BaseModel):
    """Server status"""

    status: str
    version: str
    models_loaded: List[str]
    total_agents: int
