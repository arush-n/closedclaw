"""
Addon API routes — browser extension registration, auth, and context processing.

Endpoints:
  POST /addon/register   — register addon Ed25519 public key, get challenge
  POST /addon/auth       — sign challenge, get session token
  POST /addon/process    — main pipeline: enriched prompt + redaction
  POST /addon/memory/capture — explicit memory save from extension
  GET  /addon/memory/query   — search memories from extension popup
  GET  /addon/status     — health + active rules count
  POST /addon/logout     — revoke session

  DELETE /server/shutdown — password-gated server shutdown
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from closedclaw.api.core.addon_auth import AddonSession, get_addon_session_manager
from closedclaw.api.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Addon"])


# ── Request / Response Models ────────────────────────────────────────

class AddonRegisterRequest(BaseModel):
    addon_pubkey: str = Field(..., description="Base64-encoded raw Ed25519 public key (32 bytes)")


class AddonRegisterResponse(BaseModel):
    addon_id: str
    session_challenge: str


class AddonAuthRequest(BaseModel):
    session_challenge: str = Field(..., description="Challenge from /addon/register")
    signature: str = Field(..., description="Ed25519 signature of the challenge bytes (base64)")


class AddonAuthResponse(BaseModel):
    session_token: str
    addon_id: str
    expires_in: int


class AddonProcessRequest(BaseModel):
    text: str = Field(..., description="User input text to enrich with memory context")
    provider: str = Field(default="ollama", description="Target AI provider")
    user_id: str = Field(default="default")
    site: str = Field(default="unknown", description="Site the addon is running on")


class AddonProcessResponse(BaseModel):
    enriched_prompt: str = ""
    context_text: str = ""
    redaction_count: int = 0
    consent_required: bool = False
    consent_memories: list = Field(default_factory=list)
    audit_id: Optional[str] = None
    rules_applied: int = 0


class MemoryCaptureRequest(BaseModel):
    content: str = Field(..., description="Memory content to store")
    tags: list[str] = Field(default_factory=list)
    sensitivity: int = Field(default=1, ge=0, le=3)
    source: str = Field(default="addon")
    user_id: str = Field(default="default")


class MemoryQueryRequest(BaseModel):
    query: str = Field(..., description="Search query")
    user_id: str = Field(default="default")
    limit: int = Field(default=10, ge=1, le=50)


class ShutdownRequest(BaseModel):
    password: str = Field(..., description="Shutdown password")


# ── Addon Session Dependency ─────────────────────────────────────────

async def require_addon_session(
    x_addon_session: Optional[str] = Header(None, alias="X-Addon-Session"),
) -> AddonSession:
    """Validate the addon session token from the X-Addon-Session header."""
    if not x_addon_session:
        raise HTTPException(status_code=401, detail="Missing X-Addon-Session header")

    manager = get_addon_session_manager()
    session = manager.validate_session(x_addon_session)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired addon session")

    return session


# ── Registration & Auth ──────────────────────────────────────────────

@router.post("/addon/register", response_model=AddonRegisterResponse)
async def addon_register(req: AddonRegisterRequest):
    """Register a browser addon's Ed25519 public key and receive a challenge."""
    manager = get_addon_session_manager()
    try:
        result = manager.register_addon(req.addon_pubkey)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AddonRegisterResponse(**result)


@router.post("/addon/auth", response_model=AddonAuthResponse)
async def addon_auth(req: AddonAuthRequest):
    """Authenticate by signing the challenge. Returns a session token."""
    manager = get_addon_session_manager()
    try:
        result = manager.authenticate(req.session_challenge, req.signature)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return AddonAuthResponse(**result)


@router.post("/addon/logout")
async def addon_logout(session: AddonSession = Depends(require_addon_session)):
    """Revoke the current addon session."""
    manager = get_addon_session_manager()
    manager.revoke_session(session.session_token or "")
    return {"status": "logged_out", "addon_id": session.addon_id}


# ── Context Processing ───────────────────────────────────────────────

@router.post("/addon/process", response_model=AddonProcessResponse)
async def addon_process(
    req: AddonProcessRequest,
    session: AddonSession = Depends(require_addon_session),
    settings: Settings = Depends(get_settings),
):
    """Main addon pipeline: retrieve memories, apply governance, build enriched prompt.

    This endpoint runs the ADDON_PROCESS swarm pipeline if swarm is enabled,
    otherwise falls back to a simpler memory search + redaction pass.
    """
    from closedclaw.api.deps import get_swarm_coordinator

    coordinator = get_swarm_coordinator()

    if coordinator:
        # Run via swarm ADDON_PROCESS pipeline
        from closedclaw.api.agents.swarm.models import SwarmTask, SwarmTaskType

        task = SwarmTask(
            task_type=SwarmTaskType.ADDON_PROCESS,
            user_id=req.user_id,
            provider=req.provider,
            input_data={"query": req.text, "site": req.site},
            context={"addon_id": session.addon_id},
        )
        result = await coordinator.execute(task)
        output = result.output

        return AddonProcessResponse(
            enriched_prompt=output.get("system_prefix", "") + "\n" + req.text,
            context_text=output.get("context_text", ""),
            redaction_count=output.get("firewall_decision", {}).get("redaction_count", 0)
            if isinstance(output.get("firewall_decision"), dict)
            else 0,
            consent_required=result.status == "consent_required",
            consent_memories=output.get("consent_required", []),
            audit_id=result.task_id,
            rules_applied=len(output.get("active_rules", [])),
        )

    # Fallback: simple memory search + redaction (no swarm)
    return await _fallback_process(req, settings)


async def _fallback_process(
    req: AddonProcessRequest,
    settings: Settings,
) -> AddonProcessResponse:
    """Simple processing when swarm is not enabled."""
    from closedclaw.api.core.memory import get_memory_instance
    from closedclaw.api.privacy.redactor import PIIRedactor

    try:
        from closedclaw.api.deps import _build_mem0_config
        config = _build_mem0_config(settings)
        memory = get_memory_instance(config)
        results = memory.search(query=req.text, user_id=req.user_id, limit=5)
        if isinstance(results, dict):
            memories = results.get("results", [])
        else:
            memories = results or []
    except Exception:
        memories = []

    context_parts = []
    for m in memories[:5]:
        text = m.get("memory", m.get("content", "")) if isinstance(m, dict) else str(m)
        context_parts.append(text[:200])
    context_text = "\n".join(context_parts)

    # Redact for provider
    redaction_count = 0
    if context_text:
        try:
            redactor = PIIRedactor()
            result = redactor.redact_for_provider(context_text, provider=req.provider)
            context_text = result.redacted_text
            redaction_count = result.redaction_count
        except Exception:
            pass

    enriched = ""
    if context_text:
        enriched = f"[CONTEXT: {context_text}]\n\n{req.text}"
    else:
        enriched = req.text

    return AddonProcessResponse(
        enriched_prompt=enriched,
        context_text=context_text,
        redaction_count=redaction_count,
    )


# ── Memory Operations ────────────────────────────────────────────────

@router.post("/addon/memory/capture")
async def addon_memory_capture(
    req: MemoryCaptureRequest,
    session: AddonSession = Depends(require_addon_session),
    settings: Settings = Depends(get_settings),
):
    """Capture a new memory from the browser addon."""
    from closedclaw.api.core.memory import get_memory_instance

    try:
        from closedclaw.api.deps import _build_mem0_config
        config = _build_mem0_config(settings)
        memory = get_memory_instance(config)
        memory.add(
            content=req.content,
            user_id=req.user_id,
            sensitivity=req.sensitivity,
            tags=req.tags + ["source:addon"],
            source=req.source,
        )
        return {"status": "stored", "content_length": len(req.content)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Memory capture failed: {exc}")


@router.get("/addon/memory/query")
async def addon_memory_query(
    query: str,
    user_id: str = "default",
    limit: int = 10,
    session: AddonSession = Depends(require_addon_session),
    settings: Settings = Depends(get_settings),
):
    """Search memories from the extension popup."""
    from closedclaw.api.core.memory import get_memory_instance

    try:
        from closedclaw.api.deps import _build_mem0_config
        config = _build_mem0_config(settings)
        memory = get_memory_instance(config)
        results = memory.search(query=query, user_id=user_id, limit=min(limit, 50))
        if isinstance(results, dict):
            memories = results.get("results", [])
        else:
            memories = results or []
        return {"results": memories[:limit], "count": len(memories)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Memory query failed: {exc}")


# ── Status ───────────────────────────────────────────────────────────

@router.get("/addon/status")
async def addon_status(
    session: AddonSession = Depends(require_addon_session),
):
    """Get addon-relevant status: health, active rules, session info."""
    from closedclaw.api.deps import get_swarm_coordinator

    coordinator = get_swarm_coordinator()
    rules_count = 0
    if coordinator:
        try:
            rules_count = len(coordinator.constitution.schema.principles)
        except Exception:
            pass

    return {
        "status": "connected",
        "addon_id": session.addon_id,
        "session_expires_at": session.expires_at,
        "swarm_enabled": coordinator is not None,
        "active_rules": rules_count,
    }


# ── Server Shutdown ──────────────────────────────────────────────────

@router.delete("/server/shutdown")
async def server_shutdown(req: ShutdownRequest):
    """Password-gated server shutdown.

    Requires the shutdown password set during first boot
    (stored in ~/.closedclaw/shutdown.key.password).
    """
    from closedclaw.api.core.termination_lock import get_termination_lock

    lock = get_termination_lock()
    if not lock.unlock(req.password):
        raise HTTPException(status_code=403, detail="Invalid shutdown password")

    import os
    import signal

    logger.warning("Server shutdown authorized — sending SIGTERM")
    os.kill(os.getpid(), signal.SIGTERM)
    return {"status": "shutting_down"}
