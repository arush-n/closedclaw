"""
Closedclaw - Privacy-first AI memory middleware

Your Memory. Your Rules. Your Machine.
"""

from closedclaw.api import __version__

# Re-export main components for easy import
from closedclaw.api.core.config import Settings, get_settings
from closedclaw.api.core.memory import ClosedclawMemory, get_memory_instance
from closedclaw.api.core.policies import PolicyEngine, PolicyAction, PolicyRule

__all__ = [
    "__version__",
    "Settings",
    "get_settings", 
    "ClosedclawMemory",
    "get_memory_instance",
    "PolicyEngine",
    "PolicyAction",
    "PolicyRule",
]
