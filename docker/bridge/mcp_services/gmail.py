"""
Gmail MCP Connector — controlled email access via Gmail API.

Operations:
  - get_inbox_summary: Recent email subjects/senders (no bodies)
  - search_emails: Search by query, returns metadata only
  - get_email: Get a single email (body redacted of PII)
  - send_email: Send email (requires consent, redacts PII in logs)
  - get_labels: List Gmail labels
"""

import logging
from typing import Any, Dict, List

from .base import BaseMCPConnector

logger = logging.getLogger(__name__)


class GmailConnector(BaseMCPConnector):
    SERVICE_NAME = "gmail"
    SUPPORTED_OPERATIONS = [
        "get_inbox_summary",
        "search_emails",
        "get_email",
        "send_email",
        "get_labels",
    ]

    # Operations that require explicit user consent
    CONSENT_REQUIRED = {"send_email"}

    async def _execute_operation(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._oauth_token:
            return {
                "connected": False,
                "message": "Gmail not connected. Configure Google OAuth in closedclaw settings.",
                "setup_instructions": [
                    "1. Create a Google Cloud project with Gmail API enabled",
                    "2. Create OAuth 2.0 credentials (Desktop application)",
                    "3. Set CLOSEDCLAW_GOOGLE_OAUTH_TOKEN in your .env",
                ],
            }

        if operation == "get_inbox_summary":
            return await self._get_inbox_summary(params)
        elif operation == "search_emails":
            return await self._search_emails(params)
        elif operation == "get_email":
            return await self._get_email(params)
        elif operation == "send_email":
            return await self._send_email(params)
        elif operation == "get_labels":
            return await self._get_labels(params)
        return {"error": f"Unhandled operation: {operation}"}

    async def _get_inbox_summary(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return recent inbox messages — subjects and senders only, no bodies."""
        limit = min(params.get("limit", 10), 25)
        return {
            "description": "Inbox summary (subjects and senders only — no message bodies)",
            "limit": limit,
            "messages": [],
            "note": "Connect Gmail OAuth to populate. Bodies are never returned in summaries.",
        }

    async def _search_emails(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search emails by query — returns metadata only."""
        query = params.get("query", "")
        limit = min(params.get("limit", 10), 25)
        return {
            "query": query,
            "limit": limit,
            "results": [],
            "note": "Connect Gmail OAuth to populate.",
        }

    async def _get_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get a single email — body is PII-redacted."""
        email_id = params.get("email_id", "")
        if not email_id:
            return {"error": "email_id is required"}
        return {
            "email_id": email_id,
            "message": None,
            "note": "Connect Gmail OAuth to populate. Body will be PII-redacted.",
        }

    async def _send_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send an email — requires consent gate."""
        to = params.get("to", "")
        subject = params.get("subject", "")
        if not to or not subject:
            return {"error": "Both 'to' and 'subject' are required"}
        return {
            "consent_required": True,
            "action": "send_email",
            "to": self._redact_pii(to),
            "subject": subject,
            "status": "pending_consent",
            "note": "Connect Gmail OAuth and approve consent to send.",
        }

    async def _get_labels(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List Gmail labels."""
        return {
            "labels": [],
            "note": "Connect Gmail OAuth to populate.",
        }
