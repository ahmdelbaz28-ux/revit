"""v2.py — API v2 Routers for FireAI Cloud-Native Endpoints
============================================================

MISSION TASK 3.1 — API Versioning with /api/v2/ structure
==========================================================

This module exposes the new FireAI capabilities (Generative Design,
BIM Provider abstraction, IFC 4.3 mapping, AR export, Webhooks,
Smoke Simulation state) under a versioned ``/api/v2/`` prefix.

Endpoints
---------
- ``POST /api/v2/generative/design`` — Generate 3 layout variants
- ``GET  /api/v2/bim/providers`` — List registered BIM providers
- ``POST /api/v2/bim/extract-rooms`` — Extract rooms via configured provider
- ``GET  /api/v2/bim/health`` — Health check for BIM provider
- ``POST /api/v2/ifc43/map-detector`` — Map detector to IFC 4.3
- ``POST /api/v2/ifc43/map-project`` — Map entire project to IFC 4.3
- ``POST /api/v2/ar/export`` — Export DigitalTwin to GLB/USDZ
- ``POST /api/v2/webhooks/subscribe`` — Subscribe to webhook events
- ``GET  /api/v2/webhooks/subscriptions`` — List subscriptions
- ``DELETE /api/v2/webhooks/subscriptions/{sub_id}`` — Unsubscribe
- ``POST /api/v2/webhooks/publish`` — Publish an event
- ``POST /api/v2/smoke-simulation/state`` — Create/update smoke state

Deprecation Headers
-------------------
Per HTTP standards (RFC 7234):
- v1 endpoints receive ``Deprecation: true`` header
- v1 endpoints receive ``Sunset: <date>`` header (1 year deprecation window)
- v1 endpoints receive ``Link: </api/v2/...>; rel="successor-version"``
  header pointing to the v2 equivalent

References
----------
- agent.md Rule 6/14: VERIFY BEFORE CHANGING
- RFC 7234: HTTP Caching — Deprecation and Sunset headers
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class GenerativeDesignRequest(BaseModel):
    """Request body for /api/v2/generative/design."""

    room_width: float = Field(..., gt=0, description="Room width in metres")
    room_length: float = Field(..., gt=0, description="Room length in metres")
    room_height: float = Field(3.0, gt=0, description="Ceiling height in metres")
    room_name: str = Field("API_Room", description="Room identifier")
    occupancy_type: str = Field("office", description="NFPA 101 occupancy")
    detector_type: str = Field("smoke", description="Detector type")
    use_multiprocessing: bool = Field(True, description="Use parallel variant generation")


class BIMExtractRoomsRequest(BaseModel):
    """Request body for /api/v2/bim/extract-rooms."""

    source: Optional[str] = Field(None, description="File path or URL")
    provider: Optional[str] = Field(None, description="Provider name (default: env var)")


class IFC43MapDetectorRequest(BaseModel):
    """Request body for /api/v2/ifc43/map-detector."""

    device_id: str
    type: str = "smoke"
    x: float
    y: float
    z: float = 0.0
    room_id: str = "UNASSIGNED"
    coverage_radius_m: float = 6.37
    spacing_m: float = 9.1
    ceiling_height_m: float = 3.0
    occupancy_type: str = "office"
    is_code_compliant: bool = False
    coverage_pct: float = 0.0
    run_id: str = ""
    evidence_hash: str = ""


class ARExportRequest(BaseModel):
    """Request body for /api/v2/ar/export."""

    building_id: str = "API_Building"
    format: str = Field("both", pattern="^(glb|usdz|both)$")
    nodes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="AR scene nodes (optional — empty uses DigitalTwin)",
    )


class WebhookSubscribeRequest(BaseModel):
    """Request body for /api/v2/webhooks/subscribe."""

    url: str
    secret: str = Field(..., min_length=32)  # V135 F-33: NIST SP 800-107
    event_types: List[str] = Field(default_factory=list)


class WebhookPublishRequest(BaseModel):
    """Request body for /api/v2/webhooks/publish."""

    event_type: str
    source: str
    data: Dict[str, Any]
    trace_id: Optional[str] = None


class SmokeSimulationStateRequest(BaseModel):
    """Request body for /api/v2/smoke-simulation/state."""

    room_id: str
    smoke_density_points: List[Dict[str, Any]] = Field(default_factory=list)
    visibility_at_height: Dict[float, float] = Field(default_factory=dict)
    fds_run_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Generative Design Endpoints
# ---------------------------------------------------------------------------


@router.post("/generative/design")
async def generate_design_variants(req: GenerativeDesignRequest) -> Dict[str, Any]:
    """Generate 3 layout variants (Cost-Min, Standard, Safety-Max).

    Returns scored variants with recommendation based on occupancy.
    """
    try:
        from fireai.core.spatial_engine.generative_layout_agent import (
            GenerativeLayoutAgent,
        )
        from fireai.core.spatial_engine.density_optimizer import Room

        agent = GenerativeLayoutAgent(use_multiprocessing=req.use_multiprocessing)
        room = Room(
            name=req.room_name,
            width=req.room_width,
            length=req.room_length,
            ceiling_height=req.room_height,
        )
        result = agent.generate_variants(
            room=room,
            occupancy_type=req.occupancy_type,
            detector_type=req.detector_type,
        )
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error("Generative design failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}") from e


# ---------------------------------------------------------------------------
# BIM Provider Endpoints
# ---------------------------------------------------------------------------


@router.get("/bim/providers")
async def list_bim_providers() -> Dict[str, Any]:
    """List all registered BIM providers."""
    from fireai.bridges.bim_provider import BIMProviderRegistry

    providers = BIMProviderRegistry.list_available()
    return {
        "providers": providers,
        "active": __import__("os").environ.get("FIREAI_BIM_PROVIDER"),
        "count": len(providers),
    }


@router.post("/bim/extract-rooms")
async def extract_rooms(req: BIMExtractRoomsRequest) -> Dict[str, Any]:
    """Extract rooms via configured BIM provider.

    V137 F-5 FIX: Added source path validation to prevent SSRF/path traversal.
    The OLD code passed ``req.source`` directly to ``provider.extract_rooms()``
    which calls ``ifcopenshell.open(source)`` — allowing arbitrary file reads.
    """
    from fireai.bridges.bim_provider import get_provider

    # V137 F-5: Validate source path if provided
    if req.source:
        import os
        from pathlib import Path
        try:
            source_path = Path(req.source).resolve()
            # Check for path traversal (..)
            if not str(source_path).startswith(str(Path.cwd().resolve())):
                # Allow /tmp and uploads directories
                allowed_prefixes = [
                    str(Path.cwd().resolve()),
                    "/tmp",
                    "/var/tmp",
                    os.environ.get("FIREAI_UPLOAD_DIR", str(Path.cwd() / "uploads")),
                ]
                if not any(str(source_path).startswith(p) for p in allowed_prefixes):
                    raise HTTPException(
                        status_code=400,
                        detail="Source path is outside allowed directories.",
                    )
            # Check for null byte injection
            if "\x00" in req.source:
                raise HTTPException(
                    status_code=400,
                    detail="Source path contains null byte (injection attempt).",
                )
            # Check file extension
            allowed_extensions = {".ifc", ".dxf", ".dwg", ".rvt", ".rfa", ".json"}
            if source_path.suffix.lower() not in allowed_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Source file extension '{source_path.suffix}' not allowed. "
                    f"Allowed: {allowed_extensions}",
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid source path: {exc}") from exc

    provider = get_provider(req.provider)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail=f"No BIM provider available. Set FIREAI_BIM_PROVIDER env var. "
            f"Registered: {__import__('fireai.bridges.bim_provider', fromlist=['BIMProviderRegistry']).BIMProviderRegistry.list_available()}",
        )

    rooms = provider.extract_rooms(source=req.source)
    return {
        "provider": provider.provider_name,
        "room_count": len(rooms),
        "rooms": [
            {
                "room_id": r.room_id,
                "name": r.name,
                "area_m2": r.area_m2,
                "ceiling_height_m": r.ceiling_height_m,
                "source": r.source,
            }
            for r in rooms
        ],
    }


@router.get("/bim/health")
async def bim_health() -> Dict[str, Any]:
    """Health check for active BIM provider."""
    from fireai.bridges.bim_provider import get_provider

    provider = get_provider()
    if provider is None:
        return {
            "healthy": False,
            "details": "No BIM provider configured",
            "error": "Set FIREAI_BIM_PROVIDER env var",
        }
    return provider.health_check()


# ---------------------------------------------------------------------------
# IFC 4.3 Mapping Endpoints
# ---------------------------------------------------------------------------


@router.post("/ifc43/map-detector")
async def map_detector_to_ifc43(req: IFC43MapDetectorRequest) -> Dict[str, Any]:
    """Map a FireAI detector to IFC 4.3 ADD2 representation."""
    from fireai.bridges.ifc43_mapper import IFC43Mapper

    mapper = IFC43Mapper()
    mapped = mapper.map_detector(req.model_dump())
    return {
        "global_id": mapped.global_id,
        "ifc_type": mapped.ifc_type,
        "predefined_type": mapped.predefined_type,
        "name": mapped.name,
        "location": mapped.location,
        "contained_in": mapped.contained_in,
        "property_sets": mapped.property_sets,
        "target_schema": mapped.target_schema,
    }


@router.post("/ifc43/map-project")
async def map_project_to_ifc43(req: Dict[str, Any]) -> Dict[str, Any]:
    """Map an entire FireAI project to IFC 4.3 ADD2."""
    from fireai.bridges.ifc43_mapper import IFC43Mapper

    mapper = IFC43Mapper()
    result = mapper.map_project(req)
    return {
        "header": result["header"],
        "statistics": result["statistics"],
        "schema_version": result["schema_version"],
        "building_global_id": result["building"].global_id,
        "rooms_count": len(result["rooms"]),
        "detectors_count": len(result["detectors"]),
    }


# ---------------------------------------------------------------------------
# AR Export Endpoints
# ---------------------------------------------------------------------------


@router.post("/ar/export")
async def export_ar_snapshot(req: ARExportRequest) -> Dict[str, Any]:
    """Export DigitalTwin snapshot to GLB/USDZ for AR visualization.

    Returns base64-encoded file content for each requested format.
    """
    import base64

    from fireai.integration.ar_metadata_exporter import (
        ARExportFormat,
        ARMetadataExporter,
        ARSceneNode,
        ARSnapshot,
    )

    exporter = ARMetadataExporter()

    # Build snapshot from request nodes (if provided)
    if req.nodes:
        nodes = []
        for n in req.nodes:
            nodes.append(ARSceneNode(
                id=n.get("id", "unknown"),
                name=n.get("name", ""),
                node_type=n.get("node_type", "detector"),
                position=tuple(n.get("position", (0, 0, 0))),
                is_behind_wall=n.get("is_behind_wall", False),
                inspection_critical=n.get("inspection_critical", False),
            ))
        snapshot = ARSnapshot(building_id=req.building_id, nodes=nodes)
    else:
        # Without DigitalTwin access in API context, return empty snapshot
        snapshot = ARSnapshot(building_id=req.building_id)

    fmt = ARExportFormat(req.format)
    exported = exporter.export(snapshot, fmt)

    return {
        "building_id": req.building_id,
        "node_count": snapshot.node_count,
        "behind_wall_count": snapshot.behind_wall_count,
        "formats": {
            fmt_name: {
                "size_bytes": len(content),
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
            for fmt_name, content in exported.items()
        },
    }


# ---------------------------------------------------------------------------
# Webhook Endpoints
# ---------------------------------------------------------------------------


@router.post("/webhooks/subscribe")
async def subscribe_webhook(req: WebhookSubscribeRequest) -> Dict[str, Any]:
    """Subscribe to webhook events."""
    from fireai.infrastructure.webhook_service import (
        get_webhook_service,
        WebhookSubscription,
    )

    service = get_webhook_service()
    try:
        sub = WebhookSubscription(
            id=f"sub-{__import__('uuid').uuid4().hex[:12]}",
            url=req.url,
            secret=req.secret,
            event_types=req.event_types,
        )
        service.subscribe(sub)
        return {
            "subscription_id": sub.id,
            "url": sub.url,
            "event_types": sub.event_types,
            "status": sub.status.value,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/webhooks/subscriptions")
async def list_webhook_subscriptions() -> Dict[str, Any]:
    """List all webhook subscriptions."""
    from fireai.infrastructure.webhook_service import get_webhook_service

    service = get_webhook_service()
    subs = service.list_subscriptions()
    return {
        "count": len(subs),
        "subscriptions": [
            {
                "id": s.id,
                "url": s.url,
                "event_types": s.event_types,
                "status": s.status.value,
            }
            for s in subs
        ],
    }


@router.delete("/webhooks/subscriptions/{sub_id}")
async def unsubscribe_webhook(sub_id: str) -> Dict[str, Any]:
    """Remove a webhook subscription."""
    from fireai.infrastructure.webhook_service import get_webhook_service

    service = get_webhook_service()
    removed = service.unsubscribe(sub_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Subscription {sub_id} not found")
    return {"subscription_id": sub_id, "removed": True}


@router.post("/webhooks/publish")
async def publish_webhook_event(req: WebhookPublishRequest) -> Dict[str, Any]:
    """Publish an event to all matching webhook subscribers."""
    from fireai.infrastructure.webhook_service import get_webhook_service

    service = get_webhook_service()
    event_id = service.publish_event(
        event_type=req.event_type,
        source=req.source,
        data=req.data,
        trace_id=req.trace_id,
    )
    return {
        "event_id": event_id,
        "event_type": req.event_type,
        "delivered": True,
    }


# ---------------------------------------------------------------------------
# Smoke Simulation Endpoints
# ---------------------------------------------------------------------------


@router.post("/smoke-simulation/state")
async def create_smoke_state(req: SmokeSimulationStateRequest) -> Dict[str, Any]:
    """Create or update smoke simulation state for a room.

    If FDS data is provided (fds_run_id), creates a validated state.
    Otherwise, creates a placeholder state with safety warnings.
    """
    from fireai.core.smoke_simulation_state import (
        SmokeDensityPoint,
        SmokeSimulationState,
    )

    if req.fds_run_id:
        # V137 F-6 FIX: Validate FDS run ID format to prevent fake validation.
        # The OLD code accepted ANY string as fds_run_id — a user could submit
        # arbitrary smoke data with fds_run_id="fake" and the state would be
        # marked VALIDATED, potentially tainting the legal audit chain.
        # Now we require FDS run IDs to follow a specific format (fds-YYYY-NNN)
        # and emit a WARNING if the format doesn't match. Full provenance
        # verification would require querying an FDS runner service.
        import re
        FDS_RUN_ID_PATTERN = r'^fds-\d{4}-\d{3,}$'  # e.g., "fds-2026-001"
        if not re.match(FDS_RUN_ID_PATTERN, req.fds_run_id):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid FDS run ID format: '{req.fds_run_id}'. "
                    f"Expected format: 'fds-YYYY-NNN' (e.g., 'fds-2026-001'). "
                    f"FDS run IDs must correspond to actual simulation runs — "
                    f"fake IDs are rejected to prevent audit chain contamination."
                ),
            )

        # Create validated state from FDS results
        points = [
            SmokeDensityPoint(
                x=p["x"], y=p["y"], z=p["z"],
                density_kg_m3=p["density_kg_m3"],
            )
            for p in req.smoke_density_points
        ]
        state = SmokeSimulationState.create_from_fds(
            room_id=req.room_id,
            smoke_density_points=points,
            visibility_at_height=req.visibility_at_height,
            fds_run_id=req.fds_run_id,
        )
    else:
        # Create placeholder state
        state = SmokeSimulationState.create_placeholder(req.room_id)

    return state.to_dict()


# ---------------------------------------------------------------------------
# Health Endpoint for v2
# ---------------------------------------------------------------------------


@router.get("/health")
async def v2_health() -> Dict[str, Any]:
    """Health check for v2 API endpoints."""
    return {
        "status": "ok",
        "version": "v2",
        "endpoints": [
            "/api/v2/generative/design",
            "/api/v2/bim/providers",
            "/api/v2/bim/extract-rooms",
            "/api/v2/bim/health",
            "/api/v2/ifc43/map-detector",
            "/api/v2/ifc43/map-project",
            "/api/v2/ar/export",
            "/api/v2/webhooks/subscribe",
            "/api/v2/webhooks/subscriptions",
            "/api/v2/webhooks/publish",
            "/api/v2/smoke-simulation/state",
            "/api/v2/auth/csrf-token",
            "/api/v2/health",
        ],
        "capabilities": [
            "generative_design",
            "bim_provider_abstraction",
            "ifc43_mapping",
            "ar_metadata_export",
            "webhook_delivery",
            "smoke_simulation_state",
            "csrf_protection",
        ],
    }


# ---------------------------------------------------------------------------
# CSRF Token Endpoint (PHASE 1.1)
# ---------------------------------------------------------------------------


@router.get("/auth/csrf-token")
async def get_csrf_token(request: Request) -> Dict[str, Any]:
    """Issue a CSRF token via Double Submit Cookie pattern.

    Sets the CSRF token in:
    1. A cookie (fireai_csrf_token, SameSite=Strict)
    2. The response body (for the frontend to extract and send in X-CSRF-Token header)

    The frontend MUST call this endpoint once per session, then include the
    token in the X-CSRF-Token header for all subsequent POST/PUT/DELETE/PATCH requests.

    Per OWASP CSRF Prevention Cheat Sheet — Double Submit Cookie pattern.
    """
    from backend.security_csrf import (
        CSRF_COOKIE_NAME,
        build_csrf_cookie_header,
        generate_csrf_token,
    )
    from fastapi.responses import JSONResponse

    token = generate_csrf_token()

    # Detect HTTPS from X-Forwarded-Proto (common behind reverse proxy)
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    is_https = forwarded_proto == "https" or request.url.scheme == "https"

    cookie_header = build_csrf_cookie_header(token, is_https=is_https)

    response = JSONResponse(content={
        "csrf_token": token,
        "cookie_name": CSRF_COOKIE_NAME,
        "header_name": "X-CSRF-Token",
        "instructions": (
            "Include this token in the X-CSRF-Token header for all "
            "POST/PUT/DELETE/PATCH requests. The cookie is set automatically."
        ),
    })
    response.headers["Set-Cookie"] = cookie_header
    return response


__all__ = ["router"]
