"""
Constitution — user-editable ethical principles that govern all agent behavior.

Loaded from ~/.closedclaw/constitution.json. The Policy agent can propose
amendments, but only the user can approve them (via consent gate).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from closedclaw.api.agents.swarm.models import (
    ConstitutionAmendment,
    ConstitutionPrinciple,
    ConstitutionSchema,
)

logger = logging.getLogger(__name__)

DEFAULT_PRINCIPLES = [
    ConstitutionPrinciple(
        id="sovereignty",
        name="Data Sovereignty",
        description="User is sole owner. No data leaves local machine without explicit consent.",
        priority=100,
        enforcement="strict",
    ),
    ConstitutionPrinciple(
        id="minimal-collection",
        name="Minimal Collection",
        description="Only store information explicitly shared or clearly useful.",
        priority=90,
        enforcement="strict",
    ),
    ConstitutionPrinciple(
        id="right-to-forget",
        name="Right to Be Forgotten",
        description="Any memory can be permanently deleted. Cryptographic deletion ensures irrecoverability.",
        priority=95,
        enforcement="strict",
    ),
    ConstitutionPrinciple(
        id="transparency",
        name="Transparency",
        description="Every memory access logged in audit trail. Users see exactly what was accessed.",
        priority=85,
        enforcement="strict",
    ),
    ConstitutionPrinciple(
        id="local-first",
        name="Local-First Processing",
        description="Sensitive data (level 2+) processed by local models only.",
        priority=80,
        enforcement="strict",
    ),
]


class Constitution:
    """Loads, validates, and queries the user's ethical constitution."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or (Path.home() / ".closedclaw" / "constitution.json")
        self.schema: ConstitutionSchema = ConstitutionSchema()
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                self.schema = ConstitutionSchema(**raw)
                logger.info(
                    "Constitution loaded: %d principles, v%s",
                    len(self.schema.principles),
                    self.schema.version,
                )
                return
            except Exception as exc:
                logger.warning("Failed to load constitution: %s — using defaults", exc)

        self.schema = ConstitutionSchema(principles=list(DEFAULT_PRINCIPLES))
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self.schema.model_dump(), indent=2, default=str),
            encoding="utf-8",
        )

    # ── Queries ───────────────────────────────────────────────────────

    @property
    def principles(self) -> List[ConstitutionPrinciple]:
        return sorted(self.schema.principles, key=lambda p: -p.priority)

    def get_principle(self, principle_id: str) -> Optional[ConstitutionPrinciple]:
        for p in self.schema.principles:
            if p.id == principle_id:
                return p
        return None

    def principles_summary(self, max_chars: int = 600) -> str:
        """Compact text summary for LLM prompts."""
        lines = []
        total = 0
        for p in self.principles:
            line = f"- [{p.priority}] {p.name}: {p.description}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        return "\n".join(lines)

    def is_provider_allowed(self, provider: str) -> bool:
        allowed = self.schema.allowed_providers
        if not allowed:
            return True
        return provider.lower() in [p.lower() for p in allowed]

    def is_blocked_topic(self, text: str) -> bool:
        text_lower = text.lower()
        return any(topic.lower() in text_lower for topic in self.schema.blocked_topics)

    def check_sensitivity_for_provider(self, sensitivity: int, provider: str) -> bool:
        """Return True if this sensitivity level is allowed for this provider."""
        if provider.lower() == "ollama":
            return True  # local is always allowed
        return sensitivity <= self.schema.max_sensitivity_cloud

    def check_compliance(self, memory: Dict[str, Any]) -> List[Dict[str, str]]:
        """Check a memory dict against all strict principles. Returns violations."""
        violations: List[Dict[str, str]] = []
        content = memory.get("content", memory.get("memory", ""))
        sensitivity = memory.get("sensitivity", 0)
        provider = memory.get("provider", "ollama")

        # Blocked topics
        if self.is_blocked_topic(content):
            violations.append({
                "principle": "minimal-collection",
                "reason": "Content matches a blocked topic",
            })

        # Cloud sensitivity
        if not self.check_sensitivity_for_provider(sensitivity, provider):
            violations.append({
                "principle": "local-first",
                "reason": f"Sensitivity {sensitivity} not allowed for provider {provider}",
            })

        # Provider allowlist
        if not self.is_provider_allowed(provider):
            violations.append({
                "principle": "sovereignty",
                "reason": f"Provider {provider} not in allowed list",
            })

        return violations

    def resolve_conflict(
        self, position_a: str, position_b: str, context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Try to resolve a conflict using constitutional principles alone.

        Returns a resolution dict if deterministic, None if LLM arbitration needed.
        """
        sensitivity = context.get("sensitivity", 0)
        provider = context.get("provider", "ollama")

        # If one position is about blocking and sensitivity is high, constitution says block
        block_keywords = {"block", "deny", "reject", "refuse"}
        permit_keywords = {"permit", "allow", "approve", "share"}

        a_blocks = any(k in position_a.lower() for k in block_keywords)
        b_blocks = any(k in position_b.lower() for k in block_keywords)

        if sensitivity >= 3:
            # High sensitivity: always prefer the more restrictive position
            if a_blocks and not b_blocks:
                return {"winner": "a", "reason": "Constitutional: high sensitivity favors restriction"}
            if b_blocks and not a_blocks:
                return {"winner": "b", "reason": "Constitutional: high sensitivity favors restriction"}

        if not self.is_provider_allowed(provider):
            # Non-allowed provider: block wins
            if a_blocks:
                return {"winner": "a", "reason": "Constitutional: provider not in allowed list"}
            if b_blocks:
                return {"winner": "b", "reason": "Constitutional: provider not in allowed list"}

        return None  # Need LLM arbitration

    # ── Amendments ────────────────────────────────────────────────────

    def propose_amendment(
        self, principle: ConstitutionPrinciple, reason: str, proposed_by: str
    ) -> ConstitutionAmendment:
        amendment = ConstitutionAmendment(
            proposed_by=proposed_by,
            principle=principle,
            reason=reason,
        )
        self.schema.amendments.append(amendment)
        self._save()
        return amendment

    def approve_amendment(self, amendment_id: str) -> bool:
        for a in self.schema.amendments:
            if a.id == amendment_id and a.status == "pending":
                a.status = "approved"
                self.schema.principles.append(a.principle)
                self._save()
                return True
        return False

    def reject_amendment(self, amendment_id: str) -> bool:
        for a in self.schema.amendments:
            if a.id == amendment_id and a.status == "pending":
                a.status = "rejected"
                self._save()
                return True
        return False

    def get_pending_amendments(self) -> List[ConstitutionAmendment]:
        return [a for a in self.schema.amendments if a.status == "pending"]

    def to_dict(self) -> Dict[str, Any]:
        return self.schema.model_dump()
