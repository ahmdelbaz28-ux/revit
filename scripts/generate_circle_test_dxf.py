"""
generate_circle_test_dxf.py — FireAI V5.1.2
Creates DXF file with CIRCLE entities for testing.
"""

import ezdxf
from pathlib import Path


def create_circle_test_dxf(filename: str = "tests/fixtures/circle_column.dxf"):
    Path("tests/fixtures").mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 6  # Meters

    msp = doc.modelspace()

    # Room: 10x8m (drawn with LINE entities)
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 8))
    msp.add_line((10, 8), (0, 8))
    msp.add_line((0, 8), (0, 0))

    # Circle as column (center at 5,4, radius 0.3m = 30cm)
    msp.add_circle(
        center=(5, 4),
        radius=0.3,
        dxfattribs={"layer": "A-COLS"}
    )

    doc.saveas(filename)
    print(f"✅ Circle Test DXF created: {filename}")


if __name__ == "__main__":
    create_circle_test_dxf()