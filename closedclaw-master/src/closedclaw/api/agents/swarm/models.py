"""
Swarm data models — typed envelopes for inter-agent communication.

Every message between agents is an AgentMessage with Ed25519 signature
and X25519+AES-256-GCM encrypted payload. Tasks flow through the
coordinator as SwarmTask -> SwarmResult.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Agent Identity ────────────────────────────────────────────────────
class AgentIdentity(BaseModel):
    agent_id: str
    agent_type: str
    public_key_b64: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Messages ──────────────────────────────────────────────────────────
class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sender: str
    recipient: str
    message_type: str  # "task", "result", "query", "conflict", "arbitration"
    payload: Dict[str, Any] = Field(default_factory=dict)
    in_reply_to: Optional[str] = None
    signature: Optional[str] = None
    sender_pubkey: Optional[str] = None
    # Encryption fields
    encrypted: bool = False  # True when payload is AES-256-GCM encrypted
    nonce: Optional[str] = None  # Replay-protection nonce (base64)
    chain_hash: Optional[str] = None  # Hash chain entry for tamper-evident audit


# ── Task Types ────────────────────────────────────────────────────────
class SwarmTaskType(str, Enum):
    FULL_PIPELINE = "full_pipeline"
    STORE_MEMORY = "store_memory"
    RETRIEVE_MEMORY = "retrieve_memory"
    EVALUATE_ACCESS = "evaluate_access"
    CHECK_POLICY = "check_policy"
    DETECT_HALLUCINATION = "detect_hallucination"
    RESOLVE_CONFLICT = "resolve_conflict"
    AUDIT_VERIFY = "audit_verify"
    COMPACT_MEMORIES = "compact_memories"
    EVOLVE_POLICY = "evolve_policy"
    ADDON_PROCESS = "addon_process"
    TOOL_DISPATCH = "tool_dispatch"


class SwarmTask(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    task_type: SwarmTaskType
    user_id: str = "default"
    provider: str = "ollama"
    input_data: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    max_agent_calls: int = 10
    token_budget: int = 2000
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SwarmResult(BaseModel):
    task_id: str
    status: str  # "completed", "blocked", "consent_required", "error"
    output: Dict[str, Any] = Field(default_factory=dict)
    agents_invoked: List[str] = Field(default_factory=list)
    messages_exchanged: int = 0
    llm_calls_made: int = 0
    tokens_used: int = 0
    duration_ms: float = 0.0
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)


# ── Constitution ──────────────────────────────────────────────────────
class ConstitutionPrinciple(BaseModel):
    id: str
    name: str
    description: str
    priority: int = 50  # higher = more important
    enforcement: str = "strict"  # "strict", "advisory", "default"


class ConstitutionAmendment(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    proposed_by: str = ""  # agent that proposed it
    principle: ConstitutionPrinciple
    reason: str = ""
    status: str = "pending"  # "pending", "approved", "rejected"
    proposed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConstitutionSchema(BaseModel):
    version: str = "1.0"
    name: str = "Personal Privacy Constitution"
    principles: List[ConstitutionPrinciple] = Field(default_factory=list)
    auto_generated_rules: bool = True
    max_sensitivity_cloud: int = 1
    require_consent_for_storage: bool = True
    blocked_topics: List[str] = Field(default_factory=list)
    allowed_providers: List[str] = Field(default_factory=lambda: ["ollama"])
    amendments: List[ConstitutionAmendment] = Field(default_factory=list)
    data_retention_days: Optional[int] = None


# ── Arbitration ───────────────────────────────────────────────────────
class ArbitrationCase(BaseModel):
    case_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_a: str
    agent_a_position: str
    agent_a_reasoning: str = ""
    agent_b: str
    agent_b_position: str
    agent_b_reasoning: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    resolution: Optional[str] = None
    winner: Optional[str] = None
    method: Optional[str] = None  # "constitutional", "llm_arbitration"


# ── Agent Stats ───────────────────────────────────────────────────────
class AgentStats(BaseModel):
    agent_id: str
    total_invocations: int = 0
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_tool_calls: int = 0
    errors: int = 0
    reputation: float = 1.0  # 0.0 - 1.0
    enabled: bool = True
    last_active: Optional[datetime] = None
