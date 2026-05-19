"""
core/ifc_utils.py
===================
IFC utility functions for FireAI — GUID generation, validation,
and STEP serialization helpers.

Implements the buildingSMART Compressed GUID format per the IFC
specification. This is a Base64-variant encoding of a UUID that
produces a 22-character fixed-length string, used throughout IFC
for globally unique identifiers.

Usage:
    from core.ifc_utils import generate_ifc_guid, is_valid_ifc_guid

    guid = generate_ifc_guid()     # e.g. "3xP$y0H5fBvA8qRm1NwZ$L"
    is_valid_ifc_guid(guid)        # True
"""

from __future__ import annotations

import logging
import struct
import uuid
from typing import Optional

from core.production_config import get_production_config

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# buildingSMART Compressed GUID
# ════════════════════════════════════════════════════════════════════════════
#
# The buildingSMART Compressed GUID is a 22-character Base64 variant
# encoding of a 128-bit UUID. It uses a custom alphabet:
#   0-9, A-Z, a-z, $, _
# (replacing + and / from standard Base64)
#
# This is the standard format for IfcGloballyUniqueId in IFC2x3 and IFC4.

# Custom Base64 alphabet per buildingSMART
_B64_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"


def _uuid_to_compressed_bytes(u: uuid.UUID) -> bytes:
    """Convert UUID to 16-byte big-endian representation."""
    return u.bytes


def _encode_base64_variant(data: bytes) -> str:
    """
    Encode 16 bytes using the buildingSMART Base64 variant.

    Produces exactly 22 characters (128 bits / 6 bits per char = 21.33,
    padded to 22 with trailing zero bits).
    """
    # Convert bytes to a single 128-bit integer
    value = int.from_bytes(data, byteorder='big')

    # Encode using custom charset, 22 characters
    chars = []
    for _ in range(22):
        chars.append(_B64_CHARSET[value & 0x3F])
        value >>= 6

    # The encoding is LSB-first, so reverse
    return ''.join(reversed(chars))


def _decode_base64_variant(guid_str: str) -> bytes:
    """
    Decode a buildingSMART Base64 variant GUID back to 16 bytes.

    Returns None if the string is invalid.
    """
    if len(guid_str) != 22:
        return None

    # Build reverse lookup
    lookup = {c: i for i, c in enumerate(_B64_CHARSET)}

    value = 0
    for ch in guid_str:
        if ch not in lookup:
            return None
        value = (value << 6) | lookup[ch]

    # Extract 128 bits
    return value.to_bytes(16, byteorder='big')


def generate_ifc_guid() -> str:
    """
    Generate a buildingSMART Compressed GUID.

    This is a 22-character string encoding a random UUID (version 4)
    using the IFC Base64 variant alphabet.

    Returns
    -------
    str
        A valid 22-character IFC GUID.

    Example
    -------
    >>> guid = generate_ifc_guid()
    >>> len(guid)
    22
    >>> is_valid_ifc_guid(guid)
    True
    """
    u = uuid.uuid4()
    data = _uuid_to_compressed_bytes(u)
    return _encode_base64_variant(data)


def is_valid_ifc_guid(guid_str: str) -> bool:
    """
    Validate a buildingSMART Compressed GUID.

    Checks:
      - Length is exactly 22 characters
      - All characters are in the IFC Base64 alphabet

    Parameters
    ----------
    guid_str : str
        The GUID string to validate.

    Returns
    -------
    bool
        True if valid, False otherwise.
    """
    cfg = get_production_config()

    if not isinstance(guid_str, str):
        return False

    if len(guid_str) != cfg.ifc_guid_length:
        return False

    valid_chars = set(cfg.ifc_guid_charset)
    return all(c in valid_chars for c in guid_str)


def generate_ifc_guid_deterministic(seed_string: str) -> str:
    """
    Generate a deterministic IFC GUID from a seed string.

    Uses UUID5 (SHA-1 namespace) to produce a reproducible GUID
    for the same input. Useful for testing and for ensuring
    consistent GUIDs across re-runs.

    Parameters
    ----------
    seed_string : str
        Seed string for deterministic generation.

    Returns
    -------
    str
        A 22-character deterministic IFC GUID.
    """
    namespace = uuid.NAMESPACE_DNS
    u = uuid.uuid5(namespace, seed_string)
    data = _uuid_to_compressed_bytes(u)
    return _encode_base64_variant(data)


# ════════════════════════════════════════════════════════════════════════════
# STEP Serialization Helpers
# ════════════════════════════════════════════════════════════════════════════

def step_header(schema: str = "IFC4",
                organization: str = None,
                application: str = None,
                version: str = None) -> str:
    """
    Generate a STEP file header for IFC serialization.

    Parameters
    ----------
    schema : str
        IFC schema version (default: IFC4).
    organization : str, optional
        Organization name.
    application : str, optional
        Application name.
    version : str, optional
        Application version.

    Returns
    -------
    str
        Complete STEP header section.
    """
    cfg = get_production_config()
    ifc_cfg = cfg.ifc_step_header

    org = organization or ifc_cfg["organization"]
    app = application or ifc_cfg["application"]
    ver = version or ifc_cfg["version"]

    return f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('fireai_export.ifc','{org}','{org}'),('{app}'),'','','');
FILE_SCHEMA(('{schema}'));
ENDSEC;

DATA;
"""


def step_footer() -> str:
    """Generate STEP file footer."""
    return "ENDSEC;\n\nEND-ISO-10303-21;\n"


def step_entity(entity_id: int, entity_type: str, params: list) -> str:
    """
    Generate a STEP entity line.

    Parameters
    ----------
    entity_id : int
        STEP entity ID (#1, #2, ...).
    entity_type : str
        IFC entity type name.
    params : list
        List of parameter values (auto-quoted for strings).

    Returns
    -------
    str
        STEP entity line like: #1=IFCPROJECT(...);
    """
    parts = []
    for p in params:
        if p is None:
            parts.append("$")
        elif isinstance(p, str):
            parts.append(f"'{p}'")
        elif isinstance(p, bool):
            parts.append(".T." if p else ".F.")
        elif isinstance(p, float):
            # Avoid trailing .0 for integers
            if p == int(p):
                parts.append(str(int(p)))
            else:
                parts.append(f"{p:.10g}")
        elif isinstance(p, int):
            parts.append(str(p))
        elif isinstance(p, list):
            # Reference list: (#1,#2,#3)
            parts.append("(" + ",".join(str(x) for x in p) + ")")
        else:
            parts.append(str(p))

    return f"#{entity_id}={entity_type}({','.join(parts)});"


# ════════════════════════════════════════════════════════════════════════════
# IFC Entity Type Helpers
# ════════════════════════════════════════════════════════════════════════════

# FireAI device type → IFC4 entity mapping
DEVICE_TO_IFC = {
    "SMOKE_PHOTOELECTRIC":  ("IfcSensor",        "SMOKESENSOR"),
    "SMOKE_IONIZATION":     ("IfcSensor",        "SMOKESENSOR"),
    "SMOKE_MULTI_CRITERIA": ("IfcSensor",        "MULTISENSOR"),
    "HEAT_FIXED":           ("IfcSensor",        "HEATSENSOR"),
    "HEAT_RATE_OF_RISE":    ("IfcSensor",        "HEATSENSOR"),
    "DUCT_SMOKE":           ("IfcSensor",        "SMOKESENSOR"),
    "MANUAL_PULL_STATION":  ("IfcSwitchingDevice","SWITCH"),
    "STROBE":               ("IfcActuator",      "USERDEFINED"),
    "HORN":                 ("IfcActuator",      "USERDEFINED"),
    "HORN_STROBE":          ("IfcActuator",      "USERDEFINED"),
    "FIRE_ALARM_PANEL":     ("IfcController",    "FIREALARM"),
}


def device_to_ifc_type(device_type: str) -> tuple:
    """
    Map a FireAI device type to IFC4 entity type and predefined type.

    Parameters
    ----------
    device_type : str
        FireAI device type string.

    Returns
    -------
    tuple
        (ifc_entity_type, predefined_type) or ("IfcSensor", "USERDEFINED").
    """
    return DEVICE_TO_IFC.get(device_type, ("IfcSensor", "USERDEFINED"))


# ════════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════════

def _self_test():
    """Run self-test for IFC utilities."""
    print("=" * 60)
    print("IFC Utilities — Self-Test")
    print("=" * 60)

    # ── GUID Generation ──
    guid = generate_ifc_guid()
    print(f"  Generated GUID: {guid}")
    assert len(guid) == 22, f"GUID length should be 22, got {len(guid)}"
    print("  [PASS] GUID length is 22")

    # ── GUID Validation ──
    assert is_valid_ifc_guid(guid), "Generated GUID should be valid"
    print("  [PASS] Generated GUID validates")

    assert not is_valid_ifc_guid(""), "Empty string should be invalid"
    assert not is_valid_ifc_guid("short"), "Short string should be invalid"
    assert not is_valid_ifc_guid("@" * 22), "Invalid chars should fail"
    assert not is_valid_ifc_guid(None), "None should be invalid"
    print("  [PASS] Invalid GUIDs correctly rejected")

    # ── GUID Uniqueness ──
    guids = {generate_ifc_guid() for _ in range(1000)}
    assert len(guids) == 1000, "All GUIDs should be unique"
    print("  [PASS] 1000 GUIDs are all unique")

    # ── Deterministic GUID ──
    g1 = generate_ifc_guid_deterministic("test_room_1")
    g2 = generate_ifc_guid_deterministic("test_room_1")
    g3 = generate_ifc_guid_deterministic("test_room_2")
    assert g1 == g2, "Same seed should produce same GUID"
    assert g1 != g3, "Different seed should produce different GUID"
    assert is_valid_ifc_guid(g1), "Deterministic GUID should be valid"
    print("  [PASS] Deterministic GUID generation")

    # ── GUID Roundtrip ──
    original = uuid.uuid4()
    data = original.bytes
    encoded = _encode_base64_variant(data)
    decoded = _decode_base64_variant(encoded)
    assert decoded == data, "Roundtrip encode/decode failed"
    print("  [PASS] GUID encode/decode roundtrip")

    # ── STEP Header ──
    header = step_header()
    assert "ISO-10303-21" in header
    assert "IFC4" in header
    assert "FireAI" in header
    print("  [PASS] STEP header generation")

    # ── STEP Entity ──
    entity = step_entity(1, "IFCPROJECT", ["proj_guid", "Test Project", None, "$", "#2", "#3"])
    assert entity.startswith("#1=IFCPROJECT(")
    assert entity.endswith(");")
    print(f"  STEP entity: {entity}")
    print("  [PASS] STEP entity generation")

    # ── Device type mapping ──
    ifc_type, predef = device_to_ifc_type("SMOKE_PHOTOELECTRIC")
    assert ifc_type == "IfcSensor", f"Expected IfcSensor, got {ifc_type}"
    assert predef == "SMOKESENSOR", f"Expected SMOKESENSOR, got {predef}"
    print("  [PASS] Device type mapping")

    ifc_type2, predef2 = device_to_ifc_type("UNKNOWN_TYPE")
    assert ifc_type2 == "IfcSensor", "Unknown device should default to IfcSensor"
    print("  [PASS] Unknown device type defaults")

    print("\n" + "=" * 60)
    print("IFC Utilities Self-Test: PASS")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
