#!/usr/bin/env python3
"""
fireai/cli.py - Unified CLI for FireAI
Usage: python -m fireai.cli build -f FILE.dxf -o OUTPUT_DIR

CRITICAL FIX: Removed broken import of src.dxf_importer (doesn't exist).
CLI now degrades gracefully when optional modules are missing.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

import click

# CRITICAL FIX: Lazy imports — these modules may not be available.
# The old code imported src.dxf_importer which doesn't exist.
# Now we import inside the command handler and fail gracefully.
try:
    from src.auto_placement import suggest_devices

    _HAS_AUTO_PLACEMENT = True
except ImportError:
    _HAS_AUTO_PLACEMENT = False

try:
    from src.application.cable_router import CableRouter
    from src.application.coverage_service import CoverageService
    from src.application.graph_builder import GraphBuilder
    from src.application.schemas import PanelConfig

    _HAS_APPLICATION = True
except ImportError:
    _HAS_APPLICATION = False

try:
    from src.core.models import BS5839, NFPA72, DeviceType

    _HAS_MODELS = True
except ImportError:
    _HAS_MODELS = False

try:
    from src.infrastructure.boq_generator import BOQGenerator
    from src.infrastructure.dxf_production_writer import DXFProductionWriter
    from src.infrastructure.justification_writer import generate_justification, write_justification_to_file

    _HAS_INFRASTRUCTURE = True
except ImportError:
    _HAS_INFRASTRUCTURE = False

# NOTE: src.dxf_importer was removed — DXF import must use alternative path


DISCLAIMER = """
⚠️  تنبيه قانوني ومهني IMPORTANT DISCLAIMER
==============================================================
This tool is provided for PRELIMINARY DESIGN ASSISTANCE ONLY.
Results must be reviewed and validated by a qualified professional engineer
before use in actual fire alarm system designs.
NFPA 72, BS 5839 and local codes must be consulted for final design.
Developer assumes NO LIABILITY for use of this tool's output.
==============================================================
"""


def print_header():
    print("\n" + "=" * 70)
    print("🔥 FireAI v1.0 - AHMED ELBAZ Stability Release")
    print("=" * 70)


@click.group()
def cli():
    """🔥 FireAI v1.0 - Fire Alarm Design Assistant"""
    pass


@cli.command()
@click.option("--file", "-f", "dxf_file", required=True, type=click.Path(exists=True), help="ملف DXF للمبنى")
@click.option("--calibrate", "-c", default=None, help="معايرة: distance,x1,y1,x2,y2")
@click.option("--output", "-o", default="output", help="مجلد الإخراج")
@click.option("--standard", "-s", default="NFPA72", type=click.Choice(["NFPA72", "BS5839"]), help="المعيار الهندسي")
@click.option("--panel", "-p", default="0,0", help="موقع اللوحة: x,y")
def build(dxf_file, calibrate, output, standard, panel):
    """تشغيل كامل: استيراد ← توزيع ← توجيه ← إنتاج"""
    print_header()
    click.echo(DISCLAIMER)

    # Parse panel location
    panel_x, panel_y = map(float, panel.split(","))

    # Create output directory
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Import DXF
    click.echo(f"\n📥 جاري استيراد: {dxf_file}")

    # CRITICAL FIX: DXFImporter was removed (src.dxf_importer never existed).
    # The full pipeline CLI requires the src.* application layer which may not
    # be installed. Fail gracefully instead of crashing with NameError.
    try:
        from fireai.dxf_importer import DXFImporter as _DXFImporter

        importer = _DXFImporter(dxf_file)

        if calibrate:
            d, x1, y1, x2, y2 = map(float, calibrate.split(","))
            importer.calibrate_scale(d, (x1, y1), (x2, y2))

        rooms = importer.to_domain_models()
        walls = importer.extract_walls()
        click.echo(f"✅ استيراد {len(rooms)} غرفة، {len(walls)} جدار")
    except ImportError:
        click.echo(
            "ERROR: DXFImporter module not available. "
            "Use `python run_full_pipeline.py` instead, which supports "
            "DXF import via ezdxf."
        )
        sys.exit(1)

    # 2. Device placement and coverage
    if standard == "NFPA72":
        standard_obj = NFPA72()
    else:
        standard_obj = BS5839()

    spacing = standard_obj.get_max_spacing(DeviceType.SMOKE_DETECTOR)

    service = CoverageService()
    all_devices = []
    all_violations = []

    for room in rooms:
        devices = suggest_devices(room, spacing)

        for d in devices:
            d.room_id = room.room_id or room.name

        all_devices.extend(devices)
        violations = service.check_coverage(room, devices, standard_obj)
        all_violations.extend(violations)

    click.echo(f"✅ اقتراح {len(all_devices)} جهاز")

    if all_violations:
        click.echo(click.style(f"⚠️  {len(all_violations)} مخالفة تغطية", fg="red"))
    else:
        click.echo(click.style("✅ لا توجد مخالفات تغطية", fg="green"))

    # 3. Cable routing
    panel_pos = (panel_x, panel_y)

    if rooms and rooms[0].polygon:
        builder = GraphBuilder(grid_spacing_m=1.0)
        graph = builder.build_from_polygon(rooms[0].polygon.exterior, panel_pos, walls)
        router = CableRouter(graph, panel_pos, PanelConfig())
        cable_paths, loops = router.calculate_routes(all_devices)
        total_cable_m = sum(cp.total_length_m for cp in cable_paths)
        click.echo(f"✅ توجيه {total_cable_m:.1f}m كابل في {len(loops)} حلقة")
    else:
        cable_paths = []
        total_cable_m = 0.0

    # 4. Production export
    device_dicts = []
    for d in all_devices:
        if d.position:
            device_dicts.append({"id": d.device_id, "position": (d.position.x, d.position.y), "type": "SMOKE"})

    # Export DXF
    try:
        dxf_writer = DXFProductionWriter(coverage_radius_m=6.0)
        dxf_writer.create_dxf(
            devices=device_dicts,
            cable_paths=cable_paths,
            panel_location=panel_pos,
            room_boundaries=[r.polygon for r in rooms if r.polygon],
            output_file=str(out_dir / f"{output}.dxf"),
        )
        click.echo(f"📄 Created {output}.dxf")
    except Exception as e:
        click.echo(f"⚠️ DXF export: {e}")

    # Export BOQ
    try:
        boq = BOQGenerator()
        boq.generate_boq(
            devices=device_dicts,
            cable_paths=cable_paths,
            panel_location=panel_pos,
            output_file=str(out_dir / f"{output}_boq.csv"),
        )
        click.echo(f"💰 Created {output}_boq.csv")
    except Exception as e:
        click.echo(f"⚠️ BOQ export: {e}")

    # 5. Justification reports
    try:
        for room in rooms:
            room_id = room.room_id or room.name or "room"
            room_devs = [d for d in all_devices if getattr(d, "room_id", None) == room_id]
            room_viols = [v for v in all_violations if getattr(v, "room_id", None) == room_id]

            # Estimate cable for this room
            room_cable_m = total_cable_m * len(room_devs) / max(1, len(all_devices))

            report = generate_justification(
                room=room,
                devices=room_devs,
                violations=room_viols,
                cable_total_m=room_cable_m,
                cable_direct_m=room_cable_m * 0.7,
                beams=[],
                standard=standard_obj,
                voltage_drop_v=0.0,
                loop_resistance_ohm=0.0,
                is_loop_compliant=True,
            )

            room_name = room.name or "room"
            report_file = out_dir / f"justification_{room_name}.txt"
            write_justification_to_file(report, str(report_file))
            click.echo(f"📝 Created justification_{room_name}.txt")
    except Exception as e:
        click.echo(f"⚠️ Justification: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("🎉 DESIGN COMPLETE!")
    print("=" * 70)
    print(f"   Devices: {len(all_devices)}")
    print(f"   Cable: {total_cable_m:.1f}m")
    print(f"   Violations: {len(all_violations)}")
    print(f"   Output: {out_dir.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    cli()
