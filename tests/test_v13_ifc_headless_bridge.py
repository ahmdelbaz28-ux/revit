"""
tests/test_v13_ifc_headless_bridge.py
======================================
Unit tests for HeadlessIFCBridge (pure-Python IFC4 read/write).
"""
import unittest
import tempfile
import os


class TestHeadlessIFCBridge(unittest.TestCase):
    """Test headless IFC4 bridge without COM/Revit."""

    def test_import(self):
        """Module should be importable."""
        try:
            from fireai.bridges.ifc_headless_bridge import HeadlessIFCBridge
            self.assertTrue(True)
        except ImportError:
            self.skipTest("ifcopenshell not installed")

    def test_construction_requires_ifcopenshell(self):
        """Should raise ImportError if ifcopenshell missing."""
        try:
            import ifcopenshell
            self.skipTest("ifcopenshell IS installed, cannot test missing case")
        except ImportError:
            from fireai.bridges.ifc_headless_bridge import HeadlessIFCBridge
            with self.assertRaises(ImportError):
                HeadlessIFCBridge("nonexistent.ifc")

    def test_invalid_file_raises_error(self):
        """Invalid IFC file should raise ValueError."""
        try:
            import ifcopenshell
        except ImportError:
            self.skipTest("ifcopenshell not installed")
        
        from fireai.bridges.ifc_headless_bridge import HeadlessIFCBridge
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            f.write(b"NOT A VALID IFC FILE")
            temp_path = f.name
        try:
            with self.assertRaises(ValueError):
                HeadlessIFCBridge(temp_path)
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    unittest.main()
