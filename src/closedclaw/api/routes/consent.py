"""
Consent management endpoints for closedclaw.

Handles consent gates, pending requests, and receipt management.
"""

import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from closedclaw.api.deps import get_auth_token, get_memory
from closedclaw.api.core.memory import ClosedclawMemory
from closedclaw.api.core.crypto import get_key_manager, sign_consent_receipt, verify_consent_receipt as _verify_receipt
from closedclaw.api.core.storage import get_persistent_store
from closedclaw.api.models.consent import (
    ConsentReceipt,
    ConsentPendingRequest,
    ConsentDecision,
    ConsentDecisionResponse,
    ConsentPendingListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/consent", tags=["Consent"])

# In-memory cache backed by SQLite persistent storage
_pending_requests: Dict[str, ConsentPendingRequest] = {}
_consent_receipts: Dict[str, ConsentReceipt] = {}
_loaded_from_disk: bool = False


def _ensure_loaded() -> None:
    """Load consent data from persistent storage on first access."""
    global _pending_requests, _consent_receipts, _loaded_from_disk
    if _loaded_from_disk:
        return
    _loaded_from_disk = True
    try:
        store = get_persistent_store()
        # Load pending requests
        for row in store.load_pending_consents():
            req = ConsentPendingRequest(**row)
            _pending_requests[req.request_id] = req
        # Load receipts
        for row in store.load_consent_receipts():
            receipt = ConsentReceipt(**row)
            _consent_receipts[receipt.receipt_id] = receipt
        logger.info(
            f"Loaded {len(_pending_requests)} pending consent requests "
            f"and {len(_consent_receipts)} receipts from persistent storage"
        )
    except Exception as e:
        logger.warning(f"Failed to load consent data from storage: {e}")


@router.get("/pending", response_model=ConsentPendingListResponse)
async def list_pending_consents(
    token: str = Depends(get_auth_token),
):
    """List all pending consent requests awaiting user decision."""
    _ensure_loaded()
    pending = list(_pending_requests.values())
    return ConsentPendingListResponse(
        pending=pending,
        count=len(pending),
    )


@router.get("/pending/{request_id}", response_model=ConsentPendingRequest)
async def get_pending_consent(
    request_id: str,
    token: str = Depends(get_auth_token),
):
    """Get a specific pending consent request."""
    _ensure_loaded()
    if request_id not in _pending_requests:
        raise HTTPException(status_code=404, detail="Consent request not found")
    
    return _pending_requests[request_id]


@router.post("/{request_id}", response_model=ConsentDecisionResponse)
async def respond_to_consent(
    request_id: str,
    decision: ConsentDecision,
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Respond to a pending consent request.
    
    Creates a signed consent receipt documenting the decision.
    """
    _ensure_loaded()
    if request_id not in _pending_requests:
        raise HTTPException(status_code=404, detail="Consent request not found")
    
    pending = _pending_requests[request_id]
    
    # Create consent receipt
    receipt = ConsentReceipt(
        memory_id=pending.memory_id,
        memory_hash=pending.memory_hash,
        provider=pending.provider,
        redactions=decision.custom_redactions or pending.proposed_redactions,
        sensitivity_level=pending.sensitivity,
        user_decision=decision.decision,
        rule_triggered=pending.rule_triggered,
        user_pubkey=None,
        signature=None,
    )
    
    # Sign receipt with Ed25519
    try:
        km = get_key_manager()
        signed = sign_consent_receipt(receipt.model_dump(), km)
        receipt.user_pubkey = signed.get("user_pubkey")
        receipt.signature = signed.get("signature")
    except Exception as e:
        logger.warning(f"Failed to sign consent receipt: {e}")
    
    # Store receipt and persist
    _consent_receipts[receipt.receipt_id] = receipt
    try:
        store = get_persistent_store()
        store.save_consent_receipt(receipt.model_dump())
    except Exception as e:
        logger.warning(f"Failed to persist consent receipt: {e}")
    
    # Remove from pending (both memory and disk)
    del _pending_requests[request_id]
    try:
        store = get_persistent_store()
        store.delete_pending_consent(request_id)
    except Exception as e:
        logger.warning(f"Failed to delete pending consent from storage: {e}")
    
    # Audit logging for consent decision
    try:
        from closedclaw.api.routes.audit import add_audit_entry
        add_audit_entry(
            request_id=f"consent-{request_id}",
            provider=pending.provider,
            model="consent-gate",
            memories_used=1 if decision.decision == "approve" else 0,
            memory_ids=[pending.memory_id],
            consent_required=True,
            consent_receipt_id=receipt.receipt_id,
            query_summary=f"Consent {decision.decision}d for memory {pending.memory_id}",
        )
    except Exception as e:
        logger.warning(f"Consent audit logging failed: {e}")
    
    # Handle remember preferences — persist to SQLite for future auto-decisions
    if decision.remember_for_provider:
        try:
            store = get_persistent_store()
            store.save_consent_preference(
                pref_type="provider",
                pref_key=pending.provider,
                action=decision.decision,
            )
            logger.info(f"Remembered consent '{decision.decision}' for provider: {pending.provider}")
        except Exception as e:
            logger.warning(f"Failed to persist provider preference: {e}")
    
    if decision.remember_for_tag:
        try:
            store = get_persistent_store()
            store.save_consent_preference(
                pref_type="tag",
                pref_key=decision.remember_for_tag,
                action=decision.decision,
            )
            logger.info(f"Remembered consent '{decision.decision}' for tag: {decision.remember_for_tag}")
        except Exception as e:
            logger.warning(f"Failed to persist tag preference: {e}")
    
    message = f"Consent {decision.decision}d for memory {pending.memory_id}"
    
    return ConsentDecisionResponse(
        request_id=request_id,
        decision=decision.decision,
        receipt=receipt if decision.decision != "deny" else None,
        message=message,
    )


@router.get("/receipts")
async def list_consent_receipts(
    memory_id: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = 100,
    token: str = Depends(get_auth_token),
):
    """List consent receipts with optional filtering."""
    _ensure_loaded()
    receipts = list(_consent_receipts.values())
    
    if memory_id:
        receipts = [r for r in receipts if r.memory_id == memory_id]
    
    if provider:
        receipts = [r for r in receipts if r.provider == provider]
    
    return {
        "receipts": receipts[:limit],
        "count": len(receipts[:limit]),
        "total": len(receipts),
    }


@router.get("/receipts/{receipt_id}", response_model=ConsentReceipt)
async def get_consent_receipt(
    receipt_id: str,
    token: str = Depends(get_auth_token),
):
    """Get a specific consent receipt."""
    _ensure_loaded()
    if receipt_id not in _consent_receipts:
        raise HTTPException(status_code=404, detail="Consent receipt not found")
    
    return _consent_receipts[receipt_id]


@router.post("/receipts/{receipt_id}/verify")
async def verify_consent_receipt(
    receipt_id: str,
    token: str = Depends(get_auth_token),
):
    """
    Verify a consent receipt's signature.
    
    Checks that the receipt has not been tampered with.
    """
    _ensure_loaded()
    if receipt_id not in _consent_receipts:
        raise HTTPException(status_code=404, detail="Consent receipt not found")
    
    receipt = _consent_receipts[receipt_id]
    
    # Verify Ed25519 signature
    is_valid = False
    try:
        km = get_key_manager()
        receipt_dict = receipt.model_dump()
        is_valid = _verify_receipt(receipt_dict, km)
    except Exception as e:
        logger.warning(f"Signature verification error: {e}")
    
    return {
        "receipt_id": receipt_id,
        "valid": is_valid,
        "signature_present": receipt.signature is not None,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "message": "Signature verified" if is_valid else "Signature verification failed",
    }


def get_auto_consent_decision(
    provider: str,
    tags: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Check if a remembered consent preference covers this provider/tags.

    Returns the stored action string ("approve", "approve_redacted", "deny")
    or None if no remembered preference exists.
    """
    store = get_persistent_store()

    # Check provider-scoped preference first
    prov_pref = store.get_consent_preference("provider", provider)
    if prov_pref:
        return prov_pref

    # Check tag-scoped preferences
    if tags:
        for tag in tags:
            tag_pref = store.get_consent_preference("tag", tag)
            if tag_pref:
                return tag_pref

    return None


# Internal function to create a pending consent request
def create_consent_request(
    memory_id: str,
    memory_text: str,
    sensitivity: int,
    provider: str,
    rule_triggered: str,
    proposed_redactions: Optional[List] = None,
) -> ConsentPendingRequest:
    """Create a new pending consent request."""
    memory_hash = hashlib.sha256(memory_text.encode()).hexdigest()
    
    request = ConsentPendingRequest(
        memory_id=memory_id,
        memory_text=memory_text,
        memory_hash=memory_hash,
        sensitivity=sensitivity,
        provider=provider,
        proposed_redactions=proposed_redactions or [],
        redacted_text=None,
        rule_triggered=rule_triggered,
        expires_at=None,
        context=None,
    )
    
    _ensure_loaded()
    _pending_requests[request.request_id] = request
    
    # Persist to SQLite
    try:
        store = get_persistent_store()
        store.save_pending_consent(request.model_dump())
    except Exception as e:
        logger.warning(f"Failed to persist pending consent request: {e}")
    
    # Broadcast WebSocket notification (non-blocking, best-effort)
    try:
        import asyncio
        from closedclaw.api.routes.ws_consent import notify_consent_required
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(notify_consent_required(
                request_id=request.request_id,
                memory_id=request.memory_id,
                memory_hash=request.memory_hash,
                sensitivity=request.sensitivity,
                provider=request.provider,
                rule_triggered=request.rule_triggered or "",
            ))
        except RuntimeError:
            pass  # No event loop running (e.g. during tests)
    except Exception as e:
        logger.debug(f"WebSocket notification skipped: {e}")
    
    return request
