"""
Arbitrator Agent — resolves conflicts between agents.

First tries constitutional resolution (0 LLM calls). Falls back to
LLM-based arbitration (1 call) with weighted scoring.
"""

import logging
from typing import Any, Dict

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage, ArbitrationCase

logger = logging.getLogger(__name__)


class ArbitratorAgent(BaseAgent):
    AGENT_NAME = "arbitrator"
    MODEL_TIER = "medium"  # qwen3.5:2b — constitutional conflict resolution

    ARBITRATION_PROMPT = """{few_shot}You are an impartial arbitrator resolving a conflict between two AI agents in a privacy-first memory system.

Agent {agent_a} says: {position_a}
Reasoning: {reasoning_a}

Agent {agent_b} says: {position_b}
Reasoning: {reasoning_b}

Constitutional principles (higher priority = more important):
{principles}

Context: sensitivity={sensitivity}, provider={provider}

Decide which position should prevail. When in doubt, favor privacy and restriction.
Respond with JSON: {{"winner": "agent_name", "decision": "...", "reasoning": "..."}}

JSON:"""

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        case_data = message.payload.get("case", {})
        if not case_data:
            return self._make_response(
                recipient="coordinator",
                payload={"resolution": None, "error": "No arbitration case provided", "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        case = ArbitrationCase(**case_data)

        # Step 1: Try constitutional resolution (no LLM)
        constitutional = self._constitution.resolve_conflict(
            case.agent_a_position,
            case.agent_b_position,
            {**context, **case.context},
        )

        if constitutional:
            winner_agent = case.agent_a if constitutional["winner"] == "a" else case.agent_b
            case.resolution = constitutional["reason"]
            case.winner = winner_agent
            case.method = "constitutional"

            self._store_working_memory(
                f"Resolved {case.agent_a} vs {case.agent_b}: "
                f"winner={winner_agent} (constitutional). "
                f"Reason: {constitutional['reason'][:100]}",
                tags=["agent:arbitrator", "resolution_log"],
            )

            return self._make_response(
                recipient="coordinator",
                payload={
                    "resolution": case.model_dump(),
                    "method": "constitutional",
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Step 2: LLM arbitration (1 call)
        few_shot = self._build_few_shot_context(
            f"arbitration: {case.agent_a} vs {case.agent_b}"
        )
        if few_shot:
            few_shot += "\n\n"

        sensitivity = context.get("sensitivity", case.context.get("sensitivity", 0))
        provider = context.get("provider", case.context.get("provider", "ollama"))

        prompt = self.ARBITRATION_PROMPT.format(
            few_shot=few_shot,
            agent_a=case.agent_a,
            position_a=case.agent_a_position[:300],
            reasoning_a=case.agent_a_reasoning[:200],
            agent_b=case.agent_b,
            position_b=case.agent_b_position[:300],
            reasoning_b=case.agent_b_reasoning[:200],
            principles=self._constitution.principles_summary(400),
            sensitivity=sensitivity,
            provider=provider,
        )

        raw = await self._call_llm(prompt, temperature=0.3, max_tokens=300)
        decision = self._parse_json_object(raw)

        winner = decision.get("winner", "")
        # Validate winner is one of the agents
        if winner not in (case.agent_a, case.agent_b):
            # Default: favor the more restrictive agent
            winner = case.agent_a  # Usually governance/policy = more restrictive

        case.resolution = decision.get("decision", decision.get("reasoning", ""))
        case.winner = winner
        case.method = "llm_arbitration"

        self._store_working_memory(
            f"Resolved {case.agent_a} vs {case.agent_b}: "
            f"winner={winner} (LLM). "
            f"Decision: {case.resolution[:100]}",
            tags=["agent:arbitrator", "resolution_log"],
        )

        return self._make_response(
            recipient="coordinator",
            payload={
                "resolution": case.model_dump(),
                "method": "llm_arbitration",
                "llm_calls": 1,
            },
            in_reply_to=message.message_id,
        )
