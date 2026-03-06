"""
CalendarAgent — validates calendar operations and extracts event details.

1 LLM call to parse natural language into structured event data.
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

EVENT_PARSE_PROMPT = """Extract calendar event details from this request.

Request: {prompt}

Respond with JSON: {{"title": "...", "date": "YYYY-MM-DD", "time": "HH:MM", "duration_minutes": 60, "description": "...", "action": "create|query|delete"}}
JSON:"""


class CalendarAgent(BaseAgent):
    AGENT_NAME = "calendar"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        return await self._process_calendar(message, context)

    async def _process_calendar(
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
            "action": "calendar_access",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "violations": violations, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Parse event details via LLM
        raw = await self._call_llm(
            EVENT_PARSE_PROMPT.format(prompt=prompt[:500]),
            temperature=0.1,
            max_tokens=300,
        )
        event = self._parse_json_object(raw)

        self._store_working_memory(
            f"Calendar: action={event.get('action', 'unknown')} "
            f"title='{event.get('title', '')}'",
            tags=["agent:calendar", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "calendar",
                "approved": True,
                "event": event,
                "llm_calls": 1,
                "context_updates": {
                    "calendar_event": event,
                    "tool_type": "calendar",
                },
            },
            in_reply_to=message.message_id,
        )
