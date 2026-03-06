"""
Governance Agent — guards memories and controls access.

Pure rule evaluation, NO LLM calls. Wraps the existing PrivacyFirewall
and PolicyEngine to make access control decisions.
"""

import logging
from typing import Any, Dict, List

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)


class GovernanceAgent(BaseAgent):
    AGENT_NAME = "governance"
    MODEL_TIER = "none"  # No LLM — pure PrivacyFirewall + PolicyEngine rule evaluation

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        action = message.payload.get("action", "evaluate_access")

        if action == "vote_access":
            return await self._handle_vote(message, context)

        return await self._handle_evaluate(message, context)

    async def _handle_evaluate(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Run memories through the PrivacyFirewall pipeline."""
        memories = context.get("retrieved_memories", [])
        provider = context.get("provider", "ollama")
        query = context.get("query", message.payload.get("input_data", {}).get("query", ""))

        if not memories:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "permitted": [],
                    "blocked": [],
                    "consent_required": [],
                    "context_text": "",
                    "llm_calls": 0,
                    "context_updates": {"firewall_decision": None, "permitted_memories": []},
                },
                in_reply_to=message.message_id,
            )

        # Normalize memories to dicts for the firewall
        mem_dicts = self._normalize_memories(memories)

        # Run through existing PrivacyFirewall
        from closedclaw.api.privacy.firewall import PrivacyFirewall
        from closedclaw.api.core.policies import PolicyEngine

        try:
            policy_engine = PolicyEngine()
        except Exception:
            policy_engine = None

        firewall = PrivacyFirewall(policy_engine=policy_engine)

        try:
            decision = await firewall.process(mem_dicts, provider=provider, query=query)
        except Exception:
            # Fall back to sync
            decision = firewall.process_sync(mem_dicts, provider=provider, query=query)

        permitted = [self._context_to_dict(m) for m in decision.permitted]
        blocked = [self._context_to_dict(m) for m in decision.blocked]
        consent_req = [self._context_to_dict(m) for m in decision.consent_required]

        all_blocked = len(permitted) == 0 and len(blocked) > 0

        return self._make_response(
            recipient="coordinator",
            payload={
                "permitted": permitted,
                "blocked": blocked,
                "consent_required": consent_req,
                "context_text": decision.context_text,
                "redaction_count": decision.redaction_count,
                "llm_calls": 0,
                "all_blocked": all_blocked,
                "context_updates": {
                    "firewall_decision": {
                        "permitted_count": len(permitted),
                        "blocked_count": len(blocked),
                        "consent_required_count": len(consent_req),
                        "redaction_count": decision.redaction_count,
                    },
                    "permitted_memories": permitted,
                    "context_text": decision.context_text,
                },
            },
            in_reply_to=message.message_id,
        )

    async def _handle_vote(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Vote on whether to permit access to a specific memory (for federated consensus)."""
        memory = message.payload.get("memory", {})
        provider = context.get("provider", "ollama")
        sensitivity = memory.get("sensitivity", 0)

        # Constitution check
        violations = self._constitution.check_compliance({**memory, "provider": provider})
        vote = "deny" if violations else "permit"

        # Extra caution for high sensitivity
        if sensitivity >= 3 and provider != "ollama":
            vote = "deny"

        return self._make_response(
            recipient="coordinator",
            payload={"vote": vote, "violations": violations, "llm_calls": 0},
            in_reply_to=message.message_id,
        )

    @staticmethod
    def _normalize_memories(memories: list) -> List[Dict[str, Any]]:
        """Convert memory objects/dicts to a consistent dict format for the firewall."""
        result = []
        for m in memories:
            if isinstance(m, dict):
                result.append(m)
            elif hasattr(m, "model_dump"):
                result.append(m.model_dump())
            else:
                result.append(vars(m))
        return result

    @staticmethod
    def _context_to_dict(ctx) -> Dict[str, Any]:
        """Convert a MemoryContext dataclass to a plain dict."""
        if isinstance(ctx, dict):
            return ctx
        if hasattr(ctx, "__dict__"):
            d = dict(ctx.__dict__)
            # Convert enums to strings
            for k, v in d.items():
                if hasattr(v, "value"):
                    d[k] = v.value
            return d
        return {"raw": str(ctx)}
