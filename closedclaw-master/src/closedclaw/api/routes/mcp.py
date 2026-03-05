"""
MCP integration routes.

Provides a transport bridge for sending/receiving JSON-RPC payloads
to MCP-compatible HTTP endpoints, plus server discovery from config.
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from closedclaw.api.deps import get_auth_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/mcp", tags=["MCP"])


class MCPCallRequest(BaseModel):
    """JSON-RPC call request for an MCP server."""

    server_name: Optional[str] = Field(
        default=None,
        description="Configured MCP server name from CLOSEDCLAW_MCP_SERVERS",
    )
    server_url: Optional[str] = Field(
        default=None,
        description="Direct MCP HTTP endpoint URL",
    )
    method: str = Field(..., min_length=1, description="JSON-RPC method")
    params: Optional[Any] = Field(default=None, description="JSON-RPC params")
    request_id: Optional[Any] = Field(default=None, description="JSON-RPC id")
    timeout_ms: int = Field(default=15000, ge=1000, le=120000)
    headers: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_target(self):
        if not self.server_name and not self.server_url:
            raise ValueError("Either server_name or server_url must be provided")
        return self


class MCPRawRequest(BaseModel):
    """Raw payload forwarding for MCP interoperability."""

    server_name: Optional[str] = None
    server_url: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = Field(default=15000, ge=1000, le=120000)
    headers: Dict[str, str] = Field(default_factory=dict)


def _load_mcp_servers() -> Dict[str, str]:
    """
    Load configured MCP servers from environment.

    Format:
      CLOSEDCLAW_MCP_SERVERS={"clawdbot":"http://127.0.0.1:8765/v1/clawdbot/chat"}
    """
    raw = os.environ.get("CLOSEDCLAW_MCP_SERVERS", "").strip()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {
                str(name): str(url)
                for name, url in parsed.items()
                if isinstance(name, str) and isinstance(url, str)
            }
    except Exception as exc:
        logger.warning(f"Invalid CLOSEDCLAW_MCP_SERVERS config: {exc}")

    return {}


def _resolve_target(server_name: Optional[str], server_url: Optional[str]) -> str:
    if server_url:
        return server_url

    servers = _load_mcp_servers()
    if not server_name or server_name not in servers:
        raise HTTPException(
            status_code=404,
            detail="MCP server not found. Configure CLOSEDCLAW_MCP_SERVERS or provide server_url.",
        )
    return servers[server_name]


def _validate_url(target: str) -> None:
    if not (target.startswith("http://") or target.startswith("https://")):
        raise HTTPException(status_code=400, detail="Only http(s) MCP endpoints are supported")


@router.get("/servers")
async def list_mcp_servers(token: str = Depends(get_auth_token)):
    """List configured MCP servers."""
    servers = _load_mcp_servers()
    return {
        "count": len(servers),
        "servers": [{"name": name, "url": url} for name, url in servers.items()],
    }


@router.post("/call")
async def call_mcp(request: MCPCallRequest, token: str = Depends(get_auth_token)):
    """Send a JSON-RPC call to an MCP HTTP endpoint."""
    target = _resolve_target(request.server_name, request.server_url)
    _validate_url(target)

    payload = {
        "jsonrpc": "2.0",
        "method": request.method,
        "params": request.params if request.params is not None else {},
        "id": request.request_id if request.request_id is not None else int(time.time() * 1000),
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=request.timeout_ms / 1000.0) as client:
            response = await client.post(target, json=payload, headers=request.headers)
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            if not response.headers.get("content-type", "").startswith("application/json"):
                return {
                    "server": target,
                    "status_code": response.status_code,
                    "latency_ms": elapsed_ms,
                    "raw": response.text,
                }

            data = response.json()
            return {
                "server": target,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
                "result": data.get("result"),
                "error": data.get("error"),
                "raw": data,
            }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="MCP request timed out")
    except httpx.RequestError as exc:
        logger.error("MCP request failed: %s", exc)
        raise HTTPException(status_code=502, detail="MCP request failed")


@router.post("/raw")
async def forward_mcp_raw(request: MCPRawRequest, token: str = Depends(get_auth_token)):
    """Forward a raw JSON payload to an MCP HTTP endpoint."""
    target = _resolve_target(request.server_name, request.server_url)
    _validate_url(target)

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=request.timeout_ms / 1000.0) as client:
            response = await client.post(target, json=request.payload, headers=request.headers)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            content_type = response.headers.get("content-type", "")

            if content_type.startswith("application/json"):
                body: Any = response.json()
            else:
                body = response.text

            return {
                "server": target,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
                "body": body,
            }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="MCP request timed out")
    except httpx.RequestError as exc:
        logger.error("MCP request failed: %s", exc)
        raise HTTPException(status_code=502, detail="MCP request failed")


# ── Tool Dispatch ─────────────────────────────────────────────────────


class MCPToolRequest(BaseModel):
    """Request to invoke a tool through the swarm's TOOL_DISPATCH pipeline."""

    tool: str = Field(..., min_length=1, description="Tool name (gmail, notion, drive, slack, github)")
    operation: str = Field(..., min_length=1, description="Operation to perform")
    params: Dict[str, Any] = Field(default_factory=dict, description="Operation parameters")
    user_id: str = Field(default="default")


@router.post("/tool")
async def dispatch_tool(request: MCPToolRequest, token: str = Depends(get_auth_token)):
    """Dispatch a tool operation through the swarm's governance pipeline.

    Routes through: governance -> tool_orchestrator -> auditor
    """
    from closedclaw.api.deps import get_swarm_coordinator

    coordinator = get_swarm_coordinator()
    if not coordinator:
        raise HTTPException(
            status_code=503,
            detail="Swarm system not enabled. Set CLOSEDCLAW_SWARM_ENABLED=true.",
        )

    from closedclaw.api.agents.swarm.models import SwarmTask, SwarmTaskType

    task = SwarmTask(
        task_type=SwarmTaskType.TOOL_DISPATCH,
        user_id=request.user_id,
        input_data={
            "tool": request.tool,
            "operation": request.operation,
            "params": request.params,
            "prompt": f"{request.tool} {request.operation}",
        },
    )
    result = await coordinator.execute(task)
    return {
        "tool": request.tool,
        "operation": request.operation,
        "status": result.status,
        "data": result.output,
        "agents_invoked": result.agents_invoked,
        "llm_calls": result.llm_calls_made,
        "duration_ms": result.duration_ms,
    }


@router.get("/tools")
async def list_available_tools(token: str = Depends(get_auth_token)):
    """List all available MCP tool connectors and their operations."""
    return {
        "tools": [
            {
                "name": "gmail",
                "operations": ["get_inbox_summary", "search_emails", "get_email", "send_email", "get_labels"],
                "write_operations": ["send_email"],
            },
            {
                "name": "notion",
                "operations": ["search_pages", "get_page", "create_page", "update_page", "list_databases", "query_database"],
                "write_operations": ["create_page", "update_page"],
            },
            {
                "name": "drive",
                "operations": ["list_files", "search_files", "get_file_metadata", "get_file_content", "upload_file"],
                "write_operations": ["upload_file"],
            },
            {
                "name": "slack",
                "operations": ["list_channels", "search_messages", "get_channel_history", "send_message", "get_user_info"],
                "write_operations": ["send_message"],
            },
            {
                "name": "github",
                "operations": ["list_repos", "get_repo", "list_issues", "create_issue", "list_pull_requests", "get_file_content"],
                "write_operations": ["create_issue"],
            },
        ],
    }
