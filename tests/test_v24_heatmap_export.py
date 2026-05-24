"""
tests/test_v24_heatmap_export.py
=================================
Tests for GAP-2: export_heatmap_json() on HybridSurvivabilityEngine.
Verifies that the exported JSON matches the HybridSurvivabilityMap model
and can be consumed by the WebGL heatmap viewer.

Run: pytest tests/test_v24_heatmap_export.py -v
"""

import json
import os
import tempfile

import pytest

from fireai.core.models_v21 import (
    FlameDetectorSpec,
    RayTracePoint,
    WavelengthBand,
)
from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace
from fireai.core.ugld_acoustics import UltrasonicSensor
from fireai.core.hybrid_survivability import (
    HybridSurvivabilityEngine,
    HybridSurvivabilityMap,
    SurvivabilityClass,
)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def simple_grid() -> list[RayTracePoint]:
    """5x5 grid at z=3m."""
    grid = []
    for ix in range(5):
        for iy in range(5):
            grid.append(RayTracePoint(x=float(ix), y=float(iy), z=3.0))
    return grid


@pytest.fixture
def flame_detector() -> FlameDetectorSpec:
    return FlameDetectorSpec(
        detector_id="FD-001",
        position=[2.0, 2.0, 6.0],
        orientation_vector=[0.0, 0.0, -1.0],
        rated_range_m=30.0,
        aoc_deg=90.0,
        spectral_bands=[WavelengthBand.UV, WavelengthBand.IR1],
    )


@pytest.fixture
def ugld_sensor() -> UltrasonicSensor:
    return UltrasonicSensor(
        sensor_id="UGLD-001",
        trigger_threshold_db=74.0,
        background_noise_db=55.0,
        center_frequency_hz=40_000.0,
    )


@pytest.fixture
def hybrid_map(simple_grid, flame_detector, ugld_sensor):
    """Produce a HybridSurvivabilityMap for testing the export."""
    ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
    optical_result = ray_engine.analyse_multi_v21(
        detectors=[flame_detector],
        target_grid=simple_grid,
        obstructions=[],
    )

    sensor_positions = {"UGLD-001": (2.0, 2.0, 5.0)}
    hybrid_engine = HybridSurvivabilityEngine(
        leak_spl_at_1m=100.0,
        temp_c=40.0,
        relative_humidity_pct=30.0,
    )
    return hybrid_engine.analyse(
        optical_result=optical_result,
        grid=simple_grid,
        ugld_sensors=[ugld_sensor],
        sensor_positions=sensor_positions,
    )


# ── Tests ──────────────────────────────────────────────────────────

class TestExportHeatmapJSON:

    def test_export_creates_file(self, hybrid_map):
        """export_heatmap_json() must create a valid JSON file."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            result_path = engine.export_heatmap_json(hybrid_map, output_path)
            assert result_path == output_path
            assert os.path.exists(output_path)

            with open(output_path, "r") as f:
                data = json.load(f)
            assert isinstance(data, dict)
        finally:
            os.unlink(output_path)

    def test_json_has_required_top_level_keys(self, hybrid_map):
        """JSON must have meta, statistics, class_legend, points."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            assert "meta" in data
            assert "statistics" in data
            assert "class_legend" in data
            assert "points" in data
        finally:
            os.unlink(output_path)

    def test_meta_has_version_and_standards(self, hybrid_map):
        """meta must include version and standards references."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            assert data["meta"]["version"] == "FireAI_V24"
            assert "NFPA 72" in str(data["meta"]["standards"])
            assert data["meta"]["total_points"] == hybrid_map.total_points
        finally:
            os.unlink(output_path)

    def test_statistics_match_hybrid_map(self, hybrid_map):
        """Statistics percentages must match the HybridSurvivabilityMap."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            stats = data["statistics"]
            assert stats["total_points"] == hybrid_map.total_points
            # Verify percentage consistency
            total_pct = (
                stats["redundant_hybrid_pct"]
                + stats["optical_only_pct"]
                + stats["acoustic_only_pct"]
                + stats["blind_spot_pct"]
            )
            assert abs(total_pct - 100.0) < 1.0  # Allow rounding
        finally:
            os.unlink(output_path)

    def test_points_count_matches_hybrid_map(self, hybrid_map):
        """Number of exported points must match total_points."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            assert len(data["points"]) == hybrid_map.total_points
        finally:
            os.unlink(output_path)

    def test_each_point_has_required_fields(self, hybrid_map):
        """Each point must have x, y, z, class, optical_count, acoustic_snr_db, color."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            required_keys = {"x", "y", "z", "class", "optical_count",
                             "acoustic_snr_db", "color"}
            for pt in data["points"]:
                assert required_keys.issubset(set(pt.keys())), (
                    f"Point missing keys: {required_keys - set(pt.keys())}"
                )
        finally:
            os.unlink(output_path)

    def test_class_values_are_valid(self, hybrid_map):
        """All point class values must be one of the 4 valid classes."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            valid_classes = {
                "REDUNDANT_HYBRID", "OPTICAL_ONLY",
                "ACOUSTIC_ONLY", "BLIND_SPOT",
            }
            for pt in data["points"]:
                assert pt["class"] in valid_classes, (
                    f"Invalid class: {pt['class']}"
                )
        finally:
            os.unlink(output_path)

    def test_colors_match_classes(self, hybrid_map):
        """Color must match the class according to NFPA 72 convention."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            expected_colors = {
                "REDUNDANT_HYBRID": "#00AA44",
                "OPTICAL_ONLY":     "#FFD700",
                "ACOUSTIC_ONLY":    "#FF8C00",
                "BLIND_SPOT":       "#CC0000",
            }
            for pt in data["points"]:
                assert pt["color"] == expected_colors[pt["class"]], (
                    f"Color mismatch for {pt['class']}: "
                    f"got {pt['color']}, expected {expected_colors[pt['class']]}"
                )
        finally:
            os.unlink(output_path)

    def test_class_legend_has_four_entries(self, hybrid_map):
        """class_legend must have all 4 coverage classes."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            legend = data["class_legend"]
            assert len(legend) == 4
            for cls in ["REDUNDANT_HYBRID", "OPTICAL_ONLY",
                        "ACOUSTIC_ONLY", "BLIND_SPOT"]:
                assert cls in legend
                assert "color" in legend[cls]
                assert "label" in legend[cls]
        finally:
            os.unlink(output_path)

    def test_acoustic_snr_db_is_number_or_null(self, hybrid_map):
        """acoustic_snr_db must be a number or null for each point."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            for pt in data["points"]:
                snr = pt["acoustic_snr_db"]
                assert snr is None or isinstance(snr, (int, float)), (
                    f"acoustic_snr_db must be number or null, got {type(snr)}"
                )
        finally:
            os.unlink(output_path)

    def test_coordinates_match_hybrid_map(self, hybrid_map):
        """Point coordinates must match the HybridSurvivabilityMap."""
        engine = HybridSurvivabilityEngine()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            output_path = f.name

        try:
            engine.export_heatmap_json(hybrid_map, output_path)
            with open(output_path, "r") as f:
                data = json.load(f)

            # Build a set of (x,y,z,class) from the map
            map_entries = set()
            for idx, pr in hybrid_map.point_results.items():
                map_entries.add((
                    round(pr.x, 6),
                    round(pr.y, 6),
                    round(pr.z, 6),
                    pr.survivability_class.value,
                ))

            json_entries = set()
            for pt in data["points"]:
                json_entries.add((
                    round(pt["x"], 6),
                    round(pt["y"], 6),
                    round(pt["z"], 6),
                    pt["class"],
                ))

            assert map_entries == json_entries, (
                "Exported coordinates don't match HybridSurvivabilityMap"
            )
        finally:
            os.unlink(output_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
