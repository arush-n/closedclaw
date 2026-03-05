"""
NotionAgent — validates Notion operations with PII redaction.

1 LLM call to extract structured Notion intent.
Write operations (create/update) require explicit consent.
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

NOTION_INTENT_PROMPT = """Extract Notion operation details from this request. Redact any PII.

Request: {prompt}

Respond with JSON: {{"action": "search|get_page|create_page|update_page|list_databases|query_database", "query": "...", "page_id": "...", "title": "...", "content": "...", "database_id": "...", "contains_pii": false}}
JSON:"""


class NotionAgent(BaseAgent):
    AGENT_NAME = "notion"

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
            "action": "notion_access",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "violations": violations, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        raw = self._call_llm(
            NOTION_INTENT_PROMPT.format(prompt=prompt[:500]),
            temperature=0.1,
            max_tokens=400,
        )
        notion_data = self._parse_json_object(raw)

        action = notion_data.get("action", "search")
        consent_required = action in ("create_page", "update_page")

        self._store_working_memory(
            f"Notion: action={action} page='{notion_data.get('page_id', '')}' "
            f"consent_required={consent_required}",
            tags=["agent:notion", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "notion",
                "approved": True,
                "notion": notion_data,
                "consent_required": consent_required,
                "contains_pii": notion_data.get("contains_pii", False),
                "llm_calls": 1,
                "context_updates": {
                    "notion_data": notion_data,
                    "tool_type": "notion",
                    "consent_required": consent_required,
                },
            },
            in_reply_to=message.message_id,
        )
