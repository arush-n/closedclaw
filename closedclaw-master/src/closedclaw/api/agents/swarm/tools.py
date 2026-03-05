"""
Swarm Tool Registry — provides structured tool access to swarm agents.

Each tool is a SwarmTool with validated input/output, permission checks,
and audit tracking. Wraps existing MemoryTools + adds inter-agent tools.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Type

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Tool Base ────────────────────────────────────────────────────────

class ToolInput(BaseModel):
    """Base for all tool inputs."""
    pass


class ToolOutput(BaseModel):
    """Base for all tool outputs."""
    success: bool = True
    error: Optional[str] = None


class SwarmTool(ABC):
    """Base class for all tools available to swarm agents."""

    name: str = ""
    description: str = ""
    input_schema: Type[BaseModel] = ToolInput
    output_schema: Type[BaseModel] = ToolOutput

    @abstractmethod
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool. Returns output dict."""
        ...

    def to_description(self) -> Dict[str, str]:
        """Return metadata for LLM prompt construction."""
        fields = self.input_schema.model_fields
        params = ", ".join(
            f"{name} ({f.annotation.__name__ if hasattr(f.annotation, '__name__') else str(f.annotation)})"
            for name, f in fields.items()
        )
        return {
            "name": self.name,
            "description": self.description,
            "parameters": params,
        }


# ── Tool Call Record ─────────────────────────────────────────────────

class ToolCallRecord(BaseModel):
    tool_name: str
    agent_name: str
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0
    success: bool = True


# ── Tool Registry ────────────────────────────────────────────────────

# Default tool permissions per agent
DEFAULT_AGENT_TOOLS: Dict[str, Set[str]] = {
    "accessor": {"memory_search", "memory_timeline", "delegate_to_agent", "check_constitution", "store_working_memory", "log_decision"},
    "maker": {"memory_search", "memory_write", "delegate_to_agent", "check_constitution", "store_working_memory", "log_decision"},
    "governance": {"check_constitution", "request_vote", "delegate_to_agent", "store_working_memory", "log_decision"},
    "policy": {"memory_search", "memory_reflect", "check_constitution", "request_vote", "delegate_to_agent", "store_working_memory", "log_decision"},
    "sentinel": {"memory_search", "memory_timeline", "memory_reflect", "delegate_to_agent", "store_working_memory", "log_decision"},
    "arbitrator": {"check_constitution", "delegate_to_agent", "store_working_memory", "log_decision"},
    "auditor": {"verify_signature", "check_constitution", "store_working_memory", "log_decision"},
    "injector": {"check_constitution", "store_working_memory", "log_decision"},
    "addon_memory": {"memory_search", "memory_write", "request_vote", "check_constitution", "store_working_memory", "log_decision"},
    "processor": {"memory_search", "delegate_to_agent", "store_working_memory", "log_decision"},
}


class ToolRegistry:
    """Central registry of tools available to swarm agents."""

    def __init__(self):
        self._tools: Dict[str, SwarmTool] = {}
        self._agent_permissions: Dict[str, Set[str]] = {
            k: set(v) for k, v in DEFAULT_AGENT_TOOLS.items()
        }
        self._call_history: List[ToolCallRecord] = []
        self._max_history = 500

    def register(self, tool: SwarmTool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def execute(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        agent_name: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool with permission check and audit tracking."""
        tool = self._tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        # Permission check
        allowed = self._agent_permissions.get(agent_name, set())
        if tool_name not in allowed:
            logger.warning("Agent %s denied access to tool %s", agent_name, tool_name)
            return {"success": False, "error": f"Agent '{agent_name}' not permitted to use tool '{tool_name}'"}

        # Execute with timing
        start = time.time()
        try:
            result = tool.execute(input_data, {**context, "calling_agent": agent_name})
            duration_ms = (time.time() - start) * 1000
            record = ToolCallRecord(
                tool_name=tool_name,
                agent_name=agent_name,
                input_data=input_data,
                output_data=result,
                duration_ms=round(duration_ms, 2),
                success=result.get("success", True) if isinstance(result, dict) else True,
            )
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            result = {"success": False, "error": str(exc)}
            record = ToolCallRecord(
                tool_name=tool_name,
                agent_name=agent_name,
                input_data=input_data,
                output_data=result,
                duration_ms=round(duration_ms, 2),
                success=False,
            )

        self._call_history.append(record)
        if len(self._call_history) > self._max_history:
            self._call_history = self._call_history[-self._max_history:]

        return result

    def get_tools_for_agent(self, agent_name: str) -> List[SwarmTool]:
        """Get tools available to a specific agent."""
        allowed = self._agent_permissions.get(agent_name, set())
        return [t for name, t in self._tools.items() if name in allowed]

    def get_tool_descriptions(self, agent_name: str) -> List[Dict[str, str]]:
        """Get tool metadata for LLM prompt construction."""
        return [t.to_description() for t in self.get_tools_for_agent(agent_name)]

    def set_agent_tools(self, agent_name: str, tool_names: Set[str]) -> None:
        """Configure which tools an agent can access."""
        self._agent_permissions[agent_name] = tool_names

    def get_agent_tool_names(self, agent_name: str) -> List[str]:
        """Get names of tools available to an agent."""
        return sorted(self._agent_permissions.get(agent_name, set()))

    def get_call_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent tool call history."""
        return [r.model_dump() for r in self._call_history[-limit:]]

    @property
    def all_tool_names(self) -> List[str]:
        return sorted(self._tools.keys())


# ── Memory Tools (wrap existing MemoryTools) ─────────────────────────

class MemorySearchTool(SwarmTool):
    name = "memory_search"
    description = "Semantic search over the memory vault. Returns top-k memories matching a query."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        from closedclaw.api.agents.tools import MemoryTools, SearchMemoryInput
        memory = context.get("memory")
        user_id = context.get("user_id", "default")
        settings = context.get("settings")
        tools = MemoryTools(memory=memory, user_id=user_id, settings=settings)
        inp = SearchMemoryInput(**input_data)
        result = tools.search_memory(inp)
        return result.model_dump()


class MemoryWriteTool(SwarmTool):
    name = "memory_write"
    description = "Store a new memory. Low sensitivity stored immediately; high triggers consent."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        from closedclaw.api.agents.tools import MemoryTools, WriteMemoryInput
        memory = context.get("memory")
        user_id = context.get("user_id", "default")
        settings = context.get("settings")
        tools = MemoryTools(memory=memory, user_id=user_id, settings=settings)
        inp = WriteMemoryInput(**input_data)
        result = tools.write_memory(inp)
        return result.model_dump()


class MemoryTimelineTool(SwarmTool):
    name = "memory_timeline"
    description = "Retrieve memories for a topic ordered chronologically."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        from closedclaw.api.agents.tools import MemoryTools, TimelineInput
        memory = context.get("memory")
        user_id = context.get("user_id", "default")
        settings = context.get("settings")
        tools = MemoryTools(memory=memory, user_id=user_id, settings=settings)
        inp = TimelineInput(**input_data)
        result = tools.get_memory_timeline(inp)
        return result.model_dump()


class MemoryReflectTool(SwarmTool):
    name = "memory_reflect"
    description = "Synthesize memories about a topic into a coherent summary with patterns and contradictions."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        from closedclaw.api.agents.tools import MemoryTools, ReflectInput
        memory = context.get("memory")
        user_id = context.get("user_id", "default")
        settings = context.get("settings")
        tools = MemoryTools(memory=memory, user_id=user_id, settings=settings)
        inp = ReflectInput(**input_data)
        result = tools.reflect_on_memories(inp)
        return result.model_dump()


# ── Inter-Agent Tools ────────────────────────────────────────────────

MAX_DELEGATION_DEPTH = 3


class DelegateToAgentTool(SwarmTool):
    name = "delegate_to_agent"
    description = "Send a sub-task to another agent and get its result. Max depth 3."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        target = input_data.get("agent_name", "")
        payload = input_data.get("payload", {})
        calling_agent = context.get("calling_agent", "")
        delegation_depth = context.get("delegation_depth", 0)

        if delegation_depth >= MAX_DELEGATION_DEPTH:
            return {"success": False, "error": f"Max delegation depth ({MAX_DELEGATION_DEPTH}) reached"}

        if target == calling_agent:
            return {"success": False, "error": "Cannot delegate to self"}

        valid_agents = {"governance", "maker", "accessor", "policy", "sentinel", "arbitrator", "auditor"}
        if target not in valid_agents:
            return {"success": False, "error": f"Unknown agent: {target}"}

        coordinator = context.get("coordinator")
        if not coordinator:
            return {"success": False, "error": "No coordinator available for delegation"}

        # Run the delegation synchronously via asyncio
        inner_context = {
            **context,
            "delegation_depth": delegation_depth + 1,
            "delegated_by": calling_agent,
        }

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an async context — create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        coordinator._execute_single_agent(target, payload, inner_context),
                    )
                    result_msg = future.result(timeout=30)
            else:
                result_msg = asyncio.run(
                    coordinator._execute_single_agent(target, payload, inner_context)
                )
            return {"success": True, "result": result_msg.payload}
        except Exception as exc:
            logger.error("Delegation to %s failed: %s", target, exc)
            return {"success": False, "error": str(exc)}


class RequestVoteTool(SwarmTool):
    name = "request_vote"
    description = "Request a federated vote from multiple agents on whether to permit/deny a memory."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        agents = input_data.get("agents", [])
        memory = input_data.get("memory", {})
        calling_agent = context.get("calling_agent", "")

        if not agents:
            return {"success": False, "error": "No agents specified for voting"}
        if len(agents) > 3:
            agents = agents[:3]

        # Filter out self
        agents = [a for a in agents if a != calling_agent]
        if not agents:
            return {"success": False, "error": "No valid agents to vote (filtered self)"}

        coordinator = context.get("coordinator")
        if not coordinator:
            return {"success": False, "error": "No coordinator available for voting"}

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        coordinator._federated_consensus(memory, context),
                    )
                    result = future.result(timeout=30)
            else:
                result = asyncio.run(
                    coordinator._federated_consensus(memory, context),
                )
            return {"success": True, **result}
        except Exception as exc:
            logger.error("Vote request failed: %s", exc)
            return {"success": False, "error": str(exc)}


class CheckConstitutionTool(SwarmTool):
    name = "check_constitution"
    description = "Check a memory or action against the constitutional principles. Returns violations."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        constitution = context.get("constitution")
        if not constitution:
            return {"success": False, "error": "No constitution available"}

        memory = input_data.get("memory", input_data)
        violations = constitution.check_compliance(memory)
        return {
            "success": True,
            "compliant": len(violations) == 0,
            "violations": violations,
        }


class StoreWorkingMemoryTool(SwarmTool):
    name = "store_working_memory"
    description = "Store a note in the calling agent's working memory for future few-shot use."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        content = input_data.get("content", "")
        tags = input_data.get("tags", [])
        if not content:
            return {"success": False, "error": "No content to store"}

        memory = context.get("memory")
        calling_agent = context.get("calling_agent", "unknown")
        if not memory:
            return {"success": False, "error": "No memory instance available"}

        try:
            all_tags = [f"agent:{calling_agent}", "agent:working_memory"] + tags
            memory.add(
                content=content,
                user_id=f"agent:{calling_agent}",
                sensitivity=0,
                tags=all_tags,
                source="swarm_agent",
            )
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class LogDecisionTool(SwarmTool):
    name = "log_decision"
    description = "Log a decision to the audit trail for transparency."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        decision = input_data.get("decision", "")
        reasoning = input_data.get("reasoning", "")
        calling_agent = context.get("calling_agent", "unknown")

        logger.info("DECISION [%s]: %s — %s", calling_agent, decision, reasoning[:200])
        return {"success": True, "logged": True}


class VerifySignatureTool(SwarmTool):
    name = "verify_signature"
    description = "Verify the Ed25519 signature on an agent message."

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        keyring = context.get("keyring")
        if not keyring:
            return {"success": False, "error": "No keyring available"}

        from closedclaw.api.agents.swarm.models import AgentMessage
        try:
            msg = AgentMessage(**input_data.get("message", {}))
            valid = keyring.verify_message(msg)
            return {"success": True, "valid": valid}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


# ── Registry Factory ─────────────────────────────────────────────────

def create_default_registry() -> ToolRegistry:
    """Create and populate the default tool registry."""
    registry = ToolRegistry()

    # Memory tools
    registry.register(MemorySearchTool())
    registry.register(MemoryWriteTool())
    registry.register(MemoryTimelineTool())
    registry.register(MemoryReflectTool())

    # Inter-agent tools
    registry.register(DelegateToAgentTool())
    registry.register(RequestVoteTool())
    registry.register(CheckConstitutionTool())
    registry.register(StoreWorkingMemoryTool())

    # Audit tools
    registry.register(LogDecisionTool())
    registry.register(VerifySignatureTool())

    return registry
