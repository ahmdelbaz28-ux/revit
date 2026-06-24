"""fireai – NFPA 72-2022 Automated Fire Detector Placement Engine
"""

from __future__ import annotations

# W-02 FIX: Single source of truth — import from fireai.version
# Package version (semver) for __version__ — distinct from internal FIREAI_VERSION_FULL
# Backward compat: also expose the V-prefixed string and dev version
from fireai.version import FIREAI_VERSION as FIREAI_VERSION
from fireai.version import FIREAI_VERSION_FULL as FIREAI_VERSION_FULL
from fireai.version import __package_version__ as __version__
from fireai.version import build_version_header as build_version_header

# CRITICAL FIX: Replaced wildcard import with lazy __getattr__.
# The old `from fireai.core import *` eagerly imported the entire engine
# at package level, meaning ANY import error in ANY sub-module would
# crash the entire package — including `import fireai; fireai.__version__`.
#
# Now, sub-modules are imported lazily on first access, so:
#   - `import fireai` always succeeds (no eager imports)
#   - `from fireai import FloorAnalyser` works (lazy import via __getattr__)
#   - Import errors only occur when accessing the specific broken module

# Public API names that can be imported from this package
_PUBLIC_NAMES = [
    "FloorAnalyser",
    "BuildingEngine",
    "DensityOptimizer",
    "SensitivityAnalyzer",
    "ParameterOptimizer",
    "ProjectLearner",
    "ScenarioRunner",
    "ScenarioLibrary",
    "ScenarioReporter",
    "PolygonDensityOptimizer",
    "AuditTrail",
    "AuditStore",
    "generate_pdf",
    "EventBus",
    "Event",
    "Events",
    "EventRecorder",
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
    "FireAISystem",
    "EnhancedRoomResult",
    # V17 Critical Life-Safety Triad
    "AcousticSPLCalculator",
    "StrictBatterySizer",
    "TenabilityEvaluator",
    "EnterpriseOrchestrator",
    # V19 High-Rise Engineering Suite
    "ElevatorShuntTripAuditor",
    "NACBoosterAllocator",
    "SeismicJointPenalyer",
    # V20 Digital Signaling & Master Network Architecture
    "SLCCapacitanceAuditor",
    "StairwellSmokeControlIntegrator",
    "NetworkTopologyAuditor",
]


def __getattr__(name):
    """Lazy import: only load sub-modules when actually accessed."""
    if name in _PUBLIC_NAMES:
        # V17 Critical Trilogy — import from v17_core package
        _V17_NAMES = {"AcousticSPLCalculator", "StrictBatterySizer", "TenabilityEvaluator"}
        if name in _V17_NAMES:
            from fireai.v17_core import (
                AcousticSPLCalculator,
                StrictBatterySizer,
                TenabilityEvaluator,
            )

            return {
                "AcousticSPLCalculator": AcousticSPLCalculator,
                "StrictBatterySizer": StrictBatterySizer,
                "TenabilityEvaluator": TenabilityEvaluator,
            }[name]
        if name == "EnterpriseOrchestrator":
            from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator

            return EnterpriseOrchestrator

        from fireai.core import __dict__ as core_dict  # type: ignore[attr-defined]

        if name in core_dict:
            return core_dict[name]
        # Fallback: try direct import from known modules
        try:
            from fireai.core.fireai_core import EnhancedRoomResult, FireAISystem

            if name in ("FireAISystem", "EnhancedRoomResult"):
                return (
                    locals().get(name) or {"FireAISystem": FireAISystem, "EnhancedRoomResult": EnhancedRoomResult}[name]
                )
        except ImportError:
            pass
        raise AttributeError(f"module 'fireai' has no attribute '{name}'")
    raise AttributeError(f"module 'fireai' has no attribute '{name}'")


__all__ = ["__version__"] + _PUBLIC_NAMES
