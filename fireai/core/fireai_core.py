"""
fireai_core.py — Central Orchestrator for FireAI Production System
=====================================================
This module provides FireAISystem which integrates:
  - ExpertSystemV12 (analysis engine)
  - AuditStore (tamper-evident logging) - module-level functions
  - ProjectMemory (solution caching)

Supports both room-level and floor-level analysis with full audit trail.
"""

import sys
sys.path.insert(0, '/workspace/project/revit')

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

# Import audit_store functions (module-level)
import fireai.core.audit_store as audit_store
from fireai.core.fire_expert_system_v12 import (
    ExpertSystemV12,
    ExpertResultV12,
    RoomSpec,
)


@dataclass
class FireAISystem:
    """
    Central orchestrator that combines V12 analysis with audit logging.
    
    This is the main entry point for production use of FireAI system.
    Integrates:
      - ExpertSystemV12: Analysis engine with MIP + resilience
      - AuditStore: Tamper-evident audit trail (module functions)
      - ProjectMemory: Solution caching for efficiency
    """
    
    db_path: str
    memory_max: int = 2048
    
    # Internal components (set in __post_init__)
    _expert: Optional[ExpertSystemV12] = field(default=None, init=False)
    
    def __post_init__(self):
        """Initialize internal components."""
        # Set database path in audit_store module
        # (uses default path or can be set via environment)
        
        # Create V12 expert system with memory
        from fireai.core.fire_expert_system_v12 import ProjectMemory
        memory = ProjectMemory(max_records=self.memory_max)
        self._expert = ExpertSystemV12(memory=memory)
    
    def analyse_room(
        self,
        room_spec: RoomSpec,
        user_id: str,
        run_resilience: bool = True,
    ) -> ExpertResultV12:
        """
        Analyze a single room and log to audit trail.
        
        Args:
            room_spec: Room specification
            user_id: User performing the analysis (for audit)
            run_resilience: Whether to run resilience check
            
        Returns:
            ExpertResultV12 with full analysis results
        """
        # Run V12 analysis
        result = self._expert.analyse_room(
            room_spec=room_spec,
            run_resilience=run_resilience,
        )
        
        # Log to audit trail (using module functions)
        details = {
            "detector_count": len(result.detector_positions),
            "confidence": result.confidence.value if result.confidence else "UNKNOWN",
            "used_mip": result.used_mip,
            "wall_violations": len(result.wall_violations),
            "coverage": result.placement_proof.coverage_fraction if result.placement_proof else None,
            "user_id": user_id,
            "resilience": result.resilience.resilient if result.resilience else None,
            "mip_fallback": result.mip_fallback_reason or None,
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
    
    def analyse_floor(
        self,
        rooms: List[RoomSpec],
        user_id: str,
        run_resilience: bool = True,
    ) -> List[ExpertResultV12]:
        """
        Analyze multiple rooms (floor) and log to audit trail.
        
        Args:
            rooms: List of room specifications
            user_id: User performing the analysis (for audit)
            run_resilience: Whether to run resilience check
            
        Returns:
            List of ExpertResultV12, one per room
        """
        # Run V12 floor analysis
        results = self._expert.analyse_floor(
            room_specs=rooms,
            run_resilience=run_resilience,
        )
        
        # Log floor analysis to audit trail
        if results:
            total_detectors = sum(len(r.detector_positions) for r in results)
            violations = sum(len(r.wall_violations) for r in results)
            
            details = {
                "room_count": len(rooms),
                "results_count": len(results),
                "total_detectors": total_detectors,
                "wall_violations": violations,
                "user_id": user_id,
            }
            
            audit_store.add_event(
                event_type="floor_analysis",
                room_id=f"floor:{rooms[0].room_id}" if rooms else "floor:empty",
                details_dict=details,
            )
        
        return results
    
    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """
        Get the complete audit trail.
        
        Returns:
            List of audit events as dictionaries
        """
        return audit_store.get_events()
    
    def verify_audit_integrity(self) -> bool:
        """
        Verify the integrity of the audit trail.
        
        Returns:
            True if chain is valid, False if tampered
        """
        is_valid, _ = audit_store.verify_chain()
        return is_valid
    
    def clear_audit_trail(self):
        """Clear the audit trail (for testing)."""
        import os
        db_path = getattr(audit_store, 'DATABASE_PATH', '/workspace/project/revit/fireai/core/audit_store.db')
        if os.path.exists(db_path):
            os.remove(db_path)
            # Re-initialize by importing will recreate on next add_event
    
    @property
    def expert(self) -> Optional[ExpertSystemV12]:
        """Get the expert system for direct access."""
        return self._expert