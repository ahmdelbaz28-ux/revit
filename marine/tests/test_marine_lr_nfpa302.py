"""
marine/tests/test_marine_lr_nfpa302.py — Tests for LR Rules and NFPA 302.

Covers the previously untested marine.lr_rules and marine.nfpa302 modules.
"""
from __future__ import annotations

import pytest

from marine.core.types import ShipProject, ShipType
from marine.lr_rules import (
    validate_detector_response_time,
    validate_fire_main_redundancy,
    validate_loop_capacity,
)
from marine.nfpa302 import (
    is_in_scope,
    required_portable_extinguishers,
    validate_galley_fixed_system,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def small_craft() -> ShipProject:
    return ShipProject(
        project_id="SC-001", ship_name="Test Yacht",
        ship_type=ShipType.SMALL_CRAFT, length_overall_m=18.0,
    )


@pytest.fixture
def large_craft() -> ShipProject:
    return ShipProject(
        project_id="SC-002", ship_name="Test Workboat",
        ship_type=ShipType.CARGO, length_overall_m=45.0,
    )


# ─── LR Rules Tests ─────────────────────────────────────────────────────────

class TestLRDetectorResponseTime:
    def test_compliant_response_time(self):
        result = validate_detector_response_time(15.0)
        assert result.compliant is True
        assert result.standard_reference == "LR Part 6 §2.4"
        assert not result.findings

    def test_excessive_response_time(self):
        result = validate_detector_response_time(45.0)
        assert result.compliant is False
        assert any("45.0s" in f for f in result.findings)
        assert any("30.0s" in f for f in result.findings)


class TestLRLoopCapacity:
    def test_compliant_loop_capacity(self):
        result = validate_loop_capacity(150)
        assert result.compliant is True
        assert not result.findings

    def test_excessive_loop_capacity(self):
        result = validate_loop_capacity(250)
        assert result.compliant is False
        assert any("250" in f for f in result.findings)
        assert any("200" in f for f in result.findings)


class TestLRFireMainRedundancy:
    def test_compliant_pump_count(self):
        result = validate_fire_main_redundancy(2)
        assert result.compliant is True
        assert not result.findings

    def test_insufficient_pump_count(self):
        result = validate_fire_main_redundancy(1)
        assert result.compliant is False
        assert any("1" in f for f in result.findings)
        assert any("2" in f for f in result.findings)


# ─── NFPA 302 Tests ─────────────────────────────────────────────────────────

class TestNFPA302PortableExtinguishers:
    def test_small_craft_below_26ft(self):
        result = required_portable_extinguishers(20.0)
        assert result.compliant is True
        assert result.details["min_rating"] == 5
        assert result.details["type"] == "B:C"

    def test_craft_between_26ft_and_40ft(self):
        result = required_portable_extinguishers(30.0)
        assert result.compliant is True
        assert result.details["min_rating"] == 10
        assert result.details["type"] == "B:C"

    def test_craft_between_40ft_and_65ft(self):
        result = required_portable_extinguishers(50.0)
        assert result.compliant is True
        assert result.details["min_rating"] == 20
        assert result.details["type"] == "B:C"

    def test_large_craft_above_65ft(self):
        result = required_portable_extinguishers(80.0)
        assert result.compliant is True
        assert result.details["min_rating"] == 40
        assert result.details["type"] == "B:C"

    def test_out_of_scope_length(self):
        result = required_portable_extinguishers(-1.0)
        assert result.compliant is True
        assert result.warnings
        assert any("outside NFPA 302 scope" in w for w in result.warnings)


class TestNFPA302GalleyFixedSystem:
    def test_galley_without_fixed_system(self):
        result = validate_galley_fixed_system(False)
        assert result.compliant is False
        assert result.findings

    def test_galley_with_fixed_system(self):
        result = validate_galley_fixed_system(True)
        assert result.compliant is True
        assert not result.findings


class TestNFPA302Scope:
    def test_small_craft_in_scope(self, small_craft):
        assert is_in_scope(small_craft) is True

    def test_large_craft_out_of_scope(self, large_craft):
        assert is_in_scope(large_craft) is False

    def test_small_cargo_by_length(self):
        ship = ShipProject(
            project_id="SC-003", ship_name="Small Cargo",
            ship_type=ShipType.CARGO, length_overall_m=20.0,
        )
        assert is_in_scope(ship) is True
