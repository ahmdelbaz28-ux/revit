"""
backend/routers/marine.py — Marine Fire-Safety REST API
=========================================================
REST endpoints for the marine fire-safety module.

All endpoints require ENGINEER+ permission (ELEMENT_CREATE) since they
produce engineering designs that affect ship safety systems. Read-only
endpoints (standards lookup) require VIEWER+ (ELEMENT_READ).

Endpoints:
    POST /marine/ship/validate        — Validate ship SOLAS compliance
    POST /marine/ship/design          — Full design pipeline (returns everything)
    POST /marine/zones/divide         — Divide ship into MVZs only
    POST /marine/detection/design     — Detection design for a zone
    POST /marine/extinguishing/design — Size extinguishing system
    POST /marine/divisions/generate   — Generate fire-division specs
    POST /marine/alarm-logic/generate — Generate PLC/DCS logic tree
    POST /marine/power/design         — Design electrical power system
    POST /marine/integrations/scada   — Generate SCADA config (MQTT/OPC-UA/Modbus)
    POST /marine/integrations/etap    — Generate ETAP CSV
    POST /marine/integrations/dxf     — Generate AutoCAD DXF
    POST /marine/integrations/revit   — Generate Revit families + placements
    GET  /marine/standards            — List supported standards & references
    GET  /marine/fire-classes         — List SOLAS fire division classes
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth import require_permission
from backend.limiter import limiter
from backend.rbac import Permission
from backend.services.marine_service import get_marine_service

from marine.core.types import (
    DetectorType, ExtinguishingSystem, FireClass, FireHazardClass,
    MarineZone, ShipProject, ShipType, SpaceCategory,
)


router = APIRouter(prefix="/marine", tags=["Marine"])


# ─── Pydantic Request Models ────────────────────────────────────────────────

class ShipProjectRequest(BaseModel):
    project_id: str = Field(..., description="Unique project identifier")
    ship_name: str = Field(..., description="Ship name")
    imo_number: Optional[str] = Field(None, description="7-digit IMO number")
    ship_type: ShipType = Field(ShipType.CARGO, description="SOLAS ship type")
    service: str = Field("bulk_carrier", description="Ship service category")
    length_overall_m: float = Field(..., gt=0, description="LOA in metres")
    gross_tonnage: float = Field(0.0, ge=0, description="Gross tonnage")
    passenger_capacity: int = Field(0, ge=0, description="Passenger capacity")
    flag_state: str = Field("", description="Flag state (ISO 3166)")
    classification_society: str = Field("LR", description="LR/DNV/BV/ABS")
    build_date: Optional[str] = None

    def to_domain(self) -> ShipProject:
        """Convert Pydantic model to domain dataclass."""
        from marine.core.types import ShipService
        try:
            service = ShipService(self.service)
        except ValueError:
            service = ShipService.BULK_CARRIER
        return ShipProject(
            project_id=self.project_id, ship_name=self.ship_name,
            imo_number=self.imo_number, ship_type=self.ship_type,
            service=service, length_overall_m=self.length_overall_m,
            gross_tonnage=self.gross_tonnage,
            passenger_capacity=self.passenger_capacity,
            flag_state=self.flag_state,
            classification_society=self.classification_society,
            build_date=self.build_date,
        )


class ZoneRequest(BaseModel):
    """Optional explicit zone definition (else auto-divide)."""
    zone_id: str
    name: str
    space_category: SpaceCategory
    deck: str = "main"
    frame_start: int = 0
    frame_end: int = 100
    area_m2: float = Field(..., gt=0)
    height_m: float = Field(2.5, gt=0)
    has_escape_route: bool = True


class DesignRequest(BaseModel):
    """Full design request: ship + optional explicit zones."""
    ship: ShipProjectRequest
    zones: Optional[List[ZoneRequest]] = None


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get(
    "/standards",
    dependencies=[Depends(require_permission(Permission.ELEMENT_READ))],
)
@limiter.limit("100/minute")
async def list_standards(request: Request) -> Dict[str, Any]:
    """List the marine standards supported by this module."""
    return {
        "standards": [
            {"code": "SOLAS II-2", "title": "Construction — Fire protection, detection, extinction",
             "issuer": "IMO", "edition": "2024 consolidated"},
            {"code": "IEC 60092-502", "title": "Electrical installations in ships — Tankers",
             "issuer": "IEC", "edition": "1999"},
            {"code": "IEC 60092-504", "title": "Ships carrying dangerous goods",
             "issuer": "IEC", "edition": "2016"},
            {"code": "ISO 15370", "title": "Thermal alarms for passenger ships",
             "issuer": "ISO", "edition": "2001"},
            {"code": "LR Rules Part 6", "title": "Fire Protection, Detection & Extinguishment",
             "issuer": "Lloyd's Register", "edition": "2024"},
            {"code": "NFPA 302", "title": "Fire Protection for Craft and Small Commercial Vessels",
             "issuer": "NFPA", "edition": "2020"},
            {"code": "IMO MSC.1/Circ.1316", "title": "CO2 total flooding guidelines",
             "issuer": "IMO", "edition": "2021 rev.1"},
            {"code": "IMO MSC.1/Circ.1165", "title": "Water mist fire-extinguishing systems",
             "issuer": "IMO", "edition": "2005"},
            {"code": "FSS Code Ch. 9", "title": "Fixed fire detection and fire alarm systems",
             "issuer": "IMO", "edition": "2023"},
            {"code": "FSS Code Ch. 14", "title": "Sprinkler systems",
             "issuer": "IMO", "edition": "2023"},
        ]
    }


@router.get(
    "/fire-classes",
    dependencies=[Depends(require_permission(Permission.ELEMENT_READ))],
)
@limiter.limit("100/minute")
async def list_fire_classes(request: Request) -> Dict[str, Any]:
    """List SOLAS fire division classes and their insulation minutes."""
    return {
        "fire_classes": [
            {"class": c.value, "insulation_minutes": c.insulation_minutes}
            for c in FireClass
        ]
    }


@router.post(
    "/ship/validate",
    dependencies=[Depends(require_permission(Permission.ELEMENT_READ))],
)
@limiter.limit("30/minute")
async def validate_ship(request: Request, body: DesignRequest) -> Dict[str, Any]:
    """Validate a ship's SOLAS compliance (zones, divisions, escape routes)."""
    ship = body.ship.to_domain()
    zones = [MarineZone(**z.dict()) for z in body.zones] if body.zones else None
    if zones is None:
        from marine.engine.zone_mapper import divide_into_main_vertical_zones
        zones = divide_into_main_vertical_zones(ship.length_overall_m, ship)

    from marine.solas.chapter_ii_2 import (
        validate_escape_routes, validate_main_vertical_zones,
    )
    mvz = validate_main_vertical_zones(zones, ship)
    esc = validate_escape_routes(zones)

    return {
        "compliant": mvz.compliant and esc.compliant,
        "mvz_validation": mvz.__dict__,
        "escape_validation": esc.__dict__,
    }


@router.post(
    "/ship/design",
    dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))],
)
@limiter.limit("10/minute")
async def design_full(request: Request, body: DesignRequest) -> Dict[str, Any]:
    """Run the full marine fire-safety design pipeline.

    Returns: zones, detectors, divisions, extinguishing systems, alarm
    logic tree, power spec, SCADA/ETAP/Revit/DXF integrations, and
    compliance validation results.
    """
    ship = body.ship.to_domain()
    zones = [MarineZone(**z.dict()) for z in body.zones] if body.zones else None
    service = get_marine_service()
    try:
        return service.design_full(ship, zones)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Design failed: {e}") from e


@router.post(
    "/zones/divide",
    dependencies=[Depends(require_permission(Permission.ELEMENT_READ))],
)
@limiter.limit("30/minute")
async def divide_zones(request: Request, ship: ShipProjectRequest) -> Dict[str, Any]:
    """Divide a ship into SOLAS main vertical zones."""
    from marine.engine.zone_mapper import divide_into_main_vertical_zones
    domain = ship.to_domain()
    zones = divide_into_main_vertical_zones(domain.length_overall_m, domain)
    return {
        "zone_count": len(zones),
        "zones": [z.__dict__ for z in zones],
    }


@router.post(
    "/extinguishing/design",
    dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))],
)
@limiter.limit("30/minute")
async def design_extinguishing(
    request: Request,
    ship: ShipProjectRequest,
    zone: ZoneRequest,
) -> Dict[str, Any]:
    """Size an extinguishing system for a single zone."""
    from marine.engine.extinguishment import size_system
    design = size_system(zone_to_domain(zone), ship.to_domain())
    return design.__dict__


@router.post(
    "/alarm-logic/generate",
    dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))],
)
@limiter.limit("30/minute")
async def generate_alarm_logic(
    request: Request,
    ship: ShipProjectRequest,
    zones: List[ZoneRequest],
) -> Dict[str, Any]:
    """Generate the PLC/DCS alarm-logic tree for a set of zones."""
    from marine.engine.alarm_logic import export_to_plc_script, generate_logic_tree
    from marine.iec60092.part_502 import place_detectors_grid, select_detector_type
    from marine.core.types import DetectorType
    domain_ship = ship.to_domain()
    all_nodes = []
    for zr in zones:
        z = zone_to_domain(zr)
        sel = select_detector_type(z, domain_ship)
        for dt_str in sel.details.get("selected_types", []):
            dt = DetectorType(dt_str)
            dps = place_detectors_grid(z, dt)
            all_nodes.extend(generate_logic_tree(z, dps))
    return {
        "node_count": len(all_nodes),
        "nodes": [n.__dict__ for n in all_nodes],
        "plc_script_st": export_to_plc_script(all_nodes),
    }


@router.post(
    "/integrations/scada",
    dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))],
)
@limiter.limit("30/minute")
async def generate_scada(
    request: Request,
    imo: str,
    zone_ids: List[str],
) -> Dict[str, Any]:
    """Generate SCADA integration (MQTT topics + PyScada YAML)."""
    from marine.integration.scada_bridge import (
        build_mqtt_topics, build_pyscada_yaml,
    )
    tags = build_mqtt_topics(imo, zone_ids)
    return {
        "tag_count": len(tags),
        "tags": [t.__dict__ for t in tags],
        "pyscada_yaml": build_pyscada_yaml(tags),
    }


# ─── Helpers ────────────────────────────────────────────────────────────────

def zone_to_domain(zr: ZoneRequest) -> MarineZone:
    """Convert Pydantic ZoneRequest to MarineZone dataclass."""
    return MarineZone(
        zone_id=zr.zone_id, name=zr.name, space_category=zr.space_category,
        deck=zr.deck, frame_start=zr.frame_start, frame_end=zr.frame_end,
        area_m2=zr.area_m2, height_m=zr.height_m,
        has_escape_route=zr.has_escape_route,
    )


__all__ = ["router"]
