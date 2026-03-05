"""
Closedclaw Control Bridge

Runs INSIDE Docker. Mediates all communication between openclaw (Docker)
and closedclaw (host). Enforces restricted app policies, memory safety,
and audit logging.

This is the enforcement point — openclaw can only reach the outside world
through this bridge, and the bridge enforces closedclaw's policies.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("BRIDGE_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [bridge] %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("control_bridge")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_PATH = Path(os.getenv("BRIDGE_CONFIG_PATH", "/config/closedclaw.yaml"))
CLOSEDCLAW_HOST_URL = os.getenv(
    "CLOSEDCLAW_HOST_URL", "http://host.docker.internal:8765"
)
OPENCLAW_INTERNAL_URL = os.getenv(
    "OPENCLAW_INTERNAL_URL", "http://openmemory-mcp:8766"
)

_config: dict = {}
_http: Optional[httpx.AsyncClient] = None


def load_config() -> dict:
    """Load closedclaw config from YAML. Falls back to defaults on error."""
    global _config
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            _config = yaml.safe_load(f) or {}
    else:
        logger.warning("Config not found at %s — using defaults", CONFIG_PATH)
        _config = {}
    return _config


def _get_restricted_apps() -> dict:
    return _config.get("restricted_apps", {})


def _get_memory_guardian() -> dict:
    return _config.get("memory_guardian", {})


def _get_controlled_mcps() -> dict:
    return _config.get("controlled_mcps", {})


# ---------------------------------------------------------------------------
# Audit log (append-only JSON-lines)
# ---------------------------------------------------------------------------
AUDIT_DIR = Path("/data/audit")


def _audit_log(event_type: str, details: dict) -> None:
    """Append an audit event. Non-blocking best-effort."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.time(),
        "type": event_type,
        **details,
    }
    entry["hash"] = hashlib.sha256(
        json.dumps(entry, sort_keys=True).encode()
    ).hexdigest()[:16]
    audit_file = AUDIT_DIR / f"bridge_{time.strftime('%Y%m%d')}.jsonl"
    try:
        with open(audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        logger.error("Audit write failed: %s", exc)


# ---------------------------------------------------------------------------
# Domain / URL checking
# ---------------------------------------------------------------------------

def _matches_domain(url: str, domain_patterns: list[str]) -> bool:
    """Check if a URL matches any of the domain patterns."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
    except Exception:
        return False

    for pattern in domain_patterns:
        if pattern.startswith("*."):
            suffix = pattern[2:]
            if hostname == suffix or hostname.endswith("." + suffix):
                return True
        elif hostname == pattern:
            return True
    return False


def check_url_restricted(url: str) -> tuple[bool, Optional[str], Optional[dict]]:
    """Check if a URL targets a restricted service.

    Returns (is_restricted, service_name, policy) or (False, None, None).
    """
    for svc_name, svc_cfg in _get_restricted_apps().items():
        domains = svc_cfg.get("domains", [])
        if _matches_domain(url, domains):
            return True, svc_name, svc_cfg
    return False, None, None


# ---------------------------------------------------------------------------
# Memory Guardian
# ---------------------------------------------------------------------------

def check_memory_content(content: str) -> tuple[str, Optional[str], Optional[str]]:
    """Screen memory content against dangerous patterns.

    Returns (action, category, detail).
    action is one of: "allow", "block", "redact_and_store".
    """
    guardian = _get_memory_guardian()
    if not guardian.get("enabled", True):
        return "allow", None, None

    for category, rule in guardian.get("dangerous_patterns", {}).items():
        for pattern in rule.get("patterns", []):
            try:
                if re.search(pattern, content, re.IGNORECASE):
                    action = rule.get("action", "block")
                    severity = rule.get("severity", "unknown")
                    _audit_log(
                        "memory_guardian_trigger",
                        {
                            "category": category,
                            "severity": severity,
                            "action": action,
                            "content_hash": hashlib.sha256(
                                content.encode()
                            ).hexdigest()[:16],
                        },
                    )
                    return action, category, f"Matched pattern in '{category}' (severity: {severity})"
            except re.error:
                logger.warning("Invalid regex in guardian config: %s", pattern)

    return "allow", None, None


def redact_memory_content(content: str) -> str:
    """Apply basic PII redaction patterns to memory content."""
    guardian = _get_memory_guardian()
    redact_rules = guardian.get("dangerous_patterns", {}).get("personal_identifiers", {})
    for pattern in redact_rules.get("patterns", []):
        try:
            content = re.sub(pattern, "[REDACTED]", content, flags=re.IGNORECASE)
        except re.error:
            pass

    # Also redact obvious PII patterns
    # Credit card numbers
    content = re.sub(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b", "[CARD-REDACTED]", content)
    # SSN
    content = re.sub(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "[SSN-REDACTED]", content)
    # API keys / tokens (common patterns)
    content = re.sub(
        r"\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|xox[bpas]-[A-Za-z0-9\-]+)\b",
        "[TOKEN-REDACTED]",
        content,
    )

    return content


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
_rate_counters: dict[str, list[float]] = {}


def _check_rate_limit(service_name: str, policy: dict) -> bool:
    """Return True if within rate limits, False if exceeded."""
    limits = policy.get("rate_limit")
    if not limits:
        return True

    now = time.time()
    key = service_name
    if key not in _rate_counters:
        _rate_counters[key] = []

    # Prune entries older than 24h
    _rate_counters[key] = [t for t in _rate_counters[key] if now - t < 86400]

    hourly_count = sum(1 for t in _rate_counters[key] if now - t < 3600)
    daily_count = len(_rate_counters[key])

    max_hourly = limits.get("max_requests_per_hour", 9999)
    max_daily = limits.get("max_requests_per_day", 9999)

    if hourly_count >= max_hourly or daily_count >= max_daily:
        return False

    _rate_counters[key].append(now)
    return True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ProxyRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, str] = {}
    body: Any = None


class MemoryWriteRequest(BaseModel):
    content: str
    user_id: str = "default-user"
    metadata: dict[str, Any] = {}
    categories: list[str] = []


class MCPRequest(BaseModel):
    service: str          # "email", "calendar", "files"
    operation: str        # "get_inbox_summary", etc.
    params: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http
    load_config()
    _http = httpx.AsyncClient(timeout=30.0)
    logger.info("Control bridge started — enforcing %d restricted app policies",
                len(_get_restricted_apps()))
    yield
    if _http:
        await _http.aclose()


app = FastAPI(
    title="Closedclaw Control Bridge",
    description="Mediates between openclaw (Docker) and closedclaw (host). "
                "Enforces restricted access, memory safety, and audit logging.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Internal Docker network only
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check — also verifies closedclaw host is reachable."""
    closedclaw_ok = False
    try:
        resp = await _http.get(f"{CLOSEDCLAW_HOST_URL}/health", timeout=5.0)
        closedclaw_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "ok",
        "closedclaw_reachable": closedclaw_ok,
        "restricted_apps_count": len(_get_restricted_apps()),
        "memory_guardian_enabled": _get_memory_guardian().get("enabled", True),
        "timestamp": time.time(),
    }


@app.post("/proxy/check-url")
async def check_url(request: ProxyRequest):
    """Check if a URL is restricted before openclaw attempts access."""
    is_restricted, service_name, policy = check_url_restricted(request.url)

    if not is_restricted:
        return {"allowed": True, "service": None}

    _audit_log("url_check", {
        "url": request.url,
        "service": service_name,
        "policy": policy.get("policy", "unknown"),
    })

    policy_action = policy.get("policy", "block_all")

    if policy_action == "block_all":
        return {
            "allowed": False,
            "service": service_name,
            "reason": f"Access to {service_name} is blocked by closedclaw policy",
            "suggestion": "Use the controlled MCP endpoint instead",
        }

    if policy_action == "proxy_through_closedclaw":
        allowed_ops = policy.get("allowed_operations", [])
        return {
            "allowed": False,
            "service": service_name,
            "reason": f"Direct access to {service_name} is restricted",
            "proxy_available": True,
            "allowed_operations": allowed_ops,
            "suggestion": f"Use /mcp/{service_name} endpoint instead",
        }

    return {"allowed": False, "service": service_name, "reason": "Unknown policy"}


@app.post("/proxy/request")
async def proxy_request(request: ProxyRequest):
    """Proxy a request through closedclaw with policy enforcement."""
    is_restricted, service_name, policy = check_url_restricted(request.url)

    if is_restricted:
        policy_action = policy.get("policy", "block_all")
        if policy_action == "block_all":
            _audit_log("proxy_blocked", {
                "url": request.url,
                "service": service_name,
            })
            raise HTTPException(
                status_code=403,
                detail=f"Access to {service_name} is blocked by closedclaw policy. "
                       f"Use controlled MCP endpoints instead.",
            )

        if not _check_rate_limit(service_name, policy):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for {service_name}",
            )

    # Forward to closedclaw host for proxying
    try:
        resp = await _http.post(
            f"{CLOSEDCLAW_HOST_URL}/v1/bridge/proxy",
            json={
                "url": request.url,
                "method": request.method,
                "headers": request.headers,
                "body": request.body,
                "restricted_service": service_name,
            },
        )
        return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Cannot reach closedclaw host: {exc}")


@app.post("/mcp/{service}")
async def mcp_proxy(service: str, request: MCPRequest):
    """Controlled MCP endpoint — routes through closedclaw's controlled MCPs."""
    mcps = _get_controlled_mcps()
    mcp_key = f"{service}_mcp"

    if mcp_key not in mcps:
        raise HTTPException(
            status_code=404,
            detail=f"No controlled MCP configured for '{service}'",
        )

    mcp_config = mcps[mcp_key]

    # Validate operation is allowed
    allowed_ops = [op["name"] for op in mcp_config.get("operations", [])]
    if request.operation not in allowed_ops:
        _audit_log("mcp_operation_blocked", {
            "service": service,
            "operation": request.operation,
        })
        raise HTTPException(
            status_code=403,
            detail=f"Operation '{request.operation}' is not allowed for {service}. "
                   f"Allowed: {allowed_ops}",
        )

    _audit_log("mcp_request", {
        "service": service,
        "operation": request.operation,
    })

    # Forward to closedclaw host's MCP endpoint
    try:
        resp = await _http.post(
            mcp_config["endpoint"],
            json={
                "operation": request.operation,
                "params": request.params,
                "source": "openclaw_bridge",
            },
        )
        return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach closedclaw MCP endpoint: {exc}",
        )


@app.post("/memory/screen")
async def screen_memory(request: MemoryWriteRequest):
    """Screen a memory write before openclaw stores it.

    Returns the screened content (possibly redacted) or blocks the write.
    """
    action, category, detail = check_memory_content(request.content)

    if action == "block":
        _audit_log("memory_blocked", {
            "category": category,
            "user_id": request.user_id,
            "content_hash": hashlib.sha256(
                request.content.encode()
            ).hexdigest()[:16],
        })
        return {
            "allowed": False,
            "action": "block",
            "reason": detail,
            "category": category,
        }

    if action == "redact_and_store":
        redacted = redact_memory_content(request.content)
        _audit_log("memory_redacted", {
            "category": category,
            "user_id": request.user_id,
        })
        return {
            "allowed": True,
            "action": "redact_and_store",
            "content": redacted,
            "original_category": category,
            "reason": detail,
        }

    # Allowed as-is
    return {
        "allowed": True,
        "action": "allow",
        "content": request.content,
    }


@app.post("/memory/classify")
async def classify_memory(request: MemoryWriteRequest):
    """Classify a memory's sensitivity level using closedclaw's agent system."""
    guardian = _get_memory_guardian()
    sensitive_cats = guardian.get("sensitive_categories", [])

    # Check if any requested categories overlap with sensitive ones
    overlap = set(request.categories) & set(sensitive_cats)
    sensitivity = 1  # default
    if overlap:
        sensitivity = 2  # sensitive
    
    # Check content patterns for critical sensitivity
    action, category, _ = check_memory_content(request.content)
    if action == "block":
        sensitivity = 3  # critical

    return {
        "sensitivity": sensitivity,
        "sensitive_categories_detected": list(overlap),
        "content_flags": category,
    }


@app.get("/config/restricted-apps")
async def get_restricted_apps():
    """Return the current restricted app policies (for openclaw to read)."""
    apps = _get_restricted_apps()
    # Strip internal fields, return only what openclaw needs
    result = {}
    for name, cfg in apps.items():
        result[name] = {
            "domains": cfg.get("domains", []),
            "policy": cfg.get("policy"),
            "allowed_operations": cfg.get("allowed_operations", []),
            "blocked_operations": cfg.get("blocked_operations", []),
        }
    return result


@app.get("/config/memory-rules")
async def get_memory_rules():
    """Return memory guardian rules for openclaw to self-enforce."""
    guardian = _get_memory_guardian()
    return {
        "enabled": guardian.get("enabled", True),
        "sensitive_categories": guardian.get("sensitive_categories", []),
        "retention": guardian.get("retention", {}),
    }


@app.post("/config/reload")
async def reload_config():
    """Hot-reload configuration from disk."""
    load_config()
    _audit_log("config_reload", {})
    return {"status": "reloaded", "restricted_apps": len(_get_restricted_apps())}


@app.post("/memory/sync")
async def memory_sync(request: Request):
    """Receive memory sync notifications from host-side closedclaw.

    When the browser extension captures a memory on the host, it notifies
    this endpoint so openclaw can update its index if needed.
    """
    body = await request.json()
    user_id = body.get("user_id", "default")
    source = body.get("source", "unknown")
    sensitivity = body.get("sensitivity", 0)

    _audit_log("memory_sync", {
        "user_id": user_id,
        "source": source,
        "sensitivity": sensitivity,
    })

    # Notify openclaw to refresh its memory index
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{OPENCLAW_INTERNAL_URL}/memory/refresh",
                json={"user_id": user_id, "source": source},
            )
    except Exception as exc:
        logger.debug("Openclaw memory refresh notification failed (non-critical): %s", exc)

    return {"status": "synced", "user_id": user_id}


@app.get("/audit/recent")
async def get_recent_audit(limit: int = 50):
    """Return recent audit log entries."""
    if limit > 500:
        limit = 500
    
    today_file = AUDIT_DIR / f"bridge_{time.strftime('%Y%m%d')}.jsonl"
    entries = []
    if today_file.exists():
        with open(today_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    
    return {"entries": entries[-limit:], "total": len(entries)}
