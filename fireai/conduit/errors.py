"""fireai.conduit.errors — Error Types for Conduit Fitting Engine
==============================================================

Every error includes:
  - code_reference: NEC/NFPA article number
  - remediation:    Actionable fix guidance
  - severity:       FATAL (abort) or WARNING (log and continue)

SAFETY: In a life-safety system, ambiguous errors are always FATAL.
Only conditions that are provably safe to continue past are WARNING.

Reference: NFPA 72-2022 §10.6, NEC 2022 Chapter 9
"""

from __future__ import annotations

import enum


class Severity(enum.Enum):
    """Error severity classification."""

    FATAL   = "FATAL"    # Abort — calculation result cannot be trusted
    WARNING = "WARNING"  # Log and continue — result is still usable


class ConduitError(Exception):
    """Base class for all conduit engine errors.

    Never use bare except. Always catch ConduitError or a specific subclass.

    Attributes:
        message:        Human-readable error description.
        code_reference: NEC/NFPA article citation.
        remediation:    Actionable guidance to resolve.
        severity:       FATAL or WARNING.

    """

    def __init__(
        self,
        message: str,
        code_reference: str,
        remediation: str,
        severity: Severity = Severity.FATAL,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code_reference = code_reference
        self.remediation = remediation
        self.severity = severity

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"severity={self.severity.value!r}, "
            f"ref={self.code_reference!r}, "
            f"msg={self.message!r})"
        )

    def __str__(self) -> str:
        return (
            f"[{self.severity.value}] {type(self).__name__}: {self.message}\n"
            f"  Code Reference: {self.code_reference}\n"
            f"  Remediation: {self.remediation}"
        )


class PhysicsError(ConduitError):
    """Physically impossible input detected.

    Raised when input values violate physical laws:
      - Negative length, radius, or diameter
      - NaN or Inf coordinate values
      - Zero conduit area
      - Negative cable count

    These indicate data corruption or programmer error, NOT user error.
    Always FATAL — no safe result can be produced.

    Reference: First principles — no NEC article; physics precedes code.
    """

    def __init__(self, message: str, remediation: str) -> None:
        super().__init__(
            message=message,
            code_reference="PHYSICS — precedes NEC",
            remediation=remediation,
            severity=Severity.FATAL,
        )


class CodeViolationError(ConduitError):
    """Input or result exceeds NEC/NFPA limit.

    Raised when a computed value violates a specific code requirement:
      - Conduit fill exceeds NEC Chapter 9, Table 1 limit
      - Bend radius below NEC 358.24 / 352.24 / 344.24 minimum
      - Cumulative bend degrees exceed 360° (NEC 358.26)
      - Conduit not listed for the installation location

    Severity: FATAL for construction-blocking violations.
              WARNING for advisories (e.g. fill > 35% but < 40%).

    Reference: NEC 2022 — specific article cited per instance.
    """

    def __init__(
        self,
        message: str,
        code_reference: str,
        remediation: str,
        severity: Severity = Severity.FATAL,
    ) -> None:
        super().__init__(
            message=message,
            code_reference=code_reference,
            remediation=remediation,
            severity=severity,
        )


class CatalogError(ConduitError):
    """Requested fitting not found in the catalog.

    Raised when a (conduit_type, trade_size, fitting_type) combination
    does not exist in the immutable fitting catalog. This typically
    indicates a design error — the engineer specified a non-standard or
    unsupported combination.

    Reference: Project fitting catalog (derived from manufacturer data).
               NEC 110.3(B) — equipment must be installed per listing.
    """

    def __init__(
        self,
        conduit_type: str,
        trade_size: str,
        fitting_type: str,
        remediation: str = (
            "Verify the conduit type and trade size are supported. "
            "Consult the fitting catalog or substitute an equivalent listed fitting."
        ),
    ) -> None:
        super().__init__(
            message=(
                f"No catalog entry for {fitting_type} in "
                f"{conduit_type} {trade_size}. "
                "This combination is not stocked or not listed."
            ),
            code_reference="NEC 110.3(B) — use only listed equipment",
            remediation=remediation,
            severity=Severity.FATAL,
        )


class RoutingError(ConduitError):
    """No valid conduit path exists between two points.

    Raised when the A* router cannot find a path that satisfies all
    constraints (obstacle clearance, bend limits, physical space).

    Reference: NFPA 72-2022 §12.2.2 — conduit routing requirements.
               NEC 300.4 — protection from physical damage.
    """

    def __init__(
        self,
        start: str,
        end: str,
        reason: str,
        remediation: str = (
            "Review the obstacle map and routing constraints. "
            "Consider adding a pull box, adjusting the grid resolution, "
            "or relocating the start/end points."
        ),
    ) -> None:
        super().__init__(
            message=(
                f"No valid route from {start} to {end}. "
                f"Reason: {reason}"
            ),
            code_reference=(
                "NFPA 72-2022 §12.2.2 / NEC 300.4"
            ),
            remediation=remediation,
            severity=Severity.FATAL,
        )
