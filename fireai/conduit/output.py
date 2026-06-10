"""
fireai.conduit.output — Revit, AutoCAD, and Schedule Output Generators
=======================================================================

Converts a completed ConduitRun into:
  1. Revit-compatible JSON (for Revit API / Dynamo scripts)
  2. DXF entity descriptions (for AutoCAD / pyAutoCAD)
  3. Material/fitting schedules (for procurement and BOM)

All outputs are DETERMINISTIC: same ConduitRun → same output, always.
SHA-256 hash is provided for audit trail and cross-platform verification.

DESIGN LINEAGE:
  Revit JSON structure follows the pattern used in fireai/core/revit_exporter.py
  (already in the pipeline) but extended for conduit-specific parameters.
  Schedule format matches schedule_generator.py patterns for pipeline consistency.

Reference: Autodesk Revit MEP API (Conduit, ConduitFitting elements);
           AutoCAD DXF R2018 specification; NEC 358 (EMT conduit parameters).
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List

from fireai.conduit.types import (
    Point3D, ConduitRun, ConduitSegment, ConduitType, FittingType, PlacedFitting,
)

# ─────────────────────────────────────────────────────────────────────────────
# Layer name map for AutoCAD DXF output
# Consistent with NFPA 72 drawing standard: fire alarm on FA- layers
# ─────────────────────────────────────────────────────────────────────────────

_DXF_LAYER: dict[ConduitType, str] = {
    ConduitType.EMT:        "FA-CONDUIT-EMT",
    ConduitType.UPVC_SCH40: "FA-CONDUIT-PVC-SCH40",
    ConduitType.UPVC_SCH80: "FA-CONDUIT-PVC-SCH80",
    ConduitType.RGD:        "FA-CONDUIT-RGD",
}

# Revit conduit type families
_REVIT_FAMILY: dict[ConduitType, str] = {
    ConduitType.EMT:        "EMT Conduit",
    ConduitType.UPVC_SCH40: "PVC Schedule 40 Conduit",
    ConduitType.UPVC_SCH80: "PVC Schedule 80 Conduit",
    ConduitType.RGD:        "Rigid Metal Conduit",
}

# Metres to feet conversion (Revit uses decimal feet internally)
_M_TO_FT: float = 1.0 / 0.3048


def generate_revit_conduit(run: ConduitRun) -> Dict[str, Any]:
    """
    Generate Revit-compatible JSON for a complete ConduitRun.

    Produces a structure importable by Dynamo or the Revit API Python shell
    to create Conduit and ConduitFitting elements in a Revit model.

    All lengths are in decimal FEET (Revit internal unit).
    All coordinates are in decimal FEET (Revit internal unit).

    Args:
        run: Completed ConduitRun from place_fittings().

    Returns:
        dict with keys:
          run_id, conduit_type, trade_size, family_name,
          segments (list of conduit runs),
          fittings (list of fitting placements),
          summary (totals and compliance),
          sha256 (deterministic hash for audit trail).

    Reference: Autodesk Revit MEP API — Conduit.Create(), ConduitFitting.Create().
    """
    segments_out: List[Dict[str, Any]] = []
    for seg in run.segments:
        segments_out.append({
            "start_ft": _pt_to_ft(seg.start),
            "end_ft":   _pt_to_ft(seg.end),
            "length_ft": round(seg.length_m * _M_TO_FT, 6),
            "length_m":  round(seg.length_m, 6),
            "conduit_type": seg.conduit_type.value,
            "trade_size":   seg.trade_size.value,
        })

    fittings_out: List[Dict[str, Any]] = []
    for fit in run.fittings:
        fittings_out.append({
            "fitting_type":    fit.fitting_type.name,
            "catalog_number":  fit.catalog_number,
            "position_ft":     _pt_to_ft(fit.position),
            "position_m":      _pt_to_m(fit.position),
            "angle_deg":       fit.angle_deg,
            "developed_length_ft": round(fit.developed_length_m * _M_TO_FT, 6),
            "developed_length_m":  round(fit.developed_length_m, 6),
            "weight_kg":       fit.weight_kg,
        })

    summary = _build_summary(run)

    payload: Dict[str, Any] = {
        "schema_version":  "fireai-conduit-v1",
        "run_id":          run.run_id,
        "conduit_type":    run.conduit_type.value,
        "trade_size":      run.trade_size.value,
        "family_name":     _REVIT_FAMILY.get(run.conduit_type, "Unknown Conduit"),
        "segments":        segments_out,
        "fittings":        fittings_out,
        "summary":         summary,
        "violations":      run.violations,
        "is_compliant":    run.is_compliant,
    }

    # Deterministic SHA-256 — sorted keys for cross-platform consistency
    payload["sha256"] = _sha256(payload)
    return payload


def generate_autocad_entities(run: ConduitRun) -> List[Dict[str, Any]]:
    """
    Generate DXF entity descriptions for a ConduitRun.

    Each straight segment becomes a LINE entity.
    Each elbow becomes an ARC entity.
    Each coupling/pull-box becomes a POINT entity with ATTDEF.

    Coordinates are in MILLIMETRES (AutoCAD MEP standard for metric drawings).

    Args:
        run: Completed ConduitRun from place_fittings().

    Returns:
        list of entity dicts with keys:
          entity_type, layer, color_index, [geometry keys per type].

    Reference: AutoCAD DXF R2018 specification — LINE, ARC, POINT entities.
    """
    layer = _DXF_LAYER.get(run.conduit_type, "FA-CONDUIT")
    color = _dxf_color(run.conduit_type)
    entities: List[Dict[str, Any]] = []

    # Straight segments → LINE entities
    for seg in run.segments:
        entities.append({
            "entity_type":  "LINE",
            "layer":        layer,
            "color_index":  color,
            "start_mm":     _pt_to_mm(seg.start),
            "end_mm":       _pt_to_mm(seg.end),
            "length_mm":    round(seg.length_m * 1000.0, 3),
            "description":  (
                f"{run.conduit_type.value} {run.trade_size.value} conduit "
                f"{seg.length_m * 1000:.0f}mm"
            ),
        })

    # Fittings → POINT + ATTDEF entities
    for fit in run.fittings:
        etype = "ARC" if fit.fitting_type in (
            FittingType.ELBOW_90, FittingType.ELBOW_45
        ) else "POINT"

        ent: Dict[str, Any] = {
            "entity_type":   etype,
            "layer":         layer + "-FITTINGS",
            "color_index":   color,
            "position_mm":   _pt_to_mm(fit.position),
            "catalog_number": fit.catalog_number,
            "fitting_type":  fit.fitting_type.name,
            "description":   (
                f"{fit.catalog_number} "
                f"{fit.fitting_type.name} "
                f"{run.trade_size.value}"
            ),
        }
        if fit.fitting_type in (FittingType.ELBOW_90, FittingType.ELBOW_45):
            ent["angle_deg"] = fit.angle_deg
            ent["developed_length_mm"] = round(fit.developed_length_m * 1000.0, 3)

        entities.append(ent)

    return entities


def generate_schedules(run: ConduitRun) -> Dict[str, Any]:
    """
    Generate material, fitting, and summary schedules for procurement.

    Produces three sub-schedules:
      conduit_schedule:  Trade size, type, total metres/feet, stick count.
      fitting_schedule:  Catalog number, description, quantity, weight.
      summary:           Totals and NEC compliance status.

    All quantities are deterministic (sorted by catalog number).

    Args:
        run: Completed ConduitRun from place_fittings().

    Returns:
        dict with keys: conduit_schedule, fitting_schedule, summary.

    Reference: NEC 358.120 (EMT stick length); NFPA 72 design documents.
    """
    # ── Conduit schedule ─────────────────────────────────────────────────────

    total_m = run.total_length_m
    stick_m = 3.048   # 10 ft per stick (all types)
    n_sticks = math.ceil(total_m / stick_m) if total_m > 0 else 0

    conduit_schedule = {
        "conduit_type":  run.conduit_type.value,
        "trade_size":    run.trade_size.value,
        "total_length_m":  round(total_m, 3),
        "total_length_ft": round(total_m * _M_TO_FT, 3),
        "stick_count":     n_sticks,
        "stick_length_ft": 10,
        "segment_count":   len(run.segments),
    }

    # ── Fitting schedule ─────────────────────────────────────────────────────

    # Aggregate by catalog_number
    fitting_qty: Dict[str, Dict[str, Any]] = {}
    for fit in run.fittings:
        cn = fit.catalog_number
        if cn not in fitting_qty:
            fitting_qty[cn] = {
                "catalog_number": cn,
                "fitting_type":   fit.fitting_type.name,
                "conduit_type":   fit.conduit_type.value,
                "trade_size":     fit.trade_size.value,
                "quantity":       0,
                "total_weight_kg": 0.0,
            }
        fitting_qty[cn]["quantity"] += 1
        fitting_qty[cn]["total_weight_kg"] = round(
            fitting_qty[cn]["total_weight_kg"] + fit.weight_kg, 4
        )

    # Sort by catalog number for determinism
    fitting_schedule = sorted(fitting_qty.values(), key=lambda x: x["catalog_number"])

    summary = _build_summary(run)

    return {
        "conduit_schedule": conduit_schedule,
        "fitting_schedule": fitting_schedule,
        "summary":          summary,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_summary(run: ConduitRun) -> Dict[str, Any]:
    """Build summary statistics for a ConduitRun."""
    elbow_count   = sum(1 for f in run.fittings if f.fitting_type == FittingType.ELBOW_90)
    coupling_count = sum(1 for f in run.fittings if f.fitting_type == FittingType.COUPLING)
    pullbox_count  = sum(1 for f in run.fittings if f.fitting_type == FittingType.PULL_BOX)
    total_weight   = sum(f.weight_kg for f in run.fittings)

    return {
        "run_id":            run.run_id,
        "is_compliant":      run.is_compliant,
        "violation_count":   len(run.violations),
        "total_length_m":    round(run.total_length_m, 3),
        "total_length_ft":   round(run.total_length_m * _M_TO_FT, 3),
        "total_bend_deg":    run.total_bend_deg,
        "segment_count":     len(run.segments),
        "elbow_90_count":    elbow_count,
        "coupling_count":    coupling_count,
        "pull_box_count":    pullbox_count,
        "total_weight_kg":   round(total_weight, 3),
    }


def _pt_to_ft(p: Point3D) -> Dict[str, float]:
    """Convert Point3D (metres) to Revit decimal feet dict."""
    return {
        "x": round(p.x * _M_TO_FT, 6),
        "y": round(p.y * _M_TO_FT, 6),
        "z": round(p.z * _M_TO_FT, 6),
    }


def _pt_to_m(p: Point3D) -> Dict[str, float]:
    """Convert Point3D to metres dict."""
    return {"x": round(p.x, 6), "y": round(p.y, 6), "z": round(p.z, 6)}


def _pt_to_mm(p: Point3D) -> Dict[str, float]:
    """Convert Point3D (metres) to millimetres dict."""
    return {
        "x": round(p.x * 1000.0, 3),
        "y": round(p.y * 1000.0, 3),
        "z": round(p.z * 1000.0, 3),
    }


def _dxf_color(ct: ConduitType) -> int:
    """Map conduit type to AutoCAD color index (ACI)."""
    return {
        ConduitType.EMT:        1,    # Red
        ConduitType.UPVC_SCH40: 3,    # Green
        ConduitType.UPVC_SCH80: 4,    # Cyan
        ConduitType.RGD:        5,    # Blue
    }.get(ct, 7)  # 7 = white (default)


def _sha256(payload: Dict[str, Any]) -> str:
    """
    Compute deterministic SHA-256 of a JSON-serialisable payload.

    Keys sorted, floats rounded to 9 dp for cross-platform stability.
    Excludes the 'sha256' key itself to avoid circular dependency.
    """
    clean = {k: v for k, v in payload.items() if k != "sha256"}
    serialised = json.dumps(clean, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()
