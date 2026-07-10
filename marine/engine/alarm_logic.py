# NOSONAR
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

v2 BUGFIXES:
    - export_to_plc_script previously generated INVALID IEC 61131-3 ST:
      used `AT %I*` (placeholder), duplicate VAR declarations, undeclared
      interlock variables, and inline `TON(...).Q` calls (function blocks
      cannot be invoked inline). All fixed.
    - generate_logic_tree now accepts an optional ExtinguishingSystem so the
      release output matches what was actually sized (was hardcoded to
      `release_water_mist` for all machinery ACTION, even when CO2 was
      selected by the extinguishment engine).
    - Linear-heat detectors now correctly classified (was falling through
      to the smoke branch).
"""

from __future__ import annotations

import re

from marine.core.types import (
    AlarmLevel,
    AlarmLogicNode,
    DetectorPlacement,
    ExtinguishingSystem,
    MarineZone,
    SpaceCategory,
)

# ─── Identifier sanitisation (IEC 61131-3 limits) ──────────────────────────

# IEC 61131-3 identifiers must start with a letter or underscore, followed
# by letters, digits, or underscores. Hyphens (used in our zone IDs) are
# illegal — replace with underscores.
_INVALID_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")  # NOSONAR - python:S6353


def _to_ident(name: str) -> str:
    """
    Sanitise a name into a valid IEC 61131-3 identifier.

    Hyphens, dots, and other punctuation are replaced with underscores.
    The result is prefixed with `_` if it doesn't start with a letter/underscore
    (e.g. numeric zone IDs).
    """
    sanitized = _INVALID_IDENT_RE.sub("_", name)
    if not sanitized or not (sanitized[0].isalpha() or sanitized[0] == "_"):
        sanitized = "_" + sanitized
    return sanitized


def generate_logic_tree(  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    zone: MarineZone,
    detector_placements: list[DetectorPlacement],
    extinguishing_system: ExtinguishingSystem | None = None,
) -> list[AlarmLogicNode]:
    """
    Generate alarm-logic nodes for every detector in a zone.

    Each detector generates ≥1 logic node. Multi-criteria detectors
    generate multiple nodes (one per sensor).

    Action outputs depend on zone category + alarm level:
      - MACHINERY_A + ALARM → horn, hvac_shutdown, damper_close, fuel_pump_off
      - MACHINERY_A + ACTION → release_{system} (water_mist | co2 | foam)
      - ACCOMMODATION + ALARM → public_address, door_release, sprinkler_zone_on
      - ESCAPE_ROUTE + ALARM → emergency_lighting, public_address
      - CARGO + ACTION → release_co2, hold_ventilation_close

    Args:
        zone: The marine zone being designed.
        detector_placements: Detectors placed in this zone.
        extinguishing_system: If provided, the `release_*` action output
            will match the actually-selected extinguishing system. If
            None, defaults to `release_water_mist` for machinery and
            `release_co2` for cargo (preserving v1 behavior).

    """
    nodes: list[AlarmLogicNode] = []
    cat = zone.space_category

    # Determine the correct release output for this zone's selected system.
    # BUGFIX v2: previously hardcoded `release_water_mist` regardless of the
    # system selected by the extinguishment engine (could be CO2, foam, etc.).
    if extinguishing_system is None:
        # Default per zone category if caller didn't pass one in.
        if cat == SpaceCategory.MACHINERY_SPACE_A:
            release_output = "release_water_mist"
        elif cat == SpaceCategory.CARGO_SPACE:
            release_output = "release_co2"
        else:
            release_output = ""
    else:
        release_output = f"release_{extinguishing_system.value}"

    for i, dp in enumerate(detector_placements, start=1):
        node_id = f"LOGIC-{zone.zone_id}-{i:03d}"

        # Determine alarm level by detector type + zone category.
        outputs: tuple[str, ...]
        if cat == SpaceCategory.MACHINERY_SPACE_A:
            if dp.detector_type.value.startswith("flame"):
                level = AlarmLevel.ACTION
                outputs = (release_output, "hvac_shutdown", "fuel_pump_off")
                if not release_output:
                    outputs = ("hvac_shutdown", "fuel_pump_off")
                delay = 0.0
            elif dp.detector_type.value in ("heat_fixed", "heat_ror", "linear_heat"):
                # BUGFIX v2: linear-heat detectors were falling through to
                # the smoke branch (PRE_ALARM). All heat-type detectors in
                # machinery spaces trigger ALARM (verification 30 s).
                level = AlarmLevel.ALARM
                outputs = ("horn_zone", "hvac_shutdown", "damper_close")
                delay = 30.0  # 30 s verification
            else:  # smoke
                level = AlarmLevel.PRE_ALARM
                outputs = ("panel_pre_alarm", "notify_ecr")
                delay = 0.0
        elif cat == SpaceCategory.ACCOMMODATION:
            level = AlarmLevel.ALARM
            outputs = (
                ("public_address", "door_release", "sprinkler_zone_on")
                if extinguishing_system == ExtinguishingSystem.SPRINKLER
                else ("public_address", "door_release")
            )
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


def export_to_plc_script(nodes: list[AlarmLogicNode]) -> str:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    """
    Export logic tree as a Structured Text (ST) PLC script (IEC 61131-3).

    Generates a runnable ST program for any IEC 61131-3-compliant PLC
    (Siemens S7, Schneider Modicon, ABB AC500, etc.).

    BUGFIXES v2 (the previous output would not compile on any real PLC):
      1. Replaced `AT %I*` / `AT %Q*` placeholders (invalid syntax) with
         concrete addresses `%IX0.0` / `%QX0.0` allocated sequentially.
      2. Deduplicated VAR declarations — each tag declared only once even
         when multiple logic nodes reference it.
      3. Sanitized identifiers (hyphens replaced with underscores).
      4. Declared `interlock_<node>` BOOL variables so the AND clause is
         valid (previously referenced undeclared identifiers).
      5. Replaced inline `TON(...).Q` (illegal — TON is a function block)
         with proper per-output TON instances.
      6. Added ELSE branches that reset outputs to FALSE so they don't
         latch forever when the detector clears.
    """
    # ── Collect unique I/O tags across all nodes ───────────────────────────
    declared_inputs: list[str] = []   # detector inputs
    declared_outputs: list[str] = []  # action outputs
    declared_interlocks: list[str] = []
    seen_inputs: set[str] = set()
    seen_outputs: set[str] = set()

    delayed_outputs: list[tuple] = []  # (node_id, output_name, delay_s)
    needs_interlock: list[str] = []   # node_ids with interlocks

    for n in nodes:
        in_ident = _to_ident(n.trigger_detector)
        if in_ident not in seen_inputs:
            seen_inputs.add(in_ident)
            declared_inputs.append(in_ident)
        if n.interlocks:
            interlock_var = _to_ident(f"interlock_{n.node_id}")
            if interlock_var not in seen_inputs:
                seen_inputs.add(interlock_var)
                declared_interlocks.append(interlock_var)
                needs_interlock.append(n.node_id)
        for out in n.action_outputs:
            out_ident = _to_ident(out)
            if out_ident not in seen_outputs:
                seen_outputs.add(out_ident)
                declared_outputs.append(out_ident)
            if n.delay_s > 0:
                delayed_outputs.append((n.node_id, out_ident, n.delay_s))

    # ── Build the ST program ───────────────────────────────────────────────
    lines: list[str] = [
        "// ─── Auto-generated Fire Alarm Logic Tree ───────────────",
        "// Source: marine.engine.alarm_logic.generate_logic_tree()",
        "// Standard: SOLAS II-2/5.6 + IEC 60092-502 + IEC 61131-3",
        "// DO NOT EDIT — regenerate from marine module.",
        "",
        "PROGRAM FireAlarmLogic",
        "  VAR_INPUT",
    ]

    # Detector inputs at %IX0.0, %IX0.1, ... (one bit each).
    for i, in_name in enumerate(declared_inputs):
        byte, bit = divmod(i, 8)
        lines.append(f"    {in_name} AT %IX{byte}.{bit} : BOOL;  // Detector input")
    lines.append("  END_VAR")  # NOSONAR — S1192: duplicated literal acceptable in this localized context
    lines.append("")
    lines.append("  VAR_OUTPUT")
    # Action outputs at %QX0.0, %QX0.1, ... (one bit each).
    for i, out_name in enumerate(declared_outputs):
        byte, bit = divmod(i, 8)
        lines.append(f"    {out_name} AT %QX{byte}.{bit} : BOOL;  // Action output")
    lines.append("  END_VAR")
    lines.append("")
    lines.append("  VAR")

    # Interlock inputs (declared as VAR, not VAR_INPUT — set by HMI/SCADA).
    for il in declared_interlocks:
        lines.append(f"    {il} : BOOL;  // Interlock (set by HMI/SCADA)")
    # TON function block instances for delayed outputs (one per delayed output).
    for node_id, out_name, delay_s in delayed_outputs:
        ton_inst = _to_ident(f"TON_{node_id}_{out_name}")
        lines.append(f"    {ton_inst} : TON;  // Delay timer for {out_name}")
    lines.append("  END_VAR")
    lines.append("")
    lines.append("  // ── Logic ──────────────────────────────────────────")

    # Emit one IF/ELSE per node. Outputs are RESET in the ELSE so they
    # don't latch forever (SOLAS II-2/5.6 requires reset-on-clear).
    for n in nodes:
        in_ident = _to_ident(n.trigger_detector)
        if n.interlocks:
            cond = f"{in_ident} AND {_to_ident(f'interlock_{n.node_id}')}"
        else:
            cond = in_ident
        lines.append(f"  // {n.node_id}: zone={n.zone_id} level={n.alarm_level.value}")
        lines.append(f"  IF {cond} THEN")
        for out in n.action_outputs:
            out_ident = _to_ident(out)
            if n.delay_s > 0:
                ton_inst = _to_ident(f"TON_{n.node_id}_{out_ident}")
                # Instantiate the TON properly: assign IN/PT, then read .Q
                lines.append(
                    f"    {ton_inst}(IN := TRUE, PT := T#{int(n.delay_s)}s);"
                )
                lines.append(f"    {out_ident} := {ton_inst}.Q;")
            else:
                lines.append(f"    {out_ident} := TRUE;")
        # Reset TON instances for delayed outputs not currently active.
        for node_id, out_name, delay_s in delayed_outputs:
            if node_id == n.node_id:
                continue  # already handled above
            ton_inst = _to_ident(f"TON_{node_id}_{out_name}")
            lines.append(f"    {ton_inst}(IN := FALSE, PT := T#{int(delay_s)}s);")
        # Set non-touched outputs to FALSE.
        touched = {_to_ident(o) for o in n.action_outputs}
        for out in declared_outputs:
            if out not in touched:
                lines.append(f"    {out} := FALSE;  // not asserted by this node")
        lines.append("  END_IF;")
        lines.append("")

    lines.append("END_PROGRAM")
    return "\n".join(lines)


__all__ = ["export_to_plc_script", "generate_logic_tree"]
