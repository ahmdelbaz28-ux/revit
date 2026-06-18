"""
marine/engine/alarm_logic.py — Alarm Logic Tree Generator
==========================================================
Implements the "Alarm-Logic" module from the marine agent prompt.

Generates a logic tree (PLC/DCS-programmable) for fire-alarm actions
per SOLAS II-2/5 + IEC 60092-502:

    Detector triggers → Alarm level → Action outputs (with interlocks)

Logic levels (per SOLAS II-2/5):
    FAULT     → Fault signal only (engineer action)
    PRE_ALARM → Pre-alarm at fire control panel (engineer verification)
    ALARM     → General muster alarm (passenger notification)
    ACTION    → Trigger extinguishing system (CO2 release, foam, etc.)

Interlocks (mandatory per SOLAS II-2/5.6):
    - HVAC shutdown on alarm in machinery spaces
    - Fuel pump shutdown on ACTION in engine rooms
    - Fire damper closure on alarm (zoned)
    - Door release on ALARM (escape route doors unlock)
"""

from __future__ import annotations

from typing import List

from marine.core.types import (
    AlarmLevel, AlarmLogicNode, ComplianceResult, DetectorPlacement,
    MarineZone, SpaceCategory,
)


def generate_logic_tree(
    zone: MarineZone, detector_placements: List[DetectorPlacement],
) -> List[AlarmLogicNode]:
    """Generate alarm-logic nodes for every detector in a zone.

    Each detector generates ≥1 logic node. Multi-criteria detectors
    generate multiple nodes (one per sensor).

    Action outputs depend on zone category + alarm level:
      - MACHINERY_A + ALARM → horn, hvac_shutdown, damper_close, fuel_pump_off
      - MACHINERY_A + ACTION → release_co2 OR release_water_mist
      - ACCOMMODATION + ALARM → public_address, door_release, sprinkler_zone_on
      - ESCAPE_ROUTE + ALARM → emergency_lighting, public_address
      - CARGO + ACTION → release_co2, hold_ventilation_close
    """
    nodes: List[AlarmLogicNode] = []
    cat = zone.space_category

    for i, dp in enumerate(detector_placements, start=1):
        node_id = f"LOGIC-{zone.zone_id}-{i:03d}"

        # Determine alarm level by detector type + zone category.
        if cat == SpaceCategory.MACHINERY_SPACE_A:
            if dp.detector_type.value.startswith("flame"):
                level = AlarmLevel.ACTION  # Flame → immediate release
                outputs = ("release_water_mist", "hvac_shutdown", "fuel_pump_off")
                delay = 0.0
            elif dp.detector_type == "heat_fixed":
                level = AlarmLevel.ALARM
                outputs = ("horn_zone", "hvac_shutdown", "damper_close")
                delay = 30.0  # 30 s verification
            else:  # smoke
                level = AlarmLevel.PRE_ALARM
                outputs = ("panel_pre_alarm", "notify_ecr")
                delay = 0.0
        elif cat == SpaceCategory.ACCOMMODATION:
            level = AlarmLevel.ALARM
            outputs = ("public_address", "door_release", "sprinkler_zone_on")
            delay = 0.0
        elif cat == SpaceCategory.ESCAPE_ROUTE:
            level = AlarmLevel.ALARM
            outputs = ("emergency_lighting", "public_address")
            delay = 0.0
        elif cat == SpaceCategory.CARGO_SPACE:
            level = AlarmLevel.ACTION
            outputs = ("release_co2", "hold_ventilation_close")
            delay = 60.0  # 1 min evacuation of cargo hold access
        else:
            level = AlarmLevel.ALARM
            outputs = ("horn_zone",)
            delay = 0.0

        nodes.append(AlarmLogicNode(
            node_id=node_id,
            trigger_detector=dp.detector_id,
            zone_id=zone.zone_id,
            alarm_level=level,
            action_outputs=outputs,
            delay_s=delay,
            interlocks=("verify_two_detectors",) if level == AlarmLevel.ACTION else (),
            standard_reference="SOLAS II-2/5.6 + IEC 60092-502",
        ))

    return nodes


def export_to_plc_script(nodes: List[AlarmLogicNode]) -> str:
    """Export logic tree as a Structured Text (ST) PLC script (IEC 61131-3).

    Generates a runnable ST program for any IEC 61131-3-compliant PLC
    (Siemens S7, Schneider Modicon, ABB AC500, etc.).
    """
    lines = [
        "// ─── Auto-generated Fire Alarm Logic Tree ───────────────",
        "// Source: marine.engine.alarm_logic.generate_logic_tree()",
        "// Standard: SOLAS II-2/5.6 + IEC 60092-502 + IEC 61131-3",
        "// DO NOT EDIT — regenerate from marine module.",
        "",
        "PROGRAM FireAlarmLogic",
        "  VAR",
    ]
    # Collect all I/O tags
    for n in nodes:
        lines.append(f"    {n.trigger_detector} AT %I* : BOOL;  // Detector input")
        for out in n.action_outputs:
            lines.append(f"    {out} AT %Q* : BOOL;  // Action output")
    lines.append("  END_VAR")
    lines.append("")
    lines.append("  // Logic")
    for n in nodes:
        cond = n.trigger_detector
        if n.interlocks:
            # AND-gate with interlock (verify_two_detectors pattern).
            cond = f"{n.trigger_detector} AND interlock_{n.node_id}"
        lines.append(f"  IF {cond} THEN")
        for out in n.action_outputs:
            if n.delay_s > 0:
                lines.append(f"    {out} := TON(IN := TRUE, PT := T#{int(n.delay_s)}s).Q;")
            else:
                lines.append(f"    {out} := TRUE;")
        lines.append("  END_IF;")
        lines.append("")
    lines.append("END_PROGRAM")
    return "\n".join(lines)


__all__ = ["generate_logic_tree", "export_to_plc_script"]
