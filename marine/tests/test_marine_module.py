# NOSONAR
"""
marine/tests/test_marine_module.py — Tests for the marine fire-safety module.
Covers: SOLAS compliance, IEC 60092 detector selection, fire-resistance
classification, extinguishment sizing, alarm-logic generation, and SCADA
integration. Follows property-based + unit-test patterns per agent.md Rule 10.
"""
from __future__ import annotations

import pytest

from marine.core.types import (
    DetectorType,
    ExtinguishingSystem,
    FireClass,
    MarineZone,
    ShipProject,
    ShipType,
    SpaceCategory,
)
from marine.engine.alarm_logic import export_to_plc_script, generate_logic_tree
from marine.engine.extinguishment import size_system
from marine.engine.fire_resistance import generate_division_specs
from marine.engine.zone_mapper import divide_into_main_vertical_zones
from marine.iec60092.part_502 import calculate_detector_count, select_detector_type
from marine.iec60092.part_504 import classify_hazardous_zone
from marine.integration.scada_bridge import build_mqtt_topics
from marine.solas.chapter_ii_2 import (
    required_fire_class_between,
    validate_escape_routes,
    validate_main_vertical_zones,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def cargo_ship() -> ShipProject:
    return ShipProject(
        project_id="TEST-001", ship_name="Test Cargo",
        ship_type=ShipType.CARGO, length_overall_m=120.0,
        gross_tonnage=8000.0,
    )


@pytest.fixture
def passenger_ship() -> ShipProject:
    return ShipProject(
        project_id="TEST-002", ship_name="Test Ferry",
        ship_type=ShipType.PASSENGER, length_overall_m=80.0,
        passenger_capacity=400,
    )


@pytest.fixture
def tanker() -> ShipProject:
    return ShipProject(
        project_id="TEST-003", ship_name="Test Tanker",
        ship_type=ShipType.TANKER, length_overall_m=180.0,
        gross_tonnage=25000.0,
    )


@pytest.fixture
def engine_room_zone() -> MarineZone:
    return MarineZone(
        zone_id="ER-01", name="Engine Room", space_category=SpaceCategory.MACHINERY_SPACE_A,
        deck="engine_room", frame_start=50, frame_end=80,
        area_m2=200.0, height_m=6.0,
    )


@pytest.fixture
def accommodation_zone() -> MarineZone:
    return MarineZone(
        zone_id="ACC-01", name="Cabin Block", space_category=SpaceCategory.ACCOMMODATION,
        deck="A-deck", frame_start=10, frame_end=40,
        area_m2=150.0, height_m=2.5,
    )


# ─── SOLAS Compliance Tests ─────────────────────────────────────────────────

class TestSOLASCompliance:
    def test_passenger_ship_detected(self, passenger_ship):
        assert passenger_ship.is_passenger_ship is True
        assert passenger_ship.passenger_capacity > 12

    def test_tanker_detected(self, tanker):
        assert tanker.is_tanker is True

    def test_small_craft_detected(self):
        small = ShipProject(
            project_id="S-001", ship_name="Yacht",
            ship_type=ShipType.SMALL_CRAFT, length_overall_m=18.0,
        )
        assert small.is_small_craft is True

    def test_mvz_division_cargo(self, cargo_ship):
        zones = divide_into_main_vertical_zones(cargo_ship.length_overall_m, cargo_ship)
        # 120 m / 40 m max → ≥3 zones
        assert len(zones) >= 3
        for z in zones:
            assert z.frame_end > z.frame_start

    def test_mvz_division_passenger(self, passenger_ship):
        zones = divide_into_main_vertical_zones(passenger_ship.length_overall_m, passenger_ship)
        assert len(zones) >= 2

    def test_mvz_validation_passes(self, cargo_ship):
        zones = divide_into_main_vertical_zones(cargo_ship.length_overall_m, cargo_ship)
        result = validate_main_vertical_zones(zones, cargo_ship)
        assert result.compliant is True
        assert len(result.findings) == 0

    def test_escape_route_validation(self, cargo_ship):
        zones = divide_into_main_vertical_zones(cargo_ship.length_overall_m, cargo_ship)
        result = validate_escape_routes(zones)
        # Auto-generated zones have escape routes (default True).
        assert result.compliant is True

    def test_fire_class_machinery_to_accommodation(self):
        cls = required_fire_class_between(
            SpaceCategory.MACHINERY_SPACE_A, SpaceCategory.ACCOMMODATION
        )
        assert cls == FireClass.A_60

    def test_fire_class_cargo_to_escape(self):
        cls = required_fire_class_between(
            SpaceCategory.CARGO_SPACE, SpaceCategory.ESCAPE_ROUTE
        )
        assert cls == FireClass.A_60

    def test_fire_class_accommodation_to_escape(self):
        cls = required_fire_class_between(
            SpaceCategory.ACCOMMODATION, SpaceCategory.ESCAPE_ROUTE
        )
        assert cls == FireClass.B_15


# ─── Fire Class Hierarchy Tests ─────────────────────────────────────────────

class TestFireClassHierarchy:
    def test_insulation_minutes(self):
        assert FireClass.A_60.insulation_minutes == 60
        assert FireClass.A_30.insulation_minutes == 30
        assert FireClass.A_0.insulation_minutes == 0
        assert FireClass.B_15.insulation_minutes == 15

    def test_all_classes_present(self):
        classes = {c.value for c in FireClass}
        assert classes == {"A-60", "A-30", "A-15", "A-0", "B-15", "B-0", "C"}


# ─── IEC 60092-502 Detector Tests ───────────────────────────────────────────

class TestDetectorSelection:
    def test_engine_room_triple_detection(self, engine_room_zone, cargo_ship):
        result = select_detector_type(engine_room_zone, cargo_ship)
        types = result.details["selected_types"]
        # Machinery A requires heat + flame + smoke.
        assert "heat_fixed" in types
        assert "flame_uv_ir" in types
        assert "smoke_photo" in types

    def test_accommodation_smoke(self, accommodation_zone, cargo_ship):
        result = select_detector_type(accommodation_zone, cargo_ship)
        assert "smoke_photo" in result.details["selected_types"]

    def test_passenger_accommodation_adds_co(self, accommodation_zone, passenger_ship):
        result = select_detector_type(accommodation_zone, passenger_ship)
        types = result.details["selected_types"]
        assert "smoke_photo" in types
        assert "co" in types  # passenger ship → CO early warning

    def test_tanker_engine_room_adds_aspirating(self, engine_room_zone, tanker):
        result = select_detector_type(engine_room_zone, tanker)
        assert "aspirating" in result.details["selected_types"]

    def test_detector_count_calculation(self, engine_room_zone):
        result = calculate_detector_count(engine_room_zone, DetectorType.HEAT_FIXED)
        # 200 m² / 37 m² per detector = ~6 + 10% spares
        assert result.details["detector_count"] >= 6


# ─── Fire Resistance Tests ──────────────────────────────────────────────────

class TestFireResistance:
    def test_division_specs_generated(self, cargo_ship):
        zones = divide_into_main_vertical_zones(cargo_ship.length_overall_m, cargo_ship)
        specs = generate_division_specs(zones)
        assert len(specs) > 0
        for s in specs:
            assert s.required_class in FireClass
            assert s.from_zone != s.to_zone

    def test_machinery_division_is_a60(self):
        zones = [
            MarineZone(zone_id="Z1", name="ER", space_category=SpaceCategory.MACHINERY_SPACE_A,
                       deck="main", frame_start=0, frame_end=50, area_m2=100, height_m=3,
                       adjacent_zones=("Z2",)),
            MarineZone(zone_id="Z2", name="Acc", space_category=SpaceCategory.ACCOMMODATION,
                       deck="main", frame_start=50, frame_end=100, area_m2=100, height_m=3,
                       adjacent_zones=("Z1",)),
        ]
        specs = generate_division_specs(zones)
        assert any(s.required_class == FireClass.A_60 for s in specs)


# ─── Extinguishment Tests ───────────────────────────────────────────────────

class TestExtinguishingSizing:
    def test_water_mist_for_engine_room(self, engine_room_zone, cargo_ship):
        design = size_system(engine_room_zone, cargo_ship)
        assert design.system_type == ExtinguishingSystem.WATER_MIST
        assert design.agent_quantity_kg > 0
        assert design.hold_time_min >= 30.0  # MSC.1/Circ.1165

    def test_co2_for_cargo_space(self, cargo_ship):
        zone = MarineZone(
            zone_id="CARGO-01", name="Cargo Hold",
            space_category=SpaceCategory.CARGO_SPACE,
            deck="lower_hold", frame_start=0, frame_end=100,
            area_m2=400.0, height_m=4.0,
        )
        design = size_system(zone, cargo_ship)
        assert design.system_type == ExtinguishingSystem.CO2_TOTAL
        assert design.design_concentration_pct >= 30.0
        assert design.hold_time_min >= 20.0  # MSC.1/Circ.1316

    def test_inert_gas_for_tanker(self, tanker):
        zone = MarineZone(
            zone_id="TANK-01", name="Cargo Tank",
            space_category=SpaceCategory.TANK_SPACE,
            deck="tank_deck", frame_start=0, frame_end=80,
            area_m2=300.0, height_m=15.0,
        )
        design = size_system(zone, tanker)
        assert design.system_type == ExtinguishingSystem.INERT_GAS
        assert design.design_concentration_pct == pytest.approx(8.0)

    def test_sprinkler_for_passenger_accommodation(self, passenger_ship, accommodation_zone):
        design = size_system(accommodation_zone, passenger_ship)
        assert design.system_type == ExtinguishingSystem.SPRINKLER
        assert design.nozzles >= 1


# ─── Alarm Logic Tests ──────────────────────────────────────────────────────

class TestAlarmLogic:
    def test_logic_tree_generated(self, engine_room_zone, cargo_ship):
        from marine.iec60092.part_502 import place_detectors_grid
        dps = place_detectors_grid(engine_room_zone, DetectorType.HEAT_FIXED)
        nodes = generate_logic_tree(engine_room_zone, dps)
        assert len(nodes) == len(dps)
        for n in nodes:
            assert n.zone_id == engine_room_zone.zone_id
            assert len(n.action_outputs) > 0

    def test_plc_script_export(self, engine_room_zone, cargo_ship):
        from marine.iec60092.part_502 import place_detectors_grid
        dps = place_detectors_grid(engine_room_zone, DetectorType.HEAT_FIXED)
        nodes = generate_logic_tree(engine_room_zone, dps)
        script = export_to_plc_script(nodes)
        assert "PROGRAM FireAlarmLogic" in script
        assert "END_PROGRAM" in script
        assert "IF" in script


# ─── IEC 60092-504 Hazardous Zone Tests ─────────────────────────────────────

class TestHazardousZones:
    def test_tanker_tank_space_is_zone0(self, tanker):
        zone = MarineZone(
            zone_id="T1", name="Cargo Tank", space_category=SpaceCategory.TANK_SPACE,
            deck="tanks", frame_start=0, frame_end=80, area_m2=200, height_m=10,
        )
        result = classify_hazardous_zone(zone, tanker)
        assert result.details["zone_classification"] == "zone_0"

    def test_cargo_ship_accommodation_non_hazardous(self, cargo_ship, accommodation_zone):
        result = classify_hazardous_zone(accommodation_zone, cargo_ship)
        assert result.details["zone_classification"] == "non_hazardous"


# ─── SCADA Integration Tests ────────────────────────────────────────────────

class TestSCADAIntegration:
    def test_mqtt_topics_generated(self):
        tags = build_mqtt_topics("1234567", ["Z1", "Z2"])
        # 2 zones × 2 (alarm + extinguish) + 2 ship-level (UPS + insulation) = 6
        assert len(tags) == 6
        for t in tags:
            assert t.protocol == "mqtt"
            assert "ship/1234567/" in t.address

    def test_topic_naming_convention(self):
        tags = build_mqtt_topics("9999999", ["ER-01"])
        alarm_tag = next(t for t in tags if t.tag_type == "alarm")
        assert alarm_tag.address == "ship/9999999/fire/alarm/ER-01"


# ─── Property-Based Tests (Hypothesis) ──────────────────────────────────────

def _hypothesis_available() -> bool:
    try:
        import hypothesis  # noqa: F401
        return True
    except ImportError:
        return False


class TestPropertyBased:
    @pytest.mark.skipif(
        not _hypothesis_available(),
        reason="hypothesis not installed",
    )
    def test_mvz_count_always_within_limit(self, cargo_ship):
        from hypothesis import given
        from hypothesis import strategies as st

        @given(length_m=st.floats(min_value=20.0, max_value=400.0))
        def _inner(length_m):
            zones = divide_into_main_vertical_zones(length_m, cargo_ship)
            for z in zones:
                zone_len = (z.frame_end - z.frame_start) * 0.6
                assert zone_len <= 40.0 + 0.1  # tolerance
        _inner()
