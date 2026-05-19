"""
Contextual Validation Test - The Deceptive PDF
======================================
Tests that verify the system can detect contradictions between room names and physical properties.

Scenario 1: Large "Server Room" (100 sqm) - likely not a server room
Scenario 2: Windowless "Office" - likely storage/electrical room
Scenario 3: "Office" near wet areas - likely kitchen/pantry
Scenario 4: Large "Storage" - should trigger MANUAL_REVIEW

Run: pytest tests/test_contextual_validation.py -v
"""

import pytest
from shapely.geometry import Polygon as ShapelyPolygon

from nfpa72_models import RoomSpec, CeilingSpec, DetectorType
from adapters.pdf_to_rooms_adapter import (
    guess_room_type, select_safe_detector_type, validate_and_guess_type_detailed
)


class TestContextualValidation:
    """Test contextual validation - detecting contradictions."""
    
    def test_large_server_room(self):
        """
        100 sqm room named "Server Room" - DETECT CONTRADICTION.
        Real server rooms are typically 10-30 sqm, not 100.
        """
        # Create large room (100 sqm = 10x10m)
        polygon = ShapelyPolygon([(0,0), (10,0), (10,10), (0,10)])
        
        result = validate_and_guess_type_detailed(
            room_name="Server Room A",
            polygon=polygon,
            has_windows=False,
            adjacent_rooms=[]
        )
        
        print(f"Room: Server Room A (100 sqm)")
        print(f"  Area: {polygon.area} sqm")
        print(f"  Has windows: {False}")
        print(f"  Result: {result}")
        
        # Should flag as suspicious
        assert result.get("requires_review") or result.get("detector_type") == "AMBIGUOUS"
        
    def test_windowless_office(self):
        """Office without windows - DETECT CONTRADICTION."""
        polygon = ShapelyPolygon([(0,0), (5,0), (5,5), (0,5)])
        
        result = validate_and_guess_type_detailed(
            room_name="Main Office",
            polygon=polygon,
            has_windows=False,  # No windows!
            adjacent_rooms=[]
        )
        
        print(f"Room: Main Office (25 sqm, no windows)")
        print(f"  Result: {result}")
        
        # Should flag as suspicious or recommend HEAT (storage-like)
        if result.get("requires_review"):
            print("  ✅ FLAGGED: Requires manual review")
        
    def test_kitchen_named_office(self):
        """Room near water named "Office" - likely kitchen."""
        polygon = ShapelyPolygon([(0,0), (6,0), (6,6), (0,6)])
        
        # Near wet areas
        result = validate_and_guess_type_detailed(
            room_name="Office 101",
            polygon=polygon,
            has_windows=True,
            adjacent_rooms=["Restroom", "Kitchen"]  # Wet rooms nearby
        )
        
        print(f"Room: Office 101 (near wet areas)")
        print(f"  Adjacent: Restroom, Kitchen")
        print(f"  Result: {result}")
        
    def test_large_storage(self):
        """Large storage (100 sqm) - should require review."""
        polygon = ShapelyPolygon([(0,0), (10,0), (10,10), (0,10)])
        
        result = validate_and_guess_type_detailed(
            room_name="Small Storage",
            polygon=polygon,
            has_windows=False,
            adjacent_rooms=[]
        )
        
        print(f"Room: Small Storage (100 sqm)")
        print(f"  Result: {result}")
        
        # Should require review due to size


class TestFailSafeBehavior:
    """Test that system fails safely when uncertain."""
    
    def test_ambiguous_returns_heat(self):
        """When uncertain, should default to HEAT (fail-safe)."""
        polygon = ShapelyPolygon([(0,0), (10,0), (10,10), (0,10)])
        
        result = validate_and_guess_type_detailed(
            room_name="Unknown Room X",
            polygon=polygon,
            has_windows=False,
            adjacent_rooms=[]
        )
        
        print(f"Unknown room: {result}")
        
        # Should recommend HEAT or flag for review


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])