from __future__ import annotations

"""
AnalysisPipeline — Complete Fire Safety Analysis Pipeline (NFPA 72-2022)
=========================================================================
Composes ALL stages of fire safety analysis into a single, robust workflow.

PROBLEM:
  Previously, the fire safety system required manual, sequential calls:
    1. DensityOptimizer.optimize() → get layout
    2. ConsensusEngine.verify() → get consensus (NOT called automatically)
    3. ProofCertificateGenerator.generate() → get certificate (NOT called automatically)
    4. FloorOrchestrator.process() → get floor result (doesn't use consensus or certificates)

  This was fragile and error-prone — operators could forget verification
  or certification, and the FloorOrchestrator never used consensus results.

SOLUTION:
  AnalysisPipeline composes ALL stages automatically:
    Optimize → Verify (3 engines) → Certify → Sign → Store → Emit Events

  Every stage is guaranteed to run (or fail gracefully), results are
  propagated forward, and EventBus events are published at each stage.

PIPELINE STAGES:
  OPTIMIZATION  — DensityOptimizer placement (5 strategies: hexG_x, hexG_y,
                  hexA_x, hexA_y, rect). Best valid result selected.
  VERIFICATION  — Triple Consensus verification (analytical, voronoi, grid).
                  3/3 = VERIFIED, 2/3 = WARNING, <2 = FAIL.
  CERTIFICATION — δ-conservative proof certificate generation.
                  Mathematical proof of coverage with lower bound.
  SIGNING       — SHA-256 hash sealing + UTC timestamp.
                  Tamper-evident, independently verifiable.
  STORAGE       — Audit trail persistence via tamper-evident hash chain.
                  Legal-grade evidence for AHJ review.
  COMPLETE      — All stages done. PipelineResult is final.

ERROR RESILIENCE:
  - Individual room failures don't crash the building analysis
  - Partial results are always preserved
  - Only truly critical errors (MemoryError, SystemError) propagate up
  - Each room gets its own PipelineResult with detailed timing and error info

EVENT PUBLISHING:
  - room.analysis.start        — Pipeline begins for a room
  - detector.placed            — Optimization complete, detectors placed
  - consensus.result           — Triple verification result
  - coverage.verified/failed   — Coverage pass/fail
  - proof.certificate.generated — Certificate generated
  - nfpa.compliant/violation   — NFPA 72 compliance verdict
  - room.analysis.complete     — Pipeline complete for a room

NFPA 72-2022 §17.7.4.2.3.1: Coverage radius R = 0.7 × S
"""

import enum
import hashlib
import json
import logging
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .digital_twin import DigitalTwin
from .event_bus import EventBus, Events
from .spatial_engine.consensus_engine import (
    ConfidenceLevel,
    ConsensusEngine,
    ConsensusResult,
)
from .spatial_engine.density_optimizer import (
    DETECTOR_RADIUS,
    MAX_SPACING_M,
    VERIFY_STEP,
    WALL_MIN_M,
    DensityOptimizer,
    DetectorLayout,
    Room,
)
from .spatial_engine.proof_certificate import (
    ProofCertificate,
    ProofCertificateGenerator,
)

logger = logging.getLogger("fireai.pipeline")


# ═══════════════════════════════════════════════════════════════════════════════
# PipelineStage Enum
# ═══════════════════════════════════════════════════════════════════════════════


class PipelineStage(enum.Enum):
    """Stages of the fire safety analysis pipeline.

    Each stage represents a discrete step in the analysis workflow.
    The pipeline progresses sequentially through these stages.
    If a stage fails, the pipeline stops and stage_reached reflects
    the last SUCCESSFULLY completed stage.
    """

    OPTIMIZATION = "optimization"  # DensityOptimizer placement
    VERIFICATION = "verification"  # Triple consensus verification
    CERTIFICATION = "certification"  # Proof certificate generation
    SIGNING = "signing"  # SHA-256 hash sealing
    STORAGE = "storage"  # Audit trail persistence
    TWIN_SYNC = "twin_sync"  # Digital twin snapshot (Bridge 2)
    COMPLETE = "complete"  # All stages done


# ═══════════════════════════════════════════════════════════════════════════════
# PipelineResult Dataclass
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class PipelineResult:
    """Result of the complete analysis pipeline for a single room.

    Contains all artifacts from every stage, plus timing, errors,
    and warnings. This is the authoritative output of the pipeline.

    Attributes:
        room_id: Unique identifier for the analyzed room.
        stage_reached: The last successfully completed pipeline stage.
        success: True if ALL stages completed without errors.
        layout: Detector layout from the optimization stage.
        consensus: Consensus result from the triple verification stage.
        certificate: Proof certificate from the certification stage.
        errors: List of error messages encountered during pipeline.
        warnings: List of warning messages (non-fatal issues).
        timing: Dictionary mapping stage name → elapsed seconds.
        metadata: Additional metadata about the pipeline execution.

    """

    room_id: str
    stage_reached: PipelineStage
    success: bool
    layout: Optional[DetectorLayout] = None
    consensus: Optional[ConsensusResult] = None
    certificate: Optional[ProofCertificate] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timing: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Digital Twin fields (Bridge 2)
    twin_version_id: Optional[str] = None
    twin_checksum: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dictionary (for JSON export / audit trail).

        Handles non-serializable types gracefully:
          - PipelineStage → string value
          - DetectorLayout → dataclass asdict
          - ConsensusResult → dataclass asdict (with nested enums → values)
          - ProofCertificate → dataclass asdict
        """
        result: Dict[str, Any] = {
            "room_id": self.room_id,
            "stage_reached": self.stage_reached.value,
            "success": self.success,
            "errors": self.errors,
            "warnings": self.warnings,
            "timing": self.timing,
            "metadata": self.metadata,
            "twin_version_id": self.twin_version_id,
            "twin_checksum": self.twin_checksum,
        }

        if self.layout is not None:
            try:
                layout_dict = asdict(self.layout)
                result["layout"] = layout_dict
            except Exception as exc:
                logger.warning("Failed to serialize layout: %s: %s", type(exc).__name__, exc)
                result["layout"] = {
                    "count": self.layout.count,
                    "coverage_pct": self.layout.coverage_pct,
                    "nfpa_valid": self.layout.nfpa_valid,
                    "method": self.layout.method,
                }

        if self.consensus is not None:
            try:
                consensus_dict = asdict(self.consensus)
                # Convert enum values for JSON serialization
                consensus_dict["confidence"] = self.consensus.confidence.value
                consensus_dict["engines"] = [{**asdict(v), "engine": v.engine.value} for v in self.consensus.engines]
                result["consensus"] = consensus_dict
            except Exception as exc:
                logger.warning("Failed to serialize consensus: %s: %s", type(exc).__name__, exc)
                result["consensus"] = {
                    "confidence": self.consensus.confidence.value,
                    "is_safe": self.consensus.is_safe,
                    "n_pass": self.consensus.n_pass,
                    "n_total": self.consensus.n_total,
                }

        if self.certificate is not None:
            try:
                result["certificate"] = asdict(self.certificate)
            except Exception as exc:
                logger.warning("Failed to serialize certificate: %s: %s", type(exc).__name__, exc)
                result["certificate"] = {
                    "room_id": self.certificate.room_id,
                    "coverage_guaranteed": self.certificate.coverage_guaranteed,
                    "proof_hash": self.certificate.proof_hash,
                    "timestamp": self.certificate.timestamp,
                }

        return result

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════════════════════
# AnalysisPipeline Class
# ═══════════════════════════════════════════════════════════════════════════════


class AnalysisPipeline:
    """Complete analysis pipeline: Optimize → Verify → Certify → Sign → Store.

    This is the MAIN ENTRY POINT for fire safety analysis. It replaces
    the ad-hoc manual calling of individual components with a single,
    composable, event-driven pipeline.

    Usage:
        pipeline = AnalysisPipeline(coverage_radius=6.37)
        result = pipeline.analyze_room(
            room=Room(name="Office-101", width=10.0, length=12.0),
            room_id="office-101",
            ceiling_height=3.0,
        )
        if result.success:
            print(f"Coverage: {result.layout.coverage_pct}%")
            print(f"Consensus: {result.consensus.consensus_str}")
            print(f"Certificate hash: {result.certificate.proof_hash}")
        else:
            print(f"Pipeline failed at {result.stage_reached.value}")
            for err in result.errors:
                print(f"  ERROR: {err}")

    Error Handling:
        - Stage failure → PipelineResult.success = False, stage_reached = last successful stage
        - Warning in consensus → continue but flag
        - Certificate generation failure → pipeline continues, certificate = None
    """

    def __init__(
        self,
        coverage_radius: float = DETECTOR_RADIUS,
        max_spacing: float = MAX_SPACING_M,
        wall_min: float = WALL_MIN_M,
        grid_step: float = VERIFY_STEP,
        generate_certificate: bool = True,
        require_consensus: bool = True,
    ):
        """Initialize the analysis pipeline.

        Args:
            coverage_radius: Detector coverage radius R in meters.
                Default: 6.37m (NFPA 72-2022 §17.7.4.2.3.1: R = 0.7 × S).
            max_spacing: Maximum detector spacing S in meters.
                Default: 9.1m (NFPA 72-2022 Table 17.6.3.1.1, 30ft).
            wall_min: Minimum wall distance for detectors in meters.
                Default: 0.10m (NFPA 72 §17.6.3.1.1).
            grid_step: Grid resolution for verification in meters.
                Default: 0.20m (δ-conservative proof).
            generate_certificate: Whether to generate proof certificates.
                Default: True. Set to False for fast analysis-only mode.
            require_consensus: Whether to run triple consensus verification.
                Default: True. Set to False to skip verification stage.

        """
        self.coverage_radius = coverage_radius
        self.max_spacing = max_spacing
        self.wall_min = wall_min
        self.grid_step = grid_step
        self.generate_certificate = generate_certificate
        self.require_consensus = require_consensus

        # Initialize sub-components
        self._optimizer = DensityOptimizer(
            max_spacing=max_spacing,
            wall_min=wall_min,
            radius=coverage_radius,
        )
        self._consensus = ConsensusEngine(
            coverage_radius=coverage_radius,
            wall_min=wall_min,
        )
        self._cert_gen = ProofCertificateGenerator(
            grid_step=grid_step,
            coverage_radius=coverage_radius,
            max_spacing=max_spacing,
            wall_min=wall_min,
        )

        # EventBus for publishing pipeline events (FIX-3: use singleton)
        self._bus = EventBus.instance()

        # Digital Twin (Bridge 2) — shares the same EventBus singleton
        self._twin = DigitalTwin(building_id="pipeline-managed")
        self._enable_twin_sync = True  # Can be disabled for fast mode

        # Try to import AuditStore for STORAGE stage
        self._audit_available = False
        try:
            from .audit_store import AuditStore

            self._audit_store = AuditStore()  # Store INSTANCE (FIX-11)
            self._audit_available = True
        except ImportError:
            logger.warning(
                "AuditStore not available — STORAGE stage will be skipped. "
                "Install sqlite3 support for full audit trail."
            )
            self._audit_store = None

    # ── Properties ──────────────────────────────────────────────────

    @property
    def twin(self) -> DigitalTwin:
        """Access the pipeline's DigitalTwin instance.

        After running analyze_room() or analyze_building(), the twin
        contains all planned detectors with their positions, ready
        for operational tracking.
        """
        return self._twin

    # ── Single Room Analysis ────────────────────────────────────────────────

    def analyze_room(
        self,
        room: Room,
        room_id: str = "",
        ceiling_height: float = 3.0,
    ) -> PipelineResult:
        """Run complete analysis pipeline for a single room.

        Stages:
          1. OPTIMIZATION: Run DensityOptimizer with 5 strategies
          2. VERIFICATION: Run Triple Consensus (3 independent engines)
          3. CERTIFICATION: Generate δ-conservative proof certificate
          4. SIGNING: Seal certificate with SHA-256 hash + timestamp
          5. STORAGE: Persist to audit trail (if configured)
          6. Emit EventBus events at each stage

        Args:
            room: Room object with width, length, ceiling_height.
            room_id: Unique identifier for this room. If empty,
                uses room.name.
            ceiling_height: Ceiling height in meters. Overrides
                room.ceiling_height if provided.

        Returns:
            PipelineResult with all artifacts from every completed stage.

        """
        # Resolve room_id
        if not room_id:
            room_id = room.name

        # Generate correlation ID for linking all events for this analysis
        correlation_id = str(uuid.uuid4())

        # Initialize result
        result = PipelineResult(
            room_id=room_id,
            stage_reached=PipelineStage.OPTIMIZATION,
            success=False,
            metadata={
                "correlation_id": correlation_id,
                "room_name": room.name,
                "room_width": room.width,
                "room_length": room.length,
                "ceiling_height": ceiling_height,
                "coverage_radius": self.coverage_radius,
                "max_spacing": self.max_spacing,
                "pipeline_version": "1.0.0",
            },
        )

        logger.info("Pipeline START: room=%s (%sm × %sm, h=%sm)", room_id, room.width, room.length, ceiling_height)

        # ── Event: Pipeline Start ──────────────────────────────────────
        self._bus.publish(
            Events.ROOM_ANALYSIS_START,
            data={
                "room_id": room_id,
                "room_name": room.name,
                "width": room.width,
                "length": room.length,
                "ceiling_height": ceiling_height,
                "coverage_radius": self.coverage_radius,
            },
            source="AnalysisPipeline",
            correlation_id=correlation_id,
        )

        # ═══════════════════════════════════════════════════════════════
        # ROOM GEOMETRY VALIDATION (NaN/Inf guard)
        # ═══════════════════════════════════════════════════════════════
        # V59 FIX: NaN/Inf in room dimensions silently propagates through the
        # optimizer, producing invalid layouts that appear valid (proof_valid=True).
        # Life-Safety Rule 5: reject non-finite geometry immediately.
        _geom_valid = True
        for _name, _val in [("room.width", room.width), ("room.length", room.length), ("ceiling_height", ceiling_height)]:
            if not isinstance(_val, (int, float)) or not math.isfinite(float(_val)) or float(_val) <= 0:
                result.errors.append(
                    f"GEOMETRY INVALID: {_name}={_val!r} (must be finite positive number). "
                    "Cannot run optimization with invalid room geometry."
                )
                logger.error("  GEOMETRY INVALID for %s: %s=%s", room_id, _name, _val)
                _geom_valid = False
                break
        if not _geom_valid:
            result.stage_reached = PipelineStage.OPTIMIZATION  # Mark where we stopped
            return result

        # ═══════════════════════════════════════════════════════════════
        # STAGE 1: OPTIMIZATION
        # ═══════════════════════════════════════════════════════════════
        t0 = time.monotonic()
        try:
            layout = self._optimizer.optimize(room, coverage_radius=self.coverage_radius)
            result.layout = layout
            result.stage_reached = PipelineStage.OPTIMIZATION
            result.timing["optimization"] = round(time.monotonic() - t0, 4)

            logger.info(
                f"  OPTIMIZATION: {layout.count} detectors, "
                f"coverage={layout.coverage_pct:.1f}%, "
                f"nfpa_valid={layout.nfpa_valid}, method={layout.method}"
            )

            # Collect layout warnings
            if layout.warnings:
                result.warnings.extend(layout.warnings)
            if layout.fallback_used:
                result.warnings.append(f"Room {room_id}: Fallback placement used — result may not be optimal")
            if layout.violations:
                result.warnings.extend(layout.violations)

            # ── Event: Optimization Complete ───────────────────────────
            self._bus.publish(
                Events.DETECTOR_PLACED,
                data={
                    "room_id": room_id,
                    "detector_count": layout.count,
                    "coverage_pct": layout.coverage_pct,
                    "method": layout.method,
                    "nfpa_valid": layout.nfpa_valid,
                    "positions": layout.detectors,
                },
                source="AnalysisPipeline",
                correlation_id=correlation_id,
            )

        except Exception as exc:
            elapsed = round(time.monotonic() - t0, 4)
            result.timing["optimization"] = elapsed
            result.errors.append(f"OPTIMIZATION FAILED: {type(exc).__name__}: {exc}")
            logger.error("  OPTIMIZATION FAILED for %s: %s", room_id, exc)
            # Cannot continue without a layout
            return result

        # ═══════════════════════════════════════════════════════════════
        # STAGE 2: VERIFICATION (Triple Consensus)
        # ═══════════════════════════════════════════════════════════════
        if self.require_consensus:
            t0 = time.monotonic()
            try:
                consensus = self._consensus.verify(
                    width=room.width,
                    length=room.length,
                    detectors=layout.detectors,
                    grid_proof_valid=layout.proof_valid,
                    grid_coverage_pct=layout.coverage_pct,
                )
                result.consensus = consensus
                result.stage_reached = PipelineStage.VERIFICATION
                result.timing["verification"] = round(time.monotonic() - t0, 4)

                logger.info("  VERIFICATION: %s, is_safe=%s", consensus.consensus_str, consensus.is_safe)

                # Warnings for consensus discrepancies
                if consensus.confidence == ConfidenceLevel.WARNING:
                    result.warnings.append(
                        f"Room {room_id}: Consensus WARNING — "
                        f"{consensus.n_pass}/{consensus.n_total} engines agree. "
                        f"Discrepancies: {'; '.join(consensus.discrepancies)}"
                    )
                elif consensus.confidence == ConfidenceLevel.FAIL:
                    result.warnings.append(
                        f"Room {room_id}: Consensus FAIL — "
                        f"{consensus.n_pass}/{consensus.n_total} engines agree. "
                        f"DO NOT deploy. {consensus.recommendation}"
                    )

                # ── Event: Verification Result ─────────────────────────
                self._bus.publish(
                    Events.CONSENSUS_RESULT,
                    data={
                        "room_id": room_id,
                        "confidence": consensus.confidence.value,
                        "is_safe": consensus.is_safe,
                        "n_pass": consensus.n_pass,
                        "n_total": consensus.n_total,
                        "discrepancies": consensus.discrepancies,
                    },
                    source="AnalysisPipeline",
                    correlation_id=correlation_id,
                )

                # ── Event: Coverage Verified / Failed ──────────────────
                if consensus.is_safe:
                    self._bus.publish(
                        Events.COVERAGE_VERIFIED,
                        data={
                            "room_id": room_id,
                            "coverage_pct": layout.coverage_pct,
                            "confidence": consensus.confidence.value,
                            "n_engines": consensus.n_total,
                        },
                        source="AnalysisPipeline",
                        correlation_id=correlation_id,
                    )
                else:
                    self._bus.publish(
                        Events.COVERAGE_FAILED,
                        data={
                            "room_id": room_id,
                            "coverage_pct": layout.coverage_pct,
                            "confidence": consensus.confidence.value,
                            "recommendation": consensus.recommendation,
                        },
                        source="AnalysisPipeline",
                        correlation_id=correlation_id,
                    )

                # ── Event: NFPA Compliance ─────────────────────────────
                if layout.nfpa_valid and consensus.is_safe:
                    self._bus.publish(
                        Events.NFPA_COMPLIANT,
                        data={
                            "room_id": room_id,
                            "coverage_pct": layout.coverage_pct,
                            "reference": "NFPA 72-2022 Table 17.6.3.1.1",
                            "consensus": consensus.consensus_str,
                        },
                        source="AnalysisPipeline",
                        correlation_id=correlation_id,
                    )
                else:
                    self._bus.publish(
                        Events.NFPA_VIOLATION,
                        data={
                            "room_id": room_id,
                            "coverage_pct": layout.coverage_pct,
                            "nfpa_valid": layout.nfpa_valid,
                            "consensus_safe": consensus.is_safe,
                            "violations": layout.violations,
                            "reference": "NFPA 72-2022 Table 17.6.3.1.1",
                        },
                        source="AnalysisPipeline",
                        correlation_id=correlation_id,
                    )

            except Exception as exc:
                elapsed = round(time.monotonic() - t0, 4)
                result.timing["verification"] = elapsed
                error_msg = f"VERIFICATION FAILED: {type(exc).__name__}: {exc}"
                result.errors.append(error_msg)
                result.warnings.append(f"Room {room_id}: Verification stage failed — proceeding without consensus")
                logger.warning("  VERIFICATION FAILED for %s: %s", room_id, exc)
                # Continue pipeline — verification failure is not fatal
        else:
            # Verification skipped — still emit coverage event from layout
            result.timing["verification"] = 0.0
            result.warnings.append(
                f"Room {room_id}: VERIFICATION SKIPPED (require_consensus=False). "
                "No triple consensus check performed. Coverage relies solely on "
                "optimizer proof_valid flag without independent verification. "
                "This is ACCEPTABLE only during pre-screening or when NFPA 72 "
                "compliance is verified by other means. Set require_consensus=True "
                "for production deployments."
            )
            logger.warning("  VERIFICATION: Skipped (require_consensus=False) — no independent verification performed")

            if layout.proof_valid:
                self._bus.publish(
                    Events.COVERAGE_VERIFIED,
                    data={
                        "room_id": room_id,
                        "coverage_pct": layout.coverage_pct,
                        "confidence": "skipped",
                        "n_engines": 0,
                    },
                    source="AnalysisPipeline",
                    correlation_id=correlation_id,
                )
            else:
                self._bus.publish(
                    Events.COVERAGE_FAILED,
                    data={
                        "room_id": room_id,
                        "coverage_pct": layout.coverage_pct,
                        "confidence": "skipped",
                    },
                    source="AnalysisPipeline",
                    correlation_id=correlation_id,
                )

            # NFPA compliance from layout only (no consensus)
            if layout.nfpa_valid:
                self._bus.publish(
                    Events.NFPA_COMPLIANT,
                    data={
                        "room_id": room_id,
                        "coverage_pct": layout.coverage_pct,
                        "reference": "NFPA 72-2022 Table 17.6.3.1.1",
                        "consensus": "skipped",
                    },
                    source="AnalysisPipeline",
                    correlation_id=correlation_id,
                )
            else:
                self._bus.publish(
                    Events.NFPA_VIOLATION,
                    data={
                        "room_id": room_id,
                        "coverage_pct": layout.coverage_pct,
                        "nfpa_valid": layout.nfpa_valid,
                        "violations": layout.violations,
                        "reference": "NFPA 72-2022 Table 17.6.3.1.1",
                    },
                    source="AnalysisPipeline",
                    correlation_id=correlation_id,
                )

        # ═══════════════════════════════════════════════════════════════
        # STAGE 3: CERTIFICATION (Proof Certificate Generation)
        # ═══════════════════════════════════════════════════════════════
        if self.generate_certificate:
            t0 = time.monotonic()
            try:
                # Determine NFPA compliance flags for certificate
                nfpa_compliant = layout.nfpa_valid
                wall_coverage_complete = layout.wall_violations == 0
                spacing_compliant = layout.nfpa_valid and not any("spacing" in v.lower() for v in layout.violations)

                # If consensus ran, use its verdict
                if result.consensus is not None:
                    nfpa_compliant = nfpa_compliant and result.consensus.is_safe

                cert = self._cert_gen.generate(
                    room_id=room_id,
                    width=room.width,
                    length=room.length,
                    ceiling_height=ceiling_height,
                    detectors=layout.detectors,
                    detector_type="smoke",
                    nfpa_compliant=nfpa_compliant,
                    wall_coverage_complete=wall_coverage_complete,
                    spacing_compliant=spacing_compliant,
                )
                result.certificate = cert
                result.stage_reached = PipelineStage.CERTIFICATION
                result.timing["certification"] = round(time.monotonic() - t0, 4)

                logger.info(
                    f"  CERTIFICATION: guaranteed={cert.coverage_guaranteed}, "
                    f"lower_bound={cert.coverage_lower_bound_pct:.1f}%, "
                    f"grid_points={cert.n_grid_points}, "
                    f"uncovered={cert.n_uncovered}"
                )

                # Collect certificate warnings
                if cert.warnings:
                    result.warnings.extend(cert.warnings)

                # ── Event: Certificate Generated ───────────────────────
                self._bus.publish(
                    Events.PROOF_CERTIFICATE_GENERATED,
                    data={
                        "room_id": room_id,
                        "coverage_guaranteed": cert.coverage_guaranteed,
                        "coverage_lower_bound_pct": cert.coverage_lower_bound_pct,
                        "n_grid_points": cert.n_grid_points,
                        "n_uncovered": cert.n_uncovered,
                        "nfpa_compliant": cert.nfpa_compliant,
                    },
                    source="AnalysisPipeline",
                    correlation_id=correlation_id,
                )

            except Exception as exc:
                elapsed = round(time.monotonic() - t0, 4)
                result.timing["certification"] = elapsed
                error_msg = f"CERTIFICATION FAILED: {type(exc).__name__}: {exc}"
                result.errors.append(error_msg)
                result.warnings.append(
                    f"Room {room_id}: Certificate generation failed — proceeding without proof certificate"
                )
                logger.warning("  CERTIFICATION FAILED for %s: %s", room_id, exc)
                # Continue pipeline — certificate failure is not fatal
        else:
            result.timing["certification"] = 0.0
            logger.info("  CERTIFICATION: Skipped (generate_certificate=False)")

        # ═══════════════════════════════════════════════════════════════
        # STAGE 4: SIGNING (SHA-256 Hash Sealing)
        # ═══════════════════════════════════════════════════════════════
        t0 = time.monotonic()
        try:
            if result.certificate is not None:
                result.certificate.seal()
                logger.info(
                    f"  SIGNING: hash={result.certificate.proof_hash[:16]}..., timestamp={result.certificate.timestamp}"
                )
            else:
                # No certificate to sign — create a pipeline-level hash
                # from the layout and consensus results
                hash_payload = {
                    "room_id": room_id,
                    "detector_count": layout.count,
                    "coverage_pct": layout.coverage_pct,
                    "nfpa_valid": layout.nfpa_valid,
                    "method": layout.method,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                if result.consensus is not None:
                    hash_payload["consensus_confidence"] = result.consensus.confidence.value
                    hash_payload["consensus_safe"] = result.consensus.is_safe
                pipeline_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True).encode()).hexdigest()
                result.metadata["pipeline_hash"] = pipeline_hash
                result.metadata["pipeline_timestamp"] = datetime.now(timezone.utc).isoformat()
                # V60 FIX (P1-5): Log full hash (not truncated) for verification
                logger.info("  SIGNING: pipeline_hash=%s (no certificate — hash from layout)", pipeline_hash)

            result.stage_reached = PipelineStage.SIGNING
            result.timing["signing"] = round(time.monotonic() - t0, 4)

        except Exception as exc:
            elapsed = round(time.monotonic() - t0, 4)
            result.timing["signing"] = elapsed
            error_msg = f"SIGNING FAILED: {type(exc).__name__}: {exc}"
            result.errors.append(error_msg)
            result.warnings.append(f"Room {room_id}: Signing failed — certificate may not be tamper-evident")
            logger.warning("  SIGNING FAILED for %s: %s", room_id, exc)
            # Continue — signing failure is not fatal

        # ═══════════════════════════════════════════════════════════════
        # STAGE 5: STORAGE (Audit Trail Persistence)
        # ═══════════════════════════════════════════════════════════════
        t0 = time.monotonic()
        try:
            if self._audit_available and self._audit_store is not None:
                audit_details = {
                    "room_id": room_id,
                    "room_name": room.name,
                    "width": room.width,
                    "length": room.length,
                    "ceiling_height": ceiling_height,
                    "detector_count": layout.count,
                    "coverage_pct": layout.coverage_pct,
                    "nfpa_valid": layout.nfpa_valid,
                    "method": layout.method,
                    "pipeline_stages": {
                        "optimization": result.timing.get("optimization"),
                        "verification": result.timing.get("verification"),
                        "certification": result.timing.get("certification"),
                        "signing": result.timing.get("signing"),
                    },
                }

                if result.consensus is not None:
                    audit_details["consensus"] = {
                        "confidence": result.consensus.confidence.value,
                        "is_safe": result.consensus.is_safe,
                        "n_pass": result.consensus.n_pass,
                        "n_total": result.consensus.n_total,
                    }

                if result.certificate is not None:
                    audit_details["certificate"] = {
                        "coverage_guaranteed": result.certificate.coverage_guaranteed,
                        "coverage_lower_bound_pct": result.certificate.coverage_lower_bound_pct,
                        "proof_hash": result.certificate.proof_hash,
                        "timestamp": result.certificate.timestamp,
                    }

                audit_hash = self._audit_store.add_event(
                    event_type="ROOM_ANALYSIS_COMPLETE",
                    room_id=room_id,
                    details_dict=audit_details,
                )
                result.metadata["audit_hash"] = audit_hash
                result.stage_reached = PipelineStage.STORAGE
                result.timing["storage"] = round(time.monotonic() - t0, 4)

                logger.info("  STORAGE: audit_hash=%s...", audit_hash[:16])

            else:
                # No audit store available — skip storage
                result.timing["storage"] = 0.0
                result.stage_reached = PipelineStage.STORAGE
                logger.info("  STORAGE: Skipped (AuditStore not available)")

        except Exception as exc:
            elapsed = round(time.monotonic() - t0, 4)
            result.timing["storage"] = elapsed
            error_msg = f"STORAGE FAILED: {type(exc).__name__}: {exc}"
            result.errors.append(error_msg)
            result.warnings.append(f"Room {room_id}: Audit storage failed — result not persisted to audit trail")
            logger.warning("  STORAGE FAILED for %s: %s", room_id, exc)
            # Continue — storage failure is not fatal for the result

        # ═══════════════════════════════════════════════════════════════
        # STAGE 6: TWIN_SYNC (Digital Twin Snapshot — Bridge 2)
        # ═══════════════════════════════════════════════════════════════
        #
        # CRITICAL DESIGN DECISION:
        #   TWIN_SYNC is NON-BLOCKING. If it fails, the pipeline still
        #   succeeds — the twin is a value-add, not a safety gate.
        #   The safety gate is the CERTIFICATE stage.
        #
        #   However, twin failure is ALWAYS logged as a WARNING because
        #   a missing twin means the building has no live digital copy.
        #
        if self._enable_twin_sync:
            t0 = time.monotonic()
            try:
                # Build room data in the format DigitalTwin expects
                room_data = {
                    "room_id": room_id,
                    "name": room.name,
                    "width_m": room.width,
                    "depth_m": room.length,
                    "ceiling_height_m": ceiling_height,
                    "detector_type": layout.detector_type_simple or "smoke",
                    "detectors": [
                        {"x": x, "y": y, "z": ceiling_height, "radius": layout.coverage_radius or self.coverage_radius}
                        for x, y in layout.detectors
                    ],
                    "coverage_pct": layout.coverage_pct,
                    "nfpa_valid": layout.nfpa_valid,
                    "method": layout.method,
                    "proof_certificates": ([result.certificate.proof_hash] if result.certificate else []),
                }

                # Load into twin — creates PLANNED detectors
                self._twin.from_building_report([room_data])

                # Compute snapshot checksum
                checksum = self._twin.compute_checksum()

                # Store twin metadata in result
                result.twin_checksum = checksum
                result.metadata["twin_checksum"] = checksum
                result.metadata["twin_detector_count"] = len(layout.detectors)
                result.stage_reached = PipelineStage.TWIN_SYNC
                result.timing["twin_sync"] = round(time.monotonic() - t0, 4)

                # ── Event: Twin Sync ────────────────────────────────
                self._bus.publish(
                    Events.TWIN_SYNC,
                    data={
                        "room_id": room_id,
                        "detector_count": len(layout.detectors),
                        "checksum": checksum,
                        "certificate_hash": (result.certificate.proof_hash if result.certificate else None),
                    },
                    source="AnalysisPipeline",
                    correlation_id=correlation_id,
                )

                logger.info("  TWIN_SYNC: %s detectors snapshot, checksum=%s...", len(layout.detectors), checksum[:16])

            except Exception as exc:
                elapsed = round(time.monotonic() - t0, 4)
                result.timing["twin_sync"] = elapsed
                result.warnings.append(f"Room {room_id}: Twin sync failed — no live digital copy for this room: {exc}")
                logger.warning("  TWIN_SYNC FAILED for %s: %s", room_id, exc)
                # Continue — twin failure is NOT a safety failure
        else:
            result.timing["twin_sync"] = 0.0
            logger.info("  TWIN_SYNC: Skipped (enable_twin_sync=False)")

        # ═══════════════════════════════════════════════════════════════
        # FINALIZE
        # ═══════════════════════════════════════════════════════════════
        result.stage_reached = PipelineStage.COMPLETE
        result.success = (
            len(result.errors) == 0
            and layout.proof_valid
            and (not self.require_consensus or (result.consensus is not None and result.consensus.is_safe))
        )

        # Compute total pipeline time
        total_time = sum(result.timing.values())
        result.timing["total"] = round(total_time, 4)

        # ── Event: Pipeline Complete ───────────────────────────────────
        self._bus.publish(
            Events.ROOM_ANALYSIS_COMPLETE,
            data={
                "room_id": room_id,
                "success": result.success,
                "stage_reached": result.stage_reached.value,
                "detector_count": layout.count,
                "coverage_pct": layout.coverage_pct,
                "nfpa_valid": layout.nfpa_valid,
                "consensus_safe": (result.consensus.is_safe if result.consensus else None),
                "certificate_hash": (result.certificate.proof_hash if result.certificate else None),
                "total_time_s": result.timing.get("total", 0.0),
                "errors": result.errors,
                "warnings_count": len(result.warnings),
            },
            source="AnalysisPipeline",
            correlation_id=correlation_id,
        )

        logger.info(
            f"Pipeline END: room={room_id}, success={result.success}, "
            f"total_time={result.timing.get('total', 0.0):.3f}s, "
            f"errors={len(result.errors)}, warnings={len(result.warnings)}"
        )

        return result

    # ── Building-Level Analysis ─────────────────────────────────────────────

    def analyze_building(
        self,
        rooms: List[Tuple[Room, str, float]],
    ) -> List[PipelineResult]:
        """Run pipeline for all rooms in a building.

        Error Resilience:
            - If one room fails, OTHER rooms continue (unlike old FloorOrchestrator)
            - Partial results are preserved
            - Only CRITICAL errors (memory, corruption) stop the entire building

        Args:
            rooms: List of (Room, room_id, ceiling_height) tuples.
                - Room: The room geometry object.
                - room_id: Unique identifier for the room.
                - ceiling_height: Ceiling height in meters.

        Returns:
            List of PipelineResult objects, one per room.
            Failed rooms have success=False with detailed error info.

        """
        results: List[PipelineResult] = []
        n_rooms = len(rooms)

        logger.info("Building analysis START: %s rooms", n_rooms)

        # ── Event: Building Analysis Start ────────────────────────────
        self._bus.publish(
            Events.BUILDING_ANALYSIS_START,
            data={
                "n_rooms": n_rooms,
            },
            source="AnalysisPipeline",
        )

        for _i, (room, room_id, ceiling_height) in enumerate(rooms):
            try:
                result = self.analyze_room(
                    room=room,
                    room_id=room_id,
                    ceiling_height=ceiling_height,
                )
                results.append(result)

            except MemoryError:
                # CRITICAL: Memory errors propagate — cannot safely continue
                logger.critical("CRITICAL: MemoryError in room %s. Aborting building analysis.", room_id)
                # Still record the failure
                results.append(
                    PipelineResult(
                        room_id=room_id,
                        stage_reached=PipelineStage.OPTIMIZATION,
                        success=False,
                        errors=["CRITICAL: MemoryError — building analysis aborted"],
                        metadata={"room_name": room.name, "aborted": True},
                    )
                )
                raise

            except SystemError as exc:
                # CRITICAL: System errors propagate — corrupted state
                logger.critical("CRITICAL: SystemError in room %s: %s. Aborting building analysis.", room_id, exc)
                results.append(
                    PipelineResult(
                        room_id=room_id,
                        stage_reached=PipelineStage.OPTIMIZATION,
                        success=False,
                        errors=[f"CRITICAL: SystemError — {exc}"],
                        metadata={"room_name": room.name, "aborted": True},
                    )
                )
                raise

            except Exception as exc:
                # Non-critical: Record failure and continue with other rooms
                logger.error(
                    f"Room {room_id} failed with {type(exc).__name__}: {exc}. Continuing with remaining rooms."
                )
                results.append(
                    PipelineResult(
                        room_id=room_id,
                        stage_reached=PipelineStage.OPTIMIZATION,
                        success=False,
                        errors=[f"Unexpected error: {type(exc).__name__}: {exc}"],
                        metadata={"room_name": room.name},
                    )
                )

        # Compute building-level summary
        n_success = sum(1 for r in results if r.success)
        n_failed = sum(1 for r in results if not r.success)
        n_total_detectors = sum(r.layout.count for r in results if r.layout is not None)
        total_time = sum(r.timing.get("total", 0.0) for r in results)

        logger.info(
            f"Building analysis END: {n_success}/{n_rooms} rooms passed, "
            f"{n_failed} failed, {n_total_detectors} total detectors, "
            f"total_time={total_time:.3f}s"
        )

        # ── Event: Building Analysis Complete ─────────────────────────
        self._bus.publish(
            Events.BUILDING_ANALYSIS_COMPLETE,
            data={
                "n_rooms": n_rooms,
                "n_success": n_success,
                "n_failed": n_failed,
                "n_total_detectors": n_total_detectors,
                "total_time_s": round(total_time, 4),
            },
            source="AnalysisPipeline",
        )

        return results


# ═══════════════════════════════════════════════════════════════════════════════
# Module Exports
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "AnalysisPipeline",
    "PipelineResult",
    "PipelineStage",
]
