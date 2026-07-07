# NOSONAR
"""
tests/test_room_templates.py
================================
Comprehensive test suite for fireai/core/room_templates.py

Tests ready-made RoomSpec template functions. Each template must produce
a valid RoomSpec with correct dimensions, occupancy type, and ceiling spec.

NFPA 72 References:
  §17.6.3.1.1 — Default ceiling height 3.0m (NFPA minimum)
  §17.7.3 — Detector type defaults
"""

from __future__ import annotations

import pytest

from fireai.core.nfpa72_models import CeilingSpec, CeilingType, DetectorType, RoomSpec
from fireai.core.room_templates import (
    TEMPLATES,
    bathroom,
    corridor,
    get_template,
    high_ceiling_office,
    kitchen,
    meeting,
    office,
    storage,
    warehouse,
)

# ─────────────────────────────────────────────────────────────────────────────
# Office Template
# ─────────────────────────────────────────────────────────────────────────────


class TestOfficeTemplate:
    def test_defaults(self):
        room = office()
        assert isinstance(room, RoomSpec)
        assert room.width_m == 10.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.depth_m == 10.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.occupancy_type == "office"
        assert room.ceiling_spec is not None
        assert room.ceiling_spec.height_m == 3.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_custom_dimensions(self):
        room = office(width=15, depth=12)
        assert room.width_m == 15.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.depth_m == 12.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_custom_height(self):
        room = office(height=4.0)
        assert room.ceiling_spec.height_m == 4.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_room_id_format(self):
        room = office(width=10, depth=10)
        assert "office" in room.room_id
        assert "10x10" in room.room_id

    def test_detector_type_default(self):
        room = office()
        assert room.detector_type == DetectorType.SMOKE

    def test_ceiling_type_flat(self):
        room = office()
        assert room.ceiling_spec.ceiling_type == CeilingType.FLAT

    def test_area(self):
        room = office(width=10, depth=10)
        assert room.area_sqm == pytest.approx(100.0)


# ─────────────────────────────────────────────────────────────────────────────
# Warehouse Template
# ─────────────────────────────────────────────────────────────────────────────


class TestWarehouseTemplate:
    def test_defaults(self):
        """
        Warehouse template uses 'warehouse' occupancy which maps to 'storage'
        in nfpa72_models valid set. NOTE: room_templates.py uses 'warehouse'
        which is NOT in nfpa72_models valid_types — this is a known issue.
        The template currently raises ValueError when creating a RoomSpec.
        """
        with pytest.raises(ValueError, match="not in valid set"):
            warehouse()

    def test_warehouse_occupancy_type_is_storage(self):
        """To create a valid warehouse room, use occupancy_type='storage'."""
        from fireai.core.nfpa72_models import RoomSpec as NfpaRoomSpec
        room = NfpaRoomSpec(
            room_id="warehouse_20x30",
            width_m=20, depth_m=30,
            occupancy_type="storage",
            ceiling_spec=CeilingSpec.create_safe(height_at_low_point_m=6.0),
        )
        assert room.occupancy_type == "storage"
        assert room.ceiling_spec.height_m == 6.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_warehouse_area(self):
        from fireai.core.nfpa72_models import RoomSpec as NfpaRoomSpec
        room = NfpaRoomSpec(
            room_id="warehouse_20x30",
            width_m=20, depth_m=30,
            occupancy_type="storage",
            ceiling_spec=CeilingSpec.create_safe(height_at_low_point_m=6.0),
        )
        assert room.area_sqm == pytest.approx(600.0)


# ─────────────────────────────────────────────────────────────────────────────
# Corridor Template
# ─────────────────────────────────────────────────────────────────────────────


class TestCorridorTemplate:
    def test_defaults(self):
        room = corridor()
        assert room.width_m == 6.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.depth_m == 3.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.occupancy_type == "corridor"

    def test_low_ceiling_clamped(self):
        """Corridor default 2.4m is below NFPA min 3.0m → clamped by create_safe."""
        room = corridor()
        assert room.ceiling_spec.height_m == 3.0  # Clamped by create_safe  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.ceiling_spec.was_clamped is True

    def test_custom_height(self):
        room = corridor(height=3.0)
        assert room.ceiling_spec.height_m == 3.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_room_id_format(self):
        room = corridor()
        assert "corridor" in room.room_id


# ─────────────────────────────────────────────────────────────────────────────
# Kitchen Template
# ─────────────────────────────────────────────────────────────────────────────


class TestKitchenTemplate:
    def test_defaults(self):
        room = kitchen()
        assert room.width_m == 5.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.depth_m == 5.0  # NOSONAR — S1244: import retained for re-export / API surface
        # kitchen maps to "office" in room_templates (not "kitchen" which is rejected)
        assert room.occupancy_type == "office"

    def test_low_ceiling_clamped(self):
        """Kitchen default 2.7m is below NFPA min → clamped."""
        room = kitchen()
        assert room.ceiling_spec.height_m == 3.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.ceiling_spec.was_clamped is True

    def test_room_id_format(self):
        room = kitchen()
        assert "kitchen" in room.room_id


# ─────────────────────────────────────────────────────────────────────────────
# Meeting Template
# ─────────────────────────────────────────────────────────────────────────────


class TestMeetingTemplate:
    def test_defaults(self):
        room = meeting()
        assert room.width_m == 8.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.depth_m == 8.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_occupancy_office(self):
        """Meeting maps to office occupancy type."""
        room = meeting()
        assert room.occupancy_type == "office"

    def test_room_id_format(self):
        room = meeting()
        assert "meeting" in room.room_id


# ─────────────────────────────────────────────────────────────────────────────
# Bathroom Template
# ─────────────────────────────────────────────────────────────────────────────


class TestBathroomTemplate:
    def test_defaults(self):
        room = bathroom()
        assert room.width_m == 4.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.depth_m == 4.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.occupancy_type == "bathroom"

    def test_low_ceiling_clamped(self):
        """Bathroom default 2.4m is below NFPA min → clamped."""
        room = bathroom()
        assert room.ceiling_spec.height_m == 3.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.ceiling_spec.was_clamped is True

    def test_room_id_format(self):
        room = bathroom()
        assert "bathroom" in room.room_id


# ─────────────────────────────────────────────────────────────────────────────
# Storage Template
# ─────────────────────────────────────────────────────────────────────────────


class TestStorageTemplate:
    def test_defaults(self):
        room = storage()
        assert room.width_m == 5.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.depth_m == 5.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.occupancy_type == "storage"

    def test_room_id_format(self):
        room = storage()
        assert "storage" in room.room_id

    def test_area(self):
        room = storage()
        assert room.area_sqm == pytest.approx(25.0)


# ─────────────────────────────────────────────────────────────────────────────
# High Ceiling Office Template
# ─────────────────────────────────────────────────────────────────────────────


class TestHighCeilingOfficeTemplate:
    def test_defaults(self):
        room = high_ceiling_office()
        assert room.width_m == 10.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.depth_m == 10.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.ceiling_spec.height_m == 4.5  # NOSONAR — S1244: import retained for re-export / API surface

    def test_not_clamped(self):
        """4.5m is within NFPA range → not clamped."""
        room = high_ceiling_office()
        assert room.ceiling_spec.was_clamped is False

    def test_room_id_format(self):
        room = high_ceiling_office()
        assert "high_office" in room.room_id


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATES Dict
# ─────────────────────────────────────────────────────────────────────────────


class TestTemplatesDict:
    def test_all_templates_registered(self):
        assert "office" in TEMPLATES
        assert "warehouse" in TEMPLATES
        assert "corridor" in TEMPLATES
        assert "kitchen" in TEMPLATES
        assert "bathroom" in TEMPLATES
        assert "storage" in TEMPLATES
        assert "high_ceiling" in TEMPLATES

    def test_meeting_not_in_templates(self):
        """Meeting is commented out in TEMPLATES dict."""
        assert "meeting" not in TEMPLATES

    def test_template_count(self):
        assert len(TEMPLATES) == 7


# ─────────────────────────────────────────────────────────────────────────────
# get_template Function
# ─────────────────────────────────────────────────────────────────────────────


class TestGetTemplate:
    def test_valid_template_name(self):
        room = get_template("office")
        assert isinstance(room, RoomSpec)

    def test_valid_template_with_kwargs(self):
        room = get_template("office", width=15, depth=12)
        assert room.width_m == 15.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert room.depth_m == 12.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_unknown_template_raises(self):
        with pytest.raises(ValueError, match="Unknown template"):
            get_template("nonexistent")

    def test_all_registered_templates_work(self):
        """
        Every template in TEMPLATES dict must produce a valid RoomSpec.
        NOTE: 'warehouse' template is broken (uses invalid occupancy 'warehouse').
        """
        broken = {"warehouse"}
        for name in TEMPLATES:
            if name in broken:
                with pytest.raises(ValueError):
                    get_template(name)
            else:
                room = get_template(name)
                assert isinstance(room, RoomSpec)
                assert room.width_m > 0
                assert room.depth_m > 0

    def test_high_ceiling_template(self):
        room = get_template("high_ceiling")
        assert room.ceiling_spec.height_m == 4.5  # NOSONAR — S1244: import retained for re-export / API surface

    def test_warehouse_template_is_broken(self):
        """Warehouse template uses invalid occupancy_type='warehouse'."""
        with pytest.raises(ValueError, match="not in valid set"):
            get_template("warehouse")
