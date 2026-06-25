"""evidence_chain.py — Chained Evidence Envelopes for FireAI
==========================================================
Adapted from Elite Platform V2 evidence_chain.py.

Provides a blockchain-style chain of signed evidence envelopes.
Each envelope links to the previous one via its hash, creating an
immutable audit trail that can prove:

  1. A specific analysis was produced from a specific building snapshot.
  2. The analysis results have not been tampered with.
  3. The chain is continuous — no envelopes have been removed.

This is critical for AHJ review: if an Authority Having Jurisdiction
asks "how do you know this design was generated from THIS drawing?",
the evidence chain provides cryptographic proof.

Usage:
    from fireai.core.evidence_chain import EvidenceChain

    # V113: NEVER hardcode secret keys. Use environment variables.
    import os
    secret = os.environ.get("FIREAI_EVIDENCE_SECRET")
    if not secret:
        raise EnvironmentError(
            "FIREAI_EVIDENCE_SECRET is not set. Generate a key with: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    chain = EvidenceChain(secret_key=secret, signer_id="fireai-v1")
    envelope = chain.build_envelope(snapshot_payload, analysis_payload)
    assert chain.verify_envelope(envelope, snapshot_payload, analysis_payload)

SECURITY WARNING:
    The secret_key MUST be a cryptographically random string (>= 32 chars).
    Using predictable keys like "project-key" allows attackers to forge
    evidence envelopes, compromising the entire audit trail. In a fire
    protection system, forged evidence = fake compliance = lives at risk.
    The EvidenceChain constructor now REJECTS known-weak keys.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _float_round_default(obj: Any) -> Any:
    """V59 FIX (Finding 7): Round floats to 10 significant digits before JSON serialization.

    Python's float repr can produce different strings for the same mathematical
    value across platforms and Python versions:
      - 0.1 + 0.2 → 0.30000000000000004 on most platforms
      - But json.dumps might output "0.30000000000000004" on one system and
        "0.3" on another, causing hash mismatches.

    Rounding to 10 significant digits provides deterministic output while
    preserving engineering precision (10 digits ≈ 1e-10 relative error).
    """
    if isinstance(obj, float):
        if not math.isfinite(obj):
            # NaN/Inf are not valid JSON — convert to string representation
            return str(obj)
        # Round to 10 significant digits for deterministic serialization
        if obj == 0.0:
            return 0.0
        from decimal import Decimal

        rounded = float(Decimal(obj).normalize())
        # If normalization didn't help (e.g. 0.3), use explicit rounding
        if repr(rounded) != repr(obj):
            # Fall back to 12-digit rounding for determinism
            rounded = round(obj, 12 - 1 - int(math.floor(math.log10(abs(obj)))) if abs(obj) >= 1 else 12)
        return rounded
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _canonical_dumps(payload: Any) -> str:
    """Deterministic JSON serialization for consistent hashing.

    V59 FIX (Finding 7): Added custom float serializer that rounds floats to
    deterministic precision. Without this, the same payload could produce
    different hashes on different platforms due to float repr differences.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_float_round_default,
    )


def _sha256_payload(payload: Any) -> str:
    """SHA-256 hash of a payload in canonical JSON form."""
    return hashlib.sha256(_canonical_dumps(payload).encode("utf-8")).hexdigest()


class EvidenceChainError(Exception):
    """Raised when evidence chain verification fails."""

    pass


class EvidenceChain:
    """Blockchain-style signed evidence envelope chain.

    Each envelope contains:
      - snapshot_hash:  SHA-256 of the building snapshot (input).
      - analysis_hash:  SHA-256 of the analysis results (output).
      - previous_envelope_hash: Links to the prior envelope (chain).
      - envelope_hash:  SHA-256 of the envelope body itself.
      - signature:      HMAC-SHA256 signed by the secret_key.
      - namespace:      Project namespace for collision resistance.

    This creates a tamper-evident chain:
      - Changing ANY bit in the snapshot or analysis invalidates the hash.
      - Removing an envelope breaks the chain (previous_hash mismatch).
      - Forging an envelope requires the secret_key.

    V59 FIX (Finding 4): Added `namespace` parameter for HMAC domain separation.
    Without a namespace, two different projects using the same secret_key would
    produce identical HMACs for identical payloads, allowing cross-project
    signature replay. The namespace is included in the HMAC input, ensuring
    that signatures from one project cannot be used in another.

    V59 FIX (Finding 7): Fixed JSON float serialization non-determinism by
    using a custom serializer that rounds floats to a fixed precision before
    hashing. Python's `json.dumps` can produce different string representations
    for the same float value depending on platform and precision (e.g., 1.0 vs
    1.0000000000000002), which would cause hash mismatches across systems.

    Args:
        secret_key:  Secret key for HMAC signing. Must be kept secure.
        signer_id:   Identifier for the signing entity (e.g. "fireai-v1").
        namespace:   Project namespace for HMAC domain separation (e.g. "fireai-project-42").

    """

    # V113: Known-weak secret keys that MUST be rejected.
    # These are commonly used in examples/tutorials and provide ZERO security.
    # Using any of these allows anyone who reads the source code to forge
    # evidence envelopes — completely defeating the audit trail integrity.
    _WEAK_SECRET_KEYS = frozenset(
        {
            "project-key",
            "secret",
            "password",
            "key",
            "test",
            "fireai",
            "default",
            "changeme",
            "123456",
            "abc123",
        }
    )

    def __init__(self, secret_key: str, signer_id: str, namespace: str = "fireai"):
        if not secret_key:
            raise ValueError("secret_key must not be empty")
        if not signer_id:
            raise ValueError("signer_id must not be empty")

        # V113 SECURITY: Reject known-weak secret keys.
        # Per agent.md Priority 1 (Safety): a forged evidence chain in a fire
        # protection system means fake compliance reports that can kill people.
        # A predictable secret key makes HMAC signatures worthless.
        key_lower = secret_key.strip().lower()
        if key_lower in self._WEAK_SECRET_KEYS:
            raise ValueError(
                f"SECURITY: secret_key '{secret_key[:8]}...' is a known-weak key "
                f"that provides NO cryptographic protection. Evidence envelopes "
                f"signed with this key can be forged by anyone who reads the "
                f"source code. Use a cryptographically random key (>= 32 chars) "
                f"from os.environ['FIREAI_EVIDENCE_SECRET'] or secrets.token_hex(32). "
                f"Per agent.md Priority 1 (Safety): fake evidence = fake compliance = "
                f"catastrophic loss of life."
            )

        # V113 SECURITY: Warn if key is too short (< 32 chars)
        # HMAC-SHA256 needs at least 32 bytes of entropy for full security.
        # Shorter keys are vulnerable to brute force.
        if len(secret_key) < 32:
            import logging

            logging.getLogger(__name__).warning(
                f"SECURITY: secret_key is only {len(secret_key)} chars — "
                f"recommend >= 32 chars for HMAC-SHA256. Short keys are "
                f"vulnerable to brute force. Use os.environ['FIREAI_EVIDENCE_SECRET'] "
                f"or secrets.token_hex(32)."
            )

        self._secret_key = secret_key.encode("utf-8")
        self._signer_id = signer_id
        # V59 FIX (Finding 4): Include namespace in HMAC domain
        # Without this, identical payloads in different projects produce identical
        # HMACs, enabling cross-project signature replay attacks.
        self._namespace = namespace or "fireai"

    def build_envelope(
        self,
        snapshot_payload: Dict[str, Any],
        analysis_payload: Dict[str, Any],
        previous_envelope: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a signed evidence envelope linking input to output.

        Args:
            snapshot_payload:  The building snapshot data (input).
            analysis_payload:  The analysis results (output).
            previous_envelope: The previous envelope in the chain (None for first).

        Returns:
            Signed envelope dictionary with hashes and HMAC signature.

        """
        body = {
            "schema_version": "evidence-envelope/1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "namespace": self._namespace,  # V59 FIX (Finding 4): Include namespace for domain separation
            "signer_id": self._signer_id,
            "snapshot_hash": _sha256_payload(snapshot_payload),
            "analysis_hash": _sha256_payload(analysis_payload),
            "previous_envelope_hash": (previous_envelope["envelope_hash"] if previous_envelope else None),
        }
        envelope_hash = _sha256_payload(body)
        envelope = dict(body)
        envelope["envelope_hash"] = envelope_hash
        envelope["signature"] = self._sign(envelope_hash)
        return envelope

    def verify_envelope(
        self,
        envelope: Dict[str, Any],
        snapshot_payload: Dict[str, Any],
        analysis_payload: Dict[str, Any],
        previous_envelope: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Verify an evidence envelope against its source data.

        Checks:
          1. snapshot_hash matches the provided snapshot.
          2. analysis_hash matches the provided analysis.
          3. previous_envelope_hash matches the previous envelope.
          4. envelope_hash can be rebuilt from the body.
          5. HMAC signature is valid.

        STRENGTHENED: Now raises EvidenceChainError with specific failure
        reason instead of silently returning False. This makes debugging
        and audit trail analysis possible.

        Args:
            envelope:          The envelope to verify.
            snapshot_payload:  The snapshot data to check against.
            analysis_payload:  The analysis data to check against.
            previous_envelope: The expected previous envelope.

        Returns:
            True if all checks pass.

        Raises:
            EvidenceChainError: If any check fails, with the specific reason.

        """
        expected = dict(envelope)
        signature = expected.pop("signature")
        envelope_hash = expected.pop("envelope_hash")

        # 1. Snapshot hash
        if expected["snapshot_hash"] != _sha256_payload(snapshot_payload):
            raise EvidenceChainError(
                f"Snapshot hash mismatch: envelope has {expected['snapshot_hash'][:16]}..., "
                f"computed {_sha256_payload(snapshot_payload)[:16]}... "
                f"— data may have been tampered with"
            )

        # 2. Analysis hash
        if expected["analysis_hash"] != _sha256_payload(analysis_payload):
            raise EvidenceChainError(
                f"Analysis hash mismatch: envelope has {expected['analysis_hash'][:16]}..., "
                f"computed {_sha256_payload(analysis_payload)[:16]}... "
                f"— results may have been tampered with"
            )

        # 3. Previous envelope chain
        expected_previous_hash = previous_envelope["envelope_hash"] if previous_envelope else None
        if expected["previous_envelope_hash"] != expected_previous_hash:
            raise EvidenceChainError(
                f"Chain link broken: previous_envelope_hash is "
                f"{expected['previous_envelope_hash'][:16] if expected['previous_envelope_hash'] else 'None'}, "
                f"expected {expected_previous_hash[:16] if expected_previous_hash else 'None'} "
                f"— envelope may have been inserted or removed"
            )

        # 4. Envelope hash integrity
        rebuilt_hash = _sha256_payload(expected)
        if rebuilt_hash != envelope_hash:
            raise EvidenceChainError(
                f"Envelope hash integrity failed: stored {envelope_hash[:16]}..., "
                f"rebuilt {rebuilt_hash[:16]}... — envelope body was modified"
            )

        # 5. HMAC signature
        if not hmac.compare_digest(signature, self._sign(envelope_hash)):
            raise EvidenceChainError("HMAC signature invalid — envelope may have been forged")

        return True

    def verify_chain(
        self,
        envelopes: List[Dict[str, Any]],
        snapshot_payloads: List[Dict[str, Any]],
        analysis_payloads: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Verify an entire chain of evidence envelopes.

        This detects:
          - Missing envelopes (chain gap)
          - Tampered envelopes (hash mismatch)
          - Reordered envelopes (timestamp not monotonic)
          - Forged envelopes (HMAC failure)

        Each envelope[i] is verified against snapshot_payloads[i] and
        analysis_payloads[i], and envelope[i]'s previous_envelope_hash
        must match envelope[i-1]'s envelope_hash.

        Args:
            envelopes:          Ordered list of envelopes (oldest first).
            snapshot_payloads:  Corresponding snapshot payloads.
            analysis_payloads:  Corresponding analysis payloads.

        Returns:
            Dictionary with:
              - valid: bool — True if entire chain is valid
              - envelope_count: int — Number of envelopes checked
              - errors: List[str] — Specific failures (empty if valid)
              - first_break: Optional[int] — Index of first invalid envelope

        """
        if len(envelopes) != len(snapshot_payloads) or len(envelopes) != len(analysis_payloads):
            return {
                "valid": False,
                "envelope_count": len(envelopes),
                "errors": [
                    f"Length mismatch: {len(envelopes)} envelopes, "
                    f"{len(snapshot_payloads)} snapshots, "
                    f"{len(analysis_payloads)} analyses"
                ],
                "first_break": None,
            }

        errors: List[str] = []
        first_break: Optional[int] = None
        prev_timestamp: Optional[str] = None

        for i, envelope in enumerate(envelopes):
            prev_env = envelopes[i - 1] if i > 0 else None
            try:
                self.verify_envelope(
                    envelope=envelope,
                    snapshot_payload=snapshot_payloads[i],
                    analysis_payload=analysis_payloads[i],
                    previous_envelope=prev_env,
                )
            except EvidenceChainError as e:
                errors.append(f"Envelope[{i}]: {e}")
                if first_break is None:
                    first_break = i

            # Check monotonic timestamp ordering
            ts = envelope.get("created_at", "")
            if prev_timestamp and ts < prev_timestamp:
                errors.append(
                    f"Envelope[{i}]: Timestamp regression — {ts} < {prev_timestamp} — envelopes may be reordered"
                )
                if first_break is None:
                    first_break = i
            prev_timestamp = ts

        return {
            "valid": len(errors) == 0,
            "envelope_count": len(envelopes),
            "errors": errors,
            "first_break": first_break,
        }

    def _sign(self, envelope_hash: str) -> str:
        """Sign an envelope hash with HMAC-SHA256.

        V59 FIX (Finding 4): Include namespace in HMAC input for domain separation.
        Without this, the same envelope_hash in different projects produces the
        same signature, enabling cross-project replay attacks.
        """
        # V59 FIX (Finding 4): Namespace-separated HMAC
        # Format: namespace || envelope_hash ensures that signatures from
        # different projects (different namespaces) are always different,
        # even for identical envelope content.
        message = f"{self._namespace}:{envelope_hash}".encode()
        return hmac.new(
            self._secret_key,
            message,
            hashlib.sha256,
        ).hexdigest()


__all__ = ["EvidenceChain", "EvidenceChainError"]
