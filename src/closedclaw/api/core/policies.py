"""
Closedclaw Privacy Policy Engine

Defines and evaluates privacy rules for memory access control.
"""

from typing import List, Dict, Any, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field


class PolicyAction(str, Enum):
    """Actions a policy can take."""
    PERMIT = "PERMIT"           # Allow memory to be used
    REDACT = "REDACT"           # Allow but redact PII
    BLOCK = "BLOCK"             # Block memory from being used
    CONSENT_REQUIRED = "CONSENT_REQUIRED"  # Require user consent


class PolicyConditions(BaseModel):
    """Conditions for a policy rule to match."""
    sensitivity_min: Optional[int] = Field(None, ge=0, le=3)
    sensitivity_max: Optional[int] = Field(None, ge=0, le=3)
    tags_include: Optional[List[str]] = None
    tags_exclude: Optional[List[str]] = None
    provider_is: Optional[List[str]] = None
    provider_not: Optional[List[str]] = None
    source_is: Optional[List[str]] = None
    source_not: Optional[List[str]] = None
    time_of_day: Optional[Dict[str, int]] = None  # {"start": 9, "end": 17}


class PolicyRule(BaseModel):
    """A single privacy policy rule."""
    id: str
    name: str
    description: Optional[str] = None
    priority: int = Field(default=50, ge=0, le=1000)
    enabled: bool = True
    conditions: PolicyConditions
    action: PolicyAction
    redact_entities: Optional[List[str]] = None  # For REDACT action


class PolicySet(BaseModel):
    """A collection of policy rules."""
    name: str
    description: Optional[str] = None
    rules: List[PolicyRule]


# Default policy rules shipped with closedclaw
DEFAULT_POLICIES = {
    "name": "default",
    "description": "Default closedclaw privacy policies",
    "rules": [
        {
            "id": "block-level3-cloud",
            "name": "Block Level 3 from cloud",
            "description": "Any sensitivity-3 memory is blocked from non-local providers",
            "priority": 90,
            "enabled": True,
            "conditions": {
                "sensitivity_min": 3,
                "provider_not": ["ollama"]
            },
            "action": "BLOCK"
        },
        {
            "id": "consent-level3",
            "name": "Consent gate on Level 3",
            "description": "Any Level 3 memory requires explicit per-request consent",
            "priority": 100,
            "enabled": True,
            "conditions": {
                "sensitivity_min": 3
            },
            "action": "CONSENT_REQUIRED"
        },
        {
            "id": "block-level2-cloud",
            "name": "Block Level 2 from cloud (soft default)",
            "description": "Level 2 memories blocked from cloud providers by default",
            "priority": 80,
            "enabled": True,
            "conditions": {
                "sensitivity_min": 2,
                "provider_not": ["ollama"]
            },
            "action": "BLOCK"
        },
        {
            "id": "redact-level1-names",
            "name": "Redact names on Level 1",
            "description": "Person names and emails are redacted from Level 1 memories",
            "priority": 50,
            "enabled": True,
            "conditions": {
                "sensitivity_min": 1,
                "sensitivity_max": 1
            },
            "action": "REDACT",
            "redact_entities": ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]
        },
        {
            "id": "block-health-cloud",
            "name": "Block health data from cloud",
            "description": "Health-tagged memories only allowed to local LLMs",
            "priority": 90,
            "enabled": True,
            "conditions": {
                "tags_include": ["health", "medical"],
                "provider_not": ["ollama"]
            },
            "action": "BLOCK"
        },
        {
            "id": "block-finance-cloud",
            "name": "Block financial data from cloud",
            "description": "Finance-tagged memories only allowed to local LLMs",
            "priority": 90,
            "enabled": True,
            "conditions": {
                "tags_include": ["finance", "financial", "banking"],
                "provider_not": ["ollama"]
            },
            "action": "BLOCK"
        },
        {
            "id": "permit-level0",
            "name": "Permit Level 0",
            "description": "Public memories are permitted to any provider",
            "priority": 10,
            "enabled": True,
            "conditions": {
                "sensitivity_max": 0
            },
            "action": "PERMIT"
        }
    ]
}


class PolicyEngine:
    """
    Evaluates privacy policies against memories.
    
    Rules are evaluated in priority order (highest first).
    First matching rule wins.
    """
    
    def __init__(self, policy_set: PolicySet):
        self.policy_set = policy_set
        # Sort rules by priority (descending)
        self.rules = sorted(
            [r for r in policy_set.rules if r.enabled],
            key=lambda r: r.priority,
            reverse=True
        )
    
    def evaluate(
        self,
        memory: Dict[str, Any],
        provider: str,
        context: Optional[Dict[str, Any]] = None
    ) -> tuple[PolicyAction, Optional[PolicyRule]]:
        """
        Evaluate a memory against the policy set.
        
        Args:
            memory: The memory object to evaluate
            provider: Target LLM provider
            context: Additional context (time, etc.)
        
        Returns:
            Tuple of (action, matching_rule)
        """
        for rule in self.rules:
            if self._matches(rule, memory, provider, context):
                return rule.action, rule
        
        # Default: permit if no rule matches
        return PolicyAction.PERMIT, None
    
    def _matches(
        self,
        rule: PolicyRule,
        memory: Dict[str, Any],
        provider: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if a rule matches the given memory and context."""
        cond = rule.conditions
        sensitivity = memory.get("sensitivity", 0)
        tags = set(memory.get("tags", []))
        source = memory.get("source", "conversation")
        
        # Check sensitivity range
        if cond.sensitivity_min is not None and sensitivity < cond.sensitivity_min:
            return False
        if cond.sensitivity_max is not None and sensitivity > cond.sensitivity_max:
            return False
        
        # Check tags
        if cond.tags_include:
            if not tags.intersection(set(cond.tags_include)):
                return False
        if cond.tags_exclude:
            if tags.intersection(set(cond.tags_exclude)):
                return False
        
        # Check provider
        if cond.provider_is and provider not in cond.provider_is:
            return False
        if cond.provider_not and provider in cond.provider_not:
            return False
        
        # Check source
        if cond.source_is and source not in cond.source_is:
            return False
        if cond.source_not and source in cond.source_not:
            return False
        
        # Check time of day (if context provided)
        if cond.time_of_day and context:
            from datetime import datetime
            hour = context.get("hour", datetime.now().hour)
            start = cond.time_of_day.get("start", 0)
            end = cond.time_of_day.get("end", 24)
            if not (start <= hour < end):
                return False
        
        return True
    
    def get_redact_entities(self, rule: Optional[PolicyRule]) -> List[str]:
        """Get list of entity types to redact for a REDACT action."""
        if rule and rule.action == PolicyAction.REDACT and rule.redact_entities:
            return rule.redact_entities
        # Default entities to redact
        return ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]


def load_policies(policies_dir) -> PolicyEngine:
    """Load all policy files from the policies directory."""
    import json
    from pathlib import Path
    
    policies_dir = Path(policies_dir)
    all_rules = []
    
    for policy_file in policies_dir.glob("*.json"):
        with open(policy_file) as f:
            policy_data = json.load(f)
            policy_set = PolicySet(**policy_data)
            all_rules.extend(policy_set.rules)
    
    # If no policies found, use defaults
    if not all_rules:
        policy_set = PolicySet(**DEFAULT_POLICIES)
    else:
        policy_set = PolicySet(
            name="combined",
            description="Combined policies from all files",
            rules=all_rules
        )
    
    # Normalize critical precedence so consent gates are reachable even with stale local policy files.
    rule_by_id = {rule.id: rule for rule in policy_set.rules}
    consent_rule = rule_by_id.get("consent-level3")
    block_l3_rule = rule_by_id.get("block-level3-cloud")
    if consent_rule and block_l3_rule and consent_rule.priority <= block_l3_rule.priority:
        consent_rule.priority = block_l3_rule.priority + 1

    return PolicyEngine(policy_set)
