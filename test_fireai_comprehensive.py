"""
FireAI V7.4.1 - Comprehensive Test Suite
=======================================
Run: python test_fireai_comprehensive.py
"""
import unittest
import math
import sys
from typing import List

# ============================================================================
# TEST 1: Import All Modules
# ============================================================================
class TestImports(unittest.TestCase):
    def test_fire_expert_system(self):
        from fire_expert_system import NFPA72, NFPA13, NFPA101
        from fire_expert_system import HeatDetectorType, HeatDetectorCoverage
        self.assertIsNotNone(NFPA72)
        
    def test_safety_gates(self):
        from core.safety_gates import SafetyGates, GateStatus
        self.assertIsNotNone(SafetyGates)
        
    def test_database(self):
        from core.fireai_db_reporting import FireAIDatabase
        self.assertIsNotNone(FireAIDatabase)
        
    def test_multifloor(self):
        from core.multi_floor_analyzer import MultiFloorAnalyzer, FloorInfo
        self.assertIsNotNone(MultiFloorAnalyzer)


# ============================================================================
# TEST 2: NFPA Constants Verification
# ============================================================================
class TestNFPATables(unittest.TestCase):
    def test_smoke_coverage(self):
        from fire_expert_system import NFPA72
        self.assertEqual(NFPA72.SMOKE_COVERAGE['flat_ceiling'], 9.2)
        
    def test_heat_coverage(self):
        from fire_expert_system import HeatDetectorType
        self.assertEqual(HeatDetectorType.FIXED_TEMPERATURE.name, 'FIXED_TEMPERATURE')
        
    def test_sprinkler_coverage(self):
        from fire_expert_system import NFPA13
        self.assertEqual(NFPA13.SPRINKLER_SPACING['light_hazard'], 4.6)
        
    def test_egress(self):
        from fire_expert_system import NFPA101
        self.assertEqual(NFPA101.MAX_TRAVEL['business_sprinklered'], 61.0)


# ============================================================================
# TEST 3: Safety Gates - Real Calculations (FIXED PARAMETER NAMES)
# ============================================================================
class TestSafetyGates(unittest.TestCase):
    def test_smoke_coverage_pass(self):
        """50m² with 1 detector at 3m ceiling = PASS"""
        from core.safety_gates import SafetyGates, GateStatus
        result = SafetyGates.gate_smoke_coverage(
            detector_positions=[(0,0)], 
            room_area=50, 
            ceiling_height=3.0
        )
        # 50m² needs 1 detector: 50/66.5 = 0.75 → pass
        self.assertEqual(result.status, GateStatus.PASS)
        
    def test_smoke_coverage_fail(self):
        """150m² with 1 detector = FAIL"""
        from core.safety_gates import SafetyGates, GateStatus
        result = SafetyGates.gate_smoke_coverage(
            detector_positions=[(0,0)], 
            room_area=150, 
            ceiling_height=3.0
        )
        # 150m² needs 3 detectors: 150/66.5 = 2.25 → fail
        self.assertEqual(result.status, GateStatus.FAIL)
        
    def test_egress_no_exits(self):
        """No exits = FAIL"""
        from core.safety_gates import SafetyGates, GateStatus
        result = SafetyGates.gate_egress(
            occupant_points=[(5,5)],
            exit_points=[]
        )
        self.assertEqual(result.status, GateStatus.FAIL)
        
    def test_high_ceiling(self):
        """Ceiling >3.7m = REVIEW_REQUIRED"""
        from core.safety_gates import SafetyGates, GateStatus
        result = SafetyGates.gate_smoke_coverage(
            detector_positions=[(0,0)], 
            room_area=50, 
            ceiling_height=4.0
        )
        self.assertEqual(result.status, GateStatus.REVIEW_REQUIRED)


# ============================================================================
# TEST 4: Database Operations
# ============================================================================
class TestDatabase(unittest.TestCase):
    def test_save_project(self):
        from core.fireai_db_reporting import FireAIDatabase
        db = FireAIDatabase(":memory:")
        project_hash = db.save_project("Test Project", "test.dxf", "DXF")
        self.assertIsNotNone(project_hash)
        
    def test_save_analysis(self):
        from core.fireai_db_reporting import FireAIDatabase
        db = FireAIDatabase(":memory:")
        project_hash = db.save_project("Test", "test.dxf", "DXF")
        db.save_analysis(project_hash, 5, 10, 0, {"data": "test"})
        
        projects = db.list_projects()
        self.assertGreater(len(projects), 0)


# ============================================================================
# TEST 5: Multi-Floor Analyzer - Real Calculations
# ============================================================================
class TestMultiFloor(unittest.TestCase):
    def test_analyze_building_single_panel(self):
        """95 devices needs 1 panel"""
        from core.multi_floor_analyzer import MultiFloorAnalyzer, FloorInfo
        floors = [
            FloorInfo(level=1, area=500, devices=45),
            FloorInfo(level=2, area=500, devices=50)
        ]
        result = MultiFloorAnalyzer.analyze_building(floors, max_devices_per_panel=1000)
        self.assertEqual(result['panels_needed'], 1)
        
    def test_check_multi_building_requires_multiple(self):
        """200m apart requires multiple panels"""
        from core.multi_floor_analyzer import MultiFloorAnalyzer
        result = MultiFloorAnalyzer.check_multi_building(
            [(0,0), (200,0)], max_distance=150
        )
        self.assertEqual(result['single_panel'], False)
        
    def test_check_multi_building_single_ok(self):
        """50m apart = single panel OK"""
        from core.multi_floor_analyzer import MultiFloorAnalyzer
        result = MultiFloorAnalyzer.check_multi_building(
            [(0,0), (50,0)], max_distance=150
        )
        self.assertEqual(result['single_panel'], True)


# ============================================================================
# TEST 6: Cable Length Calculation - Real Math
# ============================================================================
class TestCableLength(unittest.TestCase):
    def test_straight_line(self):
        """Direct 100m = 115m with routing"""
        from core.multi_floor_analyzer import calculate_cable_length
        length = calculate_cable_length(start=(0,0), end=(100, 0))
        expected = 100 * 1.15
        self.assertAlmostEqual(length, expected, places=1)
        
    def test_diagonal(self):
        """Diagonal 100x50m = 128.6m"""
        from core.multi_floor_analyzer import calculate_cable_length
        length = calculate_cable_length(start=(0,0), end=(100, 50))
        direct = math.sqrt(100**2 + 50**2)
        expected = direct * 1.15
        self.assertAlmostEqual(length, expected, places=1)


# ============================================================================
# TEST 7: Voltage Drop Calculation
# ============================================================================
class TestVoltageDrop(unittest.TestCase):
    def test_short_run(self):
        """100m, 0.5A, #14 = ~0.5V"""
        from core.multi_floor_analyzer import estimate_voltage_drop
        vdrop = estimate_voltage_drop(distance=100, current=0.5, wire_gauge=14)
        self.assertGreater(vdrop, 0)
        self.assertLess(vdrop, 1.0)
        
    def test_awg_sizes(self):
        """Different wire gauges give different drops"""
        from core.multi_floor_analyzer import estimate_voltage_drop
        vdrop_14 = estimate_voltage_drop(distance=100, current=0.5, wire_gauge=14)
        vdrop_12 = estimate_voltage_drop(distance=100, current=0.5, wire_gauge=12)
        self.assertLess(vdrop_12, vdrop_14)


# ============================================================================
# TEST 8: Circle Coverage Formula (CRITICAL)
# ============================================================================
class TestCoverageFormula(unittest.TestCase):
    def test_circle_vs_square(self):
        """Circle: π×r² = 66.5m², Square: 84.6m²"""
        spacing = 9.2
        circle_area = math.pi * (spacing/2)**2
        square_area = spacing ** 2
        
        self.assertAlmostEqual(circle_area, 66.5, places=1)
        self.assertAlmostEqual(square_area, 84.6, places=1)
        self.assertNotEqual(circle_area, square_area)
        
    def test_detector_count(self):
        """100m² needs 2 detectors (not 1)"""
        room_area = 100
        coverage_per_detector = math.pi * (9.2/2)**2
        detectors_needed = math.ceil(room_area / coverage_per_detector)
        self.assertEqual(detectors_needed, 2)


# ============================================================================
# MAIN - Run all tests
# ============================================================================
if __name__ == '__main__':
    print("=" * 70)
    print("🔥 FireAI V7.4.1 - COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print()
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestImports))
    suite.addTests(loader.loadTestsFromTestCase(TestNFPATables))
    suite.addTests(loader.loadTestsFromTestCase(TestSafetyGates))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabase))
    suite.addTests(loader.loadTestsFromTestCase(TestMultiFloor))
    suite.addTests(loader.loadTestsFromTestCase(TestCableLength))
    suite.addTests(loader.loadTestsFromTestCase(TestVoltageDrop))
    suite.addTests(loader.loadTestsFromTestCase(TestCoverageFormula))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print()
    print("=" * 70)
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED!")
        print(f"   Tests run: {result.testsRun}")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED!")
        sys.exit(1)
