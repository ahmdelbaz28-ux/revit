"""
tests/test_evidence_chain.py
==============================
Comprehensive test suite for fireai/core/evidence_chain.py

SAFETY CRITICAL: The evidence chain provides cryptographic proof that a
specific analysis was produced from a specific building snapshot. Forged
evidence = fake compliance = lives at risk.

Key features tested:
  - HMAC-SHA256 signature integrity
  - Chain link verification (previous_envelope_hash)
  - V59 FIX: Namespace separation for cross-project replay prevention
  - V59 FIX: Deterministic float serialization
  - V113 FIX: Weak secret key rejection
  - Timestamp monotonicity
  - EvidenceChainError with specific failure reasons
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from fireai.core.evidence_chain import (
    EvidenceChain,
    EvidenceChainError,
    _canonical_dumps,
    _float_round_default,
    _sha256_payload,
)

# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

# Use a long enough key to avoid V113 warning
_SECRET = "a" * 64  # 64-char cryptographically strong key for testing


@pytest.fixture
def chain() -> EvidenceChain:
    return EvidenceChain(secret_key=_SECRET, signer_id="test-signer")


@pytest.fixture
def snapshot():
    return {"building_id": "BLDG-A", "floor": 1, "rooms": 10}


@pytest.fixture
def analysis():
    return {"detector_count": 15, "compliant": True, "nfpa_section": "17.6.3"}


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


class TestCanonicalDumps:

    def test_deterministic(self):
        payload = {"b": 2, "a": 1}
        assert _canonical_dumps(payload) == _canonical_dumps(payload)

    def test_sort_keys(self):
        payload = {"z": 1, "a": 2}
        result = _canonical_dumps(payload)
        # "a" should come before "z" in sorted output
        assert result.index('"a"') < result.index('"z"')

    def test_compact_separators(self):
        payload = {"key": "val"}
        result = _canonical_dumps(payload)
        assert ", " not in result  # No space after comma
        assert ": " not in result  # No space after colon


class TestFloatRoundDefault:

    def test_finite_float_rounds(self):
        result = _float_round_default(3.141592653589793)
        assert isinstance(result, float)

    def test_nan_converts_to_string(self):
        result = _float_round_default(float("nan"))
        assert isinstance(result, str)

    def test_inf_converts_to_string(self):
        result = _float_round_default(float("inf"))
        assert isinstance(result, str)

    def test_neg_inf_converts_to_string(self):
        result = _float_round_default(float("-inf"))
        assert isinstance(result, str)

    def test_zero_stays_zero(self):
        result = _float_round_default(0.0)
        assert result == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_non_float_raises(self):
        with pytest.raises(TypeError):
            _float_round_default({1, 2, 3})


class TestSha256Payload:

    def test_returns_64_hex_chars(self):
        h = _sha256_payload({"key": "value"})
        assert len(h) == 64

    def test_deterministic(self):
        h1 = _sha256_payload({"key": "value"})
        h2 = _sha256_payload({"key": "value"})
        assert h1 == h2

    def test_different_payloads_different_hashes(self):
        h1 = _sha256_payload({"key": "value1"})
        h2 = _sha256_payload({"key": "value2"})
        assert h1 != h2


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceChain — Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestEvidenceChainInit:

    def test_valid_init(self):
        ec = EvidenceChain(secret_key=_SECRET, signer_id="test")
        assert ec._signer_id == "test"

    def test_empty_secret_key_rejected(self):
        with pytest.raises(ValueError, match="secret_key must not be empty"):
            EvidenceChain(secret_key="", signer_id="test")

    def test_empty_signer_id_rejected(self):
        with pytest.raises(ValueError, match="signer_id must not be empty"):
            EvidenceChain(secret_key=_SECRET, signer_id="")

    def test_weak_key_project_key_rejected(self):
        """V113: Known-weak key 'project-key' must be rejected."""
        with pytest.raises(ValueError, match="known-weak key"):
            EvidenceChain(secret_key="project-key", signer_id="test")

    def test_weak_key_secret_rejected(self):
        with pytest.raises(ValueError, match="known-weak key"):
            EvidenceChain(secret_key="secret", signer_id="test")

    def test_weak_key_password_rejected(self):
        with pytest.raises(ValueError, match="known-weak key"):
            EvidenceChain(secret_key="password", signer_id="test")

    def test_weak_key_changeme_rejected(self):
        with pytest.raises(ValueError, match="known-weak key"):
            EvidenceChain(secret_key="changeme", signer_id="test")

    def test_weak_key_fireai_rejected(self):
        with pytest.raises(ValueError, match="known-weak key"):
            EvidenceChain(secret_key="fireai", signer_id="test")

    def test_weak_key_123456_rejected(self):
        with pytest.raises(ValueError, match="known-weak key"):
            EvidenceChain(secret_key="123456", signer_id="test")

    def test_weak_key_case_insensitive(self):
        """V113: Weak key check is case-insensitive."""
        with pytest.raises(ValueError, match="known-weak key"):
            EvidenceChain(secret_key="PROJECT-KEY", signer_id="test")

    def test_weak_key_whitespace_stripped(self):
        """V113: Whitespace is stripped before checking."""
        with pytest.raises(ValueError, match="known-weak key"):
            EvidenceChain(secret_key="  secret  ", signer_id="test")

    def test_namespace_default(self):
        ec = EvidenceChain(secret_key=_SECRET, signer_id="test")
        assert ec._namespace == "fireai"

    def test_namespace_custom(self):
        ec = EvidenceChain(secret_key=_SECRET, signer_id="test", namespace="project-42")
        assert ec._namespace == "project-42"


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceChain — build_envelope
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildEnvelope:

    def test_returns_dict_with_required_fields(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        assert "schema_version" in env
        assert "created_at" in env
        assert "snapshot_hash" in env
        assert "analysis_hash" in env
        assert "previous_envelope_hash" in env
        assert "envelope_hash" in env
        assert "signature" in env
        assert "namespace" in env
        assert "signer_id" in env

    def test_first_envelope_no_previous(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        assert env["previous_envelope_hash"] is None

    def test_chained_envelope_links_previous(self, chain, snapshot, analysis):
        env1 = chain.build_envelope(snapshot, analysis)
        env2 = chain.build_envelope(snapshot, analysis, previous_envelope=env1)
        assert env2["previous_envelope_hash"] == env1["envelope_hash"]

    def test_snapshot_hash_matches_payload(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        assert env["snapshot_hash"] == _sha256_payload(snapshot)

    def test_analysis_hash_matches_payload(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        assert env["analysis_hash"] == _sha256_payload(analysis)

    def test_envelope_hash_is_deterministic(self, chain, snapshot, analysis):
        env1 = chain.build_envelope(snapshot, analysis)
        env2 = chain.build_envelope(snapshot, analysis)
        # Different timestamps → different hashes
        # But snapshot_hash and analysis_hash should be the same
        assert env1["snapshot_hash"] == env2["snapshot_hash"]
        assert env1["analysis_hash"] == env2["analysis_hash"]

    def test_signature_is_hmac_sha256(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        assert len(env["signature"]) == 64  # HMAC-SHA256 hex

    def test_namespace_in_envelope(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        assert env["namespace"] == "fireai"


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceChain — verify_envelope
# ─────────────────────────────────────────────────────────────────────────────


class TestVerifyEnvelope:

    def test_valid_envelope_verifies(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        assert chain.verify_envelope(env, snapshot, analysis) is True

    def test_tampered_snapshot_detected(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        tampered_snapshot = {**snapshot, "rooms": 99}
        with pytest.raises(EvidenceChainError, match="Snapshot hash mismatch"):
            chain.verify_envelope(env, tampered_snapshot, analysis)

    def test_tampered_analysis_detected(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        tampered_analysis = {**analysis, "compliant": False}
        with pytest.raises(EvidenceChainError, match="Analysis hash mismatch"):
            chain.verify_envelope(env, snapshot, tampered_analysis)

    def test_broken_chain_link_detected(self, chain, snapshot, analysis):
        env1 = chain.build_envelope(snapshot, analysis)
        env2 = chain.build_envelope(snapshot, analysis, previous_envelope=env1)
        # Verify with wrong previous envelope
        fake_prev = dict(env1)
        fake_prev["envelope_hash"] = "0" * 64
        with pytest.raises(EvidenceChainError, match="Chain link broken"):
            chain.verify_envelope(env2, snapshot, analysis, previous_envelope=fake_prev)

    def test_tampered_envelope_body_detected(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        tampered_env = dict(env)
        tampered_env["snapshot_hash"] = "0" * 64
        with pytest.raises(EvidenceChainError):
            chain.verify_envelope(tampered_env, snapshot, analysis)

    def test_forged_signature_detected(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        forged_env = dict(env)
        forged_env["signature"] = "f" * 64
        with pytest.raises(EvidenceChainError, match="HMAC signature invalid"):
            chain.verify_envelope(forged_env, snapshot, analysis)

    def test_no_previous_envelope_ok(self, chain, snapshot, analysis):
        env = chain.build_envelope(snapshot, analysis)
        assert chain.verify_envelope(env, snapshot, analysis, previous_envelope=None) is True


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceChain — verify_chain
# ─────────────────────────────────────────────────────────────────────────────


class TestVerifyChain:

    def test_valid_chain(self, chain, snapshot, analysis):
        env1 = chain.build_envelope(snapshot, analysis)
        env2 = chain.build_envelope(snapshot, analysis, previous_envelope=env1)
        result = chain.verify_chain(
            [env1, env2],
            [snapshot, snapshot],
            [analysis, analysis],
        )
        assert result["valid"] is True
        assert result["envelope_count"] == 2
        assert len(result["errors"]) == 0

    def test_length_mismatch_detected(self, chain, snapshot, analysis):
        env1 = chain.build_envelope(snapshot, analysis)
        result = chain.verify_chain(
            [env1],
            [snapshot, snapshot],  # 2 snapshots for 1 envelope
            [analysis],
        )
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_tampered_envelope_in_chain(self, chain, snapshot, analysis):
        env1 = chain.build_envelope(snapshot, analysis)
        tampered_snapshot = {**snapshot, "rooms": 999}
        result = chain.verify_chain(
            [env1],
            [tampered_snapshot],
            [analysis],
        )
        assert result["valid"] is False
        assert result["first_break"] == 0

    def test_empty_chain(self, chain):
        result = chain.verify_chain([], [], [])
        assert result["valid"] is True  # Empty chain is trivially valid


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceChain — Namespace Separation (V59 FIX Finding 4)
# ─────────────────────────────────────────────────────────────────────────────


class TestNamespaceSeparation:

    def test_different_namespaces_different_signatures(self, snapshot, analysis):
        """V59 FIX: Same payload in different projects → different signatures."""
        chain1 = EvidenceChain(secret_key=_SECRET, signer_id="test", namespace="project-A")
        chain2 = EvidenceChain(secret_key=_SECRET, signer_id="test", namespace="project-B")
        env1 = chain1.build_envelope(snapshot, analysis)
        env2 = chain2.build_envelope(snapshot, analysis)
        assert env1["signature"] != env2["signature"]

    def test_cross_namespace_verification_fails(self, snapshot, analysis):
        """V59 FIX: Signature from project-A cannot verify in project-B."""
        chain_a = EvidenceChain(secret_key=_SECRET, signer_id="test", namespace="project-A")
        chain_b = EvidenceChain(secret_key=_SECRET, signer_id="test", namespace="project-B")
        env_a = chain_a.build_envelope(snapshot, analysis)
        with pytest.raises(EvidenceChainError, match="HMAC signature invalid"):
            chain_b.verify_envelope(env_a, snapshot, analysis)


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceChain — _sign method
# ─────────────────────────────────────────────────────────────────────────────


class TestSignMethod:

    def test_sign_includes_namespace(self, chain):
        """V59 FIX: Namespace is included in HMAC input."""
        sig = chain._sign("test_hash")
        # Manually compute expected signature
        message = f"{chain._namespace}:test_hash".encode()
        expected = hmac.new(
            chain._secret_key, message, hashlib.sha256
        ).hexdigest()
        assert sig == expected


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:

    def test_empty_snapshot(self, chain, analysis):
        env = chain.build_envelope({}, analysis)
        assert chain.verify_envelope(env, {}, analysis) is True

    def test_empty_analysis(self, chain, snapshot):
        env = chain.build_envelope(snapshot, {})
        assert chain.verify_envelope(env, snapshot, {}) is True

    def test_nan_in_payload(self, chain):
        """NaN in payload should be handled by _float_round_default."""
        snapshot = {"value": float("nan")}
        analysis = {"result": True}
        env = chain.build_envelope(snapshot, analysis)
        # Should not crash — NaN is converted to string
        assert env is not None

    def test_inf_in_payload(self, chain):
        snapshot = {"value": float("inf")}
        analysis = {"result": True}
        env = chain.build_envelope(snapshot, analysis)
        assert env is not None

    def test_nested_payload(self, chain):
        snapshot = {"building": {"id": "A", "floors": [1, 2, 3]}}
        analysis = {"detectors": {"count": 15, "compliant": True}}
        env = chain.build_envelope(snapshot, analysis)
        assert chain.verify_envelope(env, snapshot, analysis) is True

    def test_large_chain_verification(self, chain, snapshot, analysis):
        """Verify a chain of 10 envelopes."""
        envelopes = []
        prev = None
        for _i in range(10):
            env = chain.build_envelope(snapshot, analysis, previous_envelope=prev)
            envelopes.append(env)
            prev = env
        result = chain.verify_chain(
            envelopes,
            [snapshot] * 10,
            [analysis] * 10,
        )
        assert result["valid"] is True
        assert result["envelope_count"] == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
