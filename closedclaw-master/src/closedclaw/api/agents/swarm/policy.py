"""
Policy Agent — reads the constitution and manages privacy rules.

Can evaluate memories against the constitution (0 LLM calls) and
generate new policy rules based on observed patterns (1 LLM call).
"""

import json
import logging
from typing import Any, Dict, List

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage, ConstitutionPrinciple

logger = logging.getLogger(__name__)


class PolicyAgent(BaseAgent):
    AGENT_NAME = "policy"
    MODEL_TIER = "light"  # qwen3.5:0.8b — structured JSON rule generation from patterns

    RULE_GENERATION_PROMPT = """{few_shot}Based on these consent patterns and the user's constitution, suggest privacy rules.

Constitution:
{principles}

Recent consent patterns:
{patterns}

Suggest 1-3 rules as JSON array. Each: {{"id": "rule-...", "name": "...", "description": "...", "conditions": {{"sensitivity_min": 0, "sensitivity_max": 3, "tags": [], "providers": []}}, "action": "BLOCK|PERMIT|REDACT|CONSENT_REQUIRED", "priority": 50}}

JSON array:"""

    AMENDMENT_PROMPT = """Based on these repeated user actions, propose a constitutional amendment.

Actions observed:
{actions}

Current constitution:
{principles}

Propose an amendment as JSON: {{"name": "...", "description": "...", "priority": 50, "enforcement": "strict|advisory"}}
Only propose if there's a clear pattern. If no amendment needed, return: {{}}

JSON:"""

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        action = message.payload.get("action", message.payload.get("input_data", {}).get("action", "evaluate"))

        if action == "evaluate":
            return await self._evaluate_compliance(message, context)
        elif action == "generate_rules":
            return await self._generate_rules(message, context)
        elif action == "propose_amendment":
            return await self._propose_amendment(message, context)
        elif action == "vote_access":
            return await self._handle_vote(message, context)
        else:
            return await self._evaluate_compliance(message, context)

    async def _evaluate_compliance(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Check memory/action against constitution (0 LLM calls)."""
        input_data = message.payload.get("input_data", {})
        facts = context.get("extracted_facts", input_data.get("facts", []))
        provider = context.get("provider", "ollama")

        if not facts:
            return self._make_response(
                recipient="coordinator",
                payload={"compliant": True, "violations": [], "llm_calls": 0, "context_updates": {}},
                in_reply_to=message.message_id,
            )

        all_violations = []
        compliant_facts = []

        for fact in facts:
            violations = self._constitution.check_compliance({
                **fact,
                "provider": provider,
            })
            if violations:
                all_violations.append({"fact": fact.get("content", "")[:100], "violations": violations})
            else:
                compliant_facts.append(fact)

        return self._make_response(
            recipient="coordinator",
            payload={
                "compliant": len(all_violations) == 0,
                "violations": all_violations,
                "compliant_facts": compliant_facts,
                "total_checked": len(facts),
                "llm_calls": 0,
                "context_updates": {
                    "policy_compliant": len(all_violations) == 0,
                    "policy_violations": all_violations,
                    "compliant_facts": compliant_facts,
                },
            },
            in_reply_to=message.message_id,
        )

    async def _generate_rules(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Analyze consent patterns and generate new policy rules (1 LLM call)."""
        input_data = message.payload.get("input_data", {})
        patterns = input_data.get("consent_patterns", [])

        if not patterns:
            # Try to load from storage
            patterns = self._load_consent_patterns()

        if not patterns:
            return self._make_response(
                recipient="coordinator",
                payload={"suggested_rules": [], "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        few_shot = self._build_few_shot_context("generate privacy rules")
        if few_shot:
            few_shot += "\n\n"

        prompt = self.RULE_GENERATION_PROMPT.format(
            few_shot=few_shot,
            principles=self._constitution.principles_summary(),
            patterns=json.dumps(patterns[:10], default=str)[:800],
        )
        raw = await self._call_llm(prompt, temperature=0.1, max_tokens=600)
        rules = self._parse_json_array(raw)

        if rules:
            self._store_working_memory(
                f"Generated {len(rules)} policy rules from {len(patterns)} consent patterns",
                tags=["agent:policy", "rule_generation"],
            )

        return self._make_response(
            recipient="coordinator",
            payload={"suggested_rules": rules, "patterns_analyzed": len(patterns), "llm_calls": 1},
            in_reply_to=message.message_id,
        )

    async def _propose_amendment(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Propose a constitutional amendment based on observed patterns (1 LLM call)."""
        input_data = message.payload.get("input_data", {})
        actions = input_data.get("observed_actions", [])

        if not actions:
            return self._make_response(
                recipient="coordinator",
                payload={"amendment": None, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        prompt = self.AMENDMENT_PROMPT.format(
            actions=json.dumps(actions[:10], default=str)[:600],
            principles=self._constitution.principles_summary(),
        )
        raw = await self._call_llm(prompt, temperature=0.1, max_tokens=300)
        proposal = self._parse_json_object(raw)

        amendment = None
        if proposal.get("name"):
            principle = ConstitutionPrinciple(
                id=f"auto-{proposal.get('name', 'rule').lower().replace(' ', '-')[:20]}",
                name=proposal.get("name", ""),
                description=proposal.get("description", ""),
                priority=proposal.get("priority", 50),
                enforcement=proposal.get("enforcement", "advisory"),
            )
            amendment = self._constitution.propose_amendment(
                principle=principle,
                reason=f"Auto-proposed from {len(actions)} observed actions",
                proposed_by=self.AGENT_NAME,
            )

        return self._make_response(
            recipient="coordinator",
            payload={
                "amendment": amendment.model_dump() if amendment else None,
                "llm_calls": 1,
            },
            in_reply_to=message.message_id,
        )

    async def _handle_vote(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Vote on access — Policy checks against constitution."""
        memory = message.payload.get("memory", {})
        provider = context.get("provider", "ollama")
        violations = self._constitution.check_compliance({**memory, "provider": provider})
        vote = "deny" if violations else "permit"

        return self._make_response(
            recipient="coordinator",
            payload={"vote": vote, "violations": violations, "llm_calls": 0},
            in_reply_to=message.message_id,
        )

    def _load_consent_patterns(self) -> List[Dict[str, Any]]:
        """Load recent consent decisions from storage for pattern analysis."""
        try:
            from closedclaw.api.core.storage import PersistentStore
            store = PersistentStore()
            receipts = store.load_consent_receipts(limit=50)
            return [
                {
                    "decision": r.get("decision"),
                    "sensitivity": r.get("sensitivity"),
                    "provider": r.get("provider"),
                    "tags": r.get("tags", []),
                }
                for r in receipts
            ]
        except Exception:
            return []
