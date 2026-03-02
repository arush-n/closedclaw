"""
Local Memory Chat API for closedclaw.

Provides a chat interface for users to explore and understand their memories
using the local LLM engine. This allows privacy-preserving interaction where
users can ask questions about their stored memories without data leaving
their machine.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from closedclaw.api.deps import get_memory, get_auth_token, get_user_id
from closedclaw.api.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/memory-chat", tags=["Memory Chat"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ChatMessage(BaseModel):
    """A single message in the chat."""
    role: Literal["user", "assistant", "system"] = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = Field(default=None, description="Message timestamp")


class MemoryChatRequest(BaseModel):
    """Request to chat about memories."""
    message: str = Field(..., description="User's message/question")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for continuity")
    history: Optional[List[ChatMessage]] = Field(
        default=None, 
        description="Previous messages in this conversation"
    )
    # Memory retrieval options
    include_memories: bool = Field(default=True, description="Include relevant memories")
    memory_limit: int = Field(default=5, ge=1, le=20, description="Max memories to retrieve")
    sensitivity_max: Optional[int] = Field(
        default=None, ge=0, le=3, 
        description="Max sensitivity level to include"
    )
    tags_filter: Optional[List[str]] = Field(None, description="Filter memories by tags")
    # LLM options
    temperature: Optional[float] = Field(
        default=0.7, ge=0.0, le=2.0,
        description="Response temperature"
    )
    max_tokens: Optional[int] = Field(
        default=1500, ge=100, le=8000,
        description="Max response tokens"
    )


class RetrievedMemory(BaseModel):
    """A memory retrieved for context."""
    id: str
    content: str
    sensitivity: int
    tags: List[str]
    relevance_score: float
    created_at: Optional[datetime]


class MemoryChatResponse(BaseModel):
    """Response from memory chat."""
    message: ChatMessage
    conversation_id: str
    memories_used: List[RetrievedMemory] = Field(
        default_factory=list,
        description="Memories used to generate response"
    )
    memory_count: int = Field(0, description="Number of memories considered")
    model_used: str = Field(..., description="LLM model used for generation")
    is_local: bool = Field(True, description="Whether response was generated locally")
    tokens_used: Optional[int] = Field(None, description="Approximate tokens used")


class MemoryExploreRequest(BaseModel):
    """Request to explore/summarize memories."""
    mode: Literal["summary", "timeline", "topics", "insights"] = Field(
        "summary",
        description="Exploration mode"
    )
    time_range_days: Optional[int] = Field(
        None, 
        description="Limit to recent N days"
    )
    tags_filter: Optional[List[str]] = Field(None, description="Filter by tags")
    sensitivity_max: Optional[int] = Field(None, ge=0, le=3)


class MemoryExploreResponse(BaseModel):
    """Response from memory exploration."""
    mode: str
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)
    memory_count: int
    model_used: str


class LocalEngineStatusResponse(BaseModel):
    """Status of the local LLM engine."""
    enabled: bool
    ollama_installed: bool
    ollama_running: bool
    hardware_profile: Optional[str]
    llm_model: str
    llm_model_available: bool
    embedding_model: str
    embedding_model_available: bool
    available_models: List[str]
    recommended_model: Optional[str]


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

MEMORY_CHAT_SYSTEM_PROMPT = """You are a helpful assistant that helps the user understand and navigate their personal memories stored in closedclaw. 

Your role is to:
1. Answer questions about the user's stored memories
2. Help them find specific information from their memory vault
3. Summarize and explain their memories when asked
4. Provide insights about patterns or connections in their memories
5. Never make up information - only use what's provided in the memory context

IMPORTANT RULES:
- Be conversational and helpful
- If you don't find relevant memories, say so clearly
- Respect privacy - these are personal memories
- Be accurate about what's actually stored vs. what you're inferring
- Keep responses focused and useful

The user's relevant memories are provided below. Use them to answer questions accurately."""


MEMORY_EXPLORE_PROMPTS = {
    "summary": """Provide a concise summary of the user's memories below. 
Organize by themes or topics. Highlight the most important or frequently mentioned items.
Be clear about what's definitively stated vs. inferred.""",
    
    "timeline": """Create a timeline showing when key events or information was stored.
Group by time periods (today, this week, this month, etc.) when possible.
Note any gaps or patterns in when memories were created.""",
    
    "topics": """Analyze the user's memories and identify the main topics or themes.
For each topic, briefly describe what information is stored.
Note which topics have the most memories.""",
    
    "insights": """Look for patterns, connections, and insights across the user's memories.
What topics come up repeatedly? What preferences or patterns are evident?
Provide actionable observations the user might find useful.""",
}


# =============================================================================
# LOCAL LLM INTERFACE
# =============================================================================

class LocalLLMInterface:
    """
    Interface to the local LLM engine.
    
    Handles communication with Ollama for local chat generation.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization of Ollama client."""
        if self._client is None:
            try:
                from ollama import Client
                self._client = Client(host=self.settings.local_engine.ollama_base_url)
            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="Ollama library not installed. Run: pip install ollama"
                )
        return self._client
    
    def get_model_name(self) -> str:
        """Get the configured Ollama model name."""
        from closedclaw.api.core.local import LOCAL_MODELS
        
        model_key = self.settings.local_engine.llm_model
        if model_key in LOCAL_MODELS:
            return LOCAL_MODELS[model_key].ollama_model
        
        # Fallback to direct model name
        return model_key
    
    def generate_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> str:
        """
        Generate a response from the local LLM.
        
        Args:
            messages: List of {"role": str, "content": str} messages
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated response text
        """
        model = self.get_model_name()
        
        try:
            response = self.client.chat(
                model=model,
                messages=messages,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "top_p": 0.9,
                }
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Local LLM generation failed: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Local LLM generation failed: {str(e)}"
            )
    
    def is_available(self) -> bool:
        """Check if the local LLM is available."""
        try:
            self.client.list()
            return True
        except Exception:
            return False


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_memories_for_context(memories: List[Dict], max_tokens: int = 4000) -> str:
    """
    Format memories into a context string for the LLM.
    
    Args:
        memories: List of memory dictionaries
        max_tokens: Approximate token budget
        
    Returns:
        Formatted context string
    """
    if not memories:
        return "No relevant memories found."
    
    lines = ["## Your Memories", ""]
    
    for i, mem in enumerate(memories, 1):
        content = mem.get("memory", mem.get("content", ""))
        tags = mem.get("tags", [])
        created = mem.get("created_at", "")
        sensitivity = mem.get("sensitivity", 0)
        
        lines.append(f"### Memory {i}")
        if tags:
            lines.append(f"Tags: {', '.join(tags)}")
        if created:
            lines.append(f"Created: {created}")
        lines.append(f"Sensitivity: {sensitivity}")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")
    
    context = "\n".join(lines)
    
    # Rough token estimation (4 chars per token)
    if len(context) > max_tokens * 4:
        # Truncate and add indicator
        context = context[:max_tokens * 4 - 100] + "\n\n[Memory context truncated...]"
    
    return context


def generate_conversation_id() -> str:
    """Generate a unique conversation ID."""
    import uuid
    return f"conv_{uuid.uuid4().hex[:12]}"


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/status", response_model=LocalEngineStatusResponse)
async def get_engine_status(token: str = Depends(get_auth_token)):
    """
    Get the status of the local LLM engine.
    
    Returns information about Ollama installation, running status,
    available models, and current configuration.
    """
    from closedclaw.api.core.config import get_settings
    from closedclaw.api.core.local import OllamaManager, LOCAL_MODELS, LOCAL_EMBEDDING_MODELS
    
    settings = get_settings()
    manager = OllamaManager(base_url=settings.local_engine.ollama_base_url)
    
    is_installed = manager.is_installed()
    is_running = manager.is_running()
    available_models = manager.get_installed_models() if is_running else []
    
    # Check if configured models are available
    llm_model_key = settings.local_engine.llm_model
    llm_model_config = LOCAL_MODELS.get(llm_model_key)
    if llm_model_config is not None:
        llm_model_name = llm_model_config.ollama_model
    else:
        llm_model_name = llm_model_key
    
    embed_model_key = settings.local_engine.embedding_model
    embed_model_config = LOCAL_EMBEDDING_MODELS.get(embed_model_key)
    if embed_model_config is not None:
        embed_model_name = embed_model_config.ollama_model
    else:
        embed_model_name = embed_model_key

    llm_base = llm_model_name.split(":")[0]
    embed_base = str(embed_model_name).split(":")[0]
    
    llm_available = any(
        m.startswith(llm_base)
        for m in available_models
    )
    embed_available = any(
        m.startswith(embed_base)
        for m in available_models
    )
    
    # Get hardware profile
    profile = None
    recommended = None
    if is_installed:
        profile = manager.detect_hardware_profile()
        from closedclaw.api.core.local import LocalEngineConfig
        config = LocalEngineConfig.for_hardware_profile(profile)
        recommended = config.ollama_model_name
        profile = profile.value
    
    return LocalEngineStatusResponse(
        enabled=settings.local_engine.enabled,
        ollama_installed=is_installed,
        ollama_running=is_running,
        hardware_profile=profile,
        llm_model=llm_model_key,
        llm_model_available=llm_available,
        embedding_model=embed_model_key,
        embedding_model_available=embed_available,
        available_models=available_models,
        recommended_model=recommended,
    )


@router.post("/chat", response_model=MemoryChatResponse)
async def chat_with_memories(
    request: MemoryChatRequest,
    user_id: str = Depends(get_user_id),
    memory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Chat with your memories using the local LLM.
    
    Send a message and get a response that incorporates relevant memories.
    Everything runs locally on your machine.
    """
    from closedclaw.api.core.config import get_settings
    
    settings = get_settings()
    
    if not settings.local_engine.enabled:
        raise HTTPException(
            status_code=400,
            detail="Local engine is disabled in configuration"
        )
    
    llm = LocalLLMInterface()
    if not llm.is_available():
        raise HTTPException(
            status_code=503,
            detail="Local LLM is not available. Ensure Ollama is running."
        )
    
    # Retrieve relevant memories
    retrieved_memories = []
    memory_context = "No memories retrieved."
    
    if request.include_memories:
        try:
            search_results = memory.search(
                query=request.message,
                user_id=user_id,
                sensitivity_max=request.sensitivity_max,
                tags=request.tags_filter,
                limit=request.memory_limit,
            )
            
            raw_memories = search_results.get("results", [])
            
            # Convert to response format
            for mem in raw_memories:
                retrieved_memories.append(RetrievedMemory(
                    id=mem.get("id", ""),
                    content=mem.get("memory", mem.get("content", "")),
                    sensitivity=mem.get("sensitivity", 0),
                    tags=mem.get("tags", []),
                    relevance_score=mem.get("score", 0.0),
                    created_at=mem.get("created_at"),
                ))
            
            memory_context = format_memories_for_context(
                raw_memories,
                max_tokens=settings.local_engine.memory_context_budget
            )
            
        except Exception as e:
            logger.warning(f"Memory retrieval failed: {e}")
            memory_context = "Failed to retrieve memories."
    
    # Build messages for LLM
    messages = []
    
    # System prompt with memory context
    system_content = f"{MEMORY_CHAT_SYSTEM_PROMPT}\n\n{memory_context}"
    messages.append({"role": "system", "content": system_content})
    
    # Add conversation history
    if request.history:
        for msg in request.history:
            messages.append({"role": msg.role, "content": msg.content})
    
    # Add current user message
    messages.append({"role": "user", "content": request.message})
    
    # Generate response
    response_text = llm.generate_response(
        messages=messages,
        temperature=request.temperature or 0.7,
        max_tokens=request.max_tokens or 1500,
    )
    
    # Create conversation ID
    conversation_id = request.conversation_id or generate_conversation_id()
    
    return MemoryChatResponse(
        message=ChatMessage(
            role="assistant",
            content=response_text,
            timestamp=datetime.now(timezone.utc),
        ),
        conversation_id=conversation_id,
        memories_used=retrieved_memories,
        memory_count=len(retrieved_memories),
        model_used=llm.get_model_name(),
        is_local=True,
        tokens_used=None,  # TODO: Add token counting if needed
    )


@router.post("/explore", response_model=MemoryExploreResponse)
async def explore_memories(
    request: MemoryExploreRequest,
    user_id: str = Depends(get_user_id),
    memory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Explore and get insights about your memories.
    
    Modes:
    - summary: Get a summary of your memories
    - timeline: See a timeline view
    - topics: Discover main topics/themes
    - insights: Get patterns and observations
    """
    from closedclaw.api.core.config import get_settings
    
    settings = get_settings()
    
    if not settings.local_engine.enabled:
        raise HTTPException(
            status_code=400,
            detail="Local engine is disabled"
        )
    
    llm = LocalLLMInterface()
    if not llm.is_available():
        raise HTTPException(
            status_code=503,
            detail="Local LLM is not available"
        )
    
    # Get filtered memories directly
    try:
        all_memories = memory.get_all(
            user_id=user_id,
            sensitivity_max=request.sensitivity_max,
            tags=request.tags_filter,
            limit=50,
        )
    except Exception as e:
        logger.error(f"Failed to retrieve memories for exploration: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memories for exploration")
    
    memories_list = all_memories.get("results", [])
    
    if not memories_list:
        return MemoryExploreResponse(
            mode=request.mode,
            summary="No memories found matching your criteria.",
            details={},
            memory_count=0,
            model_used=llm.get_model_name(),
        )
    
    # Build context
    memory_context = format_memories_for_context(
        memories_list,
        max_tokens=settings.local_engine.memory_context_budget,
    )
    
    # Get mode-specific prompt
    explore_prompt = MEMORY_EXPLORE_PROMPTS.get(request.mode, MEMORY_EXPLORE_PROMPTS["summary"])
    
    messages = [
        {"role": "system", "content": explore_prompt + "\n\n" + memory_context},
        {"role": "user", "content": f"Please provide a {request.mode} of my memories."},
    ]
    
    response_text = llm.generate_response(
        messages=messages,
        temperature=0.5,  # Lower temp for more factual responses
        max_tokens=2000,
    )
    
    return MemoryExploreResponse(
        mode=request.mode,
        summary=response_text,
        details={
            "memory_count_analyzed": len(memories_list),
            "filters_applied": {
                "time_range_days": request.time_range_days,
                "tags": request.tags_filter,
                "sensitivity_max": request.sensitivity_max,
            }
        },
        memory_count=len(memories_list),
        model_used=llm.get_model_name(),
    )


@router.get("/models")
async def list_available_models(
    profile: Optional[str] = Query(
        None,
        description="Filter by hardware profile (minimal, standard, performance, workstation)"
    ),
    token: str = Depends(get_auth_token),
):
    """
    List available local LLM models with their requirements.
    
    Shows models compatible with the specified hardware profile.
    """
    from closedclaw.api.core.local import (
        LOCAL_MODELS, 
        LOCAL_EMBEDDING_MODELS,
        HardwareProfile,
        list_available_models as get_models,
    )
    
    hw_profile = None
    if profile:
        try:
            hw_profile = HardwareProfile(profile)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid profile. Must be one of: minimal, standard, performance, workstation"
            )
    
    models = get_models(profile=hw_profile)
    
    return {
        "llm_models": [
            {
                "key": key,
                "name": model.name,
                "ollama_model": model.ollama_model,
                "parameters": model.parameters,
                "quantization": model.quantization,
                "context_length": model.context_length,
                "vram_required_gb": model.vram_required_gb,
                "hardware_profile": model.hardware_profile.value,
                "description": model.description,
                "supports_vision": model.supports_vision,
                "supports_tools": model.supports_tools,
            }
            for key, model in LOCAL_MODELS.items()
            if hw_profile is None or model.hardware_profile.value <= hw_profile.value
        ],
        "embedding_models": [
            {
                "key": key,
                "name": model.name,
                "ollama_model": model.ollama_model,
                "embedding_dims": model.embedding_dims,
                "hardware_profile": model.hardware_profile.value,
                "description": model.description,
            }
            for key, model in LOCAL_EMBEDDING_MODELS.items()
        ],
    }
