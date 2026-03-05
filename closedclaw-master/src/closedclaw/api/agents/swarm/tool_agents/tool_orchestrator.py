"""
ToolOrchestratorAgent — routes tool requests to specialized tool agents.

No LLM call needed for routing — uses deterministic dispatch based on
the requested tool type. Validates permissions, enforces consent gates,
and aggregates results from tool agents.
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

# Tools that always require explicit user consent before execution
_WRITE_TOOLS = frozenset({
    "gmail:send_email",
    "notion:create_page",
    "notion:update_page",
    "drive:upload_file",
    "slack:send_message",
    "github:create_issue",
})


class ToolOrchestratorAgent(BaseAgent):
    """Deterministic dispatcher for tool operations.

    Receives a tool request, validates it against constitution and
    permissions, routes to the correct tool agent, and returns the
    aggregated result with consent flags.
    """

    AGENT_NAME = "tool_orchestrator"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        input_data = message.payload.get("input_data", {})
        tool_type = input_data.get("tool", "")
        operation = input_data.get("operation", "")
        params = input_data.get("params", {})

        if not tool_type:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "approved": False,
                    "reason": "No tool type specified",
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Constitution check for tool access
        violations = self._constitution.check_compliance({
            "content": f"Tool access: {tool_type}/{operation}",
            "action": "tool_access",
            "tool": tool_type,
        })
        if violations:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "approved": False,
                    "violations": violations,
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Check if this is a write operation requiring consent
        tool_op_key = f"{tool_type}:{operation}"
        consent_required = tool_op_key in _WRITE_TOOLS

        # Route to the appropriate tool agent
        tool_agent_name = self._resolve_tool_agent(tool_type)
        if not tool_agent_name:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "approved": False,
                    "reason": f"Unknown tool type: {tool_type}",
                    "available_tools": [
                        "gmail", "notion", "drive", "slack", "github",
                        "email", "calendar", "web_search", "code_executor",
                        "file_access", "browser", "notification",
                    ],
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Delegate to tool agent if coordinator is available
        if self._coordinator:
            try:
                tool_agent = self._coordinator._get_agent(tool_agent_name)
                tool_msg = self._bus.create_message(
                    sender=self.AGENT_NAME,
                    recipient=tool_agent_name,
                    message_type="task",
                    payload={
                        "input_data": {
                            "prompt": input_data.get("prompt", ""),
                            "operation": operation,
                            "params": params,
                            "tool": tool_type,
                        },
                        "context": context,
                    },
                )
                self._keyring.sign_message(tool_msg, self.AGENT_NAME)
                tool_result = await tool_agent.handle(tool_msg, context)
                tool_payload = tool_result.payload
            except Exception as exc:
                logger.error("Tool agent %s failed: %s", tool_agent_name, exc)
                tool_payload = {"error": str(exc)}
        else:
            tool_payload = {
                "tool": tool_type,
                "operation": operation,
                "params": params,
                "status": "routed",
            }

        # Record in working memory
        self._store_working_memory(
            f"Orchestrated: {tool_type}/{operation} -> {tool_agent_name} "
            f"consent={consent_required}",
            tags=["agent:tool_orchestrator", "routing"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": tool_type,
                "operation": operation,
                "approved": True,
                "consent_required": consent_required,
                "routed_to": tool_agent_name,
                "tool_result": tool_payload,
                "llm_calls": tool_payload.get("llm_calls", 0),
                "context_updates": {
                    "tool_type": tool_type,
                    "tool_operation": operation,
                    "consent_required": consent_required,
                },
            },
            in_reply_to=message.message_id,
        )

    @staticmethod
    def _resolve_tool_agent(tool_type: str) -> str | None:
        """Map tool type to the responsible agent name."""
        mapping = {
            # New MCP connector agents
            "gmail": "gmail",
            "notion": "notion",
            "drive": "drive",
            "slack": "slack",
            "github": "github_tool",
            # Existing tool agents
            "email": "email",
            "calendar": "calendar",
            "web_search": "web_search",
            "code_executor": "code_executor",
            "file_access": "file_access",
            "browser": "browser",
            "notification": "notification",
        }
        return mapping.get(tool_type)
