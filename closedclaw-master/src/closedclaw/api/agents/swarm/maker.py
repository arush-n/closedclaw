"""
Maker Agent — turns raw information into structured memories.

Uses 1 LLM call per invocation to extract facts from text, classify
sensitivity, assign tags, and categorize. Also handles memory compaction
(deduplication, summarization, importance decay) in batch mode.
"""

import logging
from typing import Any, Dict, List

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)


class MakerAgent(BaseAgent):
    AGENT_NAME = "maker"
    MODEL_TIER = "medium"  # qwen3.5:2b — structured fact extraction + sensitivity classification

    EXTRACT_PROMPT = """{few_shot}Extract key facts from this text as a JSON array.
Each fact: {{"content": "a complete sentence describing the fact", "tags": [...], "category": "...", "sensitivity_hint": 0-3}}
sensitivity: 0=public, 1=general, 2=personal, 3=sensitive (medical/financial/legal)
IMPORTANT: Each "content" MUST be a full, self-contained sentence (not just a keyword).
Example: "The user's favorite programming language is Rust." — NOT just "Rust".
Only extract facts worth remembering. Max 5 facts.

Text: {text}

JSON array:"""

    COMPACT_PROMPT = """These memories are semantically similar. Merge them into a single concise fact.
Keep the most important details. Return JSON: {{"content": "merged fact", "tags": [...], "category": "..."}}

Memories:
{memories}

JSON:"""

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        action = message.payload.get("action", message.payload.get("input_data", {}).get("action", "extract"))

        if action == "extract":
            return await self._extract_facts(message, context)
        elif action == "compact":
            return await self._compact_memories(message, context)
        elif action == "batch_extract":
            return await self._batch_extract(message, context)
        else:
            return await self._extract_facts(message, context)

    async def _extract_facts(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Extract structured facts from raw text (1 LLM call)."""
        input_data = message.payload.get("input_data", {})
        raw_text = input_data.get("raw_text", input_data.get("content", ""))
        user_id = context.get("user_id", "default")

        if not raw_text:
            return self._make_response(
                recipient="coordinator",
                payload={"facts": [], "llm_calls": 0, "context_updates": {"extracted_facts": []}},
                in_reply_to=message.message_id,
            )

        # Build few-shot context from working memory
        few_shot = self._build_few_shot_context(raw_text[:100])
        if few_shot:
            few_shot += "\n\n"

        prompt = self.EXTRACT_PROMPT.format(
            few_shot=few_shot,
            text=raw_text[:2000],
        )
        raw_response = await self._call_llm(prompt, temperature=0.2, max_tokens=600)
        facts = self._parse_json_array(raw_response)

        if not facts:
            # Fallback: treat the entire text as a single fact
            facts = [{"content": raw_text[:500], "tags": [], "category": "general", "sensitivity_hint": 1}]

        # Classify each fact with the existing classifier
        classified = []
        try:
            from closedclaw.api.privacy.classifier import SensitivityClassifier
            classifier = SensitivityClassifier()
        except Exception:
            classifier = None

        for fact in facts:
            content = fact.get("content", "")
            if not content:
                continue

            sensitivity = fact.get("sensitivity_hint", 1)
            if classifier:
                try:
                    result = classifier.classify(content, tags=fact.get("tags"))
                    sensitivity = result.level if hasattr(result, "level") else result
                except Exception:
                    pass

            # Constitution check: blocked topics
            if self._constitution.is_blocked_topic(content):
                logger.debug("Maker: blocked topic detected, skipping: %s", content[:60])
                continue

            classified.append({
                "content": content,
                "tags": fact.get("tags", []),
                "category": fact.get("category", "general"),
                "sensitivity": sensitivity if isinstance(sensitivity, int) else sensitivity.value if hasattr(sensitivity, "value") else 1,
                "user_id": user_id,
            })

        # Store successful extraction pattern in working memory
        if classified:
            self._store_working_memory(
                f"Extracted {len(classified)} facts from text. "
                f"Tags: {', '.join(set(t for f in classified for t in f.get('tags', [])))}",
                tags=["agent:maker", "extraction_log"],
            )

        return self._make_response(
            recipient="coordinator",
            payload={
                "facts": classified,
                "count": len(classified),
                "llm_calls": 1,
                "context_updates": {"extracted_facts": classified},
            },
            in_reply_to=message.message_id,
        )

    async def _compact_memories(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Deduplicate and merge semantically similar memories (1 LLM call)."""
        input_data = message.payload.get("input_data", {})
        memories = input_data.get("memories", [])

        if len(memories) < 2:
            return self._make_response(
                recipient="coordinator",
                payload={"merged": memories, "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Format for LLM
        mem_text = "\n".join(
            f"- {m.get('content', m.get('memory', ''))[:150]}"
            for m in memories[:10]
        )
        prompt = self.COMPACT_PROMPT.format(memories=mem_text)
        raw = await self._call_llm(prompt, temperature=0.1, max_tokens=300)
        merged = self._parse_json_object(raw)

        if not merged.get("content"):
            # Fallback: keep the first memory
            merged = memories[0] if memories else {}

        return self._make_response(
            recipient="coordinator",
            payload={"merged": merged, "original_count": len(memories), "llm_calls": 1},
            in_reply_to=message.message_id,
        )

    async def _batch_extract(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Process multiple text items in a single LLM call for efficiency."""
        input_data = message.payload.get("input_data", {})
        items = input_data.get("items", [])

        if not items:
            return self._make_response(
                recipient="coordinator",
                payload={"facts": [], "llm_calls": 0},
                in_reply_to=message.message_id,
            )

        # Batch up to 10 items into a single prompt
        batch_text = "\n---\n".join(
            f"Item {i+1}: {item.get('content', str(item))[:200]}"
            for i, item in enumerate(items[:10])
        )

        prompt = f"""Extract key facts from each item below. Return a JSON array with one fact per item.
Each: {{"content": "...", "tags": [...], "category": "...", "sensitivity_hint": 0-3}}

{batch_text}

JSON array:"""

        raw = await self._call_llm(prompt, temperature=0.2, max_tokens=800)
        facts = self._parse_json_array(raw)

        return self._make_response(
            recipient="coordinator",
            payload={
                "facts": facts,
                "items_processed": len(items[:10]),
                "llm_calls": 1,
            },
            in_reply_to=message.message_id,
        )
