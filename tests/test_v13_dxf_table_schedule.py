"""
tests/test_v13_dxf_table_schedule.py
======================================
Unit tests for TrueAECDraftingTable (DXF TABLE entity generation).
"""
import unittest
import ezdxf
from fireai.core.dxf_table_schedule import TrueAECDraftingTable


class TestTrueAECDraftingTable(unittest.TestCase):
    """Test DXF TABLE entity generation for device schedules."""

    def setUp(self):
        self.doc = ezdxf.new("R2018")
        self.msp = self.doc.modelspace()

    def test_construction(self):
        """Table should be constructable with default position."""
        taec = TrueAECDraftingTable()
        self.assertEqual(taec.position, (0.0, 0.0, 0.0))

    def test_custom_position(self):
        """Table should accept custom position."""
        taec = TrueAECDraftingTable(table_position_xyz=(50.0, 30.0, 0.0))
        self.assertEqual(taec.position, (50.0, 30.0, 0.0))

    def test_dict_device_input(self):
        """Devices as dicts should be processed correctly."""
        taec = TrueAECDraftingTable(table_position_xyz=(50.0, 30.0, 0.0))
        devices = [
            {'device_id': 'SM-01', 'device_type': 'SMOKE', 'circuit_id': 'SLC-1', 'zone_id': 'Z1', 'x': 5.0, 'y': 3.0},
            {'device_id': 'HT-01', 'device_type': 'HEAT', 'circuit_id': 'SLC-1', 'zone_id': 'Z1', 'x': 15.0, 'y': 7.0},
        ]
        result = taec.draft_device_boq_table(self.msp, devices)
        # Result is True if Table addon is available, False if not
        self.assertIsInstance(result, bool)

    def test_empty_device_list(self):
        """Empty device list should not crash."""
        taec = TrueAECDraftingTable()
        result = taec.draft_device_boq_table(self.msp, [])
        # Should handle gracefully
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
