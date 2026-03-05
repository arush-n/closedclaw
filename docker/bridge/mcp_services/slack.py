"""
Slack MCP Connector — controlled access to Slack workspace.

Operations:
  - list_channels: List channels the bot has access to
  - search_messages: Search messages by query
  - get_channel_history: Recent messages in a channel
  - send_message: Post a message (requires consent)
  - get_user_info: Get user profile info
"""

import logging
from typing import Any, Dict

from .base import BaseMCPConnector

logger = logging.getLogger(__name__)


class SlackConnector(BaseMCPConnector):
    SERVICE_NAME = "slack"
    SUPPORTED_OPERATIONS = [
        "list_channels",
        "search_messages",
        "get_channel_history",
        "send_message",
        "get_user_info",
    ]

    CONSENT_REQUIRED = {"send_message"}

    async def _execute_operation(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        bot_token = self._config.get("slack_bot_token") or self._oauth_token
        if not bot_token:
            return {
                "connected": False,
                "message": "Slack not connected. Configure Slack Bot token.",
                "setup_instructions": [
                    "1. Create a Slack App at https://api.slack.com/apps",
                    "2. Add Bot Token Scopes (channels:read, chat:write, search:read, users:read)",
                    "3. Install the app to your workspace",
                    "4. Set CLOSEDCLAW_SLACK_BOT_TOKEN in your .env",
                ],
            }

        if operation == "list_channels":
            return await self._list_channels(params)
        elif operation == "search_messages":
            return await self._search_messages(params)
        elif operation == "get_channel_history":
            return await self._get_channel_history(params)
        elif operation == "send_message":
            return await self._send_message(params)
        elif operation == "get_user_info":
            return await self._get_user_info(params)
        return {"error": f"Unhandled operation: {operation}"}

    async def _list_channels(self, params: Dict[str, Any]) -> Dict[str, Any]:
        limit = min(params.get("limit", 20), 50)
        return {
            "limit": limit,
            "channels": [],
            "note": "Connect Slack Bot token to populate.",
        }

    async def _search_messages(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        limit = min(params.get("limit", 10), 25)
        return {
            "query": query,
            "limit": limit,
            "results": [],
            "note": "Connect Slack Bot token to populate.",
        }

    async def _get_channel_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        channel_id = params.get("channel_id", "")
        if not channel_id:
            return {"error": "channel_id is required"}
        limit = min(params.get("limit", 20), 50)
        return {
            "channel_id": channel_id,
            "limit": limit,
            "messages": [],
            "note": "Connect Slack Bot token to populate.",
        }

    async def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        channel_id = params.get("channel_id", "")
        text = params.get("text", "")
        if not channel_id or not text:
            return {"error": "Both 'channel_id' and 'text' are required"}
        return {
            "consent_required": True,
            "action": "send_message",
            "channel_id": channel_id,
            "text_preview": text[:100],
            "status": "pending_consent",
        }

    async def _get_user_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        user_id = params.get("user_id", "")
        if not user_id:
            return {"error": "user_id is required"}
        return {
            "user_id": user_id,
            "user": None,
            "note": "Connect Slack Bot token to populate.",
        }
