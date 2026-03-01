"""
Insight Engine API Routes for closedclaw.

Provides endpoints to run on-demand insight analysis and retrieve results.
All processing runs locally using Ollama — no data leaves the machine.
"""

import asyncio
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from closedclaw.api.deps import get_auth_token, get_memory, get_user_id
from closedclaw.api.core.insights import (
    InsightEngine,
    InsightResult,
    TrendItem,
    ContradictionAlert,
    ExpiringMemory,
    get_insight_engine,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/insights", tags=["Insights"])


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================

class InsightRunRequest(BaseModel):
    """Request to trigger an on-demand insight analysis."""
    weeks: int = Field(default=4, ge=1, le=52, description="Weeks of history to analyze")
    sensitivity_max: int = Field(default=2, ge=0, le=3, description="Max sensitivity level to include")
    skip: Optional[List[str]] = Field(
        default=None,
        description="Analysis types to skip: summary, trends, contradictions, expiring",
    )


class InsightRunResponse(BaseModel):
    """Response confirming insight run was started or completed."""
    status: str = Field(..., description="running | completed | error")
    run_id: Optional[str] = None
    result: Optional[InsightResult] = None
    message: Optional[str] = None


class TrendsResponse(BaseModel):
    """Response containing trend data."""
    trends: List[TrendItem]
    count: int
    last_run: Optional[str] = None


class ExpiringResponse(BaseModel):
    """Response containing expiring memories."""
    expiring: List[ExpiringMemory]
    count: int
    days_ahead: int


class InsightHistoryResponse(BaseModel):
    """Response containing insight run history."""
    results: List[InsightResult]
    count: int


class MemoryExtendRequest(BaseModel):
    """Request to extend a memory's TTL."""
    days: int = Field(default=30, ge=1, le=365, description="Days to extend by")


# =============================================================================
# BACKGROUND TASK STATE
# =============================================================================

_running_task: Optional[str] = None  # run_id of currently running analysis
_running_lock = asyncio.Lock()  # serialise concurrent insight requests


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/run", response_model=InsightRunResponse)
async def run_insights(
    request: InsightRunRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
    memory=Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Trigger an on-demand insight analysis.

    Runs the full insight pipeline: life summary, trend detection,
    contradiction analysis, and expiry review. All processing happens
    locally using the configured Ollama model.

    This runs synchronously by default. For large memory stores,
    consider increasing the request timeout.
    """
    global _running_task

    async with _running_lock:
        if _running_task:
            return InsightRunResponse(
                status="running",
                run_id=_running_task,
                message="An insight analysis is already running. Please wait.",
            )

        from closedclaw.api.core.config import get_settings

        settings = get_settings()
        if not settings.local_engine.enabled:
            raise HTTPException(
                status_code=400,
                detail="Local engine is disabled. Insights require a local LLM.",
            )

        engine = get_insight_engine()
        engine._memory = memory  # Ensure we use the request-scoped memory

        import uuid

        run_id = str(uuid.uuid4())
        _running_task = run_id

    # Run heavy LLM analysis in a thread pool to avoid blocking the event loop
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: engine.run(
                user_id=user_id,
                weeks=request.weeks,
                sensitivity_max=request.sensitivity_max,
                skip=request.skip,
            ),
        )
        _running_task = None
        return InsightRunResponse(
            status="completed",
            run_id=result.run_id,
            result=result,
        )
    except Exception as e:
        _running_task = None
        logger.error(f"Insight run failed: {e}")
        return InsightRunResponse(
            status="error",
            run_id=run_id,
            message=str(e),
        )


@router.get("", response_model=InsightRunResponse)
async def get_latest_insights(
    token: str = Depends(get_auth_token),
):
    """
    Retrieve the latest insight analysis results.

    Returns the most recent completed run, or a message if no run has been
    performed yet.
    """
    engine = get_insight_engine()
    result = engine.last_result

    if result is None:
        return InsightRunResponse(
            status="no_data",
            message="No insight analysis has been run yet. POST /v1/insights/run to start one.",
        )

    return InsightRunResponse(
        status="completed",
        run_id=result.run_id,
        result=result,
    )


@router.get("/history", response_model=InsightHistoryResponse)
async def get_insight_history(
    limit: int = Query(default=10, ge=1, le=50),
    token: str = Depends(get_auth_token),
):
    """
    Get the history of insight analysis runs.

    Returns the most recent N runs in reverse chronological order.
    """
    engine = get_insight_engine()
    history = engine.result_history[-limit:]
    history.reverse()  # Most recent first

    return InsightHistoryResponse(
        results=history,
        count=len(history),
    )


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    user_id: str = Depends(get_user_id),
    memory=Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Get trend data (tag/topic frequency) from the latest insight run.

    If no run has been performed, runs a quick trend-only analysis.
    """
    engine = get_insight_engine()

    # Check for cached result
    if engine.last_result and engine.last_result.trends:
        return TrendsResponse(
            trends=engine.last_result.trends,
            count=len(engine.last_result.trends),
            last_run=engine.last_result.timestamp,
        )

    # Run trends-only analysis
    engine._memory = memory
    try:
        trends = engine.detect_trends(
            user_id=user_id,
            sensitivity_max=2,
        )
        return TrendsResponse(
            trends=trends,
            count=len(trends),
        )
    except Exception as e:
        logger.error(f"Trend detection failed: {e}")
        raise HTTPException(status_code=500, detail="Trend detection failed")


@router.get("/expiring", response_model=ExpiringResponse)
async def get_expiring_memories(
    days: int = Query(default=30, ge=1, le=365, description="Days to look ahead"),
    user_id: str = Depends(get_user_id),
    memory=Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Get memories approaching their TTL expiry.

    Returns memories expiring within the specified number of days,
    sorted by soonest expiry first.
    """
    engine = get_insight_engine()
    engine._memory = memory

    try:
        expiring = engine.review_expiring(
            user_id=user_id,
            days_ahead=days,
        )
        return ExpiringResponse(
            expiring=expiring,
            count=len(expiring),
            days_ahead=days,
        )
    except Exception as e:
        logger.error(f"Expiry review failed: {e}")
        raise HTTPException(status_code=500, detail="Expiry review failed")


@router.post("/expiring/{memory_id}/extend")
async def extend_memory_ttl(
    memory_id: str,
    request: MemoryExtendRequest,
    user_id: str = Depends(get_user_id),
    memory=Depends(get_memory),
    token: str = Depends(get_auth_token),
):
    """
    Extend a memory's TTL by the specified number of days.

    Useful when the expiry review surfaces a memory the user wants to keep.
    """
    from datetime import datetime, timezone, timedelta

    mem = memory.get(memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    new_expiry = datetime.now(timezone.utc) + timedelta(days=request.days)

    try:
        memory.update(
            memory_id,
            expires_at=new_expiry,
        )
        return {
            "status": "extended",
            "memory_id": memory_id,
            "new_expires_at": new_expiry.isoformat(),
            "days_added": request.days,
        }
    except Exception as e:
        logger.error(f"Failed to extend TTL for {memory_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to extend memory TTL")
