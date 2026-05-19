"""
generate_full_circle_arc_test_dxf.py — FireAI V5.1.2
Creates DXF file with ARC (full circle = 0 to 360).
"""

import ezdxf
from pathlib import Path


def create_full_circle_arc_test(filename: str = "tests/fixtures/arc_circle.dxf"):
    Path("tests/fixtures").mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 6  # Meters

    msp = doc.modelspace()

    # Room: rectangle
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 8))
    msp.add_line((10, 8), (0, 8))
    msp.add_line((0, 8), (0, 0))
    
    # Full circle ARC (0 to 360 = full circle)
    msp.add_arc(
        center=(5, 4),
        radius=1.0,
        start_angle=0,
        end_angle=360,
        dxfattribs={"layer": "A-COLS"}
    )

    doc.saveas(filename)
    print(f"✅ Full Circle ARC Test created: {filename}")


if __name__ == "__main__":
    create_full_circle_arc_test()