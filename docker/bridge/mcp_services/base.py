"""
Base MCP Connector — abstract interface for all service connectors.

Provides:
  - Standardized operation dispatch
  - PII redaction pipeline
  - Audit logging
  - Rate limiting per-service
  - OAuth token placeholder management
"""

import logging
import re
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# PII patterns to redact from service responses
_PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN-REDACTED]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[CARD-REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL-REDACTED]"),
    (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "[PHONE-REDACTED]"),
]


class BaseMCPConnector(ABC):
    """Abstract base for MCP service connectors."""

    SERVICE_NAME: str = "base"
    SUPPORTED_OPERATIONS: List[str] = []

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._oauth_token: Optional[str] = config.get("oauth_token")
        self._bridge_url: str = config.get("bridge_url", "http://host.docker.internal:8765")
        self._rate_limit = config.get("rate_limit", 30)  # requests per minute
        self._request_times: deque = deque()
        self._audit_log: List[Dict[str, Any]] = []

    def _check_rate_limit(self) -> bool:
        """Simple per-service rate limiter."""
        now = time.time()
        minute_ago = now - 60
        while self._request_times and self._request_times[0] <= minute_ago:
            self._request_times.popleft()
        if len(self._request_times) >= self._rate_limit:
            return False
        self._request_times.append(now)
        return True

    def _redact_pii(self, text: str) -> str:
        """Strip PII patterns from text content."""
        for pattern, replacement in _PII_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _redact_dict(self, data: Dict[str, Any], fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """Redact PII from string values in a dict."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self._redact_pii(value)
            elif isinstance(value, dict):
                result[key] = self._redact_dict(value, fields)
            elif isinstance(value, list):
                result[key] = [
                    self._redact_dict(item, fields) if isinstance(item, dict)
                    else self._redact_pii(item) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def _log_audit(self, operation: str, params: Dict[str, Any], success: bool) -> None:
        """Record operation for audit trail."""
        self._audit_log.append({
            "service": self.SERVICE_NAME,
            "operation": operation,
            "timestamp": time.time(),
            "success": success,
            "params_keys": list(params.keys()),
        })
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-500:]

    async def execute(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch an operation with rate limiting, PII redaction, and audit."""
        if operation not in self.SUPPORTED_OPERATIONS:
            return {
                "status": "error",
                "error": f"Unsupported operation '{operation}' for {self.SERVICE_NAME}. "
                         f"Supported: {', '.join(self.SUPPORTED_OPERATIONS)}",
            }

        if not self._check_rate_limit():
            return {"status": "error", "error": "Rate limit exceeded. Try again later."}

        try:
            result = await self._execute_operation(operation, params)
            # Redact PII from results
            if isinstance(result, dict):
                result = self._redact_dict(result)
            self._log_audit(operation, params, True)
            return {"status": "success", "operation": operation, "data": result}
        except Exception as exc:
            logger.error("%s operation %s failed: %s", self.SERVICE_NAME, operation, exc)
            self._log_audit(operation, params, False)
            return {"status": "error", "error": str(exc)}

    @abstractmethod
    async def _execute_operation(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Implement service-specific operation logic."""
        ...

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return recent audit entries."""
        return list(self._audit_log)
