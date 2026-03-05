"""
BaseAgent — abstract base class for all swarm agents.

Provides:
  - LLM helper (Ollama via httpx, shared across agents)
  - Agent working memory namespace (persistent in mem0)
  - Message signing/verification
  - Reputation tracking
  - Memory-backed few-shot example retrieval
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from closedclaw.api.agents.swarm.bus import MessageBus
from closedclaw.api.agents.swarm.constitution import Constitution
from closedclaw.api.agents.swarm.crypto import AgentKeyring
from closedclaw.api.agents.swarm.models import AgentMessage, AgentStats

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all swarm agents."""

    AGENT_NAME: str = "base"

    def __init__(
        self,
        memory,  # ClosedclawMemory instance
        settings,  # Settings object
        constitution: Constitution,
        keyring: AgentKeyring,
        bus: MessageBus,
        tool_registry=None,  # Optional ToolRegistry for tool access
        coordinator=None,  # Optional SwarmCoordinator for delegation
    ):
        self._memory = memory
        self._settings = settings
        self._constitution = constitution
        self._keyring = keyring
        self._bus = bus
        self._tool_registry = tool_registry
        self._coordinator = coordinator
        self._stats = AgentStats(agent_id=self.AGENT_NAME)
        self._current_context: Dict[str, Any] = {}
        self._ollama_base: str = getattr(
            getattr(settings, "local_engine", None), "ollama_base_url", None
        ) or "http://localhost:11434"
        self._ollama_model: str = getattr(
            getattr(settings, "local_engine", None), "llm_model", None
        ) or "llama3.2:3b"

    # ── Abstract ──────────────────────────────────────────────────────

    @abstractmethod
    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Process an incoming message and return a signed response."""
        ...

    # ── LLM Helper ────────────────────────────────────────────────────

    def _call_llm(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 500,
        system: str = "",
    ) -> str:
        """Synchronous Ollama call. Returns raw text response.

        Uses httpx sync client to keep agent code simple. Each agent
        should make at most 1 LLM call per handle() invocation.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        url = f"{self._ollama_base}/api/chat"
        start = time.time()
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                elapsed = time.time() - start
                self._stats.total_llm_calls += 1
                tokens = data.get("eval_count", len(content) // 4)
                self._stats.total_tokens += tokens
                logger.debug(
                    "%s LLM call: %d tokens in %.1fs",
                    self.AGENT_NAME, tokens, elapsed,
                )
                return content.strip()
        except Exception as exc:
            logger.warning("%s LLM call failed: %s", self.AGENT_NAME, exc)
            self._stats.errors += 1
            return ""

    # ── Memory Namespace ──────────────────────────────────────────────

    @property
    def _agent_user_id(self) -> str:
        """Each agent stores working memories under its own namespace."""
        return f"agent:{self.AGENT_NAME}"

    def _store_working_memory(self, content: str, tags: Optional[List[str]] = None) -> None:
        """Store a working memory in the agent's namespace."""
        if not self._memory:
            return
        try:
            all_tags = [f"agent:{self.AGENT_NAME}", "agent:working_memory"]
            if tags:
                all_tags.extend(tags)
            self._memory.add(
                content=content,
                user_id=self._agent_user_id,
                sensitivity=0,
                tags=all_tags,
                source="swarm_agent",
            )
        except Exception as exc:
            logger.debug("%s working memory store failed: %s", self.AGENT_NAME, exc)

    def _search_working_memory(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Search this agent's working memories for few-shot examples."""
        if not self._memory:
            return []
        try:
            results = self._memory.search(
                query=query,
                user_id=self._agent_user_id,
                sensitivity_max=0,
                limit=limit,
            )
            if isinstance(results, dict):
                return results.get("results", [])
            return [r.model_dump() if hasattr(r, "model_dump") else vars(r) for r in results]
        except Exception:
            return []

    # ── Few-Shot Prompting ────────────────────────────────────────────

    def _build_few_shot_context(self, query: str, max_examples: int = 3) -> str:
        """Pull past decisions from working memory as few-shot examples."""
        examples = self._search_working_memory(query, limit=max_examples)
        if not examples:
            return ""
        lines = ["Here are examples of how you handled similar tasks before:"]
        for ex in examples:
            text = ex.get("memory", ex.get("content", ""))[:200]
            lines.append(f"  - {text}")
        return "\n".join(lines)

    # ── Signing ───────────────────────────────────────────────────────

    def _make_response(
        self,
        recipient: str,
        payload: Dict[str, Any],
        in_reply_to: Optional[str] = None,
    ) -> AgentMessage:
        """Create a signed response message."""
        msg = self._bus.create_message(
            sender=self.AGENT_NAME,
            recipient=recipient,
            message_type="result",
            payload=payload,
            in_reply_to=in_reply_to,
        )
        self._keyring.sign_message(msg, self.AGENT_NAME)
        self._stats.total_invocations += 1
        from datetime import datetime, timezone
        self._stats.last_active = datetime.now(timezone.utc)
        return msg

    # ── Tool Access ─────────────────────────────────────────────────

    def _call_tool(self, tool_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Call a registered tool. Validates permissions and tracks in stats."""
        if not self._tool_registry:
            logger.warning("%s: no tool registry, cannot call %s", self.AGENT_NAME, tool_name)
            return {"success": False, "error": "No tool registry configured"}

        context = {
            **self._current_context,
            "calling_agent": self.AGENT_NAME,
            "memory": self._memory,
            "settings": self._settings,
            "constitution": self._constitution,
            "keyring": self._keyring,
            "coordinator": self._coordinator,
        }
        result = self._tool_registry.execute(
            tool_name=tool_name,
            input_data=input_data,
            agent_name=self.AGENT_NAME,
            context=context,
        )
        self._stats.total_tool_calls += 1
        return result

    @property
    def available_tools(self) -> List[str]:
        """List tool names available to this agent."""
        if not self._tool_registry:
            return []
        return self._tool_registry.get_agent_tool_names(self.AGENT_NAME)

    # ── Reputation ────────────────────────────────────────────────────

    def adjust_reputation(self, delta: float) -> None:
        """Adjust reputation score. Clamped to [0.0, 1.0]."""
        self._stats.reputation = max(0.0, min(1.0, self._stats.reputation + delta))

    @property
    def stats(self) -> AgentStats:
        return self._stats

    # ── JSON Parsing Helpers ──────────────────────────────────────────

    @staticmethod
    def _parse_json_array(text: str) -> List[Dict[str, Any]]:
        """Extract a JSON array from LLM output (handles markdown fences)."""
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        # Find array bounds
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return []

    @staticmethod
    def _parse_json_object(text: str) -> Dict[str, Any]:
        """Extract a JSON object from LLM output."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return {}
