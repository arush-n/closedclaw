"""
MCP Service Connectors — controlled access to external services.

Each connector implements a standardized interface for its service,
with PII redaction, audit logging, and consent enforcement built in.
All actual API calls route through closedclaw's host-side bridge for
policy enforcement.
"""

from .gmail import GmailConnector
from .notion import NotionConnector
from .drive import DriveConnector
from .slack import SlackConnector
from .github import GitHubConnector

MCP_CONNECTORS = {
    "gmail": GmailConnector,
    "notion": NotionConnector,
    "drive": DriveConnector,
    "slack": SlackConnector,
    "github": GitHubConnector,
}

__all__ = [
    "GmailConnector",
    "NotionConnector",
    "DriveConnector",
    "SlackConnector",
    "GitHubConnector",
    "MCP_CONNECTORS",
]
