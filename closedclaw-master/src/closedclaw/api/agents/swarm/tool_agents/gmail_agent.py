"""
GmailAgent — validates Gmail operations with PII redaction.

1 LLM call to extract structured email intent.
Send operations require explicit consent (sensitivity >= 2).
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

GMAIL_INTENT_PROMPT = """Extract Gmail operation details from this request. Redact any PII (social security, credit card, passwords).

Request: {prompt}

Respond with JSON: {{"action": "send|read|search|labels", "to": "...", "subject": "...", "query": "...", "body": "...", "contains_pii": false}}
JSON:"""


class GmailAgent(BaseAgent):
    AGENT_NAME = "gmail"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        input_data = message.payload.get("input_data", {})
        prompt = input_data.get("prompt", "")

        if not prompt:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "reason": "empty request", "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Constitution check
        violations = self._constitution.check_compliance({
            "content": prompt,
            "action": "gmail_access",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "violations": violations, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Parse intent via LLM
        raw = await self._call_llm(
            GMAIL_INTENT_PROMPT.format(prompt=prompt[:500]),
            temperature=0.1,
            max_tokens=400,
        )
        gmail_data = self._parse_json_object(raw)

        action = gmail_data.get("action", "read")
        consent_required = action == "send"

        self._store_working_memory(
            f"Gmail: action={action} to='{gmail_data.get('to', '')}' "
            f"consent_required={consent_required}",
            tags=["agent:gmail", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "gmail",
                "approved": True,
                "gmail": gmail_data,
                "consent_required": consent_required,
                "contains_pii": gmail_data.get("contains_pii", False),
                "llm_calls": 1,
                "context_updates": {
                    "gmail_data": gmail_data,
                    "tool_type": "gmail",
                    "consent_required": consent_required,
                },
            },
            in_reply_to=message.message_id,
        )
