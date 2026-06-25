"""test_smoke_simulation_state.py — Tests for Smoke Simulation Hooks.

MISSION TASK 4.1 — Validates placeholder smoke density and visibility
gradient data structures for future FDS integration.

Per agent.md Rule 10 + Rule 1 (no fabrication).
"""

from __future__ import annotations

import math

import pytest

from fireai.core.smoke_simulation_state import (
    DEFAULT_VISIBILITY_HEIGHTS_M,
    EYE_LEVEL_ADULT_M,
    FDSIntegrationConfig,
    PLACEHOLDER_VALIDATION_WARNING,
    SimulationStatus,
    SmokeDensityPoint,
    SmokeSimulationState,
    SOURCE_FDS,
    SOURCE_PLACEHOLDER,
    VisibilityGradient,
    VISIBILITY_TENABILITY_THRESHOLD_M,
    SMOKE_DENSITY_TENABILITY_THRESHOLD_KG_M3,
)


# ---------------------------------------------------------------------------
# Placeholder Creation Tests
# ---------------------------------------------------------------------------


class TestPlaceholder:
    def test_create_placeholder_returns_placeholder_status(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        assert state.status == SimulationStatus.PLACEHOLDER

    def test_placeholder_has_validation_warning(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        assert state.validation_warning is not None
        assert "NOT VALIDATED" in state.validation_warning

    def test_placeholder_warning_mentions_nfpa_72(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        assert "NFPA 72" in state.validation_warning

    def test_placeholder_is_not_validated(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        assert state.is_validated is False
        assert state.is_placeholder is True

    def test_placeholder_has_no_smoke_points(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        assert len(state.smoke_density_points) == 0

    def test_placeholder_has_no_visibility_gradient(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        assert state.visibility_gradient is None


# ---------------------------------------------------------------------------
# SmokeDensityPoint Tests
# ---------------------------------------------------------------------------


class TestSmokeDensityPoint:
    def test_valid_point_creation(self):
        p = SmokeDensityPoint(x=5.0, y=3.0, z=1.7, density_kg_m3=0.025)
        assert p.x == 5.0
        assert p.density_kg_m3 == 0.025

    def test_nan_x_rejected(self):
        with pytest.raises(ValueError, match="must be finite"):
            SmokeDensityPoint(x=float("nan"), y=0, z=0, density_kg_m3=0.01)

    def test_nan_y_rejected(self):
        with pytest.raises(ValueError, match="must be finite"):
            SmokeDensityPoint(x=0, y=float("nan"), z=0, density_kg_m3=0.01)

    def test_nan_z_rejected(self):
        with pytest.raises(ValueError, match="must be finite"):
            SmokeDensityPoint(x=0, y=0, z=float("nan"), density_kg_m3=0.01)

    def test_nan_density_rejected(self):
        with pytest.raises(ValueError, match="must be finite"):
            SmokeDensityPoint(x=0, y=0, z=0, density_kg_m3=float("nan"))

    def test_negative_density_rejected(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            SmokeDensityPoint(x=0, y=0, z=0, density_kg_m3=-0.01)

    def test_inf_density_rejected(self):
        with pytest.raises(ValueError, match="must be finite"):
            SmokeDensityPoint(x=0, y=0, z=0, density_kg_m3=float("inf"))

    def test_tenability_threshold_detection(self):
        # Below threshold
        p_safe = SmokeDensityPoint(x=0, y=0, z=0, density_kg_m3=0.04)
        assert p_safe.is_tenability_threshold_exceeded is False

        # At threshold
        p_threshold = SmokeDensityPoint(x=0, y=0, z=0, density_kg_m3=0.05)
        assert p_threshold.is_tenability_threshold_exceeded is True

        # Above threshold
        p_dangerous = SmokeDensityPoint(x=0, y=0, z=0, density_kg_m3=0.10)
        assert p_dangerous.is_tenability_threshold_exceeded is True

    def test_optical_density_calculation(self):
        p = SmokeDensityPoint(x=0, y=0, z=0, density_kg_m3=0.001)
        # 0.001 kg/m³ = 1 g/m³ → optical density = 7.6 * 1 = 7.6 dB/m
        assert math.isclose(p.optical_density_db_per_m, 7.6, rel_tol=0.01)


# ---------------------------------------------------------------------------
# VisibilityGradient Tests
# ---------------------------------------------------------------------------


class TestVisibilityGradient:
    def test_valid_gradient_creation(self):
        g = VisibilityGradient(
            room_id="R-001",
            visibility_at_height={1.7: 8.5, 2.5: 4.2},
        )
        assert g.room_id == "R-001"
        assert len(g.visibility_at_height) == 2

    def test_nan_height_rejected(self):
        with pytest.raises(ValueError, match="Invalid height"):
            VisibilityGradient(room_id="R", visibility_at_height={float("nan"): 5.0})

    def test_negative_height_rejected(self):
        with pytest.raises(ValueError, match="Invalid height"):
            VisibilityGradient(room_id="R", visibility_at_height={-1.0: 5.0})

    def test_nan_visibility_rejected(self):
        with pytest.raises(ValueError, match="Invalid visibility"):
            VisibilityGradient(room_id="R", visibility_at_height={1.7: float("nan")})

    def test_negative_visibility_rejected(self):
        with pytest.raises(ValueError, match="Invalid visibility"):
            VisibilityGradient(room_id="R", visibility_at_height={1.7: -5.0})

    def test_visibility_at_eye_level_returns_closest(self):
        g = VisibilityGradient(
            room_id="R",
            visibility_at_height={1.5: 6.0, 2.0: 5.0},
        )
        # 1.7 is closer to 1.5
        assert g.visibility_at_eye_level == 6.0

    def test_visibility_at_eye_level_none_if_empty(self):
        g = VisibilityGradient(room_id="R", visibility_at_height={})
        assert g.visibility_at_eye_level is None

    def test_tenability_threshold_detection(self):
        # Below 10m at eye level = exceeded
        g_dangerous = VisibilityGradient(
            room_id="R",
            visibility_at_height={1.7: 5.0},
        )
        assert g_dangerous.is_tenability_threshold_exceeded is True

        # Above 10m = safe
        g_safe = VisibilityGradient(
            room_id="R",
            visibility_at_height={1.7: 15.0},
        )
        assert g_safe.is_tenability_threshold_exceeded is False

    def test_min_max_visibility(self):
        g = VisibilityGradient(
            room_id="R",
            visibility_at_height={1.0: 10.0, 2.0: 5.0, 3.0: 15.0},
        )
        assert g.min_visibility == 5.0
        assert g.max_visibility == 15.0


# ---------------------------------------------------------------------------
# FDS Integration Tests
# ---------------------------------------------------------------------------


class TestFDSIntegration:
    def test_update_from_fds_validates_state(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        state.update_from_fds(
            smoke_density_points=[
                SmokeDensityPoint(x=5, y=3, z=1.7, density_kg_m3=0.025),
            ],
            visibility_at_height={1.7: 8.5},
            fds_run_id="fds-001",
        )
        assert state.is_validated is True
        assert state.status == SimulationStatus.VALIDATED
        assert state.validation_warning is None
        assert state.fds_run_id == "fds-001"

    def test_create_from_fds_factory(self):
        state = SmokeSimulationState.create_from_fds(
            room_id="R-001",
            smoke_density_points=[
                SmokeDensityPoint(x=0, y=0, z=1.7, density_kg_m3=0.02),
            ],
            visibility_at_height={1.7: 10.0},
            fds_run_id="fds-002",
        )
        assert state.is_validated is True
        assert state.fds_run_id == "fds-002"

    def test_fds_points_marked_with_fds_source(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        state.update_from_fds(
            smoke_density_points=[
                SmokeDensityPoint(x=0, y=0, z=0, density_kg_m3=0.01, source="placeholder"),
            ],
            visibility_at_height={1.7: 10.0},
            fds_run_id="fds-003",
        )
        for p in state.smoke_density_points:
            assert p.source == SOURCE_FDS

    def test_mark_pending(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        state.mark_pending("fds-004")
        assert state.status == SimulationStatus.PENDING
        assert state.fds_run_id == "fds-004"

    def test_mark_failed(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        state.mark_failed("Mesh generation error")
        assert state.status == SimulationStatus.FAILED
        assert "Mesh generation error" in state.validation_warning


# ---------------------------------------------------------------------------
# Safety Properties Tests
# ---------------------------------------------------------------------------


class TestSafetyProperties:
    def test_max_smoke_density_empty_returns_none(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        assert state.max_smoke_density is None

    def test_max_smoke_density_returns_max(self):
        state = SmokeSimulationState.create_from_fds(
            room_id="R-001",
            smoke_density_points=[
                SmokeDensityPoint(x=0, y=0, z=0, density_kg_m3=0.01),
                SmokeDensityPoint(x=1, y=1, z=1, density_kg_m3=0.05),
                SmokeDensityPoint(x=2, y=2, z=2, density_kg_m3=0.03),
            ],
            visibility_at_height={1.7: 10.0},
            fds_run_id="fds-005",
        )
        assert state.max_smoke_density == 0.05

    def test_is_tenability_exceeded_by_density(self):
        state = SmokeSimulationState.create_from_fds(
            room_id="R-001",
            smoke_density_points=[
                SmokeDensityPoint(x=0, y=0, z=1.7, density_kg_m3=0.06),  # Above threshold
            ],
            visibility_at_height={1.7: 20.0},  # Safe visibility
            fds_run_id="fds-006",
        )
        assert state.is_tenability_exceeded is True

    def test_is_tenability_exceeded_by_visibility(self):
        state = SmokeSimulationState.create_from_fds(
            room_id="R-001",
            smoke_density_points=[
                SmokeDensityPoint(x=0, y=0, z=1.7, density_kg_m3=0.01),  # Safe density
            ],
            visibility_at_height={1.7: 5.0},  # Below 10m threshold
            fds_run_id="fds-007",
        )
        assert state.is_tenability_exceeded is True

    def test_is_tenability_not_exceeded_when_safe(self):
        state = SmokeSimulationState.create_from_fds(
            room_id="R-001",
            smoke_density_points=[
                SmokeDensityPoint(x=0, y=0, z=1.7, density_kg_m3=0.01),
            ],
            visibility_at_height={1.7: 15.0},
            fds_run_id="fds-008",
        )
        assert state.is_tenability_exceeded is False


# ---------------------------------------------------------------------------
# Audit Safety Tests (SAFETY-R2)
# ---------------------------------------------------------------------------


class TestAuditSafety:
    """Per VERIFY-TASK4 SAFETY-R2: placeholder data must not be persisted to AuditStore."""

    def test_placeholder_audit_safe_dict_excludes_measurements(self):
        state = SmokeSimulationState.create_placeholder("R-001")
        audit_dict = state.to_audit_safe_dict()
        # Should only have minimal fields
        assert audit_dict["placeholder"] is True
        assert "smoke_density_points" not in audit_dict
        assert "note" in audit_dict

    def test_validated_audit_safe_dict_includes_all_data(self):
        state = SmokeSimulationState.create_from_fds(
            room_id="R-001",
            smoke_density_points=[
                SmokeDensityPoint(x=0, y=0, z=1.7, density_kg_m3=0.02),
            ],
            visibility_at_height={1.7: 10.0},
            fds_run_id="fds-009",
        )
        audit_dict = state.to_audit_safe_dict()
        assert "smoke_density_points" in audit_dict
        assert "placeholder" not in audit_dict or audit_dict.get("placeholder") is False


# ---------------------------------------------------------------------------
# Serialization Tests
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_includes_all_fields(self):
        state = SmokeSimulationState.create_from_fds(
            room_id="R-001",
            smoke_density_points=[
                SmokeDensityPoint(x=1, y=2, z=3, density_kg_m3=0.02),
            ],
            visibility_at_height={1.7: 10.0},
            fds_run_id="fds-010",
        )
        d = state.to_dict()
        assert d["room_id"] == "R-001"
        assert d["status"] == "validated"
        assert d["is_validated"] is True
        assert d["fds_run_id"] == "fds-010"
        assert len(d["smoke_density_points"]) == 1
        assert d["smoke_density_points"][0]["density_kg_m3"] == 0.02


# ---------------------------------------------------------------------------
# FDSIntegrationConfig Tests
# ---------------------------------------------------------------------------


class TestFDSIntegrationConfig:
    def test_default_config_is_valid(self):
        config = FDSIntegrationConfig()
        assert config.mesh_resolution_m == 0.1
        assert config.simulation_duration_s == 600.0

    def test_invalid_mesh_resolution_rejected(self):
        with pytest.raises(ValueError, match="mesh_resolution_m must be positive"):
            FDSIntegrationConfig(mesh_resolution_m=0.0)

    def test_invalid_mesh_resolution_nan_rejected(self):
        with pytest.raises(ValueError, match="mesh_resolution_m must be positive"):
            FDSIntegrationConfig(mesh_resolution_m=float("nan"))

    def test_invalid_simulation_duration_rejected(self):
        with pytest.raises(ValueError, match="simulation_duration_s must be positive"):
            FDSIntegrationConfig(simulation_duration_s=-100)

    def test_invalid_soot_yield_rejected(self):
        with pytest.raises(ValueError, match="soot_yield must be in"):
            FDSIntegrationConfig(soot_yield=1.5)


# ---------------------------------------------------------------------------
# Constants Tests
# ---------------------------------------------------------------------------


class TestConstants:
    def test_visibility_tenability_threshold_is_10m(self):
        """Per NFPA 101 §A.7.2: minimum 10m visibility for safe egress."""
        assert VISIBILITY_TENABILITY_THRESHOLD_M == 10.0

    def test_smoke_density_tenability_threshold_is_0_05(self):
        """Per SFPE Handbook: 0.05 kg/m³ (50 mg/m³) max survivable."""
        assert SMOKE_DENSITY_TENABILITY_THRESHOLD_KG_M3 == 0.05

    def test_eye_level_adult_is_1_7m(self):
        assert EYE_LEVEL_ADULT_M == 1.7

    def test_default_visibility_heights_include_eye_level(self):
        assert EYE_LEVEL_ADULT_M in DEFAULT_VISIBILITY_HEIGHTS_M
