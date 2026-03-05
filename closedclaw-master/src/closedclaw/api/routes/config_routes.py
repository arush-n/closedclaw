"""
Closedclaw Config API Routes

GET  /v1/config  — returns config with API keys masked
PUT  /v1/config  — partial config updates (auth required)
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from closedclaw.api.core.config import get_settings, clear_settings_cache, Settings
from closedclaw.api.deps import get_auth_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/config", tags=["Config"])

# Fields that should be masked in GET responses
_MASK = "••••••••"
_MASKED_FIELDS = {"openai_api_key", "anthropic_api_key", "groq_api_key", "together_api_key"}


def _mask_sensitive(data: Dict[str, Any]) -> Dict[str, Any]:
    """Replace sensitive values with a mask, preserving last 4 chars."""
    out = dict(data)
    for field in _MASKED_FIELDS:
        val = out.get(field)
        if val and isinstance(val, str) and len(val) > 4:
            out[field] = _MASK + val[-4:]
        elif val:
            out[field] = _MASK
    return out


@router.get("")
async def get_config(token: str = Depends(get_auth_token)):
    """Return current config with sensitive fields masked."""
    settings = get_settings()
    data = settings.model_dump(exclude={"auth_token"}, exclude_none=True)

    # Convert Path objects to strings
    for key, value in data.items():
        from pathlib import Path
        if isinstance(value, Path):
            data[key] = str(value)

    data = _mask_sensitive(data)
    return data


class ConfigUpdate(BaseModel):
    """Partial config update payload."""
    provider: str | None = None
    default_model: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    groq_api_key: str | None = None
    groq_base_url: str | None = None
    together_api_key: str | None = None
    together_base_url: str | None = None
    ollama_base_url: str | None = None
    default_sensitivity: int | None = None
    require_consent_level: int | None = None
    enable_redaction: bool | None = None


@router.put("")
async def update_config(body: ConfigUpdate, token: str = Depends(get_auth_token)):
    """Update config fields. Only non-None fields are applied."""
    settings = get_settings()

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_changes"}

    for key, value in updates.items():
        if hasattr(settings, key):
            setattr(settings, key, value)

    settings.save()
    clear_settings_cache()

    return {"status": "ok", "updated_fields": list(updates.keys())}
