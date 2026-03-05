"""
closedclaw agent swarm — crypto-secured agentic memory team.

7 specialized micro-agents coordinated by a SwarmCoordinator:
  Governance, Maker, Accessor, Policy, Sentinel, Arbitrator, Auditor
"""

from closedclaw.api.agents.swarm.models import (
    AgentMessage,
    SwarmTask,
    SwarmTaskType,
    SwarmResult,
)

__all__ = [
    "AgentMessage",
    "SwarmTask",
    "SwarmTaskType",
    "SwarmResult",
    "get_swarm",
]

_swarm_instance = None


def get_swarm(**kwargs):
    """Get or create the singleton SwarmCoordinator."""
    global _swarm_instance
    if _swarm_instance is None:
        from closedclaw.api.agents.swarm.coordinator import SwarmCoordinator
        _swarm_instance = SwarmCoordinator(**kwargs)
    return _swarm_instance
