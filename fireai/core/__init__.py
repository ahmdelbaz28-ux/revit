"""fireai – NFPA 72-2022 Automated Fire Detector Placement Engine."""

__version__ = "1.0.0"

# Core analysers
from fireai.core.acoustics_engine import (
    AcousticCoverageResult,
    AcousticsEngine,
    UGLDCoverageGap,
    UGLDCoverageResult,
    UGLDDetectionZone,
)
from fireai.core.analysis_pipeline import (
    AnalysisPipeline,
    PipelineResult,
    PipelineStage,
)
from fireai.core.atex_hazardous_arbiter import ATEXHazardousArbiter
from fireai.core.audit_blockchain_bridge import (
    AuditEntry,
    HashChainAuditStore,
)
from fireai.core.audit_store import AuditStore

# Audit
from fireai.core.audit_trail import AuditTrail
from fireai.core.bps_allocator import NACBoosterAllocator
from fireai.core.building_engine import BuildingEngine
from fireai.core.cable_routing_engine import (
    MAX_VOLTAGE_DROP_PCT as MAX_VOLTAGE_DROP_PCT,
)
from fireai.core.cable_routing_engine import (
    NOMINAL_VOLTAGE_FA as NOMINAL_VOLTAGE_FA,
)
from fireai.core.cable_routing_engine import (
    CableRoutingEngine,
    RouteResult,
    RoutingObstacle3D,
    VoltageDropSegment,
    WireGauge,
)
from fireai.core.cable_routing_engine import (
    ObstacleType as ObstacleType,
)
from fireai.core.circuit_topology import CircuitTopology
from fireai.core.digital_twin import DigitalTwin
from fireai.core.digital_twin_interface import (
    ChangeRecord,
    DigitalTwinInterface,
    DigitalTwinState,
    TwinModelVersion,
)
from fireai.core.digital_twin_sync import (
    CoverageValidationResult,
    DigitalTwinSync,
    DriftReport,
    SyncReport,
    SyncResult,
)
from fireai.core.dxf_table_schedule import TrueAECDraftingTable
from fireai.core.elevator_shunt_trip import ElevatorShuntTripAuditor

# Event Bus (Digital Twin foundation)
from fireai.core.event_bus import Event, EventBus, EventRecorder, Events
from fireai.core.fireai_cli_engine import (
    CLIFireAIEngine,
    Layer1Result,
    Layer2Result,
    Layer3Result,
    Layer5Result,
)
from fireai.core.firestop_annotator import FirestoppingAnnotator
from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace
from fireai.core.floor_analyser import FloorAnalyser
from fireai.core.hac_classification_engine import HACClassificationEngine
from fireai.core.hybrid_survivability import (
    AcousticCoverageDetail,
    HybridPointResult,
    HybridSurvivabilityEngine,
    HybridSurvivabilityMap,
    SurvivabilityClass,
)
from fireai.core.international_reg_selector import (
    InternationalRegSelector,
    UnknownCountryError,
    convert_division_to_zone,
)
from fireai.core.international_reg_selector import (
    resolve as resolve_regulatory,
)
from fireai.core.kernel_v30_integration import (
    KernelV30Dispatcher,
    MmapResultCache,
    MPSCWorkerPool,
)
from fireai.core.models_v21 import (
    ATEXEquipmentSpec as V21ATEXEquipmentSpec,
)
from fireai.core.models_v21 import (
    ElevationTier,
    EnvironmentalContext,
    HazardType,
    Jurisdiction,
    PasquillStability,
    RegionProfile,
    SpectralSignature,
    SpectralSignatureRegistry,
    TemperatureClass,
    VentilationLevel,
    VolumetricMedium,
    WavelengthBand,
    ZoneType,
    _select_temp_class,
    _select_temp_class_with_margin,
    beer_lambert_transmittance,
    burgess_wheeler_lfl,
    volumetric_path_transmittance,
)
from fireai.core.models_v21 import (
    FlameDetectorSpec as V21FlameDetectorSpec,
)
from fireai.core.models_v21 import (
    HACResult as V21HACResult,
)
from fireai.core.models_v21 import (
    Obstruction as V21Obstruction,
)
from fireai.core.models_v21 import (
    RayTracePoint as V21RayTracePoint,
)
from fireai.core.models_v21 import (
    RegSelectorResult as V21RegSelectorResult,
)
from fireai.core.models_v21 import (
    RegulatoryFramework as V21RegulatoryFramework,
)
from fireai.core.models_v21 import (
    SubstanceProperties as V21SubstanceProperties,
)
from fireai.core.models_v21 import (
    ZoneExtent as V21ZoneExtent,
)
from fireai.core.monte_carlo_pipeline import (
    DetectorFailureModel,
    DetectorReliabilitySimulator,
    MCPipelineAdapter,
)
from fireai.core.multi_floor_orchestrator import (
    BuildingAnalysis,
    ElevatorRecallResult,
    FloorAssignment,
    MultiFloorOrchestrator,
    RiserRoutingResult,
    SLCLoop,
    SmokeSpreadResult,
    VerticalZone,
)
from fireai.core.network_topology import NetworkTopologyAuditor
from fireai.core.parameter_optimizer import ParameterOptimizer

# Reporting
from fireai.core.pdf_report import generate_pdf

# Polygon support
from fireai.core.polygon_optimizer import PolygonDensityOptimizer
from fireai.core.project_learner import ProjectLearner
from fireai.core.revit_acl import (
    ImportReport,
    RevitDetectorDTO,
    RevitObstructionDTO,
    RevitSubstanceDTO,
    import_detectors_from_revit,
    import_obstructions_from_revit,
    import_substances_from_revit,
)

# Engineering System (v2 — from calculator to engineering system)
from fireai.core.room_lifecycle import (
    RoomLifecycle,
    RoomLifecycleManager,
    RoomState,
    RoomTransition,
)
from fireai.core.routing_engine_v10 import (
    ArchitecturalWall,
    EliteClassARouter,
    RouteSegment,
)
from fireai.core.routing_global_class_a import EliteGlobalRouter
from fireai.core.safe_building_engine import SafeBuildingEngine

# Safety Assurance (from consultant's architecture — adopted 2026-05-19)
from fireai.core.safety_assurance import (
    ABSOLUTE_MINIMUM_COVERAGE,
    MINIMUM_COVERAGE_FOR_SUBMISSION,
    PROOF_VERIFIED_THRESHOLD,
    STANDARD_COVERAGE_THRESHOLD,
    EngineeringEvidencePackage,
    OverrideRecord,
    OverrideRole,
    SafetyTier,
    apply_fail_safe,
    classify_safety_tier,
    tier_can_submit,
    tier_requires_fpe_review,
)
from fireai.core.safety_audit_engine import (
    AuditResult,
    AuditSeverity,
    AuditViolation,
    SafetyAuditEngine,
    elevation_tier_from_detector_z,
)

# Scenario engine
from fireai.core.scenario_engine import (
    ScenarioLibrary,
    ScenarioReporter,
    ScenarioRunner,
)
from fireai.core.seismic_joint_penalyer import SeismicJointPenalyer

# Optimisation & analysis tools
from fireai.core.sensitivity_analyzer import SensitivityAnalyzer
from fireai.core.slc_capacitance import SLCCapacitanceAuditor
from fireai.core.spatial_engine.consensus_engine import (
    ConfidenceLevel,
    ConsensusEngine,
    ConsensusResult,
)

# NOTE: DensityOptimizer is imported lazily to avoid runtime type-hint
# incompatibilities on older Python versions (e.g., Python 3.8).
try:
    from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
except Exception:  # pragma: no cover
    DensityOptimizer = None  # type: ignore

# Fail-safe guard: DensityOptimizer must not be None
if DensityOptimizer is None:
    raise ImportError(
        "DensityOptimizer failed to import and resolved to None. "
        "This module is REQUIRED for NFPA 72 detector placement optimization. "
        "Ensure fireai.core.spatial_engine.density_optimizer is installed correctly."
    )
from fireai.core.spatial_engine.proof_certificate import (
    ProofCertificate,
    ProofCertificateGenerator,
)
from fireai.core.stairwell_smoke_control import StairwellSmokeControlIntegrator
from fireai.core.ugld_acoustics import (
    AcousticPropagation as V23AcousticPropagation,
)
from fireai.core.ugld_acoustics import (
    UGLDFrequencyBand,
    UGLDTriggerResult,
    atmospheric_attenuation_db_per_m,
    check_ugld_trigger,
    max_detection_range_m,
    speed_of_sound,
)
from fireai.core.ugld_acoustics import (
    UltrasonicSensor as V23UltrasonicSensor,
)
from fireai.core.ugld_raytrace import (
    AcousticObstacle as V23AcousticObstacle,
)
from fireai.core.ugld_raytrace import (
    AcousticRayResult,
    ObstacleHit,
    compute_path_difference,
    maekawa_insertion_loss,
    trace_acoustic_ray,
)

__all__ = [
    "ABSOLUTE_MINIMUM_COVERAGE",
    "MINIMUM_COVERAGE_FOR_SUBMISSION",
    "PROOF_VERIFIED_THRESHOLD",
    "STANDARD_COVERAGE_THRESHOLD",
    "ATEXHazardousArbiter",
    "AcousticCoverageDetail",
    "AcousticCoverageResult",
    "AcousticRayResult",
    "AcousticsEngine",
    "AnalysisPipeline",
    "ArchitecturalWall",
    "AuditEntry",
    "AuditResult",
    "AuditSeverity",
    "AuditStore",
    # Audit
    "AuditTrail",
    "AuditViolation",
    "BuildingAnalysis",
    "BuildingEngine",
    "CLIFireAIEngine",
    "CableRoutingEngine",
    "ChangeRecord",
    "CircuitTopology",
    "ConfidenceLevel",
    "ConsensusEngine",
    "ConsensusResult",
    "CoverageValidationResult",
    "DensityOptimizer",
    "DetectorFailureModel",
    "DetectorReliabilitySimulator",
    "DigitalTwin",
    "DigitalTwinInterface",
    "DigitalTwinState",
    "DigitalTwinSync",
    "DriftReport",
    "ElevationTier",
    "ElevatorRecallResult",
    "ElevatorShuntTripAuditor",
    "EliteClassARouter",
    "EliteGlobalRouter",
    "EngineeringEvidencePackage",
    "EnvironmentalContext",
    "Event",
    # Event Bus
    "EventBus",
    "EventRecorder",
    "Events",
    "FirestoppingAnnotator",
    "FlameDetectorAOCRayTrace",
    # Analysers
    "FloorAnalyser",
    "FloorAssignment",
    "HACClassificationEngine",
    "HashChainAuditStore",
    "HazardType",
    "HybridPointResult",
    "HybridSurvivabilityEngine",
    "HybridSurvivabilityMap",
    "ImportReport",
    "InternationalRegSelector",
    "Jurisdiction",
    "KernelV30Dispatcher",
    "Layer1Result",
    "Layer2Result",
    "Layer3Result",
    "Layer5Result",
    "MCPipelineAdapter",
    "MPSCWorkerPool",
    "MmapResultCache",
    "MultiFloorOrchestrator",
    "NACBoosterAllocator",
    "NetworkTopologyAuditor",
    "ObstacleHit",
    "OverrideRecord",
    "OverrideRole",
    "ParameterOptimizer",
    "PasquillStability",
    "PipelineResult",
    "PipelineResult",
    "PipelineStage",
    # Polygon
    "PolygonDensityOptimizer",
    "ProjectLearner",
    "ProofCertificate",
    "ProofCertificateGenerator",
    "RegionProfile",
    "RevitDetectorDTO",
    "RevitObstructionDTO",
    "RevitSubstanceDTO",
    "RiserRoutingResult",
    "RoomLifecycle",
    "RoomLifecycleManager",
    # Engineering System v2
    "RoomState",
    "RoomTransition",
    "RouteResult",
    "RouteSegment",
    "RoutingObstacle3D",
    "SLCCapacitanceAuditor",
    "SLCLoop",
    "SafeBuildingEngine",
    "SafetyAuditEngine",
    # Safety Assurance
    "SafetyTier",
    "ScenarioLibrary",
    "ScenarioReporter",
    # Scenarios
    "ScenarioRunner",
    "SeismicJointPenalyer",
    # Tools
    "SensitivityAnalyzer",
    "SmokeSpreadResult",
    "SpectralSignature",
    "SpectralSignatureRegistry",
    "StairwellSmokeControlIntegrator",
    "SurvivabilityClass",
    "SyncReport",
    "SyncResult",
    "TemperatureClass",
    "TrueAECDraftingTable",
    "TwinModelVersion",
    "UGLDCoverageGap",
    "UGLDCoverageResult",
    "UGLDDetectionZone",
    "UGLDFrequencyBand",
    "UGLDTriggerResult",
    "UnknownCountryError",
    "V21ATEXEquipmentSpec",
    "V21FlameDetectorSpec",
    "V21HACResult",
    "V21Obstruction",
    "V21RayTracePoint",
    "V21RegSelectorResult",
    "V21RegulatoryFramework",
    "V21SubstanceProperties",
    "V21ZoneExtent",
    "V23AcousticObstacle",
    "V23AcousticPropagation",
    "V23UltrasonicSensor",
    "VentilationLevel",
    "VerticalZone",
    "VoltageDropSegment",
    "VolumetricMedium",
    "WavelengthBand",
    "WireGauge",
    "ZoneType",
    "__version__",
    "_select_temp_class",
    "_select_temp_class_with_margin",
    "apply_fail_safe",
    "atmospheric_attenuation_db_per_m",
    "beer_lambert_transmittance",
    "burgess_wheeler_lfl",
    "check_ugld_trigger",
    "classify_safety_tier",
    "compute_path_difference",
    "convert_division_to_zone",
    "elevation_tier_from_detector_z",
    # Reporting
    "generate_pdf",
    "import_detectors_from_revit",
    "import_obstructions_from_revit",
    "import_substances_from_revit",
    "maekawa_insertion_loss",
    "max_detection_range_m",
    "resolve_regulatory",
    "speed_of_sound",
    "tier_can_submit",
    "tier_requires_fpe_review",
    "trace_acoustic_ray",
    "volumetric_path_transmittance",
]
