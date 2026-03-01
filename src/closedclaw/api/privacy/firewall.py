"""
Privacy Firewall Module

WARNING: This module is not currently wired into any request path.
The actual privacy enforcement is done inline in routes/proxy.py
(_enrich_with_memory) and core/policies.py (PolicyEngine).
This class should either be integrated as the single entry-point for
the privacy pipeline or removed to avoid confusion.
TODO: Consolidate the inline proxy logic into PrivacyFirewall or
      deprecate this module.

The core pipeline that every memory passes through before context injection.
Enforces user-defined privacy rules with:

1. Retrieve: Get relevant memories from vault
2. Classify: Confirm/upgrade sensitivity levels
3. Rule Match: Evaluate against policy rules
4. Redact: Apply PII redaction pipeline
5. Consent Gate: Pause for user approval if needed
6. Inject: Format approved context for LLM
7. Audit: Log everything that happened

This is the mechanism that makes closedclaw's privacy promise real.
"""

from typing import List, Dict, Optional, Any, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import hashlib
import logging
import asyncio
import uuid
import math
import random
import concurrent.futures

from .detector import PIIDetector, DetectedEntity, get_detector
from .classifier import (
    SensitivityClassifier, 
    SensitivityLevel, 
    ClassificationResult
)
from .redactor import PIIRedactor, RedactionResult, RedactionStyle

logger = logging.getLogger(__name__)

_SYNC_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)


class FirewallAction(str, Enum):
    """Actions the firewall can take on a memory."""
    
    PERMIT = "PERMIT"                # Allow memory to be used as-is
    REDACT = "REDACT"                # Allow but redact PII
    BLOCK = "BLOCK"                  # Block memory from being used
    CONSENT_REQUIRED = "CONSENT_REQUIRED"  # Require user consent first
    PENDING = "PENDING"              # Awaiting consent decision


class ConsentStatus(str, Enum):
    """Status of a consent request."""
    
    PENDING = "pending"
    APPROVED = "approved"
    APPROVED_REDACTED = "approved_redacted"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class MemoryContext:
    """
    A memory item being processed through the firewall.
    
    Contains both the original memory and all firewall decisions.
    """
    
    # Original memory data
    memory_id: str
    content: str
    sensitivity: int
    tags: List[str] = field(default_factory=list)
    source: str = "conversation"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Firewall processing results
    action: FirewallAction = FirewallAction.PENDING
    classification: Optional[ClassificationResult] = None
    redaction: Optional[RedactionResult] = None
    rule_matched: Optional[str] = None
    
    # Consent tracking
    consent_id: Optional[str] = None
    consent_status: Optional[ConsentStatus] = None
    consent_reason: Optional[str] = None
    
    # Output
    processed_content: Optional[str] = None
    
    @property
    def effective_sensitivity(self) -> int:
        """Get the effective sensitivity (classified or original)."""
        if self.classification:
            return self.classification.level
        return self.sensitivity
    
    @property
    def was_modified(self) -> bool:
        """Whether the content was modified."""
        return (
            self.redaction is not None and 
            self.redaction.was_modified
        )
    
    @property
    def is_blocked(self) -> bool:
        """Whether this memory was blocked."""
        return self.action == FirewallAction.BLOCK
    
    @property
    def requires_consent(self) -> bool:
        """Whether this memory requires consent."""
        return self.action == FirewallAction.CONSENT_REQUIRED
    
    @property
    def content_hash(self) -> str:
        """SHA-256 hash of original content (for consent receipts)."""
        return hashlib.sha256(self.content.encode()).hexdigest()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "memory_id": self.memory_id,
            "content_length": len(self.content),
            "sensitivity": self.sensitivity,
            "effective_sensitivity": self.effective_sensitivity,
            "tags": self.tags,
            "source": self.source,
            "action": self.action.value,
            "rule_matched": self.rule_matched,
            "was_modified": self.was_modified,
            "classification": self.classification.to_dict() if self.classification else None,
            "redaction": self.redaction.to_dict() if self.redaction else None,
            "consent_status": self.consent_status.value if self.consent_status else None,
        }


@dataclass
class ConsentRequest:
    """A request for user consent to use a memory."""
    
    id: str
    memory_id: str
    content: str  # Full content shown to user
    content_hash: str
    sensitivity: int
    tags: List[str]
    provider: str
    proposed_redactions: List[Dict]
    reason: str
    created_at: datetime
    status: ConsentStatus = ConsentStatus.PENDING
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "memory_id": self.memory_id,
            "content": self.content,
            "content_hash": self.content_hash,
            "sensitivity": self.sensitivity,
            "tags": self.tags,
            "provider": self.provider,
            "proposed_redactions": self.proposed_redactions,
            "reason": self.reason,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class FirewallDecision:
    """
    The complete decision output from the privacy firewall.
    
    Contains all memories that passed, were blocked, or need consent.
    """
    
    request_id: str
    provider: str
    timestamp: datetime
    
    # Memory results
    permitted: List[MemoryContext] = field(default_factory=list)
    blocked: List[MemoryContext] = field(default_factory=list)
    consent_required: List[MemoryContext] = field(default_factory=list)
    
    # Aggregated context for LLM
    context_text: str = ""
    
    # Audit info
    total_memories: int = 0
    redaction_count: int = 0
    rules_evaluated: List[str] = field(default_factory=list)
    
    @property
    def has_pending_consent(self) -> bool:
        """Whether any memories require consent."""
        return len(self.consent_required) > 0
    
    @property
    def was_blocked(self) -> bool:
        """Whether any memories were blocked."""
        return len(self.blocked) > 0
    
    @property
    def summary(self) -> str:
        """Human-readable summary of the decision."""
        parts = []
        if self.permitted:
            parts.append(f"{len(self.permitted)} permitted")
        if self.blocked:
            parts.append(f"{len(self.blocked)} blocked")
        if self.consent_required:
            parts.append(f"{len(self.consent_required)} awaiting consent")
        if self.redaction_count:
            parts.append(f"{self.redaction_count} redactions applied")
        return ", ".join(parts) if parts else "No memories processed"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_id": self.request_id,
            "provider": self.provider,
            "timestamp": self.timestamp.isoformat(),
            "summary": self.summary,
            "total_memories": self.total_memories,
            "permitted_count": len(self.permitted),
            "blocked_count": len(self.blocked),
            "consent_required_count": len(self.consent_required),
            "redaction_count": self.redaction_count,
            "permitted": [m.to_dict() for m in self.permitted],
            "blocked": [m.to_dict() for m in self.blocked],
            "consent_required": [m.to_dict() for m in self.consent_required],
            "rules_evaluated": self.rules_evaluated,
            "context_length": len(self.context_text),
        }
    
    def get_audit_entry(self) -> Dict:
        """Get audit log entry for this decision."""
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "total_memories": self.total_memories,
            "permitted_ids": [m.memory_id for m in self.permitted],
            "blocked_ids": [m.memory_id for m in self.blocked],
            "consent_required_ids": [m.memory_id for m in self.consent_required],
            "redaction_count": self.redaction_count,
            "context_token_estimate": len(self.context_text) // 4,  # Rough estimate
        }


@dataclass
class PolicyRule:
    """A privacy policy rule for the firewall."""
    
    id: str
    name: str
    priority: int
    enabled: bool = True
    conditions: Dict[str, Any] = field(default_factory=dict)
    action: FirewallAction = FirewallAction.PERMIT
    redact_entities: Optional[List[str]] = None
    description: Optional[str] = None
    
    def matches(
        self, 
        memory: MemoryContext, 
        provider: str
    ) -> bool:
        """Check if this rule matches the given memory and provider."""
        cond = self.conditions
        provider_lower = provider.lower()
        
        # Sensitivity conditions
        if "sensitivity_min" in cond:
            if memory.effective_sensitivity < cond["sensitivity_min"]:
                return False
        
        if "sensitivity_max" in cond:
            if memory.effective_sensitivity > cond["sensitivity_max"]:
                return False
        
        # Tag conditions
        if "tags_include" in cond:
            if not any(tag in memory.tags for tag in cond["tags_include"]):
                return False
        
        if "tags_exclude" in cond:
            if any(tag in memory.tags for tag in cond["tags_exclude"]):
                return False
        
        # Provider conditions
        if "provider_is" in cond:
            if not any(provider_lower == p.lower() for p in cond["provider_is"]):
                return False
        
        if "provider_not" in cond:
            if any(provider_lower == p.lower() for p in cond["provider_not"]):
                return False
        
        # Source conditions
        if "source_is" in cond:
            if memory.source not in cond["source_is"]:
                return False
        
        if "source_not" in cond:
            if memory.source in cond["source_not"]:
                return False
        
        return True


# Default policy rules
DEFAULT_RULES: List[PolicyRule] = [
    PolicyRule(
        id="block-level3-cloud",
        name="Block Level 3 from cloud",
        description="Highly sensitive memories blocked from non-local providers",
        priority=90,
        conditions={
            "sensitivity_min": 3,
            "provider_not": ["ollama", "local"],
        },
        action=FirewallAction.BLOCK,
    ),
    PolicyRule(
        id="consent-level3",
        name="Consent gate on Level 3",
        description="Highly sensitive memories always require consent",
        priority=100,
        conditions={"sensitivity_min": 3},
        action=FirewallAction.CONSENT_REQUIRED,
    ),
    PolicyRule(
        id="block-level2-cloud",
        name="Block Level 2 from cloud",
        description="Personal memories blocked from cloud by default",
        priority=80,
        conditions={
            "sensitivity_min": 2,
            "sensitivity_max": 2,
            "provider_not": ["ollama", "local"],
        },
        action=FirewallAction.BLOCK,
    ),
    PolicyRule(
        id="redact-level1",
        name="Redact PII from Level 1",
        description="Redact personal identifiers from general memories",
        priority=50,
        conditions={
            "sensitivity_min": 1,
            "sensitivity_max": 1,
        },
        action=FirewallAction.REDACT,
        redact_entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"],
    ),
    PolicyRule(
        id="permit-level0",
        name="Permit Level 0",
        description="Public information permitted without modification",
        priority=10,
        conditions={"sensitivity_max": 0},
        action=FirewallAction.PERMIT,
    ),
]


class PrivacyFirewall:
    """
    The Privacy Firewall - core enforcement mechanism.
    
    Processes memories through the full pipeline:
    1. Classification (confirm/upgrade sensitivity)
    2. Rule matching (find applicable policy)
    3. Redaction (apply PII pipeline)
    4. Consent gating (pause for user approval)
    5. Context formatting (prepare for LLM)
    
    Usage:
        firewall = PrivacyFirewall()
        decision = await firewall.process(memories, provider="openai")
        
        if decision.has_pending_consent:
            # Handle consent requests
            pass
        
        context = decision.context_text  # Use in LLM prompt
    """
    
    def __init__(
        self,
        classifier: Optional[SensitivityClassifier] = None,
        redactor: Optional[PIIRedactor] = None,
        rules: Optional[List[PolicyRule]] = None,
        consent_handler: Optional[Callable[[ConsentRequest], Awaitable[ConsentStatus]]] = None,
        dp_enabled: bool = True,
        dp_epsilon: float = 2.0,
    ):
        """
        Initialize the Privacy Firewall.
        
        Args:
            classifier: SensitivityClassifier instance
            redactor: PIIRedactor instance
            rules: List of PolicyRule objects (uses defaults if None)
            consent_handler: Async function to handle consent requests
        """
        self._classifier = classifier
        self._redactor = redactor
        self.rules = sorted(rules or DEFAULT_RULES, key=lambda r: r.priority, reverse=True)
        self.consent_handler = consent_handler
        self.dp_enabled = dp_enabled
        self.dp_epsilon = max(dp_epsilon, 1e-6)
        
        # Pending consent requests
        self._pending_consents: Dict[str, ConsentRequest] = {}

    def _laplace_noise(self, scale: float) -> float:
        """Sample Laplace(0, scale) using inverse transform sampling."""
        u = random.random() - 0.5
        return -scale * math.copysign(math.log(1 - 2 * abs(u)), u)
    
    @property
    def classifier(self) -> SensitivityClassifier:
        """Get the sensitivity classifier."""
        if self._classifier is None:
            self._classifier = SensitivityClassifier()
        return self._classifier
    
    @property
    def redactor(self) -> PIIRedactor:
        """Get the PII redactor."""
        if self._redactor is None:
            self._redactor = PIIRedactor()
        return self._redactor
    
    def add_rule(self, rule: PolicyRule) -> None:
        """Add a policy rule and re-sort by priority."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID. Returns True if found."""
        for i, rule in enumerate(self.rules):
            if rule.id == rule_id:
                del self.rules[i]
                return True
        return False
    
    def get_rules(self) -> List[PolicyRule]:
        """Get all active rules."""
        return [r for r in self.rules if r.enabled]
    
    async def process(
        self,
        memories: List[Dict[str, Any]],
        provider: str,
        query: Optional[str] = None,
    ) -> FirewallDecision:
        """
        Process memories through the privacy firewall.
        
        Args:
            memories: List of memory dictionaries from the vault
            provider: Target LLM provider (e.g., "openai", "ollama")
            query: Original user query (for context)
            
        Returns:
            FirewallDecision with processed memories and context
        """
        request_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)
        active_rules = self.get_rules()
        
        # Convert to MemoryContext objects
        contexts: List[MemoryContext] = []
        for mem in memories:
            score = mem.get("score")
            noisy_score = score
            if self.dp_enabled and isinstance(score, (int, float)):
                # Step 13: add Laplacian noise to retrieval scores
                # Lower epsilon => more noise, higher privacy.
                noisy_score = float(score) + self._laplace_noise(scale=1.0 / self.dp_epsilon)

            metadata = mem.get("metadata") or {}

            ctx = MemoryContext(
                memory_id=mem.get("id", str(uuid.uuid4())),
                content=mem.get("memory", mem.get("content", "")),
                sensitivity=mem.get("sensitivity", 1),
                tags=mem.get("tags", []),
                source=mem.get("source", "conversation"),
                metadata={**metadata, "score": noisy_score},
            )
            contexts.append(ctx)
        
        # Process each memory
        permitted: List[MemoryContext] = []
        blocked: List[MemoryContext] = []
        consent_required: List[MemoryContext] = []
        rules_evaluated: List[str] = []
        seen_rules: set[str] = set()
        total_redactions = 0
        
        for ctx in contexts:
            # Stage 1: Classify
            ctx.classification = self.classifier.classify(ctx.content, ctx.tags)
            
            # Stage 2: Find matching rule
            matched_rule: Optional[PolicyRule] = None
            for rule in active_rules:
                if rule.matches(ctx, provider):
                    matched_rule = rule
                    ctx.rule_matched = rule.id
                    if rule.id not in seen_rules:
                        seen_rules.add(rule.id)
                        rules_evaluated.append(rule.id)
                    break
            
            # Stage 3: Determine action
            if matched_rule:
                ctx.action = matched_rule.action
            else:
                # Default based on sensitivity
                if ctx.effective_sensitivity >= 3:
                    ctx.action = FirewallAction.CONSENT_REQUIRED
                elif ctx.effective_sensitivity >= 2:
                    ctx.action = FirewallAction.BLOCK
                elif ctx.effective_sensitivity >= 1:
                    ctx.action = FirewallAction.REDACT
                else:
                    ctx.action = FirewallAction.PERMIT
            
            # Stage 4: Apply action
            if ctx.action == FirewallAction.BLOCK:
                blocked.append(ctx)
                continue
            
            if ctx.action == FirewallAction.CONSENT_REQUIRED:
                # Create consent request
                ctx.consent_id = str(uuid.uuid4())
                ctx.consent_status = ConsentStatus.PENDING
                ctx.consent_reason = f"Sensitivity Level {ctx.effective_sensitivity} requires consent"
                
                # Try to get consent if handler provided
                if self.consent_handler:
                    consent_req = self._create_consent_request(ctx, provider)
                    try:
                        status = await self.consent_handler(consent_req)
                        ctx.consent_status = status
                        
                        if status in (ConsentStatus.APPROVED, ConsentStatus.APPROVED_REDACTED):
                            # Apply redaction if approved with redaction
                            if status == ConsentStatus.APPROVED_REDACTED:
                                ctx.redaction = self.redactor.redact(ctx.content)
                                ctx.processed_content = ctx.redaction.redacted_text
                                total_redactions += ctx.redaction.redaction_count
                            else:
                                ctx.processed_content = ctx.content
                            
                            ctx.action = FirewallAction.PERMIT
                            permitted.append(ctx)
                        elif status == ConsentStatus.DENIED:
                            ctx.action = FirewallAction.BLOCK
                            blocked.append(ctx)
                        else:
                            # Still pending
                            consent_required.append(ctx)
                            self._pending_consents[ctx.consent_id] = consent_req
                    except Exception as e:
                        logger.error(f"Consent handler error: {e}")
                        consent_required.append(ctx)
                else:
                    # No handler - add to pending
                    consent_required.append(ctx)
                
                continue
            
            if ctx.action == FirewallAction.REDACT:
                # Apply redaction
                entities_to_redact = None
                if matched_rule and matched_rule.redact_entities:
                    entities_to_redact = matched_rule.redact_entities
                
                ctx.redaction = self.redactor.redact(
                    ctx.content,
                    entities_to_redact=entities_to_redact,
                )
                ctx.processed_content = ctx.redaction.redacted_text
                total_redactions += ctx.redaction.redaction_count
                permitted.append(ctx)
                continue
            
            # PERMIT - use original content
            ctx.processed_content = ctx.content
            permitted.append(ctx)
        
        # Stage 5: Build context text
        context_parts = []
        for ctx in permitted:
            content = ctx.processed_content or ctx.content
            context_parts.append(f"[Memory: {ctx.memory_id[:8]}]\n{content}")
        
        context_text = "\n\n".join(context_parts)
        
        return FirewallDecision(
            request_id=request_id,
            provider=provider,
            timestamp=timestamp,
            permitted=permitted,
            blocked=blocked,
            consent_required=consent_required,
            context_text=context_text,
            total_memories=len(contexts),
            redaction_count=total_redactions,
            rules_evaluated=rules_evaluated,
        )
    
    def process_sync(
        self,
        memories: List[Dict[str, Any]],
        provider: str,
        query: Optional[str] = None,
    ) -> FirewallDecision:
        """
        Synchronous version of process().
        
        Note: Consent handling requires an event loop.
        This version blocks pending consents without resolving them.
        """
        import asyncio
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop is None:
            return asyncio.run(self.process(memories, provider, query))
        else:
            # Already in async context - cannot use run_until_complete.
            # Reuse a dedicated thread to run the coroutine.
            return _SYNC_EXECUTOR.submit(
                asyncio.run, self.process(memories, provider, query)
            ).result()
    
    def _create_consent_request(
        self, 
        ctx: MemoryContext, 
        provider: str
    ) -> ConsentRequest:
        """Create a consent request for a memory."""
        # Get proposed redactions
        proposed = self.redactor.redact(ctx.content)
        
        return ConsentRequest(
            id=ctx.consent_id or str(uuid.uuid4()),
            memory_id=ctx.memory_id,
            content=ctx.content,
            content_hash=ctx.content_hash,
            sensitivity=ctx.effective_sensitivity,
            tags=ctx.tags,
            provider=provider,
            proposed_redactions=[m.to_dict() for m in proposed.mappings],
            reason=ctx.consent_reason or "Consent required",
            created_at=datetime.now(timezone.utc),
        )
    
    def get_pending_consents(self) -> List[ConsentRequest]:
        """Get all pending consent requests."""
        return list(self._pending_consents.values())
    
    def resolve_consent(
        self, 
        consent_id: str, 
        decision: ConsentStatus
    ) -> bool:
        """
        Resolve a pending consent request.
        
        Returns True if the consent was found and resolved.
        """
        if consent_id in self._pending_consents:
            request = self._pending_consents[consent_id]
            request.status = decision
            
            if decision in (ConsentStatus.APPROVED, ConsentStatus.DENIED, 
                           ConsentStatus.APPROVED_REDACTED):
                # Remove from pending
                del self._pending_consents[consent_id]
            
            return True
        return False
    
    def evaluate_memory(
        self,
        memory: Dict[str, Any],
        provider: str,
    ) -> MemoryContext:
        """
        Evaluate a single memory without full processing.
        
        Useful for previewing what would happen to a memory.
        """
        ctx = MemoryContext(
            memory_id=memory.get("id", "preview"),
            content=memory.get("memory", memory.get("content", "")),
            sensitivity=memory.get("sensitivity", 1),
            tags=memory.get("tags", []),
            source=memory.get("source", "manual"),
        )
        
        # Classify
        ctx.classification = self.classifier.classify(ctx.content, ctx.tags)
        
        # Find matching rule
        for rule in self.get_rules():
            if rule.matches(ctx, provider):
                ctx.rule_matched = rule.id
                ctx.action = rule.action
                break
        else:
            # Default action
            if ctx.effective_sensitivity >= 3:
                ctx.action = FirewallAction.CONSENT_REQUIRED
            elif ctx.effective_sensitivity >= 2:
                ctx.action = FirewallAction.BLOCK
            else:
                ctx.action = FirewallAction.PERMIT
        
        # Preview redaction
        if ctx.action in (FirewallAction.REDACT, FirewallAction.CONSENT_REQUIRED):
            ctx.redaction = self.redactor.redact(ctx.content)
        
        return ctx
    
    def test_rule(
        self,
        rule: PolicyRule,
        test_memories: List[Dict[str, Any]],
        provider: str,
    ) -> List[Dict]:
        """
        Test a rule against sample memories.
        
        Returns list of {memory_id, matches, would_action} dicts.
        """
        results = []
        
        for mem in test_memories:
            ctx = MemoryContext(
                memory_id=mem.get("id", "test"),
                content=mem.get("memory", mem.get("content", "")),
                sensitivity=mem.get("sensitivity", 1),
                tags=mem.get("tags", []),
            )
            ctx.classification = self.classifier.classify(ctx.content, ctx.tags)
            
            matches = rule.matches(ctx, provider)
            
            results.append({
                "memory_id": ctx.memory_id,
                "sensitivity": ctx.effective_sensitivity,
                "matches": matches,
                "would_action": rule.action.value if matches else None,
            })
        
        return results


# Convenience functions

def create_firewall(**kwargs) -> PrivacyFirewall:
    """Create a new PrivacyFirewall instance with defaults."""
    return PrivacyFirewall(**kwargs)


def quick_evaluate(
    content: str,
    provider: str = "openai",
    tags: Optional[List[str]] = None,
) -> Dict:
    """
    Quick evaluation of what would happen to content.
    
    Returns a summary dict with sensitivity, action, and redactions.
    """
    firewall = PrivacyFirewall()
    
    memory = {
        "id": "quick-eval",
        "content": content,
        "sensitivity": 1,
        "tags": tags or [],
    }
    
    ctx = firewall.evaluate_memory(memory, provider)
    
    return {
        "sensitivity": ctx.effective_sensitivity,
        "action": ctx.action.value,
        "rule_matched": ctx.rule_matched,
        "requires_consent": ctx.action == FirewallAction.CONSENT_REQUIRED,
        "would_block": ctx.action == FirewallAction.BLOCK,
        "would_redact": ctx.redaction.was_modified if ctx.redaction else False,
        "redactions": ctx.redaction.redaction_count if ctx.redaction else 0,
    }
