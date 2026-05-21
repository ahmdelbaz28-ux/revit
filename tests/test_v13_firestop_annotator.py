"""
tests/test_v13_firestop_annotator.py
=====================================
Unit tests for FirestoppingAnnotator (IBC S714 penetration detection).
"""
import unittest
from fireai.core.firestop_annotator import FirestoppingAnnotator


class TestFirestoppingAnnotator(unittest.TestCase):
    """Test fire-rated wall penetration detection and DXF callouts."""

    def setUp(self):
        # Vertical fire-rated wall at x=10
        self.annotator = FirestoppingAnnotator([((10.0, 0.0), (10.0, 20.0))])

    def test_crossing_wall_detected(self):
        """Cable crossing fire wall should be detected."""
        cable = [(0.0, 5.0), (20.0, 5.0)]
        penetrations = self.annotator.locate_penetrations(cable)
        self.assertEqual(len(penetrations), 1)
        self.assertAlmostEqual(penetrations[0][0], 10.0, places=1)

    def test_parallel_wall_no_crossing(self):
        """Cable parallel to wall should have no penetration."""
        cable = [(0.0, 5.0), (9.0, 5.0)]
        penetrations = self.annotator.locate_penetrations(cable)
        self.assertEqual(len(penetrations), 0)

    def test_no_fire_walls(self):
        """No fire walls = no penetrations."""
        annotator = FirestoppingAnnotator([])
        cable = [(0.0, 5.0), (20.0, 5.0)]
        penetrations = annotator.locate_penetrations(cable)
        self.assertEqual(len(penetrations), 0)

    def test_short_cable_no_penetrations(self):
        """Cable with <2 points = no penetrations."""
        penetrations = self.annotator.locate_penetrations([(5.0, 5.0)])
        self.assertEqual(len(penetrations), 0)

    def test_dxf_callout_generation(self):
        """DXF callouts should be generated at penetration points."""
        import ezdxf
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        cable = [(0.0, 5.0), (20.0, 5.0)]
        count = self.annotator.draft_callouts_to_dxf(msp, cable)
        self.assertEqual(count, 1)

    def test_multiple_crossings(self):
        """Two fire walls should detect two penetrations."""
        annotator = FirestoppingAnnotator([
            ((10.0, 0.0), (10.0, 20.0)),
            ((15.0, 0.0), (15.0, 20.0)),
        ])
        cable = [(0.0, 5.0), (20.0, 5.0)]
        penetrations = annotator.locate_penetrations(cable)
        self.assertEqual(len(penetrations), 2)


if __name__ == "__main__":
    unittest.main()
