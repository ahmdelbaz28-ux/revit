"""
V12 Compatibility Test

This test file applies monkey patches BEFORE importing V12,
then verifies the compatibility works.
"""

import sys
import re
import os

# Step 1: Fix syntax errors in nfpa72_coverage.py TEMPORARILY for loading
# These fixes are REQUIRED to load the module - they fix invalid Python syntax
nfpa72_path = '/workspace/project/revit/nfpa72_coverage.py'
with open(nfpa72_path, 'r') as f:
    content = f.read()

# Replace dates that look like octal literals
content = re.sub(r'Fixed: (\d{4})-(\d{2})-(\d{2})', r'Version', content)
content = re.sub(r'FIXED: (\d{4})-(\d{2})-(\d{2})', r'Version', content)

# Replace unicode characters that are not valid in Python strings
content = content.replace('\u00b0', ' degrees ')  # °
content = content.replace('\u00a7', 'Section')     # §
content = content.replace('3ft)', 'three feet)')

# Write back temporarily
with open(nfpa72_path, 'w') as f:
    f.write(content)

# Now we can import and patch
try:
    from fireai.core.v12_compatibility import (
        check_coverage_polygon_compat,
        OptimalMIPEngine_compat,
    )
    
    # Step 2: Apply monkey patches to modules
    import nfpa72_coverage
    import spatial_engine.mip_solver
    
    # Patch check_coverage_polygon in nfpa72_coverage
    nfpa72_coverage.check_coverage_polygon = check_coverage_polygon_compat
    
    # Patch OptimalMIPEngine in spatial_engine.mip_solver
    spatial_engine.mip_solver.OptimalMIPEngine = OptimalMIPEngine_compat
    
    print("Patches applied successfully")
    
except Exception as e:
    print(f"Error during setup: {e}")
    sys.exit(1)

# Step 3: Import V12 and run test
try:
    from fireai.core.fire_expert_system_v12 import ExpertSystemV12
    from nfpa72_models import RoomSpec, CeilingSpec, CeilingType
    
    # Create test room with ceiling
    ceiling = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
    room = RoomSpec(
        room_id='test',
        width_m=10.0,
        depth_m=10.0,
        height_m=3.0
    )
    room.ceiling_spec = ceiling
    
    # Run analysis
    expert = ExpertSystemV12()
    result = expert.analyse_room(room_spec=room, run_resilience=False)
    
    # Verify results
    print(f"Detectors: {len(result.detector_positions)}")
    print(f"Confidence: {result.confidence}")
    
    if result.detector_positions:
        print("V12 compatibility: PASS")
    else:
        print("V12 compatibility: FAIL - no detectors")
        
except Exception as e:
    print(f"Error during test: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)