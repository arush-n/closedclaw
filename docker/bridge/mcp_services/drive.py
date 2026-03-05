"""
Google Drive MCP Connector — controlled access to Drive files.

Operations:
  - list_files: List files in a folder or root
  - search_files: Search by name/content
  - get_file_metadata: Get file metadata (no direct content download)
  - get_file_content: Get text file content (PII redacted)
  - upload_file: Upload a file (requires consent)
"""

import logging
from typing import Any, Dict

from .base import BaseMCPConnector

logger = logging.getLogger(__name__)


class DriveConnector(BaseMCPConnector):
    SERVICE_NAME = "drive"
    SUPPORTED_OPERATIONS = [
        "list_files",
        "search_files",
        "get_file_metadata",
        "get_file_content",
        "upload_file",
    ]

    CONSENT_REQUIRED = {"upload_file"}

    async def _execute_operation(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._oauth_token:
            return {
                "connected": False,
                "message": "Google Drive not connected. Configure Google OAuth.",
                "setup_instructions": [
                    "1. Enable Drive API in Google Cloud project",
                    "2. Create OAuth 2.0 credentials",
                    "3. Set CLOSEDCLAW_GOOGLE_OAUTH_TOKEN in your .env",
                ],
            }

        if operation == "list_files":
            return await self._list_files(params)
        elif operation == "search_files":
            return await self._search_files(params)
        elif operation == "get_file_metadata":
            return await self._get_file_metadata(params)
        elif operation == "get_file_content":
            return await self._get_file_content(params)
        elif operation == "upload_file":
            return await self._upload_file(params)
        return {"error": f"Unhandled operation: {operation}"}

    async def _list_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        folder_id = params.get("folder_id", "root")
        limit = min(params.get("limit", 20), 50)
        return {
            "folder_id": folder_id,
            "limit": limit,
            "files": [],
            "note": "Connect Google OAuth to populate.",
        }

    async def _search_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        limit = min(params.get("limit", 10), 25)
        return {
            "query": query,
            "limit": limit,
            "results": [],
            "note": "Connect Google OAuth to populate.",
        }

    async def _get_file_metadata(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_id = params.get("file_id", "")
        if not file_id:
            return {"error": "file_id is required"}
        return {
            "file_id": file_id,
            "metadata": None,
            "note": "Connect Google OAuth to populate.",
        }

    async def _get_file_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_id = params.get("file_id", "")
        if not file_id:
            return {"error": "file_id is required"}
        return {
            "file_id": file_id,
            "content": None,
            "note": "Connect Google OAuth to populate. Content will be PII-redacted.",
        }

    async def _upload_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name", "")
        if not name:
            return {"error": "'name' is required"}
        return {
            "consent_required": True,
            "action": "upload_file",
            "name": name,
            "status": "pending_consent",
        }
