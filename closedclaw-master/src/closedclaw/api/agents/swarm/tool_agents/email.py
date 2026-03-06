"""
EmailAgent — validates email operations with PII redaction.

1 LLM call to extract structured email intent and redact sensitive content.
Requires explicit consent for sending (sensitivity >= 2).
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

EMAIL_INTENT_PROMPT = """Extract email details from this request. Redact any PII (social security, credit card, passwords).

Request: {prompt}

Respond with JSON: {{"action": "send|read|search", "to": "...", "subject": "...", "body": "...", "contains_pii": false}}
JSON:"""


class EmailAgent(BaseAgent):
    AGENT_NAME = "email"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        return await self._process_email(message, context)

    async def _process_email(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
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
            "action": "email_access",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "violations": violations, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Parse email intent via LLM
        raw = await self._call_llm(
            EMAIL_INTENT_PROMPT.format(prompt=prompt[:500]),
            temperature=0.1,
            max_tokens=400,
        )
        email_data = self._parse_json_object(raw)

        action = email_data.get("action", "read")

        # Sending requires consent
        consent_required = action == "send"

        self._store_working_memory(
            f"Email: action={action} to='{email_data.get('to', '')}' "
            f"consent_required={consent_required}",
            tags=["agent:email", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "email",
                "approved": True,
                "email": email_data,
                "consent_required": consent_required,
                "contains_pii": email_data.get("contains_pii", False),
                "llm_calls": 1,
                "context_updates": {
                    "email_data": email_data,
                    "tool_type": "email",
                    "consent_required": consent_required,
                },
            },
            in_reply_to=message.message_id,
        )
