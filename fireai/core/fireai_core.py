"""
fireai_core.py — Central Orchestrator for FireAI Production System
=====================================================
This module provides FireAISystem which integrates:
  - fire_expert_system_v10_enhanced (V10 Enhanced analysis engine)
  - audit_store (tamper-evident logging)

Supports room-level analysis with full audit trail and resilience checks.
"""

import sys
import os
sys.path.insert(0, '/workspace/project/revit')

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

# Import audit_store functions (module-level)
import fireai.core.audit_store as audit_store
from fireai.core.fire_expert_system import (
    EnhancedExpertResult,
    enhance_result,
    analyse_room_enhanced,
)
from fireai.core.nfpa72_models import RoomSpec
from fireai.core.learning_store import LearningStore


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
    """
    
    db_path: str
    
    # Internal components
    _expert: Optional[Any] = field(default=None, init=False)
    learning: Optional[LearningStore] = field(default=None, init=False)
    
    def __post_init__(self):
        """Initialize internal components."""
        import fireai.core.audit_store as audit_store
        
        # Use provided db_path or default
        db_path = self.db_path if self.db_path != ":memory:" else "/workspace/project/revit/fireai/core/audit_store.db"
        audit_store.DATABASE_PATH = db_path
        
        # Reset database
        if os.path.exists(db_path):
            os.remove(db_path)
        audit_store._init_database()
        
        # Initialize learning store
        self.learning = LearningStore(db_path="fireai_learning.sqlite3")
    
    def analyse_room(
        self,
        room_spec: RoomSpec,
        user_id: str = "system",
        run_resilience: bool = True,
    ) -> EnhancedExpertResult:
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
        
        audit_store.add_event(
            event_type="room_analysis",
            room_id=room_spec.room_id,
            details_dict=details,
        )
        
        # Log warnings if any
        if result.warnings:
            for warning in result.warnings:
                audit_store.add_event(
                    event_type="warning",
                    room_id=room_spec.room_id,
                    details_dict={"warning": warning, "user_id": user_id},
                )
        
        # Log errors if any
        if result.errors:
            for error in result.errors:
                audit_store.add_event(
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
                timestamp_utc=datetime.utcnow().isoformat() + "Z",
            )
            
            # Try recalibration
            self.learning.maybe_recalibrate()
        
        return result

    def analyse_floor(
        self,
        rooms: List[RoomSpec],
        user_id: str = "system",
        run_resilience: bool = True,
    ) -> List[EnhancedExpertResult]:
        """
        Analyze multiple rooms as a floor and log to audit trail.

        Args:
            rooms: List of RoomSpec to analyze as a floor
            user_id: User performing the analysis (for audit)
            run_resilience: Whether to run resilience checks

        Returns:
            List of EnhancedExpertResult, one per room
        """
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

        audit_store.add_event(
            event_type="floor_analysis",
            room_id="floor",
            details_dict=floor_details,
        )

        return results
    
    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get the complete audit trail."""
        return audit_store.get_events()
    
    def verify_audit_integrity(self) -> bool:
        """Verify the integrity of the audit trail."""
        is_valid, _ = audit_store.verify_chain()
        return is_valid