"""
DriveAgent — validates Google Drive operations with PII redaction.

1 LLM call to extract structured Drive intent.
Upload operations require explicit consent.
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

DRIVE_INTENT_PROMPT = """Extract Google Drive operation details from this request. Redact any PII.

Request: {prompt}

Respond with JSON: {{"action": "list|search|get_metadata|get_content|upload", "query": "...", "file_id": "...", "folder_id": "...", "file_name": "...", "contains_pii": false}}
JSON:"""


class DriveAgent(BaseAgent):
    AGENT_NAME = "drive"

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
            "action": "drive_access",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "violations": violations, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        raw = await self._call_llm(
            DRIVE_INTENT_PROMPT.format(prompt=prompt[:500]),
            temperature=0.1,
            max_tokens=400,
        )
        drive_data = self._parse_json_object(raw)

        action = drive_data.get("action", "list")
        consent_required = action == "upload"

        self._store_working_memory(
            f"Drive: action={action} file='{drive_data.get('file_id', '')}' "
            f"consent_required={consent_required}",
            tags=["agent:drive", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "drive",
                "approved": True,
                "drive": drive_data,
                "consent_required": consent_required,
                "contains_pii": drive_data.get("contains_pii", False),
                "llm_calls": 1,
                "context_updates": {
                    "drive_data": drive_data,
                    "tool_type": "drive",
                    "consent_required": consent_required,
                },
            },
            in_reply_to=message.message_id,
        )
