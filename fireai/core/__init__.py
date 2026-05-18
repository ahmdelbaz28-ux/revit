"""
fireai – NFPA 72-2022 Automated Fire Detector Placement Engine
"""

__version__ = "1.0.0"

# Core analysers
from fireai.core.floor_analyser import FloorAnalyser
from fireai.core.building_engine import BuildingEngine
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
from fireai.core.polygon_optimizer import PolygonDensityOptimizer

# Audit
from fireai.core.audit_trail import AuditTrail
from fireai.core.audit_store import AuditStore

# Reporting
from fireai.core.pdf_report import generate_pdf

# Event Bus (Digital Twin foundation)
from fireai.core.event_bus import EventBus, Event, Events, EventRecorder

# Engineering System (v2 — from calculator to engineering system)
from fireai.core.room_lifecycle import (
    RoomState, RoomTransition, RoomLifecycle, RoomLifecycleManager,
)
from fireai.core.digital_twin_interface import (
    DigitalTwinInterface, DigitalTwinState, TwinModelVersion, ChangeRecord,
)
from fireai.core.digital_twin import DigitalTwin
from fireai.core.analysis_pipeline import (
    AnalysisPipeline, PipelineStage, PipelineResult,
)
from fireai.core.spatial_engine.consensus_engine import (
    ConsensusEngine, ConsensusResult, ConfidenceLevel,
)
from fireai.core.spatial_engine.proof_certificate import (
    ProofCertificateGenerator, ProofCertificate,
)

__all__ = [
    "__version__",
    # Analysers
    "FloorAnalyser",
    "BuildingEngine",
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
    # Audit
    "AuditTrail",
    "AuditStore",
    # Reporting
    "generate_pdf",
    # Event Bus
    "EventBus",
    "Event",
    "Events",
    "EventRecorder",
    # Engineering System v2
    "RoomState",
    "RoomTransition",
    "RoomLifecycle",
    "RoomLifecycleManager",
    "DigitalTwinInterface",
    "DigitalTwinState",
    "TwinModelVersion",
    "ChangeRecord",
    "DigitalTwin",
    "AnalysisPipeline",
    "PipelineStage",
    "PipelineResult",
    "ConsensusEngine",
    "ConsensusResult",
    "ConfidenceLevel",
    "ProofCertificateGenerator",
    "ProofCertificate",
]
