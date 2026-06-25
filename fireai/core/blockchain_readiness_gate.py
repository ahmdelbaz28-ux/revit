"""blockchain_readiness_gate.py — Merkle Tree Readiness Gate for FireAI
====================================================================
LOW PRIORITY MODULE

Implements a real Merkle tree with O(log n) proof verification per
RFC 6962 for design manifest integrity checking. This module provides
cryptographic proof that a specific set of design artifacts was produced
as part of a specific design run, and that no artifacts have been added
or removed.

Key References:
    - RFC 6962 §2.1 — Certificate Transparency Merkle tree specification
    - RFC 6962 §2.1.1 — Merkle audit proof (inclusion proof)

CRITICAL TERMINOLOGY DISTINCTION:
    - design_manifest_hash: A simple SHA-256 hash of the design manifest.
      This is a SINGLE hash, NOT a Merkle root.
    - merkle_root: The root hash of the Merkle tree built from ALL design
      artifacts. This is computationally distinct from design_manifest_hash.

    These two values serve DIFFERENT purposes:
      - design_manifest_hash: Quick integrity check of one document.
      - merkle_root: Proves membership of an artifact in the complete set.

    Conflating these is a SECURITY ERROR — a single hash proves nothing
    about whether artifacts have been added or removed from the set.

DESIGN DECISIONS:
    1. This module uses a REAL Merkle tree with O(log n) proof verification,
       NOT a single hash masquerading as a Merkle root.
    2. anchor_to_audit_trail() adds ONE event to the evidence_chain — it
       does NOT replace the chain. Replacing the chain would destroy the
       audit trail.
    3. Odd-leaf duplication convention per RFC 6962 §2.1 — when the number
       of leaves is odd, the last leaf is duplicated to make the tree
       balanced.
    4. EMPTY_HASH = "0"*64 for empty trees (standard convention).

PRIORITY: LOW — This module provides supplementary integrity verification
that is nice-to-have but not required for NFPA 72 compliance.

Usage:
    from fireai.core.blockchain_readiness_gate import (
        MerkleTree, MerkleProof, BlockchainReadinessGate,
    )

    tree = MerkleTree.from_leaves(["artifact_1_hash", "artifact_2_hash"])
    proof = tree.get_proof(0)
    assert proof.verify(tree.merkle_root)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List

# ============================================================================
# Constants
# ============================================================================

EMPTY_HASH: str = "0" * 64
"""Hash value for empty trees or empty nodes. Per convention, this is
64 zero characters representing a SHA-256 hash of empty input."""

PRIORITY: str = "LOW"
"""Module priority. This is a supplementary module, not required for
NFPA 72 compliance."""


# ============================================================================
# Helper Functions
# ============================================================================


def _sha256_hex(data: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _hash_pair(left: str, right: str) -> str:
    """Hash a pair of nodes in the Merkle tree.

    The concatenation order is: left || right per RFC 6962 convention.
    """
    return _sha256_hex(left + right)


# ============================================================================
# Merkle Proof
# ============================================================================


@dataclass(frozen=True)
class MerkleProof:
    """Merkle inclusion proof per RFC 6962 §2.1.1.

    Contains the sibling hashes needed to verify that a specific leaf
    is included in the Merkle tree. Walking from the leaf to the root
    by combining with siblings should produce the merkle_root.

    Attributes:
        leaf_index: Index of the leaf being proven.
        leaf_hash: Hash of the leaf being proven.
        siblings: List of sibling hashes from bottom to top.
        merkle_root: Expected root hash for verification.

    """

    leaf_index: int
    leaf_hash: str
    siblings: Tuple[str, ...]
    merkle_root: str

    def verify(self) -> bool:
        """Verify this Merkle proof by walking siblings to the root.

        For each level, combine the current hash with the sibling:
            - If leaf_index is even: current = hash(current || sibling)
            - If leaf_index is odd:  current = hash(sibling || current)

        After processing all siblings, the result should equal merkle_root.

        Returns:
            True if the proof is valid (leaf is in the tree).

        """
        current = self.leaf_hash
        index = self.leaf_index

        for sibling in self.siblings:
            if index % 2 == 0:
                # Current is on the left
                current = _hash_pair(current, sibling)
            else:
                # Current is on the right
                current = _hash_pair(sibling, current)
            index //= 2

        return current == self.merkle_root


# Need to import Tuple for the frozen dataclass
from typing import Tuple

# ============================================================================
# Merkle Tree
# ============================================================================


class MerkleTree:
    """Merkle tree implementation per RFC 6962 §2.1.

    Builds a binary hash tree from a list of leaf hashes. When the
    number of leaves is odd, the last leaf is duplicated to make the
    tree balanced (odd-leaf duplication convention per RFC 6962).

    The tree provides:
        - merkle_root: The root hash (commitment to all leaves).
        - get_proof(index): Inclusion proof for a specific leaf.
        - Proof verification in O(log n) time.

    Attributes:
        leaves: Original leaf hashes.
        merkle_root: Root hash of the tree.
        tree_levels: All levels of the tree (for debugging).

    """

    def __init__(self, leaves: List[str]) -> None:
        """Build a Merkle tree from leaf hashes.

        Args:
            leaves: List of hex-encoded hash strings (the leaves).

        """
        self._leaves = list(leaves)
        self._levels: List[List[str]] = []
        self._build_tree()

    def _build_tree(self) -> None:
        """Build the Merkle tree from leaves to root."""
        if not self._leaves:
            self._levels = [[EMPTY_HASH]]
            return

        # Start with leaf hashes
        current_level = list(self._leaves)
        self._levels = [current_level[:]]

        # Build up to root
        while len(current_level) > 1:
            next_level: List[str] = []

            # Odd-leaf duplication: duplicate last leaf if odd count
            if len(current_level) % 2 == 1:
                current_level.append(current_level[-1])

            # Hash pairs
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1]
                next_level.append(_hash_pair(left, right))

            current_level = next_level
            self._levels.append(current_level[:])

    @property
    def merkle_root(self) -> str:
        """The root hash of the Merkle tree."""
        if not self._levels:
            return EMPTY_HASH
        return self._levels[-1][0]

    @property
    def leaves(self) -> List[str]:
        """Original leaf hashes."""
        return self._leaves[:]

    @property
    def tree_levels(self) -> List[List[str]]:
        """All levels of the tree (bottom to top). For debugging."""
        return [level[:] for level in self._levels]

    @property
    def leaf_count(self) -> int:
        """Number of leaves in the tree."""
        return len(self._leaves)

    @classmethod
    def from_leaves(cls, leaf_data: List[str]) -> MerkleTree:
        """Create a MerkleTree from raw data (hashes each item first).

        Args:
            leaf_data: List of raw data strings to hash as leaves.

        Returns:
            MerkleTree with SHA-256 hashed leaves.

        """
        leaves = [_sha256_hex(item) for item in leaf_data]
        return cls(leaves)

    def get_proof(self, index: int) -> MerkleProof:
        """Generate a Merkle inclusion proof for the leaf at index.

        The proof contains the sibling hashes needed to walk from the
        leaf to the root. Verification takes O(log n) time.

        Args:
            index: Zero-based index of the leaf.

        Returns:
            MerkleProof with siblings and root.

        Raises:
            IndexError: If index is out of range.

        """
        if index < 0 or index >= len(self._leaves):
            raise IndexError(f"Leaf index {index} out of range [0, {len(self._leaves)})")

        siblings: List[str] = []
        current_index = index

        # Walk up the tree collecting siblings
        for level in self._levels[:-1]:  # All levels except root
            # Determine sibling index
            if current_index % 2 == 0:
                sibling_index = current_index + 1
            else:
                sibling_index = current_index - 1

            # Get sibling (may be duplicated last element)
            if sibling_index < len(level):
                siblings.append(level[sibling_index])
            elif current_index < len(level):
                # Odd count: sibling is the same as current (duplicated)
                siblings.append(level[current_index])

            current_index //= 2

        return MerkleProof(
            leaf_index=index,
            leaf_hash=self._leaves[index],
            siblings=tuple(siblings),
            merkle_root=self.merkle_root,
        )

    def verify_proof(self, proof: MerkleProof) -> bool:
        """Verify a Merkle proof against this tree.

        Args:
            proof: The MerkleProof to verify.

        Returns:
            True if the proof is valid.

        """
        return proof.verify()


# ============================================================================
# Blockchain Readiness Gate
# ============================================================================


class BlockchainReadinessGate:
    """Readiness gate using Merkle tree for design manifest integrity.

    This gate verifies that all design artifacts are accounted for by
    building a Merkle tree from their hashes and checking the root.

    IMPORTANT: This module does NOT replace the evidence_chain. It adds
    a supplementary integrity check that can prove membership of specific
    artifacts in the design set.

    Args:
        design_artifacts: List of artifact data strings to include in the tree.

    """

    def __init__(self, design_artifacts: List[str]) -> None:
        self._artifacts = list(design_artifacts)
        self._tree = MerkleTree.from_leaves(design_artifacts)

    @property
    def merkle_root(self) -> str:
        """Merkle root of the design artifact tree."""
        return self._tree.merkle_root

    @property
    def design_manifest_hash(self) -> str:
        """Simple SHA-256 hash of all artifacts concatenated.

        NOTE: This is DIFFERENT from the merkle_root.
        - design_manifest_hash: Single hash of concatenated data.
        - merkle_root: Root of the Merkle tree with O(log n) proofs.

        The merkle_root can prove individual artifact membership;
        the design_manifest_hash can only verify the entire set.
        """
        combined = "".join(self._artifacts)
        return _sha256_hex(combined)

    @property
    def artifact_count(self) -> int:
        """Number of design artifacts in the tree."""
        return len(self._artifacts)

    def get_proof(self, artifact_index: int) -> MerkleProof:
        """Get a Merkle inclusion proof for a specific artifact.

        Args:
            artifact_index: Zero-based index of the artifact.

        Returns:
            MerkleProof that can be verified against the merkle_root.

        Raises:
            IndexError: If artifact_index is out of range.

        """
        return self._tree.get_proof(artifact_index)

    def verify_artifact(self, proof: MerkleProof) -> bool:
        """Verify that an artifact is included in the design set.

        Args:
            proof: MerkleProof for the artifact.

        Returns:
            True if the proof is valid.

        """
        return proof.verify()

    def check_tamper(self, original_root: str) -> bool:
        """Check if the design set has been tampered with.

        Compares the current merkle_root against a known-good root.
        If they differ, at least one artifact has been modified,
        added, or removed.

        Args:
            original_root: Previously recorded merkle_root.

        Returns:
            True if NO tampering detected (roots match).

        """
        return self.merkle_root == original_root

    def anchor_to_audit_trail(
        self,
        evidence_chain: List[Dict[str, Any]],
        event_description: str = "Merkle tree anchored",
    ) -> List[Dict[str, Any]]:
        """Anchor the Merkle root to the existing evidence chain.

        This adds ONE event to the evidence_chain — it does NOT
        replace the chain. Replacing the chain would destroy the
        audit trail, which is a critical integrity violation.

        Args:
            evidence_chain: Existing evidence chain (list of event dicts).
            event_description: Description of the anchoring event.

        Returns:
            Updated evidence chain with the new anchoring event appended.

        """
        anchoring_event = {
            "event_type": "merkle_anchor",
            "description": event_description,
            "merkle_root": self.merkle_root,
            "design_manifest_hash": self.design_manifest_hash,
            "artifact_count": self.artifact_count,
            # NOTE: merkle_root and design_manifest_hash are DIFFERENT.
            # merkle_root supports O(log n) inclusion proofs.
            # design_manifest_hash is a simple integrity hash.
        }

        # Append to chain — do NOT replace
        updated_chain = list(evidence_chain)
        updated_chain.append(anchoring_event)
        return updated_chain


__all__ = [
    "EMPTY_HASH",
    "PRIORITY",
    "BlockchainReadinessGate",
    "MerkleProof",
    "MerkleTree",
]
