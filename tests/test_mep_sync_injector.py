"""
Tests for mep_sync_injector.py — MEP Interface Module Synchronizer
===================================================================
Comprehensive test suite covering:
    - Validation (NaN, duplicates, AHU capacity, elevator designated floor)
    - AHU shutdown above 2000 CFM threshold (NFPA 90A §6.4.1)
    - FCU below threshold (no shutdown required)
    - Elevator recall (Phase I designated/alternate, Phase II NOT auto-enabled)
    - Suppression monitoring (NFPA 72 §21.4)
    - Egress control (NFPA 101 §7.2.1)
    - BOQ integration
    - Loop device format compatibility
"""

import math
import pytest

from fireai.core.mep_sync_injector import (
    AHU_CFM_THRESHOLD,
    MEP_UNIT_COSTS,
    ModuleType,
    MEPElementType,
    AddressType,
    ElevatorPhase,
    MEPElement,
    ElevatorRecallSpec,
    HVACShutdownSpec,
    MEPInterfaceModule,
    MEPSyncResult,
    validate_mep_elements,
    extend_boq_with_mep_modules,
    MEPSyncInjector,
)


# ============================================================================
# Validation Tests
# ============================================================================

class TestValidateMEPElements:
    """Test validate_mep_elements() — input validation."""

    def test_valid_elements_no_errors(self):
        """Valid elements should produce no errors."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                capacity_cfm=5000.0,
            ),
            MEPElement(
                element_id="ELEV-1",
                element_type=MEPElementType.ELEVATOR,
                designated_floor="LOBBY",
            ),
        ]
        errors = validate_mep_elements(elements)
        assert errors == []

    def test_nan_location_detected(self):
        """NaN values in location should be detected."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                location=(float("nan"), 0.0),
                capacity_cfm=3000.0,
            ),
        ]
        errors = validate_mep_elements(elements)
        assert len(errors) == 1
        assert "NaN" in errors[0] or "nan" in errors[0].lower()

    def test_inf_capacity_detected(self):
        """Inf values in capacity should be detected."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                capacity_cfm=float("inf"),
            ),
        ]
        errors = validate_mep_elements(elements)
        assert len(errors) >= 1
        assert any("Inf" in e or "inf" in e.lower() for e in errors)

    def test_duplicate_element_ids(self):
        """Duplicate element IDs should be detected."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                capacity_cfm=3000.0,
            ),
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                capacity_cfm=5000.0,
            ),
        ]
        errors = validate_mep_elements(elements)
        assert any("Duplicate" in e for e in errors)

    def test_ahu_zero_capacity_error(self):
        """AHU with zero capacity should produce an error."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                capacity_cfm=0.0,
            ),
        ]
        errors = validate_mep_elements(elements)
        assert any("capacity_cfm" in e for e in errors)

    def test_elevator_empty_designated_floor(self):
        """Elevator without designated_floor should produce an error."""
        elements = [
            MEPElement(
                element_id="ELEV-1",
                element_type=MEPElementType.ELEVATOR,
                designated_floor="",
            ),
        ]
        errors = validate_mep_elements(elements)
        assert any("designated_floor" in e for e in errors)

    def test_empty_elements_list(self):
        """Empty elements list should produce no errors."""
        errors = validate_mep_elements([])
        assert errors == []


# ============================================================================
# AHU Tests
# ============================================================================

class TestAHUProcessing:
    """Test AHU processing — NFPA 90A §6.4.1."""

    def test_ahu_above_threshold_requires_shutdown(self):
        """AHU above 2000 CFM must have shutdown module."""
        elements = [
            MEPElement(
                element_id="AHU-BIG",
                element_type=MEPElementType.AHU,
                capacity_cfm=5000.0,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        assert result.total_ahu_shutdowns == 1
        hvac_specs = result.hvac_specs
        assert len(hvac_specs) == 1
        assert hvac_specs[0].requires_shutdown is True
        assert hvac_specs[0].requires_duct_detector is True

    def test_ahu_below_threshold_no_shutdown(self):
        """AHU below 2000 CFM does NOT require shutdown."""
        elements = [
            MEPElement(
                element_id="AHU-SMALL",
                element_type=MEPElementType.AHU,
                capacity_cfm=1500.0,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        assert result.total_ahu_shutdowns == 0
        hvac_specs = result.hvac_specs
        assert len(hvac_specs) == 1
        assert hvac_specs[0].requires_shutdown is False

    def test_ahu_at_threshold_boundary(self):
        """AHU at exactly 2000 CFM does NOT require shutdown (> not >=)."""
        elements = [
            MEPElement(
                element_id="AHU-EXACT",
                element_type=MEPElementType.AHU,
                capacity_cfm=AHU_CFM_THRESHOLD,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        # > 2000 triggers shutdown, == 2000 does not
        assert result.total_ahu_shutdowns == 0

    def test_ahu_above_threshold_generates_modules(self):
        """AHU above threshold generates both shutdown and supervisory modules."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                capacity_cfm=3000.0,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        module_types = [m.module_type for m in result.interface_modules]
        assert ModuleType.HVAC_SHUTDOWN in module_types
        assert ModuleType.SUPERVISORY in module_types

    def test_ahu_cfm_threshold_value(self):
        """AHU_CFM_THRESHOLD must be 2000.0 per NFPA 90A §6.4.1."""
        assert AHU_CFM_THRESHOLD == 2000.0


# ============================================================================
# FCU Tests
# ============================================================================

class TestFCUProcessing:
    """Test FCU processing — below threshold, no shutdown required."""

    def test_fcu_below_threshold_no_shutdown(self):
        """FCU below 2000 CFM does NOT require shutdown per NFPA 90A."""
        elements = [
            MEPElement(
                element_id="FCU-1",
                element_type=MEPElementType.FCU,
                capacity_cfm=800.0,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        assert result.total_ahu_shutdowns == 0

    def test_fcu_above_threshold_requires_shutdown(self):
        """FCU above 2000 CFM DOES require shutdown (same as AHU)."""
        elements = [
            MEPElement(
                element_id="FCU-BIG",
                element_type=MEPElementType.FCU,
                capacity_cfm=3000.0,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        assert result.total_ahu_shutdowns == 1


# ============================================================================
# Elevator Recall Tests
# ============================================================================

class TestElevatorRecall:
    """Test elevator recall — NFPA 72 §21.3."""

    def test_elevator_generates_recall_module(self):
        """Elevator element should generate an ELEVATOR_RECALL module."""
        elements = [
            MEPElement(
                element_id="ELEV-A",
                element_type=MEPElementType.ELEVATOR,
                elevator_bank="BANK-1",
                designated_floor="LOBBY_GROUND",
                alternate_floor="FLOOR_3",
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        assert result.total_elevator_banks == 1
        assert len(result.interface_modules) == 1
        assert result.interface_modules[0].module_type == ModuleType.ELEVATOR_RECALL

    def test_elevator_phase_i_spec(self):
        """ElevatorRecallSpec should have correct Phase I floors."""
        elements = [
            MEPElement(
                element_id="ELEV-A",
                element_type=MEPElementType.ELEVATOR,
                elevator_bank="BANK-1",
                designated_floor="LOBBY_GROUND",
                alternate_floor="FLOOR_3",
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        spec = result.elevator_specs[0]
        assert spec.designated_floor == "LOBBY_GROUND"
        assert spec.alternate_floor == "FLOOR_3"
        assert spec.phase_i_nfpa_ref == "NFPA 72-2022 §21.3.4/§21.3.7"

    def test_phase_ii_not_auto_enabled(self):
        """Phase II must NOT be auto-enabled per §21.3.8 / ASME A17.1.

        CRITICAL: This is a life-safety requirement. Phase II
        (firefighter's service) requires PE verification.
        Auto-enabling it would be DANGEROUS.
        """
        elements = [
            MEPElement(
                element_id="ELEV-A",
                element_type=MEPElementType.ELEVATOR,
                designated_floor="LOBBY",
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        spec = result.elevator_specs[0]
        assert spec.phase_ii_enabled is False
        assert "ASME A17.1" in spec.phase_ii_nfpa_ref

    def test_elevator_no_bank_warning(self):
        """Elevator without elevator_bank should produce a warning."""
        elements = [
            MEPElement(
                element_id="ELEV-NOBANK",
                element_type=MEPElementType.ELEVATOR,
                designated_floor="LOBBY",
                elevator_bank="",
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        assert any("elevator_bank" in w for w in result.warnings)


# ============================================================================
# Suppression Tests
# ============================================================================

class TestSuppressionMonitoring:
    """Test suppression monitoring — NFPA 72 §21.4."""

    def test_sprinkler_generates_monitor_module(self):
        """Sprinkler system should generate SUPPRESSION_MONITOR module."""
        elements = [
            MEPElement(
                element_id="SPRK-1",
                element_type=MEPElementType.SPRINKLER_SYSTEM,
                sprinkler_system_id="SYSTEM-A",
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        modules = result.interface_modules
        assert any(m.module_type == ModuleType.SUPPRESSION_MONITOR for m in modules)
        monitor = next(m for m in modules if m.module_type == ModuleType.SUPPRESSION_MONITOR)
        assert "§21.4" in monitor.nfpa_reference


# ============================================================================
# Egress Tests
# ============================================================================

class TestEgressControl:
    """Test egress control — NFPA 101 §7.2.1."""

    def test_fire_rated_door_generates_egress_module(self):
        """Fire-rated egress door should generate EGRESS_CONTROL module."""
        elements = [
            MEPElement(
                element_id="DOOR-1",
                element_type=MEPElementType.EGRESS_DOOR,
                is_fire_rated=True,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        modules = result.interface_modules
        assert any(m.module_type == ModuleType.EGRESS_CONTROL for m in modules)

    def test_non_fire_rated_door_warning(self):
        """Non-fire-rated egress door should produce a warning."""
        elements = [
            MEPElement(
                element_id="DOOR-NONRATED",
                element_type=MEPElementType.EGRESS_DOOR,
                is_fire_rated=False,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        assert any("fire-rated" in w for w in result.warnings)


# ============================================================================
# BOQ Integration Tests
# ============================================================================

class TestBOQIntegration:
    """Test BOQ generation from MEP sync results."""

    def test_extend_boq_generates_items(self):
        """extend_boq_with_mep_modules should generate costed BOQ items."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                capacity_cfm=5000.0,
            ),
            MEPElement(
                element_id="ELEV-1",
                element_type=MEPElementType.ELEVATOR,
                designated_floor="LOBBY",
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()
        boq_items = extend_boq_with_mep_modules(result)

        assert len(boq_items) > 0
        # Should have items for elevator recall and HVAC shutdown
        item_types = [i["item_type"] for i in boq_items]
        assert any("elevator" in t for t in item_types)
        assert any("hvac" in t for t in item_types)

    def test_boq_items_have_costs(self):
        """BOQ items should have non-zero unit costs."""
        elements = [
            MEPElement(
                element_id="ELEV-1",
                element_type=MEPElementType.ELEVATOR,
                designated_floor="LOBBY",
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()
        boq_items = extend_boq_with_mep_modules(result)

        for item in boq_items:
            assert item["unit_cost_usd"] > 0
            assert item["total_cost_usd"] > 0

    def test_boq_duct_detectors_for_hvac(self):
        """BOQ should include duct detectors for AHUs above threshold."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                capacity_cfm=5000.0,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()
        boq_items = extend_boq_with_mep_modules(result)

        item_types = [i["item_type"] for i in boq_items]
        assert any("duct" in t for t in item_types)


# ============================================================================
# Loop Device Format Tests
# ============================================================================

class TestLoopDeviceFormat:
    """Test as_loop_device_dict() compatibility with fault_isolator_injector."""

    def test_interface_module_as_loop_device(self):
        """MEPInterfaceModule should produce loop-compatible device dict."""
        module = MEPInterfaceModule(
            module_id="ELEV-RECALL-1",
            module_type=ModuleType.ELEVATOR_RECALL,
            target_element_id="ELEV-1",
            zone_id="Z1",
            floor_id="F1",
        )
        device = module.as_loop_device_dict()

        assert "device_type" in device
        assert "device_idx" in device
        assert "position" in device
        assert "zone_id" in device
        assert device["device_type"] == "MEP_ELEVATOR_RECALL"
        assert device["zone_id"] == "Z1"

    def test_interface_module_compatible_with_fault_isolator(self):
        """Module device dicts should work with fault_isolator_injector."""
        from fireai.core.fault_isolator_injector import verify_isolator_compliance

        modules = [
            MEPInterfaceModule(
                module_id=f"MOD-{i}",
                module_type=ModuleType.HVAC_SHUTDOWN,
                target_element_id=f"AHU-{i}",
                zone_id="Z1",
            ).as_loop_device_dict()
            for i in range(5)
        ]
        # Should not crash when passed to fault isolator
        result = verify_isolator_compliance(modules)
        assert isinstance(result, dict)


# ============================================================================
# Full Sync Tests
# ============================================================================

class TestFullSync:
    """Test complete MEPSyncInjector.sync() workflow."""

    def test_sync_with_validation_errors(self):
        """Sync should return errors when validation fails."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                location=(float("nan"), 0.0),
                capacity_cfm=3000.0,
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        assert len(result.errors) > 0
        assert result.total_modules == 0

    def test_sync_mixed_elements(self):
        """Sync should process a mix of MEP element types."""
        elements = [
            MEPElement(
                element_id="AHU-1",
                element_type=MEPElementType.AHU,
                capacity_cfm=3000.0,
                zone_id="Z1",
            ),
            MEPElement(
                element_id="ELEV-1",
                element_type=MEPElementType.ELEVATOR,
                designated_floor="LOBBY",
                elevator_bank="B1",
                zone_id="Z1",
            ),
            MEPElement(
                element_id="SPRK-1",
                element_type=MEPElementType.SPRINKLER_SYSTEM,
                zone_id="Z1",
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        assert result.total_modules >= 3  # At least one per element
        assert result.total_elevator_banks == 1
        assert result.total_ahu_shutdowns == 1
        assert len(result.errors) == 0

    def test_damper_generates_supervisory_module(self):
        """Smoke/fire damper should generate SUPERVISORY module."""
        elements = [
            MEPElement(
                element_id="DAMPER-1",
                element_type=MEPElementType.SMOKE_DAMPER,
                zone_id="Z1",
            ),
        ]
        injector = MEPSyncInjector(elements)
        result = injector.sync()

        modules = result.interface_modules
        assert any(m.module_type == ModuleType.SUPERVISORY for m in modules)
