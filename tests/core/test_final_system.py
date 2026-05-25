"""
test_final_system.py – Final Integration Test for FireAI Production System
===================================================================
Tests the full FireAISystem with V10 Enhanced and AuditStore.
"""

import sys
import os
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fireai.core.fireai_core import FireAISystem
from fireai.core.nfpa72_models import RoomSpec, CeilingSpec


def test_final_system():
    """Test the full FireAISystem with V10 Enhanced and AuditStore."""
    # Create system
    system = FireAISystem(db_path=":memory:")

    # Create test room
    room = RoomSpec(
        room_id="test_room_001",
        width_m=10,
        depth_m=10,
        ceiling_spec=CeilingSpec(height_at_low_point_m=3.0),
    )

    # Analyze room
    result = system.analyse_room(room, user_id="test_user", run_resilience=True)

    # Assertions
    # 1. Confidence NOT UNSAFE
    assert not (result.confidence and result.confidence.value == "UNSAFE"), \
        f"Confidence is UNSAFE: {result.errors}"

    # 2. Audit trail has event
    events = system.get_audit_trail()
    assert len(events) > 0, "Audit trail is empty"

    # 3. Audit integrity verified
    assert system.verify_audit_integrity(), "Audit integrity verification failed"


if __name__ == "__main__":
    test_final_system()
    print("SYSTEM FINAL: PASS")
