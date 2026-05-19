"""
generate_test_dxf.py — FireAI V5.1.0
Creates a simple DXF file for testing.
Run once: python generate_test_dxf.py
"""

import ezdxf
from pathlib import Path


def create_test_dxf(filename: str = "tests/fixtures/simple_floor_2rooms.dxf"):
    Path("tests/fixtures").mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 6  # Meters

    msp = doc.modelspace()

    # Room 1: 8x6m
    msp.add_lwpolyline(
        [(0, 0), (8, 0), (8, 6), (0, 6), (0, 0)],
        close=True,
        dxfattribs={"layer": "A-WALL"}
    )

    # Room 2: 5x5m
    msp.add_lwpolyline(
        [(10, 0), (15, 0), (15, 5), (10, 5), (10, 0)],
        close=True,
        dxfattribs={"layer": "A-WALL"}
    )

    # Column in Room 1
    msp.add_lwpolyline(
        [(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)],
        close=True,
        dxfattribs={"layer": "A-COLS"}
    )

    doc.saveas(filename)
    print(f"✅ Test DXF created: {filename}")


if __name__ == "__main__":
    create_test_dxf()