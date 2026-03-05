"""
Closedclaw Integration Middleware for Openclaw

This middleware runs INSIDE the openclaw Docker container and intercepts:
1. Memory writes — screens them through the control bridge's memory guardian
2. External URL access — checks against restricted app policies
3. MCP tool calls — routes restricted services through controlled MCPs

Install by adding to openclaw's startup configuration.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("closedclaw_middleware")

BRIDGE_URL = os.getenv("CLOSEDCLAW_BRIDGE_URL", "http://control-bridge:9000")
BRIDGE_ENABLED = os.getenv("CLOSEDCLAW_BRIDGE_ENABLED", "true").lower() in (
    "1", "true", "yes",
)

_http: Optional[httpx.AsyncClient] = None


async def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=30.0)
    return _http


# ---------------------------------------------------------------------------
# Memory Screening
# ---------------------------------------------------------------------------

async def screen_memory_write(
    content: str,
    user_id: str = "default-user",
    metadata: Optional[Dict] = None,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Screen a memory write through the closedclaw control bridge.

    Returns:
        {
            "allowed": bool,
            "action": "allow" | "block" | "redact_and_store",
            "content": str,  # Original or redacted content
            "reason": str | None,
        }
    """
    if not BRIDGE_ENABLED:
        return {"allowed": True, "action": "allow", "content": content}

    try:
        http = await _get_http()
        resp = await http.post(
            f"{BRIDGE_URL}/memory/screen",
            json={
                "content": content,
                "user_id": user_id,
                "metadata": metadata or {},
                "categories": categories or [],
            },
        )
        if resp.status_code == 200:
            result = resp.json()
            if not result.get("allowed", True):
                logger.warning(
                    "Memory write BLOCKED by closedclaw: %s",
                    result.get("reason", "unknown"),
                )
            return result
    except Exception as exc:
        logger.error("Bridge memory screening failed: %s", exc)

    # Fail open if bridge is unreachable (configurable)
    return {"allowed": True, "action": "allow", "content": content}


async def classify_memory(
    content: str,
    user_id: str = "default-user",
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Classify a memory's sensitivity level through the bridge."""
    if not BRIDGE_ENABLED:
        return {"sensitivity": 1, "sensitive_categories_detected": []}

    try:
        http = await _get_http()
        resp = await http.post(
            f"{BRIDGE_URL}/memory/classify",
            json={
                "content": content,
                "user_id": user_id,
                "categories": categories or [],
            },
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.error("Bridge classification failed: %s", exc)

    return {"sensitivity": 1, "sensitive_categories_detected": []}


# ---------------------------------------------------------------------------
# URL Access Control
# ---------------------------------------------------------------------------

_restricted_apps_cache: Optional[Dict] = None
_cache_ts: float = 0


async def _load_restricted_apps() -> Dict:
    """Load restricted app policies from the bridge (cached 5 min)."""
    global _restricted_apps_cache, _cache_ts

    if _restricted_apps_cache and time.time() - _cache_ts < 300:
        return _restricted_apps_cache

    try:
        http = await _get_http()
        resp = await http.get(f"{BRIDGE_URL}/config/restricted-apps")
        if resp.status_code == 200:
            _restricted_apps_cache = resp.json()
            _cache_ts = time.time()
            return _restricted_apps_cache
    except Exception as exc:
        logger.error("Failed to load restricted apps: %s", exc)

    return _restricted_apps_cache or {}


async def check_url_access(url: str) -> Dict[str, Any]:
    """Check if a URL is restricted before accessing it.

    Returns:
        {
            "allowed": bool,
            "service": str | None,
            "reason": str | None,
            "suggestion": str | None,
        }
    """
    if not BRIDGE_ENABLED:
        return {"allowed": True}

    try:
        http = await _get_http()
        resp = await http.post(
            f"{BRIDGE_URL}/proxy/check-url",
            json={"url": url},
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.error("URL access check failed: %s", exc)

    return {"allowed": True}


# ---------------------------------------------------------------------------
# Controlled MCP Access
# ---------------------------------------------------------------------------

async def call_controlled_mcp(
    service: str,
    operation: str,
    params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Call a controlled MCP service through the bridge.

    Instead of openclaw accessing gmail/calendar/files directly,
    this routes through closedclaw's controlled MCP endpoints.
    """
    if not BRIDGE_ENABLED:
        return {"error": "Bridge not enabled"}

    try:
        http = await _get_http()
        resp = await http.post(
            f"{BRIDGE_URL}/mcp/{service}",
            json={
                "service": service,
                "operation": operation,
                "params": params or {},
            },
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            error_detail = resp.json().get("detail", resp.text)
            logger.warning("MCP call denied: %s/%s — %s", service, operation, error_detail)
            return {"error": error_detail, "status_code": resp.status_code}
    except Exception as exc:
        logger.error("Controlled MCP call failed: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Bridge Health Check
# ---------------------------------------------------------------------------

async def check_bridge_health() -> Dict[str, Any]:
    """Check if the control bridge is healthy and closedclaw is reachable."""
    try:
        http = await _get_http()
        resp = await http.get(f"{BRIDGE_URL}/health", timeout=5.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        return {
            "status": "unreachable",
            "error": str(exc),
        }
    return {"status": "error"}


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

async def shutdown():
    """Clean up HTTP client."""
    global _http
    if _http:
        await _http.aclose()
        _http = None
