"""
BrowserAgent — validates browser automation requests.

0 LLM calls. Validates URLs against constitution allowed domains
and blocked patterns.
"""

import logging
from urllib.parse import urlparse
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

BLOCKED_SCHEMES = frozenset({"file", "ftp", "data", "javascript"})


class BrowserAgent(BaseAgent):
    AGENT_NAME = "browser"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        return await self._validate_navigation(message, context)

    async def _validate_navigation(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        input_data = message.payload.get("input_data", {})
        url = input_data.get("url", "")
        action = input_data.get("action", "navigate")

        if not url:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "reason": "empty url", "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Parse and validate URL
        parsed = urlparse(url)

        if parsed.scheme in BLOCKED_SCHEMES:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "approved": False,
                    "reason": "blocked_scheme",
                    "scheme": parsed.scheme,
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        if not parsed.hostname:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "reason": "invalid_url", "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Block localhost/internal for non-Openclaw requests
        if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            if parsed.port != 8765:
                return self._make_response(
                    recipient="coordinator",
                    payload={
                        "approved": False,
                        "reason": "blocked_internal",
                        "llm_calls": 0,
                    },
                    in_reply_to=message.message_id,
                )

        # Constitution check
        violations = self._constitution.check_compliance({
            "content": url,
            "action": f"browser_{action}",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "violations": violations, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        self._store_working_memory(
            f"Browser: action={action} url={parsed.hostname}",
            tags=["agent:browser", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "browser",
                "approved": True,
                "url": url,
                "action": action,
                "hostname": parsed.hostname,
                "llm_calls": 0,
                "context_updates": {
                    "browser_url": url,
                    "tool_type": "browser",
                },
            },
            in_reply_to=message.message_id,
        )
