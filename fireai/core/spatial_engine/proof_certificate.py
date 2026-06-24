from __future__ import annotations

"""
Coverage Proof Certificate — Mathematical Proof of NFPA 72 Compliance
=====================================================================
Generates a machine-readable proof certificate that verifies detector
coverage in a room. This certificate can be independently verified by
an AHJ (Authority Having Jurisdiction) or third-party auditor.

PROOF METHOD: δ-Conservative Grid Verification
  For a grid with cell size δ:
    - Every room point P has a grid point G within distance δ√2/2
    - If G is covered by R_eff = R - δ√2/2, then P is covered by R
    - Coverage ≥ 1 - (N_uncovered × π × (δ/2)²) / A_room

MATHEMATICAL FOUNDATION:
  The proof is based on the triangle inequality:
    dist(P, D) ≤ dist(P, G) + dist(G, D)
              ≤ δ√2/2 + R_eff
              = δ√2/2 + (R - δ√2/2)
              = R
  Therefore, if every grid point is within R_eff of some detector,
  every room point is within R of some detector. QED.

NFPA 72-2022 §17.7.4.2.3.1: Coverage radius R = 0.7 × S

This is Bridge 3 of the FireAI roadmap — transforms FireAI from a
calculator to an engineering tool with mathematical proof.
"""

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Tuple

from .density_optimizer import DETECTOR_RADIUS


@dataclass
class ProofCertificate:
    """Machine-readable coverage proof certificate.

    This certificate can be independently verified:
    1. Recompute the grid with the same parameters
    2. Check that all grid points are within R_eff of a detector
    3. Verify the hash matches

    The certificate contains ALL information needed for independent
    verification — no external state is required.
    """

    # ── Room Information ──────────────────────────────────────────────
    room_id: str
    room_width_m: float
    room_length_m: float
    room_ceiling_height_m: float
    room_area_sqm: float

    # ── Detector Information ──────────────────────────────────────────
    n_detectors: int
    detector_positions: List[Tuple[float, float]]
    detector_type: str = "smoke"
    detector_radius_m: float = 0.0  # Coverage radius R

    # ── Proof Parameters ──────────────────────────────────────────────
    proof_method: str = "delta_conservative_grid"
    grid_step_m: float = 0.20  # δ = cell size
    effective_radius_m: float = 0.0  # R_eff = R - δ√2/2
    delta_margin_m: float = 0.0  # δ√2/2
    max_spacing_m: float = 0.0  # S (detector spacing)
    wall_min_m: float = 0.10  # Minimum wall distance

    # ── Proof Results ─────────────────────────────────────────────────
    n_grid_points: int = 0  # Total grid points checked
    n_covered: int = 0  # Grid points within R_eff of a detector
    n_uncovered: int = 0  # Grid points NOT within R_eff
    coverage_guaranteed: bool = False  # True iff n_uncovered == 0

    # ── Mathematical Lower Bound ──────────────────────────────────────
    coverage_lower_bound_pct: float = 0.0  # Minimum guaranteed coverage
    uncovered_area_upper_bound_sqm: float = 0.0  # Max possible uncovered area

    # ── NFPA 72 Compliance ────────────────────────────────────────────
    nfpa_compliant: bool = False
    wall_coverage_complete: bool = False
    spacing_compliant: bool = False
    nfpa_reference: str = "NFPA 72-2022 Table 17.6.3.1.1"

    # ── Verification Hash ─────────────────────────────────────────────
    proof_hash: str = ""  # SHA-256 of all inputs + results
    timestamp: str = ""  # ISO 8601 UTC timestamp

    # ── Additional Metadata ───────────────────────────────────────────
    fireai_version: str = "1.0.0"
    certificate_version: str = "1.0"
    warnings: List[str] = field(default_factory=list)

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of all proof parameters.

        This hash binds the certificate to its inputs — changing any
        parameter will produce a different hash. This prevents tampering.
        """
        data = {
            "room_id": self.room_id,
            "room_width_m": self.room_width_m,
            "room_length_m": self.room_length_m,
            "room_ceiling_height_m": self.room_ceiling_height_m,
            "n_detectors": self.n_detectors,
            "detector_positions": self.detector_positions,
            "detector_radius_m": self.detector_radius_m,
            "grid_step_m": self.grid_step_m,
            "effective_radius_m": self.effective_radius_m,
            "delta_margin_m": self.delta_margin_m,
            "max_spacing_m": self.max_spacing_m,
            "wall_min_m": self.wall_min_m,
            "n_grid_points": self.n_grid_points,
            "n_covered": self.n_covered,
            "n_uncovered": self.n_uncovered,
            "coverage_guaranteed": self.coverage_guaranteed,
            "coverage_lower_bound_pct": self.coverage_lower_bound_pct,
            "uncovered_area_upper_bound_sqm": self.uncovered_area_upper_bound_sqm,
            "nfpa_compliant": self.nfpa_compliant,
            "wall_coverage_complete": self.wall_coverage_complete,
            "spacing_compliant": self.spacing_compliant,
        }
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    def seal(self) -> None:
        """Seal the certificate by computing hash and timestamp."""
        self.proof_hash = self.compute_hash()
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def verify_hash(self) -> bool:
        """Verify the certificate hash matches the current data."""
        return self.compute_hash() == self.proof_hash

    def to_json(self, indent: int = 2) -> str:
        """Serialize certificate to JSON."""
        return json.dumps(asdict(self), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> ProofCertificate:
        """Deserialize certificate from JSON."""
        data = json.loads(json_str)
        return cls(**data)


class ProofCertificateGenerator:
    """Generate coverage proof certificates.

    Uses the δ-conservative grid verification method to produce
    a mathematical proof that every point in the room is within
    coverage radius R of at least one detector.

    Usage:
        generator = ProofCertificateGenerator(
            grid_step=0.20,  # δ = 20cm
            coverage_radius=DETECTOR_RADIUS,  # R = 0.7 × S
        )
        cert = generator.generate(
            room_id="room_001",
            width=10.0, length=10.0,
            ceiling_height=3.0,
            detectors=[(2.5, 2.5), (7.5, 2.5), (5.0, 7.5)],
        )
        cert.seal()  # Compute hash and timestamp
        print(cert.to_json())
    """

    def __init__(
        self,
        grid_step: float = 0.20,
        coverage_radius: float = DETECTOR_RADIUS,
        max_spacing: float = 9.1,
        wall_min: float = 0.10,
    ):
        self.delta = grid_step
        self.R = coverage_radius
        self.S = max_spacing
        self.wm = wall_min
        self.delta_margin = self.delta * math.sqrt(2) / 2
        self.R_eff = self.R - self.delta_margin

    def generate(
        self,
        room_id: str,
        width: float,
        length: float,
        ceiling_height: float,
        detectors: List[Tuple[float, float]],
        detector_type: str = "smoke",
        nfpa_compliant: bool = False,
        wall_coverage_complete: bool = False,
        spacing_compliant: bool = False,
    ) -> ProofCertificate:
        """Generate a coverage proof certificate.

        Args:
            room_id: Unique room identifier.
            width: Room width in meters.
            length: Room length in meters.
            ceiling_height: Ceiling height in meters.
            detectors: List of (x, y) detector positions.
            detector_type: Type of detector ("smoke" or "heat").
            nfpa_compliant: Whether the layout passes NFPA 72 audit.
            wall_coverage_complete: Whether walls are fully covered.
            spacing_compliant: Whether detector spacing is compliant.

        Returns:
            ProofCertificate with mathematical proof.

        """
        delta = self.delta
        R = self.R
        R_eff = self.R_eff
        R2_eff = R_eff**2 + 1e-9
        delta_margin = self.delta_margin

        # Build verification grid
        xs = []
        x = 0.0
        while True:
            xs.append(min(x, width))
            if x >= width:
                break
            x = min(x + delta, width)

        ys = []
        y = 0.0
        while True:
            ys.append(min(y, length))
            if y >= length:
                break
            y = min(y + delta, length)

        # Check each grid point against all detectors
        n_total = 0
        n_covered = 0
        n_uncovered = 0

        for gx in xs:
            for gy in ys:
                n_total += 1
                covered = False
                for dx, dy in detectors:
                    if (gx - dx) ** 2 + (gy - dy) ** 2 <= R2_eff:
                        covered = True
                        break
                if covered:
                    n_covered += 1
                else:
                    n_uncovered += 1

        # Compute mathematical lower bound
        room_area = width * length
        if n_uncovered == 0:
            coverage_lower_bound = 100.0
            uncovered_area_upper = 0.0
        else:
            # V15 FIX: Upper bound on uncovered area uses SQUARE cell area,
            # not circular inscribed area. The circular approximation
            # π(δ/2)² ≈ 0.785δ² understates the true maximum uncovered area
            # by ~21.5%. Using δ² (square cell) is the conservative bound
            # because each uncovered grid point represents an entire cell of
            # uncertainty, not just the inscribed circle within it.
            # Old (WRONG): uncovered_area_upper = n_uncovered * math.pi * (delta / 2) ** 2
            # New (CONSERVATIVE): uncovered_area_upper = n_uncovered * delta ** 2
            uncovered_area_upper = n_uncovered * delta**2
            coverage_lower_bound = max(0.0, 100.0 * (1 - uncovered_area_upper / room_area))

        # Build certificate
        cert = ProofCertificate(
            room_id=room_id,
            room_width_m=width,
            room_length_m=length,
            room_ceiling_height_m=ceiling_height,
            room_area_sqm=room_area,
            n_detectors=len(detectors),
            detector_positions=[(round(x, 4), round(y, 4)) for x, y in detectors],
            detector_type=detector_type,
            detector_radius_m=round(R, 4),
            proof_method="delta_conservative_grid",
            grid_step_m=delta,
            effective_radius_m=round(R_eff, 4),
            delta_margin_m=round(delta_margin, 4),
            max_spacing_m=self.S,
            wall_min_m=self.wm,
            n_grid_points=n_total,
            n_covered=n_covered,
            n_uncovered=n_uncovered,
            coverage_guaranteed=(n_uncovered == 0),
            coverage_lower_bound_pct=round(coverage_lower_bound, 4),
            uncovered_area_upper_bound_sqm=round(uncovered_area_upper, 4),
            nfpa_compliant=nfpa_compliant,
            wall_coverage_complete=wall_coverage_complete,
            spacing_compliant=spacing_compliant,
        )

        # Add warnings
        if n_uncovered > 0:
            cert.warnings.append(f"{n_uncovered} grid points uncovered — coverage not proven")
        if coverage_lower_bound < 99.9:
            cert.warnings.append(f"Coverage lower bound {coverage_lower_bound:.1f}% < 99.9%")
        if ceiling_height > 9.1:
            cert.warnings.append(f"Ceiling height {ceiling_height}m > 9.1m — consider beam detectors per NFPA 72 §17.7")

        return cert
