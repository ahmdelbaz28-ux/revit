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

# Safety Assurance (from consultant's architecture — adopted 2026-05-19)
from fireai.core.safety_assurance import (
    SafetyTier, classify_safety_tier, apply_fail_safe,
    tier_requires_fpe_review, tier_can_submit,
    OverrideRole, OverrideRecord, EngineeringEvidencePackage,
    ABSOLUTE_MINIMUM_COVERAGE, MINIMUM_COVERAGE_FOR_SUBMISSION,
    STANDARD_COVERAGE_THRESHOLD, PROOF_VERIFIED_THRESHOLD,
)

# V12 — Class A Routing + Firestopping + Safe Building Engine + DXF Schedule
from fireai.core.routing_global_class_a import EliteGlobalRouter
from fireai.core.firestop_annotator import FirestoppingAnnotator
from fireai.core.safe_building_engine import SafeBuildingEngine
from fireai.core.dxf_table_schedule import TrueAECDraftingTable
from fireai.core.routing_engine_v10 import EliteClassARouter, ArchitecturalWall, RouteSegment

# V19 — Elevator Shunt-Trip + NAC Booster Allocator + Seismic Joint Penalty
from fireai.core.elevator_shunt_trip import ElevatorShuntTripAuditor
from fireai.core.bps_allocator import NACBoosterAllocator
from fireai.core.seismic_joint_penalyer import SeismicJointPenalyer

# V20 — SLC Capacitance + Stairwell Smoke Control + Network Topology
from fireai.core.slc_capacitance import SLCCapacitanceAuditor
from fireai.core.stairwell_smoke_control import StairwellSmokeControlIntegrator
from fireai.core.network_topology import NetworkTopologyAuditor

# V21 — Pydantic Models (Fail-Fast Validation) + Hazardous Area Classification
from fireai.core.models_v21 import (
    SubstanceProperties as V21SubstanceProperties,
    HACResult as V21HACResult,
    ZoneExtent as V21ZoneExtent,
    ATEXEquipmentSpec as V21ATEXEquipmentSpec,
    FlameDetectorSpec as V21FlameDetectorSpec,
    Obstruction as V21Obstruction,
    RayTracePoint as V21RayTracePoint,
    WavelengthBand,
    TemperatureClass,
    ZoneType,
    VentilationLevel,
    HazardType,
    RegulatoryFramework as V21RegulatoryFramework,
    RegSelectorResult as V21RegSelectorResult,
    _select_temp_class,
    _select_temp_class_with_margin,
    EnvironmentalContext,
    burgess_wheeler_lfl,
    SpectralSignatureRegistry,
    SpectralSignature,
    VolumetricMedium,
    beer_lambert_transmittance,
    volumetric_path_transmittance,
    PasquillStability,
    RegionProfile,
    Jurisdiction,
    ElevationTier,
)
from fireai.core.international_reg_selector import (
    InternationalRegSelector,
    UnknownCountryError,
    resolve as resolve_regulatory,
    convert_division_to_zone,
)
from fireai.core.hac_classification_engine import HACClassificationEngine
from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace
from fireai.core.atex_hazardous_arbiter import ATEXHazardousArbiter
from fireai.core.revit_acl import (
    RevitSubstanceDTO,
    RevitObstructionDTO,
    RevitDetectorDTO,
    ImportReport,
    import_substances_from_revit,
    import_obstructions_from_revit,
    import_detectors_from_revit,
)
from fireai.core.fireai_cli_engine import (
    CLIFireAIEngine,
    PipelineResult,
    Layer1Result,
    Layer2Result,
    Layer3Result,
    Layer5Result,
)
from fireai.core.safety_audit_engine import (
    SafetyAuditEngine,
    AuditResult,
    AuditViolation,
    AuditSeverity,
    elevation_tier_from_detector_z,
)

# V23 — Ultrasonic Gas Leak Detection (UGLD) Acoustic Physics Engine
from fireai.core.ugld_acoustics import (
    UltrasonicSensor as V23UltrasonicSensor,
    AcousticPropagation as V23AcousticPropagation,
    UGLDTriggerResult,
    UGLDFrequencyBand,
    check_ugld_trigger,
    atmospheric_attenuation_db_per_m,
    max_detection_range_m,
    speed_of_sound,
)

# V23 Phase 2 — UGLD Ray Tracing & Maekawa Barrier Diffraction
from fireai.core.ugld_raytrace import (
    AcousticObstacle as V23AcousticObstacle,
    ObstacleHit,
    AcousticRayResult,
    trace_acoustic_ray,
    maekawa_insertion_loss,
    compute_path_difference,
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
    # Safety Assurance
    "SafetyTier",
    "classify_safety_tier",
    "apply_fail_safe",
    "tier_requires_fpe_review",
    "tier_can_submit",
    "OverrideRole",
    "OverrideRecord",
    "EngineeringEvidencePackage",
    "ABSOLUTE_MINIMUM_COVERAGE",
    "MINIMUM_COVERAGE_FOR_SUBMISSION",
    "STANDARD_COVERAGE_THRESHOLD",
    "PROOF_VERIFIED_THRESHOLD",
    # V12 — Class A Routing + Firestopping + Safe Engine + DXF
    "EliteGlobalRouter",
    "FirestoppingAnnotator",
    "SafeBuildingEngine",
    "TrueAECDraftingTable",
    "EliteClassARouter",
    "ArchitecturalWall",
    "RouteSegment",
    # V19 — Elevator Shunt-Trip + NAC Booster + Seismic Joint
    "ElevatorShuntTripAuditor",
    "NACBoosterAllocator",
    "SeismicJointPenalyer",
    # V20 — SLC Capacitance + Stairwell Smoke Control + Network Topology
    "SLCCapacitanceAuditor",
    "StairwellSmokeControlIntegrator",
    "NetworkTopologyAuditor",
    # V21 — Pydantic Models + Hazardous Area Classification
    "V21SubstanceProperties",
    "V21HACResult",
    "V21ZoneExtent",
    "V21ATEXEquipmentSpec",
    "V21FlameDetectorSpec",
    "V21Obstruction",
    "V21RayTracePoint",
    "WavelengthBand",
    "TemperatureClass",
    "ZoneType",
    "VentilationLevel",
    "HazardType",
    "V21RegulatoryFramework",
    "V21RegSelectorResult",
    "_select_temp_class",
    "_select_temp_class_with_margin",
    "EnvironmentalContext",
    "burgess_wheeler_lfl",
    "SpectralSignatureRegistry",
    "SpectralSignature",
    "VolumetricMedium",
    "beer_lambert_transmittance",
    "volumetric_path_transmittance",
    "PasquillStability",
    "RegionProfile",
    "Jurisdiction",
    "ElevationTier",
    "InternationalRegSelector",
    "UnknownCountryError",
    "resolve_regulatory",
    "convert_division_to_zone",
    "HACClassificationEngine",
    "FlameDetectorAOCRayTrace",
    "ATEXHazardousArbiter",
    # V21.2 — Anti-Corruption Layer
    "RevitSubstanceDTO",
    "RevitObstructionDTO",
    "RevitDetectorDTO",
    "ImportReport",
    "import_substances_from_revit",
    "import_obstructions_from_revit",
    "import_detectors_from_revit",
    # V21.2 — CLI Orchestration Engine
    "CLIFireAIEngine",
    "PipelineResult",
    "Layer1Result",
    "Layer2Result",
    "Layer3Result",
    "Layer5Result",
    # V21.2 — Safety Audit Engine
    "SafetyAuditEngine",
    "AuditResult",
    "AuditViolation",
    "AuditSeverity",
    "elevation_tier_from_detector_z",
    # V23 — UGLD Acoustic Physics
    "V23UltrasonicSensor",
    "V23AcousticPropagation",
    "UGLDTriggerResult",
    "UGLDFrequencyBand",
    "check_ugld_trigger",
    "atmospheric_attenuation_db_per_m",
    "max_detection_range_m",
    "speed_of_sound",
    # V23 Phase 2 — UGLD Ray Tracing & Maekawa Barrier
    "V23AcousticObstacle",
    "ObstacleHit",
    "AcousticRayResult",
    "trace_acoustic_ray",
    "maekawa_insertion_loss",
    "compute_path_difference",
]
