"""
Injector Agent — builds the system prompt prefix for every request.

Pure rule assembly, NO LLM calls. Reads the constitution's active
principles and any memory-context assembled by earlier pipeline stages,
then emits a structured system prefix that gets prepended to the user's
prompt before it reaches the target AI provider.

Responsibilities:
  - Load active rules from Constitution
  - Load user memory rules (from context assembled by AccessorAgent)
  - Build system prompt prefix with context, rules, and metadata
  - Stamp user_id, provider, and session metadata
"""

import logging
from typing import Any, Dict, List

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)


class InjectorAgent(BaseAgent):
    AGENT_NAME = "injector"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        action = message.payload.get(
            "action", message.payload.get("input_data", {}).get("action", "inject")
        )

        if action == "inject":
            return await self._build_injection(message, context)
        return await self._build_injection(message, context)

    async def _build_injection(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        """Assemble the system prompt prefix from rules + memory context (0 LLM calls)."""
        user_id = context.get("user_id", "default")
        provider = context.get("provider", "ollama")
        context_text = context.get("context_text", "")
        permitted_memories = context.get("permitted_memories", [])

        # Gather active constitutional principles
        rules = self._get_active_rules()

        # Build the prefix
        prefix_parts: List[str] = []

        # Session header
        prefix_parts.append(f"[SYSTEM: Memory-enabled session for user {user_id}]")
        prefix_parts.append(f"[PROVIDER: {provider}]")

        # Active rules (compact form)
        for rule in rules[:10]:
            prefix_parts.append(f"[RULE: {rule}]")

        # Memory context (from governance-approved memories)
        if context_text:
            # Trim to a reasonable size for context injection
            trimmed = context_text[:2000]
            prefix_parts.append(f"[MEMORY CONTEXT]\n{trimmed}\n[/MEMORY CONTEXT]")
        elif permitted_memories:
            # Build from individual memories if context_text wasn't assembled
            mem_lines = []
            for m in permitted_memories[:8]:
                text = (
                    m.get("memory", m.get("content", ""))
                    if isinstance(m, dict)
                    else str(m)
                )
                mem_lines.append(f"- {text[:200]}")
            if mem_lines:
                prefix_parts.append(
                    "[MEMORY CONTEXT]\n" + "\n".join(mem_lines) + "\n[/MEMORY CONTEXT]"
                )

        # Firewall summary (if governance ran before us)
        firewall = context.get("firewall_decision")
        if isinstance(firewall, dict):
            blocked = firewall.get("blocked_count", 0)
            redacted = firewall.get("redaction_count", 0)
            if blocked or redacted:
                prefix_parts.append(
                    f"[PRIVACY: {blocked} memories blocked, {redacted} redactions applied]"
                )

        system_prefix = "\n".join(prefix_parts)

        # Store injection record for few-shot
        self._store_working_memory(
            f"Injected {len(rules)} rules + {len(context_text)} chars context "
            f"for user={user_id} provider={provider}",
            tags=["agent:injector", "injection_log"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "system_prefix": system_prefix,
                "active_rules": rules,
                "injected_context_len": len(context_text),
                "rules_count": len(rules),
                "llm_calls": 0,
                "context_updates": {
                    "system_prefix": system_prefix,
                    "active_rules": rules,
                },
            },
            in_reply_to=message.message_id,
        )

    def _get_active_rules(self) -> List[str]:
        """Extract compact rule strings from the constitution's principles."""
        rules = []
        for p in self._constitution.principles:
            if p.enforcement == "strict":
                rules.append(f"{p.name}: {p.description}")
        return rules
