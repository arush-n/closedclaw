"""
Sentinel Agent — detects hallucinations, drift, and fabrication.

Cross-references LLM outputs against stored memories. Uses 1 LLM call
to compare claims in a response against the memory vault.
"""

import logging
from typing import Any, Dict, List

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)


class SentinelAgent(BaseAgent):
    AGENT_NAME = "sentinel"
    MODEL_TIER = "heavy"  # qwen3.5:4b — nuanced hallucination detection

    HALLUCINATION_CHECK_PROMPT = """{few_shot}Compare the AI response against the user's stored memories.
Flag claims that contradict or are fabricated (not supported by any memory).
Return a JSON array. Each issue: {{"claim": "...", "issue": "contradiction|fabricated|unsupported", "memory_id": "...", "explanation": "..."}}
If no issues, return: []

Response: {response}

Memories:
{memories}

JSON array:"""

    DRIFT_CHECK_PROMPT = """Check if this AI response drifts from the user's known preferences and patterns.
User patterns from memory:
{patterns}

AI Response: {response}

Return JSON: {{"drift_detected": true/false, "issues": ["..."]}}
JSON:"""

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        action = message.payload.get("action", "check_hallucination")

        if action == "vote_access":
            return await self._handle_vote(message, context)
        elif action == "check_drift":
            return await self._check_drift(message, context)
        else:
            return await self._check_hallucination(message, context)

    async def _check_hallucination(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Cross-reference LLM output against stored memories (1 LLM call)."""
        input_data = message.payload.get("input_data", {})
        llm_response = input_data.get("llm_response", context.get("llm_response", ""))
        user_id = context.get("user_id", "default")

        if not llm_response:
            return self._make_response(
                recipient="coordinator",
                payload={"issues": [], "verified": True, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Get relevant memories for comparison
        memories = context.get("retrieved_memories", [])
        if not memories and self._memory:
            try:
                results = self._memory.search(
                    query=llm_response[:500],
                    user_id=user_id,
                    limit=15,
                )
                if isinstance(results, dict):
                    memories = results.get("results", [])
                else:
                    memories = results or []
            except Exception:
                memories = []

        if not memories:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "issues": [],
                    "verified": True,
                    "note": "No memories to cross-reference",
                    "llm_calls": 0,
                },
                in_reply_to=message.message_id,
            )

        # Format memories for prompt
        mem_lines = []
        for m in memories[:10]:
            mid = m.get("id", "?")[:8] if isinstance(m, dict) else getattr(m, "id", "?")[:8]
            text = (
                m.get("memory", m.get("content", ""))
                if isinstance(m, dict)
                else getattr(m, "memory", getattr(m, "content", ""))
            )
            mem_lines.append(f"[{mid}] {text[:150]}")
        mem_text = "\n".join(mem_lines)

        # Few-shot from working memory
        few_shot = self._build_few_shot_context(f"hallucination check: {llm_response[:80]}")
        if few_shot:
            few_shot += "\n\n"

        prompt = self.HALLUCINATION_CHECK_PROMPT.format(
            few_shot=few_shot,
            response=llm_response[:1500],
            memories=mem_text,
        )
        raw = await self._call_llm(prompt, temperature=0.1, max_tokens=600)
        issues = self._parse_json_array(raw)

        # Store result in working memory for future few-shot
        verified = len(issues) == 0
        if issues:
            self._store_working_memory(
                f"Hallucination detected: {len(issues)} issues in response about "
                f"'{llm_response[:60]}...' Issues: {issues[0].get('claim', '')[:80]}",
                tags=["agent:sentinel", "hallucination_log"],
            )

        return self._make_response(
            recipient="coordinator",
            payload={
                "issues": issues,
                "verified": verified,
                "memories_compared": len(memories),
                "llm_calls": 1,
                "context_updates": {"sentinel_issues": issues, "sentinel_verified": verified},
            },
            in_reply_to=message.message_id,
        )

    async def _check_drift(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Check if response drifts from user's known patterns (1 LLM call)."""
        input_data = message.payload.get("input_data", {})
        llm_response = input_data.get("llm_response", "")
        user_id = context.get("user_id", "default")

        # Get user preference memories
        patterns = []
        if self._memory:
            try:
                results = self._memory.search(
                    query="user preferences and patterns",
                    user_id=user_id,
                    limit=10,
                )
                if isinstance(results, dict):
                    patterns = results.get("results", [])
                else:
                    patterns = results or []
            except Exception:
                patterns = []

        if not patterns:
            return self._make_response(
                recipient="coordinator",
                payload={"drift_detected": False, "issues": [], "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        pattern_text = "\n".join(
            f"- {(m.get('memory', m.get('content', '')) if isinstance(m, dict) else getattr(m, 'memory', ''))[:120]}"
            for m in patterns[:8]
        )

        prompt = self.DRIFT_CHECK_PROMPT.format(
            patterns=pattern_text,
            response=llm_response[:1000],
        )
        raw = await self._call_llm(prompt, temperature=0.1, max_tokens=300)
        result = self._parse_json_object(raw)

        return self._make_response(
            recipient="coordinator",
            payload={
                "drift_detected": result.get("drift_detected", False),
                "issues": result.get("issues", []),
                "llm_calls": 1,
            },
            in_reply_to=message.message_id,
        )

    async def _handle_vote(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Vote on access — Sentinel checks if providing this memory could enable hallucination."""
        memory = message.payload.get("memory", {})
        content = memory.get("content", memory.get("memory", ""))

        # Simple heuristic: vague or ambiguous memories are risky
        word_count = len(content.split())
        vote = "permit" if word_count >= 5 else "deny"

        return self._make_response(
            recipient="coordinator",
            payload={"vote": vote, "reason": f"Memory has {word_count} words", "llm_calls": 0},
            in_reply_to=message.message_id,
        )
