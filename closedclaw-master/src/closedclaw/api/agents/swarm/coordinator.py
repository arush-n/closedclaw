"""
SwarmCoordinator — the central dispatcher for the agentic memory team.

Routes tasks to agents via deterministic pipelines (no LLM call for routing).
Enforces sequential execution, circuit breakers, token budgets, and crypto signing.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from closedclaw.api.agents.swarm.bus import MessageBus
from closedclaw.api.agents.swarm.constitution import Constitution
from closedclaw.api.agents.swarm.crypto import AgentKeyring
from closedclaw.api.agents.swarm.models import (
    AgentMessage,
    AgentStats,
    ArbitrationCase,
    SwarmResult,
    SwarmTask,
    SwarmTaskType,
)

logger = logging.getLogger(__name__)

# ── Deterministic Pipeline Routing ────────────────────────────────────
# Each task type maps to an ordered list of agents to invoke sequentially.
# No LLM call needed — pure dispatch logic.

TASK_PIPELINES: Dict[SwarmTaskType, List[str]] = {
    SwarmTaskType.FULL_PIPELINE: [
        "accessor",     # 1. Retrieve relevant memories + graph traversal
        "governance",   # 2. Firewall + policy evaluation
        "sentinel",     # 3. Hallucination check (conditional: sensitivity >= 2)
    ],
    SwarmTaskType.STORE_MEMORY: [
        "maker",        # 1. Extract structured facts + classify sensitivity
        "governance",   # 2. Check if storage is allowed by policy
        "policy",       # 3. Verify against constitution
    ],
    SwarmTaskType.RETRIEVE_MEMORY: [
        "accessor",     # 1. Semantic search + expansion
        "governance",   # 2. Apply access controls
    ],
    SwarmTaskType.EVALUATE_ACCESS: [
        "governance",   # Single agent
    ],
    SwarmTaskType.CHECK_POLICY: [
        "policy",       # Single agent
    ],
    SwarmTaskType.DETECT_HALLUCINATION: [
        "accessor",     # 1. Get relevant memories for comparison
        "sentinel",     # 2. Cross-reference LLM output
    ],
    SwarmTaskType.RESOLVE_CONFLICT: [
        "arbitrator",   # Single agent
    ],
    SwarmTaskType.AUDIT_VERIFY: [
        "auditor",      # Single agent
    ],
    SwarmTaskType.COMPACT_MEMORIES: [
        "maker",        # Deduplicate, summarize, decay, cluster
    ],
    SwarmTaskType.EVOLVE_POLICY: [
        "policy",       # Analyze consent patterns, propose amendments
    ],
}

# Agents that require high-sensitivity context to activate
CONDITIONAL_AGENTS = {
    "sentinel": lambda ctx: ctx.get("max_sensitivity_seen", 0) >= 2,
}


class SwarmCoordinator:
    """Orchestrates the 7-agent swarm via sequential signed message passing."""

    def __init__(
        self,
        memory=None,
        settings=None,
        constitution_path=None,
    ):
        self._memory = memory
        self._settings = settings
        self._bus = MessageBus()
        self._keyring = AgentKeyring()
        self._constitution = Constitution(constitution_path)

        # Tool registry
        from closedclaw.api.agents.swarm.tools import create_default_registry
        self._tool_registry = create_default_registry()

        # Lazy-loaded agents
        self._agents: Dict[str, Any] = {}  # name -> BaseAgent
        self._agent_stats: Dict[str, AgentStats] = {}

        # Agent enable/disable state
        self._disabled_agents: set = set()

        # Custom pipeline overrides (task_type -> ordered agent names)
        self._pipeline_overrides: Dict[SwarmTaskType, List[str]] = {}

        # Initialize keys
        self._keyring.ensure_all_keys()
        logger.info("SwarmCoordinator initialized with %d agent keys", len(self._keyring._public_keys))

    # ── Agent Lifecycle (Lazy) ────────────────────────────────────────

    def _get_agent(self, name: str):
        """Lazy-load an agent by name."""
        if name not in self._agents:
            self._agents[name] = self._create_agent(name)
        return self._agents[name]

    def _create_agent(self, name: str):
        """Factory: create an agent instance by name."""
        kwargs = dict(
            memory=self._memory,
            settings=self._settings,
            constitution=self._constitution,
            keyring=self._keyring,
            bus=self._bus,
            tool_registry=self._tool_registry,
            coordinator=self,
        )
        if name == "governance":
            from closedclaw.api.agents.swarm.governance import GovernanceAgent
            return GovernanceAgent(**kwargs)
        elif name == "maker":
            from closedclaw.api.agents.swarm.maker import MakerAgent
            return MakerAgent(**kwargs)
        elif name == "accessor":
            from closedclaw.api.agents.swarm.accessor import AccessorAgent
            return AccessorAgent(**kwargs)
        elif name == "policy":
            from closedclaw.api.agents.swarm.policy import PolicyAgent
            return PolicyAgent(**kwargs)
        elif name == "sentinel":
            from closedclaw.api.agents.swarm.sentinel import SentinelAgent
            return SentinelAgent(**kwargs)
        elif name == "arbitrator":
            from closedclaw.api.agents.swarm.arbitrator import ArbitratorAgent
            return ArbitratorAgent(**kwargs)
        elif name == "auditor":
            from closedclaw.api.agents.swarm.auditor import AuditorAgent
            return AuditorAgent(**kwargs)
        else:
            raise ValueError(f"Unknown agent: {name}")

    # ── Main Execution ────────────────────────────────────────────────

    async def execute(self, task: SwarmTask) -> SwarmResult:
        """Execute a swarm task through the appropriate pipeline."""
        start = time.time()
        pipeline = self._pipeline_overrides.get(task.task_type) or TASK_PIPELINES.get(task.task_type, [])
        if not pipeline:
            return SwarmResult(
                task_id=task.task_id,
                status="error",
                output={"error": f"No pipeline for task type: {task.task_type}"},
            )

        context: Dict[str, Any] = {
            **task.context,
            "task": task.model_dump(),
            "user_id": task.user_id,
            "provider": task.provider,
        }
        agents_invoked: List[str] = []
        audit_trail: List[Dict[str, Any]] = []
        total_llm_calls = 0
        total_tokens = 0
        status = "completed"

        for agent_name in pipeline:
            # Circuit breaker
            if len(agents_invoked) >= task.max_agent_calls:
                logger.warning("Circuit breaker: max agent calls (%d) reached", task.max_agent_calls)
                status = "circuit_breaker"
                break

            # Token budget check
            if total_tokens >= task.token_budget:
                logger.warning("Token budget exhausted (%d/%d)", total_tokens, task.token_budget)
                status = "budget_exhausted"
                break

            # Disabled agent check
            if agent_name in self._disabled_agents:
                logger.debug("Skipping disabled agent: %s", agent_name)
                continue

            # Conditional agent check
            condition = CONDITIONAL_AGENTS.get(agent_name)
            if condition and not condition(context):
                logger.debug("Skipping conditional agent: %s", agent_name)
                continue

            agent = self._get_agent(agent_name)
            agent._current_context = context

            # Build signed task message
            task_msg = self._bus.create_message(
                sender="coordinator",
                recipient=agent_name,
                message_type="task",
                payload={"input_data": task.input_data, "context": context},
            )
            self._keyring.sign_message(task_msg, "coordinator")

            # Execute agent (sequential, blocking)
            try:
                result_msg = await agent.handle(task_msg, context)
            except Exception as exc:
                logger.error("Agent %s failed: %s", agent_name, exc)
                audit_trail.append({
                    "agent": agent_name,
                    "status": "error",
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                agent.adjust_reputation(-0.1)
                continue

            # Verify signature
            if result_msg.signature and not self._keyring.verify_message(result_msg):
                logger.error("TAMPER DETECTED: Agent %s response signature invalid", agent_name)
                audit_trail.append({
                    "agent": agent_name,
                    "status": "tamper_detected",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                # Invoke auditor for investigation
                status = "tamper_detected"
                break

            # Record stats
            payload = result_msg.payload
            llm_calls = payload.get("llm_calls", 0)
            tokens = payload.get("tokens_used", 0)
            total_llm_calls += llm_calls
            total_tokens += tokens
            agents_invoked.append(agent_name)

            # Check for conflicts
            if payload.get("conflict"):
                resolution = await self._resolve_conflict(
                    agent_a=agent_name,
                    position_a=payload.get("conflict_position", ""),
                    reasoning_a=payload.get("conflict_reasoning", ""),
                    conflict_with=payload.get("conflict_with", ""),
                    context=context,
                )
                context["arbitration"] = resolution
                audit_trail.append({
                    "agent": "arbitrator",
                    "status": "conflict_resolved",
                    "resolution": resolution,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            # Update context for next agent
            context_updates = payload.get("context_updates", {})
            context.update(context_updates)

            # Track max sensitivity seen (for conditional agents)
            memories = context.get("retrieved_memories", [])
            if memories:
                max_sens = max(
                    (m.get("sensitivity", 0) if isinstance(m, dict) else getattr(m, "sensitivity", 0))
                    for m in memories
                )
                context["max_sensitivity_seen"] = max(
                    context.get("max_sensitivity_seen", 0), max_sens
                )

            # Audit entry
            audit_trail.append({
                "agent": agent_name,
                "status": "ok",
                "llm_calls": llm_calls,
                "tokens": tokens,
                "message_id": result_msg.message_id,
                "signed": bool(result_msg.signature),
                "timestamp": result_msg.timestamp.isoformat(),
            })

            # Check for blocking actions (consent required, blocked, etc.)
            if payload.get("blocked") or payload.get("consent_required"):
                if payload.get("consent_required"):
                    status = "consent_required"
                elif payload.get("all_blocked"):
                    status = "blocked"
                # Don't break — let downstream agents see the decision

        duration_ms = (time.time() - start) * 1000

        return SwarmResult(
            task_id=task.task_id,
            status=status,
            output=context,
            agents_invoked=agents_invoked,
            messages_exchanged=self._bus.total_messages,
            llm_calls_made=total_llm_calls,
            tokens_used=total_tokens,
            duration_ms=round(duration_ms, 2),
            audit_trail=audit_trail,
        )

    # ── Conflict Resolution ───────────────────────────────────────────

    async def _resolve_conflict(
        self,
        agent_a: str,
        position_a: str,
        reasoning_a: str,
        conflict_with: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Route a conflict to the Arbitrator agent."""
        case = ArbitrationCase(
            agent_a=agent_a,
            agent_a_position=position_a,
            agent_a_reasoning=reasoning_a,
            agent_b=conflict_with,
            agent_b_position=context.get(f"{conflict_with}_position", ""),
            agent_b_reasoning=context.get(f"{conflict_with}_reasoning", ""),
            context=context,
        )

        arbitrator = self._get_agent("arbitrator")
        msg = self._bus.create_message(
            sender="coordinator",
            recipient="arbitrator",
            message_type="arbitration",
            payload={"case": case.model_dump()},
        )
        self._keyring.sign_message(msg, "coordinator")

        result_msg = await arbitrator.handle(msg, context)
        return result_msg.payload.get("resolution", {})

    # ── Federated Consensus (Level 3 memories) ────────────────────────

    async def _federated_consensus(
        self,
        memory: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """For sensitivity 3: require 2/3 agreement from Governance + Policy + Sentinel."""
        votes: Dict[str, str] = {}

        for agent_name in ["governance", "policy", "sentinel"]:
            agent = self._get_agent(agent_name)
            msg = self._bus.create_message(
                sender="coordinator",
                recipient=agent_name,
                message_type="vote",
                payload={"memory": memory, "context": context, "action": "vote_access"},
            )
            self._keyring.sign_message(msg, "coordinator")

            try:
                result = await agent.handle(msg, context)
                votes[agent_name] = result.payload.get("vote", "deny")
            except Exception:
                votes[agent_name] = "deny"  # fail-safe: deny on error

        permit_count = sum(1 for v in votes.values() if v in ("permit", "approve"))
        decision = "permit" if permit_count >= 2 else "deny"

        return {
            "decision": decision,
            "votes": votes,
            "method": "federated_consensus",
        }

    # ── Single Agent Execution (for delegation) ─────────────────────

    async def _execute_single_agent(
        self,
        agent_name: str,
        input_data: Dict[str, Any],
        context: Dict[str, Any],
    ) -> AgentMessage:
        """Execute a single agent (used for tool delegation). Enforces signing + verification."""
        if agent_name in self._disabled_agents:
            raise ValueError(f"Agent '{agent_name}' is disabled")

        agent = self._get_agent(agent_name)
        agent._current_context = context
        calling_agent = context.get("calling_agent", "coordinator")

        msg = self._bus.create_message(
            sender=calling_agent,
            recipient=agent_name,
            message_type="delegation",
            payload={"input_data": input_data, "context": context},
        )
        self._keyring.sign_message(msg, calling_agent)

        result = await agent.handle(msg, context)

        # Verify signature
        if result.signature and not self._keyring.verify_message(result):
            raise ValueError(f"Tamper detected on delegated response from {agent_name}")

        return result

    # ── Agent Management ──────────────────────────────────────────────

    def set_agent_enabled(self, agent_name: str, enabled: bool) -> bool:
        """Enable or disable an agent. Returns True if state changed."""
        if enabled:
            self._disabled_agents.discard(agent_name)
        else:
            self._disabled_agents.add(agent_name)
        # Update stats if agent is loaded
        if agent_name in self._agents:
            self._agents[agent_name]._stats.enabled = enabled
        return True

    def is_agent_enabled(self, agent_name: str) -> bool:
        return agent_name not in self._disabled_agents

    def get_pipeline(self, task_type: SwarmTaskType) -> List[str]:
        """Get the current pipeline for a task type."""
        return self._pipeline_overrides.get(task_type) or TASK_PIPELINES.get(task_type, [])

    def set_pipeline(self, task_type: SwarmTaskType, agents: List[str]) -> None:
        """Override the pipeline for a task type."""
        self._pipeline_overrides[task_type] = agents

    def get_all_pipelines(self) -> Dict[str, List[str]]:
        """Get all pipelines (including overrides)."""
        result = {}
        for tt in SwarmTaskType:
            result[tt.value] = self.get_pipeline(tt)
        return result

    # ── Status & Introspection ────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        all_agent_names = ["accessor", "governance", "sentinel", "maker", "policy", "arbitrator", "auditor"]
        agents_status = {}
        for name in all_agent_names:
            if name in self._agents:
                agent = self._agents[name]
                stats = agent.stats.model_dump()
                stats["enabled"] = name not in self._disabled_agents
                stats["tools"] = self._tool_registry.get_agent_tool_names(name)
                agents_status[name] = stats
            else:
                agents_status[name] = {
                    "agent_id": name,
                    "status": "not_loaded",
                    "enabled": name not in self._disabled_agents,
                    "tools": self._tool_registry.get_agent_tool_names(name),
                }

        return {
            "swarm_active": True,
            "agents": agents_status,
            "total_messages": self._bus.total_messages,
            "constitution_version": self._constitution.schema.version,
            "constitution_principles": len(self._constitution.schema.principles),
            "pending_amendments": len(self._constitution.get_pending_amendments()),
            "pipelines": self.get_all_pipelines(),
            "total_tools": len(self._tool_registry.all_tool_names),
            "disabled_agents": sorted(self._disabled_agents),
        }

    def get_agent_stats(self, agent_name: str) -> Optional[AgentStats]:
        if agent_name in self._agents:
            return self._agents[agent_name].stats
        return None

    def get_message_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [m.model_dump() for m in self._bus.get_history(limit)]

    @property
    def constitution(self) -> Constitution:
        return self._constitution
