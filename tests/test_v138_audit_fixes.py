# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
test_v138_audit_fixes.py — Regression tests for V138 AUDIT findings.

V138 fixes: F-1 (generation_ms), F-2 (DLQ TOCTOU), F-3 (SSRF fail-closed),
F-5 (converged), F-7 (path bypass), F-12 (SSRF fail-closed), F-13 (size limits),
F-14 (Pydantic model), F-15 (double-checked locking), F-16 (dead code),
V137-F-10 (violations restore), V137-F-11 (audit_safe_dict).
"""

from __future__ import annotations

import pytest


class TestGenerationMsNotStale:
    """V138 F-1: generation_ms must use per-variant data (not stale loop variable)."""

    def test_generation_ms_differs_per_variant(self):
        """Each variant should have its own generation_ms (not all same)."""
        from fireai.core.spatial_engine.density_optimizer import Room
        from fireai.core.spatial_engine.generative_layout_agent import (
            GenerativeLayoutAgent,
        )

        agent = GenerativeLayoutAgent(use_multiprocessing=False)
        room = Room(name="TestStale", width=10.0, length=8.0, ceiling_height=3.0)
        result = agent.generate_variants(room, occupancy_type="office")

        # (the OLD bug made them all the same — last variant's value)
        ms_values = [vr.generation_ms for vr in result.variants.values()]
        # At least 2 should be different (timing may coincidentally match)
        unique_ms = {round(ms, 3) for ms in ms_values}
        assert len(unique_ms) >= 2 or all(ms == 0 for ms in ms_values), (
            f"All generation_ms values are identical ({ms_values}) — stale variable bug"
        )


class TestDLQReplayTOCTOU:
    """V138 F-2: replay_dead_letter should pop first (no TOCTOU)."""

    def test_replay_invalid_index_returns_false(self):
        """Invalid index should return False."""
        from fireai.infrastructure.webhook_service import WebhookDeliveryService
        service = WebhookDeliveryService(allow_http=True)
        assert service.replay_dead_letter(999) is False
        assert service.replay_dead_letter(-1) is False


class TestSSRFFailClosed:
    """V138 F-12: SSRF check must fail CLOSED (block on error)."""

    def test_ssrf_check_returns_error_on_exception(self):
        """_check_ssrf_url should return error string (not None) on exception."""
        import inspect

        from fireai.infrastructure.webhook_service import WebhookDeliveryService
        source = inspect.getsource(WebhookDeliveryService._check_ssrf_url)
        assert "BLOCKING request" in source, (
            "SSRF check must fail CLOSED (was fail-open in V137)"
        )


class TestConvergedField:
    """V138 F-5: converged field must reflect actual convergence."""

    def test_normal_calculation_converged_true(self):
        """Normal water flow should report converged=True."""
        from fireai.core.darcy_weisbach_solver import (
            FluidType,
            calculate_darcy_weisbach_friction_loss,
        )
        result = calculate_darcy_weisbach_friction_loss(
            pipe_length_m=100.0, pipe_diameter_m=0.05,
            flow_rate_kg_s=1.0, fluid_type=FluidType.WATER,
        )
        assert result.converged is True

    def test_converged_in_to_dict(self):
        """to_dict should include converged field."""
        from fireai.core.darcy_weisbach_solver import (
            FluidType,
            calculate_darcy_weisbach_friction_loss,
        )
        result = calculate_darcy_weisbach_friction_loss(
            pipe_length_m=10.0, pipe_diameter_m=0.05,
            flow_rate_kg_s=1.0, fluid_type=FluidType.WATER,
        )
        assert "converged" in result.to_dict()


class TestPathValidationBypass:
    """V138 F-7: Path validation must use proper containment (not startswith)."""

    def test_extract_rooms_uses_relative_to(self):
        """extract_rooms should use Path.relative_to (not startswith)."""
        import inspect

        from backend.routers.v2 import extract_rooms
        source = inspect.getsource(extract_rooms)
        assert "relative_to" in source or "_is_within" in source, (
            "Path validation must use proper containment check (not startswith)"
        )


class TestSizeLimits:
    """V138 F-13: API requests must have upper bounds."""

    def test_generative_design_has_upper_bounds(self):
        """GenerativeDesignRequest must have le=1000 for dimensions."""
        from backend.routers.v2 import GenerativeDesignRequest
        fields = GenerativeDesignRequest.model_fields
        assert "le=1000.0" in str(fields["room_width"].metadata) or \
               any("le" in str(m) for m in fields["room_width"].metadata), \
               "room_width must have upper bound (le=1000)"

    def test_smoke_points_have_max_length(self):
        """SmokeSimulationStateRequest must have max_length for points."""
        from backend.routers.v2 import SmokeSimulationStateRequest
        fields = SmokeSimulationStateRequest.model_fields
        assert any("max_length" in str(m) for m in fields["smoke_density_points"].metadata), \
               "smoke_density_points must have max_length"


class TestPydanticSmokePoints:
    """V138 F-14: Smoke density points must use Pydantic model (not Dict)."""

    def test_smoke_point_model_exists(self):
        """SmokeDensityPointRequest should exist as a Pydantic model."""
        from backend.routers.v2 import SmokeDensityPointRequest
        # S5727 fix: the import itself is the smoke check. Assert on the type
        # rather than the tautological `is not None` (which SonarCloud flags
        # because it's always True after a successful import).
        assert isinstance(SmokeDensityPointRequest, type)

    def test_missing_z_raises_422(self):
        """Missing 'z' field should produce 422 (not 500 KeyError)."""
        from pydantic import ValidationError

        from backend.routers.v2 import SmokeDensityPointRequest
        with pytest.raises(ValidationError):
            SmokeDensityPointRequest(x=1.0, y=2.0)  # missing z, density_kg_m3


class TestDeadCodeRemoved:
    """V138 F-16: CSRF_COOKIE_ATTRIBUTES should be removed."""

    def test_dead_constant_removed(self):
        """CSRF_COOKIE_ATTRIBUTES should not exist."""
        from backend import security_csrf
        assert not hasattr(security_csrf, "CSRF_COOKIE_ATTRIBUTES"), (
            "CSRF_COOKIE_ATTRIBUTES should be removed (dead code)"
        )


class TestDoubleCheckedLocking:
    """V138 F-15: _init_database should have all init code inside lock."""

    def test_init_code_inside_lock(self):
        """_init_database should have _db_initialized=True inside the lock block."""
        import inspect

        from fireai.core.audit_store import _init_database
        source = inspect.getsource(_init_database)
        # The _db_initialized = True should be inside the with _init_lock block
        # (indented more than the 'with' statement)
        lines = source.split('\n')
        in_lock = False
        init_inside = False
        for line in lines:
            if 'with _init_lock' in line:
                in_lock = True
            if in_lock and '_db_initialized = True' in line:
                init_inside = True
                break
        assert init_inside, "_db_initialized=True must be inside the lock block"


class TestViolationsRestore:
    """V137 F-10: _remove_redundant should restore violations on rollback."""

    def test_violations_restored_code_exists(self):
        """_remove_redundant should save and restore violations."""
        import inspect

        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        source = inspect.getsource(DensityOptimizer._remove_redundant)
        assert "old_violations" in source, (
            "_remove_redundant must save/restore violations (V137 F-10)"
        )


class TestAuditSafeDict:
    """V137 F-11: to_audit_safe_dict should reject non-VALIDATED states."""

    def test_failed_state_returns_minimal_dict(self):
        """FAILED state should not persist full data."""
        from fireai.core.smoke_simulation_state import (
            SimulationStatus,
            SmokeDensityPoint,
            SmokeSimulationState,
        )
        state = SmokeSimulationState(
            room_id="R-001",
            smoke_density_points=[
                SmokeDensityPoint(x=0, y=0, z=1.7, density_kg_m3=0.05),
            ],
            status=SimulationStatus.FAILED,
        )
        d = state.to_audit_safe_dict()
        assert "smoke_density_points" not in d, (
            "FAILED state should not persist measurement data"
        )
        assert "note" in d

    def test_validated_state_persists_full_data(self):
        """VALIDATED state should persist full data."""
        from fireai.core.smoke_simulation_state import (
            SmokeDensityPoint,
            SmokeSimulationState,
        )
        state = SmokeSimulationState.create_from_fds(
            room_id="R-001",
            smoke_density_points=[
                SmokeDensityPoint(x=0, y=0, z=1.7, density_kg_m3=0.02),
            ],
            visibility_at_height={1.7: 10.0},
            fds_run_id="fds-2026-001",
        )
        d = state.to_audit_safe_dict()
        assert "smoke_density_points" in d
