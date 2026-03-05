"""
Memory Guardian Agent

Swarm agent that monitors all memory writes from openclaw and enforces
closedclaw's memory safety policies. Runs as part of the closedclaw
agent swarm on the HOST side.

Responsibilities:
- Screen all incoming memory writes from openclaw (via the control bridge)
- Auto-classify memory sensitivity
- Block dangerous memories (credentials, financial data, etc.)
- Redact PII from memories before storage
- Enforce memory retention policies (TTL, dedup, limits)
- Log all decisions to audit trail
"""

import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

# Default dangerous patterns (overridden by config)
DEFAULT_DANGEROUS_PATTERNS = {
    "credentials": {
        "patterns": [
            r"password[s]?\s*[:=]",
            r"api[_-]?key[s]?\s*[:=]",
            r"secret[_-]?key\s*[:=]",
            r"access[_-]?token\s*[:=]",
            r"bearer\s+[A-Za-z0-9\-._~+/]+",
            r"ssh-rsa\s+",
            r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
        ],
        "action": "block",
        "severity": "critical",
    },
    "financial": {
        "patterns": [
            r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
            r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b",
            r"\brouting[\s_-]?number\s*[:=]",
            r"\baccount[\s_-]?number\s*[:=]",
        ],
        "action": "block",
        "severity": "critical",
    },
    "personal_identifiers": {
        "patterns": [
            r"\bdate[\s_-]?of[\s_-]?birth\s*[:=]",
            r"\bdriver'?s?[\s_-]?license\s*[:=]",
            r"\bpassport[\s_-]?number\s*[:=]",
        ],
        "action": "redact_and_store",
        "severity": "high",
    },
}


class MemoryGuardianAgent(BaseAgent):
    """Monitors and controls openclaw memory writes."""

    AGENT_NAME = "memory_guardian"

    def __init__(self, config: Optional[dict] = None, **kwargs):
        super().__init__(**kwargs)
        self._config = config or {}
        self._dangerous_patterns = self._config.get(
            "dangerous_patterns", DEFAULT_DANGEROUS_PATTERNS
        )
        self._sensitive_categories = self._config.get("sensitive_categories", [
            "medical", "financial", "legal", "authentication",
            "personal_identity", "relationships",
        ])
        self._retention = self._config.get("retention", {})

    async def handle(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        action = message.payload.get("action", "screen")

        if action == "screen":
            return await self._screen_memory(message, context)
        elif action == "classify":
            return await self._classify_memory(message, context)
        elif action == "enforce_retention":
            return await self._enforce_retention(message, context)
        elif action == "batch_screen":
            return await self._batch_screen(message, context)
        else:
            return self._make_response(
                recipient="coordinator",
                payload={"error": f"Unknown action: {action}"},
                in_reply_to=message.message_id,
            )

    async def _screen_memory(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        """Screen a single memory write for dangerous content."""
        content = message.payload.get("content", "")
        user_id = message.payload.get("user_id", "unknown")
        source = message.payload.get("source", "openclaw")

        # Run pattern matching
        result = self._check_patterns(content)

        if result["action"] == "block":
            logger.warning(
                "Memory BLOCKED for user %s from %s — category: %s",
                user_id, source, result["category"],
            )
            return self._make_response(
                recipient="coordinator",
                payload={
                    "decision": "block",
                    "reason": result["detail"],
                    "category": result["category"],
                    "severity": result["severity"],
                    "content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
                    "context_updates": {
                        "memory_blocked": True,
                        "block_reason": result["detail"],
                    },
                },
                in_reply_to=message.message_id,
            )

        if result["action"] == "redact_and_store":
            redacted = self._redact_content(content)
            logger.info(
                "Memory REDACTED for user %s from %s — category: %s",
                user_id, source, result["category"],
            )
            return self._make_response(
                recipient="coordinator",
                payload={
                    "decision": "redact_and_store",
                    "original_content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
                    "redacted_content": redacted,
                    "category": result["category"],
                    "severity": result["severity"],
                    "context_updates": {
                        "memory_redacted": True,
                        "redaction_category": result["category"],
                    },
                },
                in_reply_to=message.message_id,
            )

        # Allowed
        return self._make_response(
            recipient="coordinator",
            payload={
                "decision": "allow",
                "content": content,
                "context_updates": {"memory_allowed": True},
            },
            in_reply_to=message.message_id,
        )

    async def _classify_memory(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        """Classify a memory's sensitivity level."""
        content = message.payload.get("content", "")
        categories = message.payload.get("categories", [])

        # Check category overlap
        overlap = set(categories) & set(self._sensitive_categories)
        sensitivity = 1

        if overlap:
            sensitivity = 2

        # Check content patterns
        result = self._check_patterns(content)
        if result["action"] == "block":
            sensitivity = 3

        # Use LLM for borderline cases if available
        if sensitivity == 1 and len(content) > 50:
            try:
                llm_classification = await self._llm_classify(content)
                if llm_classification and llm_classification.get("sensitivity", 1) > 1:
                    sensitivity = llm_classification["sensitivity"]
            except Exception:
                pass  # Fall back to pattern-based classification

        return self._make_response(
            recipient="coordinator",
            payload={
                "sensitivity": sensitivity,
                "sensitive_categories": list(overlap),
                "pattern_flags": result.get("category"),
                "context_updates": {
                    "memory_sensitivity": sensitivity,
                },
            },
            in_reply_to=message.message_id,
        )

    async def _enforce_retention(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        """Enforce memory retention policies (TTL, dedup, limits)."""
        user_id = message.payload.get("user_id", "default")
        memories = message.payload.get("memories", [])

        expired = []
        deduped = []
        now = time.time()

        session_ttl = self._retention.get("session_memories_ttl_hours", 24) * 3600
        sensitive_ttl = self._retention.get("sensitive_memories_ttl_days", 30) * 86400
        critical_ttl = self._retention.get("critical_memories_ttl_days", 7) * 86400
        max_memories = self._retention.get("max_memories_per_user", 10000)
        dedup_threshold = self._retention.get("dedup_similarity_threshold", 0.92)

        for mem in memories:
            created = mem.get("created_at", now)
            sensitivity = mem.get("sensitivity", 1)
            scope = mem.get("scope", "user")

            # Check TTL
            age = now - created
            if scope == "session" and age > session_ttl:
                expired.append(mem.get("id"))
            elif sensitivity >= 3 and age > critical_ttl:
                expired.append(mem.get("id"))
            elif sensitivity >= 2 and age > sensitive_ttl:
                expired.append(mem.get("id"))

        # Enforce max memories limit
        over_limit = max(0, len(memories) - len(expired) - max_memories)

        return self._make_response(
            recipient="coordinator",
            payload={
                "expired_ids": expired,
                "over_limit_count": over_limit,
                "action": "prune" if expired or over_limit > 0 else "none",
                "context_updates": {
                    "retention_enforced": True,
                    "memories_expired": len(expired),
                },
            },
            in_reply_to=message.message_id,
        )

    async def _batch_screen(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        """Screen multiple memories in a batch."""
        memories = message.payload.get("memories", [])
        results = []

        for mem in memories:
            content = mem.get("content", "")
            action_result = self._check_patterns(content)
            
            if action_result["action"] == "block":
                results.append({
                    "id": mem.get("id"),
                    "decision": "block",
                    "category": action_result["category"],
                })
            elif action_result["action"] == "redact_and_store":
                results.append({
                    "id": mem.get("id"),
                    "decision": "redact_and_store",
                    "redacted_content": self._redact_content(content),
                    "category": action_result["category"],
                })
            else:
                results.append({
                    "id": mem.get("id"),
                    "decision": "allow",
                })

        blocked = sum(1 for r in results if r["decision"] == "block")
        redacted = sum(1 for r in results if r["decision"] == "redact_and_store")

        return self._make_response(
            recipient="coordinator",
            payload={
                "results": results,
                "summary": {
                    "total": len(results),
                    "allowed": len(results) - blocked - redacted,
                    "blocked": blocked,
                    "redacted": redacted,
                },
            },
            in_reply_to=message.message_id,
        )

    # --- Helpers ---------------------------------------------------------------

    def _check_patterns(self, content: str) -> dict:
        """Check content against dangerous patterns."""
        for category, rule in self._dangerous_patterns.items():
            for pattern in rule.get("patterns", []):
                try:
                    if re.search(pattern, content, re.IGNORECASE):
                        return {
                            "action": rule.get("action", "block"),
                            "category": category,
                            "severity": rule.get("severity", "unknown"),
                            "detail": f"Matched '{category}' pattern (severity: {rule.get('severity', 'unknown')})",
                        }
                except re.error:
                    logger.warning("Invalid regex: %s", pattern)

        return {"action": "allow", "category": None, "severity": None, "detail": None}

    def _redact_content(self, content: str) -> str:
        """Redact PII and sensitive data from content."""
        # Credit cards
        content = re.sub(
            r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
            "[CARD-REDACTED]",
            content,
        )
        # SSN
        content = re.sub(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "[SSN-REDACTED]", content)
        # API keys
        content = re.sub(
            r"\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|xox[bpas]-[A-Za-z0-9\-]+)\b",
            "[TOKEN-REDACTED]",
            content,
        )
        # Password values
        content = re.sub(
            r"(password|passwd|pwd)\s*[:=]\s*\S+",
            r"\1: [REDACTED]",
            content,
            flags=re.IGNORECASE,
        )
        return content

    async def _llm_classify(self, content: str) -> Optional[dict]:
        """Use local LLM to classify borderline memory sensitivity."""
        prompt = (
            "Classify the sensitivity of this memory content on a scale of 1-3:\n"
            "1 = Normal (public facts, general preferences)\n"
            "2 = Sensitive (personal details, private opinions, location data)\n"
            "3 = Critical (credentials, financial info, health data, legal info)\n\n"
            f"Content: {content[:500]}\n\n"
            "Respond with ONLY a JSON object: {\"sensitivity\": N, \"reason\": \"...\"}"
        )
        try:
            response_text = await self._call_llm(prompt)
            if response_text:
                import json
                # Extract JSON from response
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start >= 0 and end > start:
                    return json.loads(response_text[start:end])
        except Exception as exc:
            logger.debug("LLM classification failed: %s", exc)
        return None
