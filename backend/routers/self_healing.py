"""
backend/routers/self_healing.py — Self-Healing Engine monitoring endpoints.

V214: Exposes the self-healing engine's internal state:
  GET /api/v1/self-healing/health   — Circuit breaker + LRU cache + audit stats
  GET /api/v1/self-healing/audit    — Recent audit log entries
  POST /api/v1/self-healing/reset   — Reset circuit breaker (admin only)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import require_permission
from backend.rbac import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/self-healing", tags=["self-healing"])


@router.get("/health", dependencies=[Depends(require_permission(Permission.MONITOR_READ))])
async def self_healing_health():
    """
    Get self-healing engine health status.

    Returns circuit breaker state, LRU cache stats, audit logger stats,
    and LLM circuit breaker stats.
    """
    try:
        from fireai.core.qomn_self_healing_engine import (
            global_audit_logger,
            global_circuit_breaker,
            global_llm_breaker,
            global_lru_cache,
        )
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Self-healing engine not available: {e}",
        )

    return {
        "success": True,
        "circuit_breaker": global_circuit_breaker.health(),
        "lru_cache": global_lru_cache.stats(),
        "audit_logger": global_audit_logger.stats(),
        "llm_breaker": global_llm_breaker.stats(),
    }


@router.get("/audit", dependencies=[Depends(require_permission(Permission.MONITOR_READ))])
async def self_healing_audit(limit: int = 20):
    """
    Get recent self-healing audit log entries.

    Args:
        limit: Maximum number of entries to return (default 20, max 100).
    """
    try:
        from fireai.core.qomn_self_healing_engine import global_audit_logger
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Self-healing engine not available: {e}",
        )

    limit = min(limit, 100)
    stats = global_audit_logger.stats()

    # Verify chain integrity
    try:
        chain_result = global_audit_logger.verify_chain()
    except Exception as e:
        chain_result = {"valid": False, "error": str(e)}

    return {
        "success": True,
        "stats": stats,
        "chain_integrity": chain_result,
        "limit": limit,
    }


@router.post("/reset", dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))])
async def self_healing_reset():
    """
    Reset the circuit breaker (admin only).

    Use this after investigating and fixing the root cause of repeated
    healing events. The circuit breaker will return to CLOSED state
    and allow normal operation.
    """
    try:
        from fireai.core.qomn_self_healing_engine import global_circuit_breaker
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Self-healing engine not available: {e}",
        )

    global_circuit_breaker.reset()
    return {
        "success": True,
        "message": "Circuit breaker reset to CLOSED state",
        "circuit_breaker": global_circuit_breaker.health(),
    }
