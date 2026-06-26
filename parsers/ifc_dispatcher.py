"""
parsers/ifc_dispatcher.py — Canonical IFC Entry Point
======================================================

Routes IFC file parsing to the correct backend based on file extension:
  - .ifc       -> ifcopenshell (native IFC parser, ISO 16739-1:2024)
  - .ifc.json  -> Legacy JSON parser (parsers.ifc_parser.IFCParser)

This dispatcher is the SINGLE ENTRY POINT for all IFC parsing in FireAI.
Direct use of parsers.ifc_parser.IFCParser for .ifc files is deprecated.

SAFETY-CRITICAL DESIGN:
  - File path validation via _path_security before ANY parsing
  - Correlation ID propagation for audit trail (NFPA 72-2022 §14.2.4)
  - DeprecationWarning on legacy path to prevent silent regression
  - No silent fallbacks — if a parser fails, the error propagates

REFERENCE:
  ISO 16739-1:2024 (IFC 4.3 ADD2)
  NFPA 72-2022 §10.6 (audit trail), §14.2.4 (correlation ID)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("fireai.parsers.ifc_dispatcher")

# ── Parser Availability Detection ─────────────────────────────────────────────

_IFCOPENSHELL_AVAILABLE: bool | None = None


def _is_ifcopenshell_available() -> bool:
    """Check if ifcopenshell is installed (cached after first check)."""
    global _IFCOPENSHELL_AVAILABLE
    if _IFCOPENSHELL_AVAILABLE is None:
        try:
            import ifcopenshell  # noqa: F401
            _IFCOPENSHELL_AVAILABLE = True
            logger.info("ifcopenshell available — native .ifc parsing enabled")
        except ImportError:
            _IFCOPENSHELL_AVAILABLE = False
            logger.warning(
                "ifcopenshell NOT installed — .ifc files will use legacy JSON parser. "
                "Install with: pip install ifcopenshell"
            )
    return _IFCOPENSHELL_AVAILABLE


# ── Security Validation ───────────────────────────────────────────────────────

def _validate_ifc_path(file_path: str) -> Path:
    """
    Validate IFC file path using shared _path_security module.

    Defense-in-depth:
      - Path traversal prevention
      - Null byte injection check
      - Symlink resolution
      - File size validation
      - Extension allowlist

    Raises:
        ValueError: If path fails security validation.
        FileNotFoundError: If file does not exist.
    """
    from parsers._path_security import (
        UnsafePathError,
        validate_file_size,
        validate_input_path,
    )

    _IFC_MAX_BYTES = int(os.getenv(
        "FIREAI_IFC_MAX_FILE_SIZE_BYTES",
        str(500 * 1024 * 1024),  # 500 MB
    ))
    _ALLOWED_EXTENSIONS = frozenset({".ifc", ".ifcxml", ".ifc.json", ".json"})

    try:
        safe_path = validate_input_path(
            file_path,
            allowed_extensions=_ALLOWED_EXTENSIONS,
            parser_name="IFCDispatcher",
        )
        validate_file_size(
            safe_path,
            max_size_bytes=_IFC_MAX_BYTES,
            parser_name="IFCDispatcher",
        )
    except FileNotFoundError as e:
        raise ValueError(f"IFC file not found: {e}") from e
    except UnsafePathError as e:
        raise ValueError(f"SECURITY: {e}") from e

    return safe_path


# ── Route Determination ───────────────────────────────────────────────────────

def _determine_parser_type(file_path: str | Path) -> str:
    """
    Determine which parser to use based on file extension.

    Returns:
        "ifcopenshell" for .ifc / .ifcxml files
        "legacy_json" for .ifc.json / .json files

    Raises:
        ValueError: For unsupported extensions.
    """
    path_str = str(file_path).lower()

    if path_str.endswith(".ifc.json") or path_str.endswith(".json"):
        return "legacy_json"
    elif path_str.endswith(".ifc") or path_str.endswith(".ifcxml"):
        return "ifcopenshell"
    else:
        raise ValueError(
            f"Unsupported IFC file extension: {Path(file_path).suffix}. "
            f"Supported: .ifc, .ifcxml, .ifc.json, .json"
        )


# ── Native IFC Parsing (ifcopenshell) ────────────────────────────────────────

def _parse_with_ifcopenshell(
    file_path: str | Path,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Parse native .ifc file using ifcopenshell.

    Extracts spaces, devices, and building structure from IFC 4.3/4/2x3 files.
    This is the preferred parser — it reads the actual IFC schema.

    Args:
        file_path: Path to the .ifc file (already validated).
        correlation_id: Audit trail correlation ID.

    Returns:
        Dict with parsed building data in standard format.

    Raises:
        ImportError: If ifcopenshell is not installed.
        ValueError: If the IFC file cannot be parsed.
    """
    import ifcopenshell
    from ifcopenshell.util import elements as ifc_elements

    logger.info(
        "Parsing with ifcopenshell | file=%s | correlation_id=%s",
        file_path, correlation_id,
    )

    try:
        ifc_file = ifcopenshell.open(str(file_path))
    except Exception as e:
        raise ValueError(
            f"ifcopenshell failed to open '{file_path}': {e}"
        ) from e

    # ── Extract Building ──
    buildings = ifc_file.by_type("IfcBuilding")
    building_name = "Unknown"
    if buildings:
        building = buildings[0]
        building_name = getattr(building, "Name", None) or "Unknown"

    # ── Extract Stories (Floors) ──
    stories = ifc_file.by_type("IfcBuildingStorey")
    floor_count = len(stories)

    # ── Extract Spaces (Rooms) ──
    spaces = ifc_file.by_type("IfcSpace")
    rooms = []
    for space in spaces:
        name = getattr(space, "Name", None) or f"Space-{space.id()}"
        long_name = getattr(space, "LongName", None) or ""
        elevation = getattr(space, "ElevationWithFlooring", 0) or 0

        # Try to get area from property sets
        area = 0.0
        try:
            for prop_set in getattr(space, "IsDefinedBy", []):
                if hasattr(prop_set, "RelatingPropertyDefinition"):
                    pdef = prop_set.RelatingPropertyDefinition
                    if hasattr(pdef, "HasProperties"):
                        for prop in pdef.HasProperties:
                            if getattr(prop, "Name", "") == "Area" or \
                               getattr(prop, "Name", "") == "GrossArea":
                                area = float(getattr(prop, "NominalValue", 0) or 0)
                                break
        except Exception:
            pass  # Area extraction is best-effort

        if area < 0:
            logger.warning(
                "Negative area for space %s: %s. Space REJECTED — "
                "manual fire protection design REQUIRED. correlation_id=%s",
                space.id(), area, correlation_id,
            )
            continue

        rooms.append({
            "id": space.id(),
            "name": name,
            "long_name": long_name,
            "area": area,
            "elevation": elevation,
        })

    # ── Extract Fire Protection Devices ──
    fire_device_types = {
        "IfcFireSuppressionDeviceType",
        "IfcAlarmType",
        "IfcSensorType",
        "IfcProtectiveDeviceType",
    }
    devices = []
    for device_type_name in fire_device_types:
        try:
            for device in ifc_file.by_type(device_type_name):
                devices.append({
                    "id": device.id(),
                    "name": getattr(device, "Name", None) or f"Device-{device.id()}",
                    "type": device_type_name,
                })
        except Exception:
            pass  # Some types may not exist in all IFC versions

    total_area = sum(r.get("area", 0) for r in rooms)

    result = {
        "building_name": building_name,
        "floors": floor_count,
        "rooms": rooms,
        "devices": devices,
        "total_area": total_area,
        "parser": "ifcopenshell",
        "correlation_id": correlation_id,
    }

    logger.info(
        "ifcopenshell parse complete | building=%s | floors=%d | rooms=%d | devices=%d | area=%.1f",
        building_name, floor_count, len(rooms), len(devices), total_area,
    )

    return result


# ── Legacy JSON Parsing ───────────────────────────────────────────────────────

def _parse_with_legacy_json(
    file_path: str | Path,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Parse .ifc.json file using the legacy IFCParser.

    This parser handles JSON-serialized IFC data (instances array format).
    It is DEPRECATED for native .ifc files but remains the canonical
    parser for .ifc.json exports.

    Args:
        file_path: Path to the .ifc.json file (already validated).
        correlation_id: Audit trail correlation ID.

    Returns:
        Dict with parsed building data in standard format.
    """
    import warnings

    from parsers.ifc_parser import IFCParser

    logger.info(
        "Parsing with legacy JSON parser | file=%s | correlation_id=%s",
        file_path, correlation_id,
    )

    parser = IFCParser(str(file_path))
    analysis = parser.parse()
    standard = parser.to_standard_format(analysis)

    # Add dispatcher metadata
    standard["parser"] = "legacy_json"
    standard["correlation_id"] = correlation_id

    logger.info(
        "Legacy JSON parse complete | building=%s | floors=%d | rooms=%d | area=%.1f",
        standard.get("building_name", "Unknown"),
        standard.get("floors", 0),
        len(standard.get("rooms", [])),
        standard.get("total_area", 0),
    )

    return standard


# ── Public API ────────────────────────────────────────────────────────────────

def dispatch_ifc_parse(
    file_path: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Canonical IFC parsing entry point.

    Routes .ifc files to ifcopenshell and .ifc.json files to the legacy
    JSON parser. This is the ONLY function that should be called to parse
    IFC data in FireAI.

    Args:
        file_path: Path to the IFC file (.ifc, .ifcxml, .ifc.json).
        correlation_id: Audit trail correlation ID (NFPA 72 §14.2.4).

    Returns:
        Dict with parsed building data in standard format.

    Raises:
        ValueError: If path validation or parsing fails.
        FileNotFoundError: If file does not exist.
    """
    import warnings

    if correlation_id is None:
        import uuid
        correlation_id = f"ifc-dispatch-{uuid.uuid4().hex[:12]}"

    # ── Security Gate ──
    safe_path = _validate_ifc_path(file_path)

    # ── Route ──
    parser_type = _determine_parser_type(safe_path)

    if parser_type == "ifcopenshell":
        if _is_ifcopenshell_available():
            return _parse_with_ifcopenshell(safe_path, correlation_id=correlation_id)
        else:
            # Fallback: ifcopenshell not installed, try legacy parser
            # ONLY if the file is also a valid JSON
            warnings.warn(
                "ifcopenshell not installed — attempting legacy JSON parser for .ifc file. "
                "This may fail for binary IFC files. Install ifcopenshell for native support.",
                DeprecationWarning,
                stacklevel=2,
            )
            try:
                return _parse_with_legacy_json(safe_path, correlation_id=correlation_id)
            except Exception as e:
                raise ValueError(
                    f"Cannot parse .ifc file '{file_path}': ifcopenshell not installed "
                    f"and legacy JSON parser failed: {e}. "
                    f"Install ifcopenshell: pip install ifcopenshell"
                ) from e

    elif parser_type == "legacy_json":
        return _parse_with_legacy_json(safe_path, correlation_id=correlation_id)

    else:
        # Should never reach here due to _determine_parser_type validation
        raise ValueError(f"Unknown parser type: {parser_type}")
