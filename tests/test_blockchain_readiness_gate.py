"""
Tests for blockchain_readiness_gate.py — Merkle Tree Readiness Gate
===================================================================
Comprehensive test suite covering:
    - Merkle tree construction
    - Merkle proof verification
    - Tamper detection
    - Audit trail anchoring (does NOT replace evidence_chain)
    - Odd-leaf handling (RFC 6962 convention)
    - Tree internals
    - design_manifest_hash vs merkle_root distinction
"""

import hashlib
import pytest

from fireai.core.blockchain_readiness_gate import (
    EMPTY_HASH,
    PRIORITY,
    MerkleProof,
    MerkleTree,
    BlockchainReadinessGate,
    _sha256_hex,
    _hash_pair,
)


# ============================================================================
# Helper Function Tests
# ============================================================================

class TestHelperFunctions:
    """Test internal helper functions."""

    def test_sha256_hex_produces_64_char_hex(self):
        """SHA-256 hex digest should be 64 characters."""
        result = _sha256_hex("test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_sha256_hex_deterministic(self):
        """Same input should produce same hash."""
        assert _sha256_hex("test") == _sha256_hex("test")

    def test_hash_pair_order_matters(self):
        """hash_pair(A, B) != hash_pair(B, A) per RFC 6962 convention."""
        a = _sha256_hex("leaf_a")
        b = _sha256_hex("leaf_b")
        assert _hash_pair(a, b) != _hash_pair(b, a)

    def test_hash_pair_uses_concatenation(self):
        """hash_pair should use left||right concatenation."""
        a = "a"
        b = "b"
        expected = hashlib.sha256((a + b).encode("utf-8")).hexdigest()
        assert _hash_pair(a, b) == expected


# ============================================================================
# Merkle Tree Construction Tests
# ============================================================================

class TestMerkleTreeConstruction:
    """Test Merkle tree building."""

    def test_single_leaf(self):
        """Tree with one leaf should have root = hash of that leaf."""
        leaf = _sha256_hex("item_1")
        tree = MerkleTree([leaf])
        assert tree.merkle_root == leaf
        assert tree.leaf_count == 1

    def test_two_leaves(self):
        """Tree with two leaves should have root = hash(hash(a) + hash(b))."""
        leaf_a = _sha256_hex("item_a")
        leaf_b = _sha256_hex("item_b")
        tree = MerkleTree([leaf_a, leaf_b])
        expected_root = _hash_pair(leaf_a, leaf_b)
        assert tree.merkle_root == expected_root

    def test_three_leaves_odd_duplication(self):
        """Tree with 3 leaves: last leaf is duplicated per RFC 6962."""
        leaf_a = _sha256_hex("a")
        leaf_b = _sha256_hex("b")
        leaf_c = _sha256_hex("c")
        tree = MerkleTree([leaf_a, leaf_b, leaf_c])

        # Level 0: [a, b, c, c] (c duplicated)
        # Level 1: [hash(a+b), hash(c+c)]
        # Level 2: [root]
        level_1_left = _hash_pair(leaf_a, leaf_b)
        level_1_right = _hash_pair(leaf_c, leaf_c)
        expected_root = _hash_pair(level_1_left, level_1_right)
        assert tree.merkle_root == expected_root

    def test_four_leaves(self):
        """Tree with 4 leaves: balanced, no duplication needed."""
        leaves = [_sha256_hex(f"item_{i}") for i in range(4)]
        tree = MerkleTree(leaves)

        # Level 1: [hash(0+1), hash(2+3)]
        l1_left = _hash_pair(leaves[0], leaves[1])
        l1_right = _hash_pair(leaves[2], leaves[3])
        expected_root = _hash_pair(l1_left, l1_right)
        assert tree.merkle_root == expected_root

    def test_empty_tree(self):
        """Empty tree should have EMPTY_HASH as root."""
        tree = MerkleTree([])
        assert tree.merkle_root == EMPTY_HASH
        assert tree.leaf_count == 0

    def test_from_leaves_hashes_data(self):
        """from_leaves should hash each data item before building tree."""
        tree = MerkleTree.from_leaves(["item_1", "item_2"])
        expected_leaves = [_sha256_hex("item_1"), _sha256_hex("item_2")]
        assert tree.leaves == expected_leaves

    def test_leaves_not_mutated(self):
        """Tree should not mutate the original leaves list."""
        leaves = [_sha256_hex("a"), _sha256_hex("b")]
        original = list(leaves)
        tree = MerkleTree(leaves)
        assert leaves == original


# ============================================================================
# Merkle Proof Tests
# ============================================================================

class TestMerkleProof:
    """Test Merkle inclusion proofs."""

    def test_proof_single_leaf(self):
        """Proof for single-leaf tree should have no siblings."""
        leaf = _sha256_hex("only_item")
        tree = MerkleTree([leaf])
        proof = tree.get_proof(0)

        assert proof.leaf_hash == leaf
        assert proof.siblings == ()
        assert proof.verify() is True

    def test_proof_two_leaves(self):
        """Proof for 2-leaf tree should have 1 sibling."""
        leaf_a = _sha256_hex("a")
        leaf_b = _sha256_hex("b")
        tree = MerkleTree([leaf_a, leaf_b])

        proof_a = tree.get_proof(0)
        assert len(proof_a.siblings) == 1
        assert proof_a.siblings[0] == leaf_b
        assert proof_a.verify() is True

        proof_b = tree.get_proof(1)
        assert proof_b.siblings[0] == leaf_a
        assert proof_b.verify() is True

    def test_proof_four_leaves(self):
        """Proof for 4-leaf tree should have 2 siblings (log2(4) = 2)."""
        leaves = [_sha256_hex(f"item_{i}") for i in range(4)]
        tree = MerkleTree(leaves)

        for i in range(4):
            proof = tree.get_proof(i)
            assert len(proof.siblings) == 2
            assert proof.verify() is True

    def test_proof_eight_leaves(self):
        """Proof for 8-leaf tree should have 3 siblings (log2(8) = 3)."""
        leaves = [_sha256_hex(f"item_{i}") for i in range(8)]
        tree = MerkleTree(leaves)

        for i in range(8):
            proof = tree.get_proof(i)
            assert len(proof.siblings) == 3
            assert proof.verify() is True

    def test_proof_odd_count(self):
        """Proofs should work with odd number of leaves (RFC 6962)."""
        leaves = [_sha256_hex(f"item_{i}") for i in range(5)]
        tree = MerkleTree(leaves)

        for i in range(5):
            proof = tree.get_proof(i)
            assert proof.verify() is True

    def test_proof_index_out_of_range(self):
        """Out-of-range index should raise IndexError."""
        leaves = [_sha256_hex("a"), _sha256_hex("b")]
        tree = MerkleTree(leaves)

        with pytest.raises(IndexError):
            tree.get_proof(5)

    def test_proof_negative_index(self):
        """Negative index should raise IndexError."""
        leaves = [_sha256_hex("a")]
        tree = MerkleTree(leaves)

        with pytest.raises(IndexError):
            tree.get_proof(-1)

    def test_tampered_proof_detected(self):
        """Modified leaf hash should cause proof verification to fail."""
        leaves = [_sha256_hex(f"item_{i}") for i in range(4)]
        tree = MerkleTree(leaves)

        proof = tree.get_proof(0)
        # Tamper with the leaf hash
        tampered_proof = MerkleProof(
            leaf_index=0,
            leaf_hash=_sha256_hex("tampered"),
            siblings=proof.siblings,
            merkle_root=proof.merkle_root,
        )
        assert tampered_proof.verify() is False

    def test_tampered_sibling_detected(self):
        """Modified sibling should cause proof verification to fail."""
        leaves = [_sha256_hex(f"item_{i}") for i in range(4)]
        tree = MerkleTree(leaves)

        proof = tree.get_proof(0)
        tampered_siblings = tuple(_sha256_hex("bad") if i == 0 else s
                                  for i, s in enumerate(proof.siblings))
        tampered_proof = MerkleProof(
            leaf_index=0,
            leaf_hash=proof.leaf_hash,
            siblings=tampered_siblings,
            merkle_root=proof.merkle_root,
        )
        assert tampered_proof.verify() is False

    def test_tampered_root_detected(self):
        """Wrong merkle_root should cause proof verification to fail."""
        leaves = [_sha256_hex(f"item_{i}") for i in range(4)]
        tree = MerkleTree(leaves)

        proof = tree.get_proof(0)
        tampered_proof = MerkleProof(
            leaf_index=0,
            leaf_hash=proof.leaf_hash,
            siblings=proof.siblings,
            merkle_root=_sha256_hex("wrong_root"),
        )
        assert tampered_proof.verify() is False


# ============================================================================
# Blockchain Readiness Gate Tests
# ============================================================================

class TestBlockchainReadinessGate:
    """Test BlockchainReadinessGate high-level API."""

    def test_merkle_root_computed(self):
        """Gate should compute a valid merkle_root."""
        gate = BlockchainReadinessGate(["artifact_1", "artifact_2", "artifact_3"])
        assert len(gate.merkle_root) == 64

    def test_design_manifest_hash_different_from_merkle_root(self):
        """design_manifest_hash must be DIFFERENT from merkle_root.

        These serve different purposes:
          - merkle_root: Supports O(log n) inclusion proofs
          - design_manifest_hash: Simple hash of concatenated data
        Conflating them is a SECURITY ERROR.
        """
        gate = BlockchainReadinessGate(["artifact_1", "artifact_2", "artifact_3"])
        assert gate.design_manifest_hash != gate.merkle_root

    def test_artifact_count(self):
        """artifact_count should match number of artifacts."""
        gate = BlockchainReadinessGate(["a", "b", "c"])
        assert gate.artifact_count == 3

    def test_get_proof_and_verify(self):
        """Proof from get_proof should verify successfully."""
        gate = BlockchainReadinessGate(["artifact_1", "artifact_2", "artifact_3"])
        proof = gate.get_proof(0)
        assert gate.verify_artifact(proof) is True
        assert proof.verify() is True

    def test_check_tamper_no_tamper(self):
        """check_tamper should return True when root matches."""
        gate = BlockchainReadinessGate(["a", "b", "c"])
        root = gate.merkle_root
        assert gate.check_tamper(root) is True

    def test_check_tamper_detected(self):
        """check_tamper should return False when root doesn't match."""
        gate1 = BlockchainReadinessGate(["a", "b", "c"])
        gate2 = BlockchainReadinessGate(["a", "b", "modified"])
        assert gate2.check_tamper(gate1.merkle_root) is False

    def test_anchor_to_audit_trail_appends(self):
        """anchor_to_audit_trail should APPEND, not replace.

        CRITICAL: Replacing the evidence chain would destroy the
        audit trail. This is a critical integrity violation.
        """
        gate = BlockchainReadinessGate(["artifact_1", "artifact_2"])
        existing_chain = [
            {"event_type": "analysis", "data": "run_1"},
            {"event_type": "review", "data": "checked"},
        ]
        original_len = len(existing_chain)

        updated_chain = gate.anchor_to_audit_trail(existing_chain)

        # Should be longer by 1
        assert len(updated_chain) == original_len + 1
        # Original events should be preserved
        assert updated_chain[0]["event_type"] == "analysis"
        assert updated_chain[1]["event_type"] == "review"
        # New event should be the anchor
        assert updated_chain[-1]["event_type"] == "merkle_anchor"
        assert updated_chain[-1]["merkle_root"] == gate.merkle_root

    def test_anchor_preserves_original_chain(self):
        """Anchoring should not modify the original chain list."""
        gate = BlockchainReadinessGate(["a", "b"])
        original_chain = [{"event": "test"}]
        original_copy = list(original_chain)

        gate.anchor_to_audit_trail(original_chain)

        # Original should be unchanged
        assert original_chain == original_copy

    def test_anchor_event_has_both_hashes(self):
        """Anchor event should contain both merkle_root and design_manifest_hash."""
        gate = BlockchainReadinessGate(["a", "b", "c"])
        chain = gate.anchor_to_audit_trail([])
        event = chain[-1]

        assert "merkle_root" in event
        assert "design_manifest_hash" in event
        # They must be different
        assert event["merkle_root"] != event["design_manifest_hash"]


# ============================================================================
# Odd-Leaf Handling Tests
# ============================================================================

class TestOddLeafHandling:
    """Test RFC 6962 odd-leaf duplication convention."""

    def test_odd_leaf_count_produces_valid_proofs(self):
        """Odd number of leaves should produce valid proofs for all leaves."""
        for count in [1, 3, 5, 7, 9]:
            leaves = [_sha256_hex(f"item_{i}") for i in range(count)]
            tree = MerkleTree(leaves)
            for i in range(count):
                proof = tree.get_proof(i)
                assert proof.verify() is True, (
                    f"Proof for leaf {i} in {count}-leaf tree failed"
                )

    def test_five_leaves_tree_structure(self):
        """5-leaf tree should have correct structure."""
        leaves = [_sha256_hex(f"item_{i}") for i in range(5)]
        tree = MerkleTree(leaves)
        # Should have 3 levels: leaves, intermediate, root
        assert len(tree.tree_levels) >= 2

    def test_single_leaf_proof_no_siblings(self):
        """Single leaf should have no siblings in proof."""
        tree = MerkleTree([_sha256_hex("only")])
        proof = tree.get_proof(0)
        assert len(proof.siblings) == 0


# ============================================================================
# Priority and Constants Tests
# ============================================================================

class TestPriorityAndConstants:
    """Test module priority and constants."""

    def test_priority_is_low(self):
        """Module priority should be LOW."""
        assert PRIORITY == "LOW"

    def test_empty_hash_is_64_zeros(self):
        """EMPTY_HASH should be 64 zero characters."""
        assert EMPTY_HASH == "0" * 64
        assert len(EMPTY_HASH) == 64

    def test_merkle_proof_is_frozen(self):
        """MerkleProof should be immutable."""
        proof = MerkleProof(
            leaf_index=0,
            leaf_hash=_sha256_hex("test"),
            siblings=(),
            merkle_root=_sha256_hex("root"),
        )
        with pytest.raises(AttributeError):
            proof.leaf_hash = "modified"


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflows."""

    def test_full_workflow_create_verify_detect(self):
        """Complete workflow: create tree, verify proofs, detect tamper."""
        artifacts = [f"design_artifact_{i}" for i in range(10)]
        gate = BlockchainReadinessGate(artifacts)

        # Record root
        original_root = gate.merkle_root

        # Verify all artifacts
        for i in range(len(artifacts)):
            proof = gate.get_proof(i)
            assert proof.verify() is True

        # Simulate tampering
        tampered_gate = BlockchainReadinessGate(
            artifacts[:8] + ["TAMPERED", "design_artifact_9"]
        )
        assert tampered_gate.check_tamper(original_root) is False

    def test_large_tree_proofs_work(self):
        """Merkle proofs should work for large trees (100 leaves)."""
        leaves = [_sha256_hex(f"leaf_{i}") for i in range(100)]
        tree = MerkleTree(leaves)

        # Verify a sample of proofs
        for i in [0, 25, 50, 75, 99]:
            proof = tree.get_proof(i)
            assert proof.verify() is True

    def test_tree_level_structure(self):
        """Tree levels should have correct sizes for balanced tree."""
        leaves = [_sha256_hex(f"item_{i}") for i in range(8)]
        tree = MerkleTree(leaves)

        levels = tree.tree_levels
        assert len(levels[0]) == 8  # Leaves
        assert len(levels[1]) == 4  # Level 1
        assert len(levels[2]) == 2  # Level 2
        assert len(levels[3]) == 1  # Root
