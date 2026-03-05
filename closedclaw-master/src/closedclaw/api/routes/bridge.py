"""
Bridge Routes — Host-side endpoints for the Docker control bridge.

These endpoints are called BY the control bridge (running in Docker)
to get policy decisions, proxy restricted service access, and log audit events.
The bridge runs inside Docker; these routes run on the HOST closedclaw server.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
# These are stub implementations. In production, connect to actual
# service APIs (Gmail API, Google Calendar API, etc.) with proper OAuth.
# ---------------------------------------------------------------------------

@router.post("/mcp/email")
async def mcp_email(request: MCPOperationRequest):
    """Controlled email MCP — returns sanitized email data."""
    if request.operation == "get_inbox_summary":
        # In production: connect to Gmail API with user's OAuth token
        # Return only subjects, senders, dates — no bodies
        return {
            "operation": "get_inbox_summary",
            "status": "success",
            "data": {
                "message": "Email MCP is configured but not yet connected to a mail provider. "
                           "Configure OAuth in closedclaw settings to enable.",
                "emails": [],
            },
        }
    elif request.operation == "search_emails":
        query = request.params.get("query", "")
        return {
            "operation": "search_emails",
            "status": "success",
            "data": {
                "message": "Email search MCP not yet connected. Configure OAuth to enable.",
                "query": query,
                "results": [],
            },
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown email operation: {request.operation}",
        )


@router.post("/mcp/calendar")
async def mcp_calendar(request: MCPOperationRequest):
    """Controlled calendar MCP — returns sanitized calendar data."""
    if request.operation == "get_upcoming_events":
        return {
            "operation": "get_upcoming_events",
            "status": "success",
            "data": {
                "message": "Calendar MCP not yet connected. Configure OAuth to enable.",
                "events": [],
            },
        }
    elif request.operation == "search_events":
        return {
            "operation": "search_events",
            "status": "success",
            "data": {
                "message": "Calendar search not yet connected.",
                "results": [],
            },
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown calendar operation: {request.operation}",
        )


@router.post("/mcp/files")
async def mcp_files(request: MCPOperationRequest):
    """Controlled file access MCP — returns sanitized file listings."""
    if request.operation == "list_files":
        return {
            "operation": "list_files",
            "status": "success",
            "data": {
                "message": "File MCP not yet connected. Configure cloud storage to enable.",
                "files": [],
            },
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown file operation: {request.operation}",
        )


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
    """Dispatch a tool request through the swarm's TOOL_DISPATCH pipeline."""
    from closedclaw.api.deps import get_swarm_coordinator

    coordinator = get_swarm_coordinator()
    if not coordinator:
        return {
            "operation": request.operation,
            "status": "success",
            "data": {
                "tool": tool,
                "message": f"{tool.title()} MCP ready. Enable swarm for full pipeline.",
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
