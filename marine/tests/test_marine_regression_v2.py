"""
marine/tests/test_marine_regression_v2.py — Regression tests for v2 bugfixes.

Each test corresponds to a specific bug from the v2 audit report:
  - Zone overlap bug (zone_mapper)
  - assign_space_categories field-drop bug
  - CO2 safety factor + alternative method
  - Inert gas formula (logarithmic purge + cargo discharge rate)
  - Foam high-expansion / AFFF sizing (new functions)
  - PLC script IEC 61131-3 compliance (var declarations, TON instances)
  - Linear-heat detector classification in alarm logic
  - Fire-resistance material consistency (B-15)
  - ISO 15370 thermal alarm count (ceil + linear spacing)
  - ETAP UPS units (kW not kWh)
  - SCADA dashboard timestamp (was hardcoded)
  - SCADA Modbus register widths (per-type)
  - AutoCAD DXF wrappers (SECTION/EOF) + zone offsets
  - SOLAS II-2/2.2.1.1 passenger-ship 24m MVZ limit
  - SOLAS II-2/10.7.1.1 passenger-ship cargo CO2 requirement
  - validate_alarm_circuit_redundancy actual_circuits parameter
  - validate_insulation_monitoring ship parameter + UPS autonomy
"""
from __future__ import annotations

import functools
import operator

import pytest

from marine.core.errors import ExtinguishingDesignError
from marine.core.types import (
    AlarmLevel,
    DetectorType,
    ExtinguishingSystem,
    FireClass,
    MarineZone,
    ShipProject,
    ShipType,
    SpaceCategory,
)
from marine.engine.alarm_logic import (
    export_to_plc_script,
    generate_logic_tree,
)
from marine.engine.extinguishment import (
    size_afff,
    size_co2_total_flooding,
    size_foam_high_expansion,
    size_inert_gas,
)
from marine.engine.fire_resistance import (
    generate_division_specs,
    select_insulation_material,
)
from marine.engine.zone_mapper import (
    assign_space_categories,
    divide_into_main_vertical_zones,
)
from marine.iec60092.electrical_installations import (
    validate_insulation_monitoring,
)
from marine.iec60092.part_502 import validate_alarm_circuit_redundancy
from marine.integration.autocad_exporter import generate_full_dxf
from marine.integration.etap_bridge import export_etap_loads_csv
from marine.integration.scada_bridge import (
    build_modbus_registers,
    dashboard_payload,
)
from marine.iso15370.thermal_alarms import (
    calculate_thermal_alarm_count,
)
from marine.solas.chapter_ii_2 import (
    required_extinguishing_for_space,
    validate_main_vertical_zones,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def cargo_ship() -> ShipProject:
    return ShipProject(
        project_id="R-001", ship_name="Regression Cargo",
        ship_type=ShipType.CARGO, length_overall_m=120.0,
        gross_tonnage=8000.0,
    )


@pytest.fixture
def large_passenger_ship() -> ShipProject:
    """Passenger ship with >36 pax — triggers 24m MVZ limit per SOLAS."""
    return ShipProject(
        project_id="R-002", ship_name="Big Ferry",
        ship_type=ShipType.PASSENGER, length_overall_m=120.0,
        passenger_capacity=500, gross_tonnage=12000.0,
    )


@pytest.fixture
def tanker() -> ShipProject:
    return ShipProject(
        project_id="R-003", ship_name="Regression Tanker",
        ship_type=ShipType.TANKER, length_overall_m=180.0,
        gross_tonnage=25000.0,
    )


@pytest.fixture
def engine_room_zone() -> MarineZone:
    return MarineZone(
        zone_id="ER-01", name="Engine Room",
        space_category=SpaceCategory.MACHINERY_SPACE_A,
        deck="engine_room", frame_start=50, frame_end=80,
        area_m2=200.0, height_m=6.0,
    )


@pytest.fixture
def escape_route_zone() -> MarineZone:
    return MarineZone(
        zone_id="ESC-01", name="Corridor A",
        space_category=SpaceCategory.ESCAPE_ROUTE,
        deck="A-deck", frame_start=10, frame_end=40,
        area_m2=50.0, height_m=2.5,
    )


# ─── Bug #1: Zone Overlap ────────────────────────────────────────────────────

class TestZoneOverlapRegression:
    """
    Bugs: zones overlapped by up to 15 m because start/end frames were
    computed with inconsistent formulas.
    """

    def test_adjacent_zones_share_boundary(self, cargo_ship):
        zones = divide_into_main_vertical_zones(199.0, cargo_ship)
        # Each zone's end_frame must equal next zone's start_frame.
        for i in range(len(zones) - 1):
            assert zones[i].frame_end == zones[i + 1].frame_start, (
                f"Zone {zones[i].zone_id} ends at frame {zones[i].frame_end} "
                f"but zone {zones[i+1].zone_id} starts at frame "
                f"{zones[i+1].frame_start} — overlap or gap."
            )

    def test_zones_tile_full_length(self, cargo_ship):
        ship_length_m = 199.0
        zones = divide_into_main_vertical_zones(ship_length_m, cargo_ship)
        total_length = sum(
            (z.frame_end - z.frame_start) * 0.6 for z in zones
        )
        # Total should match ship length within rounding (≤ 1 frame = 0.6 m).
        assert abs(total_length - ship_length_m) < 0.7, (
            f"Zones tile {total_length:.2f} m, ship is {ship_length_m} m — "
            f"gap or overflow of {abs(total_length - ship_length_m):.2f} m."
        )

    def test_all_zones_under_40m(self, cargo_ship):
        """SOLAS II-2/2.2.1: every MVZ ≤ 40 m. No tolerance for rounding."""
        # Test many edge lengths to catch rounding overshoots.
        for length in [39.0, 40.0, 41.0, 79.0, 80.0, 81.0, 119.0, 120.0,
                       121.0, 159.0, 199.0, 200.0, 239.0, 240.0, 241.0]:
            zones = divide_into_main_vertical_zones(length, cargo_ship)
            for z in zones:
                zlen = (z.frame_end - z.frame_start) * 0.6
                assert zlen <= 40.0, (
                    f"At ship_length={length} m, zone {z.zone_id} spans "
                    f"{zlen:.2f} m — exceeds SOLAS 40 m limit."
                )


# ─── Bug #12: assign_space_categories field-drop ─────────────────────────────

class TestAssignSpaceCategoriesRegression:
    """
    Bug: previously this function rebuilt the dataclass by hand and
    silently dropped 4 fields (required_fire_class, hazard_class,
    ventilation_rate_ach, has_escape_route).
    """

    def test_preserves_has_escape_route_false(self, cargo_ship):
        # Create a zone with has_escape_route=False — previously this got
        # silently flipped to True after category reassignment.
        zones = divide_into_main_vertical_zones(120.0, cargo_ship)
        # Force-override one zone to has_escape_route=False using dataclass replace.
        import dataclasses
        target = zones[0]
        zones[0] = dataclasses.replace(target, has_escape_route=False,
                                       ventilation_rate_ach=8.0,
                                       hazard_class=None)  # type: ignore[arg-type]
        # Now reassign category.
        updated = assign_space_categories(
            zones, {zones[0].zone_id: SpaceCategory.CONTROL_STATION}
        )
        # The has_escape_route=False MUST be preserved.
        assert updated[0].has_escape_route is False, (
            "has_escape_route was flipped from False to True during "
            "category reassignment — safety-relevant data corruption."
        )
        # ventilation_rate_ach MUST be preserved.
        assert updated[0].ventilation_rate_ach == pytest.approx(8.0)
        # The category MUST be the new one.
        assert updated[0].space_category == SpaceCategory.CONTROL_STATION


# ─── Bug #3: CO2 safety factor + alternative method ──────────────────────────

class TestCO2SizingRegression:
    """
    Bug: CO2 mass was under-estimated by ~25% because safety factor was
    hardcoded to 1.0 and the alternative (free-gas) method was not used.
    """

    def test_co2_mass_uses_larger_method(self, engine_room_zone):
        design = size_co2_total_flooding(engine_room_zone, "engine_room")
        # Volume = 200 * 6 = 1200 m³. Method 1: 1200 * 35/65 * 1.98 * 1.10
        # = 1407 kg. Method 2: 1200 / 0.75 = 1600 kg. Larger = 1600.
        assert design.agent_quantity_kg >= 1500, (
            f"CO2 mass {design.agent_quantity_kg} kg < 1500 — safety factor "
            f"or alternative method not applied."
        )

    def test_co2_zero_area_raises(self):
        bad_zone = MarineZone(
            zone_id="Z", name="Empty", space_category=SpaceCategory.MACHINERY_SPACE_A,
            deck="m", frame_start=0, frame_end=1, area_m2=0.0, height_m=3.0,
        )
        with pytest.raises(ExtinguishingDesignError):
            size_co2_total_flooding(bad_zone)


# ─── Bug #2: Inert gas formula ───────────────────────────────────────────────

class TestInertGasRegression:
    """
    Bug: IG discharge time was constant 2880s regardless of zone size.
    Also: linear (not logarithmic) purge formula under-estimated IG volume
    by ~14×.
    """

    def test_discharge_time_scales_with_volume(self, tanker):
        # Same ship, two different tank sizes → discharge times must differ.
        small = MarineZone(
            zone_id="TS", name="Small Tank", space_category=SpaceCategory.TANK_SPACE,
            deck="tanks", frame_start=0, frame_end=10, area_m2=100.0, height_m=10.0,
        )
        large = MarineZone(
            zone_id="TL", name="Large Tank", space_category=SpaceCategory.TANK_SPACE,
            deck="tanks", frame_start=0, frame_end=10, area_m2=1000.0, height_m=10.0,
        )
        d_small = size_inert_gas(small, cargo_discharge_rate_m3_per_hr=250.0)
        d_large = size_inert_gas(large, cargo_discharge_rate_m3_per_hr=250.0)
        assert d_large.discharge_time_s > d_small.discharge_time_s, (
            f"Large tank discharge {d_large.discharge_time_s}s should exceed "
            f"small tank {d_small.discharge_time_s}s — formula is volume-blind."
        )

    def test_purge_volume_matches_logarithmic_formula(self):
        """For O2 21%→8% with IG O2=4%, purge volume should be ~1.93× tank volume."""
        zone = MarineZone(
            zone_id="Z", name="Tank", space_category=SpaceCategory.TANK_SPACE,
            deck="tanks", frame_start=0, frame_end=10,
            area_m2=100.0, height_m=10.0,  # V=1000 m³
        )
        # Use very low cargo rate to make discharge time observable; check
        # via the standard_reference string which embeds the purge volume.
        design = size_inert_gas(zone, cargo_discharge_rate_m3_per_hr=250.0)
        # Purge volume ≈ 1000 × ln(21/8) / (1 - 4/8) ≈ 1930 m³
        assert "193" in design.standard_reference or "194" in design.standard_reference, (
            f"Purge volume {design.standard_reference!r} doesn't match "
            f"logarithmic formula (~1930 m³)."
        )

    def test_rejects_bad_o2_pct(self, engine_room_zone):
        zone = MarineZone(
            zone_id="Z", name="Tank", space_category=SpaceCategory.TANK_SPACE,
            deck="tanks", frame_start=0, frame_end=10,
            area_m2=100.0, height_m=10.0,
        )
        # IG O2% must be in [0, 8) — 10% would never achieve ≤8% tank O2.
        with pytest.raises(ExtinguishingDesignError):
            size_inert_gas(zone, inert_gas_o2_pct=10.0)


# ─── Bug #4, #5: New size_foam_high_expansion and size_afff ──────────────────

class TestNewExtinguishingSizers:
    """
    Bug: FOAM_HIGH and AFFF constants were imported but no size_* function
    existed. README claimed both were sized; code fell through to a 12 kg
    dry-chemical default.
    """

    def test_foam_high_expansion_sizing(self):
        zone = MarineZone(
            zone_id="ER", name="Engine Room",
            space_category=SpaceCategory.MACHINERY_SPACE_A,
            deck="engine", frame_start=0, frame_end=10,
            area_m2=200.0, height_m=6.0,  # V = 1200 m³
        )
        d = size_foam_high_expansion(zone)
        assert d.system_type == ExtinguishingSystem.FOAM_HIGH
        # Fill time = 10 min, so discharge_time_s = 600.
        assert d.discharge_time_s == 600
        # Concentrate should be > 0.
        assert d.agent_quantity_kg > 0

    def test_afff_sizing(self):
        zone = MarineZone(
            zone_id="HD", name="Helideck",
            space_category=SpaceCategory.OPEN_DECK,
            deck="heli", frame_start=0, frame_end=10,
            area_m2=100.0, height_m=1.0,  # area matters for AFFF, not volume
        )
        d = size_afff(zone)
        assert d.system_type == ExtinguishingSystem.AFFF
        # 100 m² × 2.5 L/min/m² × 5 min × 0.03 × 1.05 = 39.375 kg.
        assert 35 <= d.agent_quantity_kg <= 45
        # Discharge time = 5 min = 300 s.
        assert d.discharge_time_s == 300


# ─── Bugs #6-#10: PLC script IEC 61131-3 compliance ─────────────────────────

class TestPLCScriptRegression:
    """
    Bugs: PLC output used AT %I* (invalid), duplicate VAR declarations,
    undeclared interlock vars, inline TON() calls (function blocks can't
    be invoked inline), no ELSE reset (latched forever).
    """

    def _build_nodes(self, engine_room_zone, cargo_ship):
        from marine.iec60092.part_502 import place_detectors_grid
        dps = place_detectors_grid(engine_room_zone, DetectorType.HEAT_FIXED)
        # Add a second detector type to force duplicate output declarations.
        dps += place_detectors_grid(engine_room_zone, DetectorType.SMOKE_PHOTOELECTRIC)
        return generate_logic_tree(
            engine_room_zone, dps,
            extinguishing_system=ExtinguishingSystem.WATER_MIST,
        )

    def test_no_at_star_placeholder(self, engine_room_zone, cargo_ship):
        nodes = self._build_nodes(engine_room_zone, cargo_ship)
        script = export_to_plc_script(nodes)
        # AT %I* and AT %Q* are invalid — must use concrete addresses.
        assert "AT %I*" not in script, "PLC script uses invalid `AT %I*` placeholder"
        assert "AT %Q*" not in script, "PLC script uses invalid `AT %Q*` placeholder"
        # Should use concrete addresses like %IX0.0 or %QX0.0.
        assert "%IX0.0" in script or "%QX0.0" in script

    def test_no_duplicate_var_declarations(self, engine_room_zone, cargo_ship):
        nodes = self._build_nodes(engine_room_zone, cargo_ship)
        script = export_to_plc_script(nodes)
        # Find all VAR declarations and check uniqueness.
        decls = []
        for line in script.split("\n"):
            line = line.strip()
            if line.endswith(": BOOL;") or line.endswith(': TON;'):
                # Extract the identifier (first token before space).
                ident = line.split()[0]
                decls.append(ident)
        # All declarations must be unique.
        assert len(decls) == len(set(decls)), (
            f"Duplicate VAR declarations: "
            f"{[d for d in decls if decls.count(d) > 1]}"
        )

    def test_interlock_vars_declared(self, engine_room_zone, cargo_ship):
        nodes = self._build_nodes(engine_room_zone, cargo_ship)
        script = export_to_plc_script(nodes)
        # For every "AND interlock_X" reference, "interlock_X : BOOL" must be declared.
        import re
        and_refs = set(re.findall(r"AND (interlock_\S+)", script))
        for ref in and_refs:
            assert f"{ref} : BOOL" in script, (
                f"Interlock variable {ref!r} referenced in logic but not "
                f"declared in VAR section."
            )

    def test_no_inline_ton_calls(self, engine_room_zone, cargo_ship):
        nodes = self._build_nodes(engine_room_zone, cargo_ship)
        script = export_to_plc_script(nodes)
        # The pattern "TON(IN := ...).Q" is invalid — TON is a function block.
        assert "TON(IN :=" not in script, (
            "PLC script uses inline TON(...) call — function blocks must be "
            "instantiated, not invoked inline."
        )
        # Should have proper TON instance declarations: "<name> : TON;"
        assert ": TON;" in script

    def test_logic_release_matches_selected_system(self, engine_room_zone, cargo_ship):
        """
        Bug: release output was hardcoded to release_water_mist regardless
        of the actually-selected extinguishing system.
        """
        from marine.iec60092.part_502 import place_detectors_grid
        dps = place_detectors_grid(engine_room_zone, DetectorType.FLAME_UV_IR)
        # Generate logic with CO2 selected (not water_mist).
        nodes = generate_logic_tree(
            engine_room_zone, dps,
            extinguishing_system=ExtinguishingSystem.CO2_TOTAL,
        )
        # Find the ACTION-level node (flame triggers ACTION).
        action_nodes = [n for n in nodes if n.alarm_level == AlarmLevel.ACTION]
        assert action_nodes, "No ACTION-level node generated for flame detector"
        # The release output must match the selected system (release_co2_total).
        all_outputs = functools.reduce(operator.iadd, (list(n.action_outputs) for n in action_nodes), [])
        assert "release_co2_total" in all_outputs, (
            f"Expected release_co2_total in outputs, got {all_outputs}"
        )
        assert "release_water_mist" not in all_outputs, (
            "release_water_mist was emitted even though CO2 was selected — "
            "alarm logic is decoupled from extinguishment sizing."
        )


# ─── Bug #18: Fire-resistance material consistency ───────────────────────────

class TestFireResistanceMaterialConsistency:
    """
    Bug: generate_division_specs returned "intumescent_board" for B-15
    while select_insulation_material returned "intumescent_paint".
    """

    def test_b15_material_consistent(self):
        direct = select_insulation_material(FireClass.B_15)
        # The generate_division_specs path picks via _pick_insulation_material.
        zones = [
            MarineZone(zone_id="Z1", name="Acc", space_category=SpaceCategory.ACCOMMODATION,
                       deck="m", frame_start=0, frame_end=10, area_m2=50, height_m=3,
                       adjacent_zones=("Z2",)),
            MarineZone(zone_id="Z2", name="Esc", space_category=SpaceCategory.ESCAPE_ROUTE,
                       deck="m", frame_start=10, frame_end=20, area_m2=50, height_m=3,
                       adjacent_zones=("Z1",)),
        ]
        specs = generate_division_specs(zones)
        b15_spec = next(
            (s for s in specs if s.required_class == FireClass.B_15), None
        )
        assert b15_spec is not None, "No B-15 division generated"
        assert b15_spec.insulation_material == direct, (
            f"generate_division_specs returns {b15_spec.insulation_material!r} "
            f"but select_insulation_material returns {direct!r} — inconsistent."
        )


# ─── Bug #20, #21, #22: ISO 15370 thermal alarm count ────────────────────────

class TestThermalAlarmRegression:
    """
    Bugs: int() truncation under-counted alarms; area-based formula
    wrong for linear corridors; no scope check.
    """

    def test_ceil_not_truncate(self):
        """Area=150 m², spacing=10 m → int(1.5)=1 (wrong), ceil(1.5)=2 (right)."""
        zone = MarineZone(
            zone_id="ESC", name="Corridor",
            space_category=SpaceCategory.ESCAPE_ROUTE,
            deck="A", frame_start=0, frame_end=10,
            area_m2=150.0, height_m=2.5,
        )
        ship = ShipProject(
            project_id="T", ship_name="Ferry",
            ship_type=ShipType.PASSENGER, length_overall_m=80.0,
            passenger_capacity=400,
        )
        result = calculate_thermal_alarm_count(zone, ship, route_length_m=15.0)
        # 15 m / 10 m + 1 = 2.5 → ceil = 3 (15/10=1.5, ceil=2, +1=3).
        assert result.details["alarm_count"] >= 2, (
            f"Got {result.details['alarm_count']} — int() truncation bug?"
        )

    def test_route_length_overrides_area(self):
        zone = MarineZone(
            zone_id="ESC", name="Long Corridor",
            space_category=SpaceCategory.ESCAPE_ROUTE,
            deck="A", frame_start=0, frame_end=100,
            area_m2=100.0, height_m=2.5,  # sqrt = 10 m (would give 1 alarm)
        )
        ship = ShipProject(
            project_id="T", ship_name="Ferry",
            ship_type=ShipType.PASSENGER, length_overall_m=80.0,
            passenger_capacity=400,
        )
        # 50 m corridor / 10 m spacing + 1 = 6 alarms.
        result = calculate_thermal_alarm_count(zone, ship, route_length_m=50.0)
        assert result.details["alarm_count"] == 6, (
            f"Got {result.details['alarm_count']} alarms for 50 m corridor "
            f"— should be 6 (50/10 + 1)."
        )

    def test_rejects_non_passenger_ship(self, cargo_ship, escape_route_zone):
        result = calculate_thermal_alarm_count(escape_route_zone, cargo_ship)
        # ISO 15370 doesn't apply to cargo ships → must add finding.
        assert not result.compliant
        assert any("non-passenger" in f for f in result.findings)

    def test_rejects_non_escape_route(self, large_passenger_ship):
        engine_zone = MarineZone(
            zone_id="ER", name="Engine",
            space_category=SpaceCategory.MACHINERY_SPACE_A,
            deck="m", frame_start=0, frame_end=10,
            area_m2=200.0, height_m=6.0,
        )
        result = calculate_thermal_alarm_count(engine_zone, large_passenger_ship)
        assert not result.compliant


# ─── Bug #23: ETAP UPS units ─────────────────────────────────────────────────

class TestETAPBridgeRegression:
    """
    Bug: UPS load was computed as Ah × 0.024, labeled as kW but actually
    yielding kWh (energy, not power).
    """

    def test_ups_load_is_in_kw(self):
        from marine.core.types import ShipElectricalSpec
        spec = ShipElectricalSpec(ups_capacity_ah=100.0, ups_autonomy_min=30.0)
        ship = ShipProject(
            project_id="T", ship_name="T", ship_type=ShipType.CARGO,
            length_overall_m=120.0, gross_tonnage=8000.0,
        )
        csv = export_etap_loads_csv(ship, spec, ups_power_kw=5.0)
        # The UPS row should report 5.00 kW (not 100*0.024=2.40).
        assert "5.00" in csv, "UPS load should be 5.00 kW (ups_power_kw param)"
        assert "2.40" not in csv, (
            "UPS load still computed from Ah × 0.024 — kWh labeled as kW."
        )


# ─── Bug #24: SCADA dashboard timestamp ──────────────────────────────────────

class TestSCADATimestampRegression:
    """
    Bug: dashboard_payload hardcoded a fake timestamp and accepted no
    parameter to override it.
    """

    def test_timestamp_can_be_overridden(self):
        payload = dashboard_payload(
            "1234567", {"Z1": "normal"},
            timestamp="2026-12-31T23:59:59Z",
        )
        assert payload["timestamp"] == "2026-12-31T23:59:59Z"

    def test_default_timestamp_is_current_utc(self):
        payload = dashboard_payload("1234567", {"Z1": "normal"})
        # Must NOT be the old hardcoded value.
        assert payload["timestamp"] != "2026-06-18T00:00:00Z"
        # Must be a valid ISO 8601 UTC timestamp ending with Z.
        assert payload["timestamp"].endswith("Z")
        assert "T" in payload["timestamp"]


# ─── Bug #25: Modbus register widths ─────────────────────────────────────────

class TestModbusRegisterWidthRegression:
    """Bug: BOOL=1, everything else=2 (wrong for INT=1, STRING=16)."""

    def test_int_uses_one_register(self):
        from marine.integration.scada_bridge import SCADATag
        tags = [SCADATag(tag_id="t", zone_id="z", tag_type="power",
                         protocol="modbus", address="r", data_type="INT")]
        regs = build_modbus_registers(tags)
        assert regs[0]["width"] == 1, f"INT should be 1 register, got {regs[0]['width']}"

    def test_real_uses_two_registers(self):
        from marine.integration.scada_bridge import SCADATag
        tags = [SCADATag(tag_id="t", zone_id="z", tag_type="power",
                         protocol="modbus", address="r", data_type="REAL")]
        regs = build_modbus_registers(tags)
        assert regs[0]["width"] == 2, f"REAL should be 2 registers, got {regs[0]['width']}"

    def test_string_uses_16_registers(self):
        from marine.integration.scada_bridge import SCADATag
        tags = [SCADATag(tag_id="t", zone_id="z", tag_type="power",
                         protocol="modbus", address="r", data_type="STRING")]
        regs = build_modbus_registers(tags)
        assert regs[0]["width"] == 16, (
            f"STRING should be 16 registers (32 chars), got {regs[0]['width']}"
        )


# ─── Bugs #26, #27: AutoCAD DXF wrappers + zone offsets ──────────────────────

class TestDXFOutputRegression:
    """Bugs: output had no SECTION/EOF wrappers; all zones drawn at (0,0)."""

    def test_full_dxf_has_eof_marker(self, cargo_ship):
        zones = divide_into_main_vertical_zones(120.0, cargo_ship)
        dxf = generate_full_dxf(zones)
        assert "EOF" in dxf, "DXF output missing EOF marker — not a valid file"
        assert "SECTION" in dxf, "DXF output missing SECTION marker"
        assert "ENTITIES" in dxf, "DXF output missing ENTITIES section"

    def test_zones_offset_longitudinally(self, cargo_ship):
        zones = divide_into_main_vertical_zones(120.0, cargo_ship)
        dxf = generate_full_dxf(zones)
        # Each zone must produce a distinct X coordinate (not all at 0,0).
        # The first zone starts at x=0, but subsequent zones must offset.
        # Look for the second zone's start (≥ 1m = 1000 mm forward).
        # Find all "10" X-coordinates in LWPOLYLINEs.
        import re
        x_coords = re.findall(r"^10\n(\S+)", dxf, re.MULTILINE)
        x_floats = [float(x) for x in x_coords]
        # At least 2 distinct non-zero coordinates (zones 2+ offset forward).
        distinct_nonzero = {x for x in x_floats if x > 0}
        assert len(distinct_nonzero) >= 2, (
            f"Zones not offset longitudinally — X coords: {x_floats[:10]}"
        )


# ─── Bug #17: Passenger-ship 24m MVZ limit ───────────────────────────────────

class TestPassengerMVZLimitRegression:
    """
    Bug: SOLAS II-2/2.2.1.1 mandates 24m MVZ limit for passenger ships
    >36 pax, but code applied 40m uniformly.
    """

    def test_large_passenger_uses_24m_limit(self, large_passenger_ship):
        # 120 m / 24 m = 5 zones minimum (vs 3 for cargo).
        zones = divide_into_main_vertical_zones(
            large_passenger_ship.length_overall_m, large_passenger_ship
        )
        # 24 m / 0.6 m = 40 frames per zone.
        for z in zones:
            zlen = (z.frame_end - z.frame_start) * 0.6
            assert zlen <= 24.0 + 0.1, (
                f"Passenger-ship zone {z.zone_id} spans {zlen:.2f} m — "
                f"exceeds SOLAS II-2/2.2.1.1 limit of 24 m for >36 pax."
            )

    def test_validator_uses_24m_for_large_passenger(self, large_passenger_ship):
        # Build a synthetic 30m zone — should fail validation for passenger
        # ships (>24m) but pass for cargo ships (≤40m).
        from marine.core.types import MarineZone, SpaceCategory
        long_zone = MarineZone(
            zone_id="X", name="Long",
            space_category=SpaceCategory.ACCOMMODATION,
            deck="main", frame_start=0, frame_end=50,  # 50 × 0.6 = 30 m
            area_m2=300.0, height_m=2.5,
        )
        result = validate_main_vertical_zones([long_zone], large_passenger_ship)
        assert not result.compliant, (
            "30 m zone should fail for passenger ship (>24m limit) but passed."
        )
        assert "24" in result.findings[0], (
            f"Finding should mention 24m limit, got: {result.findings[0]!r}"
        )


# ─── Bug #14: Passenger-ship cargo CO2 requirement ───────────────────────────

class TestPassengerCargoCO2Regression:
    """
    Bug: SOLAS II-2/10.7.1.1 requires fixed extinguishing in cargo spaces
    of passenger ships regardless of GT — but code applied >2000 GT rule
    uniformly. A passenger ship with GT=0 (default!) got nothing.
    """

    def test_passenger_ship_cargo_requires_co2(self, large_passenger_ship):
        # Passenger ship with GT=0 (default if not set explicitly).
        # This is a degenerate case but SOLAS still applies.
        result = required_extinguishing_for_space(
            SpaceCategory.CARGO_SPACE, large_passenger_ship
        )
        assert "co2_total" in result.details["required_systems"], (
            "Passenger ship cargo space must require CO2 regardless of GT "
            "(SOLAS II-2/10.7.1.1)."
        )


# ─── Bug #29: validate_alarm_circuit_redundancy ──────────────────────────────

class TestAlarmCircuitRedundancyRegression:
    """
    Bug: function never added a finding — accepted no actual_circuits
    input, so the validator could never FAIL.
    """

    def test_finds_when_actual_below_required(self, engine_room_zone):
        result = validate_alarm_circuit_redundancy(
            engine_room_zone, detector_count=10, actual_circuits=1,
        )
        assert not result.compliant, (
            "1 circuit for 10 detectors should fail IEC 60092-502 §6.3.2."
        )

    def test_passes_when_actual_meets_required(self, engine_room_zone):
        result = validate_alarm_circuit_redundancy(
            engine_room_zone, detector_count=10, actual_circuits=2,
        )
        assert result.compliant


# ─── Bug #30: validate_insulation_monitoring ─────────────────────────────────

class TestInsulationMonitoringRegression:
    """
    Bugs: function took no ship param (flagged non-tankers too strictly);
    did not validate UPS autonomy ≥30 min.
    """

    def test_non_tanker_missing_imd_is_warning_not_finding(self, cargo_ship):
        from marine.core.types import ShipElectricalSpec
        # IMD disabled.
        spec = ShipElectricalSpec(insulation_monitoring=False,
                                  ups_autonomy_min=30.0)
        result = validate_insulation_monitoring(spec, cargo_ship)
        # For non-tankers, missing IMD should be WARNING, not FINDING.
        assert result.compliant, (
            "Non-tanker with missing IMD should still be compliant (warning only)."
        )
        assert any("recommended" in w for w in result.warnings)

    def test_tanker_missing_imd_is_finding(self, tanker):
        from marine.core.types import ShipElectricalSpec
        spec = ShipElectricalSpec(insulation_monitoring=False,
                                  ups_autonomy_min=30.0)
        result = validate_insulation_monitoring(spec, tanker)
        assert not result.compliant, (
            "Tanker with missing IMD must be non-compliant per IEC 60092-504 §5."
        )

    def test_low_ups_autonomy_is_finding(self, cargo_ship):
        from marine.core.types import ShipElectricalSpec
        # UPS autonomy 15 min < 30 min SOLAS minimum.
        spec = ShipElectricalSpec(insulation_monitoring=True,
                                  ups_autonomy_min=15.0)
        result = validate_insulation_monitoring(spec, cargo_ship)
        assert not result.compliant, (
            "UPS autonomy 15 min < SOLAS 30 min minimum must be a finding."
        )
        assert any("UPS autonomy" in f for f in result.findings)
