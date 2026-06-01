"""
tests/test_dxf_table_schedule.py
=================================
Comprehensive test suite for fireai/core/dxf_table_schedule.py

Tests DXF TABLE entity generation for fire alarm device schedules.
TrueAECDraftingTable creates proper DXF TABLE entities (queryable in
Navisworks/AutoCAD) instead of plain MTEXT (not queryable).
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from fireai.core.dxf_table_schedule import TrueAECDraftingTable, Table


# ═══════════════════════════════════════════════════════════════════════════════
# TrueAECDraftingTable Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTrueAECDraftingTable:
    def test_init_default_position(self):
        t = TrueAECDraftingTable()
        assert t.position == (0.0, 0.0, 0.0)

    def test_init_custom_position(self):
        t = TrueAECDraftingTable(table_position_xyz=(1.0, 2.0, 0.0))
        assert t.position == (1.0, 2.0, 0.0)

    def test_draft_returns_false_without_ezdxf_table(self):
        """If ezdxf Table addon not available, returns False."""
        msp = MagicMock()
        t = TrueAECDraftingTable()
        with patch("fireai.core.dxf_table_schedule.Table", None):
            result = t.draft_device_boq_table(msp, [])
            assert result is False

    def test_draft_with_dict_devices(self):
        """Device data as dicts should work."""
        if Table is None:
            pytest.skip("ezdxf Table addon not available")

        msp = MagicMock()
        tbl_mock = MagicMock()
        with patch("fireai.core.dxf_table_schedule.Table", return_value=tbl_mock):
            t = TrueAECDraftingTable()
            devices = [
                {
                    "device_id": "D1",
                    "device_type": "Smoke Detector",
                    "circuit_id": "SLC-01",
                    "zone_id": "Z1",
                    "x": 10.5,
                    "y": 20.3,
                },
                {
                    "device_id": "D2",
                    "device_type": "Heat Detector",
                    "circuit_id": "SLC-01",
                    "zone_id": "Z2",
                    "x": 30.0,
                    "y": 40.0,
                },
            ]
            result = t.draft_device_boq_table(msp, devices, "Test Schedule")
            assert result is True
            tbl_mock.render.assert_called_once_with(msp)

    def test_draft_with_object_devices(self):
        """Device data as objects with attributes should work."""
        if Table is None:
            pytest.skip("ezdxf Table addon not available")

        msp = MagicMock()
        tbl_mock = MagicMock()

        class DevObj:
            device_id = "D3"
            device_type = "Strobe"
            circuit_id = "NAC-01"
            zone_id = "Z3"
            x = 5.0
            y = 10.0

        with patch("fireai.core.dxf_table_schedule.Table", return_value=tbl_mock):
            t = TrueAECDraftingTable()
            result = t.draft_device_boq_table(msp, [DevObj()])
            assert result is True

    def test_draft_object_device_no_xy(self):
        """Object without x/y attributes should default to (0,0)."""
        if Table is None:
            pytest.skip("ezdxf Table addon not available")

        msp = MagicMock()
        tbl_mock = MagicMock()

        class DevObjNoXY:
            device_id = "D4"
            device_type = "Pull Station"
            circuit_id = "SLC-02"
            zone_id = "Z4"
            # No x, y attributes

        with patch("fireai.core.dxf_table_schedule.Table", return_value=tbl_mock):
            t = TrueAECDraftingTable()
            result = t.draft_device_boq_table(msp, [DevObjNoXY()])
            assert result is True

    def test_draft_dict_device_defaults(self):
        """Dict device missing keys should use defaults."""
        if Table is None:
            pytest.skip("ezdxf Table addon not available")

        msp = MagicMock()
        tbl_mock = MagicMock()

        with patch("fireai.core.dxf_table_schedule.Table", return_value=tbl_mock):
            t = TrueAECDraftingTable()
            devices = [{}]  # All defaults
            result = t.draft_device_boq_table(msp, devices)
            assert result is True

    def test_draft_render_exception_returns_false(self):
        """If render() throws, return False."""
        if Table is None:
            pytest.skip("ezdxf Table addon not available")

        msp = MagicMock()
        tbl_mock = MagicMock()
        tbl_mock.render.side_effect = RuntimeError("Render failed")

        with patch("fireai.core.dxf_table_schedule.Table", return_value=tbl_mock):
            t = TrueAECDraftingTable()
            result = t.draft_device_boq_table(msp, [])
            assert result is False

    def test_draft_empty_device_array(self):
        """Empty device array should still create header rows."""
        if Table is None:
            pytest.skip("ezdxf Table addon not available")

        msp = MagicMock()
        tbl_mock = MagicMock()

        with patch("fireai.core.dxf_table_schedule.Table", return_value=tbl_mock):
            t = TrueAECDraftingTable()
            result = t.draft_device_boq_table(msp, [], "Empty Schedule")
            assert result is True

    def test_position_passed_to_table(self):
        """Table position should be passed to Table constructor."""
        if Table is None:
            pytest.skip("ezdxf Table addon not available")

        msp = MagicMock()
        pos = (5.0, 10.0, 0.0)
        tbl_mock = MagicMock()

        with patch("fireai.core.dxf_table_schedule.Table", return_value=tbl_mock) as MockTable:
            t = TrueAECDraftingTable(table_position_xyz=pos)
            t.draft_device_boq_table(msp, [])
            MockTable.assert_called_once()
            call_args = MockTable.call_args
            assert call_args.kwargs.get("insert", call_args[1].get("insert", None)) == pos or call_args[0][0] == pos


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
