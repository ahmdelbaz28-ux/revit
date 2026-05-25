"""
test_learning.py — Learning Store Test Suite
======================================
Quick test for LearningStore calibration functionality.
"""

import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fireai.core.learning_store import LearningStore

# Constants from V10 (for comparison)
_DEFAULT_HIGH = 0.90
_DEFAULT_MEDIUM = 0.75


def test_learning_store():
    """Test basic learning store functionality."""
    print("TEST: LearningStore Basic")
    
    # Create in-memory store
    ls = LearningStore(':memory:')
    
    # Store 40 mock experiences with HIGH confidence scores
    # Use scores >= 0.90 so recalibration raises thresholds above defaults
    for i in range(40):
        # Confidence scores from 0.90 to 1.0 (to trigger recalibration above defaults)
        confidence = 0.90 + (i * 0.0025)
        score = min(1.0, confidence)
        
        level = 'HIGH' if score >= _DEFAULT_HIGH else 'MEDIUM' if score >= _DEFAULT_MEDIUM else 'LOW'
        
        # All compliant for recalibration test
        compliant = True
        
        ls.store(
            project_id='test_project',
            room_id=f'room_{i}',
            geometry_hash='10x10',
            room_area_m2=100.0,
            occupancy='office',
            detector_type='SMOKE_PHOTOELECTRIC',
            solver_used='fireai_v10',
            coverage_pct=score * 100,
            confidence_score=score,
            confidence_level=level,
            resilience_pass_rate=0.8 if score > 0.8 else None,
            wall_violation_count=0,
            greedy_retries=0,
            proof_valid=True,
            compliant=compliant,
            timestamp_utc='2026-05-16T12:00:00Z',
        )
    
    print(f"  Stored 40 experiences (scores 0.90-1.0, all compliant)")
    
    # Test that thresholds return defaults (no calibration yet)
    thresholds = ls.get_calibrated_thresholds()
    print(f"  Default thresholds: high={thresholds[0]:.3f}, medium={thresholds[1]:.3f}")
    
    # Force recalibration
    recalibrated = ls.recalibrate()
    print(f"  Recalibrated: {recalibrated}")
    
    # Get new thresholds
    new_thresholds = ls.get_calibrated_thresholds()
    print(f"  New thresholds: high={new_thresholds[0]:.3f}, medium={new_thresholds[1]:.3f}")
    
    # Verify thresholds >= defaults
    assert new_thresholds[0] >= _DEFAULT_HIGH, f"High threshold {new_thresholds[0]} < {_DEFAULT_HIGH}"
    assert new_thresholds[1] >= _DEFAULT_MEDIUM, f"Medium threshold {new_thresholds[1]} < {_DEFAULT_MEDIUM}"
    
    print(f"  Thresholds >= defaults: PASS")
    
    # Show comparison
    print(f"\n  THRESHOLD COMPARISON:")
    print(f"    Default:  high={_DEFAULT_HIGH:.3f}, medium={_DEFAULT_MEDIUM:.3f}")
    print(f"    Calibrated: high={new_thresholds[0]:.3f}, medium={new_thresholds[1]:.3f}")
    print(f"    Change:   high+{new_thresholds[0]-_DEFAULT_HIGH:+.3f}, medium+{new_thresholds[1]-_DEFAULT_MEDIUM:+.3f}")
    
    ls.close()
    print("  RESULT: PASS")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("LEARNING STORE TEST SUITE")
    print("=" * 60)
    print()
    
    try:
        test_learning_store()
        print()
        print("=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
    except Exception as e:
        print(f"  RESULT: FAIL - {e}")
        raise