"""
tests/test_fault_isolator_injector.py
======================================
Comprehensive test suite for:
  - fireai/core/fault_isolator_injector.py

SAFETY CRITICAL: Without fault isolators, a single short circuit on an SLC
loop can disable ALL 250 devices — leaving an entire building without fire
detection. This module injects fault isolators to prevent catastrophic failure.

NFPA 72 References:
  - §12.3.1: Fault isolation required on addressable circuits
  - §12.3.2: A single fault must not affect more than one zone
  - §21.4: Class A circuit requirements
  - Annex A.12.3.1: Fault isolation architecture explanatory material
"""

from __future__ import annotations

import pytest

from fireai.core.fault_isolator_injector import (
    DEFAULT_MAX_DEVICES_BETWEEN_ISOLATORS,
    ISOLATOR_DEVICE_TYPE,
    NFPA_CITATION_ISOLATION,
    NFPA_CITATION_ZONE_LIMIT,
    IsolatorInjectionResult,
    IsolatorPlacement,
    inject_fault_isolators,
    verify_isolator_compliance,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants Verification
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    """Verify NFPA 72 constants."""

    def test_default_max_devices_32(self):
        """Conservative engineering limit of 32 devices between isolators."""
        assert DEFAULT_MAX_DEVICES_BETWEEN_ISOLATORS == 32

    def test_isolator_device_type(self):
        assert ISOLATOR_DEVICE_TYPE == "FAULT_ISOLATOR"

    def test_nfpa_citation_isolation(self):
        assert "§12.3.1" in NFPA_CITATION_ISOLATION

    def test_nfpa_citation_zone_limit(self):
        assert "§12.3.2" in NFPA_CITATION_ZONE_LIMIT


# ─────────────────────────────────────────────────────────────────────────────
# IsolatorPlacement Dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestIsolatorPlacement:
    """Isolator placement record dataclass."""

    def test_placement_fields(self):
        p = IsolatorPlacement(
            position_index=5,
            position_xy=(10.0, 20.0),
            reason="Zone boundary",
            nfpa_citation=NFPA_CITATION_ISOLATION,
            zone_id_before="Z1",
            zone_id_after="Z2",
        )
        assert p.position_index == 5
        assert p.position_xy == (10.0, 20.0)
        assert p.reason == "Zone boundary"
        assert p.zone_id_before == "Z1"
        assert p.zone_id_after == "Z2"


# ─────────────────────────────────────────────────────────────────────────────
# IsolatorInjectionResult Dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestIsolatorInjectionResult:
    """Injection result dataclass."""

    def test_result_fields(self):
        r = IsolatorInjectionResult(
            original_device_count=10,
            injected_isolator_count=2,
            total_device_count=12,
            secure_loop=[],
            isolator_placements=[],
        )
        assert r.original_device_count == 10
        assert r.injected_isolator_count == 2
        assert r.total_device_count == 12
        assert r.is_compliant is False  # V112: FAIL-SAFE default

    def test_default_is_compliant_false(self):
        """V112: FAIL-SAFE — starts NOT compliant until verified."""
        r = IsolatorInjectionResult(
            original_device_count=0,
            injected_isolator_count=0,
            total_device_count=0,
            secure_loop=[],
            isolator_placements=[],
        )
        assert r.is_compliant is False

    def test_default_violations_empty(self):
        r = IsolatorInjectionResult(
            original_device_count=0,
            injected_isolator_count=0,
            total_device_count=0,
            secure_loop=[],
            isolator_placements=[],
        )
        assert r.violations == []


# ─────────────────────────────────────────────────────────────────────────────
# inject_fault_isolators — Empty Input
# ─────────────────────────────────────────────────────────────────────────────


class TestInjectFaultIsolatorsEmpty:
    """Edge case: empty loop devices."""

    def test_empty_loop(self):
        result = inject_fault_isolators(loop_devices=[])
        assert result.original_device_count == 0
        assert result.injected_isolator_count == 0
        assert result.total_device_count == 0
        assert result.secure_loop == []
        assert result.isolator_placements == []


# ─────────────────────────────────────────────────────────────────────────────
# inject_fault_isolators — Entry Point Isolator
# ─────────────────────────────────────────────────────────────────────────────


class TestEntryPointIsolator:
    """Rule 1: Always insert an isolator at the first device (loop entry point)."""

    def test_single_device_gets_entry_isolator(self):
        """Even a single device should get an entry point isolator."""
        result = inject_fault_isolators(
            loop_devices=[{"device_idx": "D1", "zone_id": "Z1"}],
        )
        assert result.injected_isolator_count >= 1
        # First item in secure_loop should be an isolator
        assert result.secure_loop[0]["device_type"] == ISOLATOR_DEVICE_TYPE

    def test_entry_isolator_reason(self):
        """Entry point isolator should cite NFPA 72 §12.3.1."""
        result = inject_fault_isolators(
            loop_devices=[{"device_idx": "D1"}],
        )
        first_placement = result.isolator_placements[0]
        assert NFPA_CITATION_ISOLATION in first_placement.reason

    def test_entry_isolator_at_first_device_position(self):
        """Entry point isolator should be at the first device's position."""
        result = inject_fault_isolators(
            loop_devices=[{"device_idx": "D1", "position": (5.0, 10.0)}],
        )
        first_placement = result.isolator_placements[0]
        assert first_placement.position_xy == (5.0, 10.0)


# ─────────────────────────────────────────────────────────────────────────────
# inject_fault_isolators — Zone Boundary Injection
# ─────────────────────────────────────────────────────────────────────────────


class TestZoneBoundaryInjection:
    """Rule 2: Insert isolator at zone boundary per NFPA 72 §12.3.2."""

    def test_zone_boundary_triggers_isolator(self):
        """Device in different zone than previous → isolator injected."""
        result = inject_fault_isolators(
            loop_devices=[
                {"device_idx": "D1", "zone_id": "Z1"},
                {"device_idx": "D2", "zone_id": "Z1"},
                {"device_idx": "D3", "zone_id": "Z2"},  # Zone boundary
            ],
        )
        # Should have: ISO(entry), D1, D2, ISO(zone boundary), D3
        assert result.injected_isolator_count >= 2
        # Check that zone boundary placement exists
        zone_isos = [p for p in result.isolator_placements if "Zone boundary" in p.reason]
        assert len(zone_isos) >= 1

    def test_same_zone_no_extra_isolator(self):
        """Devices in the same zone should not trigger extra isolators."""
        result = inject_fault_isolators(
            loop_devices=[
                {"device_idx": "D1", "zone_id": "Z1"},
                {"device_idx": "D2", "zone_id": "Z1"},
                {"device_idx": "D3", "zone_id": "Z1"},
            ],
        )
        # Should only have entry point isolator (no zone boundaries)
        assert result.injected_isolator_count == 1

    def test_zone_map_lookup(self):
        """Zone map should be used when devices lack zone_id key."""
        zone_map = {"D1": "Z1", "D2": "Z1", "D3": "Z2"}
        result = inject_fault_isolators(
            loop_devices=[
                {"id": "D1"},
                {"id": "D2"},
                {"id": "D3"},
            ],
            zone_map=zone_map,
        )
        zone_isos = [p for p in result.isolator_placements if "Zone boundary" in p.reason]
        assert len(zone_isos) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# inject_fault_isolators — Device Count Injection
# ─────────────────────────────────────────────────────────────────────────────


class TestDeviceCountInjection:
    """Rule 3: Max devices between isolators limit."""

    def test_exceeding_max_devices_triggers_isolator(self):
        """More than max_devices_between_isolators → extra isolator injected."""
        # 10 devices, max 5 between isolators
        devices = [{"device_idx": f"D{i}", "zone_id": "Z1"} for i in range(10)]
        result = inject_fault_isolators(
            loop_devices=devices,
            max_devices_between_isolators=5,
        )
        # Entry point (1) + device count triggers (at least 1)
        assert result.injected_isolator_count >= 2

    def test_exactly_max_devices_no_extra_isolator(self):
        """Exactly max devices → no extra isolator (boundary is >=)."""
        devices = [{"device_idx": f"D{i}", "zone_id": "Z1"} for i in range(5)]
        result = inject_fault_isolators(
            loop_devices=devices,
            max_devices_between_isolators=5,
        )
        # Should only have entry point isolator
        assert result.injected_isolator_count == 1

    def test_custom_max_devices(self):
        """Custom max_devices_between_isolators should be respected."""
        devices = [{"device_idx": f"D{i}", "zone_id": "Z1"} for i in range(20)]
        result = inject_fault_isolators(
            loop_devices=devices,
            max_devices_between_isolators=10,
        )
        assert result.injected_isolator_count >= 2


# ─────────────────────────────────────────────────────────────────────────────
# inject_fault_isolators — Class A Return Point
# ─────────────────────────────────────────────────────────────────────────────


class TestClassAReturnPoint:
    """Class A loops get an additional isolator at the return point."""

    def test_class_a_gets_return_isolator(self):
        """class_a=True → extra isolator at loop return point."""
        devices = [{"device_idx": f"D{i}", "zone_id": "Z1"} for i in range(3)]
        result_class_a = inject_fault_isolators(loop_devices=devices, class_a=True)
        result_class_b = inject_fault_isolators(loop_devices=devices, class_a=False)
        assert result_class_a.injected_isolator_count > result_class_b.injected_isolator_count

    def test_class_a_return_isolator_at_last_device_position(self):
        """Return point isolator should be at the last device's position."""
        devices = [
            {"device_idx": "D1", "position": (0.0, 0.0)},
            {"device_idx": "D2", "position": (10.0, 0.0)},
            {"device_idx": "D3", "position": (20.0, 0.0)},
        ]
        result = inject_fault_isolators(loop_devices=devices, class_a=True)
        last_placement = result.isolator_placements[-1]
        assert "Class A" in last_placement.reason or "return" in last_placement.reason.lower()
        assert last_placement.position_xy == (20.0, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# inject_fault_isolators — Secure Loop Structure
# ─────────────────────────────────────────────────────────────────────────────


class TestSecureLoopStructure:
    """Verify the structure of the secure loop output."""

    def test_secure_loop_contains_original_devices(self):
        """All original devices must appear in the secure loop."""
        devices = [{"device_idx": f"D{i}"} for i in range(5)]
        result = inject_fault_isolators(loop_devices=devices)
        original_ids = {d["device_idx"] for d in devices}
        loop_ids = {d.get("device_idx") for d in result.secure_loop if d.get("device_type") != ISOLATOR_DEVICE_TYPE}
        assert original_ids.issubset(loop_ids)

    def test_secure_loop_contains_isolators(self):
        """Isolators must be present in the secure loop."""
        devices = [{"device_idx": f"D{i}"} for i in range(5)]
        result = inject_fault_isolators(loop_devices=devices)
        isolators = [d for d in result.secure_loop if d.get("device_type") == ISOLATOR_DEVICE_TYPE]
        assert len(isolators) >= 1

    def test_isolator_dict_structure(self):
        """Each injected isolator should have required keys."""
        devices = [{"device_idx": "D1"}]
        result = inject_fault_isolators(loop_devices=devices)
        isolator = next(d for d in result.secure_loop if d.get("device_type") == ISOLATOR_DEVICE_TYPE)
        assert "device_type" in isolator
        assert "device_idx" in isolator
        assert "position" in isolator
        assert "is_injector_inserted" in isolator
        assert isolator["is_injector_inserted"] is True
        assert isolator["device_type"] == ISOLATOR_DEVICE_TYPE

    def test_total_device_count_matches(self):
        """total_device_count = original + injected."""
        devices = [{"device_idx": f"D{i}"} for i in range(10)]
        result = inject_fault_isolators(loop_devices=devices)
        assert result.total_device_count == result.original_device_count + result.injected_isolator_count


# ─────────────────────────────────────────────────────────────────────────────
# inject_fault_isolators — Compliance Verification
# ─────────────────────────────────────────────────────────────────────────────


class TestInjectionCompliance:
    """Verify the result is compliant after injection."""

    def test_small_loop_is_compliant(self):
        """Small loop with few devices should be compliant after injection."""
        devices = [{"device_idx": f"D{i}", "zone_id": "Z1"} for i in range(5)]
        result = inject_fault_isolators(loop_devices=devices)
        assert result.is_compliant is True

    def test_large_loop_compliant_with_isolators(self):
        """Large loop should be compliant after proper isolator injection."""
        devices = [{"device_idx": f"D{i}", "zone_id": "Z1"} for i in range(50)]
        result = inject_fault_isolators(loop_devices=devices, max_devices_between_isolators=32)
        assert result.is_compliant is True


# ─────────────────────────────────────────────────────────────────────────────
# inject_fault_isolators — Position Extraction
# ─────────────────────────────────────────────────────────────────────────────


class TestPositionExtraction:
    """Test position extraction from device dicts."""

    def test_position_tuple(self):
        """Position key with tuple should be extracted."""
        devices = [{"device_idx": "D1", "position": (5.0, 10.0)}]
        result = inject_fault_isolators(loop_devices=devices)
        assert result.secure_loop[0]["position"] == (5.0, 10.0)

    def test_position_list(self):
        """Position key with list should be extracted."""
        devices = [{"device_idx": "D1", "position": [5.0, 10.0]}]
        result = inject_fault_isolators(loop_devices=devices)
        assert result.secure_loop[0]["position"] == (5.0, 10.0)

    def test_xy_keys(self):
        """X and y keys should be extracted as fallback."""
        devices = [{"device_idx": "D1", "x": 5.0, "y": 10.0}]
        result = inject_fault_isolators(loop_devices=devices)
        assert result.secure_loop[0]["position"] == (5.0, 10.0)

    def test_no_position_defaults_to_zero(self):
        """Missing position should default to (0.0, 0.0)."""
        devices = [{"device_idx": "D1"}]
        result = inject_fault_isolators(loop_devices=devices)
        assert result.secure_loop[0]["position"] == (0.0, 0.0)


# verify_isolator_compliance
# ─────────────────────────────────────────────────────────────────────────────


class TestVerifyIsolatorCompliance:
    """Verify that an existing loop has adequate fault isolation."""

    def test_empty_loop_compliant(self):
        """Empty loop should be compliant."""
        result = verify_isolator_compliance(loop_devices=[])
        assert result["compliant"] is True
        assert result["max_segment_devices"] == 0

    def test_loop_with_isolators_compliant(self):
        """Loop with proper isolator spacing should be compliant."""
        loop = [
            {"device_type": "FAULT_ISOLATOR"},
            {"device_type": "detector"},
            {"device_type": "detector"},
            {"device_type": "FAULT_ISOLATOR"},
            {"device_type": "detector"},
        ]
        result = verify_isolator_compliance(loop_devices=loop)
        assert result["compliant"] is True
        assert result["isolator_count"] == 2

    def test_loop_without_isolators_not_compliant(self):
        """Loop without any isolators should not be compliant."""
        loop = [{"device_type": "detector"} for _ in range(10)]
        result = verify_isolator_compliance(loop_devices=loop)
        assert result["compliant"] is False
        assert result["isolator_count"] == 0

    def test_loop_with_too_many_devices_between_isolators(self):
        """Segment exceeding max devices → not compliant."""
        loop = [{"device_type": "FAULT_ISOLATOR"}] + [
            {"device_type": "detector"} for _ in range(40)
        ]
        result = verify_isolator_compliance(loop_devices=loop, max_devices_between_isolators=32)
        assert result["compliant"] is False
        assert result["max_segment_devices"] == 40

    def test_custom_max_devices(self):
        """Custom max_devices_between_isolators should be respected."""
        loop = [{"device_type": "FAULT_ISOLATOR"}] + [
            {"device_type": "detector"} for _ in range(10)
        ]
        result_strict = verify_isolator_compliance(loop_devices=loop, max_devices_between_isolators=5)
        result_lenient = verify_isolator_compliance(loop_devices=loop, max_devices_between_isolators=15)
        assert result_strict["compliant"] is False
        assert result_lenient["compliant"] is True

    def test_isolator_detected_by_name(self):
        """Isolator detection should work with 'ISOLATOR' in device_type."""
        loop = [
            {"device_type": "fault_isolator"},
            {"device_type": "detector"},
        ]
        result = verify_isolator_compliance(loop_devices=loop)
        assert result["isolator_count"] == 1

    def test_recommendation_field(self):
        """Result should have a recommendation string."""
        loop = [{"device_type": "FAULT_ISOLATOR"}, {"device_type": "detector"}]
        result = verify_isolator_compliance(loop_devices=loop)
        assert isinstance(result["recommendation"], str)

    def test_violations_list(self):
        """Non-compliant loops should have violations."""
        loop = [{"device_type": "detector"} for _ in range(5)]
        result = verify_isolator_compliance(loop_devices=loop)
        assert len(result["violations"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration — Realistic SLC Loop Scenario
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrationScenario:
    """End-to-end scenario: realistic SLC loop with mixed zones."""

    def test_office_floor_slc_loop(self):
        """Typical office floor: 3 zones, 40 devices, max 32 between isolators."""
        devices = []
        # Zone 1: 15 devices
        for i in range(15):
            devices.append({
                "device_idx": f"D{i:03d}",
                "zone_id": "ZONE-1",
                "position": (float(i * 3), 0.0),
            })
        # Zone 2: 20 devices
        for i in range(20):
            devices.append({
                "device_idx": f"D{i + 15:03d}",
                "zone_id": "ZONE-2",
                "position": (float((i + 15) * 3), 0.0),
            })
        # Zone 3: 10 devices
        for i in range(10):
            devices.append({
                "device_idx": f"D{i + 35:03d}",
                "zone_id": "ZONE-3",
                "position": (float((i + 35) * 3), 0.0),
            })

        result = inject_fault_isolators(
            loop_devices=devices,
            max_devices_between_isolators=32,
        )

        # Should have entry point + 2 zone boundaries = 3 isolators minimum
        assert result.injected_isolator_count >= 3
        assert result.is_compliant is True
        assert result.original_device_count == 45
        assert result.total_device_count == 45 + result.injected_isolator_count

        # Verify using compliance checker
        compliance = verify_isolator_compliance(
            loop_devices=result.secure_loop,
            max_devices_between_isolators=32,
        )
        assert compliance["compliant"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
