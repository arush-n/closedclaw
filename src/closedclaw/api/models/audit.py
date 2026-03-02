"""
Audit-related Pydantic models for closedclaw.

Audit log entries and verification schemas.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


class AuditEntry(BaseModel):
    """
    A single audit log entry.
    
    Records every LLM request that passes through closedclaw.
    """
    entry_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), 
        description="Unique entry ID"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Entry timestamp"
    )
    
    # Request info
    request_id: str = Field(..., description="Unique request ID")
    provider: str = Field(..., description="LLM provider used")
    model: str = Field(..., description="Model used")
    
    # Memory context
    memories_retrieved: int = Field(default=0, description="Number of memories retrieved")
    memories_used: int = Field(default=0, description="Number of memories actually used")
    memory_ids: List[str] = Field(default_factory=list, description="IDs of memories used")
    
    # Privacy actions
    redactions_applied: int = Field(default=0, description="Number of redactions applied")
    blocked_memories: int = Field(default=0, description="Number of memories blocked")
    consent_required: bool = Field(default=False, description="Whether consent was required")
    consent_receipt_id: Optional[str] = Field(None, description="Associated consent receipt")
    
    # Token usage
    context_tokens: int = Field(default=0, description="Tokens used for context")
    total_tokens: Optional[int] = Field(None, description="Total tokens in request")
    
    # Hash chain
    prev_hash: Optional[str] = Field(None, description="Hash of previous entry")
    entry_hash: Optional[str] = Field(None, description="SHA-256 hash of this entry")
    signature: Optional[str] = Field(None, description="Ed25519 signature")
    
    class Config:
        from_attributes = True


class AuditEntryDetail(AuditEntry):
    """Extended audit entry with full details."""
    # Additional detail fields (only shown in detail view)
    query_summary: Optional[str] = Field(None, description="Summary of user query")
    memories_detail: Optional[List[Dict[str, Any]]] = Field(
        None, 
        description="Details of each memory used"
    )
    redaction_map: Optional[Dict[str, str]] = Field(
        None, 
        description="Original to redacted mapping"
    )
    provider_response_summary: Optional[str] = Field(
        None, 
        description="Summary of provider response"
    )


class AuditListRequest(BaseModel):
    """Schema for listing audit entries."""
    from_time: Optional[datetime] = Field(None, description="Start time filter")
    to_time: Optional[datetime] = Field(None, description="End time filter")
    provider: Optional[str] = Field(None, description="Filter by provider")
    has_consent: Optional[bool] = Field(None, description="Filter by consent requirement")
    limit: int = Field(default=100, ge=1, le=1000, description="Max entries to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class AuditListResponse(BaseModel):
    """Response for audit log listing."""
    entries: List[AuditEntry]
    total: int
    offset: int
    limit: int


class AuditVerifyResponse(BaseModel):
    """Response for audit log verification."""
    valid: bool = Field(..., description="Whether the hash chain is intact")
    entries_checked: int = Field(..., description="Number of entries verified")
    first_entry: Optional[str] = Field(None, description="ID of first entry")
    last_entry: Optional[str] = Field(None, description="ID of last entry")
    broken_at: Optional[str] = Field(
        None, 
        description="Entry ID where chain breaks (if invalid)"
    )
    message: str


class AuditExportResponse(BaseModel):
    """Response for audit log export."""
    bundle_id: str
    created_at: datetime
    entries_count: int
    from_time: Optional[datetime] = None
    to_time: Optional[datetime] = None
    signature: str
