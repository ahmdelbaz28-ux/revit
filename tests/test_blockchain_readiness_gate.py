"""
tests/test_blockchain_readiness_gate.py
=========================================
Comprehensive test suite for fireai/core/blockchain_readiness_gate.py

Tests the Merkle tree implementation and BlockchainReadinessGate for
design manifest integrity checking per RFC 6962.

Key distinction verified:
  - merkle_root ≠ design_manifest_hash (they serve different purposes)
  - merkle_root supports O(log n) inclusion proofs
  - design_manifest_hash is a simple integrity hash

References:
  RFC 6962 §2.1   — Certificate Transparency Merkle tree
  RFC 6962 §2.1.1 — Merkle audit proof (inclusion proof)

"""

from __future__ import annotations

import dataclasses

import pytest

from fireai.core.blockchain_readiness_gate import (
    EMPTY_HASH,
    PRIORITY,
    BlockchainReadinessGate,
    MerkleProof,
    MerkleTree,
    _hash_pair,
    _sha256_hex,
)

# Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:

    def test_empty_hash_is_64_zeros(self):
        assert EMPTY_HASH == "0" * 64

    def test_priority_is_low(self):
        assert PRIORITY == "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


class TestHelperFunctions:

    def test_sha256_hex_deterministic(self):
        h1 = _sha256_hex("test data")
        h2 = _sha256_hex("test data")
        assert h1 == h2

    def test_sha256_hex_length(self):
        h = _sha256_hex("test")
        assert len(h) == 64

    def test_sha256_hex_different_inputs(self):
        h1 = _sha256_hex("data1")
        h2 = _sha256_hex("data2")
        assert h1 != h2

    def test_hash_pair_order_matters(self):
        """RFC 6962: left || right concatenation order."""
        h1 = _hash_pair("a", "b")
        h2 = _hash_pair("b", "a")
        assert h1 != h2

    def test_hash_pair_uses_sha256(self):
        h = _hash_pair("a", "b")
        expected = _sha256_hex("a" + "b")
        assert h == expected


# MerkleProof
# ─────────────────────────────────────────────────────────────────────────────


class TestMerkleProof:

    def test_frozen(self):
        proof = MerkleProof(0, "leaf_hash", ("sib1",), "root")
        with pytest.raises(dataclasses.FrozenInstanceError):
            proof.leaf_index = 99

    def test_verify_valid_proof(self):
        """Build a 2-leaf tree and verify proof for leaf 0."""
        tree = MerkleTree.from_leaves(["artifact_1", "artifact_2"])
        proof = tree.get_proof(0)
        assert proof.verify() is True

    def test_verify_valid_proof_leaf_1(self):
        tree = MerkleTree.from_leaves(["artifact_1", "artifact_2"])
        proof = tree.get_proof(1)
        assert proof.verify() is True

    def test_tampered_proof_fails(self):
        tree = MerkleTree.from_leaves(["artifact_1", "artifact_2"])
        proof = tree.get_proof(0)
        # Tamper with the proof
        tampered = MerkleProof(
            leaf_index=0,
            leaf_hash="tampered_hash",
            siblings=proof.siblings,
            merkle_root=proof.merkle_root,
        )
        assert tampered.verify() is False

    def test_tampered_root_fails(self):
        tree = MerkleTree.from_leaves(["artifact_1", "artifact_2"])
        proof = tree.get_proof(0)
        tampered = MerkleProof(
            leaf_index=0,
            leaf_hash=proof.leaf_hash,
            siblings=proof.siblings,
            merkle_root="0" * 64,
        )
        assert tampered.verify() is False


# MerkleTree
# ─────────────────────────────────────────────────────────────────────────────


class TestMerkleTree:

    def test_empty_tree_root(self):
        tree = MerkleTree([])
        assert tree.merkle_root == EMPTY_HASH

    def test_single_leaf(self):
        tree = MerkleTree.from_leaves(["only_one"])
        assert tree.leaf_count == 1
        assert tree.merkle_root != EMPTY_HASH

    def test_two_leaves(self):
        tree = MerkleTree.from_leaves(["a", "b"])
        assert tree.leaf_count == 2
        # Root = hash(hash(a) || hash(b))
        expected = _hash_pair(_sha256_hex("a"), _sha256_hex("b"))
        assert tree.merkle_root == expected

    def test_four_leaves(self):
        tree = MerkleTree.from_leaves(["a", "b", "c", "d"])
        assert tree.leaf_count == 4
        assert tree.merkle_root != EMPTY_HASH

    def test_odd_leaf_duplication(self):
        """RFC 6962: odd number of leaves → last leaf duplicated."""
        tree3 = MerkleTree.from_leaves(["a", "b", "c"])
        # Level 0: [h(a), h(b), h(c)]
        # After duplication: [h(a), h(b), h(c), h(c)]
        # Level 1: [hash(h(a)||h(b)), hash(h(c)||h(c))]
        # Level 2: root
        assert tree3.leaf_count == 3
        assert tree3.merkle_root != EMPTY_HASH

    def test_from_leaves_hashes_data(self):
        raw = ["test"]
        tree = MerkleTree.from_leaves(raw)
        expected_leaf = _sha256_hex("test")
        assert tree.leaves[0] == expected_leaf

    def test_leaves_property_returns_copy(self):
        tree = MerkleTree.from_leaves(["a", "b"])
        leaves = tree.leaves
        leaves.append("tampered")
        assert len(tree.leaves) == 2  # Original unchanged

    def test_tree_levels_property(self):
        tree = MerkleTree.from_leaves(["a", "b"])
        levels = tree.tree_levels
        assert len(levels) >= 1

    def test_get_proof_index_out_of_range(self):
        tree = MerkleTree.from_leaves(["a", "b"])
        with pytest.raises(IndexError):
            tree.get_proof(5)

    def test_get_proof_negative_index(self):
        tree = MerkleTree.from_leaves(["a", "b"])
        with pytest.raises(IndexError):
            tree.get_proof(-1)

    def test_verify_proof_method(self):
        tree = MerkleTree.from_leaves(["a", "b", "c", "d"])
        for i in range(4):
            proof = tree.get_proof(i)
            assert tree.verify_proof(proof) is True

    def test_deterministic_root(self):
        """Same leaves → same root, always."""
        t1 = MerkleTree.from_leaves(["a", "b", "c"])
        t2 = MerkleTree.from_leaves(["a", "b", "c"])
        assert t1.merkle_root == t2.merkle_root

    def test_different_leaves_different_root(self):
        t1 = MerkleTree.from_leaves(["a", "b"])
        t2 = MerkleTree.from_leaves(["x", "y"])
        assert t1.merkle_root != t2.merkle_root

    def test_large_tree_proofs_verify(self):
        """Test with a larger tree (16 leaves)."""
        data = [f"artifact_{i}" for i in range(16)]
        tree = MerkleTree.from_leaves(data)
        for i in range(16):
            proof = tree.get_proof(i)
            assert proof.verify() is True


# BlockchainReadinessGate
# ─────────────────────────────────────────────────────────────────────────────


class TestBlockchainReadinessGate:

    def test_init_with_artifacts(self):
        gate = BlockchainReadinessGate(["art1", "art2", "art3"])
        assert gate.artifact_count == 3

    def test_merkle_root_not_empty(self):
        gate = BlockchainReadinessGate(["art1", "art2"])
        assert gate.merkle_root != EMPTY_HASH
        assert len(gate.merkle_root) == 64

    def test_merkle_root_differs_from_manifest_hash(self):
        """CRITICAL: merkle_root and design_manifest_hash are DIFFERENT."""
        gate = BlockchainReadinessGate(["art1", "art2", "art3"])
        assert gate.merkle_root != gate.design_manifest_hash

    def test_design_manifest_hash(self):
        gate = BlockchainReadinessGate(["art1", "art2"])
        expected = _sha256_hex("art1art2")
        assert gate.design_manifest_hash == expected

    def test_get_proof(self):
        gate = BlockchainReadinessGate(["art1", "art2", "art3"])
        proof = gate.get_proof(0)
        assert isinstance(proof, MerkleProof)
        assert proof.leaf_index == 0

    def test_verify_artifact(self):
        gate = BlockchainReadinessGate(["art1", "art2"])
        proof = gate.get_proof(0)
        assert gate.verify_artifact(proof) is True

    def test_get_proof_out_of_range(self):
        gate = BlockchainReadinessGate(["art1", "art2"])
        with pytest.raises(IndexError):
            gate.get_proof(5)

    def test_check_tamper_no_tampering(self):
        gate = BlockchainReadinessGate(["art1", "art2"])
        original_root = gate.merkle_root
        assert gate.check_tamper(original_root) is True

    def test_check_tamper_detected(self):
        gate1 = BlockchainReadinessGate(["art1", "art2"])
        gate2 = BlockchainReadinessGate(["art1", "modified"])
        assert gate2.check_tamper(gate1.merkle_root) is False

    def test_anchor_to_audit_trail_appends(self):
        """Anchoring adds ONE event — does NOT replace chain."""
        gate = BlockchainReadinessGate(["art1", "art2"])
        existing_chain = [{"event_type": "previous_event"}]
        updated = gate.anchor_to_audit_trail(existing_chain)
        assert len(updated) == 2
        assert updated[0]["event_type"] == "previous_event"
        assert updated[1]["event_type"] == "merkle_anchor"

    def test_anchor_preserves_original_chain(self):
        gate = BlockchainReadinessGate(["art1"])
        original = [{"event": "orig"}]
        gate.anchor_to_audit_trail(original)
        assert len(original) == 1  # Original not modified

    def test_anchor_event_has_merkle_root(self):
        gate = BlockchainReadinessGate(["art1", "art2"])
        chain = gate.anchor_to_audit_trail([])
        event = chain[0]
        assert "merkle_root" in event
        assert "design_manifest_hash" in event
        assert "artifact_count" in event
        assert event["artifact_count"] == 2

    def test_anchor_event_hashes_differ(self):
        """merkle_root and design_manifest_hash must be different in anchor."""
        gate = BlockchainReadinessGate(["art1", "art2"])
        chain = gate.anchor_to_audit_trail([])
        event = chain[0]
        assert event["merkle_root"] != event["design_manifest_hash"]

    def test_custom_description(self):
        gate = BlockchainReadinessGate(["art1"])
        chain = gate.anchor_to_audit_trail([], event_description="Custom anchor event")
        assert chain[0]["description"] == "Custom anchor event"

    def test_empty_artifacts(self):
        gate = BlockchainReadinessGate([])
        assert gate.artifact_count == 0
        assert gate.merkle_root == EMPTY_HASH


# ─────────────────────────────────────────────────────────────────────────────
# Integration — Full Gate Scenario
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrationScenario:

    def test_full_lifecycle(self):
        """Build gate → verify proofs → check tamper → anchor to chain."""
        artifacts = ["detector_report.json", "voltage_drop.csv", "coverage_map.dxf"]
        gate = BlockchainReadinessGate(artifacts)

        # 1. All proofs verify
        for i in range(len(artifacts)):
            proof = gate.get_proof(i)
            assert gate.verify_artifact(proof) is True

        # 2. No tampering detected
        assert gate.check_tamper(gate.merkle_root) is True

        # 3. Anchor to audit trail
        chain = gate.anchor_to_audit_trail(
            [{"event": "design_start"}],
            event_description="Design run completed",
        )
        assert len(chain) == 2
        assert chain[1]["merkle_root"] == gate.merkle_root

    def test_tampered_artifact_detected(self):
        """If an artifact changes, merkle_root changes."""
        gate1 = BlockchainReadinessGate(["art1", "art2", "art3"])
        original_root = gate1.merkle_root

        gate2 = BlockchainReadinessGate(["art1", "MODIFIED", "art3"])
        assert gate2.check_tamper(original_root) is False

    def test_added_artifact_detected(self):
        """Adding an artifact changes the merkle_root."""
        gate1 = BlockchainReadinessGate(["art1", "art2"])
        original_root = gate1.merkle_root

        gate2 = BlockchainReadinessGate(["art1", "art2", "art3"])
        assert gate2.check_tamper(original_root) is False

    def test_removed_artifact_detected(self):
        """Removing an artifact changes the merkle_root."""
        gate1 = BlockchainReadinessGate(["art1", "art2", "art3"])
        original_root = gate1.merkle_root

        gate2 = BlockchainReadinessGate(["art1", "art2"])
        assert gate2.check_tamper(original_root) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
