"""
Consent-related Pydantic models for closedclaw.

Consent receipts, gates, and approval schemas.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
import uuid


class RedactionEntry(BaseModel):
    """A single redaction applied to a memory."""
    entity_type: str = Field(..., description="Type of entity redacted (PERSON, EMAIL, etc.)")
    original_text: Optional[str] = Field(None, description="Original text (stored locally only)")
    placeholder: str = Field(..., description="Placeholder used in redacted text")
    start_pos: int = Field(..., description="Start position in original text")
    end_pos: int = Field(..., description="End position in original text")


class ConsentReceiptCreate(BaseModel):
    """Schema for creating a consent receipt."""
    memory_id: str = Field(..., description="Referenced memory ID")
    provider: str = Field(..., description="Target LLM provider")
    user_decision: Literal["approve", "approve_redacted", "deny"] = Field(
        ..., 
        description="User's consent decision"
    )
    redactions: List[RedactionEntry] = Field(
        default_factory=list, 
        description="Redactions applied before sending"
    )


class ConsentReceipt(BaseModel):
    """
    Full consent receipt schema.
    
    A cryptographically signed record of a consent decision.
    """
    receipt_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), 
        description="Unique receipt ID"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Receipt creation time"
    )
    memory_id: str = Field(..., description="Referenced memory ID")
    memory_hash: str = Field(..., description="SHA-256 of memory content at consent time")
    provider: str = Field(..., description="LLM provider memory was approved for")
    redactions: List[RedactionEntry] = Field(
        default_factory=list, 
        description="Redactions applied"
    )
    sensitivity_level: int = Field(..., ge=0, le=3, description="Sensitivity at consent time")
    user_decision: Literal["approve", "approve_redacted", "deny"] = Field(
        ..., 
        description="User's decision"
    )
    rule_triggered: Optional[str] = Field(None, description="Policy rule that required consent")
    user_pubkey: Optional[str] = Field(None, description="User's Ed25519 public key (hex)")
    signature: Optional[str] = Field(None, description="Ed25519 signature (hex)")
    
    class Config:
        from_attributes = True


class ConsentPendingRequest(BaseModel):
    """A pending consent request awaiting user decision."""
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), 
        description="Unique request ID"
    )
    memory_id: str = Field(..., description="Memory requiring consent")
    memory_text: str = Field(..., description="Full memory text (for user review)")
    memory_hash: str = Field(..., description="SHA-256 of memory content")
    sensitivity: int = Field(..., ge=0, le=3, description="Memory sensitivity level")
    provider: str = Field(..., description="Target LLM provider")
    proposed_redactions: List[RedactionEntry] = Field(
        default_factory=list, 
        description="Proposed redactions"
    )
    redacted_text: Optional[str] = Field(None, description="Text after proposed redactions")
    rule_triggered: str = Field(..., description="Policy rule that required consent")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="When request was created"
    )
    expires_at: Optional[datetime] = Field(None, description="When request expires")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class ConsentDecision(BaseModel):
    """User's decision on a pending consent request."""
    decision: Literal["approve", "approve_redacted", "deny"] = Field(
        ..., 
        description="User's consent decision"
    )
    custom_redactions: Optional[List[RedactionEntry]] = Field(
        None, 
        description="Custom redactions (if modifying proposed)"
    )
    remember_for_provider: bool = Field(
        default=False, 
        description="Remember this decision for similar requests to this provider"
    )
    remember_for_tag: Optional[str] = Field(
        None, 
        description="Remember decision for memories with this tag"
    )


class ConsentDecisionResponse(BaseModel):
    """Response after processing a consent decision."""
    request_id: str
    decision: str
    receipt: Optional[ConsentReceipt] = None
    message: str


class ConsentPendingListResponse(BaseModel):
    """List of pending consent requests."""
    pending: List[ConsentPendingRequest]
    count: int
