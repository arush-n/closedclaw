"""
Accessor Agent — retrieves and serves memories based on requests.

Handles semantic search, related memory expansion via graph traversal,
and context building. Applies the firewall pipeline before returning.
Basic mode: 0 LLM calls. With query expansion: 1 LLM call.
"""

import logging
from typing import Any, Dict, List, Optional

from closedclaw.api.agents.swarm.base import BaseAgent
from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)


class AccessorAgent(BaseAgent):
    AGENT_NAME = "accessor"

    EXPAND_PROMPT = """Given this user query, generate 2 alternative search queries that might find related memories. Return a JSON array of strings.

Query: {query}

JSON array:"""

    async def handle(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        input_data = message.payload.get("input_data", {})
        query = input_data.get("query", context.get("query", ""))
        user_id = context.get("user_id", "default")
        sensitivity_max = input_data.get("sensitivity_max", 3)
        limit = input_data.get("limit", 10)

        if not query or not self._memory:
            return self._make_response(
                recipient="coordinator",
                payload={
                    "memories": [],
                    "count": 0,
                    "llm_calls": 0,
                    "context_updates": {"retrieved_memories": [], "query": query},
                },
                in_reply_to=message.message_id,
            )

        # Step 1: Direct semantic search (no LLM)
        memories = self._search(query, user_id, sensitivity_max, limit)

        # Step 2: Graph traversal — follow related_ids for richer context
        expanded = self._expand_via_graph(memories, user_id, sensitivity_max)
        all_memories = memories + expanded

        # Step 3: Optional query expansion if too few results
        llm_calls = 0
        if len(all_memories) < 3 and len(query) > 15:
            extra, calls = self._query_expand(query, user_id, sensitivity_max, all_memories)
            all_memories.extend(extra)
            llm_calls += calls

        # Step 4: Build few-shot context for future use
        if all_memories:
            self._store_working_memory(
                f"Search '{query[:80]}' returned {len(all_memories)} memories "
                f"(sensitivity_max={sensitivity_max})",
                tags=["agent:accessor", "search_log"],
            )

        mem_dicts = [self._to_dict(m) for m in all_memories]

        return self._make_response(
            recipient="coordinator",
            payload={
                "memories": mem_dicts,
                "count": len(mem_dicts),
                "direct_matches": len(memories),
                "graph_expanded": len(expanded),
                "llm_calls": llm_calls,
                "context_updates": {
                    "retrieved_memories": mem_dicts,
                    "query": query,
                },
            },
            in_reply_to=message.message_id,
        )

    def _search(self, query: str, user_id: str, sensitivity_max: int, limit: int) -> list:
        """Semantic search via the memory manager."""
        try:
            results = self._memory.search(
                query=query,
                user_id=user_id,
                sensitivity_max=sensitivity_max,
                limit=limit,
            )
            if isinstance(results, dict):
                return results.get("results", [])
            if isinstance(results, list):
                return results
            return []
        except Exception as exc:
            logger.warning("Accessor search failed: %s", exc)
            return []

    def _expand_via_graph(self, memories: list, user_id: str, sensitivity_max: int) -> list:
        """Walk related_ids to expand context (no LLM call)."""
        seen_ids = set()
        for m in memories:
            mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
            if mid:
                seen_ids.add(mid)

        expanded = []
        for m in memories:
            related = (
                m.get("related_ids", [])
                if isinstance(m, dict)
                else getattr(m, "related_ids", []) or []
            )
            for rid in related[:3]:
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                try:
                    rel = self._memory.get(rid)
                    if rel:
                        sens = rel.get("sensitivity", 0) if isinstance(rel, dict) else getattr(rel, "sensitivity", 0)
                        if sens <= sensitivity_max:
                            expanded.append(rel)
                except Exception:
                    pass
            if len(expanded) >= 5:
                break

        return expanded

    def _query_expand(
        self, query: str, user_id: str, sensitivity_max: int, existing: list
    ) -> tuple:
        """Use LLM to generate alternative search queries (1 call)."""
        prompt = self.EXPAND_PROMPT.format(query=query[:200])
        raw = self._call_llm(prompt, temperature=0.3, max_tokens=150)
        sub_queries = self._parse_json_array(raw)
        if not sub_queries:
            # Try parsing as list of strings
            sub_queries = [s for s in sub_queries if isinstance(s, str)]

        existing_ids = set()
        for m in existing:
            mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
            if mid:
                existing_ids.add(mid)

        extra = []
        for sq in sub_queries[:2]:
            if isinstance(sq, str):
                results = self._search(sq, user_id, sensitivity_max, limit=5)
                for r in results:
                    rid = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
                    if rid and rid not in existing_ids:
                        existing_ids.add(rid)
                        extra.append(r)

        return extra, 1

    @staticmethod
    def _to_dict(m) -> Dict[str, Any]:
        if isinstance(m, dict):
            return m
        if hasattr(m, "model_dump"):
            return m.model_dump()
        return vars(m) if hasattr(m, "__dict__") else {"raw": str(m)}
