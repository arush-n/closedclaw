"""
ClawdBot Memory Tools

Provides structured tools that the ClawdBot LangGraph agent can call
to interact with the closedclaw memory vault. Each tool wraps a
ClosedclawMemory method with input validation and consent handling.

Tools:
- search_memory: Semantic search over the vault
- write_memory: Propose storing a new memory (triggers consent for level >= 2)
- request_consent: Explicitly request consent for a sensitive memory
- reflect_on_memories: Synthesize memories around a topic
- get_memory_timeline: Chronological retrieval for a topic/tag
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL INPUT / OUTPUT SCHEMAS
# =============================================================================

class SearchMemoryInput(BaseModel):
    """Input for search_memory tool."""
    query: str = Field(..., description="Semantic search query")
    sensitivity_max: Optional[int] = Field(
        default=None, ge=0, le=3,
        description="Maximum sensitivity level to return (0-3). None returns all.",
    )
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags")
    limit: int = Field(default=5, ge=1, le=20, description="Max results")


class SearchMemoryOutput(BaseModel):
    """Output from search_memory tool."""
    memories: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    query: str = ""


class WriteMemoryInput(BaseModel):
    """Input for write_memory tool."""
    content: str = Field(..., description="Memory content to store", min_length=1)
    sensitivity: Optional[int] = Field(
        default=None, ge=0, le=3,
        description="Sensitivity level override. Auto-classified if None.",
    )
    tags: Optional[List[str]] = Field(default=None, description="Semantic tags")
    source: str = Field(default="conversation", description="Memory source")


class WriteMemoryOutput(BaseModel):
    """Output from write_memory tool."""
    memory_id: Optional[str] = None
    stored: bool = False
    consent_required: bool = False
    consent_request_id: Optional[str] = None
    sensitivity: int = 0
    message: str = ""


class RequestConsentInput(BaseModel):
    """Input for request_consent tool."""
    memory_id: str = Field(..., description="Memory ID to request consent for")
    reason: str = Field(
        ...,
        description="Why this memory is needed (shown to user)",
    )


class RequestConsentOutput(BaseModel):
    """Output from request_consent tool."""
    consent_request_id: str = ""
    status: str = ""  # pending, approved, denied
    message: str = ""


class ReflectInput(BaseModel):
    """Input for reflect_on_memories tool."""
    topic: str = Field(..., description="Topic to reflect on")
    sensitivity_max: Optional[int] = Field(
        default=2, ge=0, le=3,
        description="Max sensitivity for reflection",
    )


class ReflectOutput(BaseModel):
    """Output from reflect_on_memories tool."""
    reflection: str = ""
    memory_count: int = 0
    topic: str = ""


class TimelineInput(BaseModel):
    """Input for get_memory_timeline tool."""
    topic: str = Field(..., description="Topic or tag to retrieve timeline for")
    limit: int = Field(default=20, ge=1, le=100)


class TimelineOutput(BaseModel):
    """Output from get_memory_timeline tool."""
    entries: List[Dict[str, Any]] = Field(default_factory=list)
    topic: str = ""
    count: int = 0


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

class MemoryTools:
    """
    Collection of memory tools for the ClawdBot agent.

    Each method is a standalone tool that can be called by the LangGraph
    agent. All tools operate on the local memory vault.
    """

    def __init__(self, memory=None, user_id: str = "default", settings=None):
        self._memory = memory
        self._user_id = user_id
        self._settings = settings

    @property
    def memory(self):
        if self._memory is None:
            from closedclaw.api.core.memory import get_memory_instance
            self._memory = get_memory_instance()
        return self._memory

    @property
    def settings(self):
        if self._settings is None:
            from closedclaw.api.core.config import get_settings
            self._settings = get_settings()
        return self._settings

    # ---------------------------------------------------------------
    # search_memory
    # ---------------------------------------------------------------

    def search_memory(self, input: SearchMemoryInput) -> SearchMemoryOutput:
        """
        Semantic search over the local memory vault.

        Returns top-k chunks with sensitivity badges.
        """
        logger.info(f"search_memory: query='{input.query}', limit={input.limit}")

        try:
            result = self.memory.search(
                query=input.query,
                user_id=self._user_id,
                sensitivity_max=input.sensitivity_max,
                tags=input.tags,
                limit=input.limit,
            )

            memories = []
            for mem in result.get("results", []):
                memories.append({
                    "id": mem.get("id", ""),
                    "content": mem.get("memory", mem.get("content", "")),
                    "sensitivity": mem.get("sensitivity", 0),
                    "tags": mem.get("tags", []),
                    "score": mem.get("score", 0.0),
                    "consent_required": mem.get("consent_required", False),
                })

            return SearchMemoryOutput(
                memories=memories,
                count=len(memories),
                query=input.query,
            )
        except Exception as e:
            logger.error(f"search_memory failed: {e}")
            return SearchMemoryOutput(query=input.query)

    # ---------------------------------------------------------------
    # write_memory
    # ---------------------------------------------------------------

    def write_memory(self, input: WriteMemoryInput) -> WriteMemoryOutput:
        """
        Propose storing a new memory.

        Memories with sensitivity >= 2 trigger the consent flow.
        Low sensitivity memories (0-1) are stored immediately.
        """
        logger.info(f"write_memory: content='{input.content[:60]}...', tags={input.tags}")

        try:
            # First classify to determine consent needs
            sensitivity = self.memory._classify_sensitivity(
                input.content,
                input.tags,
                input.sensitivity,
            )

            consent_threshold = self.settings.require_consent_level

            if sensitivity >= consent_threshold:
                # Queue for consent via the persistent consent system
                logger.info(
                    f"write_memory: consent required (level={sensitivity}, threshold={consent_threshold})"
                )
                try:
                    from closedclaw.api.routes.consent import create_consent_request
                    pending = create_consent_request(
                        memory_id=f"pending-{uuid.uuid4().hex[:12]}",
                        memory_text=input.content,
                        sensitivity=sensitivity,
                        provider="clawdbot",
                        rule_triggered=f"sensitivity_level_{sensitivity}_requires_consent",
                    )
                    consent_id = pending.request_id
                except Exception as e:
                    logger.warning(f"Failed to create persistent consent request: {e}")
                    consent_id = str(uuid.uuid4())

                return WriteMemoryOutput(
                    stored=False,
                    consent_required=True,
                    consent_request_id=consent_id,
                    sensitivity=sensitivity,
                    message=(
                        f"Memory classified as sensitivity level {sensitivity}. "
                        f"User consent required before storage."
                    ),
                )

            # Store immediately for low sensitivity
            result = self.memory.add(
                content=input.content,
                user_id=self._user_id,
                sensitivity=input.sensitivity,
                tags=input.tags or [],
                source=input.source,
            )

            mem_id = None
            if result and "result" in result:
                results = result["result"].get("results", [])
                if results:
                    mem_id = results[0].get("id")

            return WriteMemoryOutput(
                memory_id=mem_id,
                stored=True,
                consent_required=False,
                sensitivity=sensitivity,
                message=f"Memory stored successfully (sensitivity={sensitivity}).",
            )
        except Exception as e:
            logger.error(f"write_memory failed: {e}")
            return WriteMemoryOutput(
                stored=False,
                message=f"Failed to store memory: {str(e)}",
            )

    # ---------------------------------------------------------------
    # request_consent
    # ---------------------------------------------------------------

    def request_consent(self, input: RequestConsentInput) -> RequestConsentOutput:
        """
        Explicitly request user consent for a specific memory.

        The agent calls this when it determines that sensitive context
        is needed and the user has not yet consented.
        """
        logger.info(
            f"request_consent: memory_id={input.memory_id}, reason='{input.reason[:60]}'"
        )

        # Check if memory exists
        mem = self.memory.get(input.memory_id)
        if mem is None:
            return RequestConsentOutput(
                status="error",
                message=f"Memory {input.memory_id} not found.",
            )

        # Create a consent request
        consent_id = str(uuid.uuid4())

        # In a full implementation, this would push to the consent WebSocket
        # and block until the user responds. For now we create the request
        # and return it as pending.
        try:
            from closedclaw.api.routes.consent import _pending_requests, _ensure_loaded
            from closedclaw.api.models.consent import ConsentPendingRequest

            _ensure_loaded()

            pending = ConsentPendingRequest(
                request_id=consent_id,
                memory_id=input.memory_id,
                memory_text=mem.get("memory", mem.get("content", "")),
                memory_hash=hashlib.sha256(
                    mem.get("memory", mem.get("content", "")).encode()
                ).hexdigest(),
                sensitivity=mem.get("sensitivity", 0),
                provider="clawdbot",
                redacted_text=None,
                rule_triggered=input.reason,
                expires_at=None,
                context={"agent": "clawdbot", "reason": input.reason},
            )
            _pending_requests[consent_id] = pending

            return RequestConsentOutput(
                consent_request_id=consent_id,
                status="pending",
                message=(
                    f"Consent request created. Waiting for user approval. "
                    f"Reason: {input.reason}"
                ),
            )
        except Exception as e:
            logger.error(f"request_consent failed: {e}")
            return RequestConsentOutput(
                status="error",
                message=str(e),
            )

    # ---------------------------------------------------------------
    # reflect_on_memories
    # ---------------------------------------------------------------

    def reflect_on_memories(self, input: ReflectInput) -> ReflectOutput:
        """
        Retrieve all memories tagged with a topic and synthesize a
        coherent summary, identifying recurring patterns and flagging
        contradictions.
        """
        logger.info(f"reflect_on_memories: topic='{input.topic}'")

        # Search for memories related to the topic
        results = self.memory.search(
            query=input.topic,
            user_id=self._user_id,
            sensitivity_max=input.sensitivity_max,
            limit=20,
        )
        memories = results.get("results", [])

        if not memories:
            return ReflectOutput(
                reflection=f"No memories found related to '{input.topic}'.",
                memory_count=0,
                topic=input.topic,
            )

        # Format memories for LLM
        memory_texts = []
        for i, mem in enumerate(memories, 1):
            content = mem.get("memory", mem.get("content", ""))
            tags = mem.get("tags", [])
            text = f"{i}. "
            if tags:
                text += f"[{', '.join(tags)}] "
            text += content
            memory_texts.append(text)

        context = "\n".join(memory_texts)

        prompt = (
            f"Reflect on the following memories about '{input.topic}'.\n\n"
            f"Memories:\n{context}\n\n"
            f"Provide:\n"
            f"1. A coherent summary of what is known about this topic\n"
            f"2. Any recurring patterns or themes\n"
            f"3. Any contradictions between memories\n"
            f"4. Key takeaways\n\n"
            f"Be factual and only reference what the memories contain."
        )

        try:
            from ollama import Client

            client = Client(host=self.settings.local_engine.ollama_base_url)
            from closedclaw.api.core.local import LOCAL_MODELS

            model_key = self.settings.local_engine.llm_model
            model = LOCAL_MODELS.get(model_key)
            model_name = model.ollama_model if model else model_key

            response = client.chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.4, "num_predict": 1500},
            )
            reflection = response["message"]["content"]
        except ImportError:
            # Fallback: generate a simple summary without LLM
            reflection = (
                f"Found {len(memories)} memories about '{input.topic}':\n\n"
                + "\n".join(
                    f"- {mem.get('memory', mem.get('content', ''))}"
                    for mem in memories[:10]
                )
            )
        except Exception as e:
            logger.error(f"Reflection LLM call failed: {e}")
            reflection = (
                f"Reflection failed ({e}). Found {len(memories)} related memories:\n\n"
                + "\n".join(
                    f"- {mem.get('memory', mem.get('content', ''))}"
                    for mem in memories[:10]
                )
            )

        return ReflectOutput(
            reflection=reflection,
            memory_count=len(memories),
            topic=input.topic,
        )

    # ---------------------------------------------------------------
    # get_memory_timeline
    # ---------------------------------------------------------------

    def get_memory_timeline(self, input: TimelineInput) -> TimelineOutput:
        """
        Retrieve memories for a topic ordered chronologically.

        Enables the agent to reason about how something has changed
        over time.
        """
        logger.info(f"get_memory_timeline: topic='{input.topic}'")

        results = self.memory.search(
            query=input.topic,
            user_id=self._user_id,
            limit=input.limit,
        )
        memories = results.get("results", [])

        # Build timeline entries — batch metadata lookup
        mem_ids = [m.get("id", "") for m in memories if m.get("id")]
        stored_batch: Dict[str, Dict] = {}
        if mem_ids:
            try:
                stored_batch = self.memory._store.load_memory_metadata_batch(mem_ids) or {}
            except Exception:
                stored_batch = {}

        entries = []
        for mem in memories:
            mem_id = mem.get("id", "")
            content = mem.get("memory", mem.get("content", ""))
            stored = stored_batch.get(mem_id, {})
            created = stored.get("created_at") or mem.get("created_at", "")

            entries.append({
                "id": mem_id,
                "content": content,
                "sensitivity": mem.get("sensitivity", 0),
                "tags": mem.get("tags", []),
                "created_at": created,
                "source": stored.get("source", "unknown"),
            })

        # Sort chronologically (oldest first)
        entries.sort(key=lambda e: e.get("created_at", ""))

        return TimelineOutput(
            entries=entries,
            topic=input.topic,
            count=len(entries),
        )

    # ---------------------------------------------------------------
    # TOOL REGISTRY
    # ---------------------------------------------------------------

    def get_tool_descriptions(self) -> List[Dict[str, str]]:
        """Return tool metadata descriptions for prompt construction."""
        return [
            {
                "name": "search_memory",
                "description": (
                    "Semantic search over the local memory vault. "
                    "Returns top-k chunks with sensitivity badges."
                ),
                "parameters": "query (str, required), sensitivity_max (int, 0-3), tags (list[str]), limit (int, 1-20)",
            },
            {
                "name": "write_memory",
                "description": (
                    "Propose storing a new memory. "
                    "Low sensitivity stored immediately; high sensitivity triggers consent."
                ),
                "parameters": "content (str, required), sensitivity (int, 0-3), tags (list[str]), source (str)",
            },
            {
                "name": "request_consent",
                "description": (
                    "Explicitly request user consent for a specific sensitive memory. "
                    "Call when sensitive context is needed."
                ),
                "parameters": "memory_id (str, required), reason (str, required)",
            },
            {
                "name": "reflect_on_memories",
                "description": (
                    "Retrieve all memories about a topic and synthesize a coherent "
                    "summary, identify patterns, and flag contradictions."
                ),
                "parameters": "topic (str, required), sensitivity_max (int, 0-3)",
            },
            {
                "name": "get_memory_timeline",
                "description": (
                    "Retrieve memories for a topic ordered chronologically. "
                    "Enables reasoning about how something changed over time."
                ),
                "parameters": "topic (str, required), limit (int, 1-100)",
            },
        ]
