"""
Memory API endpoints for closedclaw.

Provides CRUD operations for the memory vault with privacy controls.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query

from closedclaw.api.core.memory import ClosedclawMemory
from closedclaw.api.deps import get_memory, get_auth_token, get_user_id
from closedclaw.api.models.memory import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryListResponse,
    TagsResponse,
    MemoryAddFromMessagesRequest,
    MemoryBulkDeleteRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/memory", tags=["Memory"])


@router.get("", response_model=MemorySearchResponse)
async def search_memories(
    q: str = Query(..., description="Search query"),
    sensitivity_max: Optional[int] = Query(None, ge=0, le=3, description="Max sensitivity"),
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    user_id: str = Depends(get_user_id),
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Search memories semantically.
    
    Returns memories matching the query, filtered by sensitivity and tags.
    """
    tag_list = tags.split(",") if tags else None
    
    try:
        results = await asyncio.to_thread(
            memory.search,
            query=q,
            user_id=user_id,
            sensitivity_max=sensitivity_max,
            tags=tag_list,
            limit=limit,
        )
        
        # Convert to response format
        memories = [_to_memory_response(mem) for mem in results.get("results", [])]
        
        return MemorySearchResponse(
            results=memories,
            count=len(memories),
            query=q,
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Memory search failed")


@router.post("", response_model=MemoryResponse)
async def add_memory(
    memory_create: MemoryCreate,
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Add a new memory manually.
    
    Memory will be classified for sensitivity and encrypted at rest.
    """
    try:
        result = await asyncio.to_thread(
            memory.add,
            content=memory_create.content,
            user_id=memory_create.user_id or "default",
            sensitivity=memory_create.sensitivity,
            tags=memory_create.tags,
            source=memory_create.source,
            expires_at=memory_create.expires_at,
            metadata=memory_create.metadata,
            consent_given=memory_create.consent_given,
        )

        # Consent gate — memory was not stored, return classification info
        if result.get("consent_required") and result.get("result") is None:
            raise HTTPException(
                status_code=451,  # Unavailable For Legal Reasons
                detail={
                    "error": "consent_required",
                    "message": "This memory contains sensitive content and requires explicit consent before storage.",
                    "sensitivity": result["sensitivity"],
                    "classification": result.get("classification"),
                    "content_hash": result.get("content_hash"),
                    "hint": "Resubmit with consent_given=true after user approval.",
                },
            )

        # Get the created memory
        results_list = result.get("result", {}).get("results", [])
        mem_result = results_list[0] if results_list else {}
        extended = result.get("extended", {})
        mem_id = mem_result.get("id", str(uuid.uuid4()))
        
        # Audit logging for memory creation
        try:
            from closedclaw.api.routes.audit import add_audit_entry
            add_audit_entry(
                request_id=f"mem-add-{uuid.uuid4()}",
                provider="local",
                model="memory-vault",
                memories_used=1,
                memory_ids=[mem_id],
                query_summary=f"Memory added: sensitivity={extended.get('sensitivity', 0)}, source={extended.get('source', 'manual')}",
            )
        except Exception as e:
            logger.warning(f"Memory add audit logging failed: {e}")
        
        return MemoryResponse(
            id=mem_id,
            memory=memory_create.content,
            user_id=memory_create.user_id or "default",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            sensitivity=extended.get("sensitivity", memory_create.sensitivity),
            tags=extended.get("tags", memory_create.tags),
            source=extended.get("source", memory_create.source),
            expires_at=memory_create.expires_at,
            content_hash=result.get("content_hash"),
            encrypted=extended.get("encrypted", False),
            last_accessed=None,
            score=None,
        )
    except Exception as e:
        logger.error(f"Add memory failed: {e}")
        raise HTTPException(status_code=500, detail="Memory creation failed")


@router.post("/messages")
async def add_memory_from_messages(
    request: MemoryAddFromMessagesRequest,
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Add memories extracted from chat messages (mem0 style).
    
    Uses LLM to extract memorable facts from the conversation.
    """
    try:
        # Format messages as string for mem0
        message_text = "\n".join(
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in request.messages
        )
        
        result = await asyncio.to_thread(
            memory.add,
            content=message_text,
            user_id=request.user_id or "default",
            source="conversation",
            metadata=request.metadata,
        )
        
        return {
            "status": "success",
            "memories_added": len(result.get("result", {}).get("results", [])),
            "result": result.get("result"),
        }
    except Exception as e:
        logger.error(f"Add from messages failed: {e}")
        raise HTTPException(status_code=500, detail="Memory extraction failed")


@router.get("/all", response_model=MemoryListResponse)
async def list_all_memories(
    user_id: str = Depends(get_user_id),
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    List all memories for a user.
    """
    try:
        results = memory.get_all(user_id=user_id)
        
        memories = [_to_memory_response(mem) for mem in results.get("results", [])]
        
        return MemoryListResponse(
            memories=memories,
            total=len(memories),
            user_id=user_id,
        )
    except Exception as e:
        logger.error(f"List memories failed: {e}")
        raise HTTPException(status_code=500, detail="Memory listing failed")


@router.get("/tags", response_model=TagsResponse)
async def list_tags(
    user_id: str = Depends(get_user_id),
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    List all tags in the vault with their counts.
    """
    try:
        tags = memory.get_tags(user_id=user_id)
        return TagsResponse(tags=tags)
    except Exception as e:
        logger.error(f"List tags failed: {e}")
        raise HTTPException(status_code=500, detail="Tag listing failed")


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory_by_id(
    memory_id: str,
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Get a specific memory by ID.
    """
    try:
        result = memory.get(memory_id)
        if not result:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        return _to_memory_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get memory failed: {e}")
        raise HTTPException(status_code=500, detail="Memory retrieval failed")


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    update: MemoryUpdate,
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Update a memory's content or metadata.
    """
    try:
        # First get the existing memory
        existing = memory.get(memory_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        memory.update(
            memory_id=memory_id,
            content=update.content,
            sensitivity=update.sensitivity,
            tags=update.tags,
            expires_at=update.expires_at,
            metadata=update.metadata,
        )
        
        # Get updated memory
        updated = memory.get(memory_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Memory not found after update")
        
        # Audit logging for memory update
        try:
            from closedclaw.api.routes.audit import add_audit_entry
            add_audit_entry(
                request_id=f"mem-update-{uuid.uuid4()}",
                provider="local",
                model="memory-vault",
                memories_used=1,
                memory_ids=[memory_id],
                query_summary=f"Memory updated: {list(update.model_dump(exclude_unset=True).keys())}",
            )
        except Exception as e:
            logger.warning(f"Memory update audit logging failed: {e}")
        
        return _to_memory_response(updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update memory failed: {e}")
        raise HTTPException(status_code=500, detail="Memory update failed")


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Delete a memory (cryptographic deletion).
    
    DEK is destroyed, making ciphertext permanently irrecoverable.
    """
    try:
        success = memory.delete(memory_id)
        if not success:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        # Audit logging for memory deletion
        try:
            from closedclaw.api.routes.audit import add_audit_entry
            add_audit_entry(
                request_id=f"mem-delete-{uuid.uuid4()}",
                provider="local",
                model="memory-vault",
                memories_used=0,
                memory_ids=[memory_id],
                query_summary=f"Memory deleted: {memory_id}",
            )
        except Exception as e:
            logger.warning(f"Memory delete audit logging failed: {e}")
        
        return {
            "status": "deleted",
            "memory_id": memory_id,
            "method": "cryptographic_deletion",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete memory failed: {e}")
        raise HTTPException(status_code=500, detail="Memory deletion failed")


@router.delete("")
async def delete_all_memories(
    user_id: str = Depends(get_user_id),
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
    confirm: bool = Query(False, description="Must be true to confirm deletion"),
):
    """
    Delete all memories for a user.
    
    Requires confirm=true query parameter.
    """
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="Must provide confirm=true to delete all memories"
        )
    
    try:
        success = memory.delete_all(user_id=user_id)
        return {
            "status": "deleted",
            "user_id": user_id,
            "method": "cryptographic_deletion",
        }
    except Exception as e:
        logger.error(f"Delete all memories failed: {e}")
        raise HTTPException(status_code=500, detail="Delete all memories failed")


@router.post("/bulk-delete")
async def bulk_delete_memories(
    request: MemoryBulkDeleteRequest,
    memory: ClosedclawMemory = Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Delete multiple memories by ID.
    """
    deleted = []
    failed = []
    
    for mem_id in request.memory_ids:
        try:
            if memory.delete(mem_id):
                deleted.append(mem_id)
            else:
                failed.append({"id": mem_id, "error": "Not found"})
        except Exception as e:
            failed.append({"id": mem_id, "error": str(e)})
    
    return {
        "deleted": deleted,
        "failed": failed,
        "deleted_count": len(deleted),
        "failed_count": len(failed),
    }


def _to_memory_response(mem: dict) -> MemoryResponse:
    """Convert mem0 memory dict to MemoryResponse."""
    return MemoryResponse(
        id=mem.get("id", ""),
        memory=mem.get("memory", mem.get("content", "")),
        user_id=mem.get("user_id", "default"),
        created_at=mem.get("created_at", datetime.now(timezone.utc)),
        updated_at=mem.get("updated_at"),
        sensitivity=mem.get("sensitivity", 0),
        tags=mem.get("tags", []),
        source=mem.get("source", "conversation"),
        expires_at=mem.get("expires_at"),
        content_hash=mem.get("content_hash"),
        encrypted=mem.get("encrypted", False),
        access_count=mem.get("access_count", 0),
        last_accessed=mem.get("last_accessed"),
        consent_required=mem.get("consent_required", False),
        score=mem.get("score"),
    )
