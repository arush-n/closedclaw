"""
FileAccessAgent — validates file read/write requests against constitution.

0 LLM calls. Pure path validation and permission checking.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

BLOCKED_PATHS = frozenset({
    "/etc/shadow", "/etc/passwd", "/etc/sudoers",
    "~/.ssh", "~/.gnupg", "~/.aws/credentials",
})

ALLOWED_EXTENSIONS = frozenset({
    ".txt", ".md", ".json", ".csv", ".yaml", ".yml",
    ".py", ".js", ".ts", ".html", ".css", ".log",
})


class FileAccessAgent(BaseAgent):
    AGENT_NAME = "file_access"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        return await self._validate_access(message, context)

    async def _validate_access(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        input_data = message.payload.get("input_data", {})
        file_path = input_data.get("path", "")
        operation = input_data.get("operation", "read")

        if not file_path:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "reason": "empty path", "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Normalize and resolve path
        resolved = str(Path(os.path.expanduser(file_path)).resolve())

        # Check blocked paths
        for blocked in BLOCKED_PATHS:
            expanded = str(Path(os.path.expanduser(blocked)).resolve())
            if resolved.startswith(expanded):
                return self._make_response(
                    recipient="coordinator",
                    payload={
                        "approved": False,
                        "reason": "blocked_path",
                        "path": file_path,
                        "llm_calls": 0,
                    },
                    in_reply_to=message.message_id,
                )

        # Check extension for writes
        if operation == "write":
            ext = Path(resolved).suffix.lower()
            if ext and ext not in ALLOWED_EXTENSIONS:
                return self._make_response(
                    recipient="coordinator",
                    payload={
                        "approved": False,
                        "reason": "blocked_extension",
                        "extension": ext,
                        "llm_calls": 0,
                    },
                    in_reply_to=message.message_id,
                )

        # Constitution check
        violations = self._constitution.check_compliance({
            "content": file_path,
            "action": f"file_{operation}",
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

        self._store_working_memory(
            f"File {operation}: path={file_path} approved=True",
            tags=["agent:file_access", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "file_access",
                "approved": True,
                "path": resolved,
                "operation": operation,
                "llm_calls": 0,
                "context_updates": {
                    "file_approved": True,
                    "tool_type": "file_access",
                },
            },
            in_reply_to=message.message_id,
        )
