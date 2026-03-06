"""
GitHubToolAgent — validates GitHub operations with PII redaction.

1 LLM call to extract structured GitHub intent.
Write operations (create issue) require explicit consent.
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

GITHUB_INTENT_PROMPT = """Extract GitHub operation details from this request. Redact any PII.

Request: {prompt}

Respond with JSON: {{"action": "list_repos|get_repo|list_issues|create_issue|list_prs|get_file", "owner": "...", "repo": "...", "title": "...", "path": "...", "query": "...", "contains_pii": false}}
JSON:"""


class GitHubToolAgent(BaseAgent):
    AGENT_NAME = "github_tool"

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
            "action": "github_access",
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "violations": violations, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        raw = await self._call_llm(
            GITHUB_INTENT_PROMPT.format(prompt=prompt[:500]),
            temperature=0.1,
            max_tokens=400,
        )
        github_data = self._parse_json_object(raw)

        action = github_data.get("action", "list_repos")
        consent_required = action == "create_issue"

        self._store_working_memory(
            f"GitHub: action={action} repo='{github_data.get('repo', '')}' "
            f"consent_required={consent_required}",
            tags=["agent:github_tool", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "github",
                "approved": True,
                "github": github_data,
                "consent_required": consent_required,
                "contains_pii": github_data.get("contains_pii", False),
                "llm_calls": 1,
                "context_updates": {
                    "github_data": github_data,
                    "tool_type": "github",
                    "consent_required": consent_required,
                },
            },
            in_reply_to=message.message_id,
        )
