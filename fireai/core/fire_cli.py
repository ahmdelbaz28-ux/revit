"""fire_cli.py – FireAI command-line entry point.

Usage:
    fireai version
    fireai analyse <input.json>
    fireai report --format pdf <input.json> [--output <out.pdf>]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Literal

_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        print(f"[fireai] ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def _detect_input_type(data: Dict[str, Any]) -> str:
    """Heuristic: decide whether JSON is a room, floor, or building spec."""
    if "floors" in data or "floor_reports" in data:
        return "building"
    if "rooms" in data or "room_summaries" in data:
        return "floor"
    if "width" in data or "polygon_coords" in data:
        return "room"
    # fallback
    return "floor"


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"fireai {_VERSION}")
    return 0


def cmd_analyse(args: argparse.Namespace) -> int:
    data = _load_json(args.input)
    input_type = _detect_input_type(data)

    if input_type == "room":
        return _analyse_room(data)
    if input_type == "floor":
        return _analyse_floor(data)
    return _analyse_building(data)


def _analyse_room(data: Dict[str, Any]) -> int:
    try:
        from fireai.core.geometry_utils import is_rectangular
        from fireai.core.nfpa72_calculations import (
            calculate_coverage_radius_from_height,
        )
        from fireai.core.polygon_optimizer import PolygonDensityOptimizer, PolygonRoom
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room

        polygon = data.get("polygon_coords")
        # V114 FIX: Validate ceiling_height for NaN/Inf — float() accepts NaN silently
        _raw_ceiling_h = data.get("ceiling_height", 3.0)
        ceiling_h = float(_raw_ceiling_h)
        if not math.isfinite(ceiling_h):
            raise ValueError(
                f"ceiling_height must be a finite number, got {ceiling_h!r} "
                f"(from input: {_raw_ceiling_h!r}). NaN/Inf corrupt all NFPA 72 calculations."
            )
        det_type = data.get("detector_type", "smoke")

        if polygon and not is_rectangular(polygon):
            poly_room = PolygonRoom(
                room_id=data.get("room_id", "room-cli"),
                polygon=polygon,
                ceiling_height=ceiling_h,
                detector_type=det_type,
                ducts=data.get("ducts", []),
            )
            summary = PolygonDensityOptimizer().optimize_polygon(poly_room)
            result = {
                "room_id": summary.room_id,
                "method": summary.method,
                "detector_count": summary.count,
                "coverage_pct": summary.coverage_pct,
                "proof_valid": summary.proof_valid,
                "wall_violations": summary.wall_violations,
                "detectors": summary.detectors,
                "duct_devices": summary.duct_devices,
                "duct_warnings": summary.duct_warnings,
            }
        else:
            # V114 FIX: Validate width/length for NaN/Inf
            width = float(data.get("width", data.get("length", 10.0)))
            length = float(data.get("length", 10.0))
            if not math.isfinite(width) or not math.isfinite(length):
                raise ValueError(
                    f"Room dimensions must be finite, got width={width!r} length={length!r}. "
                    f"NaN/Inf corrupt NFPA 72 detector placement calculations."
                )
            room = Room(
                name=data.get("room_id", "room-cli"),
                width=width,
                length=length,
                ceiling_height=ceiling_h,
            )
            cov_det_type: Literal["smoke", "heat"] = "heat" if "heat" in det_type.lower() else "smoke"
            spec = calculate_coverage_radius_from_height(ceiling_h, cov_det_type)
            radius = spec.radius
            layout = DensityOptimizer().optimize(room, coverage_radius=radius)
            result = {
                "room_id": data.get("room_id", "room-cli"),
                "method": layout.method,
                "detector_count": layout.count,
                "coverage_pct": layout.coverage_pct,
                "proof_valid": layout.proof_valid,
                "wall_violations": layout.wall_violations,
                "detectors": layout.detectors,
            }

        _print_json(result)
        return 0

    except Exception as exc:
        print(f"[fireai] analyse room failed: {exc}", file=sys.stderr)
        return 2


def _analyse_floor(data: Dict[str, Any]) -> int:
    try:
        from fireai.core.floor_analyser import FloorAnalyser
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

        rooms = data.get("rooms", data.get("room_summaries", [data]))
        opt = DensityOptimizer()
        report = FloorAnalyser(floor_id="floor-cli", optimizer=opt).analyse(rooms)
        _print_json(
            {
                "floor_id": getattr(report, "floor_id", "floor-cli"),
                "total_rooms": len(getattr(report, "room_summaries", [])),
                "total_detectors": getattr(report, "total_detectors", "N/A"),
                "fully_compliant": getattr(report, "fully_compliant", "N/A"),
                "room_summaries": [
                    {
                        "room_id": getattr(rs, "room_id", "-"),
                        "detector_count": getattr(rs, "detector_count", getattr(rs, "count", "-")),
                        "coverage_pct": getattr(rs, "coverage_pct", "-"),
                        "nfpa_valid": getattr(rs, "nfpa_valid", "-"),
                    }
                    for rs in getattr(report, "room_summaries", [])
                ],
            }
        )
        return 0

    except Exception as exc:
        print(f"[fireai] analyse floor failed: {exc}", file=sys.stderr)
        return 2


def _analyse_building(data: Dict[str, Any]) -> int:
    try:
        from fireai.core.building_engine import BuildingEngine
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

        opt = DensityOptimizer()
        building_id = data.get("building_id", "building-cli")
        engine = BuildingEngine(building_id=building_id, optimizer=opt)

        floors_raw = data.get("floors", [data])
        if isinstance(floors_raw, dict):
            floors = floors_raw
        elif isinstance(floors_raw, list):
            floors = {"F1": floors_raw}
        else:
            floors = {"F1": [data]}

        report = engine.analyse(floors=floors)
        _print_json(
            {
                "building_id": report.building_id,
                "total_detectors": report.total_detectors,
                "total_duct_devices": report.total_duct_devices,
                "fully_compliant": report.fully_compliant,
                "safe_to_submit": report.safe_to_submit,
                "non_compliant_floors": report.non_compliant_floors,
                "building_warnings": report.building_warnings,
            }
        )
        return 0

    except Exception as exc:
        print(f"[fireai] analyse building failed: {exc}", file=sys.stderr)
        return 2


def cmd_report(args: argparse.Namespace) -> int:
    fmt = args.format.lower()
    if fmt != "pdf":
        print(f"[fireai] Unsupported format: {fmt}. Only 'pdf' is supported.", file=sys.stderr)
        return 1

    data = _load_json(args.input)

    # Determine output path
    if args.output:
        out_path = args.output
    else:
        stem = Path(args.input).stem
        out_path = f"{stem}_report.pdf"

    try:
        from fireai.core.building_engine import BuildingEngine
        from fireai.core.pdf_report import generate_building_report
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

        opt = DensityOptimizer()
        building_id = data.get("building_id", "report-cli")
        engine = BuildingEngine(building_id=building_id, optimizer=opt)

        floors_raw = data.get("floors", [data])
        if isinstance(floors_raw, dict):
            floors = floors_raw
        elif isinstance(floors_raw, list):
            floors = {"F1": floors_raw}
        else:
            floors = {"F1": [data]}

        report = engine.analyse(floors=floors)
        result = generate_building_report(report, out_path)
        print(f"[fireai] PDF report written to: {result}")
        return 0

    except Exception as exc:
        print(f"[fireai] report generation failed: {exc}", file=sys.stderr)
        return 2


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fireai",
        description="FireAI – NFPA 72-2022 Automated Fire Detector Placement Engine",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_VERSION}",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # version sub-command
    sub.add_parser("version", help="Print version and exit")

    # analyse sub-command
    p_analyse = sub.add_parser(
        "analyse",
        help="Analyse a room / floor / building JSON file",
    )
    p_analyse.add_argument(
        "input",
        metavar="INPUT.JSON",
        help="Path to JSON input file (room, floor, or building spec)",
    )

    # report sub-command
    p_report = sub.add_parser(
        "report",
        help="Generate a formatted report from a building JSON file",
    )
    p_report.add_argument(
        "--format",
        default="pdf",
        choices=["pdf"],
        help="Output format (default: pdf)",
    )
    p_report.add_argument(
        "input",
        metavar="INPUT.JSON",
        help="Path to building JSON input file",
    )
    p_report.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="OUTPUT",
        help="Output file path (default: <input_stem>_report.pdf)",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        sys.exit(cmd_version(args))
    elif args.command == "analyse":
        sys.exit(cmd_analyse(args))
    elif args.command == "report":
        sys.exit(cmd_report(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
