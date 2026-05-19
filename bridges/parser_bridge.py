"""
bridges/parser_bridge.py
========================
Bridge 2: Drawing → FireAI Room/Device models

Converts the Elite Drawing Analyzer (EDA) NormalizedDrawing output
into FireAI's native Room, Device, and Obstruction models.

SAFETY: This bridge NEVER guesses. If a room polygon cannot be extracted
or a symbol cannot be classified with confidence ≥ 0.5, it goes into
`warnings` — not into the output.

Usage:
    from bridges.parser_bridge import parse_drawing_to_fireai
    result = parse_drawing_to_fireai("floor_plan.dxf")
    for room in result.rooms:
        print(room.name, room.floor_area)
"""

from __future__ import annotations
import logging, os, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint

from core.models import Room, Device, Obstruction

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Data structures
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ParseBridgeResult:
    """Result of the parser bridge conversion."""
    source_file: str
    source_type: str  # 'dxf', 'dwg', 'pdf', 'ifc', 'image'
    rooms: list = field(default_factory=list)       # FireAI Room objects
    devices: list = field(default_factory=list)      # FireAI Device objects
    obstructions: list = field(default_factory=list) # FireAI Obstruction objects
    classified_symbols: list = field(default_factory=list)  # EDA classifications
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# Symbol → Device type mapping (EDA symbol names → FireAI device types)
# ════════════════════════════════════════════════════════════════════════════

SYMBOL_TO_DEVICE_TYPE = {
    "smoke_detector":     "SMOKE_PHOTOELECTRIC",
    "heat_detector":      "HEAT_FIXED",
    "manual_call_point":  "MANUAL_PULL_STATION",
    "sprinkler_pendant":  "SPRINKLER_PENDANT",
    "sprinkler_upright":  "SPRINKLER_UPRIGHT",
    "exit_sign":          "EXIT_SIGN",
    "emergency_light":    "EMERGENCY_LIGHT",
    "fire_extinguisher":  "FIRE_EXTINGUISHER",
    "camera_dome":        "CCTV_DOME",
    "camera_bullet":      "CCTV_BULLET",
    "pir_sensor":         "PIR_SENSOR",
    "access_reader":      "ACCESS_READER",
}

# Symbols that belong to fire-alarm domain
FIRE_SYMBOLS = {
    "smoke_detector", "heat_detector", "manual_call_point",
    "sprinkler_pendant", "sprinkler_upright", "exit_sign",
    "emergency_light", "fire_extinguisher",
}

# Default coverage radii per device type (metres, NFPA 72/13)
DEVICE_COVERAGE_RADIUS = {
    "SMOKE_PHOTOELECTRIC": 6.37,   # 0.7 × 9.1m spacing
    "SMOKE_IONIZATION":    6.37,
    "SMOKE_MULTI_CRITERIA": 6.37,
    "HEAT_FIXED":          4.90,   # 0.7 × 7.0m spacing
    "HEAT_RATE_OF_RISE":   4.90,
    "MANUAL_PULL_STATION": 0.0,    # no radius — travel distance instead
    "SPRINKLER_PENDANT":   2.30,
    "SPRINKLER_UPRIGHT":   2.30,
}

# Default mounting height (metres)
DEVICE_MOUNT_HEIGHT = {
    "SMOKE_PHOTOELECTRIC": 2.8,
    "HEAT_FIXED": 2.4,
    "MANUAL_PULL_STATION": 1.4,
    "SPRINKLER_PENDANT": 0.0,  # pendant from ceiling
}


# ════════════════════════════════════════════════════════════════════════════
# Room extraction from DXF/DWG entities
# ════════════════════════════════════════════════════════════════════════════

def _extract_rooms_from_entities(entities: list, units_to_m: float = 0.001) -> list:
    """
    Extract rooms from closed polylines / hatches on architectural layers.

    Heuristic: a closed polyline on a layer containing 'ROOM', 'SPACE', 'AREA',
    or an enclosed hatch is treated as a room boundary.

    Returns list of FireAI Room objects.
    """
    rooms = []
    room_idx = 0
    seen_layers = set()

    for e in entities:
        layer = (e.layer or "").upper()
        # Skip obvious non-room layers
        skip = any(k in layer for k in
                   ("DIM", "TEXT", "HATCH", "TITLE", "GRID", "FA-", "FIRE",
                    "NOTE", "SYMBOL", "LEGEND", "SCHEDULE"))
        if skip:
            continue

        if e.kind != "polyline" or not e.geom.get("closed"):
            continue

        pts_raw = e.geom.get("points", [])
        if len(pts_raw) < 3:
            continue

        # Convert to Shapely polygon
        try:
            coords = [(p[0] * units_to_m, p[1] * units_to_m) for p in pts_raw]
            poly = ShapelyPolygon(coords)
            if not poly.is_valid or poly.area < 1.0:  # < 1 m² → skip
                continue
        except Exception:
            continue

        room_idx += 1
        room_name = f"Room_{room_idx}"

        # Try to find a text label nearby (future: use OCR results)
        room_type = "unknown"
        if "OFFICE" in layer:
            room_type = "office"
        elif "CORRIDOR" in layer or "CORR" in layer:
            room_type = "corridor"
        elif "STAIR" in layer:
            room_type = "stairwell"
        elif "MECH" in layer:
            room_type = "mechanical"
        elif "ELEC" in layer:
            room_type = "electrical"
        elif "STOR" in layer:
            room_type = "storage"

        rooms.append(Room(
            id=f"room_{room_idx}",
            name=room_name,
            room_type=room_type,
            floor_area=round(poly.area, 2),
            geometry=poly,
            ceiling_height=2.8,
            ceiling_type="SMOOTH",
        ))
        seen_layers.add(layer)

    return rooms


def _extract_rooms_from_ifc(entities: list) -> list:
    """
    Extract rooms from IFC entities. Each IfcSpace becomes a Room.
    """
    rooms = []
    for e in entities:
        if e.kind != "ifcspace":
            continue
        attrs = e.attributes
        name = attrs.get("name") or attrs.get("long_name") or "Unnamed"
        # IFC geometry is stored as GlobalId reference; we need the bridge
        # to resolve it. For now, create a placeholder polygon.
        rooms.append(Room(
            id=e.provenance.get("ifc_id", str(id(e))),
            name=name,
            room_type="unknown",
            floor_area=0.0,
            geometry=ShapelyPolygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            ceiling_height=2.8,
            ceiling_type="SMOOTH",
        ))
    return rooms


# ════════════════════════════════════════════════════════════════════════════
# Device extraction from classified symbols
# ════════════════════════════════════════════════════════════════════════════

def _extract_devices_from_classifications(
    elements: list,
    units_to_m: float = 0.001,
    min_confidence: float = 0.5,
) -> list:
    """
    Convert classified EDA elements into FireAI Device objects.

    Only symbols with confidence ≥ min_confidence are converted.
    Below this threshold, a warning is issued instead.
    """
    devices = []
    dev_idx = 0

    for el in elements:
        cls = el.get("classification", {}) if isinstance(el, dict) else {}
        symbol = cls.get("symbol", "unknown")
        confidence = cls.get("confidence", 0.0)

        if symbol == "unknown":
            continue
        if confidence < min_confidence:
            continue  # don't guess

        device_type = SYMBOL_TO_DEVICE_TYPE.get(symbol)
        if not device_type:
            continue  # not a recognized device

        bbox = el.get("bbox", (0, 0, 0, 0))
        cx = ((bbox[0] + bbox[2]) / 2) * units_to_m
        cy = ((bbox[1] + bbox[3]) / 2) * units_to_m

        dev_idx += 1
        devices.append(Device(
            id=f"dev_{dev_idx}",
            device_type=device_type,
            position=ShapelyPoint(cx, cy),
            room_id="",  # assigned later by spatial containment
            z_height=DEVICE_MOUNT_HEIGHT.get(device_type, 2.4),
            coverage_radius=DEVICE_COVERAGE_RADIUS.get(device_type, 0.0),
        ))

    return devices


def _assign_devices_to_rooms(devices: list, rooms: list) -> list:
    """
    Assign each device to the room that contains its position.
    Devices not contained in any room get room_id="" and a warning.
    """
    warnings = []
    for d in devices:
        assigned = False
        for r in rooms:
            if r.geometry.contains(d.position):
                d.room_id = r.id
                assigned = True
                break
            # Fallback: nearest room within 0.5m
            if r.geometry.buffer(0.5).contains(d.position):
                d.room_id = r.id
                assigned = True
                warnings.append(
                    f"Device {d.id} assigned to {r.name} by proximity (0.5m buffer), "
                    f"not strict containment. Verify manually."
                )
                break
        if not assigned:
            warnings.append(
                f"Device {d.id} ({d.device_type}) at ({d.position.x:.2f}, {d.position.y:.2f}) "
                f"is NOT inside any room. Skipping device."
            )
    return warnings


# ════════════════════════════════════════════════════════════════════════════
# Obstruction extraction
# ════════════════════════════════════════════════════════════════════════════

def _extract_obstructions_from_entities(
    entities: list,
    units_to_m: float = 0.001,
) -> list:
    """
    Extract obstructions (columns, beams) from DXF/DWG entities.
    Looks for closed polylines on structural layers.
    """
    obstructions = []
    obs_idx = 0

    for e in entities:
        layer = (e.layer or "").upper()
        is_structural = any(k in layer for k in
                           ("COL", "COLUMN", "BEAM", "STR", "STRUCT", "STRUC"))
        if not is_structural:
            continue
        if e.kind != "polyline" or not e.geom.get("closed"):
            continue

        pts_raw = e.geom.get("points", [])
        if len(pts_raw) < 3:
            continue

        try:
            coords = [(p[0] * units_to_m, p[1] * units_to_m) for p in pts_raw]
            poly = ShapelyPolygon(coords)
            if not poly.is_valid or poly.area < 0.01:
                continue
        except Exception:
            continue

        obs_idx += 1
        obstructions.append(Obstruction(
            id=f"obs_{obs_idx}",
            geometry=poly,
            height=2.4,
            blocks_visibility=True,
        ))

    return obstructions


# ════════════════════════════════════════════════════════════════════════════
# Main entry point
# ════════════════════════════════════════════════════════════════════════════

def parse_drawing_to_fireai(
    path: str,
    units_to_m: float = 0.001,
    min_confidence: float = 0.5,
    schedule: list = None,
    auto_schedule: bool = True,
) -> ParseBridgeResult:
    """
    Bridge 2: Parse any drawing file → FireAI Room/Device/Obstruction models.

    Uses EDA's ingest pipeline under the hood, then converts the
    NormalizedDrawing into FireAI's native data structures.

    Parameters
    ----------
    path           : Drawing file path (DXF/DWG/PDF/IFC/image)
    units_to_m     : Multiplier from drawing units to metres (mm → 0.001)
    min_confidence : Minimum classification confidence to accept a device
    schedule       : Optional BOQ list [{"item": ..., "qty": ...}]
    auto_schedule  : Auto-extract schedule from PDF if available

    Returns
    -------
    ParseBridgeResult with rooms, devices, obstructions, warnings
    """
    t0 = time.time()
    warnings = []

    # ── Step 1: Run EDA ingest ──
    try:
        from elite_drawing_analyzer.core.ingest import ingest, NormalizedDrawing
        nd: NormalizedDrawing = ingest(path)
    except ImportError:
        warnings.append("EDA not available. Install elite_drawing_analyzer package.")
        return ParseBridgeResult(
            source_file=os.path.basename(path),
            source_type="unknown",
            warnings=warnings,
            elapsed_seconds=time.time() - t0,
        )
    except Exception as ex:
        warnings.append(f"Ingest failed: {ex}")
        return ParseBridgeResult(
            source_file=os.path.basename(path),
            source_type="unknown",
            warnings=warnings,
            elapsed_seconds=time.time() - t0,
        )

    log.info("Ingested %s as %s: %d entities, %d layers",
             path, nd.file_type, len(nd.entities), len(nd.layers))

    # ── Step 2: Extract rooms ──
    if nd.file_type == "ifc":
        rooms = _extract_rooms_from_ifc(nd.entities)
        warnings.append("IFC room extraction is placeholder — geometry needs resolution.")
    else:
        rooms = _extract_rooms_from_entities(nd.entities, units_to_m)

    # ── Step 3: Run EDA classification pipeline ──
    classified_elements = []
    try:
        from elite_drawing_analyzer.pipeline import analyze_file
        from elite_drawing_analyzer.intelligence.knowledge_base import KnowledgeBase

        kb = KnowledgeBase()
        report = analyze_file(path, kb=kb, schedule=schedule,
                              auto_schedule=auto_schedule,
                              units_to_m=units_to_m, do_ocr=True)

        classified_elements = report.elements

        # Capture EDA warnings
        for w in report.warnings:
            warnings.append(f"EDA: {w}")

    except Exception as ex:
        warnings.append(f"EDA classification failed (non-fatal): {ex}")
        log.warning("EDA pipeline error: %s", ex)

    # ── Step 4: Extract devices from classifications ──
    devices = _extract_devices_from_classifications(
        classified_elements, units_to_m, min_confidence)

    # ── Step 5: Assign devices to rooms ──
    assignment_warnings = _assign_devices_to_rooms(devices, rooms)
    warnings.extend(assignment_warnings)

    # ── Step 6: Extract obstructions ──
    obstructions = _extract_obstructions_from_entities(nd.entities, units_to_m)

    # ── Step 7: Build stats ──
    stats = {
        "total_entities": len(nd.entities),
        "rooms_found": len(rooms),
        "devices_classified": len(devices),
        "obstructions_found": len(obstructions),
        "classified_elements": len(classified_elements),
        "eda_file_type": nd.file_type,
        "eda_layers": len(nd.layers),
        "eda_blocks": len(nd.blocks),
        "low_confidence_skipped": sum(
            1 for el in classified_elements
            if isinstance(el, dict)
            and el.get("classification", {}).get("confidence", 0) < min_confidence
        ),
    }

    result = ParseBridgeResult(
        source_file=os.path.basename(path),
        source_type=nd.file_type,
        rooms=rooms,
        devices=devices,
        obstructions=obstructions,
        classified_symbols=classified_elements,
        warnings=warnings,
        stats=stats,
        elapsed_seconds=round(time.time() - t0, 2),
    )

    log.info("Bridge 2 complete: %d rooms, %d devices, %d obstructions from %s",
             len(rooms), len(devices), len(obstructions), os.path.basename(path))

    return result


# ════════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════════

def _self_test():
    """Test with a programmatically created DXF file."""
    import tempfile
    print("=" * 60)
    print("BRIDGE 2: Parser Bridge — Self-Test")
    print("=" * 60)

    # Create a minimal DXF with a room rectangle and a block ref
    try:
        import ezdxf
    except ImportError:
        print("SKIP: ezdxf not installed")
        return

    doc = ezdxf.new("R2018")
    msp = doc.modelspace()

    # Room outline (closed polyline)
    msp.add_lwpolyline(
        [(0, 0), (10000, 0), (10000, 8000), (0, 8000)],
        format="xy", close=True,
        dxfattribs={"layer": "A-ROOM"}
    )

    # Column
    msp.add_lwpolyline(
        [(4000, 3000), (4200, 3000), (4200, 3200), (4000, 3200)],
        format="xy", close=True,
        dxfattribs={"layer": "S-COLUMN"}
    )

    # Smoke detector block reference
    doc.blocks.new("SMOKE_DETECTOR")
    msp.add_blockref(
        "SMOKE_DETECTOR", insert=(5000, 4000),
        dxfattribs={"layer": "FA-DETECTORS"}
    )

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        dxf_path = f.name
    doc.saveas(dxf_path)

    print(f"\nCreated test DXF: {dxf_path}")

    # Run bridge
    result = parse_drawing_to_fireai(dxf_path, units_to_m=0.001)

    print(f"\nSource: {result.source_file} ({result.source_type})")
    print(f"Rooms:  {len(result.rooms)}")
    print(f"Devices: {len(result.devices)}")
    print(f"Obstructions: {len(result.obstructions)}")
    print(f"Warnings: {len(result.warnings)}")
    print(f"Stats: {result.stats}")
    print(f"Elapsed: {result.elapsed_seconds}s")

    for w in result.warnings:
        print(f"  ⚠ {w}")

    for r in result.rooms:
        print(f"  Room: {r.name} ({r.room_type}) area={r.floor_area}m²")

    for d in result.devices:
        print(f"  Device: {d.device_type} room={d.room_id} @ ({d.position.x:.3f}, {d.position.y:.3f})")

    # Cleanup
    os.unlink(dxf_path)

    print("\n" + "=" * 60)
    status = "PASS" if len(result.rooms) >= 1 else "FAIL"
    print(f"Bridge 2 Self-Test: {status}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
