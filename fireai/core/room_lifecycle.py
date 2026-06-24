"""room_lifecycle.py — FireAI Room Lifecycle State Machine
========================================================
NFPA 72-2022 compliant state machine that transforms the fire safety
system from a stateless "calculator" into a proper engineering system
with full lifecycle management, state tracking, and workflow enforcement.

Design Principles:
  - Finite State Machine with strictly validated transitions
  - Every transition is recorded with full audit metadata
  - Thread-safe via threading.Lock for concurrent room processing
  - EventBus integration for real-time lifecycle notifications
  - Zero external dependencies beyond stdlib + existing fireai modules

State Flow (happy path):
  PENDING → ANALYZING → OPTIMIZED → VERIFYING → VERIFIED → CERTIFYING → CERTIFIED

Branching paths:
  VERIFYING → WARNING (2/3 engines agree, needs investigation)
  WARNING → VERIFYING (retry) or VERIFIED (PE override)
  Any stage → FAILED (error / validation failure)
  FAILED → PENDING (retry)
  CERTIFIED → REJECTED (AHJ override)
  REJECTED → PENDING (resubmit)

NFPA 72-2022 Rationale:
  The lifecycle mirrors the engineering workflow mandated by NFPA 72:
    1. Room data received (PENDING)
    2. Placement optimization per §17.6.3 (ANALYZING → OPTIMIZED)
    3. Triple consensus verification per §17.7.4.2.3.1 (VERIFYING → VERIFIED/WARNING)
    4. Proof certificate with SHA-256 seal (CERTIFYING → CERTIFIED)
    5. AHJ review (CERTIFIED → REJECTED if overridden)

Usage:
    from fireai.core.room_lifecycle import (
        RoomState, RoomTransition, RoomLifecycle, RoomLifecycleManager,
    )

    lifecycle = RoomLifecycle(room_id="R-101")
    lifecycle.transition_to(RoomState.ANALYZING, reason="Starting placement", actor="system")
    lifecycle.transition_to(RoomState.OPTIMIZED, reason="3 detectors placed", actor="system")
    # ... continue through the pipeline
"""

from __future__ import annotations

import enum
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .event_bus import EventBus

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# RoomState Enum
# ═══════════════════════════════════════════════════════════════════════


class RoomState(enum.Enum):
    """Finite states for room analysis lifecycle.

    Each state represents a distinct phase in the NFPA 72-2022 compliant
    engineering workflow. Transitions between states are strictly validated
    to prevent illegal state changes (e.g. jumping from PENDING to CERTIFIED).

    States:
        PENDING    — Room received, not yet analyzed.
        ANALYZING  — Placement optimization in progress (§17.6.3).
        OPTIMIZED  — Placement complete, awaiting verification.
        VERIFYING  — Triple consensus verification in progress (§17.7.4.2.3.1).
        VERIFIED   — All 3 engines agree (3/3 PASS). Safe to proceed.
        WARNING    — 2/3 engines agree. Requires investigation or PE review.
        CERTIFYING — Proof certificate generation in progress.
        CERTIFIED  — Proof certificate generated and sealed with SHA-256.
        FAILED     — Analysis failed at any stage. Can retry.
        REJECTED   — AHJ rejected (manual override). Can resubmit.
    """

    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    OPTIMIZED = "OPTIMIZED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    WARNING = "WARNING"
    CERTIFYING = "CERTIFYING"
    CERTIFIED = "CERTIFIED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


# ═══════════════════════════════════════════════════════════════════════
# Legal Transition Map
# ═══════════════════════════════════════════════════════════════════════

LEGAL_TRANSITIONS: Dict[RoomState, set] = {
    RoomState.PENDING: {RoomState.ANALYZING, RoomState.FAILED},
    RoomState.ANALYZING: {RoomState.OPTIMIZED, RoomState.FAILED},
    RoomState.OPTIMIZED: {RoomState.VERIFYING, RoomState.FAILED},
    RoomState.VERIFYING: {RoomState.VERIFIED, RoomState.WARNING, RoomState.FAILED},
    RoomState.WARNING: {RoomState.VERIFYING, RoomState.VERIFIED, RoomState.FAILED},
    RoomState.VERIFIED: {RoomState.CERTIFYING, RoomState.FAILED},
    RoomState.CERTIFYING: {RoomState.CERTIFIED, RoomState.FAILED},
    RoomState.CERTIFIED: {RoomState.REJECTED},
    RoomState.FAILED: {RoomState.PENDING},
    RoomState.REJECTED: {RoomState.PENDING},
}


# ═══════════════════════════════════════════════════════════════════════
# RoomTransition Dataclass
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RoomTransition:
    """Immutable record of a single state transition in the room lifecycle.

    Every transition is recorded with full audit metadata for NFPA 72
    compliance and AHJ review. The frozen dataclass ensures that transition
    records cannot be modified after creation (audit integrity).

    Attributes:
        from_state: The state before this transition.
        to_state: The state after this transition.
        timestamp: ISO 8601 UTC timestamp when the transition occurred.
        reason: Human-readable explanation for the transition.
        actor: Who initiated the transition: "system", "pe" (Professional
            Engineer), or "ahj" (Authority Having Jurisdiction).
        metadata: Optional dict for extra information (e.g. engine results,
            error details, detector counts, coverage percentages).

    """

    from_state: RoomState
    to_state: RoomState
    timestamp: str
    reason: str
    actor: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize transition to a plain dictionary."""
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "actor": self.actor,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════
# RoomLifecycle Class
# ═══════════════════════════════════════════════════════════════════════


class RoomLifecycle:
    """State machine for a single room's analysis lifecycle.

    Maintains the current state and full transition history for one room.
    All transitions are validated against the LEGAL_TRANSITIONS map and
    recorded as immutable RoomTransition objects.

    Thread Safety:
        All public methods are protected by a threading.Lock, making
        this class safe for concurrent access (e.g. FastAPI async handlers
        or multi-threaded pipeline processing).

    EventBus Integration:
        Each successful transition publishes a "room.lifecycle.changed"
        event via the singleton EventBus, enabling real-time monitoring
        and Digital Twin synchronization.

    Example:
        lc = RoomLifecycle(room_id="R-101")
        lc.transition_to(RoomState.ANALYZING, "Begin placement", "system")
        lc.transition_to(RoomState.OPTIMIZED, "3 detectors placed", "system")
        assert lc.state == RoomState.OPTIMIZED
        assert lc.can_transition_to(RoomState.VERIFYING)
        assert not lc.can_transition_to(RoomState.CERTIFIED)

    """

    def __init__(
        self,
        room_id: str,
        bus: Optional[EventBus] = None,
    ) -> None:
        """Initialize a new room lifecycle in PENDING state.

        Args:
            room_id: Unique identifier for this room (e.g. "R-101").
            bus: Optional EventBus instance. If None, uses the singleton.

        """
        self._room_id = room_id
        self._state = RoomState.PENDING
        self._transitions: List[RoomTransition] = []
        self._state_entered_at: str = datetime.now(timezone.utc).isoformat()
        # ✅ FIX: Use RLock to prevent deadlock — RoomLifecycle.to_dict()
        # calls methods that also acquire the lock.
        self._lock = threading.RLock()
        self._bus = bus  # None → lazy init from singleton

    # ── Properties ────────────────────────────────────────────────────

    @property
    def room_id(self) -> str:
        """Unique identifier for this room."""
        return self._room_id

    @property
    def state(self) -> RoomState:
        """Current lifecycle state (thread-safe read)."""
        with self._lock:
            return self._state

    @property
    def history(self) -> List[RoomTransition]:
        """Full transition history (returns a copy for thread safety)."""
        with self._lock:
            return list(self._transitions)

    @property
    def state_entered_at(self) -> str:
        """ISO 8601 UTC timestamp when the current state was entered."""
        with self._lock:
            return self._state_entered_at

    # ── Transition Validation ─────────────────────────────────────────

    def can_transition_to(self, new_state: RoomState) -> bool:
        """Check whether a transition to new_state is legal from current state.

        Args:
            new_state: The target state to check.

        Returns:
            True if the transition is legal, False otherwise.

        Note:
            This method is thread-safe and does NOT modify state.

        """
        with self._lock:
            allowed = LEGAL_TRANSITIONS.get(self._state, set())
            return new_state in allowed

    # ── State Transition ──────────────────────────────────────────────

    def transition_to(
        self,
        new_state: RoomState,
        reason: str,
        actor: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RoomTransition:
        """Execute a validated state transition and record it.

        Validates the transition against LEGAL_TRANSITIONS, creates an
        immutable RoomTransition record, updates the current state, and
        publishes an EventBus notification.

        Args:
            new_state: Target state to transition to.
            reason: Human-readable explanation for the transition.
            actor: Who initiated the transition ("system", "pe", or "ahj").
            metadata: Optional dict for extra information (engine results,
                error details, detector counts, etc.).

        Returns:
            The RoomTransition record that was created.

        Raises:
            ValueError: If the transition is not legal from the current state.

        Example:
            lc.transition_to(
                RoomState.VERIFYING,
                reason="Starting triple consensus verification",
                actor="system",
                metadata={"engines": ["analytical", "voronoi", "grid"]},
            )

        """
        with self._lock:
            allowed = LEGAL_TRANSITIONS.get(self._state, set())
            if new_state not in allowed:
                raise ValueError(
                    f"Illegal transition for room {self._room_id}: "
                    f"{self._state.value} → {new_state.value}. "
                    f"Allowed transitions from {self._state.value}: "
                    f"{sorted(s.value for s in allowed)}"
                )

            now = datetime.now(timezone.utc).isoformat()
            transition = RoomTransition(
                from_state=self._state,
                to_state=new_state,
                timestamp=now,
                reason=reason,
                actor=actor,
                metadata=metadata or {},
            )

            # Record transition and update state
            self._transitions.append(transition)
            old_state = self._state
            self._state = new_state
            self._state_entered_at = now

        # Publish event outside the lock to prevent deadlock
        # (EventBus has its own lock internally)
        self._publish_transition_event(old_state, new_state, reason, actor)

        logger.info(
            "Room %s: %s → %s (actor=%s, reason=%s)",
            self._room_id,
            old_state.value,
            new_state.value,
            actor,
            reason,
        )

        return transition

    def _publish_transition_event(
        self,
        from_state: RoomState,
        to_state: RoomState,
        reason: str,
        actor: str,
    ) -> None:
        """Publish a lifecycle change event to the EventBus.

        Args:
            from_state: State before transition.
            to_state: State after transition.
            reason: Transition reason.
            actor: Who initiated the transition.

        """
        try:
            # FIX-3: Always use the singleton EventBus to ensure all
            # modules (pipeline, twin, lifecycle) share the SAME bus.
            # The old code used EventBus() which created a NEW instance,
            # so lifecycle events never reached the twin or pipeline.
            bus = self._bus if self._bus is not None else EventBus.instance()
            bus.publish(
                "room.lifecycle.changed",
                {
                    "room_id": self._room_id,
                    "from_state": from_state.value,
                    "to_state": to_state.value,
                    "reason": reason,
                    "actor": actor,
                },
                source="room_lifecycle",
            )
        except Exception as exc:
            # Event publishing failure must NOT break the state machine.
            # Log the error but continue — the transition is already recorded.
            logger.error(
                "Failed to publish lifecycle event for room %s: %s",
                self._room_id,
                exc,
            )

    # ── Duration Tracking ─────────────────────────────────────────────

    def duration_in_state(self) -> float:
        """Return the number of seconds spent in the current state.

        Returns:
            Seconds (as a float) since the current state was entered.
            Sub-second precision depends on the OS clock.

        Example:
            lc.transition_to(RoomState.ANALYZING, "Start", "system")
            time.sleep(2.5)
            assert lc.duration_in_state() >= 2.0

        """
        with self._lock:
            entered = self._state_entered_at

        entered_dt = datetime.fromisoformat(entered)
        now_dt = datetime.now(timezone.utc)
        delta = now_dt - entered_dt
        return delta.total_seconds()

    # ── Utility ───────────────────────────────────────────────────────

    def is_terminal(self) -> bool:
        """Check if the current state is terminal (CERTIFIED or REJECTED).

        Terminal states have no forward transitions (only backward
        retry/resubmit paths). This is useful for pipeline completion
        checks.

        Returns:
            True if the room is in a terminal state.

        """
        with self._lock:
            return self._state in {RoomState.CERTIFIED, RoomState.REJECTED}

    def is_failed(self) -> bool:
        """Check if the room is in FAILED state.

        Returns:
            True if the room is in FAILED state.

        """
        with self._lock:
            return self._state == RoomState.FAILED

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the lifecycle state and history to a dictionary.

        Returns:
            Dictionary containing room_id, current state, transition count,
            state entered timestamp, and full transition history.

        """
        with self._lock:
            return {
                "room_id": self._room_id,
                "state": self._state.value,
                "state_entered_at": self._state_entered_at,
                "transition_count": len(self._transitions),
                "history": [t.to_dict() for t in self._transitions],
            }

    def __repr__(self) -> str:
        return f"RoomLifecycle(room_id={self._room_id!r}, state={self._state.value})"


# ═══════════════════════════════════════════════════════════════════════
# RoomLifecycleManager Class
# ═══════════════════════════════════════════════════════════════════════


class RoomLifecycleManager:
    """Manages lifecycles for all rooms in a building.

    Provides centralized access to room lifecycles, building-level status
    aggregation, and certification checks. Thread-safe for concurrent
    room processing across multiple floors or zones.

    The manager acts as a registry — rooms are registered with
    ``register_room()`` and accessed via ``get_room()``. Each room
    gets its own RoomLifecycle instance with independent state.

    Building Certification:
        A building is "all certified" only when EVERY room has reached
        the CERTIFIED state. This is a hard gate for AHJ submission.

    Example:
        manager = RoomLifecycleManager()
        manager.register_room("R-101")
        manager.register_room("R-102")

        lc = manager.get_room("R-101")
        lc.transition_to(RoomState.ANALYZING, "Start analysis", "system")

        status = manager.building_status()
        # {"PENDING": 1, "ANALYZING": 1, ...}

        assert not manager.all_certified()

    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        """Initialize the lifecycle manager.

        Args:
            bus: Optional EventBus instance. If None, the singleton
                is used for each room's lifecycle.

        """
        self._rooms: Dict[str, RoomLifecycle] = {}
        # ✅ FIX: Use RLock instead of Lock to prevent deadlock.
        # RoomLifecycleManager.to_dict() calls certification_progress()
        # and building_status() while holding the lock. With Lock (non-reentrant),
        # this causes immediate deadlock. RLock allows re-entrant acquisition,
        # matching DigitalTwin's proven pattern.
        self._lock = threading.RLock()
        self._bus = bus

    # ── Room Management ───────────────────────────────────────────────

    def register_room(self, room_id: str) -> RoomLifecycle:
        """Register a new room and create its lifecycle.

        If the room is already registered, returns the existing lifecycle
        without creating a duplicate.

        Args:
            room_id: Unique identifier for the room.

        Returns:
            The RoomLifecycle for the room.

        Raises:
            TypeError: If room_id is not a string.

        """
        if not isinstance(room_id, str):
            raise TypeError(f"room_id must be str, got {type(room_id).__name__}")

        with self._lock:
            if room_id in self._rooms:
                logger.debug("Room %s already registered, returning existing lifecycle", room_id)
                return self._rooms[room_id]

            lifecycle = RoomLifecycle(room_id=room_id, bus=self._bus)
            self._rooms[room_id] = lifecycle
            logger.info("Registered room %s with lifecycle manager", room_id)
            return lifecycle

    def get_room(self, room_id: str) -> Optional[RoomLifecycle]:
        """Get the lifecycle for a specific room.

        Args:
            room_id: Unique identifier for the room.

        Returns:
            The RoomLifecycle for the room, or None if not registered.

        """
        with self._lock:
            return self._rooms.get(room_id)

    def has_room(self, room_id: str) -> bool:
        """Check if a room is registered.

        Args:
            room_id: Unique identifier for the room.

        Returns:
            True if the room is registered.

        """
        with self._lock:
            return room_id in self._rooms

    def room_ids(self) -> List[str]:
        """Return a list of all registered room IDs.

        Returns:
            List of room ID strings.

        """
        with self._lock:
            return list(self._rooms.keys())

    def room_count(self) -> int:
        """Return the total number of registered rooms."""
        with self._lock:
            return len(self._rooms)

    # ── Building-Level Status ─────────────────────────────────────────

    def building_status(self) -> Dict[RoomState, int]:
        """Aggregate room states across the entire building.

        Returns a count of rooms in each lifecycle state. States with
        zero rooms are still included for completeness (useful for
        dashboard rendering).

        Returns:
            Dictionary mapping each RoomState to its count.
            All states are included, even those with zero rooms.

        Example:
            status = manager.building_status()
            # {
            #     RoomState.PENDING: 3,
            #     RoomState.ANALYZING: 1,
            #     RoomState.CERTIFIED: 5,
            #     ...
            # }

        """
        with self._lock:
            # Initialize all states to zero
            status: Dict[RoomState, int] = dict.fromkeys(RoomState, 0)
            for lifecycle in self._rooms.values():
                # Access state directly (we already hold our own lock,
                # but RoomLifecycle.state also acquires its internal lock)
                status[lifecycle.state] += 1
            return status

    def all_certified(self) -> bool:
        """Check if ALL rooms in the building are CERTIFIED.

        This is the hard gate for AHJ submission. A building cannot
        be submitted until every single room has a proof certificate
        sealed with SHA-256.

        Returns:
            True if ALL rooms are in CERTIFIED state.
            False if any room is in any other state, or if no rooms
            are registered.

        """
        with self._lock:
            if not self._rooms:
                return False
            return all(lc.state == RoomState.CERTIFIED for lc in self._rooms.values())

    def any_failed(self) -> bool:
        """Check if any room in the building is in FAILED state.

        Returns:
            True if at least one room is FAILED.

        """
        with self._lock:
            return any(lc.state == RoomState.FAILED for lc in self._rooms.values())

    def any_warnings(self) -> bool:
        """Check if any room in the building is in WARNING state.

        Returns:
            True if at least one room is in WARNING state.

        """
        with self._lock:
            return any(lc.state == RoomState.WARNING for lc in self._rooms.values())

    def certified_count(self) -> int:
        """Return the number of rooms in CERTIFIED state."""
        with self._lock:
            return sum(1 for lc in self._rooms.values() if lc.state == RoomState.CERTIFIED)

    def certification_progress(self) -> float:
        """Return the certification progress as a percentage (0.0–100.0).

        Returns:
            Percentage of rooms that are CERTIFIED.
            Returns 0.0 if no rooms are registered.

        """
        with self._lock:
            if not self._rooms:
                return 0.0
            certified = sum(1 for lc in self._rooms.values() if lc.state == RoomState.CERTIFIED)
            return (certified / len(self._rooms)) * 100.0

    # ── Bulk Operations ───────────────────────────────────────────────

    def reset_room(self, room_id: str) -> None:
        """Reset a room's lifecycle back to PENDING.

        This is useful for retrying a failed room. The room must
        already be registered.

        Args:
            room_id: Unique identifier for the room.

        Raises:
            KeyError: If the room is not registered.

        """
        with self._lock:
            if room_id not in self._rooms:
                raise KeyError(f"Room {room_id} is not registered")
            # Re-create the lifecycle for a clean reset
            self._rooms[room_id] = RoomLifecycle(room_id=room_id, bus=self._bus)
        logger.info("Reset lifecycle for room %s", room_id)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the manager state to a dictionary.

        Returns:
            Dictionary containing room count, certification progress,
            building status, and per-room lifecycle summaries.

        """
        with self._lock:
            return {
                "room_count": len(self._rooms),
                "certification_progress": self.certification_progress(),
                "building_status": {s.value: count for s, count in self.building_status().items()},
                "rooms": {rid: lc.to_dict() for rid, lc in self._rooms.items()},
            }

    def __repr__(self) -> str:
        with self._lock:
            return f"RoomLifecycleManager(rooms={len(self._rooms)}, certified={self.certified_count()})"


# ═══════════════════════════════════════════════════════════════════════
# Module Exports
# ═══════════════════════════════════════════════════════════════════════

__all__ = [
    "LEGAL_TRANSITIONS",
    "RoomLifecycle",
    "RoomLifecycleManager",
    "RoomState",
    "RoomTransition",
]


# ═══════════════════════════════════════════════════════════════════════
# Self-Test Block
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import time

    print("=" * 70)
    print("FireAI Room Lifecycle — Self-Test")
    print("=" * 70)

    EventBus.reset()

    # ── Test 1: Basic Lifecycle ─────────────────────────────────────
    print("\n[TEST 1] Full happy-path lifecycle")
    lc = RoomLifecycle(room_id="R-101")
    assert lc.state == RoomState.PENDING
    assert lc.can_transition_to(RoomState.ANALYZING)
    assert not lc.can_transition_to(RoomState.CERTIFIED)

    lc.transition_to(RoomState.ANALYZING, "Begin placement optimization", "system")
    assert lc.state == RoomState.ANALYZING

    lc.transition_to(
        RoomState.OPTIMIZED, "3 smoke detectors placed", "system", metadata={"detector_count": 3, "coverage_pct": 100.0}
    )
    assert lc.state == RoomState.OPTIMIZED

    lc.transition_to(RoomState.VERIFYING, "Triple consensus start", "system")
    assert lc.state == RoomState.VERIFYING

    lc.transition_to(RoomState.VERIFIED, "3/3 engines PASS", "system", metadata={"n_pass": 3, "n_total": 3})  # nosec B105 — false positive: '3' is engine count, not password
    assert lc.state == RoomState.VERIFIED

    lc.transition_to(RoomState.CERTIFYING, "Generating proof certificate", "system")
    assert lc.state == RoomState.CERTIFYING

    lc.transition_to(RoomState.CERTIFIED, "SHA-256 sealed", "system", metadata={"sha256": "abc123def456"})
    assert lc.state == RoomState.CERTIFIED
    assert lc.is_terminal()
    assert len(lc.history) == 6
    print(f"   ✓ Full lifecycle: PENDING → CERTIFIED in {len(lc.history)} transitions")

    # ── Test 2: Illegal Transition ──────────────────────────────────
    print("\n[TEST 2] Illegal transition rejection")
    lc2 = RoomLifecycle(room_id="R-102")
    assert not lc2.can_transition_to(RoomState.VERIFIED)
    try:
        lc2.transition_to(RoomState.VERIFIED, "Skip ahead", "system")
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "Illegal transition" in str(e)
        print(f"   ✓ Illegal transition blocked: {e}")

    # ── Test 3: WARNING Path ────────────────────────────────────────
    print("\n[TEST 3] WARNING → VERIFYING (retry) path")
    lc3 = RoomLifecycle(room_id="R-103")
    lc3.transition_to(RoomState.ANALYZING, "Start", "system")
    lc3.transition_to(RoomState.OPTIMIZED, "Done", "system")
    lc3.transition_to(RoomState.VERIFYING, "Verify", "system")
    lc3.transition_to(RoomState.WARNING, "2/3 engines agree", "system", metadata={"n_pass": 2, "n_total": 3})  # nosec B105 — false positive: '2' is engine count, not password
    assert lc3.state == RoomState.WARNING
    assert not lc3.is_failed()

    # Retry verification
    lc3.transition_to(RoomState.VERIFYING, "Retry after investigation", "system")
    lc3.transition_to(RoomState.VERIFIED, "3/3 PASS on retry", "system")
    assert lc3.state == RoomState.VERIFIED
    print("   ✓ WARNING → VERIFYING (retry) → VERIFIED path works")

    # ── Test 4: WARNING → VERIFIED (PE override) ────────────────────
    print("\n[TEST 4] WARNING → VERIFIED (PE override)")
    lc4 = RoomLifecycle(room_id="R-104")
    lc4.transition_to(RoomState.ANALYZING, "Start", "system")
    lc4.transition_to(RoomState.OPTIMIZED, "Done", "system")
    lc4.transition_to(RoomState.VERIFYING, "Verify", "system")
    lc4.transition_to(RoomState.WARNING, "2/3 engines agree", "system")
    lc4.transition_to(
        RoomState.VERIFIED,
        "PE reviewed and approved",
        "pe",
        metadata={"pe_license": "PE-12345", "override_reason": "Grid engine false positive"},
    )
    assert lc4.state == RoomState.VERIFIED
    assert lc4.history[-1].actor == "pe"
    print("   ✓ PE override: WARNING → VERIFIED with actor='pe'")

    # ── Test 5: FAILED → PENDING (retry) ────────────────────────────
    print("\n[TEST 5] FAILED → PENDING (retry)")
    lc5 = RoomLifecycle(room_id="R-105")
    lc5.transition_to(RoomState.ANALYZING, "Start", "system")
    lc5.transition_to(RoomState.FAILED, "Geometry error", "system", metadata={"error": "Room has zero area"})
    assert lc5.state == RoomState.FAILED
    assert lc5.is_failed()

    lc5.transition_to(RoomState.PENDING, "Retry after fix", "system")
    assert lc5.state == RoomState.PENDING
    print("   ✓ FAILED → PENDING retry works")

    # ── Test 6: CERTIFIED → REJECTED (AHJ override) ────────────────
    print("\n[TEST 6] CERTIFIED → REJECTED (AHJ override)")
    lc6 = RoomLifecycle(room_id="R-106")
    lc6.transition_to(RoomState.ANALYZING, "Start", "system")
    lc6.transition_to(RoomState.OPTIMIZED, "Done", "system")
    lc6.transition_to(RoomState.VERIFYING, "Verify", "system")
    lc6.transition_to(RoomState.VERIFIED, "3/3 PASS", "system")
    lc6.transition_to(RoomState.CERTIFYING, "Generate cert", "system")
    lc6.transition_to(RoomState.CERTIFIED, "SHA-256 sealed", "system")
    lc6.transition_to(
        RoomState.REJECTED,
        "AHJ requires additional detectors",
        "ahj",
        metadata={"ahj_inspector": "Inspector Smith", "case_number": "AHJ-2024-001"},
    )
    assert lc6.state == RoomState.REJECTED
    assert lc6.is_terminal()

    lc6.transition_to(RoomState.PENDING, "Resubmit with corrections", "system")
    assert lc6.state == RoomState.PENDING
    print("   ✓ AHJ override: CERTIFIED → REJECTED → PENDING (resubmit)")

    # ── Test 7: Duration in State ───────────────────────────────────
    print("\n[TEST 7] Duration in state tracking")
    lc7 = RoomLifecycle(room_id="R-107")
    time.sleep(0.1)
    duration = lc7.duration_in_state()
    assert duration >= 0.05, f"Expected duration >= 0.05s, got {duration}s"
    print(f"   ✓ Duration in PENDING state: {duration:.3f}s")

    # ── Test 8: Transition History ──────────────────────────────────
    print("\n[TEST 8] Transition history integrity")
    lc8 = RoomLifecycle(room_id="R-108")
    lc8.transition_to(RoomState.ANALYZING, "Start", "system")
    lc8.transition_to(RoomState.OPTIMIZED, "Done", "system")
    history = lc8.history
    assert len(history) == 2
    assert history[0].from_state == RoomState.PENDING
    assert history[0].to_state == RoomState.ANALYZING
    assert history[1].from_state == RoomState.ANALYZING
    assert history[1].to_state == RoomState.OPTIMIZED
    # Verify immutability
    try:
        history[0].reason = "tampered"
        raise AssertionError("RoomTransition should be frozen")
    except AttributeError:
        pass
    print(f"   ✓ History: {len(history)} transitions, immutable records confirmed")

    # ── Test 9: RoomLifecycleManager ────────────────────────────────
    print("\n[TEST 9] RoomLifecycleManager")
    EventBus.reset()
    mgr = RoomLifecycleManager()

    mgr.register_room("R-201")
    mgr.register_room("R-202")
    mgr.register_room("R-203")

    assert mgr.room_count() == 3
    assert not mgr.all_certified()

    # Get room and advance it
    r201 = mgr.get_room("R-201")
    assert r201 is not None
    r201.transition_to(RoomState.ANALYZING, "Start", "system")
    r201.transition_to(RoomState.OPTIMIZED, "Done", "system")
    r201.transition_to(RoomState.VERIFYING, "Verify", "system")
    r201.transition_to(RoomState.VERIFIED, "3/3 PASS", "system")
    r201.transition_to(RoomState.CERTIFYING, "Cert", "system")
    r201.transition_to(RoomState.CERTIFIED, "Sealed", "system")

    status = mgr.building_status()
    assert status[RoomState.CERTIFIED] == 1
    assert status[RoomState.PENDING] == 2
    assert not mgr.all_certified()
    assert mgr.certification_progress() == (1.0 / 3.0) * 100.0
    print(f"   ✓ Manager: {mgr.room_count()} rooms, 1 certified, progress={mgr.certification_progress():.1f}%")

    # Certify remaining rooms
    for rid in ["R-202", "R-203"]:
        r = mgr.get_room(rid)
        r.transition_to(RoomState.ANALYZING, "Start", "system")
        r.transition_to(RoomState.OPTIMIZED, "Done", "system")
        r.transition_to(RoomState.VERIFYING, "Verify", "system")
        r.transition_to(RoomState.VERIFIED, "3/3 PASS", "system")
        r.transition_to(RoomState.CERTIFYING, "Cert", "system")
        r.transition_to(RoomState.CERTIFIED, "Sealed", "system")

    assert mgr.all_certified()
    assert mgr.certification_progress() == 100.0
    print(f"   ✓ All rooms certified: all_certified()={mgr.all_certified()}")

    # ── Test 10: EventBus Integration ───────────────────────────────
    print("\n[TEST 10] EventBus integration")
    EventBus.reset()
    bus = EventBus()
    received_events = []

    def on_lifecycle_change(event):
        received_events.append(event)

    bus.subscribe("room.lifecycle.changed", on_lifecycle_change)

    lc10 = RoomLifecycle(room_id="R-301", bus=bus)
    lc10.transition_to(RoomState.ANALYZING, "Start", "system")
    lc10.transition_to(RoomState.OPTIMIZED, "Done", "system")

    assert len(received_events) == 2
    assert received_events[0].data["room_id"] == "R-301"
    assert received_events[0].data["from_state"] == "PENDING"
    assert received_events[0].data["to_state"] == "ANALYZING"
    assert received_events[0].source == "room_lifecycle"
    assert received_events[1].data["to_state"] == "OPTIMIZED"
    print(f"   ✓ EventBus: {len(received_events)} lifecycle events received")

    # ── Test 11: Serialization ──────────────────────────────────────
    print("\n[TEST 11] Serialization (to_dict)")
    d = lc10.to_dict()
    assert d["room_id"] == "R-301"
    assert d["state"] == "OPTIMIZED"
    assert d["transition_count"] == 2
    assert len(d["history"]) == 2
    assert d["history"][0]["from_state"] == "PENDING"
    assert d["history"][0]["to_state"] == "ANALYZING"
    print(f"   ✓ Serialization: room_id={d['room_id']}, state={d['state']}, transitions={d['transition_count']}")

    mgr_d = mgr.to_dict()
    assert mgr_d["room_count"] == 3
    assert mgr_d["certification_progress"] == 100.0
    print(f"   ✓ Manager serialization: {mgr_d['room_count']} rooms, progress={mgr_d['certification_progress']:.1f}%")

    # ── Test 12: Thread Safety (stress test) ────────────────────────
    print("\n[TEST 12] Thread safety stress test")
    import concurrent.futures

    lc_ts = RoomLifecycle(room_id="R-THREAD")
    errors = []

    def transition_worker(start_state_label, target_state, reason):
        try:
            # Small delay to increase chance of concurrent access
            time.sleep(0.001)
            if lc_ts.can_transition_to(target_state):
                lc_ts.transition_to(target_state, reason, "system")
        except ValueError:
            pass  # Expected if another thread changed state first
        except Exception as e:
            errors.append(e)

    # Run transitions from multiple threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for _ in range(10):
            futures.append(executor.submit(transition_worker, "PENDING", RoomState.ANALYZING, "Thread test"))
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Thread safety errors: {errors}"
    assert lc_ts.state == RoomState.ANALYZING  # Only one transition should have succeeded
    print(f"   ✓ Thread safety: 10 concurrent transitions, no errors, state={lc_ts.state.value}")

    # ── Cleanup ─────────────────────────────────────────────────────
    EventBus.reset()

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED ✓")
    print("=" * 70)
