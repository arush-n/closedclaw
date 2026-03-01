"""
Closedclaw Insight Engine

A scheduled, local-only analysis engine that mines the memory store for
personal value without sending any data externally.

Produces four insight types:
- Life Summary: Natural-language summary of recent memories
- Trend Detection: Recurring themes and patterns
- Contradiction Alerts: Memories that appear to conflict
- Memory Expiry Review: Memories approaching TTL expiry

All processing uses the local LLM (Ollama) for text generation steps.
No personal memory text is sent to a cloud provider.
"""

import json
import logging
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# INSIGHT DATA MODELS
# =============================================================================

class TrendItem(BaseModel):
    """A detected trend/recurring theme."""
    topic: str = Field(..., description="Topic or theme name")
    count: int = Field(..., description="Number of memories mentioning this topic")
    tags: List[str] = Field(default_factory=list, description="Related tags")
    first_seen: Optional[str] = Field(None, description="Earliest memory timestamp")
    last_seen: Optional[str] = Field(None, description="Most recent memory timestamp")
    description: Optional[str] = Field(None, description="LLM-generated description of the trend")
    memory_ids: List[str] = Field(default_factory=list, description="IDs of related memories")


class ContradictionAlert(BaseModel):
    """A pair of memories that appear to contradict each other."""
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    memory_a_id: str = Field(..., description="First memory ID")
    memory_a_text: str = Field(..., description="First memory text")
    memory_b_id: str = Field(..., description="Second memory ID")
    memory_b_text: str = Field(..., description="Second memory text")
    explanation: str = Field(..., description="LLM explanation of the contradiction")
    severity: str = Field(default="medium", description="low/medium/high")
    resolved: bool = Field(default=False)


class ExpiringMemory(BaseModel):
    """A memory approaching its TTL expiry."""
    memory_id: str
    content: str
    tags: List[str] = Field(default_factory=list)
    sensitivity: int = 0
    expires_at: str
    days_remaining: int
    created_at: Optional[str] = None


class InsightResult(BaseModel):
    """Complete result from an insight engine run."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    life_summary: Optional[str] = None
    trends: List[TrendItem] = Field(default_factory=list)
    contradictions: List[ContradictionAlert] = Field(default_factory=list)
    expiring_memories: List[ExpiringMemory] = Field(default_factory=list)
    memories_analyzed: int = 0
    model_used: str = ""
    duration_seconds: float = 0.0
    errors: List[str] = Field(default_factory=list)


# =============================================================================
# PROMPTS FOR LOCAL LLM
# =============================================================================

LIFE_SUMMARY_PROMPT = """You are a personal reflection assistant. Analyze the user's recent memories below and produce a concise, well-structured summary.

Guidelines:
- Organize by themes (work, health, relationships, hobbies, etc.)
- Note key events, decisions, and milestones
- Highlight recurring interests or concerns
- Keep it clear, factual, and respectful of privacy
- Use markdown formatting for readability
- Limit to about 500 words

MEMORIES:
{memories}

Provide a thoughtful life summary based on these memories:"""

TREND_ANALYSIS_PROMPT = """Analyze the following memories and identify the top recurring themes, topics, or patterns.

For each theme:
- Name the topic
- Describe how it appears across memories
- Note any changes or progression over time

Return your analysis as a JSON array with objects containing: "topic", "description", "count" (approximate frequency).

MEMORIES:
{memories}

Respond ONLY with a JSON array like:
[{{"topic": "...", "description": "...", "count": N}}, ...]"""

CONTRADICTION_CHECK_PROMPT = """Compare the following pairs of memories and identify any contradictions, inconsistencies, or conflicts between them.

A contradiction is when two memories state different facts about the same subject. For example:
- "I live in Austin" vs "I moved to San Francisco last month"
- "I'm allergic to peanuts" vs "I love peanut butter"

For each contradiction found, explain what conflicts and rate severity (low/medium/high).

MEMORY PAIRS TO CHECK:
{memory_pairs}

Return your findings as a JSON array:
[{{"memory_a_index": N, "memory_b_index": N, "explanation": "...", "severity": "low|medium|high"}}]

If no contradictions are found, return an empty array: []"""


# =============================================================================
# INSIGHT ENGINE
# =============================================================================

class InsightEngine:
    """
    Local-only insight engine for analyzing the memory store.

    All analysis runs on the local LLM (Ollama). No personal data
    is sent to any cloud provider during insight generation.
    """

    def __init__(self, memory=None, settings=None):
        """
        Initialize the InsightEngine.

        Args:
            memory: ClosedclawMemory instance
            settings: Application Settings
        """
        self._memory = memory
        self._settings = settings
        self._llm = None
        self._last_result: Optional[InsightResult] = None
        self._result_history: List[InsightResult] = []

    @property
    def memory(self):
        """Lazy-load memory instance."""
        if self._memory is None:
            from closedclaw.api.core.memory import get_memory_instance
            self._memory = get_memory_instance()
        return self._memory

    @property
    def settings(self):
        """Lazy-load settings."""
        if self._settings is None:
            from closedclaw.api.core.config import get_settings
            self._settings = get_settings()
        return self._settings

    def _get_llm(self):
        """Get or create the local LLM interface."""
        if self._llm is None:
            try:
                from ollama import Client
                self._llm = Client(
                    host=self.settings.local_engine.ollama_base_url
                )
            except ImportError:
                raise RuntimeError(
                    "Ollama library not installed. Run: pip install ollama"
                )
        return self._llm

    def _get_model_name(self) -> str:
        """Get the configured Ollama model name."""
        from closedclaw.api.core.local import LOCAL_MODELS

        model_key = self.settings.local_engine.llm_model
        if model_key in LOCAL_MODELS:
            return LOCAL_MODELS[model_key].ollama_model
        return model_key

    def _llm_generate(
        self,
        prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 2000,
    ) -> str:
        """Generate text using the local LLM."""
        client = self._get_llm()
        model = self._get_model_name()

        try:
            response = client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "top_p": 0.9,
                },
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise

    def _format_memories_text(
        self, memories: List[Dict], max_chars: int = 16000
    ) -> str:
        """Format memories into a text block for LLM context."""
        lines = []
        total_chars = 0

        for i, mem in enumerate(memories, 1):
            content = mem.get("memory", mem.get("content", ""))
            tags = mem.get("tags", [])
            created = mem.get("created_at", "")
            sensitivity = mem.get("sensitivity", 0)

            entry = f"[{i}] "
            if tags:
                entry += f"(tags: {', '.join(tags)}) "
            if created:
                entry += f"({created}) "
            entry += f"[sensitivity={sensitivity}]\n{content}"

            if total_chars + len(entry) > max_chars:
                lines.append(f"\n[...{len(memories) - i} more memories truncated...]")
                break

            lines.append(entry)
            total_chars += len(entry)

        return "\n\n".join(lines)

    # =========================================================================
    # ANALYSIS METHODS
    # =========================================================================

    def generate_life_summary(
        self,
        user_id: str = "default",
        weeks: int = 4,
        sensitivity_max: int = 2,
        _prefetched: Optional[List[Dict]] = None,
    ) -> str:
        """
        Generate a natural-language summary of recent memories.

        Args:
            user_id: User identifier
            weeks: Number of weeks to look back
            sensitivity_max: Max sensitivity level to include
            _prefetched: Pre-fetched memories to avoid repeated DB calls

        Returns:
            Markdown-formatted life summary
        """
        logger.info(f"Generating life summary for user={user_id}, weeks={weeks}")

        if _prefetched is not None:
            memories = _prefetched
        else:
            all_mems = self.memory.get_all(
                user_id=user_id,
                sensitivity_max=sensitivity_max,
                limit=100,
            )
            memories = all_mems.get("results", [])

        if not memories:
            return "No memories found for the specified time period."

        # Filter by date if memories have timestamps
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        filtered = []
        for mem in memories:
            created = mem.get("created_at") or mem.get("metadata", {}).get("created_at")
            if created:
                try:
                    dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    if dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            filtered.append(mem)

        if not filtered:
            filtered = memories  # Fall back to all memories if no timestamps

        context = self._format_memories_text(filtered)
        prompt = LIFE_SUMMARY_PROMPT.format(memories=context)

        return self._llm_generate(prompt, temperature=0.5, max_tokens=2000)

    def detect_trends(
        self,
        user_id: str = "default",
        sensitivity_max: int = 2,
        _prefetched: Optional[List[Dict]] = None,
    ) -> List[TrendItem]:
        """
        Identify recurring themes and patterns in memories.

        Uses a two-pass approach:
        1. Statistical pass: count tags/keywords
        2. LLM pass: identify semantic themes

        Returns:
            List of TrendItem objects
        """
        logger.info(f"Detecting trends for user={user_id}")

        if _prefetched is not None:
            memories = _prefetched
        else:
            all_mems = self.memory.get_all(
                user_id=user_id,
                sensitivity_max=sensitivity_max,
                limit=200,
            )
            memories = all_mems.get("results", [])

        if not memories:
            return []

        # Pass 1: Statistical tag counting
        tag_counter: Counter = Counter()
        tag_memory_ids: Dict[str, List[str]] = defaultdict(list)
        tag_timestamps: Dict[str, List[str]] = defaultdict(list)

        for mem in memories:
            mem_id = mem.get("id", "")
            tags = mem.get("tags", [])
            created = mem.get("created_at", "")

            for tag in tags:
                tag_lower = tag.lower()
                tag_counter[tag_lower] += 1
                tag_memory_ids[tag_lower].append(mem_id)
                if created:
                    tag_timestamps[tag_lower].append(created)

        # Build initial trends from tags
        trends: List[TrendItem] = []
        for tag, count in tag_counter.most_common(20):
            timestamps = sorted(tag_timestamps.get(tag, []))
            trends.append(
                TrendItem(
                    topic=tag,
                    count=count,
                    tags=[tag],
                    first_seen=timestamps[0] if timestamps else None,
                    last_seen=timestamps[-1] if timestamps else None,
                    description=None,
                    memory_ids=tag_memory_ids.get(tag, [])[:10],
                )
            )

        # Pass 2: LLM semantic analysis for deeper trends
        if len(memories) >= 5:
            try:
                context = self._format_memories_text(memories[:50])
                prompt = TREND_ANALYSIS_PROMPT.format(memories=context)
                raw = self._llm_generate(prompt, temperature=0.3, max_tokens=1500)

                # Parse JSON from LLM response
                llm_trends = self._parse_json_array(raw)
                existing_topics = {t.topic.lower() for t in trends}

                for item in llm_trends:
                    topic = item.get("topic", "").strip()
                    if not topic or topic.lower() in existing_topics:
                        continue
                    trends.append(
                        TrendItem(
                            topic=topic,
                            count=item.get("count", 1),
                            tags=[],
                            first_seen=None,
                            last_seen=None,
                            description=item.get("description", ""),
                        )
                    )
            except Exception as e:
                logger.warning(f"LLM trend analysis failed: {e}")

        # Sort by count descending
        trends.sort(key=lambda t: t.count, reverse=True)
        return trends[:25]

    def find_contradictions(
        self,
        user_id: str = "default",
        sensitivity_max: int = 2,
        max_pairs: int = 15,
        _prefetched: Optional[List[Dict]] = None,
    ) -> List[ContradictionAlert]:
        """
        Find contradictions between stored memories.

        Compares memories with overlapping tags for semantic contradictions
        using the local LLM to identify conflicts.

        Args:
            user_id: User identifier
            sensitivity_max: Max sensitivity to include
            max_pairs: Max number of pairs to check
            _prefetched: Pre-fetched memories to avoid repeated DB calls

        Returns:
            List of ContradictionAlert objects
        """
        logger.info(f"Finding contradictions for user={user_id}")

        if _prefetched is not None:
            memories = _prefetched
        else:
            all_mems = self.memory.get_all(
                user_id=user_id,
                sensitivity_max=sensitivity_max,
                limit=100,
            )
            memories = all_mems.get("results", [])

        if len(memories) < 2:
            return []

        # Build pairs of memories with overlapping tags or similar content
        pairs: List[Tuple[Dict, Dict]] = []
        tag_index: Dict[str, List[int]] = defaultdict(list)

        for idx, mem in enumerate(memories):
            for tag in mem.get("tags", []):
                tag_index[tag.lower()].append(idx)

        # Find pairs that share at least one tag  (O(T * k²) where k = max indices per tag)
        seen_pairs: set = set()
        pairs_full = False
        for indices in tag_index.values():
            if pairs_full:
                break
            for i in range(len(indices)):
                if pairs_full:
                    break
                for j in range(i + 1, len(indices)):
                    pair_key = (
                        min(indices[i], indices[j]),
                        max(indices[i], indices[j]),
                    )
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        pairs.append(
                            (memories[pair_key[0]], memories[pair_key[1]])
                        )
                        if len(pairs) >= max_pairs:
                            pairs_full = True
                            break

        if not pairs:
            # Fall back to comparing sequential memories
            for i in range(min(len(memories) - 1, max_pairs)):
                pairs.append((memories[i], memories[i + 1]))

        # Format pairs for LLM
        pair_text_lines = []
        for idx, (a, b) in enumerate(pairs):
            content_a = a.get("memory", a.get("content", ""))
            content_b = b.get("memory", b.get("content", ""))
            pair_text_lines.append(
                f"Pair {idx}:\n"
                f"  Memory A: {content_a}\n"
                f"  Memory B: {content_b}"
            )

        pair_text = "\n\n".join(pair_text_lines)
        prompt = CONTRADICTION_CHECK_PROMPT.format(memory_pairs=pair_text)

        try:
            raw = self._llm_generate(prompt, temperature=0.2, max_tokens=1500)
            items = self._parse_json_array(raw)
        except Exception as e:
            logger.warning(f"Contradiction analysis failed: {e}")
            return []

        alerts: List[ContradictionAlert] = []
        for item in items:
            idx_a = item.get("memory_a_index", 0)
            idx_b = item.get("memory_b_index", 0)

            if idx_a >= len(pairs) or idx_b > len(pairs):
                continue

            pair = pairs[min(idx_a, len(pairs) - 1)]
            mem_a, mem_b = pair

            alerts.append(
                ContradictionAlert(
                    memory_a_id=mem_a.get("id", ""),
                    memory_a_text=mem_a.get("memory", mem_a.get("content", "")),
                    memory_b_id=mem_b.get("id", ""),
                    memory_b_text=mem_b.get("memory", mem_b.get("content", "")),
                    explanation=item.get("explanation", "Potential contradiction detected."),
                    severity=item.get("severity", "medium"),
                )
            )

        return alerts

    def review_expiring(
        self,
        user_id: str = "default",
        days_ahead: int = 30,
    ) -> List[ExpiringMemory]:
        """
        Find memories approaching their TTL expiry.

        Args:
            user_id: User identifier
            days_ahead: Look ahead window in days

        Returns:
            List of ExpiringMemory objects
        """
        logger.info(f"Reviewing expiring memories for user={user_id}, window={days_ahead}d")

        all_mems = self.memory.get_all(user_id=user_id, limit=500)
        memories = all_mems.get("results", [])

        # Batch-load metadata for all memory IDs (avoids N+1 queries)
        mem_ids = [m.get("id", "") for m in memories if m.get("id")]
        stored_meta_batch: Dict[str, Dict] = {}
        if mem_ids:
            try:
                stored_meta_batch = self.memory._store.load_memory_metadata_batch(mem_ids) or {}
            except Exception:
                stored_meta_batch = {}

        now = datetime.now(timezone.utc)
        deadline = now + timedelta(days=days_ahead)
        expiring: List[ExpiringMemory] = []

        for mem in memories:
            mem_id = mem.get("id", "")
            meta = mem.get("metadata", {})
            stored = stored_meta_batch.get(mem_id, {})

            expires_str = (
                meta.get("expires_at")
                or stored.get("expires_at")
            )
            if not expires_str:
                continue

            try:
                expires_dt = datetime.fromisoformat(
                    str(expires_str).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                continue

            if now <= expires_dt <= deadline:
                days_remaining = (expires_dt - now).days
                expiring.append(
                    ExpiringMemory(
                        memory_id=mem_id,
                        content=mem.get("memory", mem.get("content", "")),
                        tags=mem.get("tags", stored.get("tags", [])),
                        sensitivity=mem.get(
                            "sensitivity", stored.get("sensitivity", 0)
                        ),
                        expires_at=expires_str,
                        days_remaining=days_remaining,
                        created_at=stored.get("created_at"),
                    )
                )

        # Sort by soonest expiry
        expiring.sort(key=lambda m: m.days_remaining)
        return expiring

    # =========================================================================
    # FULL RUN
    # =========================================================================

    def run(
        self,
        user_id: str = "default",
        weeks: int = 4,
        sensitivity_max: int = 2,
        skip: Optional[List[str]] = None,
    ) -> InsightResult:
        """
        Run the full insight engine pipeline.

        Args:
            user_id: User identifier
            weeks: Weeks of history to analyze
            sensitivity_max: Max sensitivity level
            skip: List of analysis types to skip
                  ("summary", "trends", "contradictions", "expiring")

        Returns:
            InsightResult with all analysis outputs
        """
        import time

        start = time.monotonic()
        skip_set: set = set(skip or [])
        result = InsightResult(
            model_used=self._get_model_name(),
            memories_analyzed=0,
        )

        # Fetch ALL memories ONCE and reuse across sub-methods
        all_mems = self.memory.get_all(
            user_id=user_id,
            sensitivity_max=sensitivity_max,
            limit=500,
        )
        prefetched = all_mems.get("results", [])
        result.memories_analyzed = len(prefetched)

        # Life summary
        if "summary" not in skip_set:
            try:
                result.life_summary = self.generate_life_summary(
                    user_id=user_id,
                    weeks=weeks,
                    sensitivity_max=sensitivity_max,
                    _prefetched=prefetched,
                )
            except Exception as e:
                logger.error(f"Life summary failed: {e}")
                result.errors.append(f"life_summary: {str(e)}")

        # Trends
        if "trends" not in skip_set:
            try:
                result.trends = self.detect_trends(
                    user_id=user_id,
                    sensitivity_max=sensitivity_max,
                    _prefetched=prefetched,
                )
            except Exception as e:
                logger.error(f"Trend detection failed: {e}")
                result.errors.append(f"trends: {str(e)}")

        # Contradictions
        if "contradictions" not in skip_set:
            try:
                result.contradictions = self.find_contradictions(
                    user_id=user_id,
                    sensitivity_max=sensitivity_max,
                    _prefetched=prefetched,
                )
            except Exception as e:
                logger.error(f"Contradiction check failed: {e}")
                result.errors.append(f"contradictions: {str(e)}")

        # Expiring memories
        if "expiring" not in skip_set:
            try:
                result.expiring_memories = self.review_expiring(
                    user_id=user_id
                )
            except Exception as e:
                logger.error(f"Expiry review failed: {e}")
                result.errors.append(f"expiring: {str(e)}")

        result.duration_seconds = round(time.monotonic() - start, 2)

        # Cache the result
        self._last_result = result
        self._result_history.append(result)
        # Keep only last 10 results in memory
        if len(self._result_history) > 10:
            self._result_history = self._result_history[-10:]

        logger.info(
            f"Insight run complete: {result.memories_analyzed} memories, "
            f"{len(result.trends)} trends, {len(result.contradictions)} contradictions, "
            f"{len(result.expiring_memories)} expiring, "
            f"{result.duration_seconds}s"
        )

        return result

    # =========================================================================
    # RESULT ACCESS
    # =========================================================================

    @property
    def last_result(self) -> Optional[InsightResult]:
        """Get the most recent insight result."""
        return self._last_result

    @property
    def result_history(self) -> List[InsightResult]:
        """Get the history of insight results."""
        return list(self._result_history)

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _parse_json_array(text: str) -> List[Dict]:
        """
        Extract and parse a JSON array from LLM output.

        Handles cases where the LLM wraps the JSON in markdown code fences
        or adds extra text around it.
        """
        import re

        # Try direct parse first
        text = text.strip()
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError:
            pass

        # Try extracting from code fences
        code_block = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
        if code_block:
            try:
                result = json.loads(code_block.group(1).strip())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        # Try finding array brackets
        bracket_match = re.search(r"\[[\s\S]*\]", text)
        if bracket_match:
            try:
                result = json.loads(bracket_match.group(0))
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse JSON array from LLM output: {text[:200]}")
        return []


# =============================================================================
# SINGLETON
# =============================================================================

_insight_engine: Optional[InsightEngine] = None


def get_insight_engine() -> InsightEngine:
    """Get or create the singleton InsightEngine instance."""
    global _insight_engine
    if _insight_engine is None:
        _insight_engine = InsightEngine()
    return _insight_engine
