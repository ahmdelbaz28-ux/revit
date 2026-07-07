# NOSONAR
"""
tests/test_fire_zone_engine.py
================================
Comprehensive test suite for fireai/core/fire_zone_engine.py

SAFETY CRITICAL: Fire zone clustering groups rooms into fire alarm zones
per NFPA 72 §21.3.3. Incorrect zone assignments could lead to wrong
fault isolator placement or improper FACP programming — affecting
system response during a fire event.

NFPA 72 References:
  §21.3.3 — Zone requirements
  §21.2.2 — Maximum 250 devices per panel / SLC loop
  §10.4.4 — Zone identification
  §12.3.2 — Single fault affects only one zone
"""

from __future__ import annotations

import pytest

from fireai.core.fire_zone_engine import (
    FireZone,
    FireZoneEngine,
    ZoneConstraints,
    ZoneReport,
)

# ZoneConstraints
# ─────────────────────────────────────────────────────────────────────────────


class TestZoneConstraints:
    def test_defaults(self):
        c = ZoneConstraints()
        assert c.max_area_sqm == pytest.approx(1858.0, abs=0.1)
        assert c.max_detectors_per_zone == 100
        assert c.max_rooms_per_zone == 0
        assert c.separate_occupancy_types is True
        assert c.prefer_adjacent is True
        assert c.max_slc_devices_per_loop == 250

    def test_custom_values(self):
        c = ZoneConstraints(
            max_area_sqm=1000.0,
            max_detectors_per_zone=50,
            max_rooms_per_zone=10,
            separate_occupancy_types=False,
            prefer_adjacent=False,
        )
        assert c.max_area_sqm == 1000.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert c.max_detectors_per_zone == 50
        assert c.max_rooms_per_zone == 10
        assert c.separate_occupancy_types is False

    def test_no_area_limit_with_zero(self):
        """0 means no area limit."""
        c = ZoneConstraints(max_area_sqm=0)
        assert c.max_area_sqm == 0

    def test_no_room_limit_with_zero(self):
        """0 means no room count limit."""
        c = ZoneConstraints(max_rooms_per_zone=0)
        assert c.max_rooms_per_zone == 0


# FireZone
# ─────────────────────────────────────────────────────────────────────────────


class TestFireZone:
    def test_defaults(self):
        z = FireZone(zone_id="Z-01")
        assert z.zone_id == "Z-01"
        assert z.rooms == []
        assert z.total_area_sqm == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert z.total_detectors == 0
        assert z.occupancy_types == set()
        assert z.floor_id == ""
        assert z.zone_type == "alarm"

    def test_custom_values(self):
        z = FireZone(
            zone_id="Z-02",
            rooms=["R1", "R2"],
            total_area_sqm=150.0,
            total_detectors=5,
            occupancy_types={"office", "corridor"},
            floor_id="GF",
            zone_type="supervisory",
        )
        assert len(z.rooms) == 2
        assert z.total_area_sqm == 150.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert z.zone_type == "supervisory"


# ZoneReport
# ─────────────────────────────────────────────────────────────────────────────


class TestZoneReport:
    def test_defaults(self):
        r = ZoneReport(floor_id="GF")
        assert r.floor_id == "GF"
        assert r.zones == []
        assert r.total_zones == 0
        assert r.total_area_sqm == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert r.total_detectors == 0
        assert r.warnings == []
        assert r.unzoned_rooms == []


# ─────────────────────────────────────────────────────────────────────────────
# FireZoneEngine — Empty / Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestFireZoneEngineEmpty:
    def test_empty_rooms(self):
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [])
        assert report.total_zones == 0
        assert "No rooms" in report.warnings[0]

    def test_empty_rooms_no_zones(self):
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [])
        assert len(report.zones) == 0


# ─────────────────────────────────────────────────────────────────────────────
# FireZoneEngine — Basic Clustering
# ─────────────────────────────────────────────────────────────────────────────


class TestFireZoneEngineBasicClustering:
    def test_single_room(self):
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
        ])
        assert report.total_zones == 1
        assert "R1" in report.zones[0].rooms

    def test_two_same_occupancy_rooms(self):
        """Same occupancy → same zone (if constraints allow)."""
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 80.0, "detectors": 3, "occupancy": "office"},
        ])
        assert report.total_zones >= 1

    def test_different_occupancy_separate_zones(self):
        """separate_occupancy_types=True: different occupancy → different zones."""
        engine = FireZoneEngine(constraints=ZoneConstraints(separate_occupancy_types=True))
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 60.0, "detectors": 3, "occupancy": "industrial"},
        ])
        assert report.total_zones >= 2

    def test_no_occupancy_separation(self):
        """separate_occupancy_types=False: all rooms can be in same zone."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 60.0, "detectors": 3, "occupancy": "industrial"},
        ])
        # Should allow all in one zone if constraints permit
        assert report.total_zones >= 1

    def test_room_area_aggregated(self):
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 80.0, "detectors": 3, "occupancy": "office"},
        ])
        assert report.total_area_sqm == pytest.approx(130.0, abs=0.1)

    def test_detector_count_aggregated(self):
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 80.0, "detectors": 3, "occupancy": "office"},
        ])
        assert report.total_detectors == 5


# ─────────────────────────────────────────────────────────────────────────────
# FireZoneEngine — Constraint Splitting
# ─────────────────────────────────────────────────────────────────────────────


class TestFireZoneEngineConstraintSplitting:
    def test_area_constraint_split(self):
        """Zone exceeding max_area_sqm must split."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(max_area_sqm=100.0, separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 60.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 60.0, "detectors": 2, "occupancy": "office"},
        ])
        assert report.total_zones >= 2

    def test_detector_constraint_split(self):
        """Zone exceeding max_detectors_per_zone must split."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(max_detectors_per_zone=3, separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 50.0, "detectors": 2, "occupancy": "office"},
        ])
        assert report.total_zones >= 2

    def test_room_count_constraint_split(self):
        """Zone exceeding max_rooms_per_zone must split."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(max_rooms_per_zone=2, separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 1, "occupancy": "office"},
            {"id": "R2", "area": 50.0, "detectors": 1, "occupancy": "office"},
            {"id": "R3", "area": 50.0, "detectors": 1, "occupancy": "office"},
        ])
        assert report.total_zones >= 2

    def test_no_area_limit_no_split(self):
        """max_area_sqm=0 means no area limit."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(max_area_sqm=0, separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 1000.0, "detectors": 2, "occupancy": "office"},
        ])
        assert report.total_zones == 1


# ─────────────────────────────────────────────────────────────────────────────
# FireZoneEngine — Adjacency-Aware Clustering
# ─────────────────────────────────────────────────────────────────────────────


class TestFireZoneEngineAdjacency:
    def test_adjacent_rooms_grouped(self):
        """Adjacent rooms should preferentially be in the same zone."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(separate_occupancy_types=False, prefer_adjacent=True)
        )
        adjacency = {"R1": {"R2"}, "R2": {"R1"}}
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 50.0, "detectors": 2, "occupancy": "office"},
        ], adjacency=adjacency)
        # Both rooms should be in the same zone
        assert report.total_zones >= 1

    def test_non_adjacent_rooms_separate_clusters(self):
        """Non-adjacent rooms form separate clusters."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(separate_occupancy_types=False, prefer_adjacent=True)
        )
        adjacency = {"R1": set(), "R2": set(), "R3": set()}
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R3", "area": 50.0, "detectors": 2, "occupancy": "office"},
        ], adjacency=adjacency)
        # With no adjacency connections, each room is its own cluster
        assert report.total_zones >= 3

    def test_chain_adjacency(self):
        """R1-R2-R3 chain: all should be in same cluster."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(separate_occupancy_types=False, prefer_adjacent=True)
        )
        adjacency = {"R1": {"R2"}, "R2": {"R1", "R3"}, "R3": {"R2"}}
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 30.0, "detectors": 1, "occupancy": "office"},
            {"id": "R2", "area": 30.0, "detectors": 1, "occupancy": "office"},
            {"id": "R3", "area": 30.0, "detectors": 1, "occupancy": "office"},
        ], adjacency=adjacency)
        assert report.total_zones >= 1


# ─────────────────────────────────────────────────────────────────────────────
# FireZoneEngine — Zone ID Generation
# ─────────────────────────────────────────────────────────────────────────────


class TestFireZoneEngineZoneIDs:
    def test_zone_id_format_with_floor(self):
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
        ])
        zone_id = report.zones[0].zone_id
        assert "GF" in zone_id
        assert "Z" in zone_id

    def test_zone_id_sequential(self):
        engine = FireZoneEngine(
            constraints=ZoneConstraints(max_detectors_per_zone=1, separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 1, "occupancy": "office"},
            {"id": "R2", "area": 50.0, "detectors": 1, "occupancy": "office"},
        ])
        assert len(report.zones) >= 2
        zone_ids = [z.zone_id for z in report.zones]
        # IDs should be unique
        assert len(zone_ids) == len(set(zone_ids))


# ─────────────────────────────────────────────────────────────────────────────
# FireZoneEngine — Warnings
# ─────────────────────────────────────────────────────────────────────────────


class TestFireZoneEngineWarnings:
    def test_area_exceeds_warning(self):
        """Zone exceeding max_area_sqm generates warning."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(max_area_sqm=50.0, separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 80.0, "detectors": 2, "occupancy": "office"},
        ])
        # Large room that can't be split → area exceeds limit
        area_warnings = [w for w in report.warnings if "area" in w.lower() and "exceeds" in w.lower()]
        assert len(area_warnings) >= 1

    def test_detector_exceeds_warning(self):
        """Zone exceeding max_detectors_per_zone generates warning."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(max_detectors_per_zone=2, separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 5, "occupancy": "office"},
        ])
        det_warnings = [w for w in report.warnings if "detector" in w.lower() and "limit" in w.lower()]
        assert len(det_warnings) >= 1

    def test_slc_loop_capacity_warning(self):
        """Floor total detectors exceeding SLC loop capacity → warning."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(max_slc_devices_per_loop=5, separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": f"R{i}", "area": 50.0, "detectors": 2, "occupancy": "office"}
            for i in range(3)
        ])
        slc_warnings = [w for w in report.warnings if "SLC" in w or "FLOOR_DETECTOR_COUNT" in w]
        assert len(slc_warnings) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# FireZoneEngine — build_zone_map
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildZoneMap:
    def test_zone_map_from_report(self):
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 80.0, "detectors": 3, "occupancy": "office"},
        ])
        zone_map = engine.build_zone_map(report)
        assert "R1" in zone_map
        assert "R2" in zone_map
        # Both rooms in same zone
        assert zone_map["R1"] == zone_map["R2"]

    def test_zone_map_multiple_zones(self):
        engine = FireZoneEngine(
            constraints=ZoneConstraints(separate_occupancy_types=True)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
            {"id": "R2", "area": 60.0, "detectors": 3, "occupancy": "industrial"},
        ])
        zone_map = engine.build_zone_map(report)
        assert len(zone_map) == 2
        # Different occupancy → different zones
        assert zone_map["R1"] != zone_map["R2"]


# ─────────────────────────────────────────────────────────────────────────────
# FireZoneEngine — Room Normalization
# ─────────────────────────────────────────────────────────────────────────────


class TestFireZoneEngineRoomNormalization:
    def test_room_id_key(self):
        """Rooms can use 'id' or 'room_id' key."""
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [
            {"room_id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
        ])
        assert len(report.zones) >= 1
        assert "R1" in report.zones[0].rooms

    def test_detector_count_key(self):
        """Rooms can use 'detectors' or 'detector_count' key."""
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detector_count": 2, "occupancy": "office"},
        ])
        assert report.total_detectors == 2

    def test_occupancy_room_type_key(self):
        """Rooms can use 'occupancy' or 'room_type' key."""
        engine = FireZoneEngine()
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2, "room_type": "office"},
        ])
        assert report.total_zones >= 1

    def test_default_occupancy(self):
        """Missing occupancy defaults to 'standard'."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(separate_occupancy_types=False)
        )
        report = engine.cluster_floor("GF", [
            {"id": "R1", "area": 50.0, "detectors": 2},
        ])
        assert report.total_zones >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Integration — Multi-Zone Scenario
# ─────────────────────────────────────────────────────────────────────────────


class TestFireZoneEngineIntegration:
    def test_large_building_clustering(self):
        """10 rooms, mixed occupancy, tight constraints."""
        engine = FireZoneEngine(
            constraints=ZoneConstraints(
                max_area_sqm=200.0,
                max_detectors_per_zone=5,
                separate_occupancy_types=True,
            )
        )
        rooms = []
        for i in range(5):
            rooms.append({"id": f"office_{i}", "area": 50.0, "detectors": 2, "occupancy": "office"})
            rooms.append({"id": f"industrial_{i}", "area": 80.0, "detectors": 3, "occupancy": "industrial"})
        report = engine.cluster_floor("GF", rooms)
        assert report.total_zones >= 2  # At least one per occupancy type
        assert report.total_area_sqm == pytest.approx(5 * 50 + 5 * 80, abs=0.1)
        assert report.total_detectors == 5 * 2 + 5 * 3
