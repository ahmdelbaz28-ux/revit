"""backend/routers/memory.py — REST API Router for FireAI Memory Service.

Provides HTTP endpoints for the Mem0-based memory layer:
  POST /api/memory/add          → Add a memory
  POST /api/memory/search       → Search memories
  GET  /api/memory/all          → Get all memories (with filters)
  DELETE /api/memory/{id}       → Delete a memory
  GET  /api/memory/{id}/history → Get memory history
  GET  /api/memory/status       → Get service status

LIFE-SAFETY DESIGN PRINCIPLE:
  Memory endpoints are READ-WRITE for context storage only.
  They MUST NEVER:
  - Replace or override NFPA 72 calculation endpoints
  - Influence deterministic engineering calculations
  - Bypass verification gates or safety checks

  Every response includes a "disclaimer" field reminding users that
  memory results are ADVISORY CONTEXT, not authoritative calculations.

Reference: agent.md Rules 1-21, Priority Hierarchy
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import require_permission
from backend.rbac import Permission
from backend.services.memory_service import (
    MemoryAddRequest,
    MemorySearchRequest,
    get_memory_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/memory",
    tags=["memory"],
    responses={
        404: {"description": "Memory not found"},
        500: {"description": "Internal server error"},
    },
)


# ── SAFETY DISCLAIMER ────────────────────────────────────────────────────────
# Included in every response to prevent misuse of memory as authoritative data.

MEMORY_DISCLAIMER = (
    "Memory results are ADVISORY CONTEXT only. They MUST NOT replace "
    "deterministic NFPA 72 calculations or engineering judgment. All "
    "fire alarm designs require Professional Engineer (PE) review per "
    "NFPA 72. Memory context should inform, never dictate, design decisions."
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", summary="Get memory service status", dependencies=[Depends(require_permission(Permission.HEALTH_READ))])
async def get_status():
    """Get the current status of the memory service.

    Returns initialization state, provider info, and any errors.
    This endpoint is useful for health checks and debugging.
    """
    service = get_memory_service()
    status = service.status
    return {
        "success": True,
        "status": status.model_dump(),
        "disclaimer": MEMORY_DISCLAIMER,
    }


@router.post("/add", summary="Add a memory", dependencies=[Depends(require_permission(Permission.USER_MANAGE))])
async def add_memory(request: MemoryAddRequest):
    """Add a memory to the FireAI memory store.

    The memory service extracts facts from the provided messages and
    stores them with the specified scoping (user, project, agent).

    SAFETY: Memory addition never blocks or influences calculations.

    Args:
        request: MemoryAddRequest with messages and scoping

    Returns:
        Dict with operation result

    """
    service = get_memory_service()
    result = service.add_memory(request)
    result["disclaimer"] = MEMORY_DISCLAIMER
    return result


@router.post("/search", summary="Search memories", dependencies=[Depends(require_permission(Permission.QOMN_READ))])
async def search_memories(request: MemorySearchRequest):
    """Search memories using hybrid search (semantic + BM25 + entity boosting).

    Results are ADVISORY CONTEXT — they must not replace deterministic
    NFPA 72 calculations or engineering judgment.

    Args:
        request: MemorySearchRequest with query and filters

    Returns:
        MemorySearchResponse with results and safety disclaimer

    """
    service = get_memory_service()
    response = service.search_memories(request)
    return response.model_dump()


@router.get("/all", summary="Get all memories", dependencies=[Depends(require_permission(Permission.QOMN_READ))])
async def get_all_memories(
    user_id: Optional[str] = Query(None, description="Filter by user/engineer"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    run_id: Optional[str] = Query(None, description="Filter by project/run"),
):
    """Get all memories for a given scope.

    Supports filtering by user, agent, or project.

    Args:
        user_id: Filter by user/engineer
        agent_id: Filter by agent
        run_id: Filter by project/run

    Returns:
        Dict with list of memories

    """
    service = get_memory_service()
    result = service.get_all_memories(
        user_id=user_id,
        agent_id=agent_id,
        run_id=run_id,
    )
    result["disclaimer"] = MEMORY_DISCLAIMER
    return result


@router.delete("/{memory_id}", summary="Delete a memory", dependencies=[Depends(require_permission(Permission.USER_MANAGE))])
async def delete_memory(memory_id: str):
    """Delete a specific memory by ID.

    Args:
        memory_id: The memory ID to delete

    Returns:
        Dict with operation result

    """
    service = get_memory_service()
    result = service.delete_memory(memory_id=memory_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Memory not found"))
    result["disclaimer"] = MEMORY_DISCLAIMER
    return result


@router.get("/{memory_id}/history", summary="Get memory history", dependencies=[Depends(require_permission(Permission.QOMN_READ))])
async def get_memory_history(memory_id: str):
    """Get the full history of a memory (all changes over time).

    Supports agent.md's traceability requirement (Priority 7).

    Args:
        memory_id: The memory ID to get history for

    Returns:
        Dict with memory history

    """
    service = get_memory_service()
    result = service.get_memory_history(memory_id=memory_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Memory not found"))
    result["disclaimer"] = MEMORY_DISCLAIMER
    return result
