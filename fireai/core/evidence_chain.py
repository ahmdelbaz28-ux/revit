"""
evidence_chain.py — Chained Evidence Envelopes for FireAI
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

    chain = EvidenceChain(secret_key="project-key", signer_id="fireai-v1")
    envelope = chain.build_envelope(snapshot_payload, analysis_payload)
    assert chain.verify_envelope(envelope, snapshot_payload, analysis_payload)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _canonical_dumps(payload: Any) -> str:
    """Deterministic JSON serialization for consistent hashing."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
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

    This creates a tamper-evident chain:
      - Changing ANY bit in the snapshot or analysis invalidates the hash.
      - Removing an envelope breaks the chain (previous_hash mismatch).
      - Forging an envelope requires the secret_key.

    Args:
        secret_key:  Secret key for HMAC signing. Must be kept secure.
        signer_id:   Identifier for the signing entity (e.g. "fireai-v1").
    """

    def __init__(self, secret_key: str, signer_id: str):
        if not secret_key:
            raise ValueError("secret_key must not be empty")
        if not signer_id:
            raise ValueError("signer_id must not be empty")
        self._secret_key = secret_key.encode("utf-8")
        self._signer_id = signer_id

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
            "signer_id": self._signer_id,
            "snapshot_hash": _sha256_payload(snapshot_payload),
            "analysis_hash": _sha256_payload(analysis_payload),
            "previous_envelope_hash": (
                previous_envelope["envelope_hash"] if previous_envelope else None
            ),
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

        Args:
            envelope:          The envelope to verify.
            snapshot_payload:  The snapshot data to check against.
            analysis_payload:  The analysis data to check against.
            previous_envelope: The expected previous envelope.

        Returns:
            True if all checks pass, False otherwise.
        """
        expected = dict(envelope)
        signature = expected.pop("signature")
        envelope_hash = expected.pop("envelope_hash")

        # 1. Snapshot hash
        if expected["snapshot_hash"] != _sha256_payload(snapshot_payload):
            return False

        # 2. Analysis hash
        if expected["analysis_hash"] != _sha256_payload(analysis_payload):
            return False

        # 3. Previous envelope chain
        expected_previous_hash = (
            previous_envelope["envelope_hash"] if previous_envelope else None
        )
        if expected["previous_envelope_hash"] != expected_previous_hash:
            return False

        # 4. Envelope hash integrity
        rebuilt_hash = _sha256_payload(expected)
        if rebuilt_hash != envelope_hash:
            return False

        # 5. HMAC signature
        return hmac.compare_digest(signature, self._sign(envelope_hash))

    def _sign(self, envelope_hash: str) -> str:
        """Sign an envelope hash with HMAC-SHA256."""
        return hmac.new(
            self._secret_key,
            envelope_hash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


__all__ = ["EvidenceChain", "EvidenceChainError"]
