"""Bill of Quantities (BOQ) generator for fire alarm systems.

Produces a comprehensive, code-compliant BOQ from room and loop data,
including detectors, fault isolators, cable, batteries, and notification
appliances — all costed against typical US 2024 market rates.

Key NFPA 72 references:
    - §10.6.7  – Battery redundancy (two batteries required)
    - §17.6    – Spot-type detector spacing
    - §12.3    – Fault isolator requirements (SLC loops)
    - §18.5    – Notification appliance circuit design
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fireai.core.fault_isolator_injector import (
    verify_isolator_compliance,
)
from fireai.core.nfpa72_calculations import (
    auto_select_awg,
    required_battery_capacity_ah,
)

__all__ = [
    "STANDARD_BATTERY_SIZES",
    "UNIT_COSTS",
    "BOQItem",
    "BOQResult",
    "BatterySpec",
    "calculate_battery_for_panels",
    "generate_battery_result_for_release_gate",
    "generate_cable_boq",
    "generate_detector_boq",
    "generate_full_boq",
    "generate_isolator_boq",
    "standard_battery_size",
]

# ---------------------------------------------------------------------------
# Unit cost table – typical US market 2024
# ---------------------------------------------------------------------------

UNIT_COSTS: Dict[str, float] = {
    "smoke_detector": 85.0,
    "heat_detector": 65.0,
    "duct_detector": 120.0,
    "fault_isolator": 95.0,
    "pull_station": 45.0,
    "strobe": 75.0,
    "speaker": 90.0,
    "speaker_strobe": 130.0,
    "monitor_module": 55.0,
    "control_module": 65.0,
    "fire_alarm_panel": 3500.0,
    "battery_ah": 12.0,  # per Ah
    "cable_fpl_per_m": 1.80,
    "cable_fplr_per_m": 2.10,
    "cable_fplp_per_m": 2.80,
    "cable_ci_per_m": 4.50,  # Circuit Integrity cable (2-hour rated)
    "conduit_per_m": 4.50,
    "conduit_rated_2hr_per_m": 18.00,  # 2-hour fire-rated conduit
    "junction_box": 25.0,
    "firestop_penetration": 65.0,  # per penetration (firestopping material + labor)
}

# Standard VRLA / lead-acid battery sizes commonly available (Ah)
STANDARD_BATTERY_SIZES: List[float] = [
    7.0,
    12.0,
    18.0,
    26.0,
    33.0,
    40.0,
    55.0,
    75.0,
    90.0,
    100.0,
    120.0,
    150.0,
    180.0,
    200.0,
]

# NFPA 72 §17.6.3.1 – nominal spacing for spot-type smoke detectors (m)
# 30 ft nominal → 9.1 m radius, coverage area ≈ 83.6 m² on flat ceiling
SMOKE_DETECTOR_SPACING_M: float = 9.1
SMOKE_DETECTOR_COVERAGE_M2: float = 83.6

# NFPA 72 §17.9 – heat detector spacing (typical 50 ft → 15.2 m, area ≈ 232 m²)
HEAT_DETECTOR_SPACING_M: float = 15.2
HEAT_DETECTOR_COVERAGE_M2: float = 232.0

# Duct detectors – one per duct penetration (not area-based)
DUCT_DETECTOR_COVERAGE_M2: float = float("inf")  # handled separately

# Cable waste factor (10 %)
CABLE_WASTE_FACTOR: float = 1.10

# Warning thresholds
HIGH_DEVICE_COUNT_WARNING: int = 200
LONG_LOOP_WARNING_M: float = 1000.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BOQItem:
    """Single line item in a Bill of Quantities."""

    item_type: str
    description: str
    quantity: int
    unit: str
    unit_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    nfpa_reference: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        # Auto-compute total if not explicitly provided
        if self.total_cost_usd == 0.0 and self.unit_cost_usd != 0.0:
            self.total_cost_usd = round(self.quantity * self.unit_cost_usd, 2)


@dataclass
class BatterySpec:
    """Specification for fire alarm panel battery sizing."""

    standby_current_ma: float
    alarm_current_ma: float
    standby_hours: float = 24.0
    alarm_minutes: float = 5.0
    safety_factor: float = 1.20
    panel_voltage_v: float = 24.0


@dataclass
class BOQResult:
    """Complete Bill of Quantities result for a fire alarm system."""

    items: List[BOQItem]
    total_items: int
    grand_total_usd: float
    battery_ah: float
    detector_count: int
    isolator_count: int
    panel_count: int
    cable_meters: float
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper – standard battery size
# ---------------------------------------------------------------------------


def standard_battery_size(required_ah: float) -> float:
    """Return the next standard battery size >= *required_ah*.

    Standard sizes (Ah): 7, 12, 18, 26, 33, 40, 55, 75, 90, 100,
    120, 150, 180, 200.  If the required capacity exceeds the largest
    standard size, it is rounded up to the nearest 50 Ah.

    Args:
        required_ah: Minimum required capacity in ampere-hours.

    Returns:
        Standard battery size in Ah (always >= required_ah).

    """
    for size in STANDARD_BATTERY_SIZES:
        if size >= required_ah:
            return size
    # Beyond the largest standard size – round up to nearest 50 Ah
    return math.ceil(required_ah / 50.0) * 50.0


# ---------------------------------------------------------------------------
# Battery calculation
# ---------------------------------------------------------------------------


def calculate_battery_for_panels(
    panel_count: int,
    spec: BatterySpec,
) -> Dict[str, Any]:
    """Calculate battery requirements for one or more fire alarm panels.

    Uses :func:`required_battery_capacity_ah` from *nfpa72_calculations*
    and enforces NFPA 72 §10.6.7 (two batteries for redundancy).

    Args:
        panel_count: Number of fire alarm control panels.
        spec: Battery specification (currents, durations, safety factor).

    Returns:
        Dict with keys: ``required_ah``, ``installed_ah``, ``battery_count``,
        ``is_adequate``, ``cost_usd``, ``per_panel_ah``.

    """
    # Per-panel required capacity
    per_panel_ah = required_battery_capacity_ah(  # type: ignore[call-arg]
        standby_current_ma=spec.standby_current_ma,
        alarm_current_ma=spec.alarm_current_ma,
        standby_hours=spec.standby_hours,
        alarm_minutes=spec.alarm_minutes,
        safety_factor=spec.safety_factor,
    )

    installed_ah = standard_battery_size(per_panel_ah)

    # NFPA 72 §10.6.7 – two batteries per panel for redundancy
    battery_count = panel_count * 2

    cost_per_battery = installed_ah * UNIT_COSTS["battery_ah"]
    total_cost = battery_count * cost_per_battery

    return {
        "required_ah": round(per_panel_ah, 2),
        "installed_ah": installed_ah,
        "battery_count": battery_count,
        "is_adequate": installed_ah >= per_panel_ah,
        "cost_usd": round(total_cost, 2),
        "per_panel_ah": round(per_panel_ah, 2),
    }


# ---------------------------------------------------------------------------
# Detector BOQ
# ---------------------------------------------------------------------------


def generate_detector_boq(
    rooms: List[Dict],
    ceiling_height_m: float = 3.0,
) -> List[BOQItem]:
    """Generate BOQ line items for detectors from a list of rooms.

    NFPA 72 §17.6 – spot-type smoke detectors are spaced at 30 ft (9.1 m)
    nominal on flat ceilings.  Heat detectors per §17.9 at 50 ft (15.2 m).
    Detector counts are always rounded **up** (life-safety rule).

    Each room dict should contain:
        - ``room_id`` (str): Room identifier.
        - ``area_m2`` (float): Floor area in square metres.
        - ``detector_type`` (str): One of ``smoke_detector``,
          ``heat_detector``, or ``duct_detector``.
    Optional keys:
        - ``duct_count`` (int): Number of duct penetrations (for
          ``duct_detector`` type).

    Args:
        rooms: List of room descriptor dictionaries.
        ceiling_height_m: Ceiling height in metres (affects spacing
            de-rating above 3.0 m per NFPA 72 §17.6.3.3).

    Returns:
        List of :class:`BOQItem` for detectors.

    """
    items: List[BOQItem] = []

    # Height de-rating factor per NFPA 72 §17.6.3.3 – for every 0.3 m (1 ft)
    # above 3.0 m, spacing is reduced ~1 %.  Capped at 50 % reduction.
    if ceiling_height_m > 3.0:
        extra_height = ceiling_height_m - 3.0
        derating = max(0.50, 1.0 - 0.01 * (extra_height / 0.3))
    else:
        derating = 1.0

    # Aggregate by detector type
    type_counts: Dict[str, int] = {}

    for room in rooms:
        det_type = room.get("detector_type", "smoke_detector").lower()
        area = room.get("area_m2", 0.0)

        if det_type == "duct_detector":
            duct_count = room.get("duct_count", 1)
            count = max(1, int(duct_count))
        elif det_type == "heat_detector":
            effective_coverage = HEAT_DETECTOR_COVERAGE_M2 * derating
            count = max(1, math.ceil(area / effective_coverage))
        else:
            # Default: smoke detector
            effective_coverage = SMOKE_DETECTOR_COVERAGE_M2 * derating
            count = max(1, math.ceil(area / effective_coverage))

        type_counts[det_type] = type_counts.get(det_type, 0) + count

    # Build BOQ items
    for det_type, quantity in sorted(type_counts.items()):
        unit_cost = UNIT_COSTS.get(det_type, 0.0)
        nfpa_ref = (
            "NFPA 72 §17.6" if "smoke" in det_type else "NFPA 72 §17.9" if "heat" in det_type else "NFPA 72 §17.13"
        )
        unit_label = "ea" if det_type != "duct_detector" else "ea"

        items.append(
            BOQItem(
                item_type=det_type,
                description=f"{det_type.replace('_', ' ').title()}",
                quantity=quantity,
                unit=unit_label,
                unit_cost_usd=unit_cost,
                nfpa_reference=nfpa_ref,
                notes=f"Ceiling height {ceiling_height_m:.1f} m; derating={derating:.2f}"
                if ceiling_height_m > 3.0
                else "",
            )
        )

    return items


# ---------------------------------------------------------------------------
# Isolator BOQ
# ---------------------------------------------------------------------------


def generate_isolator_boq(loops: List[Dict]) -> List[BOQItem]:
    """Generate BOQ line items for fault isolators using compliance verification.

    For each loop, :func:`verify_isolator_compliance` is called to assess
    whether existing isolators are sufficient.  If not, the shortfall is
    computed and additional isolators are added to the BOQ.

    Each loop dict should contain:
        - ``loop_id`` (str): Loop identifier.
        - ``devices`` (List[Dict]): Ordered list of device dicts with at
          least a ``device_type`` key.
    Optional keys:
        - ``max_devices_between_isolators`` (int): Override for the
          maximum segment size.

    Args:
        loops: List of loop descriptor dictionaries.

    Returns:
        List of :class:`BOQItem` for fault isolators.

    """
    items: List[BOQItem] = []
    total_isolators_needed = 0

    for loop in loops:
        loop.get("loop_id", "unknown")
        devices = loop.get("devices", [])
        max_between = loop.get("max_devices_between_isolators", 32)

        compliance = verify_isolator_compliance(
            loop_devices=devices,
            max_devices_between_isolators=max_between,
        )

        existing = compliance.get("isolator_count", 0)

        if not compliance.get("compliant", False):  # V111 FIX: Fail-safe default — missing key = NOT compliant
            # Estimate needed isolators from the worst segment
            worst_segment = compliance.get(
                "max_segment_devices", 0
            )  # 0 is safe default — no segment = no isolator need
            # Each isolator splits a segment; need enough to bring
            # all segments under max_between
            if worst_segment > max_between:
                needed_for_segment = math.ceil(worst_segment / max_between) - 1
            else:
                needed_for_segment = 1  # at least one to satisfy compliance
            total_isolators_needed += needed_for_segment
        else:
            # Compliant – but ensure at least one isolator per loop
            # if there are devices (NFPA 72 §12.3)
            if existing == 0 and len(devices) > 0:
                total_isolators_needed += 1

    if total_isolators_needed > 0:
        unit_cost = UNIT_COSTS["fault_isolator"]
        items.append(
            BOQItem(
                item_type="fault_isolator",
                description="Fault Isolator Module",
                quantity=total_isolators_needed,
                unit="ea",
                unit_cost_usd=unit_cost,
                nfpa_reference="NFPA 72 §12.3",
                notes=f"Additional isolators to achieve compliance across {len(loops)} loop(s)",
            )
        )

    return items


# ---------------------------------------------------------------------------
# Cable BOQ
# ---------------------------------------------------------------------------


def generate_cable_boq(
    loops: List[Dict],
    cable_type: str = "FPL",
    survivability_level: Optional[str] = None,
    auto_size_awg: bool = False,
    supply_voltage_v: float = 24.0,
    load_current_a: float = 0.5,
    require_rated_enclosure: bool = False,
) -> List[BOQItem]:
    """Generate BOQ line items for cable and conduit from loop data.

    Cable length is taken from each loop's ``cable_length_m`` field.  A
    10 % waste factor is applied per industry practice.  Conduit is
    estimated at 60 % of cable length (typical for fire alarm wiring where
    not all runs are in conduit).

    Supported cable types: ``FPL``, ``FPLR``, ``FPLP``, ``CI``.

    V2 ENHANCEMENTS:
      - ``survivability_level``: Overrides cable_type based on NFPA 72 §12.4.
        When provided, cable_type is automatically upgraded:
          Level 2 → CI cable
          Level 3 → CI cable + 2-hour rated conduit
      - ``auto_size_awg``: When True, calls auto_select_awg() to determine
        the correct wire gauge based on voltage drop, and adds an AWG
        specification to the BOQ item notes.
      - ``require_rated_enclosure``: When True, uses 2-hour fire-rated
        conduit instead of standard EMT.

    Each loop dict should contain:
        - ``loop_id`` (str): Loop identifier.
        - ``cable_length_m`` (float): Estimated cable run length in metres.

    Args:
        loops: List of loop descriptor dictionaries.
        cable_type: Cable rating – ``FPL``, ``FPLR``, ``FPLP``, or ``CI``.
        survivability_level: Override from PathwaySurvivabilityEngine.
        auto_size_awg: Auto-select AWG gauge based on voltage drop.
        supply_voltage_v: Panel voltage for AWG sizing (default 24 VDC).
        load_current_a: Circuit load current for AWG sizing (default 0.5 A).
        require_rated_enclosure: Use 2-hour rated conduit.

    Returns:
        List of :class:`BOQItem` for cable, conduit, and junction boxes.

    """
    items: List[BOQItem] = []

    cable_type_upper = cable_type.upper().strip()

    # ── Survivability override ────────────────────────────────────────
    if survivability_level is not None:
        level = survivability_level.upper().strip()
        if level in ("LEVEL_2", "LEVEL_3"):
            cable_type_upper = "CI"
            if level == "LEVEL_3":
                require_rated_enclosure = True

    cable_key_map = {
        "FPL": "cable_fpl_per_m",
        "FPLR": "cable_fplr_per_m",
        "FPLP": "cable_fplp_per_m",
        "CI": "cable_ci_per_m",
    }
    cable_key = cable_key_map.get(cable_type_upper, "cable_fpl_per_m")

    total_cable_m = 0.0
    loop_count = 0

    for loop in loops:
        length_m = loop.get("cable_length_m", 0.0)
        total_cable_m += length_m
        loop_count += 1

    # Apply 10 % waste factor
    cable_with_waste = math.ceil(total_cable_m * CABLE_WASTE_FACTOR)

    # ── AWG auto-sizing ───────────────────────────────────────────────
    awg_note = ""
    selected_awg = None
    if auto_size_awg and total_cable_m > 0:
        awg_result = auto_select_awg(
            supply_voltage_v=supply_voltage_v,
            load_current_a=load_current_a,
            cable_length_m=total_cable_m / max(loop_count, 1),  # avg per loop
        )
        if awg_result.get("selected_awg") is not None:
            selected_awg = awg_result["selected_awg"]
            awg_note = f"; AWG={selected_awg} (auto-sized for VD ≤15%)"
        else:
            awg_note = "; WARNING: no AWG satisfies VD — split circuits"

    # Cable item
    if cable_with_waste > 0:
        unit_cost = UNIT_COSTS.get(cable_key, UNIT_COSTS["cable_fpl_per_m"])
        items.append(
            BOQItem(
                item_type=f"cable_{cable_type_upper}",
                description=f"Fire Alarm Cable – {cable_type_upper} (per metre)",
                quantity=cable_with_waste,
                unit="m",
                unit_cost_usd=unit_cost,
                nfpa_reference="NFPA 72 §12.2 / §12.4 / NEC Art. 760",
                notes=f"Includes 10% waste factor; raw length={total_cable_m:.0f}m{awg_note}",
            )
        )

    # Conduit – estimated at 60 % of cable length
    conduit_m = math.ceil(cable_with_waste * 0.60)
    if conduit_m > 0:
        if require_rated_enclosure:
            items.append(
                BOQItem(
                    item_type="conduit_rated_2hr",
                    description="2-Hour Fire-Rated Conduit for FA Wiring (per metre)",
                    quantity=conduit_m,
                    unit="m",
                    unit_cost_usd=UNIT_COSTS["conduit_rated_2hr_per_m"],
                    nfpa_reference="NFPA 72 §12.4.2 / IBC §714",
                    notes="2-hour fire-rated enclosure per survivability Level 3",
                )
            )
        else:
            items.append(
                BOQItem(
                    item_type="conduit",
                    description="EMT Conduit for Fire Alarm Wiring (per metre)",
                    quantity=conduit_m,
                    unit="m",
                    unit_cost_usd=UNIT_COSTS["conduit_per_m"],
                    nfpa_reference="NEC Art. 760",
                    notes="Estimated at 60% of cable length",
                )
            )

    # Junction boxes – rough estimate: one every 30 m of conduit
    if conduit_m > 0:
        jb_count = max(1, math.ceil(conduit_m / 30.0))
        items.append(
            BOQItem(
                item_type="junction_box",
                description="Junction Box (4×4)",
                quantity=jb_count,
                unit="ea",
                unit_cost_usd=UNIT_COSTS["junction_box"],
                nfpa_reference="",
                notes="Estimated 1 per 30 m of conduit run",
            )
        )

    # Firestopping – one penetration per floor per riser
    if require_rated_enclosure or cable_type_upper == "CI":
        floor_count = max(1, loop_count)
        items.append(
            BOQItem(
                item_type="firestop_penetration",
                description="Firestopping Penetration Seal (rated assembly)",
                quantity=floor_count,
                unit="ea",
                unit_cost_usd=UNIT_COSTS["firestop_penetration"],
                nfpa_reference="IBC 2021 §714 / NFPA 72 §12.4",
                notes="One penetration per floor for rated enclosure through-penetration",
            )
        )

    return items


# ---------------------------------------------------------------------------
# Full BOQ
# ---------------------------------------------------------------------------


def generate_full_boq(
    rooms: List[Dict],
    loops: List[Dict],
    panels: int = 1,
    battery_spec: Optional[BatterySpec] = None,
    include_notification: bool = True,
) -> BOQResult:
    """Generate a complete Bill of Quantities for a fire alarm system.

    Aggregates detectors, fault isolators, cable, batteries, panels, and
    optional notification appliances into a single :class:`BOQResult`.

    Args:
        rooms: List of room descriptor dicts (see
            :func:`generate_detector_boq`).
        loops: List of loop descriptor dicts (see
            :func:`generate_isolator_boq` and :func:`generate_cable_boq`).
        panels: Number of fire alarm control panels.
        battery_spec: Battery specification; defaults to a reasonable
            spec if not provided.
        include_notification: If *True*, add default notification
            appliances (strobes + speaker-strobes estimated from room
            count).

    Returns:
        A :class:`BOQResult` with all line items, totals, and any
        warnings for unusual configurations.

    """
    warnings: List[str] = []

    if battery_spec is None:
        battery_spec = BatterySpec(
            standby_current_ma=250.0,
            alarm_current_ma=1500.0,
        )

    all_items: List[BOQItem] = []

    # --- Panels ---
    all_items.append(
        BOQItem(
            item_type="fire_alarm_panel",
            description="Fire Alarm Control Panel (FACP)",
            quantity=panels,
            unit="ea",
            unit_cost_usd=UNIT_COSTS["fire_alarm_panel"],
            nfpa_reference="NFPA 72 §10.6",
        )
    )

    # --- Detectors ---
    detector_items = generate_detector_boq(rooms)
    all_items.extend(detector_items)
    detector_count = sum(it.quantity for it in detector_items)

    # --- Isolators ---
    isolator_items = generate_isolator_boq(loops)
    all_items.extend(isolator_items)
    isolator_count = sum(it.quantity for it in isolator_items)

    # --- Cable ---
    cable_items = generate_cable_boq(loops)
    all_items.extend(cable_items)
    cable_meters = sum(it.quantity for it in cable_items if it.item_type.startswith("cable_"))

    # --- Batteries ---
    battery_info = calculate_battery_for_panels(panels, battery_spec)
    installed_ah = battery_info["installed_ah"]
    all_items.append(
        BOQItem(
            item_type="battery",
            description=f"VRLA Battery {installed_ah:.0f} Ah @ {battery_spec.panel_voltage_v:.0f} V",
            quantity=battery_info["battery_count"],
            unit="ea",
            unit_cost_usd=round(installed_ah * UNIT_COSTS["battery_ah"], 2),
            nfpa_reference="NFPA 72 §10.6.7",
            notes="Two batteries per panel for redundancy per §10.6.7",
        )
    )

    # --- Notification appliances (acoustic-calculator-based sizing) ---
    if include_notification:
        room_count = len(rooms)

        if room_count > 0:
            # Use acoustic_calculator to determine speaker count per room
            # based on actual SPL physics, not fixed coverage radii.
            total_speakers = 0
            total_strobes = 0
            for room in rooms:
                area = room.get("area_m2", 0.0)
                if area <= 0:
                    # Try to estimate from detector coverage
                    area = room.get("estimated_area_m2", 50.0)

                # Estimate room dimensions from area (assume square)
                room_side = math.sqrt(max(area, 1.0))

                try:
                    from fireai.core.acoustic_calculator import (
                        calculate_min_speakers_for_room,
                    )

                    speaker_result = calculate_min_speakers_for_room(
                        room_length_m=room_side,
                        room_width_m=room_side,
                        room_height_m=3.0,
                        source_dba=95.0,
                        ambient_dba=55.0,
                        mode="public",
                    )
                    total_speakers += speaker_result.speaker_count
                except Exception:
                    # Fallback to heuristic if acoustic_calculator unavailable
                    total_speakers += max(1, math.ceil(area / 83.6))

                # Strobes: 1 per room minimum for accessibility (ADA/NFPA 72 §18.5)
                total_strobes += 1

            all_items.append(
                BOQItem(
                    item_type="speaker_strobe",
                    description="Speaker/Strobe Combination",
                    quantity=total_speakers,
                    unit="ea",
                    unit_cost_usd=UNIT_COSTS["speaker_strobe"],
                    nfpa_reference="NFPA 72 §18.5 / §18.4.3",
                    notes=(
                        f"Speaker count from acoustic_calculator (distance-based SPL). Total across {room_count} rooms."
                    ),
                )
            )
            all_items.append(
                BOQItem(
                    item_type="strobe",
                    description="Strobe Only (corridors/common areas)",
                    quantity=max(1, total_strobes // 2),
                    unit="ea",
                    unit_cost_usd=UNIT_COSTS["strobe"],
                    nfpa_reference="NFPA 72 §18.5",
                    notes="Additional strobes for corridors — 1 per 2 rooms estimated",
                )
            )

    # --- Pull stations (manual fire alarm boxes) ---
    # NFPA 72 §17.13.2 – within 1.5 m of each exit
    if len(rooms) > 0:
        # Estimate one pull station per floor / major exit group
        pull_count = max(1, math.ceil(len(rooms) / 10))
        all_items.append(
            BOQItem(
                item_type="pull_station",
                description="Manual Pull Station",
                quantity=pull_count,
                unit="ea",
                unit_cost_usd=UNIT_COSTS["pull_station"],
                nfpa_reference="NFPA 72 §17.13.2",
                notes="Within 1.5 m of each exit – verify with egress plan",
            )
        )

    # --- Totals ---
    total_items = sum(it.quantity for it in all_items)
    grand_total = round(sum(it.total_cost_usd for it in all_items), 2)

    # --- Warnings for unusual configurations ---
    total_loop_devices = sum(len(loop.get("devices", [])) for loop in loops)
    if total_loop_devices > HIGH_DEVICE_COUNT_WARNING:
        warnings.append(
            f"High device count on SLC loops: {total_loop_devices} devices. "
            f"Verify panel loop capacity and voltage drop calculations."
        )
    total_cable_raw = sum(loop.get("cable_length_m", 0.0) for loop in loops)
    if total_cable_raw > LONG_LOOP_WARNING_M:
        warnings.append(
            f"Very long total cable run: {total_cable_raw:.0f} m. "
            f"Verify voltage drop and signal integrity per NFPA 72 §12.2."
        )
    if detector_count == 0:
        warnings.append("No detectors in BOQ. Verify that detection requirements are met per NFPA 72 §17.3.")
    if panels > 3:
        warnings.append(
            f"Multiple panels ({panels}) – ensure network configuration complies with NFPA 72 §10.6.7 and §23.8."
        )
    if not battery_info["is_adequate"]:
        warnings.append(
            f"Installed battery ({installed_ah} Ah) may be insufficient "
            f"for the calculated load ({battery_info['required_ah']} Ah). "
            f"Review battery calculations."
        )

    return BOQResult(
        items=all_items,
        total_items=total_items,
        grand_total_usd=grand_total,
        battery_ah=installed_ah,
        detector_count=detector_count,
        isolator_count=isolator_count,
        panel_count=panels,
        cable_meters=float(cable_meters),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Battery Result for Release Gate 8
# ---------------------------------------------------------------------------


def generate_battery_result_for_release_gate(
    panel_count: int = 1,
    standby_current_ma: float = 250.0,
    alarm_current_ma: float = 1500.0,
    standby_hours: float = 24.0,
    alarm_minutes: float = 5.0,
    safety_factor: float = 1.20,
) -> Dict[str, Any]:
    """Generate battery sizing result for release_gates.py Gate 8.

    This is the output path that calls :func:`required_battery_capacity_ah`
    and returns a dict compatible with the ``battery_result`` parameter of
    :func:`fireai.core.release_gates.verify_and_evaluate`.

    Gate 8 requires:
      - required_ah > 0 (computed value)
      - installed_ah >= required_ah (standard battery size)
      - is_adequate = True

    This function ensures all those conditions are met by computing
    battery capacity per NFPA 72 §10.6.7 and selecting the next
    standard battery size.

    NFPA 72 §10.6.7.2.1 requires:
      - 24 hours of standby current
      - 5 minutes of alarm current
      - 20% safety factor for aging and temperature derating
      - Two batteries per panel for redundancy

    Args:
        panel_count: Number of fire alarm control panels.
        standby_current_ma: Total standby current draw in mA.
        alarm_current_ma: Total alarm current draw in mA.
        standby_hours: Required standby duration (default 24h per NFPA 72).
        alarm_minutes: Required alarm duration (default 5 min per NFPA 72).
        safety_factor: Safety factor for aging/temperature (default 1.20).

    Returns:
        Dict with keys required by release_gates.py Gate 8:
          - required_ah: Calculated required capacity
          - installed_ah: Selected standard battery size
          - is_adequate: Whether installed >= required
          - battery_count: Total batteries (2 per panel per §10.6.7)

    """
    spec = BatterySpec(
        standby_current_ma=standby_current_ma,
        alarm_current_ma=alarm_current_ma,
        standby_hours=standby_hours,
        alarm_minutes=alarm_minutes,
        safety_factor=safety_factor,
    )
    return calculate_battery_for_panels(panel_count, spec)
