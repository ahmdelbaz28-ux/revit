"""fireai/core/submittal_integrity_gate.py
=======================================
Post-draft SHA-256 hash verification for the DXF compilation pipeline.

TOCTOU (Time-of-Check Time-of-Use) Vulnerability — CWE-367
----------------------------------------------------------
Between reading a CAD source file and producing the final submittal drawing,
the source file could be modified by a concurrent process, a user edit, or
a malicious actor. The existing parser_safe.py (src/v8_core/) protects files
DURING parsing with hash re-validation and file locking. However, the DXF
compilation pipeline does not verify that the final drawing hash matches the
calculation hash — a classic TOCTOU gap.

If a building floor plan is modified between the coverage calculation and the
final submittal output, the fire alarm design may be based on outdated building
geometry. This could result in:
  - Missing detectors in newly-added rooms
  - Incorrect spacing for resized corridors
  - Non-compliant device placement per NFPA 72

This module provides the final gate check: it records the SHA-256 hash of
the source file at the pre-calculation phase, then verifies it again at the
post-draft and final-submittal phases. Any mismatch triggers a CRITICAL
violation that blocks the submittal.

References:
    - CWE-367: Time-of-Check Time-of-Use Race Condition
      https://cwe.mitre.org/data/definitions/367.html
    - NFPA 72-2022 Documentation Integrity requirements
      (design documents must reflect the as-built conditions)

Usage:
    gate = SubmittalIntegrityGate()

    # Phase 1: Record hash before calculation
    pre = gate.record_hash("building.dxf", "pre_calculation")

    # ... perform coverage calculation, generate submittal ...

    # Phase 2: Verify integrity before final submittal
    result = gate.verify_integrity("building.dxf", pre.sha256_hex)
    if not result.match:
        # REJECT submittal — source was modified
        raise RuntimeError(result.violations[0]["description"])

"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Provenance imports — same pattern as other fireai.core modules
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

_CITE_CWE367 = "CWE-367: Time-of-Check Time-of-Use Race Condition"
_CITE_NFPA72_INTEGRITY = "NFPA 72-2022 Documentation Integrity"

_SHA256_CHUNK_SIZE = 8192  # 8 KB read buffer — matches parser_safe.py


# ============================================================================
# Data classes
# ============================================================================


@dataclass(frozen=True)
class HashRecord:
    """Immutable record of a file's SHA-256 hash at a specific pipeline phase.

    Attributes:
        file_path: Absolute or relative path to the file that was hashed.
        sha256_hex: 64-character lowercase hex SHA-256 digest.
        recorded_at_epoch_ms: Unix epoch in milliseconds when the hash was
            computed.
        phase: Pipeline phase — one of "pre_calculation", "post_draft",
            "final_submittal".

    """

    file_path: str
    sha256_hex: str
    recorded_at_epoch_ms: float
    phase: str  # "pre_calculation", "post_draft", "final_submittal"


@dataclass
class IntegrityCheckResult:
    """Result of comparing pre-calculation and post-draft hashes.

    Attributes:
        source_file: Path of the file that was checked.
        pre_hash: SHA-256 hash recorded during the pre-calculation phase.
        post_hash: SHA-256 hash computed at verification time.
        match: True if pre_hash == post_hash (file unchanged).
        violations: List of violation dicts if mismatch detected.

    """

    source_file: str
    pre_hash: str
    post_hash: str
    match: bool
    violations: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================================
# SubmittalIntegrityGate
# ============================================================================


class SubmittalIntegrityGate:
    """Post-draft SHA-256 hash verification gate for the DXF compilation
    pipeline.

    Records file hashes at key pipeline phases and verifies that source files
    have not been modified between the pre-calculation check and the final
    submittal compilation. A mismatch is treated as a CRITICAL violation
    (CWE-367 TOCTOU) and the submittal must be rejected.

    Usage::

        gate = SubmittalIntegrityGate()
        pre = gate.record_hash("building.dxf", "pre_calculation")
        # ... run calculations ...
        result = gate.verify_integrity("building.dxf", pre.sha256_hex)
    """

    def __init__(self) -> None:
        self._hash_records: Dict[str, List[HashRecord]] = {}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_sha256(self, file_path: str) -> str:
        """Compute the SHA-256 hex digest of a file.

        Reads the file in 8 KB chunks to handle large CAD files without
        excessive memory usage. This matches the chunked-read approach
        used in parser_safe.py.

        Args:
            file_path: Path to the file to hash.

        Returns:
            64-character lowercase hex SHA-256 digest.

        Raises:
            FileNotFoundError: If *file_path* does not exist.
            IOError: If the file cannot be read.

        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(_SHA256_CHUNK_SIZE)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_hash(self, file_path: str, phase: str) -> HashRecord:
        """Compute and store the SHA-256 hash of *file_path* for *phase*.

        The hash is computed from the current on-disk contents and stored
        internally so that it can be compared later via
        :meth:`verify_integrity`.

        Args:
            file_path: Path to the source CAD file.
            phase: Pipeline phase identifier. One of:
                ``"pre_calculation"``, ``"post_draft"``,
                ``"final_submittal"``.

        Returns:
            A frozen :class:`HashRecord` with the computed digest.

        Raises:
            FileNotFoundError: If *file_path* does not exist.
            IOError: If the file cannot be read.

        """
        hex_digest = self._compute_sha256(file_path)
        record = HashRecord(
            file_path=file_path,
            sha256_hex=hex_digest,
            recorded_at_epoch_ms=time.time() * 1000.0,
            phase=phase,
        )
        self._hash_records.setdefault(file_path, []).append(record)
        logger.info(
            "Hash recorded for %s at phase '%s': %s",
            file_path,
            phase,
            hex_digest[:16] + "...",
        )
        return record

    def verify_integrity(
        self,
        source_file: str,
        pre_calculation_hash: str,
    ) -> Any:
        """Verify that *source_file* has not changed since pre-calculation.

        Recomputes the SHA-256 hash of *source_file* and compares it against
        *pre_calculation_hash*. A mismatch indicates a TOCTOU vulnerability
        (CWE-367) — the fire alarm design may be based on outdated building
        geometry.

        **If the hashes match** — returns a :class:`DecisionProvenance` with
        HIGH confidence and ``safe=True``.

        **If the hashes differ** — returns a :class:`DecisionProvenance` with
        LOW confidence, ``safe=False``, and a CRITICAL violation describing
        the TOCTOU attack. The submittal **must be rejected** and the
        calculation re-run.

        When :class:`DecisionProvenance` is not available (import failed),
        an :class:`IntegrityCheckResult` is returned instead.

        Args:
            source_file: Path to the CAD source file to verify.
            pre_calculation_hash: SHA-256 hex digest recorded at the
                ``"pre_calculation"`` phase.

        Returns:
            A :class:`DecisionProvenance` (preferred) or
            :class:`IntegrityCheckResult` (fallback).

        Raises:
            FileNotFoundError: If *source_file* does not exist.

        """
        current_hash = self._compute_sha256(source_file)
        match = current_hash == pre_calculation_hash

        # Record the post-draft hash for audit trail
        self.record_hash(source_file, "post_draft")

        if match:
            logger.info(
                "Integrity verified for %s — hash unchanged (%s...)",
                source_file,
                current_hash[:16],
            )
            violations_list: List[Dict[str, Any]] = []
            result = IntegrityCheckResult(
                source_file=source_file,
                pre_hash=pre_calculation_hash,
                post_hash=current_hash,
                match=True,
                violations=violations_list,
            )

            if DecisionProvenance is not None and ConfidenceScore is not None:
                confidence = ConfidenceScore(
                    input_quality_score=1.0,
                    rule_coverage=1.0,
                    geometry_certainty=1.0,
                    overall=ConfidenceLevel.HIGH,  # type: ignore[union-attr]
                )
                return DecisionProvenance.new(
                    decision_type="submittal_integrity_gate",
                    value={"safe": True, "source_file": source_file},
                    inputs={
                        "source_file": source_file,
                        "pre_calculation_hash": pre_calculation_hash,
                        "post_draft_hash": current_hash,
                    },
                    rules_applied=[
                        RuleApplied(  # type: ignore[misc]
                            citation=_CITE_NFPA72_INTEGRITY,
                            constant_id="submittal_integrity.sha256_match",
                            value_used=1.0,
                            unit="boolean",
                        ),
                    ],
                    algorithm={
                        "name": "sha256_hash_comparison",
                        "version": "1.0.0",
                        "parameters": {"chunk_size": _SHA256_CHUNK_SIZE},
                    },
                    confidence=confidence,
                    selected_because="Source file hash unchanged between pre-calculation and final submittal.",
                    feasible_alternatives_considered=1,
                    warnings=[],
                    violations=[],
                )
            return result

        # MISMATCH — CRITICAL violation
        description = (
            f"Source file '{source_file}' was modified between calculation "
            f"(hash: {pre_calculation_hash}) and final submittal compilation "
            f"(hash: {current_hash}). This is a TOCTOU vulnerability "
            f"({_CITE_CWE367}) — the fire alarm design may be based on "
            f"outdated building geometry. REJECT submittal and recalculate."
        )
        logger.critical("INTEGRITY FAILURE: %s", description)

        violation_dict: Dict[str, Any] = {
            "severity": "CRITICAL",
            "citation": _CITE_CWE367,
            "description": description,
            "location": source_file,
            "pre_calculation_hash": pre_calculation_hash,
            "post_draft_hash": current_hash,
        }
        violations = [violation_dict]

        result = IntegrityCheckResult(
            source_file=source_file,
            pre_hash=pre_calculation_hash,
            post_hash=current_hash,
            match=False,
            violations=violations,
        )

        if DecisionProvenance is not None and ConfidenceScore is not None:
            confidence = ConfidenceScore(
                input_quality_score=0.0,
                rule_coverage=0.0,
                geometry_certainty=0.0,
                overall=ConfidenceLevel.LOW,  # type: ignore[union-attr]
            )

            provenance_violation = Violation(  # type: ignore[misc]
                severity="CRITICAL",
                citation=_CITE_CWE367,
                description=description,
                location=source_file,
            )

            return DecisionProvenance.new(
                decision_type="submittal_integrity_gate",
                value={"safe": False, "source_file": source_file},
                inputs={
                    "source_file": source_file,
                    "pre_calculation_hash": pre_calculation_hash,
                    "post_draft_hash": current_hash,
                },
                rules_applied=[
                    RuleApplied(  # type: ignore[misc]
                        citation=_CITE_CWE367,
                        constant_id="submittal_integrity.toctou_violation",
                        value_used=0.0,
                        unit="boolean",
                    ),
                ],
                algorithm={
                    "name": "sha256_hash_comparison",
                    "version": "1.0.0",
                    "parameters": {"chunk_size": _SHA256_CHUNK_SIZE},
                },
                confidence=confidence,
                selected_because="Source file hash MISMATCH — TOCTOU vulnerability detected. Submittal MUST be rejected.",
                feasible_alternatives_considered=0,
                warnings=[],
                violations=[provenance_violation],
            )
        return result

    def get_hash_history(self, file_path: str) -> List[HashRecord]:
        """Return the recorded hash history for a file.

        Args:
            file_path: Path to the source file.

        Returns:
            List of :class:`HashRecord` entries in chronological order.

        """
        return list(self._hash_records.get(file_path, []))

    def clear(self) -> None:
        """Clear all stored hash records."""
        self._hash_records.clear()
        logger.debug("All hash records cleared.")


__all__ = [
    "HashRecord",
    "IntegrityCheckResult",
    "SubmittalIntegrityGate",
]
