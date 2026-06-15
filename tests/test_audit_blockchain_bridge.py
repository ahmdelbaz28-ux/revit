"""
tests/test_audit_blockchain_bridge.py
======================================
Comprehensive test suite for fireai/core/audit_blockchain_bridge.py

SAFETY CRITICAL: The hash chain audit trail provides tamper-evident logging
for fire alarm system analysis results per NFPA 72-2022 §10.6.

Key features tested:
  - SHA-256 hash chain integrity (not blockchain — honest naming)
  - HMAC-SHA256 tamper detection on every read
  - Merkle proof generation and verification
  - AHJ-ready compliance reports
  - Actor tracking for audit trail integrity
"""

from __future__ import annotations

import json
import threading

import pytest

from fireai.core.audit_blockchain_bridge import (
    AUDIT_SYSTEM_NAME,
    AUDIT_VERSION,
    NOT_A_BLOCKCHAIN_NOTE,
    AuditEntry,
    HashChainAuditStore,
    _chain_hash,
    _hmac_sha256,
    _sha256,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestConstants:
    def test_audit_system_name_honest(self):
        """NOT 'blockchain' — honest naming per surgical fix."""
        assert "SHA-256" in AUDIT_SYSTEM_NAME
        assert "blockchain" not in AUDIT_SYSTEM_NAME.lower() or "NOT" in AUDIT_SYSTEM_NAME

    def test_audit_version(self):
        assert AUDIT_VERSION == "1.0.0"

    def test_honest_disclosure(self):
        assert "NOT a distributed blockchain" in NOT_A_BLOCKCHAIN_NOTE
        assert "NFPA 72" in NOT_A_BLOCKCHAIN_NOTE


# ═══════════════════════════════════════════════════════════════════════════════
# Hash Primitives Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHashPrimitives:
    def test_sha256_string(self):
        result = _sha256("hello")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_sha256_bytes(self):
        result = _sha256(b"hello")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_sha256_deterministic(self):
        assert _sha256("test") == _sha256("test")

    def test_sha256_different_inputs(self):
        assert _sha256("a") != _sha256("b")

    def test_hmac_sha256_string(self):
        key = b"secret"
        result = _hmac_sha256(key, "data")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hmac_sha256_bytes(self):
        key = b"secret"
        result = _hmac_sha256(key, b"data")
        assert isinstance(result, str)

    def test_chain_hash(self):
        prev = "0" * 64
        entry = '{"test": true}'
        result = _chain_hash(prev, entry)
        # Should be SHA-256(prev + "|" + entry)
        expected = _sha256(prev + "|" + entry)
        assert result == expected


# ═══════════════════════════════════════════════════════════════════════════════
# AuditEntry Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditEntry:
    def _make_entry(self, **overrides):
        defaults = {
            "entry_id": "test-1",
            "event_type": "test_event",
            "data": {"key": "value"},
            "timestamp": 1000.0,
            "seq_num": 0,
            "prev_hash": "0" * 64,
            "chain_hash": "a" * 64,
            "hmac_sig": "b" * 64,
            "actor": "test_user",
        }
        defaults.update(overrides)
        return AuditEntry(**defaults)

    def test_create(self):
        e = self._make_entry()
        assert e.entry_id == "test-1"
        assert e.actor == "test_user"

    def test_to_json(self):
        e = self._make_entry()
        j = e.to_json()
        parsed = json.loads(j)
        assert parsed["entry_id"] == "test-1"
        assert parsed["actor"] == "test_user"

    def test_from_json_roundtrip(self):
        e = self._make_entry()
        j = e.to_json()
        e2 = AuditEntry.from_json(j)
        assert e2.entry_id == e.entry_id
        assert e2.chain_hash == e.chain_hash
        assert e2.actor == e.actor


# ═══════════════════════════════════════════════════════════════════════════════
# HashChainAuditStore Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHashChainAuditStore:
    @pytest.fixture
    def store(self):
        return HashChainAuditStore(db_path=":memory:", secret_key="test-secret-key")

    def test_init(self, store):
        assert store._seq == 0
        assert store._entries == []
        assert store._prev_hash == store.GENESIS_HASH

    def test_log_entry(self, store):
        entry = store.log(event_type="test", data={"action": "create"}, actor="user1")
        assert entry.event_type == "test"
        assert entry.seq_num == 0
        assert entry.actor == "user1"
        assert len(store._entries) == 1

    def test_log_increments_seq(self, store):
        store.log(event_type="e1", data={})
        store.log(event_type="e2", data={})
        assert store._seq == 2
        assert store._entries[0].seq_num == 0
        assert store._entries[1].seq_num == 1

    def test_log_chain_linkage(self, store):
        """Each entry's prev_hash must equal previous entry's chain_hash."""
        e1 = store.log(event_type="e1", data={"a": 1})
        e2 = store.log(event_type="e2", data={"b": 2})
        assert e2.prev_hash == e1.chain_hash

    def test_first_entry_links_to_genesis(self, store):
        e1 = store.log(event_type="first", data={})
        assert e1.prev_hash == store.GENESIS_HASH

    def test_add_event_alias(self, store):
        entry = store.add_event(event_type="alias_test", data={"x": 1})
        assert entry.event_type == "alias_test"

    def test_verify_chain_empty(self, store):
        is_valid, violations = store.verify_chain()
        assert is_valid is True
        assert violations == []

    def test_verify_chain_valid(self, store):
        store.log(event_type="e1", data={"a": 1})
        store.log(event_type="e2", data={"b": 2})
        store.log(event_type="e3", data={"c": 3})
        is_valid, violations = store.verify_chain()
        assert is_valid is True
        assert violations == []

    def test_verify_chain_tampered_data(self, store):
        """Tampering with entry data should be detected."""
        store.log(event_type="e1", data={"original": True})
        # Tamper: modify the data in-memory
        object.__setattr__(store._entries[0], "data", {"tampered": True})
        is_valid, violations = store.verify_chain()
        assert is_valid is False
        assert any("TAMPER DETECTED" in v for v in violations)

    def test_verify_chain_broken_prev_hash(self, store):
        """Breaking prev_hash linkage should be detected."""
        store.log(event_type="e1", data={})
        store.log(event_type="e2", data={})
        # Tamper: change prev_hash
        object.__setattr__(store._entries[1], "prev_hash", "X" * 64)
        is_valid, violations = store.verify_chain()
        assert is_valid is False
        assert any("prev_hash mismatch" in v for v in violations)

    def test_verify_chain_hmac_failure(self, store):
        """HMAC mismatch should be detected."""
        store.log(event_type="e1", data={})
        # Tamper with HMAC
        object.__setattr__(store._entries[0], "hmac_sig", "X" * 64)
        is_valid, violations = store.verify_chain()
        assert is_valid is False
        assert any("HMAC FAILURE" in v for v in violations)

    def test_actor_included_in_chain_hash(self, store):
        """Actor is included in chain hash for full audit integrity."""
        e1 = store.log(event_type="e1", data={}, actor="alice")
        # Verify chain hash includes actor
        entry_core = {
            "entry_id": e1.entry_id,
            "event_type": e1.event_type,
            "data": e1.data,
            "timestamp": e1.timestamp,
            "seq_num": e1.seq_num,
            "prev_hash": e1.prev_hash,
            "actor": "alice",
        }
        entry_json = json.dumps(entry_core, sort_keys=True, default=str)
        expected_ch = _chain_hash(e1.prev_hash, entry_json)
        assert e1.chain_hash == expected_ch

    def test_different_actors_different_hashes(self):
        """Different actors for same event produce different chain hashes."""
        s1 = HashChainAuditStore(db_path=":memory:", secret_key="key1")
        s2 = HashChainAuditStore(db_path=":memory:", secret_key="key1")
        e1 = s1.log(event_type="e1", data={"x": 1}, actor="alice")
        e2 = s2.log(event_type="e1", data={"x": 1}, actor="bob")
        assert e1.chain_hash != e2.chain_hash


# ═══════════════════════════════════════════════════════════════════════════════
# Merkle Proof Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMerkleProof:
    @pytest.fixture
    def store(self):
        s = HashChainAuditStore(db_path=":memory:", secret_key="test-key")
        for i in range(4):
            s.log(event_type=f"event_{i}", data={"idx": i})
        return s

    def test_build_merkle_proof_found(self, store):
        entry_id = store._entries[0].entry_id
        proof = store.build_merkle_proof(entry_id)
        assert proof is not None
        assert proof["entry_id"] == entry_id
        assert proof["proof_valid"] is True
        assert "merkle_root" in proof
        assert "proof_path" in proof

    def test_build_merkle_proof_not_found(self, store):
        proof = store.build_merkle_proof("nonexistent-id")
        assert proof is None

    def test_build_merkle_proof_empty_store(self):
        s = HashChainAuditStore(db_path=":memory:", secret_key="k")
        assert s.build_merkle_proof("any") is None

    def test_merkle_root_consistency(self, store):
        """Same entries should produce same merkle root."""
        proof1 = store.build_merkle_proof(store._entries[0].entry_id)
        proof2 = store.build_merkle_proof(store._entries[1].entry_id)
        assert proof1["merkle_root"] == proof2["merkle_root"]

    def test_proof_contains_audit_system_info(self, store):
        proof = store.build_merkle_proof(store._entries[0].entry_id)
        assert proof["audit_system"] == AUDIT_SYSTEM_NAME
        assert proof["audit_version"] == AUDIT_VERSION
        assert "NOT a distributed blockchain" in proof["note"]

    def test_merkle_levels_static(self):
        """Static method _build_merkle_levels."""
        levels = HashChainAuditStore._build_merkle_levels(["a", "b"])
        assert len(levels) == 2  # leaf level + root
        assert len(levels[0]) == 2
        assert len(levels[1]) == 1

    def test_merkle_levels_empty(self):
        levels = HashChainAuditStore._build_merkle_levels([])
        assert levels[0][0] == "0" * 64

    def test_merkle_levels_odd_count(self):
        """Odd number of leaves: last leaf duplicated (RFC 6962)."""
        levels = HashChainAuditStore._build_merkle_levels(["a", "b", "c"])
        assert len(levels[0]) == 3  # Original leaves
        # Second level: hash(a+b), hash(c+c)
        assert len(levels[1]) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Compliance Report Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestComplianceReport:
    @pytest.fixture
    def store(self):
        s = HashChainAuditStore(db_path=":memory:", secret_key="report-key")
        for i in range(3):
            s.log(event_type=f"event_{i}", data={"idx": i})
        return s

    def test_compliance_report_structure(self, store):
        report = store.compliance_report()
        assert report["is_valid"] is True
        assert report["total_entries"] == 3
        assert "merkle_root" in report
        assert "first_entry_ts" in report
        assert "last_entry_ts" in report
        assert "chain_violations" in report
        assert report["chain_violations"] == []

    def test_compliance_report_honest_disclosure(self, store):
        report = store.compliance_report()
        assert "NOT a distributed blockchain" in report["honest_disclosure"]

    def test_compliance_report_nfpa_reference(self, store):
        report = store.compliance_report()
        assert "NFPA 72" in report["nfpa_reference"]

    def test_compliance_report_verification_instructions(self, store):
        report = store.compliance_report()
        assert "verification_instructions" in report
        assert "HMAC key" in report["verification_instructions"]

    def test_summary_alias(self, store):
        report = store.summary()
        assert "is_valid" in report

    def test_empty_store_compliance_report(self):
        s = HashChainAuditStore(db_path=":memory:", secret_key="k")
        report = s.compliance_report()
        assert report["is_valid"] is True
        assert report["total_entries"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Thread Safety Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreadSafety:
    def test_concurrent_logging(self):
        """Multiple threads logging concurrently must not corrupt chain."""
        store = HashChainAuditStore(db_path=":memory:", secret_key="concurrent-key")
        errors = []

        def log_entries(n):
            try:
                for i in range(n):
                    store.log(event_type="thread_event", data={"n": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=log_entries, args=(10,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        is_valid, violations = store.verify_chain()
        assert is_valid is True, f"Chain corrupted: {violations}"
        assert len(store._entries) == 50


# ═══════════════════════════════════════════════════════════════════════════════
# HMAC Key Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHMACKey:
    def test_secret_key_derived_hmac(self):
        """Secret key is SHA-256 hashed to produce HMAC key."""
        store = HashChainAuditStore(db_path=":memory:", secret_key="my-secret")
        import hashlib
        expected_key = hashlib.sha256("my-secret".encode()).digest()
        assert store._hmac_key == expected_key

    def test_explicit_hmac_key(self):
        key = b"\x01" * 32
        store = HashChainAuditStore(db_path=":memory:", hmac_key=key)
        assert store._hmac_key == key

    def test_ephemeral_key_generated(self):
        """No secret/hmac key → random ephemeral key."""
        store = HashChainAuditStore(db_path=":memory:")
        assert len(store._hmac_key) == 32

    def test_different_keys_different_signatures(self):
        """Different HMAC keys produce different signatures for same data."""
        s1 = HashChainAuditStore(db_path=":memory:", secret_key="key1")
        s2 = HashChainAuditStore(db_path=":memory:", secret_key="key2")
        e1 = s1.log(event_type="test", data={"x": 1})
        e2 = s2.log(event_type="test", data={"x": 1})
        assert e1.hmac_sig != e2.hmac_sig


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
