"""
WebSearchAgent — validates, sanitizes, and executes web search tool calls.

1 LLM call to extract structured search intent from the user prompt.
Checks constitution for allowed search domains and blocked topics.
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

SEARCH_INTENT_PROMPT = """Extract a structured web search query from the user's request.

User request: {prompt}

Respond with JSON: {{"query": "...", "domains": [], "max_results": 5, "safe_search": true}}
JSON:"""


class WebSearchAgent(BaseAgent):
    AGENT_NAME = "web_search"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        action = message.payload.get(
            "action", message.payload.get("input_data", {}).get("action", "search")
        )

        if action == "search":
            return await self._execute_search(message, context)
        return await self._execute_search(message, context)

    async def _execute_search(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        input_data = message.payload.get("input_data", {})
        prompt = input_data.get("prompt", input_data.get("query", ""))

        if not prompt:
            return self._make_response(
                recipient="coordinator",
                payload={"results": [], "error": "empty query", "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Check constitution for blocked topics
        violations = self._constitution.check_compliance({
            "content": prompt,
            "action": "web_search",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "results": [],
                    "blocked": True,
                    "violations": violations,
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Extract search intent via LLM
        intent_prompt = SEARCH_INTENT_PROMPT.format(prompt=prompt[:500])
        raw = self._call_llm(intent_prompt, temperature=0.1, max_tokens=200)
        intent = self._parse_json_object(raw)

        query = intent.get("query", prompt)
        max_results = min(intent.get("max_results", 5), 10)

        # Store for audit
        self._store_working_memory(
            f"Web search: query='{query}' max_results={max_results}",
            tags=["agent:web_search", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "web_search",
                "query": query,
                "max_results": max_results,
                "safe_search": intent.get("safe_search", True),
                "domains": intent.get("domains", []),
                "llm_calls": 1,
                "context_updates": {
                    "tool_query": query,
                    "tool_type": "web_search",
                },
            },
            in_reply_to=message.message_id,
        )
