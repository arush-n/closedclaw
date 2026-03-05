"""
Closedclaw FastAPI Application

Main application setup with all routes and middleware.
"""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi

from closedclaw.api import __version__  # noqa: E402
from closedclaw.api.core.config import get_settings, init_closedclaw
from closedclaw.api.routes import (
    health,
    memory,
    proxy,
    consent,
    audit,
    memory_chat,
    ws_consent,
    policies,
    insights,
    clawdbot,
    mcp,
    swarm,
)

# Configure logging
_log_level_name = os.getenv("CLOSEDCLAW_LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    startup_started = time.perf_counter()
    startup_started_epoch = time.time()
    startup_info = {
        "started_at": startup_started_epoch,
        "startup_duration_ms": 0,
        "degraded_mode": False,
        "degraded_reason": None,
        "provider": None,
        "local_engine": {"enabled": False},
        "fast_startup": False,
    }
    app.state.startup_info = startup_info

    logger.info("Starting closedclaw server...")
    try:
        settings = init_closedclaw()
    except Exception:
        logger.exception("Failed to initialize closedclaw configuration")
        raise

    startup_info["provider"] = settings.provider
    startup_info["local_engine"] = {"enabled": bool(settings.local_engine.enabled)}

    logger.info(f"Closedclaw initialized at {settings.closedclaw_dir}")
    logger.info(f"Provider: {settings.provider}")
    logger.info(f"Memory DB: {settings.memory_db_path}")

    # Check local engine status
    if settings.local_engine.enabled:
        from closedclaw.api.core.config import init_local_engine

        fast_startup = _env_flag("CLOSEDCLAW_FAST_STARTUP", default=True)
        startup_info["fast_startup"] = fast_startup
        try:
            local_status = init_local_engine(settings, fast_startup=fast_startup)
            startup_info["local_engine"] = {
                "enabled": True,
                "ollama_installed": bool(local_status.get("ollama_installed")),
                "ollama_running": bool(local_status.get("ollama_running")),
                "models_available": len(local_status.get("models_available", [])),
                "hardware_profile": local_status.get("hardware_profile"),
                "llm_model": settings.local_engine.llm_model,
            }
            if local_status["ollama_running"]:
                logger.info(
                    f"Local engine: Ollama running, {len(local_status['models_available'])} models available"
                )
                logger.info(f"Hardware profile: {local_status['hardware_profile']}")
                logger.info(f"LLM model: {settings.local_engine.llm_model}")
            elif local_status["ollama_installed"]:
                logger.warning("Local engine: Ollama installed but not running")
            else:
                logger.warning("Local engine: Ollama not installed")
        except Exception as exc:
            startup_info["degraded_mode"] = True
            startup_info["degraded_reason"] = f"local_engine_init_failed: {type(exc).__name__}"
            logger.warning(f"Failed to initialize local engine: {exc}")

    startup_duration_ms = round((time.perf_counter() - startup_started) * 1000, 2)
    startup_info["startup_duration_ms"] = startup_duration_ms
    app.state.startup_info = startup_info
    logger.info(
        "Startup complete in %.2fms%s",
        startup_duration_ms,
        " (degraded mode)" if startup_info["degraded_mode"] else "",
    )
    
    yield
    
    # Shutdown
    # Close shared httpx AsyncClient if it was opened
    try:
        from closedclaw.api.routes.proxy import _HTTP_CLIENT as _proxy_http_client
        if _proxy_http_client is not None:
            await _proxy_http_client.aclose()
    except Exception:
        pass

    uptime_seconds = max(0.0, time.time() - startup_started_epoch)
    logger.info("Shutting down closedclaw server after %.1fs uptime...", uptime_seconds)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title="Closedclaw",
        description="""
# Closedclaw API

**Your Memory. Your Rules. Your Machine.**

Closedclaw is a privacy-first AI memory middleware that wraps mem0 with consent-gated, 
encrypted, and auditable personal data governance.

## Features

- **OpenAI-Compatible Proxy**: Drop-in replacement for OpenAI API with memory enrichment
- **Memory Vault**: CRUD operations for personal memories with sensitivity classification
- **Privacy Firewall**: Policy-based access control with PII redaction
- **Consent Gates**: Explicit consent for sensitive memory sharing
- **Audit Log**: Hash-chained, signed log of all context injections

## Quick Start

1. Point your OpenAI SDK to `http://localhost:8765/v1`
2. All your existing tools now have private, on-device memory

## Authentication

All endpoints require authentication via:
- `Authorization: Bearer <token>` header
- `X-API-Key: <token>` header

Get your token from `~/.closedclaw/token`
        """,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    
    # CORS middleware (local-only by default)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        GZipMiddleware,
        minimum_size=1024,
        compresslevel=5,
    )
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc) if settings.debug else "An unexpected error occurred",
            },
        )
    
    # Include routers
    app.include_router(health.router)
    app.include_router(memory.router)
    app.include_router(proxy.router)
    app.include_router(consent.router)
    app.include_router(audit.router)
    app.include_router(memory_chat.router)
    app.include_router(ws_consent.router)
    app.include_router(policies.router)
    app.include_router(insights.router)
    app.include_router(clawdbot.router)
    app.include_router(mcp.router)
    app.include_router(swarm.router)

    # Custom OpenAPI schema
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        openapi_schema = get_openapi(
            title="Closedclaw API",
            version=__version__,
            description=app.description,
            routes=app.routes,
        )
        
        # Add server URLs
        openapi_schema["servers"] = [
            {"url": f"http://localhost:{settings.port}", "description": "Local server"},
        ]
        
        # Add security schemes
        openapi_schema["components"]["securitySchemes"] = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "description": "Local authentication token from ~/.closedclaw/token",
            },
            "apiKey": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key header",
            },
        }
        
        # Add tags descriptions
        openapi_schema["tags"] = [
            {
                "name": "Health",
                "description": "Health checks and system status",
            },
            {
                "name": "Memory",
                "description": "Memory vault CRUD operations",
            },
            {
                "name": "Proxy",
                "description": "OpenAI-compatible proxy with memory enrichment",
            },
            {
                "name": "Consent",
                "description": "Consent gates and receipt management",
            },
            {
                "name": "Audit",
                "description": "Audit log access and verification",
            },
            {
                "name": "Policies",
                "description": "Policy rules and policy simulation",
            },
            {
                "name": "Insights",
                "description": "Memory trends and expiration insights",
            },
            {
                "name": "ClawdBot",
                "description": "Adapter endpoint for ClawdBot memory/chat integrations",
            },
            {
                "name": "MCP",
                "description": "Model Context Protocol server discovery and tool forwarding",
            },
            {
                "name": "Agent Swarm",
                "description": "Crypto-secured agentic memory team with Ed25519-signed inter-agent communication",
            },
        ]
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = custom_openapi
    
    return app


# Create the app instance
app = create_app()


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    reload: bool = False,
    log_level: str = "info",
):
    """Run the uvicorn server."""
    import uvicorn
    
    uvicorn.run(
        "closedclaw.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


if __name__ == "__main__":
    run_server(reload=True)
