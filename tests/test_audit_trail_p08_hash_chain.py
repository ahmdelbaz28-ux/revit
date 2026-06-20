"""
tests/test_audit_trail_p08_hash_chain.py — P0.8 regression tests
================================================================

Regression coverage for the hash-chaining fix in
fireai/core/audit_trail.py.

Pre-P0.8 design verified only per-entry integrity:
  verify_integrity() = ∀ entry: _compute_hash(entry) == entry.entry_hash

This caught content tampering but did NOT catch:
  - INSERTION of forged entries (each forged entry has a valid hash)
  - DELETION of entries (no link between consecutive entries)
  - REORDERING of entries (no sequence integrity)

P0.8 adds prev_hash chaining:
  H(i) = SHA256(content(i) || prev_hash(i))
  prev_hash(0) = "GENESIS"
  prev_hash(i) = H(i-1) for i > 0

These tests verify the chain catches all four tampering modes.

Per agent.md Rule 10 — these tests are NEVER modified; only production
code is modified. A failure here means production code is wrong.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from fireai.core.audit_trail import (
    AuditEntry,
    AuditTrail,
    GENESIS_PREV_HASH,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def populated_trail() -> AuditTrail:
    """A trail with 3 entries for tampering tests."""
    trail = AuditTrail("test_project", "FL01")
    trail.log_placement("R1", 3, "smoke_photoelectric", 99.5, [(1, 1), (2, 2)])
    trail.log_rejection("R2", "Invalid room type")
    trail.log_coverage_result("R1", 3, 99.5, 0.20, "PASS")
    return trail


# ── Chain integrity tests ───────────────────────────────────────────────────


class TestAuditTrailHashChain:
    """P0.8: prev_hash chaining makes the audit trail tamper-evident
    against insertion, deletion, reordering, and content modification."""

    def test_empty_trail_verifies(self):
        """An empty trail has no chain to break — must verify True."""
        trail = AuditTrail("p08_empty")
        assert trail.verify_integrity() is True

    def test_single_entry_has_genesis_prev_hash(self):
        """The first entry's prev_hash MUST be the GENESIS sentinel."""
        trail = AuditTrail("p08_single")
        trail.log_placement("R1", 3, "smoke", 99.5, [(1, 1)])
        entries = trail.entries()
        assert len(entries) == 1
        assert entries[0].prev_hash == GENESIS_PREV_HASH
        assert trail.verify_integrity() is True

    def test_chain_links_correct(self, populated_trail):
        """Each entry's prev_hash MUST equal the previous entry's entry_hash."""
        entries = populated_trail.entries()
        assert len(entries) == 3
        assert entries[0].prev_hash == GENESIS_PREV_HASH
        assert entries[1].prev_hash == entries[0].entry_hash
        assert entries[2].prev_hash == entries[1].entry_hash
        assert populated_trail.verify_integrity() is True

    def test_tampering_content_breaks_chain(self, populated_trail):
        """Modifying an entry's content changes its hash → breaks the
        next entry's prev_hash pointer → chain verification fails."""
        assert populated_trail.verify_integrity() is True
        # Tamper with entry 1's content (bypass frozen=True to simulate
        # an attacker with direct memory access or a serialized-then-
        # modified audit trail).
        object.__setattr__(populated_trail._entries[1], "operation", "TAMPERED")
        assert populated_trail.verify_integrity() is False, (
            "Content tampering must break chain verification"
        )

    def test_deletion_breaks_chain(self, populated_trail):
        """Removing an entry leaves a gap — the next entry's prev_hash
        still points to the deleted entry's hash, not the new predecessor's."""
        assert populated_trail.verify_integrity() is True
        # Delete the middle entry
        del populated_trail._entries[1]
        assert populated_trail.verify_integrity() is False, (
            "Deletion must break chain verification"
        )

    def test_reordering_breaks_chain(self, populated_trail):
        """Swapping two entries makes their prev_hash pointers inconsistent."""
        assert populated_trail.verify_integrity() is True
        # Swap entries 0 and 1
        populated_trail._entries[0], populated_trail._entries[1] = (
            populated_trail._entries[1],
            populated_trail._entries[0],
        )
        assert populated_trail.verify_integrity() is False, (
            "Reordering must break chain verification"
        )

    def test_insertion_of_forged_entry_breaks_chain(self, populated_trail):
        """Inserting a forged entry between two real ones breaks the chain
        because the real entry after the forged one still has its prev_hash
        pointing to the entry BEFORE the forged one."""
        assert populated_trail.verify_integrity() is True

        # Construct a forged entry with the correct prev_hash to chain
        # off entry 0 (so the forged entry itself appears valid).
        forged = AuditEntry(
            timestamp_utc="2026-01-01T00:00:00+00:00",
            room_id="FORGED",
            operation="FORGED_OPERATION",
            inputs={},
            outputs={},
            nfpa_reference="N/A",
        )
        # Set its prev_hash to entry 0's hash, then recompute its own hash
        object.__setattr__(forged, "prev_hash", populated_trail._entries[0].entry_hash)
        object.__setattr__(forged, "entry_hash", forged._compute_hash())

        # Insert it at position 1 (between entry 0 and the original entry 1)
        populated_trail._entries.insert(1, forged)

        # The forged entry's own hash is valid, but the original entry 1
        # (now at position 2) has prev_hash = old entry 0's hash, NOT
        # the forged entry's hash. So verification must fail.
        assert populated_trail.verify_integrity() is False, (
            "Forged insertion must break chain verification (the entry "
            "after the forged one still points to the pre-forgery predecessor)"
        )

    def test_replacing_entry_with_different_content_breaks_chain(
        self, populated_trail
    ):
        """Replacing an entire entry with a different one (even if it
        has a valid hash) breaks the chain — the next entry's prev_hash
        no longer matches the replacement's hash."""
        assert populated_trail.verify_integrity() is True

        # Construct a replacement for entry 1 with completely different
        # content but the same prev_hash (so it chains off entry 0).
        replacement = AuditEntry(
            timestamp_utc="2026-12-31T23:59:59+00:00",
            room_id="REPLACED",
            operation="REPLACED_OPERATION",
            inputs={"fake": "data"},
            outputs={"fake": "result"},
            nfpa_reference="FAKE",
        )
        object.__setattr__(
            replacement, "prev_hash", populated_trail._entries[0].entry_hash
        )
        object.__setattr__(replacement, "entry_hash", replacement._compute_hash())

        # Replace entry 1
        populated_trail._entries[1] = replacement

        # The replacement's own hash is valid, but entry 2's prev_hash
        # still points to the ORIGINAL entry 1's hash, not the
        # replacement's hash. So verification must fail.
        assert populated_trail.verify_integrity() is False, (
            "Entry replacement must break chain verification"
        )

    def test_to_dict_includes_prev_hash(self, populated_trail):
        """Serialized audit entries MUST include prev_hash so the chain
        can be verified after deserialization."""
        for entry in populated_trail.entries():
            d = entry.to_dict()
            assert "prev_hash" in d, "to_dict() must include prev_hash"
            assert "entry_hash" in d, "to_dict() must include entry_hash"

    def test_chain_grows_correctly_across_many_entries(self):
        """Adding many entries must produce a consistent chain — no
        off-by-one errors in prev_hash assignment."""
        trail = AuditTrail("p08_long")
        for i in range(50):
            trail.log_placement(f"R{i}", i + 1, "smoke", 99.0, [(i, i)])
        assert trail.count() == 50
        assert trail.verify_integrity() is True
        # Verify chain links explicitly
        entries = trail.entries()
        prev = GENESIS_PREV_HASH
        for entry in entries:
            assert entry.prev_hash == prev, (
                f"Chain broken at entry {entry.room_id}: prev_hash mismatch"
            )
            prev = entry.entry_hash


# ── Thread safety tests (chain must not fork under concurrency) ────────────


class TestAuditTrailChainThreadSafety:
    """P0.8: The chain construction in _add() MUST be atomic — two
    concurrent appends must NOT both read the same "last entry" and
    chain off it, producing a forked chain."""

    def test_concurrent_appends_produce_valid_chain(self):
        """50 threads each append 10 entries; the result must be a
        single non-forked chain of 500 entries that verifies cleanly."""
        import threading

        trail = AuditTrail("p08_concurrent")
        barrier = threading.Barrier(50)  # synchronize start

        def worker():
            barrier.wait()
            for i in range(10):
                trail.log_placement(f"R{i}", i, "smoke", 99.0, [(i, i)])

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert trail.count() == 500, (
            f"Expected 500 entries, got {trail.count()} (race condition in _add)"
        )
        assert trail.verify_integrity() is True, (
            "Concurrent appends must produce a single non-forked chain"
        )
