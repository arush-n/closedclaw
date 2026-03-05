"""
Closedclaw FastAPI Dependencies

Provides dependency injection for authentication, memory, policies, etc.
"""

import logging
import re
import threading
from typing import Optional, Any
from collections import deque

from fastapi import Depends, HTTPException, Security, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from closedclaw.api.core.config import Settings, get_settings
from closedclaw.api.core.memory import ClosedclawMemory, get_memory_instance
from closedclaw.api.core.policies import PolicyEngine, load_policies

logger = logging.getLogger(__name__)

# HTTP Bearer security scheme
security = HTTPBearer(auto_error=False)
_SAFE_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _extract_token(
    credentials: Optional[HTTPAuthorizationCredentials],
    x_api_key: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    """Extract token from supported auth headers."""
    if credentials:
        return credentials.credentials
    if x_api_key:
        return x_api_key
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return None


def _is_provider_api_key(token: str) -> bool:
    """Detect known provider key prefixes."""
    return token.startswith(("sk-", "anthropic-", "gsk_", "tog_"))


async def get_auth_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    settings: Settings = Depends(get_settings),
) -> str:
    """
    Validate authentication token.
    
    Supports:
    - Bearer token in Authorization header
    - X-API-Key header
    - OpenAI-style Authorization: Bearer sk-...
    """
    token = _extract_token(credentials, x_api_key, authorization)
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if settings.is_local_auth_token(token):
        return token

    # Optional compatibility mode for direct provider-key auth
    if settings.allow_provider_api_key_auth and _is_provider_api_key(token):
        return token
    
    raise HTTPException(
        status_code=401,
        detail="Invalid authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_auth_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    settings: Settings = Depends(get_settings),
) -> Optional[str]:
    """Get auth token if provided, but don't require it."""
    token = _extract_token(credentials, x_api_key, authorization)
    if not token:
        return None

    if settings.is_local_auth_token(token):
        return token

    if settings.allow_provider_api_key_auth and _is_provider_api_key(token):
        return token

    # Optional auth should not raise; treat invalid token as unauthenticated.
    return None


def get_memory(settings: Settings = Depends(get_settings)) -> ClosedclawMemory:
    """Get the memory instance."""
    # Build mem0 config from settings
    config = _build_mem0_config(settings)
    return get_memory_instance(
        config,
        require_consent_level=settings.require_consent_level,
    )


_mem0_config_cache_key: Optional[tuple] = None
_mem0_config_cache_value: Optional[dict[str, Any]] = None
_mem0_cache_lock = threading.Lock()


def _build_mem0_config(settings: Settings) -> dict[str, Any]:
    """Build mem0 configuration from settings."""
    global _mem0_config_cache_key, _mem0_config_cache_value

    cache_key = (
        settings.provider,
        str(settings.memory_db_path),
        settings.openai_api_key,
        settings.default_model,
        settings.embedding_model,
        settings.local_model,
        settings.ollama_base_url,
        settings.qdrant_host,
        settings.qdrant_port,
        settings.qdrant_collection,
    )
    with _mem0_cache_lock:
        if _mem0_config_cache_key == cache_key and _mem0_config_cache_value is not None:
            return _mem0_config_cache_value

    config: dict[str, Any] = {
        "version": "v1.1",
        "history_db_path": str(settings.memory_db_path),
    }
    
    # Configure LLM provider
    if settings.provider == "openai" and settings.openai_api_key:
        config["llm"] = {
            "provider": "openai",
            "config": {
                "api_key": settings.openai_api_key,
                "model": settings.default_model,
                "temperature": 0.2,
            }
        }
        config["embedder"] = {
            "provider": "openai",
            "config": {
                "api_key": settings.openai_api_key,
                "model": settings.embedding_model,
            }
        }
        config["vector_store"] = {
            "provider": "qdrant",
            "config": {
                "host": settings.qdrant_host,
                "port": settings.qdrant_port,
                "collection_name": settings.qdrant_collection,
                "embedding_model_dims": 1536,
            }
        }
    elif settings.provider == "ollama":
        config["llm"] = {
            "provider": "ollama",
            "config": {
                "model": settings.local_model,
                "ollama_base_url": settings.ollama_base_url,
            }
        }
        config["embedder"] = {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text",
                "ollama_base_url": settings.ollama_base_url,
            }
        }
        config["vector_store"] = {
            "provider": "qdrant",
            "config": {
                "host": settings.qdrant_host,
                "port": settings.qdrant_port,
                "collection_name": settings.qdrant_collection,
                "embedding_model_dims": 768,
            }
        }
    
    with _mem0_cache_lock:
        _mem0_config_cache_key = cache_key
        _mem0_config_cache_value = config
    return config


# Module-level policy engine cache
_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine(settings: Settings = Depends(get_settings)) -> PolicyEngine:
    """Get the policy engine (cached after first load)."""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = load_policies(settings.policies_dir)
    return _policy_engine


def reload_policy_engine(settings: Settings) -> PolicyEngine:
    """Reload policy engine from disk and refresh module cache."""
    global _policy_engine
    _policy_engine = load_policies(settings.policies_dir)
    return _policy_engine


async def get_user_id(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> str:
    """
    Get user ID from request.
    
    Priority:
    1. X-User-ID header
    2. Request body (for POST requests)
    3. Query parameter
    4. Default
    """
    if x_user_id:
        if not _SAFE_USER_ID_PATTERN.fullmatch(x_user_id):
            raise HTTPException(status_code=400, detail="Invalid user_id format")
        return x_user_id
    
    # Try to get from query params
    user_id = request.query_params.get("user_id")
    if user_id:
        if not _SAFE_USER_ID_PATTERN.fullmatch(user_id):
            raise HTTPException(status_code=400, detail="Invalid user_id format")
        return user_id
    
    return "default"


class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self._requests: dict[str, deque[float]] = {}
    
    async def check(self, key: str) -> bool:
        """Check if request is within rate limit."""
        import time
        now = time.time()
        minute_ago = now - 60

        request_times = self._requests.setdefault(key, deque())

        # Evict old timestamps in O(k_evicted)
        while request_times and request_times[0] <= minute_ago:
            request_times.popleft()

        # Check limit
        if len(request_times) >= self.requests_per_minute:
            return False

        # Record request
        request_times.append(now)
        return True


# Global rate limiter instance
_rate_limiter = RateLimiter()


def get_swarm_coordinator():
    """Get the SwarmCoordinator singleton (lazy init, returns None if swarm disabled)."""
    settings = get_settings()
    if not settings.swarm_enabled:
        return None
    from closedclaw.api.agents.swarm import get_swarm
    return get_swarm()


async def check_rate_limit(
    request: Request,
    token: str = Depends(get_auth_token),
) -> None:
    """Check rate limit for the request."""
    # Use token as rate limit key
    key = token[:16] if len(token) > 16 else token
    
    if not await _rate_limiter.check(key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait before making more requests.",
        )
