"""
backend/routers/aps.py — Autodesk Platform Services API Endpoint Routing.
========================================================================

Exposes endpoints to:
1. Submit drawings/BIM files to Autodesk Cloud for design automation.
2. Poll design automation job (WorkItem) progress.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.services.aps_service import ApsService, get_aps_service

router = APIRouter(prefix="/api/v2/aps", tags=["Autodesk Platform Services"])


class ApsProcessRequest(BaseModel):
    bucket_key: str = Field(default="bazspark_bucket", description="Autodesk OSS bucket key")
    object_key: str = Field(..., description="File name/object key inside the bucket")
    activity_id: str = Field(..., description="Autodesk Design Automation Activity ID")
    params: Dict[str, Any] = Field(default_factory=dict, description="Command line parameter overrides")


@router.post("/process")
async def process_file_in_cloud(
    body: ApsProcessRequest,
    service = Depends(get_aps_service),
) -> Dict[str, Any]:
    """
    Submits a design automation task (WorkItem) to Autodesk Platform Services.
    """
    # 1. Get OAuth Access Token
    token_res = service.get_token()
    if not token_res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"APS Authentication failed: {token_res.get('error')}"
        )
    token = token_res["access_token"]

    # 2. Ensure the OSS storage bucket exists
    bucket_res = service.create_bucket(body.bucket_key, token)
    if not bucket_res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create bucket: {bucket_res.get('error')}"
        )

    # 3. Create and dispatch the cloud WorkItem
    input_urn = f"urn:adsk.objects:os.object:{body.bucket_key}/{body.object_key}"
    output_urn = f"urn:adsk.objects:os.object:{body.bucket_key}/output_{body.object_key}"

    work_res = service.execute_work_item(
        activity_id=body.activity_id,
        input_urn=input_urn,
        output_urn=output_urn,
        params=body.params,
        token=token
    )
    if not work_res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"WorkItem submission failed: {work_res.get('error')}"
        )

    return {
        "success": True,
        "work_item_id": work_res["work_item_id"],
        "input_urn": input_urn,
        "output_urn": output_urn,
        "simulation_mode": work_res.get("simulation_mode", False)
    }


@router.get("/status/{work_item_id}")
async def get_work_item_status(
    work_item_id: str,
    service = Depends(get_aps_service),
) -> Dict[str, Any]:
    """
    Retrieves the execution status and report URL for a dispatched WorkItem job.
    """
    token_res = service.get_token()
    if not token_res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="APS Authentication failed"
        )

    status_res = service.poll_work_item(work_item_id, token_res["access_token"])
    if not status_res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=status_res.get("error")
        )

    return status_res
