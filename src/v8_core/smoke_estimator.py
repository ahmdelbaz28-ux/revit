"""
smoke_estimator.py — Pre-Screening Estimator (NOT a simulation)
================================================================
REPLACES the V7.6 `smoke_simulator.py`, which claimed NFPA 92 compliance
on a single-zone analytical approximation. That claim was unsupportable
and is removed.

DESIGN INVARIANTS (any violation is a CI failure):
  1. This module is a LEAF NODE in the dependency graph. No other engine
     module may import its output for downstream decisions.
  2. Output always includes the locked disclaimer. The disclaimer is not
     editable, not optional, and not removable by the renderer.
  3. The class name, module name, and output schema all contain the word
     "estimator" or "pre-screening" — never "simulator" or "NFPA 92".
  4. The error band is hardcoded to ±50% and is part of every result.

If you need real performance-based smoke modeling, use a validated CFD
tool (e.g. NIST FDS) operated by a qualified fire modeler. This is not
that tool and will not become that tool.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .decision_provenance import (
    ConfidenceLevel, ConfidenceScore, DecisionProvenance,
    RuleApplied, Violation,
)


LOCKED_DISCLAIMER = (
    "PRE-SCREENING ESTIMATE ONLY — NOT A SIMULATION. "
    "This number is a single-zone analytical approximation with an "
    "estimated error band of ±50%. It is not validated against CFD or "
    "experimental data. It must not be used for performance-based design, "
    "code compliance, or any decision affecting human safety. For "
    "performance-based design, a validated CFD model (e.g. NIST FDS) "
    "operated by a qualified fire modeler is required."
)


@dataclass(frozen=True)
class EstimatorInputs:
    volume_m3: float
    ceiling_height_m: float
    detector_height_m: float
    fire_heat_release_kw: float = 500.0   # default t-squared "medium" fire growth at 60s
    growth_coefficient: float = 0.0117    # NFPA 92 medium-growth alpha (s^-2 kW); reference only

    def validate(self) -> Optional[Violation]:
        if self.volume_m3 <= 0 or self.ceiling_height_m <= 0:
            return Violation("ERROR", "internal",
                             "Volume and ceiling height must be positive.", None)
        if self.detector_height_m >= self.ceiling_height_m:
            return Violation("ERROR", "internal",
                             "Detector height must be below ceiling height.", None)
        if self.fire_heat_release_kw <= 0:
            return Violation("ERROR", "internal",
                             "Heat release rate must be positive.", None)
        return None


class ZoneSmokeEstimator:
    """
    Highly simplified two-region 'estimator' (NOT a simulator).
    Computes a rough zone-fill time from inputs using crude conservation,
    then wraps the result in a fixed ±50% band and a non-removable disclaimer.

    The math here is intentionally simple and NOT representative of NFPA 92
    or any validated correlation. The output exists ONLY to give a PE a
    coarse 'is this the right order of magnitude' sanity check before
    commissioning a real CFD study.
    """
    ERROR_BAND = 0.50  # ±50%
    VERSION = "v8.0.0"

    def estimate(self, inputs: EstimatorInputs,
                 drawing_hash: str = "sha256:unknown") -> DecisionProvenance:
        v = inputs.validate()
        if v:
            return self._refusal(inputs, drawing_hash, v)

        # Crude zone-fill model: descent rate proportional to (Q^(1/3)) / area.
        # NOT a validated correlation. Used only to produce an order-of-magnitude estimate.
        area = inputs.volume_m3 / inputs.ceiling_height_m
        plume_proxy = (inputs.fire_heat_release_kw ** (1.0 / 3.0))
        descent_rate_m_per_s = max(plume_proxy / max(area, 1.0) * 0.05, 1e-6)
        layer_depth_to_detector = max(inputs.ceiling_height_m - inputs.detector_height_m, 0.01)
        est_time_s = layer_depth_to_detector / descent_rate_m_per_s

        lower = est_time_s * (1.0 - self.ERROR_BAND)
        upper = est_time_s * (1.0 + self.ERROR_BAND)

        # Confidence is permanently capped at MEDIUM for this module.
        confidence = ConfidenceScore(
            input_quality_score=0.7, rule_coverage=0.0,
            geometry_certainty=0.5, overall=ConfidenceLevel.MEDIUM,
        )
        # rule_coverage = 0 because we do NOT claim to apply NFPA 92.

        value = {
            "estimated_zone_fill_time_s": round(est_time_s, 2),
            "error_band_low_s": round(lower, 2),
            "error_band_high_s": round(upper, 2),
            "error_band_pct": int(self.ERROR_BAND * 100),
            "method": "single-zone analytical approximation",
            "claims_nfpa92": False,
            "validated_against_cfd": False,
            "disclaimer": LOCKED_DISCLAIMER,
        }

        dp = DecisionProvenance.new(
            decision_type="smoke_pre_screening_estimate",
            value=value,
            inputs={"drawing_hash": drawing_hash,
                    "volume_m3": inputs.volume_m3,
                    "ceiling_height_m": inputs.ceiling_height_m,
                    "detector_height_m": inputs.detector_height_m,
                    "fire_heat_release_kw": inputs.fire_heat_release_kw,
                    "jurisdiction": None,
                    "code_versions": {}},
            rules_applied=[RuleApplied(
                citation="(no NFPA 92 claim) — pre-screen only",
                constant_id="FIRECALC.smoke_estimator.disclaimer",
                value_used=self.ERROR_BAND, unit="ratio")],
            algorithm={"name": "zone_descent_proxy",
                       "version": self.VERSION,
                       "parameters": {
                           "deterministic": True,
                           "notes": "NOT validated. NOT NFPA 92."}},
            confidence=confidence,
            selected_because="Pre-screening estimate for order-of-magnitude check.",
            warnings=[
                "This output is NOT for performance-based design.",
                "Error band is ±50%.",
                "Engage NIST FDS or equivalent for any compliance-bearing analysis.",
            ],
        )
        dp.validate()
        dp.sign_engine()
        return dp

    def _refusal(self, inputs, drawing_hash, violation):
        confidence = ConfidenceScore(0.0, 0.0, 0.0, ConfidenceLevel.REFUSE)
        dp = DecisionProvenance.new(
            decision_type="smoke_pre_screening_estimate",
            value=None,
            inputs={"drawing_hash": drawing_hash},
            rules_applied=[RuleApplied(
                citation="(input validation)",
                constant_id="FIRECALC.smoke_estimator.input_check",
                value_used=0.0, unit="bool")],
            algorithm={"name": "input_validation", "version": self.VERSION,
                       "parameters": {}},
            confidence=confidence,
            selected_because="Input validation failed; estimator refused to run.",
            violations=[violation],
        )
        dp.validate()
        dp.sign_engine()
        return dp


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    est = ZoneSmokeEstimator()
    inp = EstimatorInputs(volume_m3=300.0, ceiling_height_m=4.0,
                          detector_height_m=3.8, fire_heat_release_kw=500.0)
    dp = est.estimate(inp, drawing_hash="sha256:demo")
    v = dp.value
    assert v["claims_nfpa92"] is False
    assert v["validated_against_cfd"] is False
    assert v["error_band_pct"] == 50
    assert "PRE-SCREENING ESTIMATE ONLY" in v["disclaimer"]
    print(f"[smoke_estimator] PASS — t≈{v['estimated_zone_fill_time_s']}s "
          f"(±50%: {v['error_band_low_s']}..{v['error_band_high_s']}s)")
    print(f"[smoke_estimator] disclaimer locked.")
