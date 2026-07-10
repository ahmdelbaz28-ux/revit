"""
Gate 2: Runtime Validation Tests.
=================================
Validates that the skill loads and executes cleanly at runtime.

Per FireAI agent.md VERIFICATION GATES:
    [Gate 2] Runtime Validation
    - startup success (imports clean)
    - execution stability (no crashes)
    - dependency integrity (yaml available)
    - resource validation (file handles)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Module imports
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleImports:
    """Test that all skill modules import cleanly."""

    def test_skill_loader_imports(self) -> None:
        mod = importlib.import_module("skill_loader")
        assert hasattr(mod, "load_skill")
        assert hasattr(mod, "load_skill_or_raise")
        assert hasattr(mod, "SkillFrontMatter")
        assert hasattr(mod, "SkillStructure")
        assert hasattr(mod, "ValidationResult")

    def test_internal_simulation_engine_imports(self) -> None:
        mod = importlib.import_module("internal_simulation_engine")
        assert hasattr(mod, "simulate_cable_sizing")
        assert hasattr(mod, "simulate_transformer_sizing")
        assert hasattr(mod, "simulate_protection_coordination")
        assert hasattr(mod, "simulate_arc_flash")
        assert hasattr(mod, "simulate_flisr")
        assert hasattr(mod, "run_all_simulations")

    def test_yaml_dependency_available(self) -> None:
        import yaml

        assert hasattr(yaml, "safe_load")

    def test_pydantic_dependency_available(self) -> None:
        import pydantic

        assert hasattr(pydantic, "BaseModel")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Loader execution
# ═══════════════════════════════════════════════════════════════════════════


class TestLoaderExecution:
    """Test that loader executes without runtime errors."""

    def test_load_skill_returns_result(self) -> None:
        from skill_loader import load_skill

        result = load_skill(SKILL_ROOT / "SKILL.md")
        assert result is not None
        assert hasattr(result, "is_valid")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert hasattr(result, "structure")

    def test_load_skill_or_raise_returns_structure(self) -> None:
        from skill_loader import load_skill_or_raise

        structure = load_skill_or_raise(SKILL_ROOT / "SKILL.md")
        assert structure is not None
        assert structure.front_matter.name == "etap-expert"

    def test_load_nonexistent_file_fails_gracefully(self) -> None:
        from skill_loader import load_skill

        result = load_skill("/nonexistent/path/SKILL.md")
        assert not result.is_valid
        assert any("not found" in e for e in result.errors)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Simulation engine execution
# ═══════════════════════════════════════════════════════════════════════════


class TestSimulationEngineExecution:
    """Test that all 5 simulations execute without errors."""

    def test_cable_sizing_runs(self) -> None:
        from internal_simulation_engine import simulate_cable_sizing

        result = simulate_cable_sizing()
        assert result is not None
        assert result.recommended_size
        assert result.ampacity_a > 0
        assert result.voltage_drop_v > 0
        assert result.voltage_drop_pct > 0

    def test_transformer_sizing_runs(self) -> None:
        from internal_simulation_engine import simulate_transformer_sizing

        result = simulate_transformer_sizing()
        assert result.recommended_size_kva > 0
        assert result.loading_pct > 0

    def test_protection_coordination_runs(self) -> None:
        from internal_simulation_engine import simulate_protection_coordination

        result = simulate_protection_coordination()
        assert result.motor_fla_a > 0
        assert result.ct_ratio_primary > 0
        assert result.relay_50_pickup_primary_a > 0
        assert result.relay_51_pickup_primary_a > 0

    def test_arc_flash_runs(self) -> None:
        from internal_simulation_engine import simulate_arc_flash

        result = simulate_arc_flash()
        assert result.arcing_current_ka > 0
        assert result.incident_energy_cal_cm2 > 0
        assert 0 <= result.ppe_category <= 4

    def test_flisr_runs(self) -> None:
        from internal_simulation_engine import simulate_flisr

        result = simulate_flisr()
        assert result.fault_distance_miles > 0
        assert result.isolation_time_seconds > 0

    def test_run_all_simulations_returns_dict(self) -> None:
        from internal_simulation_engine import run_all_simulations

        results = run_all_simulations()
        assert isinstance(results, dict)
        # V131 Phase 2: expanded from 5 → 7 simulations (added Harmonic + Transient Stability)
        assert len(results) == 7
        expected_keys = {
            "cable_sizing", "transformer_sizing", "protection_coordination",
            "arc_flash", "flisr", "harmonic_analysis", "transient_stability"
        }
        assert set(results.keys()) == expected_keys
