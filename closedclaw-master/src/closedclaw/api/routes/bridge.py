"""
Bridge Routes — Host-side endpoints for MCP service access and control bridge.

These endpoints handle both:
  - Local operation: MCP connectors run in-process (no Docker needed)
  - Docker operation: control bridge proxies requests through these routes

MCP connectors (Gmail, Notion, Drive, Slack, GitHub) are loaded from
closedclaw.api.mcp_services and dispatched via the /v1/bridge/mcp/* routes.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Connector Registry — lazy-initialized singletons
# ---------------------------------------------------------------------------
_mcp_connectors: Dict[str, Any] = {}


def _get_connector(tool: str):
    """Get or create an MCP connector instance for the given tool."""
    if tool not in _mcp_connectors:
        from closedclaw.api.mcp_services import MCP_CONNECTORS

        connector_cls = MCP_CONNECTORS.get(tool)
        if not connector_cls:
            return None

        config = {
            "oauth_token": os.getenv("GOOGLE_OAUTH_TOKEN", ""),
            "bridge_url": "http://localhost:8765",
            "notion_api_key": os.getenv("NOTION_API_KEY", ""),
            "slack_bot_token": os.getenv("SLACK_BOT_TOKEN", ""),
            "github_token": os.getenv("GITHUB_TOKEN", ""),
        }
        _mcp_connectors[tool] = connector_cls(config)

    return _mcp_connectors[tool]

router = APIRouter(prefix="/v1/bridge", tags=["bridge"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class BridgeProxyRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Dict[str, str] = {}
    body: Any = None
    restricted_service: Optional[str] = None


class BridgeAuditEvent(BaseModel):
    event_type: str
    source: str = "control_bridge"
    details: Dict[str, Any] = {}


class MCPOperationRequest(BaseModel):
    operation: str
    params: Dict[str, Any] = {}
    source: str = "openclaw_bridge"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status")
async def bridge_status():
    """Status endpoint for the control bridge to verify host is alive."""
    return {
        "status": "ok",
        "service": "closedclaw-host",
        "timestamp": time.time(),
        "bridge_api_version": "1.0",
    }


@router.post("/proxy")
async def bridge_proxy(request: BridgeProxyRequest):
    """Proxy a request on behalf of openclaw (via the control bridge).

    The bridge has already enforced policy checks before calling this.
    This endpoint performs the actual external request with closedclaw's
    controlled access.
    """
    import httpx

    logger.info(
        "Bridge proxy request: %s %s (service: %s)",
        request.method, request.url, request.restricted_service,
    )

    # Sanitize: don't allow proxying to local/internal addresses
    from urllib.parse import urlparse
    parsed = urlparse(request.url)
    hostname = (parsed.hostname or "").lower()
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"):
        raise HTTPException(
            status_code=403,
            detail="Cannot proxy to internal/localhost addresses",
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                json=request.body if request.method in ("POST", "PUT", "PATCH") else None,
            )
            return {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp.text[:10000],  # Limit response size
            }
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Proxy request failed: {exc}")


@router.post("/audit")
async def bridge_audit(event: BridgeAuditEvent):
    """Receive audit events from the control bridge and log them."""
    logger.info(
        "Bridge audit: [%s] from %s — %s",
        event.event_type, event.source, event.details,
    )

    # Forward to closedclaw's audit system if available
    try:
        from closedclaw.api.core.storage import get_storage
        storage = get_storage()
        storage.append_audit_log({
            "timestamp": time.time(),
            "event_type": f"bridge.{event.event_type}",
            "source": event.source,
            "details": event.details,
        })
    except Exception as exc:
        logger.warning("Failed to persist bridge audit event: %s", exc)

    return {"status": "logged"}


# ---------------------------------------------------------------------------
# Controlled MCP endpoints — mail, calendar, files
# These route through the MCP connector system for local operation.
# ---------------------------------------------------------------------------

@router.post("/mcp/email")
async def mcp_email(request: MCPOperationRequest):
    """Controlled email MCP — routes through Gmail connector."""
    return await _dispatch_tool("gmail", request)


@router.post("/mcp/calendar")
async def mcp_calendar(request: MCPOperationRequest):
    """Controlled calendar MCP — calendar operations via Drive connector."""
    # Calendar uses the same Google OAuth — return placeholder until dedicated connector
    return {
        "operation": request.operation,
        "status": "success",
        "data": {
            "message": "Calendar MCP ready. Configure Google OAuth to connect.",
            "operation": request.operation,
            "results": [],
        },
    }


@router.post("/mcp/files")
async def mcp_files(request: MCPOperationRequest):
    """Controlled file access MCP — routes through Drive connector."""
    return await _dispatch_tool("drive", request)


# ---------------------------------------------------------------------------
# MCP Service Status — list available connectors and their connection state
# ---------------------------------------------------------------------------

@router.get("/mcp/status")
async def mcp_status():
    """Return status of all MCP service connectors."""
    from closedclaw.api.mcp_services import MCP_CONNECTORS

    services = {}
    for name in MCP_CONNECTORS:
        connector = _get_connector(name)
        has_token = bool(connector and connector._oauth_token)
        services[name] = {
            "available": True,
            "connected": has_token,
            "operations": connector.SUPPORTED_OPERATIONS if connector else [],
        }
    return {"services": services, "mode": "local"}


# ---------------------------------------------------------------------------
# MCP Connector Routes — Gmail, Notion, Drive, Slack, GitHub
# These route through closedclaw's tool agent pipeline for policy enforcement.
# ---------------------------------------------------------------------------

@router.post("/mcp/gmail")
async def mcp_gmail(request: MCPOperationRequest):
    """Controlled Gmail MCP — routes through tool orchestrator."""
    return await _dispatch_tool("gmail", request)


@router.post("/mcp/notion")
async def mcp_notion(request: MCPOperationRequest):
    """Controlled Notion MCP — routes through tool orchestrator."""
    return await _dispatch_tool("notion", request)


@router.post("/mcp/drive")
async def mcp_drive(request: MCPOperationRequest):
    """Controlled Google Drive MCP — routes through tool orchestrator."""
    return await _dispatch_tool("drive", request)


@router.post("/mcp/slack")
async def mcp_slack(request: MCPOperationRequest):
    """Controlled Slack MCP — routes through tool orchestrator."""
    return await _dispatch_tool("slack", request)


@router.post("/mcp/github")
async def mcp_github(request: MCPOperationRequest):
    """Controlled GitHub MCP — routes through tool orchestrator."""
    return await _dispatch_tool("github", request)


async def _dispatch_tool(tool: str, request: MCPOperationRequest) -> dict:
    """Dispatch a tool request through the MCP connector (local) or swarm pipeline.

    Tries the local MCP connector first. If the swarm is enabled, routes
    through the governance pipeline instead.
    """
    # Try local MCP connector first
    connector = _get_connector(tool)
    if connector:
        result = await connector.execute(request.operation, request.params)
        return {
            "operation": request.operation,
            "status": result.get("status", "success"),
            "data": result.get("data", result),
        }

    # Fall back to swarm pipeline if available
    from closedclaw.api.deps import get_swarm_coordinator

    coordinator = get_swarm_coordinator()
    if not coordinator:
        return {
            "operation": request.operation,
            "status": "success",
            "data": {
                "tool": tool,
                "message": f"{tool.title()} MCP ready. Configure API credentials to connect.",
                "operation": request.operation,
                "params": request.params,
            },
        }

    from closedclaw.api.agents.swarm.models import SwarmTask, SwarmTaskType

    task = SwarmTask(
        task_type=SwarmTaskType.TOOL_DISPATCH,
        user_id="default",
        input_data={
            "tool": tool,
            "operation": request.operation,
            "params": request.params,
            "prompt": f"{tool} {request.operation}",
        },
        context={"source": request.source},
    )
    result = await coordinator.execute(task)
    return {
        "operation": request.operation,
        "status": result.status,
        "data": result.output,
        "agents_invoked": result.agents_invoked,
    }
