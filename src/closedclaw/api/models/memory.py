"""
Memory-related Pydantic models for closedclaw.

Extended memory schema with sensitivity, TTL, encryption, and consent fields.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
import uuid


class MemoryBase(BaseModel):
    """Base memory fields shared across operations."""
    content: str = Field(..., description="Memory text content", min_length=1)
    sensitivity: Optional[int] = Field(
        default=None, 
        ge=0, 
        le=3, 
        description="Sensitivity level: 0=public, 1=general, 2=personal, 3=sensitive. None = auto-classify."
    )
    tags: List[str] = Field(default_factory=list, description="Semantic category tags")
    source: Literal["conversation", "manual", "imported", "insight"] = Field(
        default="manual",
        description="Source of the memory"
    )
    expires_at: Optional[datetime] = Field(None, description="TTL expiry timestamp (null=permanent)")


class MemoryCreate(MemoryBase):
    """Schema for creating a new memory."""
    user_id: Optional[str] = Field(default="default", description="User identifier")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class MemoryUpdate(BaseModel):
    """Schema for updating an existing memory."""
    content: Optional[str] = Field(None, description="New memory content")
    sensitivity: Optional[int] = Field(None, ge=0, le=3, description="New sensitivity level")
    tags: Optional[List[str]] = Field(None, description="New tags")
    expires_at: Optional[datetime] = Field(None, description="New expiry timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata to merge")


class MemoryResponse(BaseModel):
    """Full memory response schema (closedclaw extended fields)."""
    # Standard mem0 fields
    id: str = Field(..., description="Memory UUID")
    memory: str = Field(..., description="Memory text content")
    user_id: str = Field(..., description="Owner identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    
    # closedclaw extensions
    sensitivity: int = Field(default=1, description="Sensitivity level (0-3)")
    tags: List[str] = Field(default_factory=list, description="Semantic tags")
    source: str = Field(default="conversation", description="Memory source")
    expires_at: Optional[datetime] = Field(None, description="TTL expiry")
    content_hash: Optional[str] = Field(None, description="SHA-256 of plaintext")
    encrypted: bool = Field(default=False, description="Whether memory is encrypted")
    access_count: int = Field(default=0, description="Number of times retrieved")
    last_accessed: Optional[datetime] = Field(None, description="Last access timestamp")
    consent_required: bool = Field(default=False, description="Requires consent gate")
    score: Optional[float] = Field(None, description="Relevance score (for search)")
    
    class Config:
        from_attributes = True


class MemorySearchRequest(BaseModel):
    """Schema for searching memories."""
    query: str = Field(..., description="Search query", min_length=1)
    user_id: Optional[str] = Field(default="default", description="User identifier")
    sensitivity_max: Optional[int] = Field(
        None, 
        ge=0, 
        le=3, 
        description="Maximum sensitivity level to return"
    )
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    limit: int = Field(default=10, ge=1, le=100, description="Max results to return")
    include_metadata: bool = Field(default=True, description="Include full metadata")


class MemorySearchResponse(BaseModel):
    """Schema for search results."""
    results: List[MemoryResponse]
    count: int
    query: str


class MemoryListResponse(BaseModel):
    """Schema for listing all memories."""
    memories: List[MemoryResponse]
    total: int
    user_id: str


class TagsResponse(BaseModel):
    """Schema for listing all tags."""
    tags: Dict[str, int]  # tag -> count


class MemoryAddFromMessagesRequest(BaseModel):
    """Schema for adding memory from chat messages (mem0 style)."""
    messages: List[Dict[str, str]] = Field(
        ..., 
        description="List of messages with 'role' and 'content' keys"
    )
    user_id: Optional[str] = Field(default="default", description="User identifier")
    agent_id: Optional[str] = Field(None, description="Agent identifier")
    run_id: Optional[str] = Field(None, description="Run identifier")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    infer: bool = Field(default=True, description="Use LLM to infer memories")


class MemoryBulkDeleteRequest(BaseModel):
    """Schema for bulk deleting memories."""
    memory_ids: List[str] = Field(..., description="List of memory IDs to delete", min_length=1)


class MemoryExportRequest(BaseModel):
    """Schema for exporting memories."""
    passphrase: str = Field(..., description="Encryption passphrase", min_length=8)
    include_audit: bool = Field(default=True, description="Include audit log")
    include_policies: bool = Field(default=True, description="Include policy rules")


class MemoryExportResponse(BaseModel):
    """Schema for export bundle metadata."""
    bundle_id: str
    created_at: datetime
    memory_count: int
    audit_count: Optional[int] = None
    encrypted: bool = True
    signature: str


class MemoryImportRequest(BaseModel):
    """Schema for importing memories."""
    passphrase: str = Field(..., description="Decryption passphrase", min_length=8)
    merge_strategy: Literal["skip", "replace", "merge"] = Field(
        default="skip",
        description="How to handle duplicate memories"
    )


class MemoryImportResponse(BaseModel):
    """Schema for import results."""
    imported: int
    skipped: int
    merged: int
    errors: List[str]
