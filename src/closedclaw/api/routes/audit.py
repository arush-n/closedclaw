"""
Audit log endpoints for closedclaw.

Provides access to the append-only, hash-chained audit log.
"""

import logging
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from closedclaw.api.deps import get_auth_token
from closedclaw.api.core.crypto import get_key_manager, sign_audit_entry, verify_audit_entry
from closedclaw.api.core.storage import get_persistent_store
from closedclaw.api.models.audit import (
    AuditEntry,
    AuditEntryDetail,
    AuditListRequest,
    AuditListResponse,
    AuditVerifyResponse,
    AuditExportResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/audit", tags=["Audit"])

# In-memory cache backed by SQLite persistent storage
_MAX_AUDIT_CACHE = 10_000  # keep at most 10k entries in memory
_audit_entries: List[AuditEntry] = []
_audit_by_id: Dict[str, AuditEntry] = {}
_audit_by_request: Dict[str, List[AuditEntry]] = {}
_last_hash: Optional[str] = None
_loaded_from_disk: bool = False


def _ensure_loaded() -> None:
    """Load audit entries from persistent storage on first access."""
    global _audit_entries, _audit_by_id, _audit_by_request, _last_hash, _loaded_from_disk
    if _loaded_from_disk:
        return
    _loaded_from_disk = True
    try:
        store = get_persistent_store()
        rows = store.load_audit_entries(limit=100_000)
        for row in reversed(rows):  # rows come DESC, we want chronological
            entry = AuditEntry(**row)
            _audit_entries.append(entry)
            _audit_by_id[entry.entry_id] = entry
            _audit_by_request.setdefault(entry.request_id, []).append(entry)
        _last_hash = store.get_last_audit_hash()
        logger.info(f"Loaded {len(_audit_entries)} audit entries from persistent storage")
    except Exception as e:
        logger.warning(f"Failed to load audit entries from storage: {e}")


def _compute_entry_hash(entry: AuditEntry, prev_hash: Optional[str]) -> str:
    """Compute SHA-256 hash for an audit entry."""
    # Create canonical JSON representation
    entry_dict = entry.model_dump(exclude={"entry_hash", "signature", "prev_hash"})
    entry_dict["prev_hash"] = prev_hash
    canonical = json.dumps(entry_dict, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def add_audit_entry(
    request_id: str,
    provider: str,
    model: str,
    memories_retrieved: int = 0,
    memories_used: int = 0,
    memory_ids: Optional[List[str]] = None,
    redactions_applied: int = 0,
    blocked_memories: int = 0,
    consent_required: bool = False,
    consent_receipt_id: Optional[str] = None,
    context_tokens: int = 0,
    total_tokens: Optional[int] = None,
    query_summary: Optional[str] = None,
) -> AuditEntry:
    """Add a new entry to the audit log."""
    global _last_hash
    _ensure_loaded()
    
    entry = AuditEntry(
        request_id=request_id,
        provider=provider,
        model=model,
        memories_retrieved=memories_retrieved,
        memories_used=memories_used,
        memory_ids=memory_ids or [],
        redactions_applied=redactions_applied,
        blocked_memories=blocked_memories,
        consent_required=consent_required,
        consent_receipt_id=consent_receipt_id,
        context_tokens=context_tokens,
        total_tokens=total_tokens,
        prev_hash=_last_hash,
        entry_hash=None,
        signature=None,
    )
    
    # Compute hash
    entry.entry_hash = _compute_entry_hash(entry, _last_hash)
    _last_hash = entry.entry_hash
    
    # Sign with Ed25519
    try:
        km = get_key_manager()
        entry_dict = entry.model_dump(exclude={"signature"})
        entry.signature = km.sign_json(entry_dict, exclude_keys=("signature",))
    except Exception as e:
        logger.warning(f"Failed to sign audit entry: {e}")
        entry.signature = None
    
    _audit_entries.append(entry)
    _audit_by_id[entry.entry_id] = entry
    _audit_by_request.setdefault(entry.request_id, []).append(entry)

    # Evict oldest entries if the in-memory cache exceeds the cap
    if len(_audit_entries) > _MAX_AUDIT_CACHE:
        evicted = _audit_entries[:-_MAX_AUDIT_CACHE]
        _audit_entries[:] = _audit_entries[-_MAX_AUDIT_CACHE:]
        for old in evicted:
            _audit_by_id.pop(old.entry_id, None)
            req_list = _audit_by_request.get(old.request_id)
            if req_list:
                try:
                    req_list.remove(old)
                except ValueError:
                    pass
                if not req_list:
                    _audit_by_request.pop(old.request_id, None)
    
    # Persist to SQLite
    try:
        store = get_persistent_store()
        store.save_audit_entry(entry.model_dump())
    except Exception as e:
        logger.warning(f"Failed to persist audit entry: {e}")
    
    return entry


@router.get("", response_model=AuditListResponse)
async def list_audit_entries(
    from_time: Optional[datetime] = Query(None, description="Start time filter"),
    to_time: Optional[datetime] = Query(None, description="End time filter"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    has_consent: Optional[bool] = Query(None, description="Filter by consent requirement"),
    limit: int = Query(100, ge=1, le=1000, description="Max entries"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    token: str = Depends(get_auth_token),
):
    """
    Retrieve audit log entries with filtering.
    
    Returns a paginated list of audit entries.
    """
    _ensure_loaded()

    if from_time is None and to_time is None and provider is None and has_consent is None:
        total = len(_audit_entries)
        if total == 0:
            page: List[AuditEntry] = []
        else:
            start = max(total - offset - limit, 0)
            stop = max(total - offset, 0)
            page = list(reversed(_audit_entries[start:stop]))

        return AuditListResponse(
            entries=page,
            total=total,
            offset=offset,
            limit=limit,
        )

    total = 0
    page: List[AuditEntry] = []
    page_end = offset + limit

    for entry in reversed(_audit_entries):
        if from_time and entry.timestamp < from_time:
            continue
        if to_time and entry.timestamp > to_time:
            continue
        if provider and entry.provider != provider:
            continue
        if has_consent is not None and entry.consent_required != has_consent:
            continue

        if total >= offset and len(page) < limit:
            page.append(entry)

        total += 1
    
    return AuditListResponse(
        entries=page,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/verify", response_model=AuditVerifyResponse)
async def verify_audit_chain(
    token: str = Depends(get_auth_token),
):
    """
    Verify the integrity of the audit log hash chain.
    
    Checks that no entries have been tampered with.
    """
    _ensure_loaded()
    if not _audit_entries:
        return AuditVerifyResponse(
            valid=True,
            entries_checked=0,
            first_entry=None,
            last_entry=None,
            broken_at=None,
            message="Audit log is empty",
        )
    
    prev_hash = None
    broken_at = None
    
    for entry in _audit_entries:
        # Verify prev_hash matches
        if entry.prev_hash != prev_hash:
            broken_at = entry.entry_id
            break
        
        # Verify entry hash
        expected_hash = _compute_entry_hash(entry, prev_hash)
        if entry.entry_hash != expected_hash:
            broken_at = entry.entry_id
            break
        
        prev_hash = entry.entry_hash
    
    if broken_at:
        return AuditVerifyResponse(
            valid=False,
            entries_checked=len(_audit_entries),
            first_entry=_audit_entries[0].entry_id if _audit_entries else None,
            last_entry=_audit_entries[-1].entry_id if _audit_entries else None,
            broken_at=broken_at,
            message=f"Hash chain integrity violation at entry {broken_at}",
        )
    
    return AuditVerifyResponse(
        valid=True,
        entries_checked=len(_audit_entries),
        first_entry=_audit_entries[0].entry_id if _audit_entries else None,
        last_entry=_audit_entries[-1].entry_id if _audit_entries else None,
        broken_at=None,
        message="Hash chain integrity verified",
    )


@router.get("/export", response_model=AuditExportResponse)
async def export_audit_log(
    from_time: Optional[datetime] = Query(None),
    to_time: Optional[datetime] = Query(None),
    token: str = Depends(get_auth_token),
):
    """
    Export the audit log as a signed bundle.
    
    Returns metadata about the export bundle.
    """
    import uuid
    
    _ensure_loaded()
    filtered: List[AuditEntry] = []
    for entry in _audit_entries:
        if from_time and entry.timestamp < from_time:
            continue
        if to_time and entry.timestamp > to_time:
            continue
        filtered.append(entry)
    
    # Compute bundle hash
    bundle_content = json.dumps(
        [e.model_dump() for e in filtered],
        sort_keys=True,
        default=str,
    )
    bundle_hash = hashlib.sha256(bundle_content.encode()).hexdigest()
    
    # Sign export bundle with Ed25519
    try:
        km = get_key_manager()
        signature = km.sign(bundle_content.encode())
    except Exception:
        signature = bundle_hash  # Fallback to hash if signing fails
    
    return AuditExportResponse(
        bundle_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        entries_count=len(filtered),
        from_time=from_time,
        to_time=to_time,
        signature=signature,
    )


@router.get("/{entry_id}", response_model=AuditEntryDetail)
async def get_audit_entry(
    entry_id: str,
    token: str = Depends(get_auth_token),
):
    """Get a specific audit entry with full details."""
    _ensure_loaded()
    entry = _audit_by_id.get(entry_id)
    if entry:
        return AuditEntryDetail(**entry.model_dump())
    
    raise HTTPException(status_code=404, detail="Audit entry not found")


@router.get("/request/{request_id}")
async def get_audit_by_request(
    request_id: str,
    token: str = Depends(get_auth_token),
):
    """Get audit entries for a specific request ID."""
    _ensure_loaded()
    entries = _audit_by_request.get(request_id, [])
    
    return {
        "request_id": request_id,
        "entries": entries,
        "count": len(entries),
    }
