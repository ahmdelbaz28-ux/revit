"""
decision_provenance.py — Layer 3 of the V8 Trust Stack
=======================================================
Every public engineering function returns a DecisionProvenance object.
A bare scalar or coordinate tuple is FORBIDDEN by CI lint.

This object is the legally-defensible artifact. It must contain:
  - what was decided (value)
  - which inputs produced it (drawing hash, jurisdiction, code editions)
  - which rules were applied (citations + values used)
  - which algorithm + parameters + seed
  - alternatives considered
  - violations + warnings
  - confidence (decomposed)
  - who must review (always: a licensed PE)
  - an engine signature (proves the output came from this engine version)

The renderer MUST surface confidence.overall, requires_review_by, and the
violations count. This is enforced by linter_rules.py.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    REFUSE = "REFUSE"   # confidence so low that no answer is returned


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    OVERRIDDEN = "overridden"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RuleApplied:
    citation: str           # e.g. "NFPA72-2019 §17.6.3.1"
    constant_id: str
    value_used: float
    unit: str


@dataclass(frozen=True)
class Alternative:
    rank: int
    value: Any
    cost: float
    safety_margin: float
    why_not_selected: str


@dataclass(frozen=True)
class Violation:
    severity: str           # "ERROR" | "WARNING"
    citation: str
    description: str
    location: Optional[Any] = None


@dataclass(frozen=True)
class ConfidenceScore:
    input_quality_score: float        # 0..1 — PDF/DWG cleanness
    rule_coverage: float              # 0..1 — fraction of needed rules with FPE-signed constants
    geometry_certainty: float         # 0..1 — topology IoU vs heuristic
    overall: ConfidenceLevel

    def __post_init__(self):
        for f in ("input_quality_score", "rule_coverage", "geometry_certainty"):
            v = getattr(self, f)
            if not (0.0 <= float(v) <= 1.0):
                raise ValueError(f"{f} must be in [0,1], got {v}")


@dataclass
class DecisionProvenance:
    decision_id: str
    decision_type: str
    value: Any
    inputs: dict
    rules_applied: list
    algorithm: dict
    feasible_alternatives_considered: int
    selected_because: str
    alternatives_top_3: list
    warnings: list
    violations_detected: list
    confidence: ConfidenceScore
    requires_review_by: str = "Licensed PE or FPE"
    review_status: ReviewStatus = ReviewStatus.PENDING
    produced_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    engine_version: str = "v8.0.0"
    signature_engine: Optional[str] = None

    # ------------------ factory ------------------

    @staticmethod
    def new(decision_type: str,
            value: Any,
            inputs: dict,
            rules_applied: list[RuleApplied],
            algorithm: dict,
            confidence: ConfidenceScore,
            selected_because: str,
            alternatives_top_3: Optional[list[Alternative]] = None,
            feasible_alternatives_considered: int = 0,
            warnings: Optional[list[str]] = None,
            violations: Optional[list[Violation]] = None) -> "DecisionProvenance":
        return DecisionProvenance(
            decision_id=str(uuid.uuid4()),
            decision_type=decision_type,
            value=value,
            inputs=inputs,
            rules_applied=[asdict(r) for r in rules_applied],
            algorithm=algorithm,
            feasible_alternatives_considered=feasible_alternatives_considered,
            selected_because=selected_because,
            alternatives_top_3=[asdict(a) for a in (alternatives_top_3 or [])],
            warnings=list(warnings or []),
            violations_detected=[asdict(v) for v in (violations or [])],
            confidence=confidence,
        )

    # ------------------ serialization ------------------

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence"]["overall"] = self.confidence.overall.value
        d["review_status"] = self.review_status.value
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True, default=str)

    # ------------------ validation ------------------

    def validate(self) -> None:
        """Hard contract: every required field present and well-formed."""
        if not self.decision_id:
            raise ValueError("decision_id missing")
        if not self.decision_type:
            raise ValueError("decision_type missing")
        if self.requires_review_by not in {"Licensed PE or FPE", "Licensed PE", "FPE"}:
            raise ValueError("requires_review_by must name a licensed reviewer")
        if not self.rules_applied and not self.violations_detected:
            raise ValueError(
                "A decision with no rules applied and no violations is "
                "indistinguishable from a guess. Refuse to emit."
            )
        # Confidence
        if self.confidence.overall == ConfidenceLevel.REFUSE and self.value is not None:
            raise ValueError(
                "Confidence=REFUSE but value provided. Refuse to emit a value."
            )

    # ------------------ engine signature ------------------

    def _canonical_payload(self) -> bytes:
        d = self.to_dict()
        d.pop("signature_engine", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    def sign_engine(self, key: Optional[bytes] = None) -> None:
        key = key or _engine_key()
        self.signature_engine = hmac.new(key, self._canonical_payload(), hashlib.sha256).hexdigest()

    def verify_engine_signature(self, key: Optional[bytes] = None) -> bool:
        if not self.signature_engine:
            return False
        key = key or _engine_key()
        expected = hmac.new(key, self._canonical_payload(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature_engine)


def _engine_key() -> bytes:
    env = os.environ.get("FIRECALC_ENGINE_KEY")
    if env:
        return env.encode("utf-8")
    # DEV ONLY
    return hashlib.sha256(b"FIRECALC_ENGINE_DEV_KEY").digest()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    rule = RuleApplied(
        citation="NFPA72-2019 §17.6.3.1",
        constant_id="NFPA72.17.6.3.1.smoke_max_spacing",
        value_used=9.1, unit="m",
    )
    conf = ConfidenceScore(
        input_quality_score=0.92, rule_coverage=1.0,
        geometry_certainty=0.88, overall=ConfidenceLevel.HIGH,
    )
    dp = DecisionProvenance.new(
        decision_type="panel_placement",
        value={"panels": [(10.0, 5.0)]},
        inputs={"drawing_hash": "sha256:ab12", "jurisdiction": "US.GENERIC",
                "code_versions": {"NFPA72": "2019"}},
        rules_applied=[rule],
        algorithm={"name": "k_median", "version": "v8.0.0",
                   "parameters": {"k": 1, "seed": "hash-derived"}},
        confidence=conf,
        selected_because="single feasible solution within safety margin 15%",
        feasible_alternatives_considered=1,
    )
    dp.validate()
    dp.sign_engine()
    assert dp.verify_engine_signature(), "engine signature failed"
    print("[decision_provenance] PASS")
    print(dp.to_json())
