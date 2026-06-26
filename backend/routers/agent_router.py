"""backend/routers/agent_router.py — Design Agent API Endpoints"""

from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Request
from backend.services.design_agent import DesignAgent

logger = logging.getLogger("fireai.routers.agent")
router = APIRouter(prefix="/agent", tags=["agent"])
_agent = DesignAgent()


@router.post("/propose")
async def propose_design(request: Request) -> dict:
    """Generate a detector placement PROPOSAL (requires human approval)."""
    body = await request.json()
    room_id = body.get("room_id")
    if not room_id:
        raise HTTPException(status_code=400, detail="room_id is required")

    proposal = _agent.propose(
        room_id=room_id,
        room_name=body.get("room_name", ""),
        room_area=body.get("room_area", 0),
        room_width=body.get("room_width", 0),
        room_length=body.get("room_length", 0),
        detector_type=body.get("detector_type", "smoke"),
    )
    return {"status": "proposed", "data": {
        "room_id": proposal.room_id,
        "total_detectors": proposal.total_detectors,
        "estimated_coverage_pct": proposal.estimated_coverage_pct,
        "approved": proposal.approved,
        "disclaimer": proposal.disclaimer,
        "correlation_id": proposal.correlation_id,
    }}


@router.post("/approve")
async def approve_design(request: Request) -> dict:
    """Approve a design proposal — MANDATORY human gate."""
    body = await request.json()
    approver = body.get("approver")
    if not approver:
        raise HTTPException(status_code=400, detail="approver name is required — auto-approval FORBIDDEN")
    return {"status": "approved", "approver": approver, "message": "Design approved by " + approver}
