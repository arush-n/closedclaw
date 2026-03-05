"""
Message Bus — in-process signed & encrypted message queue for agent communication.

All inter-agent messages flow through this bus. It:
  - Records every message for audit replay
  - Tracks encryption status per message
  - Provides security metrics (encrypted %, tamper detections)
  - Stores messages with their chain hashes for tamper-evident history
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from closedclaw.api.agents.swarm.models import AgentMessage

logger = logging.getLogger(__name__)

_MAX_HISTORY = 2000


class MessageBus:
    """In-process signed + encrypted message queue with audit trail."""

    def __init__(self):
        self._history: List[AgentMessage] = []
        self._by_id: Dict[str, AgentMessage] = {}
        # Security metrics
        self._total_encrypted: int = 0
        self._total_signed: int = 0
        self._tamper_detections: int = 0
        self._replay_detections: int = 0

    def create_message(
        self,
        sender: str,
        recipient: str,
        message_type: str,
        payload: dict,
        in_reply_to: Optional[str] = None,
    ) -> AgentMessage:
        msg = AgentMessage(
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            payload=payload,
            in_reply_to=in_reply_to,
        )
        self._record(msg)
        return msg

    def record(self, msg: AgentMessage) -> None:
        """Record an externally-created message."""
        self._record(msg)

    def _record(self, msg: AgentMessage) -> None:
        self._history.append(msg)
        self._by_id[msg.message_id] = msg

        # Track security metrics
        if msg.encrypted:
            self._total_encrypted += 1
        if msg.signature:
            self._total_signed += 1

        if len(self._history) > _MAX_HISTORY:
            evicted = self._history[: len(self._history) - _MAX_HISTORY]
            self._history = self._history[-_MAX_HISTORY:]
            for m in evicted:
                self._by_id.pop(m.message_id, None)

    def record_tamper_detection(self, message_id: str, agent_name: str) -> None:
        """Record a tamper detection event."""
        self._tamper_detections += 1
        logger.warning(
            "TAMPER DETECTION #%d: message %s from agent %s",
            self._tamper_detections, message_id, agent_name,
        )

    def record_replay_detection(self, nonce: str, agent_name: str) -> None:
        """Record a replay attack detection."""
        self._replay_detections += 1
        logger.warning(
            "REPLAY DETECTION #%d: nonce %s from agent %s",
            self._replay_detections, nonce, agent_name,
        )

    def get_message(self, message_id: str) -> Optional[AgentMessage]:
        return self._by_id.get(message_id)

    def get_history(self, limit: int = 100) -> List[AgentMessage]:
        return self._history[-limit:]

    def get_conversation(self, message_id: str) -> List[AgentMessage]:
        """Walk the reply chain for a message."""
        chain: List[AgentMessage] = []
        current = self._by_id.get(message_id)
        seen = set()
        while current and current.message_id not in seen:
            chain.append(current)
            seen.add(current.message_id)
            if current.in_reply_to:
                current = self._by_id.get(current.in_reply_to)
            else:
                break
        chain.reverse()
        return chain

    def get_agent_messages(self, agent_name: str, limit: int = 50) -> List[AgentMessage]:
        """Get recent messages sent by or to a specific agent."""
        return [
            m
            for m in reversed(self._history)
            if m.sender == agent_name or m.recipient == agent_name
        ][:limit]

    def clear(self) -> None:
        self._history.clear()
        self._by_id.clear()

    @property
    def total_messages(self) -> int:
        return len(self._history)

    def get_security_metrics(self) -> Dict[str, Any]:
        """Return security metrics for the message bus."""
        total = len(self._history)
        return {
            "total_messages": total,
            "encrypted_messages": self._total_encrypted,
            "signed_messages": self._total_signed,
            "encryption_rate": (self._total_encrypted / total * 100) if total else 0,
            "signing_rate": (self._total_signed / total * 100) if total else 0,
            "tamper_detections": self._tamper_detections,
            "replay_detections": self._replay_detections,
        }

    def compute_history_hash(self) -> str:
        """Compute a SHA-256 hash of the entire message history for integrity check."""
        h = hashlib.sha256()
        for msg in self._history:
            data = json.dumps(
                msg.model_dump(exclude={"signature", "sender_pubkey"}),
                sort_keys=True,
                default=str,
            ).encode("utf-8")
            h.update(data)
        return h.hexdigest()
