"""
Processor Agent — secondary redaction and context sanitization.

The last pass before context leaves the server. Applies provider-specific
PII redaction rules to the assembled context_text and system_prefix.

NO LLM calls — pure PIIRedactor pipeline.

Responsibilities:
  - Apply PIIRedactor.redact_for_provider() on assembled context_text
  - Apply PIIRedactor on system_prefix if provider is cloud
  - Build final sanitized_context for the response
  - Return redaction_summary for audit trail
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)


class ProcessorAgent(BaseAgent):
    AGENT_NAME = "processor"
    MODEL_TIER = "none"  # No LLM — pure PIIRedactor pipeline

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        action = message.payload.get(
            "action", message.payload.get("input_data", {}).get("action", "redact")
        )

        if action == "redact":
            return await self._secondary_redaction(message, context)
        return await self._secondary_redaction(message, context)

    async def _secondary_redaction(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        """Apply provider-specific PII redaction to assembled context (0 LLM calls)."""
        provider = context.get("provider", "ollama")
        context_text = context.get("context_text", "")
        system_prefix = context.get("system_prefix", "")

        total_redactions = 0
        total_blocked = 0
        redacted_context = context_text
        redacted_prefix = system_prefix

        try:
            from closedclaw.api.privacy.redactor import PIIRedactor

            redactor = PIIRedactor()

            # Redact context_text
            if context_text:
                result = redactor.redact_for_provider(context_text, provider=provider)
                redacted_context = result.redacted_text
                total_redactions += result.redaction_count
                total_blocked += result.blocked_count

            # Redact system_prefix for cloud providers
            is_cloud = provider.lower() not in ("ollama", "local", "llama")
            if system_prefix and is_cloud:
                result = redactor.redact_for_provider(system_prefix, provider=provider)
                redacted_prefix = result.redacted_text
                total_redactions += result.redaction_count
                total_blocked += result.blocked_count

        except ImportError:
            logger.warning("PIIRedactor not available — skipping secondary redaction")
        except Exception as exc:
            logger.warning("Secondary redaction failed: %s", exc)

        # Build final sanitized output
        sanitized_context = redacted_context
        if redacted_prefix and redacted_context:
            sanitized_context = redacted_prefix + "\n\n" + redacted_context
        elif redacted_prefix:
            sanitized_context = redacted_prefix

        # Log for audit
        if total_redactions or total_blocked:
            self._store_working_memory(
                f"Secondary redaction for provider={provider}: "
                f"{total_redactions} redactions, {total_blocked} blocked entities",
                tags=["agent:processor", "redaction_log"],
            )

        return self._make_response(
            recipient="coordinator",
            payload={
                "sanitized_context": sanitized_context,
                "redacted_context_text": redacted_context,
                "redacted_system_prefix": redacted_prefix,
                "total_redactions": total_redactions,
                "total_blocked": total_blocked,
                "provider": provider,
                "is_cloud": provider.lower() not in ("ollama", "local", "llama"),
                "llm_calls": 0,
                "context_updates": {
                    "context_text": redacted_context,
                    "system_prefix": redacted_prefix,
                    "sanitized_context": sanitized_context,
                    "processor_redaction_count": total_redactions,
                    "processor_blocked_count": total_blocked,
                },
            },
            in_reply_to=message.message_id,
        )
