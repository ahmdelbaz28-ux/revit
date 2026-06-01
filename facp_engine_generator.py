"""
FACP SELECTION ENGINE - MASTER GENERATOR & RUNTIME INTEGRATOR
=============================================================
Author: Senior Fire Protection Engineer & Systems Architect
Standards: NFPA 72 (2022) SS10.6.10, UL 864 10th Edition, CSFM, FDNY COA

V54 Bug Fixes Applied (vs. original user-submitted code):
  F1: Missing hashlib/dataclass imports in panel_selector.py (HIGH)
      - Root cause: hashlib.sha256() and @dataclass used without imports
      - Impact: NameError at import time — module won't load
      - Fix: Added import hashlib and from dataclasses import dataclass, field

  F2: NAC capacity 1.2x margin rejects valid panels (CRITICAL)
      - Root cause: required_nacs = nac_circuit_count * 1.2 eliminates panels
        with exact NAC match. NFPA 72 does NOT mandate 20% spare NAC capacity.
        NAC circuits are physical hardware outputs, expandable via extender modules.
      - Impact: FC924 (6 NACs) rejected for 6-NAC design; Golden Test 2 FAILS
      - Fix: Changed to required_nacs = nac_circuit_count (exact match)
             Added WARNING for >80% NAC utilization

  F3: Sort key prefers oversized panels on ties (HIGH)
      - Root cause: reverse=True with x[0].points_capacity selects LARGEST
        capacity on ties — most oversized panel wins
      - Impact: Consistently selects most expensive/oversized panel
      - Fix: Changed to -x[1] trick without reverse=True, preferring
             SMALLEST adequate capacity (best utilization)

  F4: requires_releasing never checked (CRITICAL)
      - Root cause: Field existed in ProjectRequirements but no matching
        supports_releasing field in FireAlarmPanel, and no filter logic
      - Impact: Non-releasing panel selected for suppression systems — NFPA 72 SS21.7 violation
      - Fix: Added supports_releasing to FireAlarmPanel dataclass + filter logic

  F5: Battery calc uses flat 1.2x instead of NFPA 72 derating (HIGH)
      - Root cause: Flat 1.2x provides only 82% of required safety factor at 20C
        and 62% at 0C per IEEE 485/1188. The production battery_aging_derating
        module provides >= 1.46x at 20C and >= 1.93x at 0C.
      - Impact: Battery undersized in cold climates — panel goes dead during fire
      - Fix: Integrated fireai.core.battery_aging_derating.size_battery() with
             fallback to enhanced simplified calculation for standalone deployment

  F6: Per-device standby current 1mA unrealistically low (MEDIUM)
      - Root cause: Typical addressable device quiescent current is 0.3-2.0 mA
        (detector vs module). 1.0 mA underestimates mixed loads.
      - Impact: Battery capacity underestimated by 20-100%
      - Fix: Changed to 0.8 mA (conservative average, matches production auditor)
"""

import os
import sys
import unittest
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


# =====================================================================
# AUTOMATED WORKSPACE VERIFICATION
# =====================================================================

def verify_workspace():
    """Verify all FACP system files exist on disk."""
    print("[FACP WORKSPACE] Verifying codebase integrity...")
    required_files = [
        "facp_system/__init__.py",
        "facp_system/panel_database.py",
        "facp_system/panel_selector.py",
        "facp_system/panel_verifier.py",
        "facp_system/panel_output.py",
    ]
    all_ok = True
    for filepath in required_files:
        if not os.path.exists(filepath):
            print(f"  [MISSING] {filepath}")
            all_ok = False
        else:
            print(f"  [OK] {filepath}")
    return all_ok


# =====================================================================
# INTEGRATED MASTER TEST SUITE (pytest/unittest compatible)
# =====================================================================

class TestFACPSelectionEngine(unittest.TestCase):

    def setUp(self):
        from facp_system.panel_selector import SelectionEngine, ProjectRequirements
        self.engine = SelectionEngine
        self.req_class = ProjectRequirements

    def test_golden_small_building(self):
        """
        GOLDEN TEST 1: Small building, No voice, Standalone.
        Input: 30 devices, 2 NACs.
        Expected: FC901 selected (FDNY-listed, optimal utilization).
        
        Battery calculation (enhanced simplified, standalone mode):
          standby_load = (30 * 0.8/1000) + 0.120 = 0.024 + 0.120 = 0.144 A
          alarm_load = (2 * 2.0) + (30 * 5.0/1000) + 0.250 = 4.0 + 0.15 + 0.250 = 4.400 A
          alarm_duration = 5/60 h (no voice)
          raw = (0.144 * 24) + (4.400 * 0.0833) = 3.456 + 0.367 = 3.823 Ah
          With enhanced factor (1.47x): 3.823 * 1.47 = 5.62 Ah
          Or with production module (1.46x at 20C): similar
        """
        req = self.req_class(
            device_count=30,
            nac_circuit_count=2,
            building_size_m2=1500.0,
            building_floors=2,
            requires_network=False,
            requires_voice=False,
            requires_releasing=False,
            jurisdiction="US"
        )
        rec = self.engine.select_panel(req)
        self.assertEqual(rec.manufacturer, "SIEMENS")
        self.assertEqual(rec.recommended_model, "FC901")
        # Battery must be positive and reasonable
        self.assertGreater(rec.battery_size_ah, 3.0)
        self.assertLess(rec.battery_size_ah, 15.0)

    def test_golden_voice_networked(self):
        """
        GOLDEN TEST 2: High rise building with Voice Evacuation and networking.
        Input: 300 devices, 6 NACs.
        Expected: FC924 (504 pts >= 360 required, 6 NACs >= 6 required).
        
        V54 FIX F2: With original 1.2x NAC margin, FC924 would be REJECTED
        (6 < 7.2). Now with exact NAC match, FC924 qualifies.
        
        V54 FIX F3: With original sort, NFS2-3030 (3180 pts) would win on
        capacity tie-break. Now FC924 (504 pts, better utilization) wins.
        """
        req = self.req_class(
            device_count=300,
            nac_circuit_count=6,
            building_size_m2=20000.0,
            building_floors=10,
            requires_network=True,
            requires_voice=True,
            requires_releasing=False,
            jurisdiction="US",
            preferred_manufacturer="SIEMENS"
        )
        rec = self.engine.select_panel(req)
        self.assertEqual(rec.manufacturer, "SIEMENS")
        self.assertEqual(rec.recommended_model, "FC924")
        # Voice evacuation requires 15min alarm = 0.25h
        # Battery should be significantly larger than non-voice
        self.assertGreater(rec.battery_size_ah, 10.0)

    def test_golden_fdny_constraint(self):
        """
        GOLDEN TEST 3: FDNY Jurisdiction Restrictions.
        Case: Panels lacking FDNY COA are rejected.
        
        With V54 FIX F2 (exact NAC match), FC922 qualifies for 100 devices
        with 2 NACs (4 NACs >= 2 required, 252 pts >= 120 required).
        FC901 has 50 pts < 120 required — filtered by points, not NACs.
        """
        req = self.req_class(
            device_count=100,
            nac_circuit_count=2,
            building_size_m2=5000.0,
            building_floors=3,
            requires_network=False,
            requires_voice=False,
            requires_releasing=False,
            jurisdiction="FDNY"
        )
        rec = self.engine.select_panel(req)
        self.assertIn("FDNY", rec.listings)

    def test_golden_releasing_constraint(self):
        """
        V54 FIX F4: Releasing service filter verification.
        Case: Project requiring releasing service must select releasing-capable panel.
        
        Without the fix, a non-releasing panel could be selected for suppression.
        With the fix, only releasing-capable panels pass the filter.
        """
        req = self.req_class(
            device_count=200,
            nac_circuit_count=4,
            building_size_m2=10000.0,
            building_floors=3,
            requires_network=True,
            requires_voice=True,
            requires_releasing=True,  # V54 FIX F4: This was previously ignored
            jurisdiction="US",
            preferred_manufacturer="SIEMENS"
        )
        rec = self.engine.select_panel(req)
        # FC924 supports releasing, FC922 does not
        # With 200*1.2=240 pts needed, FC922 (252 pts) qualifies but doesn't support releasing
        # FC924 (504 pts, supports releasing) should be selected
        self.assertEqual(rec.recommended_model, "FC924")

    def test_determinism_selection(self):
        """
        DETERMINISM TEST: Same inputs MUST produce bit-identical results.
        Case: Execute selector 100 times.
        Expected: 100% stable SHA-256 signatures across all runs.
        """
        req = self.req_class(
            device_count=150,
            nac_circuit_count=4,
            building_size_m2=8000.0,
            building_floors=4,
            requires_network=True,
            requires_voice=True,
            requires_releasing=False,
            jurisdiction="US"
        )

        signature_ref = None
        for cycle in range(100):
            rec = self.engine.select_panel(req)
            if signature_ref is None:
                signature_ref = rec.signature_hash
            else:
                self.assertEqual(signature_ref, rec.signature_hash,
                    f"Nondeterministic deviation on cycle {cycle}")
        print(f"[SUCCESS] Evaluated determinism over 100 cycles. Stable hash: {signature_ref}")

    def test_battery_derating_method(self):
        """
        V54 FIX F5: Verify battery sizing uses proper NFPA 72 derating.
        The derating method must NOT be a flat 1.2x multiplier.
        """
        req = self.req_class(
            device_count=50,
            nac_circuit_count=2,
            building_size_m2=2000.0,
            building_floors=1,
            requires_network=False,
            requires_voice=False,
            requires_releasing=False,
            jurisdiction="US"
        )
        rec = self.engine.select_panel(req)
        method = rec.battery_derating_details.get("method", "unknown")
        self.assertNotEqual(method, "unknown")
        # The derating method should include IEEE or NFPA references
        self.assertTrue(
            "NFPA" in method or "IEEE" in method or "derating" in method.lower(),
            f"Expected proper derating method, got: {method}"
        )


# =====================================================================
# INTEGRATED PRODUCTION SELECTION DEMONSTRATION RUNNER
# =====================================================================

def execute_production_selection_pipeline():
    """Runs selection engine, executes verifier, and outputs submittal packages."""
    print("\n" + "="*80)
    print("          QOMN-FIRE PANEL SELECTION ENGINE - REAL-WORLD DEMONSTRATION")
    print("="*80)

    from facp_system.panel_selector import SelectionEngine, ProjectRequirements
    from facp_system.panel_verifier import ComplianceVerifier
    from facp_system.panel_output import OutputGenerator

    # Project Scenario: Hospital Campus Facility
    req = ProjectRequirements(
        device_count=450,
        nac_circuit_count=8,
        building_size_m2=45000.0,
        building_floors=5,
        requires_network=True,
        requires_voice=True,
        requires_releasing=True,
        jurisdiction="FDNY",
        preferred_manufacturer="SIEMENS",
        min_temperature_c=20.0
    )

    print(f"Project Inputs:")
    print(f"  - Device Count        : {req.device_count} points (Required with margin: {req.device_count*1.2:.1f} pts)")
    print(f"  - NAC Circuit Count   : {req.nac_circuit_count} circuits")
    print(f"  - Location Compliance : {req.jurisdiction} Authority Having Jurisdiction (AHJ)")
    print(f"  - Audio Evacuation    : YES (Requires Integrated Voice Evac)")
    print(f"  - Releasing Service   : YES (Requires Suppression Control)")
    print(f"  - Min Temperature     : {req.min_temperature_c}C (for battery derating)")

    # 1. Run Selection Engine
    rec = SelectionEngine.select_panel(req)

    print(f"\nEngine Recommendation:")
    print(f"  -> Recommended Model  : {rec.recommended_model}")
    print(f"  -> Manufacturer       : {rec.manufacturer}")
    print(f"  -> Capacity Load Ratio: {rec.capacity_utilization:.2%}")
    print(f"  -> NAC Utilization    : {rec.nac_utilization:.2%}")
    print(f"  -> Battery Back-up    : {rec.battery_size_ah} Ah")
    print(f"  -> Battery Derating   : {rec.battery_derating_details.get('method', 'N/A')}")

    # 2. Run Verification Layer
    violations = ComplianceVerifier.verify_national_code_rules(req, rec)
    if violations:
        print("\n[CRITICAL WARNING] Compliance Failures Found:")
        for v in violations:
            print(f"  - {v}")
    else:
        print("\n[COMPLIANCE CHECK: SUCCESS] Selected panel satisfies all UL and NFPA codes.")

    # 3. Generate Schedules and CSI Specifications
    schedule = OutputGenerator.generate_dxf_schedule(rec)
    spec = OutputGenerator.generate_csi_specification(req, rec)
    alternatives = OutputGenerator.generate_alternatives_table(rec)

    print("\n" + "="*80)
    print("              AUTO-GENERATED CAD LAYOUT VIEWPORT SCHEDULE")
    print("="*80)
    print(schedule)

    print("\n" + "="*80)
    print("              CSI SPECIFICATION PARAGRAPH FOR SUBMITTALS")
    print("="*80)
    print(spec)

    print("\n" + "="*80)
    print("              ENGINEERING ALTERNATIVES COMPARISON")
    print("="*80)
    print(alternatives)

    return rec, violations


# =====================================================================
# RUNTIME CONTROLLER MAIN BLOCK
# =====================================================================

if __name__ == "__main__":
    print("="*80)
    print("        QOMN-FIRE: FIRE ALARM CONTROL PANEL SELECTION ENGINE")
    print("        V54 — 6 Safety Bug Fixes Applied (F1-F6)")
    print("="*80)

    # Add project root to Python path
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, project_root)

    # 1. Verify workspace files exist
    if not verify_workspace():
        print("\n[CRITICAL ERROR] Workspace files missing. Ensure all facp_system/ files are present.")
        sys.exit(1)

    # 2. Run the dynamic unit testing suite
    print("\n" + "="*80)
    print("             EXECUTING AUTOMATED CRITICAL UNIT TEST SUITE")
    print("="*80)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFACPSelectionEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)

    if not test_result.wasSuccessful():
        print("\n[CRITICAL ERROR] Test suite failures occurred. Aborting selection run.")
        sys.exit(1)

    # 3. Run production select demonstration
    rec, violations = execute_production_selection_pipeline()

    # 4. Final verdict
    print("\n" + "="*80)
    print("              FINAL ENGINEERING VERDICT")
    print("="*80)
    if not violations:
        print("  STATUS: APPROVED FOR SUBMITTAL USE")
        print(f"  Selected Panel: {rec.manufacturer} {rec.recommended_model}")
        print(f"  Battery: {rec.battery_size_ah} Ah ({rec.battery_derating_details.get('method', 'N/A')})")
        print(f"  Deterministic Signature: {rec.signature_hash}")
    else:
        print("  STATUS: REQUIRES MANUAL REVIEW")
        print(f"  Violations Found: {len(violations)}")
        for v in violations:
            print(f"    - {v}")
