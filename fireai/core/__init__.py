"""
fireai – NFPA 72-2022 Automated Fire Detector Placement Engine
"""

__version__ = "1.0.0"

# Core analysers
from fireai.core.floor_analyser import FloorAnalyser, FloorReport, RoomSummary
from fireai.core.building_engine import BuildingEngine, BuildingReport
from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

# Optimisation & analysis tools
from fireai.core.sensitivity_analyzer import SensitivityAnalyzer
from fireai.core.parameter_optimizer import ParameterOptimizer
from fireai.core.project_learner import ProjectLearner

# Scenario engine
from fireai.core.scenario_engine import (
    ScenarioRunner,
    ScenarioLibrary,
    ScenarioReporter,
)

# Polygon support
from fireai.core.polygon_optimizer import PolygonDensityOptimizer, PolygonRoom, PolygonRoomSummary

# Audit
from fireai.core.audit_trail import AuditTrail

# Reporting
from fireai.core.pdf_report import generate_building_report

__all__ = [
    "__version__",
    # Analysers
    "FloorAnalyser",
    "FloorReport",
    "RoomSummary",
    "BuildingEngine",
    "BuildingReport",
    "DensityOptimizer",
    # Tools
    "SensitivityAnalyzer",
    "ParameterOptimizer",
    "ProjectLearner",
    # Scenarios
    "ScenarioRunner",
    "ScenarioLibrary",
    "ScenarioReporter",
    # Polygon
    "PolygonDensityOptimizer",
    "PolygonRoom",
    "PolygonRoomSummary",
    # Audit
    "AuditTrail",
    # Reporting
    "generate_building_report",
]
