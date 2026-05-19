"""
fireai_core.py — Central Orchestrator for FireAI Production System
=====================================================
This module provides FireAISystem which integrates:
  - fire_expert_system_v10_enhanced (V10 Enhanced analysis engine)
  - audit_store (tamper-evident logging)

Supports room-level analysis with full audit trail and resilience checks.

SECURITY FIXES APPLIED:
  - Removed hardcoded absolute path /workspace/project/revit
  - Removed os.remove(db_path) which destroyed the audit trail on every init
  - Database now uses APPEND-ONLY mode (CREATE TABLE IF NOT EXISTS preserves data)
  - db_path defaults to relative path or env variable
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from fireai.core.audit_store import AuditStore, SecurityError
from fireai.core.nfpa72_models import RoomSpec
from fireai.core.learning_store import LearningStore

logger = logging.getLogger(__name__)


def _resolve_db_path(db_path: Optional[str] = None) -> str:
    """Resolve the database path from argument, environment, or sensible default.

    Priority:
        1. Explicit db_path argument (including ":memory:" for testing)
        2. FIREAI_DB_PATH environment variable
        3. Relative to THIS FILE's directory: ./data/fireai_audit.db

    SELF-CRITIQUE FIX:
      The previous version used os.getcwd() as the default base directory.
      This was WRONG because CWD changes depending on how the process is
      launched (systemd, docker, cron, etc.), leading to the database
      being created in unpredictable locations or lost between restarts.
      Using __file__-relative path is deterministic and portable.

    BUG FIX (from 6-phase testing):
      The previous version fell through to env var check even when
      ":memory:" was explicitly passed. This meant FIREAI_DB_PATH
      would override an explicit ":memory:" request, breaking test
      isolation. Now, ":memory:" is returned immediately since it's
      an explicit argument that should take priority.

    Returns:
        Resolved absolute path for the audit database.
    """
    if db_path:
        # ":memory:" is a special SQLite path for in-memory databases.
        # Return it as-is — it should NOT be overridden by env vars.
        if db_path == ":memory:":
            return db_path
        return os.path.abspath(db_path)

    env_path = os.environ.get("FIREAI_DB_PATH")
    if env_path:
        return os.path.abspath(env_path)

    # Deterministic default — relative to this file, not CWD
    this_dir = os.path.dirname(os.path.abspath(__file__))
    default_dir = os.path.join(this_dir, "..", "..", "data")
    default_dir = os.path.normpath(default_dir)
    os.makedirs(default_dir, exist_ok=True)
    return os.path.join(default_dir, "fireai_audit.db")


@dataclass
class FireAISystem:
    """
    Central orchestrator that combines V10 Enhanced analysis with audit logging
    and adaptive learning.

    This is the main entry point for production use of FireAI system.
    Integrates:
      - analyse_room_enhanced: V10 analysis with resilience
      - enhance_result: Add resilience to any result
      - AuditStore: Tamper-evident audit trail
      - LearningStore: Adaptive confidence calibration

    Args:
        db_path: Path to the audit database. If None, uses FIREAI_DB_PATH
            env var or './data/fireai_audit.db'. If ':memory:', uses
            in-memory SQLite (testing only).
    """

    db_path: str

    # Internal components
    _expert: Optional[Any] = field(default=None, init=False)
    learning: Optional[LearningStore] = field(default=None, init=False)

    def __post_init__(self):
        """Initialize internal components."""
        import fireai.core.audit_store as audit_store

        # ✅ FIX: Use resolved path — no hardcoded /workspace/project/revit
        resolved_path = _resolve_db_path(self.db_path)
        audit_store.DATABASE_PATH = resolved_path
        self._resolved_db_path = resolved_path

        # ✅ FIX: REMOVED os.remove(db_path) — the audit trail must NEVER be destroyed.
        # Previously, every FireAISystem() instantiation deleted the entire audit database,
        # completely defeating the tamper-evident chain. Now we only INITIALIZE (append).
        #
        # Before (CATASTROPHIC):
        #   if os.path.exists(db_path):
        #       os.remove(db_path)  # 💀 Destroys audit trail!
        #   audit_store._init_database()
        #
        # After (SAFE):
        #   _init_database() uses CREATE TABLE IF NOT EXISTS — appends safely.
        audit_store._init_database()
        logger.info("Audit store initialized at: %s", resolved_path)

        # ✅ Verify audit integrity on startup
        try:
            is_valid, error = audit_store.verify_chain()
            if is_valid:
                logger.info("Audit chain integrity verified on startup")
            else:
                logger.error("AUDIT CHAIN INTEGRITY FAILURE: %s", error)
        except Exception as exc:
            logger.warning("Could not verify audit chain on startup: %s", exc)

        # Initialize learning store
        learning_db = os.environ.get(
            "FIREAI_LEARNING_DB_PATH",
            os.path.join(os.path.dirname(resolved_path), "fireai_learning.sqlite3"),
        )
        self.learning = LearningStore(db_path=learning_db)

    def analyse_room(
        self,
        room_spec: RoomSpec,
        user_id: str = "system",
        run_resilience: bool = True,
    ) -> Any:
        """
        Analyze a single room and log to audit trail.
        Uses V10 Enhanced with resilience check.

        Args:
            room_spec: Room specification
            user_id: User performing the analysis (for audit)
            run_resilience: Whether to run resilience check

        Returns:
            EnhancedExpertResult with full analysis results and resilience
        """
        # ✅ Input validation
        if not room_spec or not hasattr(room_spec, 'room_id'):
            raise ValueError("room_spec must have a room_id attribute")
        if not user_id or not isinstance(user_id, str):
            raise ValueError("user_id must be a non-empty string")

        # Import analysis engine
        from fireai.core.fire_expert_system import (
            analyse_room_enhanced,
        )

        # Run V10 Enhanced analysis with resilience
        result = analyse_room_enhanced(
            room_id=room_spec.room_id,
            width_m=room_spec.width_m,
            depth_m=room_spec.depth_m,
            ceiling_height_m=room_spec.ceiling_spec.height_at_low_point_m if room_spec.ceiling_spec else 3.0,
            run_resilience=run_resilience,
        )

        # Log to audit trail
        details = {
            "detector_count": len(result.detector_positions),
            "confidence": result.confidence.value if result.confidence else "UNKNOWN",
            "wall_violations": len(result.wall_violations),
            "coverage": result.placement_proof.coverage_fraction if result.placement_proof else None,
            "user_id": user_id,
            "resilience": result.resilience.resilient if result.resilience else None,
        }

        AuditStore.add_event(
            event_type="room_analysis",
            room_id=room_spec.room_id,
            details_dict=details,
        )

        # Log warnings if any
        if result.warnings:
            for warning in result.warnings:
                AuditStore.add_event(
                    event_type="warning",
                    room_id=room_spec.room_id,
                    details_dict={"warning": warning, "user_id": user_id},
                )

        # Log errors if any
        if result.errors:
            for error in result.errors:
                AuditStore.add_event(
                    event_type="error",
                    room_id=room_spec.room_id,
                    details_dict={"error": error, "user_id": user_id},
                )

        # Store experience and potentially recalibrate
        if self.learning:
            # Extract room info for storage
            geometry_hash = f"{room_spec.width_m:.2f}x{room_spec.depth_m:.2f}"
            room_area = room_spec.width_m * room_spec.depth_m
            occupancy = room_spec.occupancy_type or "office"
            detector_type = room_spec.detector_type.value if room_spec.detector_type else "SMOKE_PHOTOELECTRIC"

            # Get result data
            coverage_pct = (result.placement_proof.coverage_fraction * 100) if result.placement_proof else 0.0
            confidence_score = result.confidence_score or 0.0
            confidence_level = result.confidence.value if result.confidence else "LOW"
            resilience_pass_rate = result.resilience.pass_rate if result.resilience else None
            wall_violation_count = len(result.wall_violations)
            greedy_retries = 0  # Not tracked in current result
            proof_valid = result.placement_proof.proof_valid if result.placement_proof else False
            compliant = result.compliant if hasattr(result, 'compliant') else (coverage_pct >= 95.0)

            self.learning.store(
                project_id=user_id,
                room_id=room_spec.room_id,
                geometry_hash=geometry_hash,
                room_area_m2=room_area,
                occupancy=occupancy,
                detector_type=detector_type,
                solver_used="fireai_v10",
                coverage_pct=coverage_pct,
                confidence_score=confidence_score,
                confidence_level=confidence_level,
                resilience_pass_rate=resilience_pass_rate,
                wall_violation_count=wall_violation_count,
                greedy_retries=greedy_retries,
                proof_valid=proof_valid,
                compliant=compliant,
                timestamp_utc=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            )

            # Try recalibration
            self.learning.maybe_recalibrate()

        return result

    def analyse_floor(
        self,
        rooms: List[RoomSpec],
        user_id: str = "system",
        run_resilience: bool = True,
    ) -> List[Any]:
        """
        Analyze multiple rooms as a floor and log to audit trail.

        Args:
            rooms: List of RoomSpec to analyze as a floor
            user_id: User performing the analysis (for audit)
            run_resilience: Whether to run resilience checks

        Returns:
            List of EnhancedExpertResult, one per room
        """
        # ✅ Input validation
        if not rooms:
            raise ValueError("rooms list must not be empty")
        if len(rooms) > 500:
            raise ValueError("Maximum 500 rooms per floor analysis request")

        results = []

        for room_spec in rooms:
            # Analyze each room using existing method
            result = self.analyse_room(room_spec, user_id, run_resilience)
            results.append(result)

        # Log floor-level event (single event for entire floor)
        floor_details = {
            "room_count": len(rooms),
            "rooms": [r.room_id for r in rooms],
            "user_id": user_id,
            "results_count": len(results),
        }

        AuditStore.add_event(
            event_type="floor_analysis",
            room_id="floor",
            details_dict=floor_details,
        )

        return results

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get the complete audit trail."""
        return AuditStore.get_events()

    def verify_audit_integrity(self) -> bool:
        """Verify the integrity of the audit trail."""
        is_valid, _ = AuditStore.verify_chain()
        return is_valid

    def get_memory_summary(self) -> Dict[str, Any]:
        """Get learning store summary."""
        if not self.learning:
            return {"error": "Learning store not initialized"}
        try:
            return self.learning.get_summary()
        except Exception as exc:
            logger.error("Failed to get memory summary: %s", exc)
            return {"error": str(exc)}


__all__ = [
    "FireAISystem",
    "SecurityError",
    "_resolve_db_path",
]
