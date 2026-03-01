"""
OpenAI-compatible proxy Pydantic models for closedclaw.

Follows OpenAI Chat Completions API specification.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# OpenAI-compatible Request/Response models
# ============================================================================

class ChatMessage(BaseModel):
    """A single chat message."""
    role: Literal["system", "user", "assistant", "function", "tool"] = Field(
        ..., 
        description="Role of the message sender"
    )
    content: Optional[str] = Field(None, description="Message content")
    name: Optional[str] = Field(None, description="Name of the function/tool")
    function_call: Optional[Dict[str, Any]] = Field(None, description="Function call data")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls")
    tool_call_id: Optional[str] = Field(None, description="Tool call ID for tool responses")


class FunctionDefinition(BaseModel):
    """Definition of a function for function calling."""
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class ToolDefinition(BaseModel):
    """Definition of a tool."""
    type: Literal["function"] = "function"
    function: FunctionDefinition


class ResponseFormat(BaseModel):
    """Response format specification."""
    type: Literal["text", "json_object"] = "text"


class ChatCompletionRequest(BaseModel):
    """
    OpenAI-compatible chat completion request.
    
    This matches the OpenAI API spec for drop-in compatibility.
    """
    model: str = Field(..., min_length=1, max_length=128, description="Model to use")
    messages: List[ChatMessage] = Field(..., description="Chat messages")
    
    # Optional parameters
    temperature: Optional[float] = Field(None, ge=0, le=2)
    top_p: Optional[float] = Field(None, ge=0, le=1)
    n: Optional[int] = Field(None, ge=1, le=128)
    stream: Optional[bool] = Field(default=False)
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = Field(None, ge=1)
    presence_penalty: Optional[float] = Field(None, ge=-2, le=2)
    frequency_penalty: Optional[float] = Field(None, ge=-2, le=2)
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None
    
    # Function calling (legacy)
    functions: Optional[List[FunctionDefinition]] = None
    function_call: Optional[Union[str, Dict[str, str]]] = None
    
    # Tools (new)
    tools: Optional[List[ToolDefinition]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    
    # Response format
    response_format: Optional[ResponseFormat] = None
    seed: Optional[int] = None
    
    # Closedclaw extensions (optional)
    closedclaw_user_id: Optional[str] = Field(
        None, 
        alias="x-closedclaw-user-id",
        description="User ID for memory lookup"
    )
    closedclaw_sensitivity_max: Optional[int] = Field(
        None, 
        alias="x-closedclaw-sensitivity-max",
        description="Max sensitivity for memory retrieval"
    )
    closedclaw_disable_memory: Optional[bool] = Field(
        None, 
        alias="x-closedclaw-disable-memory",
        description="Disable memory enrichment for this request"
    )

    @field_validator("messages")
    @classmethod
    def validate_message_bounds(cls, value: List[ChatMessage]) -> List[ChatMessage]:
        if not value:
            raise ValueError("messages must not be empty")
        if len(value) > 50:
            raise ValueError("messages exceeds max length of 50")

        total_chars = 0
        for message in value:
            content = message.content or ""
            if len(content) > 20000:
                raise ValueError("single message content exceeds 20000 characters")
            total_chars += len(content)

        if total_chars > 100000:
            raise ValueError("total message content exceeds 100000 characters")

        return value


class ChatCompletionChoice(BaseModel):
    """A single completion choice."""
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None
    logprobs: Optional[Any] = None


class UsageInfo(BaseModel):
    """Token usage information."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[UsageInfo] = None
    system_fingerprint: Optional[str] = None
    
    # Closedclaw extensions (in response metadata)
    closedclaw_memories_used: Optional[int] = None
    closedclaw_redactions_applied: Optional[int] = None
    closedclaw_audit_id: Optional[str] = None


class ChatCompletionChunkDelta(BaseModel):
    """Delta content in a streaming chunk."""
    role: Optional[str] = None
    content: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatCompletionChunkChoice(BaseModel):
    """A choice in a streaming chunk."""
    index: int
    delta: ChatCompletionChunkDelta
    finish_reason: Optional[str] = None
    logprobs: Optional[Any] = None


class ChatCompletionChunk(BaseModel):
    """OpenAI-compatible streaming chunk."""
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChatCompletionChunkChoice]
    system_fingerprint: Optional[str] = None


# ============================================================================
# Model listing (for compatibility)
# ============================================================================

class ModelInfo(BaseModel):
    """Information about an available model."""
    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str


class ModelListResponse(BaseModel):
    """List of available models."""
    object: Literal["list"] = "list"
    data: List[ModelInfo]


# ============================================================================
# Context injection metadata
# ============================================================================

class ContextInjectionInfo(BaseModel):
    """Information about context injection for a request."""
    memories_retrieved: int = 0
    memories_used: int = 0
    memories_blocked: int = 0
    redactions_applied: int = 0
    consent_gates: int = 0
    context_tokens_added: int = 0
    provider_used: str = ""
    memory_ids: List[str] = Field(default_factory=list)
    audit_entry_id: Optional[str] = None
