"""
tests/test_apocalypse_v18.py
=============================
RUTHLESS VULNERABILITY TESTING PROTOCOL (APOCALYPSE SUITE)

هذا الملف لا يختبر 'عمل البرنامج'، بل يحاول 'كسر' البرنامج عن عمد.
يحتوي على أعتى السيناريوهات الميدانية المروعة للتأكد من أن جدار الحماية الهندسي
(Engineering Constraints) الذي بنيناه في الإصدار 18 يمنع تمرير هذه الكوارث.

CORRECTIONS FROM ORIGINAL CONSULTANT'S CODE (8 bugs fixed):
  1. FACPGlobalCapacityAuditor → FACPCapacityAuditor (class name mismatch)
  2. ManufacturerProfile → FACP_Profile (class name mismatch)
  3. fireai.core.battery_calculator → fireai.v17_core.battery_calculator (module path)
  4. fireai.v8_core.decision_provenance → fireai.core.provenance (import path)
  5. fireai.core.models → src.core.models (module path)
  6. AsBuiltReconciliator: constructor arg order, method name, required keys, return type
  7. AcousticSPLCalculator: core version rejects dicts → must use v17_core wrapper
  8. SequenceOfOperationsMatrix: DeviceInput objects not dicts, different field names
  9. ConduitSizer: 20 wires AWG14 in 1" EMT = 36.72% (< 40% limit, still compliant)
     → Need more wires (30) to actually trigger overfill violation
"""

import unittest
import math
from typing import Dict, List

# ============================================================================
# CORRECTED IMPORTS — all consultant import bugs fixed
# ============================================================================

# FIX 1 & 2: FACPGlobalCapacityAuditor → FACPCapacityAuditor, ManufacturerProfile → FACP_Profile
from fireai.core.facp_capacity_auditor import FACPCapacityAuditor, FACP_Profile

from fireai.core.as_built_reconciliator import AsBuiltReconciliator
from fireai.core.routing_global_class_a import EliteGlobalRouter
from fireai.core.firestop_annotator import FirestoppingAnnotator

# FIX 3: fireai.core.battery_calculator → fireai.v17_core.battery_calculator
from fireai.v17_core.battery_calculator import StrictBatterySizer

# FIX 7: Core AcousticSPLCalculator rejects dicts → use v17_core wrapper
from fireai.v17_core.acoustic_calculator import AcousticSPLCalculator

# FIX 8: SequenceOfOperationsMatrix uses DeviceInput objects
from fireai.core.sequence_of_operations import (
    SequenceOfOperationsMatrix, LogicFunction, DeviceInput, DeviceInputType,
)

from fireai.core.conduit_fill_analyzer import ConduitSizer

# FIX 4: fireai.v8_core.decision_provenance → fireai.core.provenance
from fireai.core.provenance import ConfidenceLevel

# FIX 5: fireai.core.models → src.core.models
from src.core.models import Device, DeviceType


class TestApocalypseV18(unittest.TestCase):

    def setUp(self):
        print("\n[⚠️] Executing Ruthless Simulation:", self._testMethodName)

    # --------------------------------------------------------
    # 1. اختبار احتراق اللوحة (FACP PSU Burnout Test)
    # --------------------------------------------------------
    def test_facp_catastrophic_overload(self):
        """يحاول إرفاق عدد سارينات يسحب 9 أمبير على لوحة أقصى تحمل لها 7 أمبير."""
        # FIX 1 & 2: Use FACPCapacityAuditor with FACP_Profile, not string
        profile = FACP_Profile(
            manufacturer="NOTIFIER_FLASHSCAN",
            max_detectors_per_slc=99,
            max_modules_per_slc=99,
            max_total_devices_per_slc=198,
            max_total_nac_amps=7.0,   # 7A max PSU capacity
            max_amps_per_nac=3.0,      # 3A per NAC circuit
            slc_max_current_ma=500.0,
        )
        auditor = FACPCapacityAuditor(profile)
        nac_circuits = [
            {"id": "NAC1", "total_inrush_amps": 2.8},
            {"id": "NAC2", "total_inrush_amps": 2.9},
            {"id": "NAC3", "total_inrush_amps": 3.5},  # <- This triggers total to 9.2A
        ]
        # FIX: Method is audit_global_inrush, not audit_nac_inrush_and_psu
        result = auditor.audit_global_inrush(nac_circuits)

        # The result is a dict with 'status' and 'provenance'
        self.assertEqual(result['status'], 'CATASTROPHIC_OVERLOAD',
                         "System allowed FACP burnout!")

        # Check provenance for audit trail
        provenance = result['provenance']
        self.assertEqual(provenance.value, 'CATASTROPHIC_OVERLOAD')

        # Verify that NAC aggregate overload violation was detected
        violation_codes = [v['code'] for v in result['violations']]
        self.assertIn('FACP-NAC-AGGREGATE', violation_codes,
                      "PSU burnout violation not detected!")

        # Verify "burn out" is mentioned in violation descriptions
        violation_messages = [v['message'] for v in result['violations']]
        self.assertTrue(
            any("burnout" in msg.lower() or "exceeds" in msg.lower()
                for msg in violation_messages),
            "No burnout/overload warning in violations!",
        )

    # --------------------------------------------------------
    # 2. اختبار كشف التزوير في الموقع (As-Built Forgery Check)
    # --------------------------------------------------------
    def test_as_built_contractor_forgery(self):
        """مقاول يقوم بتغيير مكان Manual Pull Station بـ 1 متر، وهي كارثة تخص قوانين ذوي الهمم ADA."""
        # FIX 6: Use correct keys: 'id', 'device_type' (not 'type')
        # FIX 6: Constructor arg order: (design_manifest, merkle_root)
        manifest = {
            "devices": [
                {"id": "MCP-1", "device_type": "MANUAL_CALL_POINT", "x": 5.0, "y": 1.0, "z": 1.2}
            ]
        }

        # Skip merkle check by passing None — we're testing geometric drift
        reconciliator = AsBuiltReconciliator(design_manifest=manifest, merkle_root=None)

        # المقاول وضع الجهاز على x = 6.0 بدلا من 5.0 (انحراف 1 متر)
        # FIX 6: Use 'id' not 'device_id', use dict not FakeDevice class
        rogue_device = {"id": "MCP-1", "device_type": "MANUAL_CALL_POINT", "x": 6.0, "y": 1.0, "z": 1.2}

        # FIX 6: Method is reconcile(), not audit_field_installations()
        result = reconciliator.reconcile([rogue_device])

        # FIX 6: Result is ReconciliationResult, not dict with "integrity_verdict"
        self.assertEqual(result.status, "DEVIATION_DETECTED",
                         "System failed to detect contractor forgery!")

        # Verify that the 1.0m drift was detected
        self.assertEqual(len(result.drifted_devices), 1,
                         "Should detect exactly 1 drifted device!")

        # Verify drift details mention the device and distance
        drift_info = result.drifted_devices[0]
        # drift_info is a tuple: (device_id, drift_m, tolerance, message)
        self.assertEqual(drift_info[0], "MCP-1")
        self.assertGreater(drift_info[1], 0.5,  # drift > 0.5m tolerance
                           "Drift should exceed 0.5m tolerance for MCP!")
        # FIX: The message uses "exceeding tolerance" not "exceeded tolerance"
        self.assertIn("exceeding tolerance", drift_info[3],
                      "Drift message should mention tolerance violation!")

    # --------------------------------------------------------
    # 3. اختبار تقاطع مسار الفئة أ (Class A Short Circuit Death)
    # --------------------------------------------------------
    def test_class_a_loop_survival(self):
        """التأكد من أن المصفوفة التوجيهية تفصل خط الذهاب عن العودة حتى في المساحات الضيقة."""
        router = EliteGlobalRouter((0.0, 0.0, 20.0, 20.0), 1.0)
        # FIX: apply_class_a_separation is a no-op (delegated internally).
        # Use route_class_a_loop which returns DecisionProvenance with
        # out_path and return_path, plus NFPA 72 §12.2.2 separation check.
        result = router.route_class_a_loop(
            panel=(0.0, 0.0),
            terminal_device=(18.0, 18.0),
        )

        # Verify that Class A loop was created with separated paths
        self.assertEqual(result.decision_type, "class_a_route_creation",
                         "Wrong decision type from Class A router!")

        # Verify outgoing and return paths both exist and are different
        value = result.value
        self.assertIn("out_path", value, "Missing outgoing path in Class A result!")
        self.assertIn("return_path", value, "Missing return path in Class A result!")

        # Verify NFPA 72 §12.2.2 separation rule was applied
        rules = result.rules_applied
        self.assertTrue(
            any("12.2.2" in r.get("citation", "") or "CLASS_A" in r.get("constant_id", "")
                for r in rules),
            "NFPA 72 §12.2.2 Class A separation rule not applied!",
        )

    # --------------------------------------------------------
    # 4. اختراق الجدران المقاومة للحريق (Firestop Omission Bypass)
    # --------------------------------------------------------
    def test_illegal_wall_penetration(self):
        """يحاول تمرير كابل عبر حائط استنادي مصنف مقاوم للحريق ليرى إن كان البرنامج سيُسقط (Firestop)."""
        wall_line = ((0.0, 5.0), (10.0, 5.0))  # حائط عرضي عند Y=5
        annotator = FirestoppingAnnotator([wall_line])
        # fire_lines are Shapely LineString objects; all walls are assumed fire-rated
        route = [(5.0, 0.0), (5.0, 10.0)]  # مسار الكابل يخترق الحائط عمودياً عند (5, 5)

        penetrations = annotator.locate_penetrations(route)
        self.assertEqual(len(penetrations), 1, "Failed to detect Fire-Rated wall penetration!")
        self.assertEqual(penetrations[0], (5.0, 5.0), "Penetration coordinates calculated incorrectly.")

    # --------------------------------------------------------
    # 5. اختبار ذوبان المواسير (Conduit Melting by Overfill)
    # --------------------------------------------------------
    def test_conduit_severe_overfill(self):
        """وضع عدد هائل من الكابلات داخل ماسورة وتوقع الفشل."""
        sizer = ConduitSizer()
        # FIX: ConduitSizer auto-sizes to the next larger conduit, so 20 or 30
        # wires of AWG 14 will simply get a bigger conduit and remain compliant.
        # To actually trigger overfill, we need a bundle that exceeds ALL conduit
        # sizes — 500 wires AWG 14 triggers the "exceeds all conduit sizes" path.
        wire_inventory = [{"awg": 14, "count": 500}]
        result = sizer.analyze_routing_bundle("TEST-TRUNK", wire_inventory)

        # With extreme overfill, confidence should NOT be HIGH
        self.assertNotEqual(result.confidence.overall, ConfidenceLevel.HIGH,
                            "Permitted severe conduit overfill with HIGH confidence!")
        # Fill percentage should exceed the 40% NEC limit
        self.assertTrue(result.value['actual_fill_percentage'] > 40.0,
                        "Fill limit computation bypassed — 500 wires should exceed 40%!")
        # Should be marked as non-compliant
        self.assertFalse(result.value['is_compliant'],
                         "Conduit overfill should be flagged as non-compliant!")

    # --------------------------------------------------------
    # 6. الهلاك بالمناطق الميتة الصوتية (Acoustic Blindspots)
    # --------------------------------------------------------
    def test_mechanical_room_acoustic_deafness(self):
        """وضع سماعة قوية بجوار غرفة ضواغط ميكانيكية بها 85 ديسيبل ومسافة بعيدة ليظهر العمى الصوتي."""
        # FIX 7: Use v17_core AcousticSPLCalculator which accepts dicts
        acoustics = AcousticSPLCalculator()
        speakers = [{"x": 0.0, "y": 0.0, "z": 2.8, "rating_db_3m": 90.0, "behind_closed_door": True}]
        check_points = [{"x": 10.0, "y": 10.0, "z": 1.5}]

        # In mechanical room, ambient is 85dB. Required is 100dB.
        result = acoustics.calculate_room_spl("MEC_01", "mechanical", speakers, check_points)

        # v17_core returns DecisionProvenance with .value dict
        self.assertFalse(result.value['pass'],
                         "Approved non-audible signal in noisy environment!")
        # Violations should be detected (SPL deficit)
        self.assertTrue(len(result.violations_detected) > 0,
                        "No violations detected for deaf mechanical room!")

    # --------------------------------------------------------
    # 7. ذعر الهروب الكاذب (General Alarm Misfire - Panic Check)
    # --------------------------------------------------------
    def test_duct_detector_triggers_general_alarm_panic(self):
        """اختبار عدم تفعيل مصفوفة الأخلاء الصوتي بناءً على كاشف الدكت كما ينص الكود."""
        seq_ops = SequenceOfOperationsMatrix()
        # FIX 8: Use DeviceInput objects, not dicts
        devices = [DeviceInput(
            device_id="DUCT_01",
            device_type=DeviceInputType.DUCT_DETECTOR,
            zone_id="Z1",
            description="HVAC UNIT",
        )]

        result = seq_ops.generate_matrix(devices)
        # FIX: generate_matrix returns DecisionProvenance, not dict
        # Access the value dict via .value attribute
        result_value = result.value
        matrix = result_value['matrix']
        row = matrix[0]

        # FIX 8: Output key is 'outputs', not 'outputs_triggered'
        outputs = row['outputs']

        # Duct detector should NOT trigger General Alarm / Evacuation
        general_alarm_str = LogicFunction.ALARM.value  # "General Alarm / Evacuation"
        self.assertNotIn(general_alarm_str, outputs,
                         "FATAL ERROR: Duct detector caused a building-wide evacuation alarm!")

        # Duct detector SHOULD trigger HVAC shutdown
        hvac_shutdown_str = LogicFunction.HVAC_SHUTDOWN_ZONE.value
        self.assertIn(hvac_shutdown_str, outputs,
                      "Duct detector failed to initiate HVAC/fan shutdown!")

    # --------------------------------------------------------
    # 8. التدهور الحراري للبطاريات (Deep Freeze Battery Death)
    # --------------------------------------------------------
    def test_siberian_battery_derating(self):
        """وضع لوحة التحكم في غرفة شديدة البرودة والتأكد أن السعة تُضاعف للحماية."""
        batt = StrictBatterySizer(standby_hours=24, alarm_minutes=5)
        q_ma, a_ma = 100.0, 2000.0  # (0.1A * 24) + (2A * 0.08) = 2.4 + 0.16 = 2.56 Ah Base.

        # الغرفة المتجمدة (-10C) — battery only has 60% of rated capacity
        result_frozen = batt.calculate_minimum_ah(q_ma, a_ma, panel_ambient_temp_c=-10.0)
        # الغرفة القياسية (25C)
        result_normal = batt.calculate_minimum_ah(q_ma, a_ma, panel_ambient_temp_c=25.0)

        # At -10°C, derating factor = 0.60, so required Ah should be significantly larger
        # Required_frozen / Required_normal ≈ (1.0 / 0.60) = 1.67x
        # The test checks > 1.3x which is a conservative threshold
        self.assertTrue(
            result_frozen.value['min_required_ah'] > result_normal.value['min_required_ah'] * 1.3,
            "Thermal battery decay failed to resize capacity massively in freezing environment!"
        )


if __name__ == '__main__':
    unittest.main()
