"""
SlackAgent — validates Slack operations with PII redaction.

1 LLM call to extract structured Slack intent.
Message sending requires explicit consent.
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

SLACK_INTENT_PROMPT = """Extract Slack operation details from this request. Redact any PII.

Request: {prompt}

Respond with JSON: {{"action": "list_channels|search|history|send|user_info", "channel": "...", "query": "...", "message": "...", "user_id": "...", "contains_pii": false}}
JSON:"""


class SlackAgent(BaseAgent):
    AGENT_NAME = "slack"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        input_data = message.payload.get("input_data", {})
        prompt = input_data.get("prompt", "")

        if not prompt:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "reason": "empty request", "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        violations = self._constitution.check_compliance({
            "content": prompt,
            "action": "slack_access",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "violations": violations, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        raw = self._call_llm(
            SLACK_INTENT_PROMPT.format(prompt=prompt[:500]),
            temperature=0.1,
            max_tokens=400,
        )
        slack_data = self._parse_json_object(raw)

        action = slack_data.get("action", "search")
        consent_required = action == "send"

        self._store_working_memory(
            f"Slack: action={action} channel='{slack_data.get('channel', '')}' "
            f"consent_required={consent_required}",
            tags=["agent:slack", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "slack",
                "approved": True,
                "slack": slack_data,
                "consent_required": consent_required,
                "contains_pii": slack_data.get("contains_pii", False),
                "llm_calls": 1,
                "context_updates": {
                    "slack_data": slack_data,
                    "tool_type": "slack",
                    "consent_required": consent_required,
                },
            },
            in_reply_to=message.message_id,
        )
