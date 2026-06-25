"""safety_audit_engine.py – FireAI V21.2 Automated Safety Audit Engine
====================================================================
Post-calculation compliance validation engine. Runs as the final step
after all 5 layers complete. Validates design outputs against IEC/NFPA
rules and jurisdiction-specific requirements.

Design Principle: The audit engine NEVER modifies design outputs.
It only reports violations. Engineering judgment always prevails.

Consultant Proposals Integrated:
  - SafetyAuditEngine (4 audit gates) — ACCEPTED with Pydantic models
  - MENA Region Localization — ACCEPTED with advisory (not forced) approach
  - Z-Axis/Vapor Density Audit — ACCEPTED with flexibility

Rejected Elements:
  - RegionProfile forcing max(temp, 55.0) — violates engineering judgment
  - Empty jurisdiction stubs (UAE_FIRE_CODE, EGYPTIAN_FIRE_CODE) — misleading
  - Dict-based AuditResult — replaced with Pydantic models

Standards:
  IEC 60079-10-1:2015  – Gas zone classification
  IEC 61508:2010       – Functional safety (SIL)
  NFPA 72-2022 §17.8.3.4 – Redundancy requirements
  FM Global DS 5-48    – Flame detector application
  HCIS SAF Directive   – Saudi industrial safety requirements
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fireai.core.models_v21 import (
    MIN_REDUNDANCY_BY_ZONE,
    ElevationTier,
    EnvironmentalContext,
    HazardType,
    Jurisdiction,
    RegionProfile,
    SubstanceProperties,
    ZoneType,
    vapor_density_tier,
)

# ---------------------------------------------------------------------------
# Audit Models
# ---------------------------------------------------------------------------


class AuditSeverity(str):
    """Violation severity levels.

    Use as: AuditSeverity.CRITICAL (str subclass, value='CRITICAL').
    AuditViolation.severity is validated against these values.
    """

    CRITICAL = "CRITICAL"  # Must fix before deployment
    WARNING = "WARNING"  # Advisory — engineering review recommended
    INFO = "INFO"  # Informational — no action required

    @classmethod
    def valid_values(cls) -> set:
        """Return the set of valid severity strings."""
        return {cls.CRITICAL, cls.WARNING, cls.INFO}


class AuditViolation(BaseModel):
    """A single audit violation with full traceability."""

    model_config = ConfigDict(frozen=True, strict=True)

    gate: str  # e.g., "REDUNDANCY", "FOULING", "ZONE_MAPPING", "Z_AXIS", "MENA"
    severity: str  # CRITICAL, WARNING, INFO — validated against AuditSeverity
    code: str  # e.g., "RED-001", "FOUL-001", "ZAX-001"
    message: str  # Human-readable violation description
    standard_ref: str  # e.g., "NFPA 72 §17.8.3.4"
    remediation: str  # What the engineer should do

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        """Ensure severity is one of the AuditSeverity defined values."""
        valid = AuditSeverity.valid_values()
        if v not in valid:
            raise ValueError(
                f"Invalid severity '{v}'. Must be one of: {sorted(valid)}. "
                f"Use AuditSeverity.CRITICAL / .WARNING / .INFO."
            )
        return v


class AuditInput(BaseModel):
    """Immutable, strict input for safety audit engine.

    All fields are validated at construction time. No loose types,
    no extra fields, no mutation after creation. This is the
    anti-corruption layer between user input and audit logic.

    Design Principles:
      - frozen=True: No mutation after construction
      - strict=True: No type coercion (string "2" won't become int 2)
      - extra='forbid': No injected fields (security anti-tampering)
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    zone: str = Field(description="Zone classification string (e.g., 'ZONE_1', 'ZONE_2')")
    min_redundancy: int = Field(ge=0, description="Actual minimum detector redundancy")
    final_transmittance: float = Field(
        gt=0.0,
        le=1.0,
        description="Spectral optical transmittance BEFORE fouling adjustment (fouling applied in _check_fouling)",
    )
    substance_molecular_weight: float = Field(gt=0.0, description="Molecular weight of the target gas (g/mol)")
    detector_elevation_tier: ElevationTier = Field(description="Elevation tier where detectors are placed")
    jurisdiction: Jurisdiction = Field(
        default=Jurisdiction.GLOBAL_IEC, description="Regulatory jurisdiction for audit rules"
    )
    hazard_type: Optional[HazardType] = Field(
        default=None,
        description="Hazard type for zone mapping validation (GAS, DUST, HYBRID). "
        "If not provided, inferred from zone classification.",
    )
    region: Optional[RegionProfile] = Field(
        default=None,
        description="Environmental region preset for MENA advisory checks. "
        "If not provided, inferred from jurisdiction.",
    )
    lens_fouling_factor: float = Field(
        default=0.85,
        gt=0.0,
        le=1.0,
        description=(
            "Optical path attenuation from lens fouling (0.0-1.0). "
            "Default 0.85 = typical industrial. Provide actual measured value "
            "for accurate fouling assessment. Per FM Global DS 5-48 §3.2.1."
        ),
    )


class AuditResult(BaseModel):
    """Result of safety audit. Immutable after construction."""

    model_config = ConfigDict(frozen=True, strict=True)

    status: str = Field(description="PASS or FAIL")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        """Ensure status is PASS or FAIL."""
        if v not in ("PASS", "FAIL"):
            raise ValueError(f"Invalid status '{v}'. Must be 'PASS' or 'FAIL'.")
        return v

    violations: List[AuditViolation] = Field(default_factory=list)
    total_checks: int = Field(ge=0, description="Total number of audit checks performed")
    passed_checks: int = Field(ge=0, description="Number of checks that passed")

    @property
    def is_pass(self) -> bool:
        return self.status == "PASS"

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "CRITICAL")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "WARNING")

    @property
    def info_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "INFO")


# ---------------------------------------------------------------------------
# Detector Elevation Inference
# ---------------------------------------------------------------------------


def elevation_tier_from_detector_z(z_position: float, ceiling_height_m: float = 6.0) -> ElevationTier:
    """Infer the elevation tier of a detector from its Z position.

    This is a heuristic mapping. In practice, the engineer should specify
    the intended elevation tier directly. This function provides a reasonable
    default for audit purposes.

    Args:
        z_position: Detector Z coordinate (meters from floor)
        ceiling_height_m: Room ceiling height (default 6.0m for industrial)

    Returns:
        ElevationTier based on detector height relative to ceiling

    """
    # V57 FIX: NaN z_position silently falls through to BREATHING_ZONE.
    # NaN >= X is False, NaN <= X is False → BREATHING_ZONE (middle tier).
    # A detector with unknown elevation should NOT be classified as correctly placed.
    if not isinstance(z_position, (int, float)) or not math.isfinite(z_position):
        return ElevationTier.BREATHING_ZONE  # Tier assigned, but callers must check
        # for NaN and emit CRITICAL violation via ZAX-002/ZAX-003
    if z_position >= ceiling_height_m * 0.75:
        return ElevationTier.HIGH
    if z_position <= ceiling_height_m * 0.25:
        return ElevationTier.LOW
    return ElevationTier.BREATHING_ZONE


# ---------------------------------------------------------------------------
# MENA Jurisdiction Rules
# ---------------------------------------------------------------------------

# Saudi HCIS: minimum 1oo2 voting for flame detectors in Zone 2
# Source: HCIS SAF Directive 2021, Section 4.3
# Applies to "critical process installations" — defined as installations
# where a fire could cause cascade failure of process equipment.
_HCIS_MIN_REDUNDANCY: Dict[ZoneType, int] = {
    ZoneType.ZONE_0: 3,  # 2oo3 (same as IEC)
    ZoneType.ZONE_1: 2,  # 1oo2 (same as IEC)
    ZoneType.ZONE_2: 2,  # 1oo2 MINIMUM (stricter than IEC which allows 1)
    ZoneType.ZONE_20: 3,  # 2oo3 (same as IEC)
    ZoneType.ZONE_21: 2,  # 1oo2 (same as IEC)
    ZoneType.ZONE_22: 2,  # 1oo2 (stricter than IEC which allows 1)
    ZoneType.UNCLASSIFIED: 0,
}


def _get_required_redundancy(
    zone: ZoneType,
    jurisdiction: Jurisdiction,
) -> int:
    """Get minimum required detector redundancy per zone and jurisdiction.

    For GLOBAL_IEC / EGYPTIAN_FIRE_CODE / USA_NFPA: uses MIN_REDUNDANCY_BY_ZONE
    These jurisdictions follow base IEC/NFPA standards which allow
    single detector (1oo1) in Zone 2.

    For SAUDI_HCIS: uses _HCIS_MIN_REDUNDANCY (1oo2 minimum in Zone 2/22)
    This is stricter than the base IEC standard per HCIS SAF Directive.

    Args:
        zone: The zone type
        jurisdiction: The regulatory jurisdiction

    Returns:
        Minimum number of independent detectors required per point

    """
    # V43 FIX: If zone is None or unrecognized, return a conservative default
    # (2 detectors) instead of 1. A single detector in an unknown zone is a
    # Single Point of Failure. Fail-safe: require MORE redundancy for unknown
    # zones, not less. Per IEC 60079-10-1, unknown zone classification is a
    # safety concern that should require manual review.
    if zone is None:
        return 2  # Conservative fail-safe for unknown zone
    if jurisdiction == Jurisdiction.SAUDI_HCIS:
        return _HCIS_MIN_REDUNDANCY.get(zone, 2)  # V43: changed default 1→2
    # GLOBAL_IEC, EGYPTIAN_FIRE_CODE, USA_NFPA all follow base IEC/NFPA
    return MIN_REDUNDANCY_BY_ZONE.get(zone, 2)  # V43: changed default 1→2


# ---------------------------------------------------------------------------
# Safety Audit Engine
# ---------------------------------------------------------------------------


class SafetyAuditEngine:
    """Automated safety audit engine for FireAI design outputs.

    Runs as the FINAL step in the design pipeline (after Layer 5).
    Validates design outputs against IEC/NFPA rules and jurisdiction-specific
    requirements. NEVER modifies outputs — only reports violations.

    Audit Gates:
      1. REDUNDANCY GATE — Zone-based minimum detector redundancy
      2. FOULING GATE — Optical transmittance degradation check
      3. ZONE_MAPPING GATE — Zone/hazard_type consistency validation
      4. Z-AXIS GATE — Detector elevation vs gas buoyancy behavior
      5. MENA GATE — Region-specific advisory checks (if applicable)

    Usage:
        engine = SafetyAuditEngine()
        result = engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=1,
            min_transmittance=0.75,
            env_context=env_context,
            substance=substance,
            detector_z_positions=[5.5, 5.8],
            ceiling_height_m=6.0,
        )
        if result.status == "FAIL":
            for v in result.violations:
                print(f"[{v.code}] {v.message}")
    """

    # Minimum transmittance threshold for fouling gate
    # Below this, the optical path is considered degraded beyond
    # acceptable service life per FM Global DS 5-48 §3.2.1
    MIN_TRANSMITTANCE_WARNING: float = 0.25
    MIN_TRANSMITTANCE_CRITICAL: float = 0.10

    def run_audit(
        self,
        zone=None,
        hazard_type=None,
        min_redundancy: int = 0,
        min_transmittance: Optional[float] = None,
        env_context: Optional[EnvironmentalContext] = None,
        substance: Optional[SubstanceProperties] = None,
        detector_z_positions: Optional[List[float]] = None,
        ceiling_height_m: float = 6.0,
        audit_input: Optional[AuditInput] = None,
    ) -> AuditResult:
        """Run all audit gates and return combined AuditResult.

        Args:
            zone: Zone classification from Layer 2
            hazard_type: Hazard type from Layer 2
            min_redundancy: Actual minimum redundancy from Layer 5
            min_transmittance: Actual minimum spectral transmittance from Layer 5
            env_context: Environmental context with region/jurisdiction
            substance: Substance properties (for Z-Axis gate)
            detector_z_positions: Z coordinates of detectors (for Z-Axis gate)
            ceiling_height_m: Room ceiling height (default 6.0m industrial)

        Returns:
            AuditResult with PASS/FAIL status and list of violations

        """
        # ── Handle AuditInput (simplified API) ──
        if audit_input is not None:
            return self._run_audit_from_input(audit_input)

        env_context = env_context or EnvironmentalContext()
        violations: List[AuditViolation] = []
        total_checks = 0
        passed_checks = 0

        # V48 FIX: Wrap each gate in try/except to ensure audit NEVER fails to
        # produce a result. In safety-critical systems, the audit engine must
        # ALWAYS return a result — any gate crash should produce a CRITICAL
        # violation, not propagate an exception (fail-safe, not fail-open).

        # ── Gate 1: Redundancy ──
        try:
            v, tc, pc = self._check_redundancy(zone, min_redundancy, env_context)
            violations.extend(v)
            total_checks += tc
            passed_checks += pc
        except Exception as e:
            violations.append(
                AuditViolation(
                    gate="REDUNDANCY",
                    severity="CRITICAL",
                    code="AUDIT-001",
                    message=f"Redundancy gate failed: {e}",
                    standard_ref="Safety audit integrity",
                    remediation="Review input data",
                )
            )
            total_checks += 1

        # ── Gate 2: Fouling / Transmittance ──
        try:
            v, tc, pc = self._check_fouling(min_transmittance, env_context)
            violations.extend(v)
            total_checks += tc
            passed_checks += pc
        except Exception as e:
            violations.append(
                AuditViolation(
                    gate="FOULING",
                    severity="CRITICAL",
                    code="AUDIT-002",
                    message=f"Fouling gate failed: {e}",
                    standard_ref="Safety audit integrity",
                    remediation="Review input data",
                )
            )
            total_checks += 1

        # ── Gate 3: Zone Mapping ──
        try:
            v, tc, pc = self._check_zone_mapping(zone, hazard_type)
            violations.extend(v)
            total_checks += tc
            passed_checks += pc
        except Exception as e:
            violations.append(
                AuditViolation(
                    gate="ZONE_MAPPING",
                    severity="CRITICAL",
                    code="AUDIT-003",
                    message=f"Zone mapping gate failed: {e}",
                    standard_ref="Safety audit integrity",
                    remediation="Review input data",
                )
            )
            total_checks += 1

        # ── Gate 4: Z-Axis / Vapor Density ──
        try:
            v, tc, pc = self._check_z_axis(substance, detector_z_positions, ceiling_height_m)
            violations.extend(v)
            total_checks += tc
            passed_checks += pc
        except Exception as e:
            violations.append(
                AuditViolation(
                    gate="Z_AXIS",
                    severity="CRITICAL",
                    code="AUDIT-004",
                    message=f"Z-axis gate failed: {e}",
                    standard_ref="Safety audit integrity",
                    remediation="Review input data",
                )
            )
            total_checks += 1

        # ── Gate 5: MENA Region ──
        try:
            v, tc, pc = self._check_mena(zone, env_context)
            violations.extend(v)
            total_checks += tc
            passed_checks += pc
        except Exception as e:
            violations.append(
                AuditViolation(
                    gate="MENA",
                    severity="CRITICAL",
                    code="AUDIT-005",
                    message=f"MENA gate failed: {e}",
                    standard_ref="Safety audit integrity",
                    remediation="Review input data",
                )
            )
            total_checks += 1

        # Determine overall status
        has_critical = any(v.severity == "CRITICAL" for v in violations)
        status = "FAIL" if has_critical else "PASS"

        return AuditResult(
            status=status,
            violations=violations,
            total_checks=total_checks,
            passed_checks=passed_checks,
        )

    def _run_audit_from_input(self, audit_input: AuditInput) -> AuditResult:
        """Run audit from a structured AuditInput object.

        This method uses the simplified AuditInput API where the caller
        provides a single immutable object with all audit parameters.
        It translates AuditInput fields to the internal gate checks.

        Key difference from run_audit: uses vapor_density_tier (ratio-based)
        for elevation classification instead of determine_gas_elevation_tier
        (heuristic-based). This is the precise physics engine path.

        All 5 audit gates are executed, matching run_audit() behavior:
          Gate 1: Redundancy
          Gate 2: Fouling / Transmittance
          Gate 3: Zone Mapping
          Gate 4: Elevation Mismatch (via vapor_density_tier)
          Gate 5: MENA Region
        """
        violations: List[AuditViolation] = []
        total_checks = 0
        passed_checks = 0

        # Parse zone string to ZoneType
        try:
            zone = ZoneType(audit_input.zone)
        except ValueError:
            violations.append(
                AuditViolation(
                    gate="INPUT",
                    severity="CRITICAL",
                    code="INPUT-001",
                    message=f"Invalid zone string: {audit_input.zone}",
                    standard_ref="IEC 60079-10-1:2015",
                    remediation="Use valid zone: ZONE_0, ZONE_1, ZONE_2, ZONE_20, ZONE_21, ZONE_22",
                )
            )
            return AuditResult(status="FAIL", violations=violations, total_checks=1, passed_checks=0)

        # Determine region: explicit from AuditInput, or inferred from jurisdiction
        if audit_input.region is not None:
            region = audit_input.region
        else:
            _JURISDICTION_REGION_MAP = {
                Jurisdiction.SAUDI_HCIS: RegionProfile.GULF_HCIS,
                Jurisdiction.EGYPTIAN_FIRE_CODE: RegionProfile.EGYPT_CODE,
            }
            region = _JURISDICTION_REGION_MAP.get(audit_input.jurisdiction, RegionProfile.STANDARD_IEC)

        # Build EnvironmentalContext from AuditInput jurisdiction and region
        # V48 FIX: Pass lens_fouling_factor from AuditInput to EnvironmentalContext.
        # Without this, fouling gate always uses the optimistic default (0.85)
        # regardless of actual environmental conditions, allowing a detector
        # that cannot sense fire to PASS audit.
        env_context = EnvironmentalContext(
            jurisdiction=audit_input.jurisdiction,
            region=region,
            lens_fouling_factor=audit_input.lens_fouling_factor,
        )

        # Determine hazard_type: explicit from AuditInput, or inferred from zone
        if audit_input.hazard_type is not None:
            hazard_type = audit_input.hazard_type
        else:
            _GAS_ZONES = {ZoneType.ZONE_0, ZoneType.ZONE_1, ZoneType.ZONE_2}
            _DUST_ZONES = {ZoneType.ZONE_20, ZoneType.ZONE_21, ZoneType.ZONE_22}
            if zone in _GAS_ZONES:
                hazard_type = HazardType.GAS
            elif zone in _DUST_ZONES:
                hazard_type = HazardType.DUST
            else:
                hazard_type = None  # UNCLASSIFIED — no mapping to validate

        # ── Gate 1: Redundancy ──
        v, tc, pc = self._check_redundancy(zone, audit_input.min_redundancy, env_context)
        violations.extend(v)
        total_checks += tc
        passed_checks += pc

        # ── Gate 2: Fouling / Transmittance ──
        v, tc, pc = self._check_fouling(audit_input.final_transmittance, env_context)
        violations.extend(v)
        total_checks += tc
        passed_checks += pc

        # ── Gate 3: Zone Mapping ──
        # V48 FIX: Always run zone mapping gate, even when hazard_type is None.
        # Skipping this gate means missing zone/hazard consistency issues.
        # When hazard_type is None, _check_zone_mapping emits a WARNING.
        v, tc, pc = self._check_zone_mapping(zone, hazard_type)
        violations.extend(v)
        total_checks += tc
        passed_checks += pc

        # ── Gate 4: Elevation Mismatch (Z-Axis via vapor_density_tier) ──
        # Uses ratio-based buoyancy classification for precise physics
        v, tc, pc = self._check_elevation_mismatch(audit_input)
        violations.extend(v)
        total_checks += tc
        passed_checks += pc

        # ── Gate 5: MENA Region ──
        v, tc, pc = self._check_mena(zone, env_context)
        violations.extend(v)
        total_checks += tc
        passed_checks += pc

        # Determine overall status
        has_critical = any(v.severity == "CRITICAL" for v in violations)
        status = "FAIL" if has_critical else "PASS"

        return AuditResult(
            status=status,
            violations=violations,
            total_checks=total_checks,
            passed_checks=passed_checks,
        )

    def _check_elevation_mismatch(
        self,
        audit_input: AuditInput,
    ) -> tuple:
        """Check detector elevation vs gas buoyancy using ratio-based classification.

        Uses vapor_density_tier() from models_v21 for precise density-ratio
        classification (0.97/1.03 of AIR_MW thresholds).

        This gate produces CRITICAL violations because placing a detector
        at the wrong elevation for the gas is a physical blind spot that
        may render the entire detection system ineffective.

        Args:
            audit_input: Validated audit input with MW and elevation tier

        Returns:
            Tuple of (violations, total_checks, passed_checks)

        """
        violations: List[AuditViolation] = []
        total_checks = 1
        passed_checks = 0

        # Determine expected tier from molecular weight using ratio-based physics
        expected_tier = vapor_density_tier(audit_input.substance_molecular_weight)
        actual_tier = audit_input.detector_elevation_tier

        if actual_tier != expected_tier:
            # Describe the mismatch
            tier_desc = {
                ElevationTier.HIGH: "ceiling/high level (gas rises)",
                ElevationTier.BREATHING_ZONE: "breathing zone (1-2m, gas disperses)",
                ElevationTier.LOW: "floor/low level (gas sinks)",
            }
            gas_behavior = {
                ElevationTier.HIGH: "lighter than air — rises to ceiling",
                ElevationTier.BREATHING_ZONE: "near air density — disperses in breathing zone",
                ElevationTier.LOW: "heavier than air — pools at floor level",
            }
            violations.append(
                AuditViolation(
                    gate="ELEVATION",
                    severity="CRITICAL",
                    code="ELEV-001",
                    message=(
                        f"ELEVATION MISMATCH: Gas with MW={audit_input.substance_molecular_weight:.2f} g/mol "
                        f"is {gas_behavior[expected_tier]}, but detector is at "
                        f"{tier_desc[actual_tier]}. This creates a physical blind spot — "
                        f"the gas cloud may never reach the detector. "
                        f"Expected tier: {expected_tier.value}, Actual tier: {actual_tier.value}."
                    ),
                    standard_ref="IEC 60079-10-1:2015 §B.4, NFPA 497 §4.5",
                    remediation=(
                        f"Relocate detector to {tier_desc[expected_tier]} for this gas, "
                        f"or add an additional detector at the correct elevation. "
                        f"Document engineering rationale if current placement is intentional."
                    ),
                )
            )
        else:
            passed_checks = 1

        return violations, total_checks, passed_checks

    # ── Gate 1: Redundancy ─────────────────────────────────────────────

    def _check_redundancy(
        self,
        zone: ZoneType,
        min_redundancy: int,
        env_context: EnvironmentalContext,
    ) -> tuple:
        """Check zone-based minimum detector redundancy."""
        violations: List[AuditViolation] = []
        total_checks = 1
        passed_checks = 0

        required = _get_required_redundancy(zone, env_context.jurisdiction)

        # V48 FIX: None-guard for zone.value — zone=None caused AttributeError crash
        zone_label = zone.value if zone is not None else "UNCLASSIFIED"

        if min_redundancy < required:
            jur_note = ""
            if env_context.jurisdiction == Jurisdiction.SAUDI_HCIS:
                jur_note = " [HCIS SAF Directive 2021 §4.3]"
            violations.append(
                AuditViolation(
                    gate="REDUNDANCY",
                    severity="CRITICAL",
                    code="RED-001",
                    message=(
                        f"Insufficient detector redundancy for {zone_label}: "
                        f"actual={min_redundancy}, required={required}.{jur_note} "
                        f"Points with <{required} detector(s) are Single Point "
                        f"of Failure (SPOF)."
                    ),
                    standard_ref=f"NFPA 72-2022 §17.8.3.4, FM Global DS 5-48 §3.1{jur_note}",
                    remediation=(
                        f"Add {required - min_redundancy} additional independent "
                        f"detector(s) to achieve {required}-detector coverage per point."
                    ),
                )
            )
        else:
            passed_checks = 1

        return violations, total_checks, passed_checks

    # ── Gate 2: Fouling / Transmittance ───────────────────────────────

    def _check_fouling(
        self,
        min_transmittance: Optional[float],
        env_context: EnvironmentalContext,
    ) -> tuple:
        """Check optical transmittance degradation from fouling."""
        violations: List[AuditViolation] = []
        total_checks = 0
        passed_checks = 0

        fouling = env_context.lens_fouling_factor

        # Check 2a: Fouling factor itself
        total_checks += 1
        # V55 FIX: NaN guard — fouling must be a finite number
        if not isinstance(fouling, (int, float)) or not math.isfinite(fouling):
            violations.append(
                AuditViolation(
                    gate="FOULING",
                    severity="CRITICAL",
                    code="FOUL-006",
                    message=(
                        f"Lens fouling factor is not a valid number (got {fouling!r}). "
                        f"Cannot verify optical path integrity. "
                        f"[FM Global DS 5-48 §3.2.1]"
                    ),
                    standard_ref="FM Global DS 5-48 §3.2.1",
                    remediation=(
                        "Investigate data pipeline for NaN/Inf contamination. "
                        "Replace invalid fouling factor with a measured or assumed value "
                        "before re-running the audit."
                    ),
                )
            )
        elif fouling < 0.50:
            violations.append(
                AuditViolation(
                    gate="FOULING",
                    severity="CRITICAL",
                    code="FOUL-001",
                    message=(
                        f"Lens fouling factor ({fouling:.2f}) is critically low. "
                        f"Effective transmittance may be below detection threshold. "
                        f"Scheduled lens cleaning program is MANDATORY."
                    ),
                    standard_ref="FM Global DS 5-48 §3.2.1",
                    remediation=(
                        "Implement scheduled lens cleaning program per manufacturer "
                        "recommendations. Consider protective shielding or purged "
                        "enclosures for detectors in high-fouling environments."
                    ),
                )
            )
        elif fouling < 0.70:
            violations.append(
                AuditViolation(
                    gate="FOULING",
                    severity="WARNING",
                    code="FOUL-002",
                    message=(
                        f"Lens fouling factor ({fouling:.2f}) indicates significant "
                        f"optical degradation. Effective detection range is reduced."
                    ),
                    standard_ref="FM Global DS 5-48 §3.2.1",
                    remediation=(
                        "Review cleaning schedule. Consider increasing fouling "
                        "allowance in design calculations or adding redundant detectors."
                    ),
                )
            )
        else:
            passed_checks += 1

        # Check 2b: Effective transmittance after fouling
        if min_transmittance is not None:
            total_checks += 1
            # V57 FIX: NaN min_transmittance makes effective_t = NaN,
            # then NaN < threshold is False → fouling gate PASSES.
            # Cannot verify optical path with corrupt spectral data.
            if not isinstance(min_transmittance, (int, float)) or not math.isfinite(min_transmittance):
                violations.append(
                    AuditViolation(
                        gate="FOULING",
                        severity="CRITICAL",
                        code="FOUL-006",
                        message=(
                            f"NaN/Inf min_transmittance={min_transmittance!r}. "
                            f"Cannot verify optical path integrity. Per FM Global DS 5-48 §3.2.1, "
                            f"flame detector audit requires valid spectral transmittance data."
                        ),
                        standard_ref="FM Global DS 5-48 §3.2.1",
                        remediation=(
                            "Investigate data pipeline for NaN/Inf contamination. "
                            "Provide valid spectral transmittance value before re-running audit."
                        ),
                    )
                )
                # V79 FIX: Don't reset passed_checks to 0 — this erases the valid
                # pass from Check 2a (fouling factor ≥ 0.70). Just don't increment
                # for this check. The NaN/Inf case is already handled above with
                # a CRITICAL violation, which will correctly mark the audit as failed.
                # passed_checks = 0  ← REMOVED
            else:
                effective_t = min_transmittance * fouling
                if effective_t < self.MIN_TRANSMITTANCE_CRITICAL:
                    violations.append(
                        AuditViolation(
                            gate="FOULING",
                            severity="CRITICAL",
                            code="FOUL-003",
                            message=(
                                f"Effective transmittance ({effective_t:.4f}) is below "
                                f"critical threshold ({self.MIN_TRANSMITTANCE_CRITICAL}). "
                                f"Detector may fail to sense fire at rated range. "
                                f"(spectral_t={min_transmittance:.4f}, fouling={fouling:.2f})"
                            ),
                            standard_ref="FM Global DS 5-48 §3.2.1, IEC 60079-29-4 §6.2",
                            remediation=(
                                "Reduce detector-to-target distance, add redundant "
                                "detectors, or implement lens cleaning program to "
                                "restore optical path integrity."
                            ),
                        )
                    )
                elif effective_t < self.MIN_TRANSMITTANCE_WARNING:
                    violations.append(
                        AuditViolation(
                            gate="FOULING",
                            severity="WARNING",
                            code="FOUL-004",
                            message=(
                                f"Effective transmittance ({effective_t:.4f}) is below "
                                f"warning threshold ({self.MIN_TRANSMITTANCE_WARNING}). "
                                f"Detection margin is reduced. "
                                f"(spectral_t={min_transmittance:.4f}, fouling={fouling:.2f})"
                            ),
                            standard_ref="FM Global DS 5-48 §3.2.1",
                            remediation=(
                                "Review detector placement. Consider closer spacing "
                                "or additional detectors to maintain detection margin."
                            ),
                        )
                    )
                else:
                    passed_checks += 1
        else:
            # V31 FIX: min_transmittance not provided — severity depends on
            # fouling severity. CRITICAL only when fouling is already at
            # CRITICAL level (< 0.50 per FOUL-001), because:
            #   - Fouling < 0.50: detection may be compromised; missing
            #     transmittance verification is CRITICAL (aligned with FOUL-001)
            #   - Fouling 0.50-0.70: FOUL-002 already flags degradation at
            #     WARNING; missing data is WARNING (advisory, not blocking)
            #   - Fouling >= 0.70: low risk; WARNING suffices
            # Previous threshold (0.85) was too broad — it made FOUL-005
            # CRITICAL even when fouling was only at WARNING level, causing
            # false FAIL for scenarios where the engineer has already
            # acknowledged degradation via a low fouling factor.
            # Per agent.md V25 finding #3: silently skipping masks risks.
            # Per NFPA 72 §17.8.3.4 and FM Global DS 5-48 §3.2.1: fouling
            # verification is advisory when fouling is already accounted for
            # in the design; CRITICAL only when it may mask a detection failure.
            total_checks += 1
            is_harsh_env = fouling < 0.50
            violations.append(
                AuditViolation(
                    gate="FOULING",
                    severity="CRITICAL" if is_harsh_env else "WARNING",
                    code="FOUL-005",
                    message=(
                        f"Effective transmittance check SKIPPED — "
                        f"min_transmittance not provided. Optical path degradation "
                        f"from fouling, dust, or contaminant accumulation cannot be "
                        f"verified. This may mask reduced detection capability in "
                        f"industrial or harsh environments per FM Global DS 5-48 §3.2.1."
                        f"{' HARSH ENVIRONMENT DETECTED: fouling factor=' + f'{fouling:.2f}' + ' < 0.50 — skipping this check is CRITICAL.' if is_harsh_env else ''}"
                    ),
                    standard_ref="FM Global DS 5-48 §3.2.1, IEC 60079-29-4 §6.2",
                    remediation=(
                        "Provide min_transmittance from spectral analysis (Layer 5) "
                        "or detector manufacturer datasheet. For flame detectors, "
                        "this is typically 0.5-0.9 for clean optical paths."
                    ),
                )
            )

        return violations, total_checks, passed_checks

    # ── Gate 3: Zone Mapping ──────────────────────────────────────────

    def _check_zone_mapping(
        self,
        zone: ZoneType,
        hazard_type: HazardType,
    ) -> tuple:
        """Check zone/hazard_type consistency per IEC 60079-10-1 §1.3."""
        violations: List[AuditViolation] = []
        total_checks = 1
        passed_checks = 0

        _GAS_ZONES = {ZoneType.ZONE_0, ZoneType.ZONE_1, ZoneType.ZONE_2}
        _DUST_ZONES = {ZoneType.ZONE_20, ZoneType.ZONE_21, ZoneType.ZONE_22}

        if zone in _GAS_ZONES and hazard_type == HazardType.DUST:
            violations.append(
                AuditViolation(
                    gate="ZONE_MAPPING",
                    severity="CRITICAL",
                    code="ZMAP-001",
                    message=(
                        f"Zone {zone.value} is a GAS zone but hazard_type is DUST. "
                        f"This combination indicates a data-entry error or "
                        f"classification error. Zones 0/1/2 are for GAS/VAPOUR. "
                        f"Did you mean Zone 20/21/22?"
                    ),
                    standard_ref="IEC 60079-10-1:2015 §1.3",
                    remediation=(
                        "Re-classify using correct zone type for DUST hazard (Zone 20/21/22 per IEC 60079-10-2)."
                    ),
                )
            )
        elif zone in _DUST_ZONES and hazard_type == HazardType.GAS:
            violations.append(
                AuditViolation(
                    gate="ZONE_MAPPING",
                    severity="CRITICAL",
                    code="ZMAP-002",
                    message=(
                        f"Zone {zone.value} is a DUST zone but hazard_type is GAS. "
                        f"Zones 20/21/22 are for combustible DUST. "
                        f"Did you mean Zone 0/1/2?"
                    ),
                    standard_ref="IEC 60079-10-1:2015 §1.3",
                    remediation=("Re-classify using correct zone type for GAS hazard (Zone 0/1/2 per IEC 60079-10-1)."),
                )
            )
        elif zone in _GAS_ZONES and hazard_type == HazardType.HYBRID:
            violations.append(
                AuditViolation(
                    gate="ZONE_MAPPING",
                    severity="WARNING",
                    code="ZMAP-003",
                    message=(
                        f"Zone {zone.value} is a gas zone but hazard_type is HYBRID "
                        f"(gas+dust). Ensure a separate dust zone analysis covers "
                        f"the dust component per IEC 60079-10-1 §5.3."
                    ),
                    standard_ref="IEC 60079-10-1:2015 §5.3",
                    remediation=(
                        "Perform separate dust zone classification per IEC 60079-10-2 and apply most severe zone."
                    ),
                )
            )
        elif zone in _DUST_ZONES and hazard_type == HazardType.HYBRID:
            violations.append(
                AuditViolation(
                    gate="ZONE_MAPPING",
                    severity="WARNING",
                    code="ZMAP-004",
                    message=(
                        f"Zone {zone.value} is a dust zone but hazard_type is HYBRID "
                        f"(gas+dust). Ensure a separate gas zone analysis covers "
                        f"the gas/vapour component per IEC 60079-10-1 §5.3."
                    ),
                    standard_ref="IEC 60079-10-1:2015 §5.3",
                    remediation=(
                        "Perform separate gas zone classification per IEC 60079-10-1 and apply most severe zone."
                    ),
                )
            )
        elif zone is None or hazard_type is None:
            # V48 FIX: Missing zone or hazard_type is a safety concern.
            # Previously silently passed — now emits a WARNING.
            violations.append(
                AuditViolation(
                    gate="ZONE_MAPPING",
                    severity="WARNING",
                    code="ZMAP-005",
                    message=(
                        f"Zone classification or hazard type not provided "
                        f"(zone={zone}, hazard_type={hazard_type}). "
                        f"Zone/hazard consistency cannot be verified. "
                        f"Provide both for complete safety audit."
                    ),
                    standard_ref="IEC 60079-10-1:2015 §1.3",
                    remediation=("Provide zone classification and hazard type to enable zone mapping verification."),
                )
            )
        else:
            passed_checks = 1

        return violations, total_checks, passed_checks

    # ── Gate 4: Elevation / Vapor Density ────────────────────────────

    def _check_z_axis(
        self,
        substance: Optional[SubstanceProperties],
        detector_z_positions: Optional[List[float]],
        ceiling_height_m: float,
    ) -> tuple:
        """Check detector elevation against gas buoyancy behavior.

        Gas buoyancy determines WHERE a gas accumulates, classified by
        density ratio (MW_gas / MW_air) using ±3% band:
          - Light gases (MW < 28.0912, ratio < 0.97) rise → detectors HIGH
          - Heavy gases (MW > 29.8288, ratio > 1.03) sink → detectors LOW
          - Near-air gases (28.0912 ≤ MW ≤ 29.8288) → BREATHING_ZONE OK

        Uses vapor_density_tier() for ratio-based classification.

        A detector at the wrong elevation for the gas is a physical
        blind spot — it may never see the gas cloud. This is a FATAL
        design flaw, not an advisory warning. The system MUST FAIL.

        Rationale for CRITICAL severity (not WARNING):
          - In SIL/IEC 61508 systems, a physical blind spot is a
            systematic failure that renders the safety function ineffective
          - If the gas cannot physically reach the detector, no amount
            of site-specific knowledge changes the physics
          - The engineer must explicitly document and justify any
            intentional deviation from the recommended elevation
        """
        violations: List[AuditViolation] = []
        total_checks = 0
        passed_checks = 0

        # FIX #4 (HIGH): When substance data is missing, we CANNOT silently
        # skip the Z-axis check — this masks a potentially fatal blind spot.
        # A missing substance means we cannot verify detector placement, which
        # is itself a WARNING condition requiring engineering review.
        if substance is None or substance.molecular_weight is None:
            total_checks = 1
            violations.append(
                AuditViolation(
                    gate="Z_AXIS",
                    severity="WARNING",
                    code="ZAX-002",
                    message=(
                        "Z-Axis elevation check CANNOT be performed — "
                        "substance molecular_weight is not available. "
                        "Detector placement against gas buoyancy behavior cannot "
                        "be verified. This may result in undetected gas accumulation "
                        "if detectors are at the wrong elevation for the substance."
                    ),
                    standard_ref="IEC 60079-10-1:2015 §B.4, NFPA 497 §4.5",
                    remediation=(
                        "Provide substance properties (at minimum molecular_weight) "
                        "to enable Z-axis elevation audit. Without this check, the "
                        "engineer must manually verify detector placement is correct "
                        "for the expected gas buoyancy behavior."
                    ),
                )
            )
            return violations, total_checks, passed_checks

        if not detector_z_positions:
            total_checks = 1
            violations.append(
                AuditViolation(
                    gate="Z_AXIS",
                    severity="WARNING",
                    code="ZAX-003",
                    message=(
                        "Z-Axis elevation check CANNOT be performed — "
                        "no detector Z-positions provided. Detector placement "
                        "against gas buoyancy behavior cannot be verified."
                    ),
                    standard_ref="IEC 60079-10-1:2015 §B.4, NFPA 497 §4.5",
                    remediation=(
                        "Provide detector Z-coordinates to enable Z-axis elevation "
                        "audit. Without this check, the engineer must manually verify "
                        "detector elevation is appropriate for the substance."
                    ),
                )
            )
            return violations, total_checks, passed_checks

        mw = substance.molecular_weight
        required_tier = vapor_density_tier(mw)

        for i, z in enumerate(detector_z_positions):
            total_checks += 1

            # MED-02 FIX: NaN z_position silently falls through to BREATHING_ZONE
            # in elevation_tier_from_detector_z(). A detector with unknown elevation
            # is NOT correctly placed — emit CRITICAL violation.
            if not isinstance(z, (int, float)) or not math.isfinite(z):
                violations.append(
                    AuditViolation(
                        gate="Z_AXIS",
                        severity="CRITICAL",
                        code="ZAX-004",
                        message=(
                            f"Detector #{i + 1} has NaN/Inf Z-position ({z!r}). "
                            f"Cannot verify detector elevation placement. "
                            f"NaN elevation silently defaults to BREATHING_ZONE tier, "
                            f"which may be incorrect for the substance. "
                            f"Detector placement audit is INVALID without valid Z-coordinates."
                        ),
                        standard_ref="IEC 60079-10-1:2015 §B.4, NFPA 497 §4.5",
                        remediation=(
                            "Provide valid Z-coordinate for this detector. "
                            "NaN/Inf elevation prevents verification of detector placement "
                            "against gas buoyancy behavior."
                        ),
                    )
                )
                continue

            detector_tier = elevation_tier_from_detector_z(z, ceiling_height_m)

            if detector_tier != required_tier:
                # Determine the mismatch description
                tier_names = {
                    ElevationTier.LOW: "floor level",
                    ElevationTier.BREATHING_ZONE: "breathing zone (1-2m)",
                    ElevationTier.HIGH: "ceiling level",
                }
                gas_behavior = {
                    ElevationTier.HIGH: "lighter than air — rises to ceiling",
                    ElevationTier.BREATHING_ZONE: "near air density — disperses in breathing zone",
                    ElevationTier.LOW: "heavier than air — pools at floor level",
                }
                violations.append(
                    AuditViolation(
                        gate="ELEVATION",
                        severity="CRITICAL",
                        code="ELEV-001",
                        message=(
                            f"ELEVATION MISMATCH: Detector #{i + 1} at z={z:.1f}m is at "
                            f"{tier_names[detector_tier]} ({detector_tier.value}), but "
                            f"{substance.name} (MW={mw:.2f} g/mol) is "
                            f"{gas_behavior[required_tier]}. This creates a physical "
                            f"blind spot — the gas cloud may never reach this detector. "
                            f"Expected tier: {required_tier.value}, Actual tier: {detector_tier.value}."
                        ),
                        standard_ref="IEC 60079-10-1:2015 §B.4, NFPA 497 §4.5, IEC 61508 §7.4",
                        remediation=(
                            f"Relocate detector to {tier_names[required_tier]} elevation "
                            f"for {substance.name}, or add an additional detector at the "
                            f"correct elevation. If current placement is intentional based "
                            f"on site-specific conditions (ventilation, mixing), document "
                            f"the engineering rationale and perform a formal risk assessment."
                        ),
                    )
                )
            else:
                passed_checks += 1

        return violations, total_checks, passed_checks

    # ── Gate 5: MENA Region ───────────────────────────────────────────

    def _check_mena(
        self,
        zone: ZoneType,
        env_context: EnvironmentalContext,
    ) -> tuple:
        """Check MENA region-specific advisory rules.

        These are advisory (WARNING/INFO) — NOT forced. The engineer
        always has the final say. The audit merely highlights conditions
        that may need attention in MENA environments.
        """
        violations: List[AuditViolation] = []
        total_checks = 0
        passed_checks = 0

        if env_context.region not in (
            RegionProfile.MENA_SUMMER_OUTDOOR,
            RegionProfile.GULF_HCIS,
            RegionProfile.EGYPT_CODE,
        ):
            return violations, total_checks, passed_checks

        # Check 5a: Ambient temperature advisory
        # Threshold varies by region: GCC 50C, Egypt 45C
        _REGION_TEMP_THRESHOLD = {
            RegionProfile.MENA_SUMMER_OUTDOOR: 50.0,
            RegionProfile.GULF_HCIS: 50.0,
            RegionProfile.EGYPT_CODE: 45.0,
        }
        temp_threshold = _REGION_TEMP_THRESHOLD.get(env_context.region, 50.0)

        total_checks += 1
        if env_context.ambient_temp_c < temp_threshold:
            violations.append(
                AuditViolation(
                    gate="MENA",
                    severity="INFO",
                    code="MENA-001",
                    message=(
                        f"{env_context.region.value} region selected but ambient temperature "
                        f"is {env_context.ambient_temp_c:.1f}C (below typical summer "
                        f"peak of {temp_threshold:.0f}C). If this is an outdoor installation, "
                        f"verify the ambient temperature assumption. Burgess-Wheeler "
                        f"LFL correction at higher temperatures will produce wider "
                        f"zone extents."
                    ),
                    standard_ref="IEC 60079-10-1:2015 Annex B, Burgess-Wheeler",
                    remediation=(
                        f"Verify ambient temperature against site meteorological data. "
                        f"Summer design temperature is typically {temp_threshold:.0f}C+ outdoor "
                        f"for this region. If actual temperature is higher, re-run HAC classification."
                    ),
                )
            )
        else:
            passed_checks += 1

        # Check 5b: Sandstorm fouling advisory
        # Applies to MENA/GULF regions with desert sandstorm conditions
        total_checks += 1
        _DESERT_REGIONS = (RegionProfile.MENA_SUMMER_OUTDOOR, RegionProfile.GULF_HCIS)
        if env_context.region in _DESERT_REGIONS and env_context.lens_fouling_factor > 0.60:
            violations.append(
                AuditViolation(
                    gate="MENA",
                    severity="WARNING",
                    code="MENA-002",
                    message=(
                        f"{env_context.region.value} region with fouling factor "
                        f"{env_context.lens_fouling_factor:.2f}. GCC desert "
                        f"sandstorms can reduce fouling to 0.45-0.55 for outdoor "
                        f"detectors without scheduled cleaning. Current fouling "
                        f"assumption may be optimistic for this environment."
                    ),
                    standard_ref="FM Global DS 5-48 §3.2.1",
                    remediation=(
                        "Consider reducing lens_fouling_factor to 0.55 or lower "
                        "for outdoor MENA installations. Implement weekly lens "
                        "cleaning schedule. Consider detector shielding or purged "
                        "enclosures."
                    ),
                )
            )
        else:
            passed_checks += 1

        # Check 5c: HCIS jurisdiction-specific check
        # V48 FIX: When zone is None, emit WARNING for Saudi HCIS —
        # unclassified zone may still require 1oo2 per HCIS directive.
        if env_context.jurisdiction == Jurisdiction.SAUDI_HCIS:
            total_checks += 1
            if zone in (ZoneType.ZONE_2, ZoneType.ZONE_22):
                zone_label = zone.value if zone is not None else "UNCLASSIFIED"
                violations.append(
                    AuditViolation(
                        gate="MENA",
                        severity="WARNING",
                        code="MENA-003",
                        message=(
                            f"SAUDI_HCIS jurisdiction with {zone_label}: HCIS SAF "
                            f"Directive 2021 §4.3 requires minimum 1oo2 voting "
                            f"architecture for flame detectors in Zone 2/22 critical "
                            f"process installations. IEC base standard allows single "
                            f"detector. Verify if this installation qualifies as "
                            f"'critical process' per HCIS definition."
                        ),
                        standard_ref="HCIS SAF Directive 2021 §4.3",
                        remediation=(
                            "If installation is classified as critical process, "
                            "add second independent detector for 1oo2 voting. "
                            "If non-critical, document the classification rationale."
                        ),
                    )
                )
            elif zone is None:
                # V48: Unknown zone in Saudi HCIS — assume Zone 2/22 requirements may apply
                violations.append(
                    AuditViolation(
                        gate="MENA",
                        severity="WARNING",
                        code="MENA-004",
                        message=(
                            "SAUDI_HCIS jurisdiction but zone classification is missing. "
                            "HCIS SAF Directive 2021 §4.3 requires minimum 1oo2 voting "
                            "for Zone 2/22 critical process installations. Cannot verify "
                            "compliance without zone classification."
                        ),
                        standard_ref="HCIS SAF Directive 2021 §4.3",
                        remediation="Provide zone classification to enable MENA compliance check.",
                    )
                )
            else:
                passed_checks += 1

        return violations, total_checks, passed_checks
