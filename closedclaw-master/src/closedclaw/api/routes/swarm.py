"""
Swarm API Routes — control and inspect the agent swarm.

Endpoints for swarm status, agent inspection, constitution management,
task submission, and integrity verification.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from closedclaw.api.core.config import get_settings
from closedclaw.api.deps import get_auth_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/swarm", tags=["Agent Swarm"])

# Lazy singleton
_coordinator = None


def _get_coordinator():
    global _coordinator
    settings = get_settings()
    if not settings.swarm_enabled:
        raise HTTPException(503, detail="Agent swarm is not enabled. Set swarm_enabled=true in config.")
    if _coordinator is None:
        from closedclaw.api.agents.swarm.coordinator import SwarmCoordinator
        from closedclaw.api.core.config import CLOSEDCLAW_DIR
        from closedclaw.api.deps import get_memory
        from pathlib import Path

        constitution_path = (
            Path(settings.constitution_path)
            if settings.constitution_path
            else CLOSEDCLAW_DIR / "constitution.json"
        )
        memory = get_memory(settings)
        _coordinator = SwarmCoordinator(
            memory=memory,
            settings=settings,
            constitution_path=constitution_path,
        )
    return _coordinator


# ── Status ────────────────────────────────────────────────────────────

@router.get("/status")
async def swarm_status(token: str = Depends(get_auth_token)):
    """Get swarm health and agent status."""
    coord = _get_coordinator()
    return coord.get_status()


@router.get("/agents")
async def list_agents(token: str = Depends(get_auth_token)):
    """List all agents with their status and stats."""
    coord = _get_coordinator()
    status = coord.get_status()
    return {"agents": status.get("agents", {})}


@router.get("/agents/{agent_name}")
async def get_agent(agent_name: str, token: str = Depends(get_auth_token)):
    """Get detailed stats for a specific agent."""
    coord = _get_coordinator()
    stats = coord.get_agent_stats(agent_name)
    if not stats:
        raise HTTPException(404, detail=f"Agent '{agent_name}' not found or not loaded")
    return stats.model_dump()


# ── Constitution ──────────────────────────────────────────────────────

@router.get("/constitution")
async def get_constitution(token: str = Depends(get_auth_token)):
    """View the current constitution."""
    coord = _get_coordinator()
    return coord.constitution.to_dict()


class ConstitutionUpdateReq(BaseModel):
    principles: Optional[list] = None
    auto_generated_rules: Optional[bool] = None
    max_sensitivity_cloud: Optional[int] = None
    require_consent_for_storage: Optional[bool] = None
    blocked_topics: Optional[list] = None
    allowed_providers: Optional[list] = None


@router.put("/constitution")
async def update_constitution(req: ConstitutionUpdateReq, token: str = Depends(get_auth_token)):
    """Update the constitution (user action)."""
    coord = _get_coordinator()
    schema = coord.constitution.schema

    if req.principles is not None:
        from closedclaw.api.agents.swarm.models import ConstitutionPrinciple
        schema.principles = [ConstitutionPrinciple(**p) for p in req.principles]
    if req.auto_generated_rules is not None:
        schema.auto_generated_rules = req.auto_generated_rules
    if req.max_sensitivity_cloud is not None:
        schema.max_sensitivity_cloud = req.max_sensitivity_cloud
    if req.require_consent_for_storage is not None:
        schema.require_consent_for_storage = req.require_consent_for_storage
    if req.blocked_topics is not None:
        schema.blocked_topics = req.blocked_topics
    if req.allowed_providers is not None:
        schema.allowed_providers = req.allowed_providers

    coord.constitution._save()
    return {"success": True, "constitution": coord.constitution.to_dict()}


@router.get("/constitution/amendments")
async def list_amendments(token: str = Depends(get_auth_token)):
    """List pending constitutional amendments proposed by the Policy agent."""
    coord = _get_coordinator()
    pending = coord.constitution.get_pending_amendments()
    return {"amendments": [a.model_dump() for a in pending]}


@router.post("/constitution/amendments/{amendment_id}/approve")
async def approve_amendment(amendment_id: str, token: str = Depends(get_auth_token)):
    """Approve a proposed constitutional amendment."""
    coord = _get_coordinator()
    if coord.constitution.approve_amendment(amendment_id):
        return {"success": True, "amendment_id": amendment_id}
    raise HTTPException(404, detail="Amendment not found or already resolved")


@router.post("/constitution/amendments/{amendment_id}/reject")
async def reject_amendment(amendment_id: str, token: str = Depends(get_auth_token)):
    """Reject a proposed constitutional amendment."""
    coord = _get_coordinator()
    if coord.constitution.reject_amendment(amendment_id):
        return {"success": True, "amendment_id": amendment_id}
    raise HTTPException(404, detail="Amendment not found or already resolved")


# ── Tasks ─────────────────────────────────────────────────────────────

class SwarmTaskReq(BaseModel):
    task_type: str
    user_id: str = "default"
    provider: str = "ollama"
    input_data: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)


@router.post("/tasks")
async def submit_task(req: SwarmTaskReq, token: str = Depends(get_auth_token)):
    """Submit a task to the swarm for processing."""
    from closedclaw.api.agents.swarm.models import SwarmTask, SwarmTaskType

    try:
        task_type = SwarmTaskType(req.task_type)
    except ValueError:
        valid = [t.value for t in SwarmTaskType]
        raise HTTPException(400, detail=f"Invalid task_type. Valid: {valid}")

    settings = get_settings()
    task = SwarmTask(
        task_type=task_type,
        user_id=req.user_id,
        provider=req.provider,
        input_data=req.input_data,
        context=req.context,
        max_agent_calls=settings.swarm_max_agent_calls,
        token_budget=settings.swarm_token_budget,
    )

    coord = _get_coordinator()
    result = await coord.execute(task)
    return result.model_dump()


# ── Messages ──────────────────────────────────────────────────────────

@router.get("/messages")
async def get_messages(limit: int = 100, token: str = Depends(get_auth_token)):
    """Get recent inter-agent message history."""
    coord = _get_coordinator()
    return {"messages": coord.get_message_history(limit)}


# ── Verification ──────────────────────────────────────────────────────

@router.post("/verify")
async def verify_integrity(token: str = Depends(get_auth_token)):
    """Run the Auditor agent to verify system integrity."""
    from closedclaw.api.agents.swarm.models import SwarmTask, SwarmTaskType

    settings = get_settings()
    task = SwarmTask(
        task_type=SwarmTaskType.AUDIT_VERIFY,
        input_data={"action": "verify_chain"},
        max_agent_calls=settings.swarm_max_agent_calls,
        token_budget=settings.swarm_token_budget,
    )

    coord = _get_coordinator()
    result = await coord.execute(task)
    return result.model_dump()


# ── Agent Management ─────────────────────────────────────────────────

class AgentToggleReq(BaseModel):
    enabled: bool


@router.put("/agents/{agent_name}/enabled")
async def toggle_agent(agent_name: str, req: AgentToggleReq, token: str = Depends(get_auth_token)):
    """Enable or disable a specific agent."""
    valid = {"accessor", "governance", "sentinel", "maker", "policy", "arbitrator", "auditor"}
    if agent_name not in valid:
        raise HTTPException(404, detail=f"Unknown agent: {agent_name}")
    coord = _get_coordinator()
    coord.set_agent_enabled(agent_name, req.enabled)
    return {"success": True, "agent": agent_name, "enabled": req.enabled}


@router.get("/agents/{agent_name}/tools")
async def get_agent_tools(agent_name: str, token: str = Depends(get_auth_token)):
    """List tools available to an agent."""
    coord = _get_coordinator()
    tools = coord._tool_registry.get_agent_tool_names(agent_name)
    descriptions = coord._tool_registry.get_tool_descriptions(agent_name)
    return {"agent": agent_name, "tools": tools, "descriptions": descriptions}


class ToolsUpdateReq(BaseModel):
    tools: list[str]


@router.put("/agents/{agent_name}/tools")
async def update_agent_tools(agent_name: str, req: ToolsUpdateReq, token: str = Depends(get_auth_token)):
    """Configure which tools an agent can access."""
    coord = _get_coordinator()
    available = set(coord._tool_registry.all_tool_names)
    invalid = set(req.tools) - available
    if invalid:
        raise HTTPException(400, detail=f"Unknown tools: {sorted(invalid)}")
    coord._tool_registry.set_agent_tools(agent_name, set(req.tools))
    return {"success": True, "agent": agent_name, "tools": sorted(req.tools)}


# ── Pipelines ────────────────────────────────────────────────────────

@router.get("/pipelines")
async def list_pipelines(token: str = Depends(get_auth_token)):
    """List all task pipelines and their agent ordering."""
    coord = _get_coordinator()
    return {"pipelines": coord.get_all_pipelines()}


class PipelineUpdateReq(BaseModel):
    agents: list[str]


@router.put("/pipelines/{task_type}")
async def update_pipeline(task_type: str, req: PipelineUpdateReq, token: str = Depends(get_auth_token)):
    """Reorder agents in a pipeline."""
    from closedclaw.api.agents.swarm.models import SwarmTaskType
    try:
        tt = SwarmTaskType(task_type)
    except ValueError:
        valid = [t.value for t in SwarmTaskType]
        raise HTTPException(400, detail=f"Invalid task_type. Valid: {valid}")

    valid_agents = {"accessor", "governance", "sentinel", "maker", "policy", "arbitrator", "auditor"}
    invalid = set(req.agents) - valid_agents
    if invalid:
        raise HTTPException(400, detail=f"Unknown agents: {sorted(invalid)}")

    coord = _get_coordinator()
    coord.set_pipeline(tt, req.agents)
    return {"success": True, "task_type": task_type, "agents": req.agents}


# ── Tool History ─────────────────────────────────────────────────────

@router.get("/tools/history")
async def tool_call_history(limit: int = 50, token: str = Depends(get_auth_token)):
    """Get recent tool call history across all agents."""
    coord = _get_coordinator()
    return {"history": coord._tool_registry.get_call_history(limit)}


@router.get("/tools")
async def list_all_tools(token: str = Depends(get_auth_token)):
    """List all available tools in the registry."""
    coord = _get_coordinator()
    tools = []
    for name in coord._tool_registry.all_tool_names:
        tool = coord._tool_registry._tools[name]
        tools.append(tool.to_description())
    return {"tools": tools}


# ── Stats ─────────────────────────────────────────────────────────────

@router.get("/stats")
async def swarm_stats(token: str = Depends(get_auth_token)):
    """Aggregate swarm statistics."""
    coord = _get_coordinator()
    status = coord.get_status()
    agents = status.get("agents", {})

    total_invocations = sum(
        a.get("total_invocations", 0)
        for a in agents.values()
        if isinstance(a, dict)
    )
    total_llm_calls = sum(
        a.get("total_llm_calls", 0)
        for a in agents.values()
        if isinstance(a, dict)
    )
    total_tokens = sum(
        a.get("total_tokens", 0)
        for a in agents.values()
        if isinstance(a, dict)
    )

    return {
        "total_invocations": total_invocations,
        "total_llm_calls": total_llm_calls,
        "total_tokens": total_tokens,
        "total_messages": status.get("total_messages", 0),
        "agents_loaded": len([a for a in agents.values() if isinstance(a, dict) and a.get("total_invocations", 0) > 0]),
        "constitution_principles": status.get("constitution_principles", 0),
        "pending_amendments": status.get("pending_amendments", 0),
    }
