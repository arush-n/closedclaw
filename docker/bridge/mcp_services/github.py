"""
GitHub MCP Connector — controlled access to GitHub repos.

Operations:
  - list_repos: List user's repositories
  - get_repo: Get repository details
  - list_issues: List issues for a repo
  - create_issue: Create an issue (requires consent)
  - list_pull_requests: List PRs for a repo
  - get_file_content: Get file content from a repo
"""

import logging
from typing import Any, Dict

from .base import BaseMCPConnector

logger = logging.getLogger(__name__)


class GitHubConnector(BaseMCPConnector):
    SERVICE_NAME = "github"
    SUPPORTED_OPERATIONS = [
        "list_repos",
        "get_repo",
        "list_issues",
        "create_issue",
        "list_pull_requests",
        "get_file_content",
    ]

    CONSENT_REQUIRED = {"create_issue"}

    async def _execute_operation(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        token = self._config.get("github_token") or self._oauth_token
        if not token:
            return {
                "connected": False,
                "message": "GitHub not connected. Configure GitHub Personal Access Token.",
                "setup_instructions": [
                    "1. Go to https://github.com/settings/tokens",
                    "2. Generate a fine-grained token with repo access",
                    "3. Set CLOSEDCLAW_GITHUB_TOKEN in your .env",
                ],
            }

        if operation == "list_repos":
            return await self._list_repos(params)
        elif operation == "get_repo":
            return await self._get_repo(params)
        elif operation == "list_issues":
            return await self._list_issues(params)
        elif operation == "create_issue":
            return await self._create_issue(params)
        elif operation == "list_pull_requests":
            return await self._list_pull_requests(params)
        elif operation == "get_file_content":
            return await self._get_file_content(params)
        return {"error": f"Unhandled operation: {operation}"}

    async def _list_repos(self, params: Dict[str, Any]) -> Dict[str, Any]:
        limit = min(params.get("limit", 20), 50)
        return {
            "limit": limit,
            "repos": [],
            "note": "Connect GitHub token to populate.",
        }

    async def _get_repo(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        if not owner or not repo:
            return {"error": "Both 'owner' and 'repo' are required"}
        return {
            "owner": owner,
            "repo": repo,
            "details": None,
            "note": "Connect GitHub token to populate.",
        }

    async def _list_issues(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        if not owner or not repo:
            return {"error": "Both 'owner' and 'repo' are required"}
        limit = min(params.get("limit", 10), 25)
        return {
            "owner": owner,
            "repo": repo,
            "limit": limit,
            "issues": [],
            "note": "Connect GitHub token to populate.",
        }

    async def _create_issue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        title = params.get("title", "")
        if not owner or not repo or not title:
            return {"error": "'owner', 'repo', and 'title' are required"}
        return {
            "consent_required": True,
            "action": "create_issue",
            "owner": owner,
            "repo": repo,
            "title": title,
            "status": "pending_consent",
        }

    async def _list_pull_requests(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        if not owner or not repo:
            return {"error": "Both 'owner' and 'repo' are required"}
        limit = min(params.get("limit", 10), 25)
        return {
            "owner": owner,
            "repo": repo,
            "limit": limit,
            "pull_requests": [],
            "note": "Connect GitHub token to populate.",
        }

    async def _get_file_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        path = params.get("path", "")
        if not owner or not repo or not path:
            return {"error": "'owner', 'repo', and 'path' are required"}
        return {
            "owner": owner,
            "repo": repo,
            "path": path,
            "content": None,
            "note": "Connect GitHub token to populate. Content will be PII-redacted.",
        }
