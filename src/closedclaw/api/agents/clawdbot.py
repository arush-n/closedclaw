"""
ClawdBot — The Reference Memory-Aware Agent

A LangGraph-style state machine that demonstrates what a memory-aware AI
companion looks like when it has access to closedclaw's private memory vault.

The agent has five memory tools:
  - search_memory: semantic search
  - write_memory: propose new memory (consent-aware)
  - request_consent: ask user for sensitive data access
  - reflect_on_memories: synthesize & analyze a topic
  - get_memory_timeline: chronological view of a topic

This module provides a self-contained agent loop that works with or without
the langgraph/langchain dependencies. When langgraph is not installed it
falls back to a simple tool-calling loop using Ollama directly.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from closedclaw.api.agents.tools import (
    MemoryTools,
    SearchMemoryInput,
    WriteMemoryInput,
    RequestConsentInput,
    ReflectInput,
    TimelineInput,
)

logger = logging.getLogger(__name__)


# =============================================================================
# AGENT STATE
# =============================================================================

class AgentPhase(str, Enum):
    """Current phase in the agent loop."""
    ROUTE = "route"
    SEARCH_MEMORY = "search_memory"
    WRITE_MEMORY = "write_memory"
    REQUEST_CONSENT = "request_consent"
    REFLECT = "reflect"
    RESPOND = "respond"
    DONE = "done"


class AgentMessage(BaseModel):
    """A message in the agent conversation."""
    role: str  # user, assistant, system, tool
    content: str
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None


class AgentState(BaseModel):
    """Full state of the ClawdBot agent."""
    conversation_id: str = Field(default_factory=lambda: f"clawdbot_{uuid.uuid4().hex[:8]}")
    messages: List[AgentMessage] = Field(default_factory=list)
    phase: AgentPhase = AgentPhase.ROUTE
    user_query: str = ""
    tool_calls_made: int = 0
    max_tool_calls: int = 5
    memory_context: List[Dict[str, Any]] = Field(default_factory=list)
    pending_consent: Optional[str] = None
    final_response: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    model_used: str = ""


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

CLAWDBOT_SYSTEM_PROMPT = """You are ClawdBot, a privacy-aware AI companion with access to {user}'s personal memory vault stored in closedclaw.

You have access to the following tools to help answer questions using the user's memories:

{tool_descriptions}

INSTRUCTIONS:
1. When the user asks a question, think about whether their memories can help answer it.
2. Use search_memory to find relevant memories before responding.
3. Use reflect_on_memories for deeper analysis of a topic across memories.
4. Use get_memory_timeline when the user asks about changes over time.
5. Use write_memory to save important new facts the user shares (with appropriate sensitivity and tags).
6. Use request_consent when you need access to sensitive (Level 3) memories.
7. Be honest about what you know vs. don't know from memories.
8. Never fabricate memories — only reference what search results contain.
9. Keep responses conversational and helpful.

To call a tool, respond with a JSON block like:
```tool
{{"tool": "tool_name", "input": {{"param": "value"}}}}
```

After receiving tool results, formulate your final response to the user.
If you don't need any tools, respond directly to the user."""


# =============================================================================
# CLAWDBOT AGENT
# =============================================================================

class ClawdBot:
    """
    Memory-aware AI agent built on closedclaw.

    Implements a simple tool-calling loop using the local LLM (Ollama).
    When langgraph is available, can optionally use a LangGraph state machine.
    """

    def __init__(
        self,
        memory=None,
        user_id: str = "default",
        settings=None,
        max_tool_calls: int = 5,
    ):
        self.user_id = user_id
        self.max_tool_calls = max_tool_calls
        self._settings = settings
        self._tools = MemoryTools(memory=memory, user_id=user_id, settings=settings)
        self._llm_client = None
        self._conversations: Dict[str, AgentState] = {}
        self._system_prompt_cache: Optional[str] = None
        self._max_conversations: int = 50  # LRU cap

    @property
    def settings(self):
        if self._settings is None:
            from closedclaw.api.core.config import get_settings
            self._settings = get_settings()
        return self._settings

    @property
    def tools(self) -> MemoryTools:
        return self._tools

    def _get_llm(self):
        """Get or create Ollama client."""
        if self._llm_client is None:
            try:
                from ollama import Client
                self._llm_client = Client(
                    host=self.settings.local_engine.ollama_base_url
                )
            except ImportError:
                raise RuntimeError(
                    "Ollama library required for ClawdBot. Run: pip install ollama"
                )
        return self._llm_client

    def _get_model_name(self) -> str:
        """Resolve model key to Ollama model tag."""
        from closedclaw.api.core.local import LOCAL_MODELS
        model_key = self.settings.local_engine.llm_model
        model = LOCAL_MODELS.get(model_key)
        return model.ollama_model if model else model_key

    def _build_system_prompt(self) -> str:
        """Build the system prompt with tool descriptions (cached)."""
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache.replace("{user_placeholder}", self.user_id)

        descriptions = self._tools.get_tool_descriptions()
        lines = []
        for td in descriptions:
            lines.append(f"- **{td['name']}**: {td['description']}")
            lines.append(f"  Parameters: {td['parameters']}")
        tool_text = "\n".join(lines)

        # Cache with placeholder for user_id (changes per request)
        self._system_prompt_cache = CLAWDBOT_SYSTEM_PROMPT.format(
            user="{user_placeholder}",
            tool_descriptions=tool_text,
        )
        return self._system_prompt_cache.replace("{user_placeholder}", self.user_id)

    def _parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract a tool call from the LLM response.

        Looks for a ```tool ... ``` block containing JSON.
        """
        # Check for ```tool block
        match = re.search(r"```tool\s*\n?([\s\S]*?)\n?```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Check for inline JSON with "tool" key
        json_match = re.search(r'\{\s*"tool"\s*:', text)
        if json_match:
            # Find the full JSON object
            start = json_match.start()
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except json.JSONDecodeError:
                            break

        return None

    def _execute_tool(self, tool_name: str, tool_input: Dict) -> Dict[str, Any]:
        """Execute a tool by name and return the result."""
        try:
            if tool_name == "search_memory":
                result = self._tools.search_memory(SearchMemoryInput(**tool_input))
                return result.model_dump()

            elif tool_name == "write_memory":
                result = self._tools.write_memory(WriteMemoryInput(**tool_input))
                return result.model_dump()

            elif tool_name == "request_consent":
                result = self._tools.request_consent(RequestConsentInput(**tool_input))
                return result.model_dump()

            elif tool_name == "reflect_on_memories":
                result = self._tools.reflect_on_memories(ReflectInput(**tool_input))
                return result.model_dump()

            elif tool_name == "get_memory_timeline":
                result = self._tools.get_memory_timeline(TimelineInput(**tool_input))
                return result.model_dump()

            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}: {e}")
            return {"error": str(e)}

    # =========================================================================
    # MAIN CHAT METHOD
    # =========================================================================

    def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> AgentState:
        """
        Process a user message through the ClawdBot agent loop.

        The agent will:
        1. Analyze the user's message
        2. Decide which tools to call (if any)
        3. Execute tool calls iteratively
        4. Generate a final response incorporating tool results

        Args:
            message: User's message
            conversation_id: Existing conversation ID for continuity
            history: Previous conversation messages
            temperature: LLM temperature
            max_tokens: Max tokens for responses

        Returns:
            AgentState with the full conversation state
        """
        model = self._get_model_name()

        # Initialize or resume state
        if conversation_id and conversation_id in self._conversations:
            state = self._conversations[conversation_id]
        else:
            state = AgentState(
                conversation_id=conversation_id or f"clawdbot_{uuid.uuid4().hex[:8]}",
                model_used=model,
            )

        state.user_query = message
        state.phase = AgentPhase.ROUTE
        state.tool_calls_made = 0

        # Add user message
        state.messages.append(
            AgentMessage(
                role="user",
                content=message,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )

        # Build messages for LLM
        llm_messages = [
            {"role": "system", "content": self._build_system_prompt()}
        ]

        # Add conversation history
        if history:
            for h in history:
                llm_messages.append({
                    "role": h.get("role", "user"),
                    "content": h.get("content", ""),
                })

        # Add recent messages from state (last 10 for context budget)
        for msg in state.messages[-10:]:
            if msg.role in ("user", "assistant"):
                llm_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })
            elif msg.role == "tool":
                # Format tool results as assistant context
                llm_messages.append({
                    "role": "assistant",
                    "content": (
                        f"[Tool result from {msg.tool_name}]:\n"
                        f"{json.dumps(msg.tool_output, indent=2)}"
                    ),
                })

        # Agent loop: LLM → tool call → result → repeat (max iterations)
        client = self._get_llm()

        for iteration in range(self.max_tool_calls + 1):
            try:
                response = client.chat(
                    model=model,
                    messages=llm_messages,
                    options={
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        "top_p": 0.9,
                    },
                )
                reply = response["message"]["content"]
            except Exception as e:
                error_msg = f"LLM call failed: {e}"
                logger.error(error_msg)
                state.errors.append(error_msg)
                state.final_response = (
                    "I'm sorry, I couldn't process your request. "
                    "Please ensure Ollama is running with a model available."
                )
                state.phase = AgentPhase.DONE
                break

            # Check for tool calls
            tool_call = self._parse_tool_call(reply)

            if tool_call and state.tool_calls_made < self.max_tool_calls:
                tool_name = tool_call.get("tool", "")
                tool_input = tool_call.get("input", {})

                logger.info(f"ClawdBot calling tool: {tool_name}")
                state.tool_calls_made += 1

                # Execute the tool
                tool_result = self._execute_tool(tool_name, tool_input)

                # Record the tool call
                state.messages.append(
                    AgentMessage(
                        role="tool",
                        content=f"Called {tool_name}",
                        tool_name=tool_name,
                        tool_input=tool_input,
                        tool_output=tool_result,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )

                # Add to LLM context for next iteration
                llm_messages.append({"role": "assistant", "content": reply})
                llm_messages.append({
                    "role": "user",
                    "content": (
                        f"[Tool result from {tool_name}]:\n"
                        f"{json.dumps(tool_result, indent=2)}\n\n"
                        "Now respond to the user incorporating these results. "
                        "If you need another tool, call it. Otherwise give your final answer."
                    ),
                })

                # Update phase
                phase_map = {
                    "search_memory": AgentPhase.SEARCH_MEMORY,
                    "write_memory": AgentPhase.WRITE_MEMORY,
                    "request_consent": AgentPhase.REQUEST_CONSENT,
                    "reflect_on_memories": AgentPhase.REFLECT,
                    "get_memory_timeline": AgentPhase.REFLECT,
                }
                state.phase = phase_map.get(tool_name, AgentPhase.RESPOND)

                # Store memory context from search results
                if tool_name == "search_memory" and "memories" in tool_result:
                    state.memory_context.extend(tool_result["memories"])

            else:
                # No tool call — this is the final response
                # Strip any leftover tool formatting
                final = reply
                if "```tool" in final:
                    # Remove tool blocks from final response
                    final = re.sub(r"```tool[\s\S]*?```", "", final).strip()

                state.final_response = final
                state.phase = AgentPhase.DONE

                state.messages.append(
                    AgentMessage(
                        role="assistant",
                        content=final,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )
                break

        # If we ran out of iterations without a final response
        if state.final_response is None:
            state.final_response = (
                "I explored several of your memories but ran out of steps. "
                "Here's what I found so far. Could you ask a more specific question?"
            )
            state.phase = AgentPhase.DONE

        # Cache the conversation state (with LRU eviction)
        self._conversations[state.conversation_id] = state
        if len(self._conversations) > self._max_conversations:
            oldest_key = next(iter(self._conversations))
            del self._conversations[oldest_key]

        return state

    # =========================================================================
    # CONVERSATION MANAGEMENT
    # =========================================================================

    def get_conversation(self, conversation_id: str) -> Optional[AgentState]:
        """Get a conversation by ID."""
        return self._conversations.get(conversation_id)

    def list_conversations(self) -> List[str]:
        """List all conversation IDs."""
        return list(self._conversations.keys())

    def clear_conversation(self, conversation_id: str) -> bool:
        """Clear a specific conversation."""
        return self._conversations.pop(conversation_id, None) is not None


# =============================================================================
# SINGLETON
# =============================================================================

_clawdbot_instance: Optional[ClawdBot] = None


def get_clawdbot(
    memory=None,
    user_id: str = "default",
) -> ClawdBot:
    """Get or create the singleton ClawdBot instance."""
    global _clawdbot_instance
    if _clawdbot_instance is None:
        _clawdbot_instance = ClawdBot(memory=memory, user_id=user_id)
    # Update memory and user_id for the current request
    if memory is not None:
        _clawdbot_instance._tools._memory = memory
    _clawdbot_instance._tools._user_id = user_id
    _clawdbot_instance.user_id = user_id
    return _clawdbot_instance
