"""
Health and status endpoints for closedclaw.

Provides system health checks and status information.
"""

from datetime import datetime, timezone
from typing import Optional, Any, Dict

from fastapi import APIRouter, Depends, Request

from closedclaw.api import __version__
from closedclaw.api.core.config import Settings, get_settings
from closedclaw.api.core.memory import ClosedclawMemory
from closedclaw.api.deps import get_memory, get_optional_auth_token

router = APIRouter(tags=["Health"])

_MEMORY_STATUS_CACHE: Dict[str, Any] = {
    "expires_at": 0.0,
    "payload": None,
}
_MEMORY_STATUS_CACHE_TTL_SECONDS = 3.0


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/v1/status")
async def get_status(
    request: Request,
    settings: Settings = Depends(get_settings),
    memory: ClosedclawMemory = Depends(get_memory),
    token: Optional[str] = Depends(get_optional_auth_token),
):
    """
    Get system status and statistics.
    
    Returns:
        System status including version, provider config, and memory stats.
    """
    # Basic status
    status: Dict[str, Any] = {
        "status": "operational",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    # Provider info
    status["provider"] = {
        "name": settings.provider,
        "default_model": settings.default_model,
        "local_model": settings.local_model if settings.provider == "ollama" else None,
    }
    
    # Privacy settings
    status["privacy"] = {
        "encryption_enabled": settings.enable_encryption,
        "redaction_enabled": settings.enable_redaction,
        "consent_required_level": settings.require_consent_level,
        "local_only_level": settings.local_only_level,
    }

    startup_info = getattr(request.app.state, "startup_info", None)
    if isinstance(startup_info, dict):
        status["runtime"] = {
            "startup_duration_ms": startup_info.get("startup_duration_ms"),
            "degraded_mode": startup_info.get("degraded_mode", False),
            "degraded_reason": startup_info.get("degraded_reason"),
            "fast_startup": startup_info.get("fast_startup", False),
            "provider": startup_info.get("provider"),
            "local_engine": startup_info.get("local_engine"),
        }
    
    # Memory stats (only if authenticated)
    if token:
        try:
            import time

            now = time.time()
            if (
                _MEMORY_STATUS_CACHE["payload"] is not None
                and _MEMORY_STATUS_CACHE["expires_at"] > now
            ):
                status["memory"] = _MEMORY_STATUS_CACHE["payload"]
            else:
                all_memories = memory.get_all(user_id="default")
                memories_list = all_memories.get("results", [])
                
                # Count by sensitivity
                sensitivity_counts = {0: 0, 1: 0, 2: 0, 3: 0}
                for mem in memories_list:
                    level = mem.get("sensitivity", 0)
                    sensitivity_counts[level] = sensitivity_counts.get(level, 0) + 1
                
                memory_payload = {
                    "total_memories": len(memories_list),
                    "by_sensitivity": sensitivity_counts,
                    "tags": memory.get_tags(),
                }
                _MEMORY_STATUS_CACHE["payload"] = memory_payload
                _MEMORY_STATUS_CACHE["expires_at"] = now + _MEMORY_STATUS_CACHE_TTL_SECONDS
                status["memory"] = memory_payload
        except Exception:
            status["memory"] = {
                "total_memories": 0,
                "error": "Unable to fetch memory stats"
            }
    
    return status


@router.get("/")
async def root():
    """
    Root endpoint - redirects to API docs.
    """
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


@router.get("/v1/info")
async def get_info():
    """Get basic API information."""
    return {
        "name": "closedclaw",
        "description": "Privacy-first AI memory middleware",
        "version": __version__,
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
        "endpoints": {
            "memory": "/v1/memory",
            "proxy": "/v1/chat/completions",
            "consent": "/v1/consent",
            "audit": "/v1/audit",
            "status": "/v1/status",
        }
    }
