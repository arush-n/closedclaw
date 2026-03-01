"""
Policy management endpoints for closedclaw.

Provides CRUD APIs and test evaluation for privacy policy rules.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from closedclaw.api.core.config import get_settings, Settings
from closedclaw.api.core.policies import (
    PolicyRule,
    PolicySet,
    PolicyAction,
    PolicyConditions,
    DEFAULT_POLICIES,
)
from closedclaw.api.deps import get_auth_token, reload_policy_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/policies", tags=["Policies"])

CUSTOM_POLICY_FILE = "custom.json"


class PolicyCreateRequest(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    priority: int = Field(default=50, ge=0, le=1000)
    enabled: bool = True
    conditions: PolicyConditions
    action: PolicyAction
    redact_entities: Optional[List[str]] = None


class PolicyUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=0, le=1000)
    enabled: Optional[bool] = None
    conditions: Optional[PolicyConditions] = None
    action: Optional[PolicyAction] = None
    redact_entities: Optional[List[str]] = None


class PolicyTestRequest(BaseModel):
    memory_text: str = Field(..., min_length=1, max_length=10000)
    sensitivity: int = Field(default=1, ge=0, le=3)
    tags: List[str] = Field(default_factory=list)
    source: str = "conversation"
    provider: str = "openai"


class PolicyListResponse(BaseModel):
    rules: List[PolicyRule]
    total: int


class PolicyMutationResponse(BaseModel):
    success: bool
    rule: Optional[PolicyRule] = None
    message: str


class PolicyTestResponse(BaseModel):
    action: PolicyAction
    matched_rule: Optional[PolicyRule] = None
    memory_preview: str


def _custom_policy_path(settings: Settings) -> Path:
    return settings.policies_dir / CUSTOM_POLICY_FILE


def _default_policy_set() -> PolicySet:
    return PolicySet(**DEFAULT_POLICIES)


def _load_custom_policy_set(settings: Settings) -> PolicySet:
    custom_path = _custom_policy_path(settings)
    if not custom_path.exists():
        return PolicySet(name="custom", description="User-defined policy rules", rules=[])

    try:
        with open(custom_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return PolicySet(**payload)
    except Exception as exc:
        logger.warning(f"Failed loading custom policies from {custom_path}: {exc}")
        return PolicySet(name="custom", description="User-defined policy rules", rules=[])


def _save_custom_policy_set(settings: Settings, policy_set: PolicySet) -> None:
    settings.policies_dir.mkdir(parents=True, exist_ok=True)
    custom_path = _custom_policy_path(settings)
    with open(custom_path, "w", encoding="utf-8") as handle:
        json.dump(policy_set.model_dump(mode="json"), handle, indent=2)


def _combined_rules(settings: Settings) -> List[PolicyRule]:
    default_rules = _default_policy_set().rules
    custom_rules = _load_custom_policy_set(settings).rules

    by_id: Dict[str, PolicyRule] = {rule.id: rule for rule in default_rules}
    for custom_rule in custom_rules:
        by_id[custom_rule.id] = custom_rule

    return sorted(by_id.values(), key=lambda rule: rule.priority, reverse=True)


@router.get("", response_model=PolicyListResponse)
async def list_policies(
    token: str = Depends(get_auth_token),
    settings: Settings = Depends(get_settings),
):
    """List active policy rules (defaults + custom overrides)."""
    rules = _combined_rules(settings)
    return PolicyListResponse(rules=rules, total=len(rules))


@router.post("", response_model=PolicyMutationResponse)
async def create_policy(
    payload: PolicyCreateRequest,
    token: str = Depends(get_auth_token),
    settings: Settings = Depends(get_settings),
):
    """Create or replace a custom policy rule."""
    custom_set = _load_custom_policy_set(settings)
    rule_id = payload.id or payload.name.lower().strip().replace(" ", "-")

    rule = PolicyRule(
        id=rule_id,
        name=payload.name,
        description=payload.description,
        priority=payload.priority,
        enabled=payload.enabled,
        conditions=payload.conditions,
        action=payload.action,
        redact_entities=payload.redact_entities,
    )

    existing_idx = next((i for i, item in enumerate(custom_set.rules) if item.id == rule.id), None)
    if existing_idx is None:
        custom_set.rules.append(rule)
        message = f"Created policy '{rule.id}'"
    else:
        custom_set.rules[existing_idx] = rule
        message = f"Replaced policy '{rule.id}'"

    _save_custom_policy_set(settings, custom_set)
    reload_policy_engine(settings)

    # Audit logging for policy mutation
    try:
        from closedclaw.api.routes.audit import add_audit_entry
        import uuid
        add_audit_entry(
            request_id=f"policy-create-{uuid.uuid4()}",
            provider="local",
            model="policy-engine",
            query_summary=f"Policy {message}: action={rule.action}, priority={rule.priority}",
        )
    except Exception as e:
        logger.warning(f"Policy create audit logging failed: {e}")

    return PolicyMutationResponse(success=True, rule=rule, message=message)


@router.put("/{policy_id}", response_model=PolicyMutationResponse)
async def update_policy(
    policy_id: str,
    payload: PolicyUpdateRequest,
    token: str = Depends(get_auth_token),
    settings: Settings = Depends(get_settings),
):
    """Update an existing custom policy rule."""
    custom_set = _load_custom_policy_set(settings)

    index = next((i for i, item in enumerate(custom_set.rules) if item.id == policy_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail=f"Custom policy '{policy_id}' not found")

    existing = custom_set.rules[index]
    merged = existing.model_dump()
    for key, value in payload.model_dump(exclude_unset=True).items():
        merged[key] = value

    updated = PolicyRule(**merged)
    custom_set.rules[index] = updated

    _save_custom_policy_set(settings, custom_set)
    reload_policy_engine(settings)

    # Audit logging for policy update
    try:
        from closedclaw.api.routes.audit import add_audit_entry
        import uuid
        add_audit_entry(
            request_id=f"policy-update-{uuid.uuid4()}",
            provider="local",
            model="policy-engine",
            query_summary=f"Policy updated: '{policy_id}', fields={list(payload.model_dump(exclude_unset=True).keys())}",
        )
    except Exception as e:
        logger.warning(f"Policy update audit logging failed: {e}")

    return PolicyMutationResponse(
        success=True,
        rule=updated,
        message=f"Updated policy '{policy_id}'",
    )


@router.delete("/{policy_id}", response_model=PolicyMutationResponse)
async def delete_policy(
    policy_id: str,
    token: str = Depends(get_auth_token),
    settings: Settings = Depends(get_settings),
):
    """Delete a custom policy rule by ID."""
    custom_set = _load_custom_policy_set(settings)

    index = next((i for i, item in enumerate(custom_set.rules) if item.id == policy_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail=f"Custom policy '{policy_id}' not found")

    removed = custom_set.rules.pop(index)

    _save_custom_policy_set(settings, custom_set)
    reload_policy_engine(settings)

    # Audit logging for policy deletion
    try:
        from closedclaw.api.routes.audit import add_audit_entry
        import uuid
        add_audit_entry(
            request_id=f"policy-delete-{uuid.uuid4()}",
            provider="local",
            model="policy-engine",
            query_summary=f"Policy deleted: '{policy_id}'",
        )
    except Exception as e:
        logger.warning(f"Policy delete audit logging failed: {e}")

    return PolicyMutationResponse(
        success=True,
        rule=removed,
        message=f"Deleted policy '{policy_id}'",
    )


@router.post("/test", response_model=PolicyTestResponse)
async def test_policy(
    payload: PolicyTestRequest,
    token: str = Depends(get_auth_token),
    settings: Settings = Depends(get_settings),
):
    """Evaluate a hypothetical memory against current policy rules."""
    engine = reload_policy_engine(settings)

    action, rule = engine.evaluate(
        memory={
            "memory": payload.memory_text,
            "sensitivity": payload.sensitivity,
            "tags": payload.tags,
            "source": payload.source,
        },
        provider=payload.provider,
    )

    preview = payload.memory_text if len(payload.memory_text) <= 160 else f"{payload.memory_text[:157]}..."

    return PolicyTestResponse(
        action=action,
        matched_rule=rule,
        memory_preview=preview,
    )
