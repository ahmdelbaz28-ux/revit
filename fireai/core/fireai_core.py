"""
fireai_core.py — Central Orchestrator for FireAI Production System
=====================================================
This module provides FireAISystem which integrates:
  - ExpertSystem (analysis engine)
  - AuditStore (tamper-evident logging)
  - V10 Enhanced improvements

Supports room-level analysis with full audit trail for production use.
"""

import sys
import os
sys.path.insert(0, '/workspace/project/revit')

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

# Import audit_store functions (module-level)
import fireai.core.audit_store as audit_store
from fireai.core.fire_expert_system import (
    ExpertSystem,
    ExpertResult,
    ConfidenceLevel,
)
from fireai.core.nfpa72_models import RoomSpec


@dataclass
class FireAISystem:
    """
    Central orchestrator that combines ExpertSystem analysis with audit logging.
    
    This is the main entry point for production use of FireAI system.
    Integrates:
      - ExpertSystem: Analysis engine
      - AuditStore: Tamper-evident audit trail (module functions)
    """
    
    db_path: str
    
    # Internal components
    _expert: Optional[ExpertSystem] = field(default=None, init=False)
    
    def __post_init__(self):
        """Initialize internal components."""
        # For production, we use file-based audit store
        # Set database path in audit_store module before first use
        import fireai.core.audit_store as audit_store
        
        # Use provided db_path or default (avoid :memory: for audit)
        db_path = self.db_path if self.db_path != ":memory:" else "/workspace/project/revit/fireai/core/audit_store.db"
        audit_store.DATABASE_PATH = db_path
        
        # Force re-initialization with new path
        # Delete existing DB if exists and we're resetting
        if os.path.exists(db_path):
            os.remove(db_path)
        
        # This will use the new db_path
        audit_store._init_database()
        
        # Create expert system
        self._expert = ExpertSystem()
    
    def analyse_room(
        self,
        room_spec: RoomSpec,
        user_id: str,
        run_resilience: bool = True,
    ) -> ExpertResult:
        """
        Analyze a single room and log to audit trail.
        
        Args:
            room_spec: Room specification
            user_id: User performing the analysis (for audit)
            run_resilience: Ignored (kept for API compatibility)
            
        Returns:
            ExpertResult with full analysis results
        """
        # Run analysis
        result = self._expert.analyse_room(
            room_spec=room_spec,
        )
        
        # Log to audit trail
        details = {
            "detector_count": len(result.detector_positions),
            "confidence": result.confidence.value if result.confidence else "UNKNOWN",
            "wall_violations": len(result.wall_violations),
            "coverage": result.placement_proof.coverage_fraction if result.placement_proof else None,
            "user_id": user_id,
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
        
        return result
    
    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get the complete audit trail."""
        return audit_store.get_events()
    
    def verify_audit_integrity(self) -> bool:
        """Verify the integrity of the audit trail."""
        is_valid, _ = audit_store.verify_chain()
        return is_valid
    
    @property
    def expert(self) -> Optional[ExpertSystem]:
        """Get the expert system for direct access."""
        return self._expert