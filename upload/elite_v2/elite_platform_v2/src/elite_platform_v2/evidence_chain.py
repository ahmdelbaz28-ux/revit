"""Chained evidence envelopes."""

from __future__ import annotations

import hmac
import hashlib
from datetime import datetime

from .canonical_json import canonical_dumps, sha256_payload


class EvidenceChain(object):
    def __init__(self, secret_key, signer_id):
        if not secret_key:
            raise ValueError("secret_key must not be empty")
        if not signer_id:
            raise ValueError("signer_id must not be empty")
        self._secret_key = secret_key.encode("utf-8")
        self._signer_id = signer_id

    def build_envelope(self, snapshot_payload, analysis_payload, previous_envelope=None):
        body = {
            "schema_version": "evidence-envelope/1",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "signer_id": self._signer_id,
            "snapshot_hash": sha256_payload(snapshot_payload),
            "analysis_hash": sha256_payload(analysis_payload),
            "previous_envelope_hash": (
                previous_envelope["envelope_hash"] if previous_envelope else None
            ),
        }
        envelope_hash = sha256_payload(body)
        envelope = dict(body)
        envelope["envelope_hash"] = envelope_hash
        envelope["signature"] = self._sign(envelope_hash)
        return envelope

    def verify_envelope(self, envelope, snapshot_payload, analysis_payload, previous_envelope=None):
        expected = dict(envelope)
        signature = expected.pop("signature")
        envelope_hash = expected.pop("envelope_hash")
        if expected["snapshot_hash"] != sha256_payload(snapshot_payload):
            return False
        if expected["analysis_hash"] != sha256_payload(analysis_payload):
            return False
        expected_previous_hash = previous_envelope["envelope_hash"] if previous_envelope else None
        if expected["previous_envelope_hash"] != expected_previous_hash:
            return False
        rebuilt_hash = sha256_payload(expected)
        if rebuilt_hash != envelope_hash:
            return False
        return hmac.compare_digest(signature, self._sign(envelope_hash))

    def _sign(self, envelope_hash):
        return hmac.new(
            self._secret_key,
            envelope_hash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
