"""
Notion MCP Connector — controlled access to Notion workspace.

Operations:
  - search_pages: Search pages/databases by query
  - get_page: Retrieve a page's content (PII redacted)
  - create_page: Create a new page (requires consent)
  - update_page: Update page content (requires consent)
  - list_databases: List accessible databases
  - query_database: Query a database with filters
"""

import logging
from typing import Any, Dict, List

from .base import BaseMCPConnector

logger = logging.getLogger(__name__)


class NotionConnector(BaseMCPConnector):
    SERVICE_NAME = "notion"
    SUPPORTED_OPERATIONS = [
        "search_pages",
        "get_page",
        "create_page",
        "update_page",
        "list_databases",
        "query_database",
    ]

    CONSENT_REQUIRED = {"create_page", "update_page"}

    async def _execute_operation(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        api_key = self._config.get("notion_api_key") or self._oauth_token
        if not api_key:
            return {
                "connected": False,
                "message": "Notion not connected. Configure Notion integration.",
                "setup_instructions": [
                    "1. Create a Notion integration at https://www.notion.so/my-integrations",
                    "2. Share target pages/databases with the integration",
                    "3. Set CLOSEDCLAW_NOTION_API_KEY in your .env",
                ],
            }

        if operation == "search_pages":
            return await self._search_pages(params)
        elif operation == "get_page":
            return await self._get_page(params)
        elif operation == "create_page":
            return await self._create_page(params)
        elif operation == "update_page":
            return await self._update_page(params)
        elif operation == "list_databases":
            return await self._list_databases(params)
        elif operation == "query_database":
            return await self._query_database(params)
        return {"error": f"Unhandled operation: {operation}"}

    async def _search_pages(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        limit = min(params.get("limit", 10), 25)
        return {
            "query": query,
            "limit": limit,
            "results": [],
            "note": "Connect Notion integration to populate.",
        }

    async def _get_page(self, params: Dict[str, Any]) -> Dict[str, Any]:
        page_id = params.get("page_id", "")
        if not page_id:
            return {"error": "page_id is required"}
        return {
            "page_id": page_id,
            "page": None,
            "note": "Connect Notion integration to populate. Content will be PII-redacted.",
        }

    async def _create_page(self, params: Dict[str, Any]) -> Dict[str, Any]:
        title = params.get("title", "")
        parent_id = params.get("parent_id", "")
        if not title:
            return {"error": "'title' is required"}
        return {
            "consent_required": True,
            "action": "create_page",
            "title": title,
            "parent_id": parent_id,
            "status": "pending_consent",
        }

    async def _update_page(self, params: Dict[str, Any]) -> Dict[str, Any]:
        page_id = params.get("page_id", "")
        if not page_id:
            return {"error": "page_id is required"}
        return {
            "consent_required": True,
            "action": "update_page",
            "page_id": page_id,
            "status": "pending_consent",
        }

    async def _list_databases(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "databases": [],
            "note": "Connect Notion integration to populate.",
        }

    async def _query_database(self, params: Dict[str, Any]) -> Dict[str, Any]:
        database_id = params.get("database_id", "")
        if not database_id:
            return {"error": "database_id is required"}
        return {
            "database_id": database_id,
            "results": [],
            "note": "Connect Notion integration to populate.",
        }
