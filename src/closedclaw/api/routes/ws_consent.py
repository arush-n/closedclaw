"""
WebSocket endpoint for real-time consent notifications.

Clients (e.g. the dashboard) can connect and receive push notifications
when a consent-required memory event fires, so they can show a UI prompt
without polling.

Usage:
    ws://localhost:8765/ws/consent?token=<api_token>
"""

import asyncio
import logging
from typing import Dict, Set
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.websockets import WebSocketState

import hmac

from closedclaw.api.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

# ---------------------------------------------------------------------------
# Connection Registry
# ---------------------------------------------------------------------------

class ConsentNotifier:
    """
    Singleton that manages active WebSocket connections and broadcasts
    consent-gate events to all connected clients.
    """

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info(f"WebSocket client connected ({len(self._connections)} total)")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        logger.info(f"WebSocket client disconnected ({len(self._connections)} total)")

    async def broadcast(self, event: dict) -> None:
        """Send an event to all connected clients.  Dead connections are pruned."""
        dead: Set[WebSocket] = set()

        async with self._lock:
            targets = set(self._connections)

        for ws in targets:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(event)
            except Exception:
                dead.add(ws)

        if dead:
            async with self._lock:
                self._connections -= dead

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Singleton
_notifier = ConsentNotifier()


def get_notifier() -> ConsentNotifier:
    """Return the singleton ConsentNotifier."""
    return _notifier


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/consent")
async def consent_ws(
    websocket: WebSocket,
    token: str = Query(..., description="API bearer token"),
):
    """
    WebSocket endpoint for real-time consent notifications.

    Send a JSON message to subscribe:
        {"action": "ping"}

    Receive notifications:
        {
          "event": "consent_required",
          "request_id": "...",
          "memory_id": "...",
          "sensitivity": 3,
          "provider": "openai",
          "rule_triggered": "block-level3-cloud",
          "timestamp": "2024-01-01T00:00:00Z"
        }
    """
    # Authenticate
    settings = get_settings()
    try:
        expected_token = settings.get_or_create_token()
    except Exception:
        await websocket.close(code=4500, reason="Token unavailable")
        return

    if not hmac.compare_digest(token, expected_token):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    notifier = get_notifier()
    await notifier.connect(websocket)

    try:
        # Send welcome
        await websocket.send_json({
            "event": "connected",
            "message": "Closedclaw consent notification stream",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Keep connection alive; handle incoming pings
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                if data.get("action") == "ping":
                    await websocket.send_json({
                        "event": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
            except asyncio.TimeoutError:
                # Send heartbeat to detect dropped connections
                await websocket.send_json({
                    "event": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WebSocket error: {e}")
    finally:
        await notifier.disconnect(websocket)


# ---------------------------------------------------------------------------
# Helper used by consent.py to fire notifications
# ---------------------------------------------------------------------------

async def notify_consent_required(
    request_id: str,
    memory_id: str,
    memory_hash: str,
    sensitivity: int,
    provider: str,
    rule_triggered: str,
) -> None:
    """
    Broadcast a consent_required event to all dashboard clients.

    Call this from create_consent_request() after persisting the record.
    """
    notifier = get_notifier()
    if notifier.connection_count == 0:
        return  # Skip marshalling if no listeners

    event = {
        "event": "consent_required",
        "request_id": request_id,
        "memory_id": memory_id,
        "memory_hash": memory_hash,
        "sensitivity": sensitivity,
        "provider": provider,
        "rule_triggered": rule_triggered,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await notifier.broadcast(event)
