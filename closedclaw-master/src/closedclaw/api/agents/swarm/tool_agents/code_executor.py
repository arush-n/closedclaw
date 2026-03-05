"""
CodeExecutorAgent — validates and sandboxes code execution requests.

1 LLM call for code safety analysis. Enforces constitution rules on
code execution (allowed languages, blocked operations, timeout limits).
"""

import logging
from typing import Any, Dict, List

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

BLOCKED_PATTERNS = frozenset({
    "os.system", "subprocess", "eval(", "exec(",
    "shutil.rmtree", "__import__", "open('/etc",
    "rm -rf", "format c:", "del /f",
})

SAFETY_PROMPT = """Analyze this code for safety. Is it safe to execute in a sandboxed environment?

Language: {language}
Code:
```
{code}
```

Respond with JSON: {{"safe": true/false, "risk_level": "low|medium|high", "concerns": ["..."]}}
JSON:"""


class CodeExecutorAgent(BaseAgent):
    AGENT_NAME = "code_executor"

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        return await self._validate_execution(message, context)

    async def _validate_execution(
        self, message: AgentMessage, context: Dict[str, Any]
    ) -> AgentMessage:
        input_data = message.payload.get("input_data", {})
        code = input_data.get("code", "")
        language = input_data.get("language", "python")

        if not code:
            return self._make_response(
                recipient="coordinator",
                payload={"approved": False, "reason": "empty code", "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Deterministic block check
        blocked = self._check_blocked_patterns(code)
        if blocked:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "approved": False,
                    "reason": "blocked_pattern",
                    "blocked_patterns": blocked,
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Constitution check
        violations = self._constitution.check_compliance({
            "content": code,
            "action": "code_execution",
            "language": language,
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

        # LLM safety analysis
        prompt = SAFETY_PROMPT.format(language=language, code=code[:1000])
        raw = self._call_llm(prompt, temperature=0.1, max_tokens=200)
        analysis = self._parse_json_object(raw)

        approved = analysis.get("safe", False) and analysis.get("risk_level") != "high"

        self._store_working_memory(
            f"Code execution: lang={language} approved={approved} "
            f"risk={analysis.get('risk_level', 'unknown')}",
            tags=["agent:code_executor", "tool_call"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "tool": "code_executor",
                "approved": approved,
                "language": language,
                "risk_level": analysis.get("risk_level", "unknown"),
                "concerns": analysis.get("concerns", []),
                "llm_calls": 1,
                "context_updates": {
                    "code_approved": approved,
                    "tool_type": "code_executor",
                },
            },
            in_reply_to=message.message_id,
        )

    @staticmethod
    def _check_blocked_patterns(code: str) -> List[str]:
        code_lower = code.lower()
        return [p for p in BLOCKED_PATTERNS if p.lower() in code_lower]
