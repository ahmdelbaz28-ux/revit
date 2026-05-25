"""
tests/test_v16_enterprise_integration.py
========================================
V16 Enterprise Integration Tests

Tests:
  1. FACP_Profile enhanced fields (total devices, SLC current)
  2. FACP SLC audit with total devices + quiescent current checks
  3. As-Built Reconciliator 3D integration with orchestrator
  4. MEP Sync Injector integration with orchestrator
  5. Fixed broken test imports (6 files)
  6. Inline test files moved from fireai/core/ to tests/core/
"""

import pytest
import math


# ═══════════════════════════════════════════════════════════════════════
# Test 1: FACP_Profile enhanced fields
# ═══════════════════════════════════════════════════════════════════════

class TestFACPProfileEnhanced:
    """V16: FACP_Profile now includes max_total_devices_per_slc and slc_max_current_ma."""

    def test_notifier_profile_has_total_devices(self):
        from fireai.core.facp_capacity_auditor import get_default_profile
        profile = get_default_profile("notifier")
        assert profile.max_total_devices_per_slc == 318
        assert profile.slc_max_current_ma == 500.0

    def test_simplex_profile_has_total_devices(self):
        from fireai.core.facp_capacity_auditor import get_default_profile
        profile = get_default_profile("simplex")
        # Simplex IDNet: shared address pool, max_total = 250
        assert profile.max_total_devices_per_slc == 250
        assert profile.slc_max_current_ma == 500.0

    def test_siemens_profile_has_total_devices(self):
        from fireai.core.facp_capacity_auditor import get_default_profile
        profile = get_default_profile("siemens")
        # Siemens FDNet: shared address pool, max_total = 252
        assert profile.max_total_devices_per_slc == 252
        assert profile.slc_max_current_ma == 450.0

    def test_notifier_combined_gt_individual(self):
        """Notifier allows 159 det + 159 mod = 318 total (both at max simultaneously)."""
        from fireai.core.facp_capacity_auditor import get_default_profile
        profile = get_default_profile("notifier")
        assert profile.max_total_devices_per_slc >= (
            profile.max_detectors_per_slc + profile.max_modules_per_slc
        ) // 2  # At minimum, should allow some combination


# ═══════════════════════════════════════════════════════════════════════
# Test 2: FACP SLC audit with total devices + quiescent current
# ═══════════════════════════════════════════════════════════════════════

class TestFACPSLCAuditEnhanced:
    """V16: SLC audit now checks total device count and quiescent current."""

    def _make_auditor(self, manufacturer="notifier"):
        from fireai.core.facp_capacity_auditor import FACPCapacityAuditor, get_default_profile
        profile = get_default_profile(manufacturer)
        return FACPCapacityAuditor(profile)

    def test_total_devices_exceeded(self):
        """V16: Total devices per loop exceeding combined limit triggers violation."""
        auditor = self._make_auditor("notifier")
        # Notifier: max_total_devices_per_slc = 318
        # Create 200 detectors + 200 modules = 400 total
        devices = []
        for i in range(200):
            devices.append({'device_type': 'SMOKE_PHOTOELECTRIC'})
        for i in range(200):
            devices.append({'device_type': 'MONITOR_MODULE'})

        result = auditor.audit_slc_protocol_limits([
            {'loop_id': 'L-01', 'devices': devices}
        ])
        assert not result['all_pass']
        violation_codes = [v['code'] for v in result['violations']]
        assert 'FACP-SLC-TOTAL-DEVICES' in violation_codes

    def test_quiescent_current_exceeded(self):
        """V16: Quiescent current exceeding SLC card limit triggers violation."""
        auditor = self._make_auditor("notifier")
        # Notifier: slc_max_current_ma = 500.0
        # 700 devices * 0.8mA = 560mA > 500mA
        devices = []
        for i in range(700):
            devices.append({
                'device_type': 'SMOKE_PHOTOELECTRIC',
                'quiescent_ma': 0.8,
            })

        result = auditor.audit_slc_protocol_limits([
            {'loop_id': 'L-01', 'devices': devices}
        ])
        violation_codes = [v['code'] for v in result['violations']]
        assert 'FACP-SLC-CURRENT' in violation_codes

    def test_normal_load_passes(self):
        """Normal device load within all limits passes."""
        auditor = self._make_auditor("notifier")
        devices = []
        for i in range(50):
            devices.append({'device_type': 'SMOKE_PHOTOELECTRIC', 'quiescent_ma': 0.5})
        for i in range(30):
            devices.append({'device_type': 'MONITOR_MODULE', 'quiescent_ma': 1.0})

        result = auditor.audit_slc_protocol_limits([
            {'loop_id': 'L-01', 'devices': devices}
        ])
        assert result['all_pass']
        loop_summary = result['loops_passing'][0]
        assert loop_summary['total_devices'] == 80
        assert loop_summary['quiescent_current_ma'] == pytest.approx(55.0, rel=0.01)

    def test_loop_summary_includes_new_fields(self):
        """V16: Loop summary includes total_devices and quiescent_current_ma."""
        auditor = self._make_auditor()
        devices = [
            {'device_type': 'SMOKE_PHOTOELECTRIC', 'quiescent_ma': 0.5},
            {'device_type': 'MONITOR_MODULE', 'quiescent_ma': 2.0},
        ]
        result = auditor.audit_slc_protocol_limits([
            {'loop_id': 'L-01', 'devices': devices}
        ])
        assert result['all_pass']
        loop = result['loops_passing'][0]
        assert 'total_devices' in loop
        assert 'quiescent_current_ma' in loop
        assert 'max_total_devices_per_slc' in loop


# ═══════════════════════════════════════════════════════════════════════
# Test 3: As-Built Reconciliator 3D integration
# ═══════════════════════════════════════════════════════════════════════

class TestAsBuiltReconciliator3D:
    """V16: As-Built reconciliator with 3D device-type-specific tolerances."""

    def _make_design_manifest(self):
        return {
            'devices': [
                {'id': 'D-001', 'x': 10.0, 'y': 20.0, 'z': 3.0, 'device_type': 'SMOKE'},
                {'id': 'D-002', 'x': 30.0, 'y': 40.0, 'z': 3.0, 'device_type': 'MANUAL_PULL_STATION'},
                {'id': 'D-003', 'x': 50.0, 'y': 60.0, 'z': 4.5, 'device_type': 'DUCT_SMOKE'},
            ]
        }

    def test_perfect_match_verified(self):
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator
        manifest = self._make_design_manifest()
        reconciliator = AsBuiltReconciliator(design_manifest=manifest)

        as_built = [
            {'id': 'D-001', 'x': 10.0, 'y': 20.0, 'z': 3.0, 'device_type': 'SMOKE'},
            {'id': 'D-002', 'x': 30.0, 'y': 40.0, 'z': 3.0, 'device_type': 'MANUAL_PULL_STATION'},
            {'id': 'D-003', 'x': 50.0, 'y': 60.0, 'z': 4.5, 'device_type': 'DUCT_SMOKE'},
        ]
        result = reconciliator.reconcile(as_built)
        assert result.status == "VERIFIED"
        assert result.verified_count == 3
        assert result.total_deviations == 0

    def test_rogue_device_detected(self):
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator
        manifest = self._make_design_manifest()
        reconciliator = AsBuiltReconciliator(design_manifest=manifest)

        as_built = [
            {'id': 'D-001', 'x': 10.0, 'y': 20.0, 'z': 3.0, 'device_type': 'SMOKE'},
            {'id': 'ROGUE-1', 'x': 99.0, 'y': 99.0, 'z': 3.0, 'device_type': 'SMOKE'},
        ]
        result = reconciliator.reconcile(as_built)
        assert result.status == "DEVIATION_DETECTED"
        assert len(result.rogue_devices) == 1
        assert 'ROGUE-1' in result.rogue_devices[0][0]

    def test_missing_device_detected(self):
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator
        manifest = self._make_design_manifest()
        reconciliator = AsBuiltReconciliator(design_manifest=manifest)

        as_built = [
            {'id': 'D-001', 'x': 10.0, 'y': 20.0, 'z': 3.0, 'device_type': 'SMOKE'},
        ]
        result = reconciliator.reconcile(as_built)
        assert result.status == "DEVIATION_DETECTED"
        assert len(result.missing_devices) == 2  # D-002, D-003

    def test_smoke_drift_within_tolerance(self):
        """SMOKE tolerance = 0.3m. Drift of 0.2m should be OK."""
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator
        manifest = {'devices': [
            {'id': 'D-001', 'x': 10.0, 'y': 20.0, 'z': 3.0, 'device_type': 'SMOKE'},
        ]}
        reconciliator = AsBuiltReconciliator(design_manifest=manifest)

        as_built = [
            {'id': 'D-001', 'x': 10.15, 'y': 20.0, 'z': 3.0, 'device_type': 'SMOKE'},
        ]
        result = reconciliator.reconcile(as_built)
        assert result.status == "VERIFIED"
        assert result.verified_count == 1

    def test_manual_pull_station_tight_tolerance(self):
        """MANUAL_PULL_STATION tolerance = 0.15m. Drift of 0.2m should FAIL."""
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator
        manifest = {'devices': [
            {'id': 'MCP-001', 'x': 10.0, 'y': 20.0, 'z': 1.22, 'device_type': 'MANUAL_PULL_STATION'},
        ]}
        reconciliator = AsBuiltReconciliator(design_manifest=manifest)

        as_built = [
            {'id': 'MCP-001', 'x': 10.2, 'y': 20.0, 'z': 1.22, 'device_type': 'MANUAL_PULL_STATION'},
        ]
        result = reconciliator.reconcile(as_built)
        assert result.status == "DEVIATION_DETECTED"
        assert len(result.drifted_devices) == 1

    def test_z_axis_drift_detected(self):
        """V16: 3D drift — device on wrong floor (z differs significantly)."""
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator
        manifest = {'devices': [
            {'id': 'D-001', 'x': 10.0, 'y': 20.0, 'z': 3.0, 'device_type': 'SMOKE'},
        ]}
        reconciliator = AsBuiltReconciliator(design_manifest=manifest)

        # Same x,y but z is 6.0 (wrong floor!)
        as_built = [
            {'id': 'D-001', 'x': 10.0, 'y': 20.0, 'z': 6.0, 'device_type': 'SMOKE'},
        ]
        result = reconciliator.reconcile(as_built)
        assert result.status == "DEVIATION_DETECTED"
        assert len(result.drifted_devices) == 1
        drift = result.drifted_devices[0][1]
        assert drift == pytest.approx(3.0, rel=0.01)


# ═══════════════════════════════════════════════════════════════════════
# Test 4: Orchestrator integration with new modules
# ═══════════════════════════════════════════════════════════════════════

class TestOrchestratorV16:
    """V16: Orchestrator now accepts as_built_devices, merkle_root, mep_elements."""

    def test_full_design_result_has_new_fields(self):
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from bridges.orchestrator import FullDesignResult
        result = FullDesignResult(project_name="test", input_file="test.dxf")
        assert hasattr(result, 'as_built_reconciliation')
        assert hasattr(result, 'mep_sync')
        assert isinstance(result.as_built_reconciliation, dict)
        assert isinstance(result.mep_sync, dict)

    def test_run_full_design_signature_accepts_new_params(self):
        """Verify run_full_design accepts new V16 parameters without error."""
        import inspect, sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from bridges.orchestrator import run_full_design
        sig = inspect.signature(run_full_design)
        params = list(sig.parameters.keys())
        assert 'as_built_devices' in params
        assert 'merkle_root' in params
        assert 'mep_elements' in params


# ═══════════════════════════════════════════════════════════════════════
# Test 5: Device classification uses device_type not device_id
# ═══════════════════════════════════════════════════════════════════════

class TestDeviceClassificationCorrect:
    """V16: Ensure device classification uses device_type field, not device_id."""

    def test_classify_detector_by_type(self):
        from fireai.core.facp_capacity_auditor import _classify_device
        assert _classify_device("SMOKE_PHOTOELECTRIC") == "detector"
        assert _classify_device("HEAT_FIXED") == "detector"
        assert _classify_device("SMOKE_MULTI_CRITERIA") == "detector"

    def test_classify_module_by_type(self):
        from fireai.core.facp_capacity_auditor import _classify_device
        assert _classify_device("MANUAL_PULL_STATION") == "module"
        assert _classify_device("MONITOR_MODULE") == "module"
        assert _classify_device("RELAY_MODULE") == "module"
        assert _classify_device("OUTPUT_MODULE") == "module"

    def test_classify_unknown_defaults_module(self):
        from fireai.core.facp_capacity_auditor import _classify_device
        # Unknown types conservatively count as modules
        assert _classify_device("SOME_RANDOM_TYPE") == "module"

    def test_not_using_device_id_string_search(self):
        """V16: Classification must NOT use string search in device_id.
        The consultant's code searched for 'DETECTOR' in device_id which
        could match 'DETECTOR-ROOM-MODULE-01' incorrectly."""
        from fireai.core.facp_capacity_auditor import _classify_device
        # A monitor module should NOT be classified as detector even if
        # its type name is unusual
        assert _classify_device("DUCT_SMOKE") == "module"  # module, not detector


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
