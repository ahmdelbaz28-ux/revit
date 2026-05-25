"""
generate_arc_test_dxf.py — FireAI V5.1.2
Creates DXF file with ARC entities for testing.
"""

import ezdxf
from pathlib import Path
import math


def create_arc_test_dxf(filename: str = "tests/fixtures/arc_wall.dxf"):
    Path("tests/fixtures").mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 6  # Meters

    msp = doc.modelspace()

    # Room: part LWPOLYLINE, part ARC (curved wall)
    # Room shape: rectangle with curved wall
    # Draw 3 straight walls
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 8))
    msp.add_line((10, 8), (0, 8))
    
    # Curved wall (ARC) from (0,8) to (0,0) - a quarter circle arc
    # Center at (0,8), radius 8, from angle 270 to 360
    msp.add_arc(
        center=(0, 8),
        radius=8,
        start_angle=270,
        end_angle=360,
        dxfattribs={"layer": "A-WALL"}
    )

    doc.saveas(filename)
    print(f"✅ Arc Test DXF created: {filename}")


if __name__ == "__main__":
    create_arc_test_dxf()