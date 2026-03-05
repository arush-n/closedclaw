"""
NotificationAgent — validates and routes user notifications.

0 LLM calls. Enforces rate limits and content filtering.
"""

import logging
import time
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

MAX_NOTIFICATIONS_PER_MINUTE = 5


class NotificationAgent(BaseAgent):
    AGENT_NAME = "notification"

    _recent_timestamps: list = []

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        return await self._validate_notification(message, context)

    async def _validate_notification(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        input_data = message.payload.get("input_data", {})
        title = input_data.get("title", "")
        body = input_data.get("body", "")
        priority = input_data.get("priority", "normal")

        if not title and not body:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "reason": "empty notification", "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Rate limiting
        now = time.time()
        self._recent_timestamps = [t for t in self._recent_timestamps if now - t < 60]
        if len(self._recent_timestamps) >= MAX_NOTIFICATIONS_PER_MINUTE:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "approved": False,
                    "reason": "rate_limited",
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Constitution check
        content = f"{title} {body}"
        violations = self._constitution.check_compliance({
            "content": content,
            "action": "notification",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "violations": violations, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        self._recent_timestamps.append(now)

        self._store_working_memory(
            f"Notification: title='{title[:50]}' priority={priority}",
            tags=["agent:notification", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "notification",
                "approved": True,
                "title": title,
                "body": body,
                "priority": priority,
                "llm_calls": 0,
                "context_updates": {
                    "notification_sent": True,
                    "tool_type": "notification",
                },
            },
            in_reply_to=message.message_id,
        )
