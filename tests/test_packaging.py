"""
Packaging smoke-tests for fireai v1.0.0.
Validates imports, version string, public API surface, and CLI entry point.
"""
import subprocess
import sys

import pytest


def test_import_fireai():
    import fireai
    assert fireai is not None


def test_version_is_string():
    import fireai
    assert isinstance(fireai.__version__, str)
    assert len(fireai.__version__) > 0


def test_version_value():
    import fireai
    assert fireai.__version__ == "1.0.0"


def test_floor_analyser_importable():
    from fireai import FloorAnalyser
    assert FloorAnalyser is not None


def test_building_engine_importable():
    from fireai import BuildingEngine
    assert BuildingEngine is not None


def test_density_optimizer_importable():
    from fireai import DensityOptimizer
    assert DensityOptimizer is not None


def test_sensitivity_analyzer_importable():
    from fireai import SensitivityAnalyzer
    assert SensitivityAnalyzer is not None


def test_parameter_optimizer_importable():
    from fireai import ParameterOptimizer
    assert ParameterOptimizer is not None


def test_project_learner_importable():
    from fireai import ProjectLearner
    assert ProjectLearner is not None


def test_scenario_runner_importable():
    from fireai import ScenarioRunner
    assert ScenarioRunner is not None


def test_scenario_library_importable():
    from fireai import ScenarioLibrary
    assert ScenarioLibrary is not None


def test_scenario_reporter_importable():
    from fireai import ScenarioReporter
    assert ScenarioReporter is not None


def test_polygon_density_optimizer_importable():
    from fireai import PolygonDensityOptimizer
    assert PolygonDensityOptimizer is not None


def test_audit_trail_importable():
    from fireai import AuditTrail
    assert AuditTrail is not None


def test_generate_building_report_importable_and_callable():
    from fireai import generate_building_report
    assert callable(generate_building_report)


def test_cli_version_flag_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "fireai.core.fire_cli", "--version"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "1.0.0" in result.stdout


def test_cli_version_subcommand_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "fireai.core.fire_cli", "version"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "1.0.0" in result.stdout


def test_cli_no_args_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "fireai.core.fire_cli"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_cli_analyse_missing_file_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "fireai.core.fire_cli",
         "analyse", "/nonexistent/path/room.json"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
