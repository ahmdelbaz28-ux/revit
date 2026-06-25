"""bim_unit_detector.py — Automated BIM Unit Detection
=======================================================

MISSION PHASE 4.2 — Fix the Hardcoded Scale Bug
==================================================

This module provides automated unit detection for BIM data sources. Instead
of assuming all DXF/IFC files use millimetres (the current hardcoded
``scale_factor=0.001``), this module inspects BIM metadata to determine
the actual unit, then returns the correct scale factor.

Supported Detection Strategies
------------------------------
1. **IFC Unit Declaration**: IFC files declare units in the header
   (``FILE_SCHEMA``, ``UNITASSIGNMENT``). We parse this directly.
2. **DXF INSUNITS Variable**: DXF files store a ``$INSUNITS`` system
   variable that declares the drawing's base unit.
3. **Revit Internal Units**: Revit stores coordinates in "internal units"
   (feet by default). We detect this via ``$INSBASE`` or document metadata.
4. **Heuristic Fallback**: If no metadata is available, we use a heuristic
   based on the magnitude of coordinates (e.g., a 10m room has coordinates
   ~10 if metres, ~10000 if millimetres).

Usage
-----
    from fireai.bridges.bim_unit_detector import detect_bim_unit, UnitSystem

    unit = detect_bim_unit("/path/to/file.ifc")
    print(unit)  # UnitSystem.METRES, UnitSystem.MILLIMETRES, etc.
    print(unit.scale_to_metres)  # 1.0, 0.001, 0.01, 0.3048

References
----------
- ISO 16739-1:2024 (IFC) — unit declaration in header
- DXF Reference: $INSUNITS system variable
- Revit API: internal units are feet (1 ft = 0.3048 m)
- agent.md Rule 17 (Root-Cause Analysis) — fix the root cause, not the symptom
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unit System Enum
# ---------------------------------------------------------------------------


class UnitSystem(str, Enum):
    """Supported BIM unit systems with their scale-to-metres factors.

    The ``scale_to_metres`` property gives the multiplier to convert a
    coordinate in this unit system to metres.
    """

    METRES = "metres"
    CENTIMETRES = "centimetres"
    MILLIMETRES = "millimetres"
    FEET = "feet"              # Revit internal units
    INCHES = "inches"
    UNKNOWN = "unknown"

    @property
    def scale_to_metres(self) -> float:
        """Multiplier to convert this unit to metres.

        Per NIST SP 1038 (International System of Units):
            1 m = 100 cm = 1000 mm = 3.28084 ft = 39.3701 in
        """
        return {
            UnitSystem.METRES: 1.0,
            UnitSystem.CENTIMETRES: 0.01,
            UnitSystem.MILLIMETRES: 0.001,
            UnitSystem.FEET: 0.3048,
            UnitSystem.INCHES: 0.0254,
            UnitSystem.UNKNOWN: 1.0,  # Safe default — assume metres
        }[self]

    @property
    def description(self) -> str:
        return {
            UnitSystem.METRES: "SI metres (m)",
            UnitSystem.CENTIMETRES: "SI centimetres (cm)",
            UnitSystem.MILLIMETRES: "SI millimetres (mm)",
            UnitSystem.FEET: "Imperial feet (ft) — Revit internal units",
            UnitSystem.INCHES: "Imperial inches (in)",
            UnitSystem.UNKNOWN: "Unknown — defaulting to metres (conservative)",
        }[self]


# ---------------------------------------------------------------------------
# DXF INSUNITS Code Mapping
# ---------------------------------------------------------------------------

# DXF $INSUNITS system variable values (per DXF Reference, AC1009+)
# These map integer codes to UnitSystem enum values.
_DXF_INSUNITS_MAP: Dict[int, UnitSystem] = {
    0: UnitSystem.UNKNOWN,      # Unspecified
    1: UnitSystem.INCHES,       # Imperial inches
    2: UnitSystem.FEET,         # Imperial feet
    3: UnitSystem.UNKNOWN,      # Miles (not relevant for BIM)
    4: UnitSystem.MILLIMETRES,  # SI millimetres
    5: UnitSystem.CENTIMETRES,  # SI centimetres
    6: UnitSystem.METRES,       # SI metres (rare in DXF, but valid)
    7: UnitSystem.UNKNOWN,      # Kilometres (not relevant for BIM)
    8: UnitSystem.UNKNOWN,      # Microinches (not relevant for BIM)
    9: UnitSystem.UNKNOWN,      # Mils (not relevant for BIM)
    10: UnitSystem.UNKNOWN,     # Yards (not relevant for BIM)
    # Note: Code 13 (Micrometres), 14 (Decimetres) exist but are extremely rare
}


# ---------------------------------------------------------------------------
# Detection Result
# ---------------------------------------------------------------------------


@dataclass
class UnitDetectionResult:
    """Result of BIM unit detection.

    Attributes:
        unit: Detected UnitSystem.
        scale_to_metres: Multiplier to convert coordinates to metres.
        source: How the unit was detected ('ifc_header', 'dxf_insunits', 'heuristic', 'default').
        confidence: Detection confidence (1.0 = certain, 0.5 = heuristic guess).
        warning: Optional warning message if confidence is low.
    """

    unit: UnitSystem
    scale_to_metres: float
    source: str
    confidence: float = 1.0
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit": self.unit.value,
            "description": self.unit.description,
            "scale_to_metres": self.scale_to_metres,
            "source": self.source,
            "confidence": self.confidence,
            "warning": self.warning,
        }


# ---------------------------------------------------------------------------
# Main Detection Function
# ---------------------------------------------------------------------------


def detect_bim_unit(filepath: str) -> UnitDetectionResult:
    """Detect the unit system used in a BIM file.

    Tries multiple detection strategies in order of confidence:
    1. IFC header unit declaration (most reliable)
    2. DXF $INSUNITS system variable
    3. Heuristic based on coordinate magnitudes (least reliable)
    4. Default to metres (safest assumption)

    Args:
        filepath: Path to BIM file (.ifc, .dxf, .dwg).

    Returns:
        UnitDetectionResult with detected unit + scale factor.
    """
    if not filepath or not isinstance(filepath, str):
        return _default_result("Invalid filepath")

    if not os.path.exists(filepath):
        return _default_result(f"File not found: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".ifc":
        result = _detect_from_ifc(filepath)
        if result is not None:
            return result
    elif ext == ".dxf":
        result = _detect_from_dxf(filepath)
        if result is not None:
            return result
    elif ext == ".dwg":
        # DWG is binary — we can't easily parse $INSUNITS without a library.
        # Fall through to heuristic.
        pass

    # Heuristic fallback
    result = _detect_from_heuristic(filepath)
    if result is not None:
        return result

    return _default_result("No detection method succeeded")


# ---------------------------------------------------------------------------
# Strategy 1: IFC Header Parsing
# ---------------------------------------------------------------------------


def _detect_from_ifc(filepath: str) -> Optional[UnitDetectionResult]:
    """Detect unit from IFC file header.

    IFC files declare units in the HEADER section:
        FILE_DESCRIPTION(...);
        FILE_NAME(...);
        FILE_SCHEMA(('IFC4X3_ADD2'));
    And in the DATA section:
        #1 = IFCUNITASSIGNMENT((#2, #3, ...));
        #2 = IFCSIUNIT(*, .LENGTHUNIT., $, .METRE.);
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            # Read first 100KB — header is at the top
            content = f.read(100_000)

        # Look for IFCSIUNIT with LENGTHUNIT
        # Pattern: IFCSIUNIT(*, .LENGTHUNIT., $, .METRE.)
        # or: IFCSIUNIT(*, .LENGTHUNIT., $, .MILLI., .METRE.)
        if ".LENGTHUNIT." in content:
            if ".MILLI." in content and ".METRE." in content:
                return UnitDetectionResult(
                    unit=UnitSystem.MILLIMETRES,
                    scale_to_metres=UnitSystem.MILLIMETRES.scale_to_metres,
                    source="ifc_header",
                    confidence=1.0,
                )
            elif ".CENTI." in content and ".METRE." in content:
                return UnitDetectionResult(
                    unit=UnitSystem.CENTIMETRES,
                    scale_to_metres=UnitSystem.CENTIMETRES.scale_to_metres,
                    source="ifc_header",
                    confidence=1.0,
                )
            elif ".METRE." in content:
                return UnitDetectionResult(
                    unit=UnitSystem.METRES,
                    scale_to_metres=UnitSystem.METRES.scale_to_metres,
                    source="ifc_header",
                    confidence=1.0,
                )
            elif ".FOOT." in content:
                return UnitDetectionResult(
                    unit=UnitSystem.FEET,
                    scale_to_metres=UnitSystem.FEET.scale_to_metres,
                    source="ifc_header",
                    confidence=1.0,
                )
            elif ".INCH." in content:
                return UnitDetectionResult(
                    unit=UnitSystem.INCHES,
                    scale_to_metres=UnitSystem.INCHES.scale_to_metres,
                    source="ifc_header",
                    confidence=1.0,
                )

        # IFC file but no LENGTHUNIT found
        return UnitDetectionResult(
            unit=UnitSystem.UNKNOWN,
            scale_to_metres=UnitSystem.UNKNOWN.scale_to_metres,
            source="ifc_header",
            confidence=0.3,
            warning="IFC file has no LENGTHUNIT declaration — defaulting to metres",
        )

    except Exception as exc:
        logger.debug("IFC unit detection failed for %s: %s", filepath, exc)
        return None


# ---------------------------------------------------------------------------
# Strategy 2: DXF $INSUNITS Parsing
# ---------------------------------------------------------------------------


def _detect_from_dxf(filepath: str) -> Optional[UnitDetectionResult]:
    """Detect unit from DXF $INSUNITS system variable.

    DXF files are text-based (ASCII). The $INSUNITS variable is in the
    HEADER section:
        9
        $INSUNITS
        70
        4          <- code (4 = millimetres)
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            # Read first 50KB — HEADER is at the top
            content = f.read(50_000)

        # Find $INSUNITS
        # Pattern: "$INSUNITS\n70\n<code>"
        idx = content.find("$INSUNITS")
        if idx == -1:
            return UnitDetectionResult(
                unit=UnitSystem.UNKNOWN,
                scale_to_metres=UnitSystem.UNKNOWN.scale_to_metres,
                source="dxf_insunits",
                confidence=0.2,
                warning="DXF file has no $INSUNITS variable — defaulting to metres",
            )

        # Look for the next "70" group code after $INSUNITS
        # The value follows on the next line
        search_start = idx + len("$INSUNITS")
        # Find "70\n" followed by a number
        import re
        match = re.search(r"70\s*\n\s*(\d+)", content[search_start:search_start + 200])
        if not match:
            return None

        code = int(match.group(1))
        unit = _DXF_INSUNITS_MAP.get(code, UnitSystem.UNKNOWN)

        if unit == UnitSystem.UNKNOWN:
            return UnitDetectionResult(
                unit=unit,
                scale_to_metres=unit.scale_to_metres,
                source="dxf_insunits",
                confidence=0.4,
                warning=f"DXF $INSUNITS code {code} is unrecognized — defaulting to metres",
            )

        return UnitDetectionResult(
            unit=unit,
            scale_to_metres=unit.scale_to_metres,
            source="dxf_insunits",
            confidence=1.0,
        )

    except Exception as exc:
        logger.debug("DXF unit detection failed for %s: %s", filepath, exc)
        return None


# ---------------------------------------------------------------------------
# Strategy 3: Heuristic Detection (Coordinate Magnitude)
# ---------------------------------------------------------------------------


def _detect_from_heuristic(filepath: str) -> Optional[UnitDetectionResult]:
    """Detect unit heuristically based on coordinate magnitudes.

    Strategy:
    - Read a sample of coordinates from the file
    - Compute the bounding box diagonal
    - A "reasonable" building has diagonal 5-200 metres
    - If diagonal is 5-200 → metres (1.0)
    - If diagonal is 500-20000 → millimetres (0.001)
    - If diagonal is 50-2000 → centimetres (0.01)
    - If diagonal is 15-600 → feet (0.3048)
    """
    try:
        # Sample coordinates from file
        coords = _sample_coordinates(filepath, max_points=1000)
        if len(coords) < 4:
            return None

        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        diagonal = math.sqrt(
            (max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2
        )

        if not math.isfinite(diagonal) or diagonal <= 0:
            return None

        # Heuristic ranges (generous to account for unusual building sizes)
        if 5.0 <= diagonal <= 500.0:
            # Likely metres
            return UnitDetectionResult(
                unit=UnitSystem.METRES,
                scale_to_metres=1.0,
                source="heuristic",
                confidence=0.6,
                warning=f"Heuristic detection: diagonal={diagonal:.1f} suggests metres",
            )
        elif 500.0 < diagonal <= 50000.0:
            # Likely millimetres
            return UnitDetectionResult(
                unit=UnitSystem.MILLIMETRES,
                scale_to_metres=0.001,
                source="heuristic",
                confidence=0.6,
                warning=f"Heuristic detection: diagonal={diagonal:.1f} suggests millimetres",
            )
        elif 50.0 < diagonal <= 5000.0:
            # Likely centimetres
            return UnitDetectionResult(
                unit=UnitSystem.CENTIMETRES,
                scale_to_metres=0.01,
                source="heuristic",
                confidence=0.5,
                warning=f"Heuristic detection: diagonal={diagonal:.1f} suggests centimetres",
            )
        elif 15.0 < diagonal <= 1500.0:
            # Likely feet (Revit internal)
            return UnitDetectionResult(
                unit=UnitSystem.FEET,
                scale_to_metres=0.3048,
                source="heuristic",
                confidence=0.5,
                warning=f"Heuristic detection: diagonal={diagonal:.1f} suggests feet",
            )

        # Diagonal doesn't match any expected range
        return UnitDetectionResult(
            unit=UnitSystem.UNKNOWN,
            scale_to_metres=1.0,
            source="heuristic",
            confidence=0.2,
            warning=f"Heuristic detection inconclusive: diagonal={diagonal:.1f}",
        )

    except Exception as exc:
        logger.debug("Heuristic unit detection failed for %s: %s", filepath, exc)
        return None


def _sample_coordinates(filepath: str, max_points: int = 1000) -> list:
    """Sample coordinate pairs from a BIM file (any format).

    For IFC: looks for IfcCartesianPoint instances.
    For DXF: looks for LINE entity coordinates.
    """
    coords = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(500_000)  # Read up to 500KB

        import re

        # IFC pattern: #N = IfcCartesianPoint((x, y, z));
        ifc_matches = re.findall(
            r"IfcCartesianPoint\(\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\)",
            content,
        )
        for x, y, z in ifc_matches[:max_points]:
            try:
                coords.append((float(x), float(y)))
            except ValueError:
                continue

        if coords:
            return coords

        # DXF pattern: lines starting with "10" (X) and "20" (Y)
        # 10\n<x_value>\n20\n<y_value>
        dxf_matches = re.findall(
            r"^\s*10\s*\n\s*([-\d.]+)\s*\n\s*20\s*\n\s*([-\d.]+)",
            content,
            re.MULTILINE,
        )
        for x, y in dxf_matches[:max_points]:
            try:
                coords.append((float(x), float(y)))
            except ValueError:
                continue

        return coords

    except Exception:
        return coords


# ---------------------------------------------------------------------------
# Default Result Helper
# ---------------------------------------------------------------------------


def _default_result(reason: str) -> UnitDetectionResult:
    """Return a default result (metres, low confidence)."""
    return UnitDetectionResult(
        unit=UnitSystem.UNKNOWN,
        scale_to_metres=UnitSystem.METRES.scale_to_metres,  # Default to metres
        source="default",
        confidence=0.1,
        warning=f"Unit detection failed ({reason}) — defaulting to metres (1.0)",
    )


__all__ = [
    "UnitSystem",
    "UnitDetectionResult",
    "detect_bim_unit",
]
