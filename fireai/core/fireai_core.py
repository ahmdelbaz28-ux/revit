"""
fireai_core.py — Central Orchestrator for FireAI Production System
=====================================================
This module provides FireAISystem which integrates:
  - fire_expert_system_v13_adapted (V13 with adaptive learning)
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
from fireai.core.nfpa72_models import RoomSpec

# Import V13 Adapted
from fireai.core.fire_expert_system_v13_adapted import (
    ExpertSystemV13,
    AdaptiveMemory,
)


@dataclass
class FireAISystem:
    """
    Central orchestrator that combines V13 analysis with audit logging.
    
    This is the main entry point for production use of FireAI system.
    Integrates:
      - ExpertSystemV13: V13 analysis with adaptive learning
      - AdaptiveMemory: Persistent experience store
      - AuditStore: Tamper-evident audit trail
    """
    
    db_path: str
    
    # Internal components
    expert: Optional[ExpertSystemV13] = field(default=None, init=False)
    memory: Optional[AdaptiveMemory] = field(default=None, init=False)
    
    def __post_init__(self):
        """Initialize internal components."""
        import fireai.core.audit_store as audit_store_module
        
        # Use provided db_path or default
        db_path = self.db_path if self.db_path != ":memory:" else "/workspace/project/revit/fireai/core/audit_store.db"
        audit_store_module.DATABASE_PATH = db_path
        
        # Reset database
        if os.path.exists(db_path):
            os.remove(db_path)
        audit_store_module._init_database()
        
        # Initialize V13 with adaptive memory
        self.memory = AdaptiveMemory(db_path=db_path)
        self.expert = ExpertSystemV13(
            audit_store=audit_store_module,
            memory=self.memory,
        )
    
    def analyse_room(
        self,
        room_spec: RoomSpec,
        user_id: str = "system",
        run_resilience: bool = True,
    ) -> Any:
        """
        Analyze a single room using V13 and log to audit trail.
        
        Args:
            room_spec: Room specification
            user_id: User performing the analysis (for audit/project_id)
            run_resilience: Whether to run resilience check
            
        Returns:
            ExpertResultV13 with full analysis results
        """
        # Run V13 analysis
        result = self.expert.analyse_room(
            room_spec=room_spec,
            project_id=user_id,
            run_resilience=run_resilience,
        )
        
        return result

    def analyse_floor(
        self,
        rooms: List[RoomSpec],
        user_id: str = "system",
        run_resilience: bool = True,
    ) -> List[Any]:
        """
        Analyze multiple rooms as a floor using V13.

        Args:
            rooms: List of RoomSpec to analyze as a floor
            user_id: User performing the analysis (for project_id)
            run_resilience: Whether to run resilience checks

        Returns:
            List of ExpertResultV13, one per room
        """
        results = self.expert.analyse_floor(
            rooms=rooms,
            project_id=user_id,
            run_resilience=run_resilience,
        )

        return results
    
    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get the complete audit trail."""
        return audit_store.get_events()
    
    def verify_audit_integrity(self) -> bool:
        """Verify the integrity of the audit trail."""
        is_valid, _ = audit_store.verify_chain()
        return is_valid

