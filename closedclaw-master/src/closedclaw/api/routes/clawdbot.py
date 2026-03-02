"""
ClawdBot Agent API routes.

Exposes the ClawdBot memory-aware agent through a chat endpoint.
The agent can autonomously search, write, and reflect on memories.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from closedclaw.api.deps import get_memory, get_auth_token, get_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/clawdbot", tags=["ClawdBot Agent"])


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================

class ClawdBotMessage(BaseModel):
    """A single message in the ClawdBot conversation."""
    role: Literal["user", "assistant", "system", "tool"] = Field(
        ..., description="Message role"
    )
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = Field(
        default=None, description="Message timestamp"
    )


class ToolCallRecord(BaseModel):
    """Record of a tool call made during the agent loop."""
    tool: str = Field(..., description="Tool name that was called")
    input: dict = Field(default_factory=dict, description="Tool input")
    output: str = Field(default="", description="Tool output (truncated)")


class ClawdBotChatRequest(BaseModel):
    """Request to chat with ClawdBot."""
    message: str = Field(
        ..., min_length=1, max_length=4000,
        description="User message to ClawdBot",
    )
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID for multi-turn continuity"
    )
    history: Optional[List[ClawdBotMessage]] = Field(
        default=None,
        description="Previous messages (used if no conversation_id)",
    )
    sensitivity_max: Optional[int] = Field(
        default=None, ge=0, le=3,
        description="Max sensitivity level the agent is allowed to access",
    )
    temperature: float = Field(
        default=0.7, ge=0.0, le=2.0,
        description="LLM temperature",
    )
    max_iterations: int = Field(
        default=5, ge=1, le=10,
        description="Max tool-call loop iterations",
    )


class ClawdBotChatResponse(BaseModel):
    """Response from ClawdBot."""
    message: ClawdBotMessage = Field(
        ..., description="The assistant's final response"
    )
    conversation_id: str = Field(
        ..., description="Conversation ID for follow-ups"
    )
    phase: str = Field(
        default="DONE",
        description="Final agent phase (DONE = completed normally)",
    )
    tool_calls: List[ToolCallRecord] = Field(
        default_factory=list,
        description="Tools invoked during this turn",
    )
    iterations: int = Field(
        default=0,
        description="Number of tool-call loop iterations used",
    )
    model_used: str = Field(
        default="unknown", description="LLM model used"
    )
    is_local: bool = Field(default=True)


class ClawdBotStatusResponse(BaseModel):
    """ClawdBot availability status."""
    available: bool
    model: Optional[str] = None
    reason: Optional[str] = None


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/status", response_model=ClawdBotStatusResponse)
async def clawdbot_status(
    token: str = Depends(get_auth_token),
):
    """Check whether ClawdBot is available (LLM reachable, etc.)."""
    from closedclaw.api.core.config import get_settings

    settings = get_settings()

    if not settings.local_engine.enabled:
        return ClawdBotStatusResponse(
            available=False,
            reason="Local engine is disabled in configuration",
        )

    try:
        from closedclaw.api.routes.memory_chat import LocalLLMInterface
        llm = LocalLLMInterface()
        if not llm.is_available():
            return ClawdBotStatusResponse(
                available=False,
                reason="Ollama is not reachable. Ensure it is running.",
            )
        return ClawdBotStatusResponse(
            available=True,
            model=llm.get_model_name(),
        )
    except Exception as exc:
        logger.warning(f"ClawdBot status check failed: {exc}")
        return ClawdBotStatusResponse(
            available=False,
            reason="Status check failed",
        )


@router.post("/chat", response_model=ClawdBotChatResponse)
async def clawdbot_chat(
    request: ClawdBotChatRequest,
    user_id: str = Depends(get_user_id),
    memory=Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Chat with ClawdBot – a memory-aware AI agent.

    ClawdBot can autonomously search, store, reflect on, and manage
    your memories.  It decides which tools to call and iterates until
    it has a final answer.  Everything runs locally via Ollama.
    """
    from closedclaw.api.core.config import get_settings
    from closedclaw.api.agents.clawdbot import get_clawdbot

    settings = get_settings()

    if not settings.local_engine.enabled:
        raise HTTPException(
            status_code=400,
            detail="Local engine is disabled in configuration",
        )

    # Obtain clawdbot singleton (updates memory / user_id each call)
    bot = get_clawdbot(memory=memory, user_id=user_id)

    # Check availability via LLM client
    try:
        bot._get_llm()
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="ClawdBot is unavailable – Ollama may not be running.",
        )

    # Convert optional history into the format the agent expects
    history: List[dict] = []
    if request.history:
        for msg in request.history:
            history.append({
                "role": msg.role,
                "content": msg.content,
            })

    # Apply per-request config
    bot.max_tool_calls = request.max_iterations

    # Run synchronous agent loop in a thread pool to avoid blocking the event loop
    try:
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(
            None,
            lambda: bot.chat(
                message=request.message,
                conversation_id=request.conversation_id,
                history=history or None,
                temperature=request.temperature,
            ),
        )
    except Exception as exc:
        logger.error(f"ClawdBot chat error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="ClawdBot encountered an internal error",
        )

    # Build tool-call records for transparency
    tool_records: List[ToolCallRecord] = []
    for msg in state.messages:
        if msg.role == "tool":
            tool_records.append(ToolCallRecord(
                tool=msg.tool_name or "unknown",
                input=msg.tool_input or {},
                output=(msg.content or "")[:500],
            ))

    # Count iterations (number of assistant messages that contained tool
    # calls = iterations used)
    iterations = sum(
        1 for m in state.messages
        if m.role == "assistant" and "```tool" in (m.content or "")
    )

    # Determine model name
    model_name = "unknown"
    try:
        from closedclaw.api.routes.memory_chat import LocalLLMInterface
        model_name = LocalLLMInterface().get_model_name()
    except Exception:
        pass

    return ClawdBotChatResponse(
        message=ClawdBotMessage(
            role="assistant",
            content=state.final_response or "",
            timestamp=datetime.now(timezone.utc),
        ),
        conversation_id=state.conversation_id or "default",
        phase=state.phase.value if hasattr(state.phase, "value") else str(state.phase),
        tool_calls=tool_records,
        iterations=iterations,
        model_used=model_name,
        is_local=True,
    )
