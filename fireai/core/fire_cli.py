#!/usr/bin/env python3
"""
fire_cli.py — Command-line runner for FireAI
Adapted for V10 Enhanced + LearningStore
Usage:
  python fire_cli.py room.json
  python fire_cli.py room.json --out report.json
  echo '{"room_id":"R1","width":10,"depth":10,"occupancy":"office"}' | python fire_cli.py -
"""
import argparse, json, sys, logging
from pathlib import Path

logging.basicConfig(level=logging.WARNING)


def parse_simple(data: dict):
    """Convert simplified JSON to RoomSpec."""
    from fireai.core.nfpa72_models import RoomSpec, CeilingSpec, CeilingType
    
    # Support width/depth (simple) or polygon (advanced)
    poly = None
    if "polygon" in data:
        poly = [tuple(p) for p in data["polygon"]]
        width = max(p[0] for p in poly) if poly else data.get("width", 10)
        depth = max(p[1] for p in poly) if poly else data.get("depth", 10)
    else:
        width = data.get("width", 10)
        depth = data.get("depth", 10)
    
    ceiling = CeilingSpec.create_safe(
        height_at_low_point_m=data.get("height", 3.0),
        height_at_high_point_m=data.get("height_high", data.get("height", 3.0)),
        ceiling_type=CeilingType[data.get("ceiling_type", "FLAT")] if data.get("ceiling_type") else CeilingType.FLAT,
    )
    
    return RoomSpec(
        room_id=data["room_id"],
        width_m=width,
        depth_m=depth,
        occupancy_type=data.get("occupancy", "office"),
        ceiling_spec=ceiling,
        polygon=poly,
    )


def result_to_dict(r) -> dict:
    return {
        "room_id": r.room_id,
        "compliant": r.compliant,
        "safe_to_submit": r.safe_to_submit if hasattr(r, 'safe_to_submit') else None,
        "confidence": r.confidence.value if r.confidence else "UNKNOWN",
        "confidence_score": round(r.confidence_score, 4) if r.confidence_score else 0,
        "detector_count": len(r.detector_positions),
        "detector_type": r.detector_type.value if r.detector_type else "SMOKE",
        "occupancy": r.occupancy_class.value if r.occupancy_class else "office",
        "coverage_pct": round(r.placement_proof.coverage_fraction * 100, 2) if r.placement_proof else 0,
        "wall_violations": len(r.wall_violations),
        "resilient": r.resilience.resilient if r.resilience else None,
        "resilience_pass_rate": round(r.resilience.pass_rate, 3) if r.resilience else None,
        "warnings": r.warnings,
        "errors": r.errors,
        "detector_positions": [{"x": round(x, 3), "y": round(y, 3)} for x, y in r.detector_positions],
    }


def main():
    ap = argparse.ArgumentParser(description="FireAI - NFPA 72 Expert System")
    ap.add_argument("input", help="JSON file path or '-' for stdin")
    ap.add_argument("--out", help="Output JSON file (default: stdout)")
    ap.add_argument("--no-resilience", action="store_true", help="Skip resilience check")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text()
    data = json.loads(raw)

    rooms_data = data if isinstance(data, list) else [data]

    from fireai.core.fireai_core import FireAISystem
    
    system = FireAISystem(':memory:')

    results = []
    for rd in rooms_data:
        spec = parse_simple(rd)
        r = system.analyse_room(spec, user_id='cli', run_resilience=not args.no_resilience)
        results.append(result_to_dict(r))

    output = json.dumps(results[0] if len(results) == 1 else results, indent=2)
    
    if args.out:
        Path(args.out).write_text(output)
        print(f"Saved → {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()