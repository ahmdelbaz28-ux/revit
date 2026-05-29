"""
fireai.core — NFPA 72-2022 Automated Fire Detector Placement Engine Core
=========================================================================

RESILIENT IMPORT DESIGN:
  This module uses try/except import blocks because the fireai package
  has ~155 source modules but only a subset are present on disk in this
  deployment. Missing modules must NOT prevent the package from loading
  — especially the Rules Engine and pipeline which ARE present.

  The rules_engine/ subpackage is ALWAYS available and safety-critical.
  All other imports are best-effort: they succeed when the module exists
  and silently skip when it doesn't.
"""

__version__ = "56.0.0"

import logging

_logger = logging.getLogger(__name__)

# ─── Always-available imports (rules_engine is on disk) ──────────────────────
from fireai.core.rules_engine.engine import (
    RulesEngine,
    Rule,
    Fact,
    RulePriority,
    RuleResult,
    RuleAuditEntry,
)
from fireai.core.rules_engine.truth_maintenance import (
    TruthMaintenanceSystem,
    DependencyRecord,
)
from fireai.core.rules_engine.nfpa72_rules import NFPA72RuleSet
from fireai.core.rules_engine.compliance_bridge import (
    NFPA72ComplianceChecker,
    ComplianceReport,
)
from fireai.core.rules_engine.api_contract import (
    ContractValidator,
    ContractSeverity,
)

# ─── Pipeline-core imports (always available since V95.1) ──────────────────
from fireai.core.contracts_validation import (
    ContractViolation,
    validate_room_input,
)
from fireai.core.nfpa72_engine import (
    SpacingResult,
    BatteryResult,
    VoltageDropResult,
    calculate_battery,
    calculate_voltage_drop,
    get_detector_spacing,
    estimate_detector_count,
    verify_fault_isolator_placement,
)
from fireai.core.safety_assurance import (
    SafetyTier,
    classify_safety_tier,
    apply_fail_safe,
    tier_requires_fpe_review,
    tier_can_submit,
    OverrideRole,
    OverrideRecord,
    EngineeringEvidencePackage,
    ABSOLUTE_MINIMUM_COVERAGE,
    MINIMUM_COVERAGE_FOR_SUBMISSION,
    STANDARD_COVERAGE_THRESHOLD,
    PROOF_VERIFIED_THRESHOLD,
)
from fireai.core.release_gates import (
    verify_and_evaluate,
    describe_blockers,
)

# ─── Best-effort imports — these modules may not be on disk ──────────────────

# Core analysers
try:
    from fireai.core.floor_analyser import FloorAnalyser
except ImportError:
    _logger.debug("fireai.core.floor_analyser not available")

try:
    from fireai.core.building_engine import BuildingEngine
except ImportError:
    _logger.debug("fireai.core.building_engine not available")

try:
    from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
except ImportError:
    _logger.debug("fireai.core.spatial_engine.density_optimizer not available")

# Optimisation & analysis tools
try:
    from fireai.core.sensitivity_analyzer import SensitivityAnalyzer
except ImportError:
    _logger.debug("fireai.core.sensitivity_analyzer not available")

try:
    from fireai.core.parameter_optimizer import ParameterOptimizer
except ImportError:
    _logger.debug("fireai.core.parameter_optimizer not available")

try:
    from fireai.core.project_learner import ProjectLearner
except ImportError:
    _logger.debug("fireai.core.project_learner not available")

# Scenario engine
try:
    from fireai.core.scenario_engine import (
        ScenarioRunner,
        ScenarioLibrary,
        ScenarioReporter,
    )
except ImportError:
    _logger.debug("fireai.core.scenario_engine not available")

# Polygon support
try:
    from fireai.core.polygon_optimizer import PolygonDensityOptimizer
except ImportError:
    _logger.debug("fireai.core.polygon_optimizer not available")

# Audit
try:
    from fireai.core.audit_trail import AuditTrail
except ImportError:
    _logger.debug("fireai.core.audit_trail not available")

try:
    from fireai.core.audit_store import AuditStore
except ImportError:
    _logger.debug("fireai.core.audit_store not available")

# Reporting
try:
    from fireai.core.pdf_report import generate_pdf
except ImportError:
    _logger.debug("fireai.core.pdf_report not available")

# Event Bus (Digital Twin foundation)
try:
    from fireai.core.event_bus import EventBus, Event, Events, EventRecorder
except ImportError:
    _logger.debug("fireai.core.event_bus not available")

# Engineering System (v2)
try:
    from fireai.core.room_lifecycle import (
        RoomState, RoomTransition, RoomLifecycle, RoomLifecycleManager,
    )
except ImportError:
    _logger.debug("fireai.core.room_lifecycle not available")

try:
    from fireai.core.digital_twin_interface import (
        DigitalTwinInterface, DigitalTwinState, TwinModelVersion, ChangeRecord,
    )
except ImportError:
    _logger.debug("fireai.core.digital_twin_interface not available")

try:
    from fireai.core.digital_twin import DigitalTwin
except ImportError:
    _logger.debug("fireai.core.digital_twin not available")

try:
    from fireai.core.analysis_pipeline import (
        AnalysisPipeline, PipelineStage, PipelineResult,
    )
except ImportError:
    _logger.debug("fireai.core.analysis_pipeline not available")

try:
    from fireai.core.spatial_engine.consensus_engine import (
        ConsensusEngine, ConsensusResult, ConfidenceLevel,
    )
except ImportError:
    _logger.debug("fireai.core.spatial_engine.consensus_engine not available")

try:
    from fireai.core.spatial_engine.proof_certificate import (
        ProofCertificateGenerator, ProofCertificate,
    )
except ImportError:
    _logger.debug("fireai.core.spatial_engine.proof_certificate not available")

# Safety Assurance — now always available (imported above as always-available)
# (Previously a try/except block; module is now on disk)

# V12 — Class A Routing + Firestopping + Safe Building Engine + DXF Schedule
try:
    from fireai.core.routing_global_class_a import EliteGlobalRouter
except ImportError:
    _logger.debug("fireai.core.routing_global_class_a not available")

try:
    from fireai.core.firestop_annotator import FirestoppingAnnotator
except ImportError:
    _logger.debug("fireai.core.firestop_annotator not available")

try:
    from fireai.core.safe_building_engine import SafeBuildingEngine
except ImportError:
    _logger.debug("fireai.core.safe_building_engine not available")

try:
    from fireai.core.dxf_table_schedule import TrueAECDraftingTable
except ImportError:
    _logger.debug("fireai.core.dxf_table_schedule not available")

try:
    from fireai.core.routing_engine_v10 import EliteClassARouter, ArchitecturalWall, RouteSegment
except ImportError:
    _logger.debug("fireai.core.routing_engine_v10 not available")

# V19 — Elevator Shunt-Trip + NAC Booster Allocator + Seismic Joint Penalty
try:
    from fireai.core.elevator_shunt_trip import ElevatorShuntTripAuditor
except ImportError:
    _logger.debug("fireai.core.elevator_shunt_trip not available")

try:
    from fireai.core.bps_allocator import NACBoosterAllocator
except ImportError:
    _logger.debug("fireai.core.bps_allocator not available")

try:
    from fireai.core.seismic_joint_penalyer import SeismicJointPenalyer
except ImportError:
    _logger.debug("fireai.core.seismic_joint_penalyer not available")

# V20 — SLC Capacitance + Stairwell Smoke Control + Network Topology
try:
    from fireai.core.slc_capacitance import SLCCapacitanceAuditor
except ImportError:
    _logger.debug("fireai.core.slc_capacitance not available")

try:
    from fireai.core.stairwell_smoke_control import StairwellSmokeControlIntegrator
except ImportError:
    _logger.debug("fireai.core.stairwell_smoke_control not available")

try:
    from fireai.core.network_topology import NetworkTopologyAuditor
except ImportError:
    _logger.debug("fireai.core.network_topology not available")

# V21 — Pydantic Models + Hazardous Area Classification
try:
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
except ImportError:
    _logger.debug("fireai.core.models_v21 not available")

try:
    from fireai.core.international_reg_selector import (
        InternationalRegSelector,
        UnknownCountryError,
        resolve as resolve_regulatory,
        convert_division_to_zone,
    )
except ImportError:
    _logger.debug("fireai.core.international_reg_selector not available")

try:
    from fireai.core.hac_classification_engine import HACClassificationEngine
except ImportError:
    _logger.debug("fireai.core.hac_classification_engine not available")

try:
    from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace
except ImportError:
    _logger.debug("fireai.core.flame_detector_aoc_raytrace not available")

try:
    from fireai.core.atex_hazardous_arbiter import ATEXHazardousArbiter
except ImportError:
    _logger.debug("fireai.core.atex_hazardous_arbiter not available")

try:
    from fireai.core.revit_acl import (
        RevitSubstanceDTO,
        RevitObstructionDTO,
        RevitDetectorDTO,
        ImportReport,
        import_substances_from_revit,
        import_obstructions_from_revit,
        import_detectors_from_revit,
    )
except ImportError:
    _logger.debug("fireai.core.revit_acl not available")

try:
    from fireai.core.fireai_cli_engine import (
        CLIFireAIEngine,
        PipelineResult,
        Layer1Result,
        Layer2Result,
        Layer3Result,
        Layer5Result,
    )
except ImportError:
    _logger.debug("fireai.core.fireai_cli_engine not available")

try:
    from fireai.core.safety_audit_engine import (
        SafetyAuditEngine,
        AuditResult,
        AuditViolation,
        AuditSeverity,
        elevation_tier_from_detector_z,
    )
except ImportError:
    _logger.debug("fireai.core.safety_audit_engine not available")

# V23 — Ultrasonic Gas Leak Detection (UGLD)
try:
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
except ImportError:
    _logger.debug("fireai.core.ugld_acoustics not available")

try:
    from fireai.core.ugld_raytrace import (
        AcousticObstacle as V23AcousticObstacle,
        ObstacleHit,
        AcousticRayResult,
        trace_acoustic_ray,
        maekawa_insertion_loss,
        compute_path_difference,
    )
except ImportError:
    _logger.debug("fireai.core.ugld_raytrace not available")

# V24 — Hybrid Survivability Index Engine
try:
    from fireai.core.hybrid_survivability import (
        HybridSurvivabilityEngine,
        HybridSurvivabilityMap,
        HybridPointResult,
        AcousticCoverageDetail,
        SurvivabilityClass,
    )
except ImportError:
    _logger.debug("fireai.core.hybrid_survivability not available")

# V25 — Pipeline Integration Modules
try:
    from fireai.core.cable_routing_engine import (
        CableRoutingEngine,
        RouteResult,
        CircuitTopology,
        WireGauge,
        RoutingObstacle3D,
        VoltageDropSegment,
    )
except ImportError:
    _logger.debug("fireai.core.cable_routing_engine not available")

try:
    from fireai.core.digital_twin_sync import (
        DigitalTwinSync,
        SyncResult,
        DriftReport,
        CoverageValidationResult,
        SyncReport,
    )
except ImportError:
    _logger.debug("fireai.core.digital_twin_sync not available")

try:
    from fireai.core.acoustics_engine import (
        AcousticsEngine,
        AcousticCoverageResult,
        UGLDCoverageResult,
        UGLDDetectionZone,
        UGLDCoverageGap,
    )
except ImportError:
    _logger.debug("fireai.core.acoustics_engine not available")

try:
    from fireai.core.multi_floor_orchestrator import (
        MultiFloorOrchestrator,
        BuildingAnalysis,
        SLCLoop,
        VerticalZone,
        FloorAssignment,
        ElevatorRecallResult,
        SmokeSpreadResult,
        RiserRoutingResult,
    )
except ImportError:
    _logger.debug("fireai.core.multi_floor_orchestrator not available")

try:
    from fireai.core.kernel_v30_integration import (
        KernelV30Dispatcher,
        MPSCWorkerPool,
        MmapResultCache,
    )
except ImportError:
    _logger.debug("fireai.core.kernel_v30_integration not available")

try:
    from fireai.core.audit_blockchain_bridge import (
        HashChainAuditStore,
        AuditEntry,
    )
except ImportError:
    _logger.debug("fireai.core.audit_blockchain_bridge not available")

try:
    from fireai.core.monte_carlo_pipeline import (
        MCPipelineAdapter,
        DetectorReliabilitySimulator,
        DetectorFailureModel,
    )
except ImportError:
    _logger.debug("fireai.core.monte_carlo_pipeline not available")


# ─── Public API — only names that were successfully imported ─────────────────
__all__ = [
    "__version__",
    # V95 — NFPA 72 Declarative Rules Engine (always available)
    "RulesEngine",
    "Rule",
    "Fact",
    "RulePriority",
    "RuleResult",
    "RuleAuditEntry",
    "TruthMaintenanceSystem",
    "DependencyRecord",
    "NFPA72RuleSet",
    "NFPA72ComplianceChecker",
    "ComplianceReport",
    "ContractValidator",
    "ContractSeverity",
    # V95.1 — Pipeline-core modules (always available)
    "ContractViolation",
    "validate_room_input",
    "SpacingResult",
    "BatteryResult",
    "VoltageDropResult",
    "calculate_battery",
    "calculate_voltage_drop",
    "get_detector_spacing",
    "estimate_detector_count",
    "verify_fault_isolator_placement",
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
    "verify_and_evaluate",
    "describe_blockers",
]

# Dynamically add successfully imported names to __all__
import sys as _sys
_current_module = _sys.modules[__name__]
_optional_names = [
    "FloorAnalyser", "BuildingEngine", "DensityOptimizer",
    "SensitivityAnalyzer", "ParameterOptimizer", "ProjectLearner",
    "ScenarioRunner", "ScenarioLibrary", "ScenarioReporter",
    "PolygonDensityOptimizer",
    "AuditTrail", "AuditStore",
    "generate_pdf",
    "EventBus", "Event", "Events", "EventRecorder",
    "RoomState", "RoomTransition", "RoomLifecycle", "RoomLifecycleManager",
    "DigitalTwinInterface", "DigitalTwinState", "TwinModelVersion", "ChangeRecord",
    "DigitalTwin",
    "AnalysisPipeline", "PipelineStage", "PipelineResult",
    "ConsensusEngine", "ConsensusResult", "ConfidenceLevel",
    "ProofCertificateGenerator", "ProofCertificate",
    "SafetyTier", "classify_safety_tier", "apply_fail_safe",
    "tier_requires_fpe_review", "tier_can_submit",
    "OverrideRole", "OverrideRecord", "EngineeringEvidencePackage",
    "ABSOLUTE_MINIMUM_COVERAGE", "MINIMUM_COVERAGE_FOR_SUBMISSION",
    "STANDARD_COVERAGE_THRESHOLD", "PROOF_VERIFIED_THRESHOLD",
    "EliteGlobalRouter", "FirestoppingAnnotator", "SafeBuildingEngine",
    "TrueAECDraftingTable", "EliteClassARouter", "ArchitecturalWall", "RouteSegment",
    "ElevatorShuntTripAuditor", "NACBoosterAllocator", "SeismicJointPenalyer",
    "SLCCapacitanceAuditor", "StairwellSmokeControlIntegrator", "NetworkTopologyAuditor",
    "V21SubstanceProperties", "V21HACResult", "V21ZoneExtent",
    "V21ATEXEquipmentSpec", "V21FlameDetectorSpec", "V21Obstruction", "V21RayTracePoint",
    "WavelengthBand", "TemperatureClass", "ZoneType", "VentilationLevel", "HazardType",
    "V21RegulatoryFramework", "V21RegSelectorResult",
    "_select_temp_class", "_select_temp_class_with_margin",
    "EnvironmentalContext", "burgess_wheeler_lfl",
    "SpectralSignatureRegistry", "SpectralSignature",
    "VolumetricMedium", "beer_lambert_transmittance", "volumetric_path_transmittance",
    "PasquillStability", "RegionProfile", "Jurisdiction", "ElevationTier",
    "InternationalRegSelector", "UnknownCountryError",
    "resolve_regulatory", "convert_division_to_zone",
    "HACClassificationEngine", "FlameDetectorAOCRayTrace", "ATEXHazardousArbiter",
    "RevitSubstanceDTO", "RevitObstructionDTO", "RevitDetectorDTO", "ImportReport",
    "import_substances_from_revit", "import_obstructions_from_revit", "import_detectors_from_revit",
    "CLIFireAIEngine", "PipelineResult", "Layer1Result", "Layer2Result", "Layer3Result", "Layer5Result",
    "SafetyAuditEngine", "AuditResult", "AuditViolation", "AuditSeverity",
    "elevation_tier_from_detector_z",
    "V23UltrasonicSensor", "V23AcousticPropagation",
    "UGLDTriggerResult", "UGLDFrequencyBand",
    "check_ugld_trigger", "atmospheric_attenuation_db_per_m",
    "max_detection_range_m", "speed_of_sound",
    "V23AcousticObstacle", "ObstacleHit", "AcousticRayResult",
    "trace_acoustic_ray", "maekawa_insertion_loss", "compute_path_difference",
    "HybridSurvivabilityEngine", "HybridSurvivabilityMap", "HybridPointResult",
    "AcousticCoverageDetail", "SurvivabilityClass",
    "CableRoutingEngine", "RouteResult", "CircuitTopology", "WireGauge",
    "RoutingObstacle3D", "VoltageDropSegment",
    "DigitalTwinSync", "SyncResult", "DriftReport",
    "CoverageValidationResult", "SyncReport",
    "AcousticsEngine", "AcousticCoverageResult",
    "UGLDCoverageResult", "UGLDDetectionZone", "UGLDCoverageGap",
    "MultiFloorOrchestrator", "BuildingAnalysis", "SLCLoop",
    "VerticalZone", "FloorAssignment", "ElevatorRecallResult",
    "SmokeSpreadResult", "RiserRoutingResult",
    "KernelV30Dispatcher", "MPSCWorkerPool", "MmapResultCache",
    "HashChainAuditStore", "AuditEntry",
    "MCPipelineAdapter", "DetectorReliabilitySimulator", "DetectorFailureModel",
]

for _name in _optional_names:
    if hasattr(_current_module, _name) and _name not in __all__:
        __all__.append(_name)
