"""API request/response models (OpenAI-compatible)"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# Chat completion models
class FunctionCall(BaseModel):
    """Function call in a message"""

    name: str
    arguments: str  # JSON string of arguments


class ToolCall(BaseModel):
    """Tool call (OpenAI format)"""

    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class ChatMessage(BaseModel):
    """Chat message"""

    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Optional[str] = None
    name: Optional[str] = None  # For function/tool messages
    function_call: Optional[FunctionCall] = None  # Legacy function calling
    tool_calls: Optional[List[ToolCall]] = None  # New tool calling
    tool_call_id: Optional[str] = None  # For tool response messages


class Function(BaseModel):
    """Function definition for function calling"""

    name: str
    description: str
    parameters: Dict[str, Any]


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request"""

    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    top_k: Optional[int] = 40
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None
    # Function/tool calling
    functions: Optional[List[Function]] = None  # Legacy function calling
    function_call: Optional[str | Dict[str, str]] = None  # "auto", "none", or {"name": "function_name"}
    tools: Optional[List[Dict[str, Any]]] = None  # New tool calling
    tool_choice: Optional[str | Dict[str, Any]] = None  # "auto", "none", "required", or {"type": "function", "function": {"name": "..."}}
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
    temperature: float = 0.7
    max_tokens: int = 512


class AgentInfo(BaseModel):
    """Agent information"""

    id: str
    name: str
    description: Optional[str] = None
    model: str
    capabilities: List[str]
    created: int
    active: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None


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
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512


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


# Vision models
class VisionChatRequest(BaseModel):
    """Vision chat request with image"""

    model: str = Field(default="moondream2", description="Vision model to use")
    prompt: str = Field(..., description="Question or prompt about the image")
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 256


class VisionChatResponse(BaseModel):
    """Vision chat response"""

    model: str
    response: str
    image_info: Dict[str, Any]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
