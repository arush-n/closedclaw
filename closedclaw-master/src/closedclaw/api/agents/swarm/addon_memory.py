"""
Addon Memory Agent — copyright attribution and contextual memory requests.

Handles memory operations originating from the browser addon:
  - Tag memories that came from copyrighted sources
  - Decide whether to cite or suppress source in responses
  - Trigger consent if new memory capture is detected
  - Manage copyright registry checks

0 LLM calls for standard flow; 1 LLM call for copyright ambiguity resolution.
"""

import logging
from typing import Any, Dict, List

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

# Known copyright-sensitive source patterns
COPYRIGHT_SOURCE_PATTERNS = frozenset({
    "news", "article", "paper", "journal", "book",
    "publication", "magazine", "report", "study",
})


class AddonMemoryAgent(BaseAgent):
    AGENT_NAME = "addon_memory"

    COPYRIGHT_RESOLVE_PROMPT = """A memory may contain copyrighted content. Determine the appropriate action.

Memory content: {content}
Source: {source}
Tags: {tags}

Respond with JSON: {{"action": "cite|suppress|permit", "reason": "...", "citation": "..."}}
- "cite": include attribution in the response
- "suppress": do not use this memory in context
- "permit": use freely (not copyrighted)

JSON:"""

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        action = message.payload.get(
            "action", message.payload.get("input_data", {}).get("action", "process")
        )

        if action == "process":
            return await self._process_memories(message, context)
        elif action == "capture":
            return await self._handle_capture(message, context)
        return await self._process_memories(message, context)

    async def _process_memories(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        """Scan retrieved memories for copyright flags and build citations (0-1 LLM calls)."""
        permitted_memories = context.get("permitted_memories", [])

        if not permitted_memories:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "copyright_citations": [],
                    "suppressed_count": 0,
                    "consent_required": False,
                    "llm_calls": 0,
                    "context_updates": {
                        "copyright_citations": [],
                        "addon_memory_processed": True,
                    },
                },
                in_reply_to=message.message_id,
            )

        citations: List[Dict[str, str]] = []
        suppressed: List[Dict[str, Any]] = []
        clean_memories: List[Dict[str, Any]] = []
        llm_calls = 0

        for mem in permitted_memories:
            if not isinstance(mem, dict):
                clean_memories.append(mem)
                continue

            source = mem.get("source", "")
            tags = mem.get("tags", [])

            # Check if memory has copyright indicators
            if self._is_copyright_flagged(source, tags, mem.get("content", "")):
                # Try deterministic resolution first
                resolution = self._deterministic_copyright_check(source, tags)

                if resolution is None and llm_calls == 0:
                    # Ambiguous — use LLM (max 1 call per invocation)
                    resolution = self._llm_copyright_check(mem)
                    llm_calls += 1

                if resolution is None:
                    # Default: cite
                    resolution = {"action": "cite", "reason": "default", "citation": source}

                if resolution["action"] == "suppress":
                    suppressed.append(mem)
                    continue
                elif resolution["action"] == "cite":
                    citations.append({
                        "memory_id": mem.get("id", "unknown"),
                        "source": source,
                        "citation": resolution.get("citation", source),
                    })

            clean_memories.append(mem)

        # Update context with cleaned memory list
        return self._make_response(
            recipient="coordinator",
            payload={
                "copyright_citations": citations,
                "suppressed_count": len(suppressed),
                "clean_memory_count": len(clean_memories),
                "consent_required": False,
                "llm_calls": llm_calls,
                "context_updates": {
                    "copyright_citations": citations,
                    "permitted_memories": clean_memories,
                    "addon_memory_processed": True,
                },
            },
            in_reply_to=message.message_id,
        )

    async def _handle_capture(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        """Handle an explicit memory capture request from the addon.

        Delegates to MakerAgent for extraction and checks if consent is needed.
        """
        input_data = message.payload.get("input_data", {})
        content = input_data.get("content", "")
        source = input_data.get("source", "addon")
        sensitivity = input_data.get("sensitivity", 1)

        if not content:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "stored": False,
                    "reason": "empty content",
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Check constitution: is storage allowed?
        violations = self._constitution.check_compliance({
            "content": content,
            "sensitivity": sensitivity,
            "provider": context.get("provider", "ollama"),
        })

        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "stored": False,
                    "reason": "constitution_violation",
                    "violations": violations,
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Check if consent is required for this sensitivity
        consent_required = (
            self._constitution.schema.require_consent_for_storage
            and sensitivity >= 2
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "stored": not consent_required,
                "consent_required": consent_required,
                "content_length": len(content),
                "source": source,
                "sensitivity": sensitivity,
                "llm_calls": 0,
                "context_updates": {
                    "capture_content": content if not consent_required else None,
                    "capture_source": source,
                    "capture_consent_required": consent_required,
                },
            },
            in_reply_to=message.message_id,
        )

    @staticmethod
    def _is_copyright_flagged(source: str, tags: List[str], content: str) -> bool:
        """Check if a memory has indicators of copyrighted content."""
        source_lower = source.lower()
        if any(p in source_lower for p in COPYRIGHT_SOURCE_PATTERNS):
            return True
        if any("copyright" in t.lower() or "source:" in t.lower() for t in tags):
            return True
        # Check for common citation patterns in content
        if "©" in content or "all rights reserved" in content.lower():
            return True
        return False

    @staticmethod
    def _deterministic_copyright_check(
        source: str, tags: List[str]
    ) -> dict | None:
        """Try to resolve copyright deterministically without LLM.

        Returns resolution dict or None if ambiguous.
        """
        source_lower = source.lower()

        # User's own content is always permitted
        if source_lower in ("user", "addon", "manual", "self", "chat"):
            return {"action": "permit", "reason": "user-generated content"}

        # Known open sources
        if any(k in source_lower for k in ("wikipedia", "public domain", "creative commons", "cc-by")):
            return {"action": "permit", "reason": "open-licensed source"}

        # Explicit copyright tags → cite
        if any("copyright" in t.lower() for t in tags):
            return {"action": "cite", "reason": "explicit copyright tag", "citation": source}

        # News/article sources → cite
        if any(p in source_lower for p in ("news", "article", "paper", "journal")):
            return {"action": "cite", "reason": "likely published content", "citation": source}

        return None  # Ambiguous — needs LLM

    def _llm_copyright_check(self, memory: Dict[str, Any]) -> dict | None:
        """Use LLM to resolve copyright ambiguity (1 call)."""
        content = memory.get("content", memory.get("memory", ""))[:500]
        source = memory.get("source", "unknown")
        tags = memory.get("tags", [])

        prompt = self.COPYRIGHT_RESOLVE_PROMPT.format(
            content=content,
            source=source,
            tags=", ".join(tags[:10]),
        )
        raw = self._call_llm(prompt, temperature=0.1, max_tokens=200)
        result = self._parse_json_object(raw)

        if result.get("action") in ("cite", "suppress", "permit"):
            return result
        return None
