#!/usr/bin/env python3
"""fireai/cli.py - Unified CLI for FireAI
Usage: python -m fireai.cli build -f FILE.dxf -o OUTPUT_DIR

V82 FIX: Removed all dead ``src.*`` imports that never existed.
The ``src.auto_placement``, ``src.application.*``, ``src.core.models``,
and ``src.infrastructure.*`` modules were removed in a prior restructure
but the CLI still had try/except blocks importing them. These were
harmless (ImportError was caught) but added confusion.

The ``build`` command's full pipeline now fails with a clear error
message if the required modules are not available, instead of crashing
with an uncaught NameError.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

import click

# V82 FIX: Try to import the application layer modules.
# These are optional — the CLI degrades gracefully if missing.
_src_modules: dict = {}

try:
    from fireai.dxf_importer import DXFImporter as _DXFImporter
    _src_modules["dxf_importer"] = _DXFImporter
except ImportError:
    pass

# NOTE: src.* modules were removed during project restructure.
# The build command will show a clear error if these are needed.


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
    # V82 FIX: The src.* application layer does not exist in this project.
    # These names (NFPA72, BS5839, DeviceType, CoverageService, etc.) were
    # imported from src.* modules that were removed during restructuring.
    # The full pipeline is available via `python run_full_pipeline.py`.
    click.echo(
        "ERROR: Full pipeline requires src.* application layer (not installed). "
        "Use `python run_full_pipeline.py` for the complete workflow, which "
        "uses the fireai.* modules directly."
    )
    sys.exit(1)


if __name__ == "__main__":
    cli()
