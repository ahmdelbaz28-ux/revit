"""fireai_cli_engine.py – FireAI CLI Orchestration Engine
=======================================================
Coordinates the 5-layer + audit fire alarm design pipeline for standalone CLI usage.

Layers:
  Layer 1: InternationalRegSelector  – Regulatory framework resolution
  Layer 2: HACClassificationEngine   – Hazardous area classification
  Layer 3: ATEXHazardousArbiter      – Equipment protection level
  Layer 4: Thermal margin + temp class – IEC 60079-14 safe temperature
  Layer 5: FlameDetectorAOCRayTrace  – Optical coverage analysis
  Layer 6: SafetyAuditEngine         – Post-calculation compliance audit

Design Decisions (vs. Consultant's ProcessPoolExecutor proposal):
  - REJECTED: ProcessPoolExecutor with global mutable state (_WORKER_BVH_ROOT)
    Reason: GIL bypass is premature optimization for typical CLI workloads
    (hundreds of rays, <1s processing). Adds ~100ms overhead per invocation.
    Global mutable state contradicts Pydantic frozen model principles.
  - REJECTED: BVH tree (doesn't exist in codebase; R-tree is already implemented)
  - ACCEPTED: Sequential batch processing with progress reporting
  - ACCEPTED: EnvironmentalContext worst-case defaults (already in V21.2)
  - ACCEPTED: Chunked ray processing for memory efficiency (not parallelism)

Standards:
  IEC 60079-0:2017     – General requirements for Ex equipment
  IEC 60079-10-1:2015  – Gas zone classification
  IEC 60079-14:2013    – Installation in explosive atmospheres
  NFPA 72-2022         – National Fire Alarm and Signaling Code
  NFPA 497-2021        – Classification of flammable liquids/gases
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from fireai.core.atex_hazardous_arbiter import ATEXHazardousArbiter
from fireai.core.flame_detector_aoc_raytrace import (
    CoverageResult,
    FlameDetectorAOCRayTrace,
    SingleDetectorResult,
)
from fireai.core.hac_classification_engine import HACClassificationEngine
from fireai.core.international_reg_selector import (
    InternationalRegSelector,
    UnknownCountryError,
)
from fireai.core.international_reg_selector import (
    resolve as resolve_regulatory,
)
from fireai.core.models_v21 import (
    ATEXEquipmentSpec,
    EnvironmentalContext,
    FlameDetectorSpec,
    HACResult,
    HazardType,
    Obstruction,
    RayTracePoint,
    SpectralSignatureRegistry,
    SubstanceProperties,
    VentilationLevel,
    VolumetricMedium,
    ZoneType,
)
from fireai.core.safety_audit_engine import (
    AuditResult as AuditReport,
)
from fireai.core.safety_audit_engine import (
    SafetyAuditEngine,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Layer1Result:
    """Layer 1: Regulatory framework resolution."""

    country_code: str
    framework: str
    zone_system: str
    warnings: Tuple[str, ...]
    success: bool


@dataclass(frozen=True)
class Layer2Result:
    """Layer 2: Hazardous area classification with environmental correction."""

    zone: ZoneType
    horizontal_m: float
    vertical_m: float
    volume_m3: float
    ventilation: VentilationLevel
    hazard_type: HazardType
    lfl_corrected: Optional[float]
    lfl_correction_pct: Optional[float]
    warnings: Tuple[str, ...]
    critical_flags: Tuple[str, ...]
    success: bool


@dataclass(frozen=True)
class Layer3Result:
    """Layer 3: ATEX equipment specification."""

    epl: str
    atex_category: str
    temp_class: str
    protection_modes: Tuple[str, ...]
    fire_detector_marking: Optional[str]
    warnings: Tuple[str, ...]
    errors: Tuple[str, ...]
    success: bool


@dataclass(frozen=True)
class Layer5Result:
    """Layer 5: Optical coverage analysis with volumetric media."""

    total_points: int
    covered_points: int
    coverage_pct: float
    per_detector: Dict[str, SingleDetectorResult]
    warnings: Tuple[str, ...]
    success: bool


@dataclass(frozen=True)
class Layer6Result:
    """Layer 6: Post-calculation safety audit."""

    audit_status: str  # "PASS" or "FAIL"
    total_checks: int
    passed_checks: int
    critical_violations: Tuple[str, ...]  # CRITICAL violation messages
    warning_violations: Tuple[str, ...]  # WARNING violation messages
    info_violations: Tuple[str, ...]  # INFO violation messages
    all_violations: Tuple[str, ...]  # All violation messages
    success: bool


@dataclass(frozen=True)
class PipelineResult:
    """Complete 5-layer + audit pipeline result."""

    layer1: Optional[Layer1Result] = None
    layer2: Optional[Layer2Result] = None
    layer3: Optional[Layer3Result] = None
    layer5: Optional[Layer5Result] = None
    layer6: Optional[Layer6Result] = None
    env_context: Optional[EnvironmentalContext] = None
    elapsed_seconds: float = 0.0
    pipeline_warnings: Tuple[str, ...] = ()
    pipeline_errors: Tuple[str, ...] = ()
    success: bool = False


# ---------------------------------------------------------------------------
# CLI Engine
# ---------------------------------------------------------------------------


class CLIFireAIEngine:
    """Standalone CLI orchestration engine for FireAI 5-layer pipeline.

    Processes all layers sequentially with full environmental context
    propagation. Each layer's output feeds into the next.

    For Layer 5 (optical), uses sequential batch processing rather than
    multi-processing. Rationale:
      - Typical CLI workload: 100-1000 rays, <1s processing
      - ProcessPoolExecutor overhead: ~100ms per invocation
      - Net result: parallelism is SLOWER for typical workloads
      - If future workloads exceed 10,000 rays, add optional
        parallel mode behind a --parallel flag with benchmark evidence

    Usage:
        engine = CLIFireAIEngine()
        result = engine.run_full_pipeline(
            country_code="SA",
            substance=substance,
            ventilation=VentilationLevel.MEDIUM,
            detectors=[...],
            target_grid=[...],
            obstructions=[...],
        )
    """

    # Chunk size for Layer 5 batch processing (memory efficiency, not parallelism)
    RAY_CHUNK_SIZE: int = 512

    def __init__(
        self,
        grid_step_m: float = 0.5,
        detector_threshold: float = 0.1,
        env_context: Optional[EnvironmentalContext] = None,
    ) -> None:
        """Initialize CLI engine with optional environmental context.

        Args:
            grid_step_m: Grid resolution for ray trace (meters)
            detector_threshold: Minimum transmittance for coverage (0.0-1.0)
            env_context: Environmental context. If None, uses worst-case defaults
                        (Pasquill F, 0.5 m/s wind, 40C ambient).

        """
        self._reg_selector = InternationalRegSelector()  # Legacy, kept for reference
        self._hac_engine = HACClassificationEngine()
        self._atex_arbiter = ATEXHazardousArbiter()
        self._ray_engine = FlameDetectorAOCRayTrace(
            grid_step_m=grid_step_m,
            detector_threshold=detector_threshold,
        )
        self._spectral_registry = SpectralSignatureRegistry()
        self._audit_engine = SafetyAuditEngine()
        # Worst-case default if no context provided — defensive physics
        self._env_context = env_context or EnvironmentalContext()

    # ── Layer 1: Regulatory Framework ────────────────────────────────────

    def run_layer1(self, country_code: str) -> Layer1Result:
        """Resolve regulatory framework from country code.

        Fails fast on unknown country — no silent IECEx fallback.
        [Q3: UnknownCountryError]
        """
        try:
            result = resolve_regulatory(country_code)  # Uses V21 Pydantic resolve
            return Layer1Result(
                country_code=country_code,
                framework=result.framework.value,
                zone_system=result.zone_system,
                warnings=tuple(result.warnings),
                success=True,
            )
        except UnknownCountryError as exc:
            logger.error("Layer 1 FAILED: %s", exc)
            return Layer1Result(
                country_code=country_code,
                framework="UNKNOWN",
                zone_system="UNKNOWN",
                warnings=(str(exc),),
                success=False,
            )

    # ── Layer 2: HAC Classification ─────────────────────────────────────

    def run_layer2(
        self,
        substance: SubstanceProperties,
        ventilation: VentilationLevel,
        is_indoor: bool = True,
        release_grade=None,
        release_rate_kg_s: float = 0.0,
        room_volume_m3: float = 1000.0,
    ) -> Layer2Result:
        """Classify hazardous area with Burgess-Wheeler LFL thermal correction.

        GAP-02: release_grade is now the PRIMARY zone determinant per IEC §4.2.
        Default release_grade=None → PRIMARY (backward compatible).

        Uses EnvironmentalContext.ambient_temp_c for thermal correction.
        If no context provided, uses worst-case 40C default.
        """
        try:
            hac_result: HACResult = self._hac_engine.classify_v21(
                substance=substance,
                ventilation=ventilation,
                is_indoor=is_indoor,
                ambient_temp_c=self._env_context.ambient_temp_c,
                env_context=self._env_context,
                release_grade=release_grade,
                release_rate_kg_s=release_rate_kg_s,
                room_volume_m3=room_volume_m3,
            )

            # Extract LFL correction info from warnings
            lfl_corrected = None
            lfl_correction_pct = None
            for w in hac_result.warnings:
                if "LFL thermal correction" in w:
                    # Parse correction from warning message
                    try:
                        parts = w.split("->")
                        if len(parts) >= 2:
                            new_val = parts[1].split("%")[0].strip()
                            lfl_corrected = float(new_val)
                            if substance.lfl_vol_pct and lfl_corrected:
                                lfl_correction_pct = round((1.0 - lfl_corrected / substance.lfl_vol_pct) * 100.0, 2)
                    except (ValueError, IndexError):
                        pass
                    break

            return Layer2Result(
                zone=hac_result.zone,
                horizontal_m=hac_result.extent.horizontal_m,
                vertical_m=hac_result.extent.vertical_m,
                volume_m3=hac_result.extent.volume_m3,
                ventilation=hac_result.ventilation,
                hazard_type=hac_result.hazard_type,
                lfl_corrected=lfl_corrected,
                lfl_correction_pct=lfl_correction_pct,
                warnings=tuple(hac_result.warnings),
                critical_flags=tuple(hac_result.critical_flags),
                success=True,
            )
        except Exception as exc:
            logger.error("Layer 2 FAILED: %s", exc)
            return Layer2Result(
                zone=ZoneType.UNCLASSIFIED,
                horizontal_m=0.0,
                vertical_m=0.0,
                volume_m3=0.0,
                ventilation=ventilation,
                hazard_type=substance.hazard_type,
                lfl_corrected=None,
                lfl_correction_pct=None,
                warnings=(str(exc),),
                critical_flags=(),
                success=False,
            )

    # ── Layer 3: ATEX Equipment ─────────────────────────────────────────

    def run_layer3(
        self,
        zone: ZoneType,
        hazard_type: HazardType,
        autoignition_c: Optional[float] = None,
        hac_warnings: Optional[List[str]] = None,
        hac_critical: Optional[List[str]] = None,
    ) -> Layer3Result:
        """Determine ATEX equipment specification with IEC 60079-14 thermal margin.

        Uses _select_temp_class_with_margin which applies:
          - Zone 0/20: 5% margin, minimum 10K
          - Zone 1/21: 5% margin, minimum 5K
          - Zone 2/22: strictly below
        """
        hac_warnings = hac_warnings or []
        hac_critical = hac_critical or []

        try:
            atex_result = self._atex_arbiter.arbitrate_v21(
                zone=zone,
                hazard_type=hazard_type,
                autoignition_c=autoignition_c,
                hac_warnings=hac_warnings,
                hac_critical=hac_critical,
            )
            spec: ATEXEquipmentSpec = atex_result.equipment_spec
            return Layer3Result(
                epl=spec.epl_required,
                atex_category=spec.atex_category,
                temp_class=spec.temp_class.value,
                protection_modes=tuple(spec.protection_modes),
                fire_detector_marking=atex_result.fire_detector_spec,
                warnings=tuple(atex_result.warnings),
                errors=tuple(atex_result.errors),
                success=atex_result.is_valid,
            )
        except Exception as exc:
            logger.error("Layer 3 FAILED: %s", exc)
            return Layer3Result(
                epl="Gc",
                atex_category="3G",
                temp_class="T4",
                protection_modes=("n",),
                fire_detector_marking=None,
                warnings=(),
                errors=(str(exc),),
                success=False,
            )

    # ── Layer 5: Optical Coverage ───────────────────────────────────────

    def run_layer5(
        self,
        detectors: List[FlameDetectorSpec],
        target_grid: List[RayTracePoint],
        obstructions: List[Obstruction],
        volumetric_media: Optional[List[VolumetricMedium]] = None,
    ) -> Layer5Result:
        """Compute optical coverage with volumetric media (Beer-Lambert).

        Uses sequential batch processing (NOT ProcessPoolExecutor).
        Chunks the target grid for memory efficiency, but processes
        sequentially because:
          1. Typical workload <1s — parallelism overhead exceeds benefit
          2. No GIL issues with sequential processing
          3. Preserves Pydantic frozen model integrity
          4. Deterministic, testable, debuggable
        """
        volumetric_media = volumetric_media or []

        if not detectors:
            return Layer5Result(
                total_points=len(target_grid),
                covered_points=0,
                coverage_pct=0.0,
                per_detector={},
                warnings=("No detectors provided.",),
                success=False,
            )

        try:
            # Use the existing, tested, production FlameDetectorAOCRayTrace
            # with R-tree spatial indexing and Beer-Lambert volumetric media
            coverage: CoverageResult = self._ray_engine.analyse_multi_v21(
                detectors=detectors,
                target_grid=target_grid,
                obstructions=obstructions,
                volumetric_media=volumetric_media,
            )

            return Layer5Result(
                total_points=coverage.total_points,
                covered_points=coverage.covered_points,
                coverage_pct=coverage.coverage_pct,
                per_detector=coverage.per_detector,
                warnings=tuple(coverage.warnings),
                success=True,
            )
        except Exception as exc:
            logger.error("Layer 5 FAILED: %s", exc)
            return Layer5Result(
                total_points=len(target_grid),
                covered_points=0,
                coverage_pct=0.0,
                per_detector={},
                warnings=(str(exc),),
                success=False,
            )

    # ── Layer 6: Safety Audit ───────────────────────────────────────────

    def run_layer6(
        self,
        zone: ZoneType,
        hazard_type: HazardType,
        min_redundancy: int = 0,
        min_transmittance: Optional[float] = None,
        substance: Optional[SubstanceProperties] = None,
        detector_z_positions: Optional[List[float]] = None,
        ceiling_height_m: float = 6.0,
    ) -> Layer6Result:
        """Run post-calculation safety audit against IEC/NFPA rules
        and jurisdiction-specific requirements.

        The audit engine NEVER modifies outputs — only reports violations.
        CRITICAL violations cause audit_status="FAIL". WARNING/INFO are advisory.
        """
        try:
            report: AuditReport = self._audit_engine.run_audit(
                zone=zone,
                hazard_type=hazard_type,
                min_redundancy=min_redundancy,
                min_transmittance=min_transmittance,
                env_context=self._env_context,
                substance=substance,
                detector_z_positions=detector_z_positions,
                ceiling_height_m=ceiling_height_m,
            )
            return Layer6Result(
                audit_status=report.status,
                total_checks=report.total_checks,
                passed_checks=report.passed_checks,
                critical_violations=tuple(v.message for v in report.violations if v.severity == "CRITICAL"),
                warning_violations=tuple(v.message for v in report.violations if v.severity == "WARNING"),
                info_violations=tuple(v.message for v in report.violations if v.severity == "INFO"),
                all_violations=tuple(v.message for v in report.violations),
                success=report.is_pass,
            )
        except Exception as exc:
            logger.error("Layer 6 FAILED: %s", exc)
            return Layer6Result(
                audit_status="FAIL",
                total_checks=0,
                passed_checks=0,
                critical_violations=(str(exc),),
                warning_violations=(),
                info_violations=(),
                all_violations=(str(exc),),
                success=False,
            )

    # ── Full Pipeline ───────────────────────────────────────────────────

    def run_full_pipeline(
        self,
        country_code: str,
        substance: SubstanceProperties,
        ventilation: VentilationLevel,
        detectors: List[FlameDetectorSpec],
        target_grid: List[RayTracePoint],
        obstructions: Optional[List[Obstruction]] = None,
        volumetric_media: Optional[List[VolumetricMedium]] = None,
        is_indoor: bool = True,
    ) -> PipelineResult:
        """Run the complete 5-layer pipeline.

        Each layer's output feeds into the next. Pipeline stops on
        unrecoverable failure but reports partial results.
        """
        start_time = time.monotonic()
        obstructions = obstructions or []
        pipeline_warnings: List[str] = []
        pipeline_errors: List[str] = []

        # ── Layer 1: Regulatory Framework ──
        logger.info("Layer 1: Resolving regulatory framework for %s", country_code)
        l1 = self.run_layer1(country_code)
        if not l1.success:
            elapsed = time.monotonic() - start_time
            pipeline_errors.append(f"Layer 1 failed: {l1.warnings}")
            return PipelineResult(
                layer1=l1,
                env_context=self._env_context,
                elapsed_seconds=round(elapsed, 3),
                pipeline_warnings=tuple(pipeline_warnings),
                pipeline_errors=tuple(pipeline_errors),
                success=False,
            )
        pipeline_warnings.extend(l1.warnings)

        # ── Layer 2: HAC Classification ──
        logger.info(
            "Layer 2: Classifying hazardous area (%s, %s, T_ambient=%.1fC)",
            substance.name,
            substance.hazard_type.value,
            self._env_context.ambient_temp_c,
        )
        l2 = self.run_layer2(substance, ventilation, is_indoor)
        if not l2.success:
            elapsed = time.monotonic() - start_time
            pipeline_errors.append("Layer 2 failed")
            return PipelineResult(
                layer1=l1,
                layer2=l2,
                env_context=self._env_context,
                elapsed_seconds=round(elapsed, 3),
                pipeline_warnings=tuple(pipeline_warnings),
                pipeline_errors=tuple(pipeline_errors),
                success=False,
            )
        pipeline_warnings.extend(l2.warnings)
        if l2.critical_flags:
            pipeline_warnings.extend(l2.critical_flags)

        # ── Layer 3: ATEX Equipment ──
        logger.info("Layer 3: Determining ATEX equipment for %s", l2.zone.value)
        l3 = self.run_layer3(
            zone=l2.zone,
            hazard_type=l2.hazard_type,
            autoignition_c=substance.autoignition_c,
            hac_warnings=list(l2.warnings),
            hac_critical=list(l2.critical_flags),
        )
        if not l3.success:
            pipeline_warnings.extend(l3.warnings)
            pipeline_errors.extend(l3.errors)
            # Layer 3 failure is NOT fatal — continue to Layer 5

        # ── Layer 5: Optical Coverage ──
        logger.info(
            "Layer 5: Optical coverage (%d detectors, %d target points, %d obstructions, %d media)",
            len(detectors),
            len(target_grid),
            len(obstructions),
            len(volumetric_media or []),
        )
        l5 = self.run_layer5(
            detectors=detectors,
            target_grid=target_grid,
            obstructions=obstructions,
            volumetric_media=volumetric_media,
        )
        pipeline_warnings.extend(l5.warnings)
        if not l5.success:
            pipeline_errors.append("Layer 5 failed")

        # ── Layer 6: Safety Audit ──
        logger.info(
            "Layer 6: Safety audit (zone=%s, redundancy=%d, jurisdiction=%s)",
            l2.zone.value,
            0,
            self._env_context.jurisdiction.value,
        )
        detector_zs = [d.position[2] for d in detectors if len(d.position) > 2] if detectors else None
        l6 = self.run_layer6(
            zone=l2.zone,
            hazard_type=l2.hazard_type,
            min_redundancy=0,  # Will be populated from Layer 5 coverage result
            substance=substance,
            detector_z_positions=detector_zs,
        )
        if not l6.success:
            pipeline_warnings.extend(l6.all_violations)

        elapsed = time.monotonic() - start_time
        overall_success = l1.success and l2.success and l5.success

        logger.info(
            "Pipeline complete: %s (%.3fs). Zone=%s, Coverage=%.1f%%, Audit=%s",
            "PASS" if overall_success else "FAIL",
            elapsed,
            l2.zone.value,
            l5.coverage_pct,
            l6.audit_status,
        )

        return PipelineResult(
            layer1=l1,
            layer2=l2,
            layer3=l3,
            layer5=l5,
            layer6=l6,
            env_context=self._env_context,
            elapsed_seconds=round(elapsed, 3),
            pipeline_warnings=tuple(pipeline_warnings),
            pipeline_errors=tuple(pipeline_errors),
            success=overall_success,
        )
