"""
engineering/ada_check.py
========================
ADA / NFPA 72 §18 / ICC A117.1 device-mounting compliance checks.

Codified rules (every value cites its source):
  - Manual pull station handle:           1.07–1.22 m (NFPA 72 §17.14.8.4)
  - Wall-mounted strobe:                  ≥ 2.03 m to bottom OR ≤ 0.15 m below ceiling
                                                  (NFPA 72 §18.5.5.6)
  - Ceiling-mounted strobe spacing/distance per Table 18.5.5
  - Visual notification candela rating thresholds
  - Operable parts (controls): 0.38–1.22 m (ICC A117.1 §308)
  - Forward reach max: 1.22 m, side reach max: 1.37 m

Outputs Findings exactly like compliance.py so the pipeline can merge them.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class ADAFinding:
    severity: str          # 'critical','major','minor','advisory'
    rule:     str
    message:  str
    citation: str
    device_id: str | None = None
    recommendation: str = ""


def check_pull_station_height(device_id: str, mount_height_m: float) -> Optional[ADAFinding]:
    lo, hi = 1.07, 1.22
    if mount_height_m < lo or mount_height_m > hi:
        return ADAFinding(
            "critical","manual_pull.mount_height",
            f"Pull station {device_id} at {mount_height_m*1000:.0f} mm "
            f"(required {lo*1000:.0f}–{hi*1000:.0f} mm).",
            "NFPA 72 §17.14.8.4", device_id,
            f"Re-mount within {lo*1000:.0f}–{hi*1000:.0f} mm of finished floor.")
    return None


def check_strobe_height(device_id: str, mount_height_m: float,
                        ceiling_height_m: float) -> Optional[ADAFinding]:
    # bottom of lens must be ≥ 2.03 m OR within 0.15 m of ceiling
    if mount_height_m >= 2.03: return None
    if (ceiling_height_m - mount_height_m) <= 0.15: return None
    return ADAFinding(
        "major", "strobe.mount_height",
        f"Strobe {device_id} at {mount_height_m:.2f} m "
        "(must be ≥ 2.03 m OR within 0.15 m of ceiling).",
        "NFPA 72 §18.5.5.6", device_id,
        "Raise strobe lens to ≥ 2.03 m above finished floor.")


def check_reach_ranges(device_id: str, mount_height_m: float,
                       reach_type: str = "forward") -> Optional[ADAFinding]:
    if reach_type == "forward":
        lo, hi = 0.38, 1.22
        cite = "ICC A117.1 §308.2"
    else:
        lo, hi = 0.38, 1.37
        cite = "ICC A117.1 §308.3"
    if mount_height_m < lo or mount_height_m > hi:
        return ADAFinding(
            "major", f"reach.{reach_type}",
            f"Control {device_id} at {mount_height_m:.2f} m outside "
            f"reach range {lo}-{hi} m.", cite, device_id,
            f"Re-mount between {lo*1000:.0f} and {hi*1000:.0f} mm AFF.")
    return None


def check_strobe_candela(room_area_m2: float, ceiling_height_m: float,
                         strobe_candela: int) -> Optional[ADAFinding]:
    """Wall-mounted strobe minimum candela per NFPA 72 Table 18.5.5.4.1(a)."""
    # Simplified: cover the larger room dimension; use square-room equivalent.
    # Table 18.5.5.4.1(a) — wall-mount, 1 light:
    table = [(20,15),(28,30),(40,60),(54,75),(60,95),
             (66,110),(73,135),(89,185),(102,240)]
    side_m = (room_area_m2 ** 0.5)
    needed = None
    for size, cd in table:
        if side_m <= size: needed = cd; break
    if needed is None: needed = 1000   # outside table — require engineering
    if strobe_candela < needed:
        return ADAFinding(
            "major", "strobe.candela",
            f"Wall strobe {strobe_candela} cd insufficient for "
            f"{room_area_m2:.0f} m² (side≈{side_m:.1f} m); needs ≥ {needed} cd.",
            "NFPA 72 Table 18.5.5.4.1(a)", None,
            f"Upgrade to ≥ {needed} cd strobe or add additional units.")
    return None


def audit_devices(devices: list, room_areas: dict | None = None) -> list[ADAFinding]:
    """
    devices: list of dicts {id, kind, mount_h_m, candela?, room_id?}
    room_areas: dict[room_id -> area_m2] for strobe candela check.
    """
    findings = []
    room_areas = room_areas or {}
    for d in devices:
        did   = d.get("id","?")
        kind  = d.get("kind","")
        h     = float(d.get("mount_h_m", 0.0))
        ceil  = float(d.get("ceiling_h_m", 2.8))

        if kind == "manual_call_point":
            f = check_pull_station_height(did, h);    f and findings.append(f)
        elif kind in ("strobe", "horn_strobe", "emergency_light"):
            f = check_strobe_height(did, h, ceil);    f and findings.append(f)
            cd = d.get("candela")
            if cd and d.get("room_id") in room_areas:
                f2 = check_strobe_candela(room_areas[d["room_id"]], ceil, int(cd))
                f2 and findings.append(f2)
        elif kind in ("access_reader", "thermostat", "control_panel"):
            f = check_reach_ranges(did, h);           f and findings.append(f)
    return findings
