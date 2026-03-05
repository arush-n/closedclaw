"""
Ollama-Enhanced PII Detection & Redaction

Uses a local Ollama LLM to identify PII entities that regex patterns miss,
such as names, contextual locations, and nuanced personal references.

Falls back gracefully to regex-only detection if Ollama is unavailable.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from .detector import DetectedEntity, ENTITY_SENSITIVITY_MAP

logger = logging.getLogger(__name__)

# Prompt template for PII detection
_PII_DETECTION_PROMPT = """Identify all personally identifiable information (PII) in the following text.
Return a JSON array of objects with these fields:
- "entity_type": one of PERSON, PHONE_NUMBER, EMAIL_ADDRESS, CREDIT_CARD, US_SSN, LOCATION, ADDRESS, DATE_TIME, ORGANIZATION, IP_ADDRESS, URL, AGE
- "text": the exact substring from the input
- "start": character offset where the entity starts
- "end": character offset where the entity ends

Only return the JSON array, nothing else. If no PII is found, return [].

Text: {text}"""


class OllamaRedactionEngine:
    """
    Uses a local Ollama model for PII entity extraction.

    Designed to supplement regex-based detection with LLM understanding
    of context (e.g., detecting that "Austin" is a city, not a name).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 15.0,
    ):
        if model is None:
            # Use the fast model tier for PII detection (lightweight task)
            try:
                from closedclaw.api.core.config import get_settings
                settings = get_settings()
                model = settings.local_engine.get_fast_ollama_model()
            except Exception:
                model = "llama3.2:3b"
        self.model = model
        self.base_url = base_url or os.getenv(
            "CLOSEDCLAW_OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self.timeout = timeout
        self._available: Optional[bool] = None

    async def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        if self._available is not None:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                self._available = resp.status_code == 200
        except Exception:
            self._available = False
        return self._available

    async def detect_pii(self, text: str) -> List[DetectedEntity]:
        """
        Use Ollama to detect PII entities in text.

        Returns DetectedEntity objects compatible with the existing pipeline.
        """
        if not text or not text.strip():
            return []

        prompt = _PII_DETECTION_PROMPT.format(text=text)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 1024},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("response", "").strip()
        except Exception as exc:
            logger.warning("Ollama PII detection failed: %s", exc)
            return []

        return self._parse_llm_response(raw, text)

    def _parse_llm_response(
        self, raw: str, original_text: str
    ) -> List[DetectedEntity]:
        """Parse the LLM JSON response into DetectedEntity objects."""
        # Extract JSON array from response (LLM may wrap in markdown)
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []

        try:
            items = json.loads(match.group())
        except json.JSONDecodeError:
            logger.debug("Failed to parse Ollama PII response as JSON")
            return []

        entities: List[DetectedEntity] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            entity_type = item.get("entity_type", "")
            entity_text = item.get("text", "")
            if not entity_type or not entity_text:
                continue

            # Verify the text actually exists in the original
            start = item.get("start")
            end = item.get("end")
            if start is not None and end is not None:
                # Verify position matches
                actual = original_text[start:end]
                if actual != entity_text:
                    # Try to find the text at a different position
                    idx = original_text.find(entity_text)
                    if idx == -1:
                        continue
                    start, end = idx, idx + len(entity_text)
            else:
                idx = original_text.find(entity_text)
                if idx == -1:
                    continue
                start, end = idx, idx + len(entity_text)

            sensitivity = ENTITY_SENSITIVITY_MAP.get(entity_type, 1)
            entities.append(
                DetectedEntity(
                    entity_type=entity_type,
                    text=entity_text,
                    start=start,
                    end=end,
                    score=0.75,  # LLM detections get moderate confidence
                    sensitivity_level=sensitivity,
                )
            )

        return entities


# Singleton
_ollama_engine: Optional[OllamaRedactionEngine] = None


def get_ollama_redaction_engine(**kwargs: Any) -> OllamaRedactionEngine:
    """Get shared OllamaRedactionEngine instance."""
    global _ollama_engine
    if _ollama_engine is None:
        _ollama_engine = OllamaRedactionEngine(**kwargs)
    return _ollama_engine
