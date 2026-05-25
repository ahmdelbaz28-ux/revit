"""
TASK-602: FIRECALC V8 SCOPE DOCUMENT
====================================
Step 0: BEFORE any deployment

This document defines what FireCalc V8 can and cannot do.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE OF USE (VALIDATED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FireCalc V8 APPROVED for use on:

1. RESIDENTIAL OCCUPANCIES
   ✓ Single-family dwellings
   ✓ Multi-family dwellings (up to 4 stories)
   ✓ Townhouses
   ✓ Residential care facilities (Group R-1, R-2, R-4, < 4 stories)

2. COMMERCIAL OCCUPANCIES  
   ✓ Business (Group B) - standard offices
   ✓ Mercantile (Group M) - retail stores
   ✓ Light manufacturing (Group S-1, S-2) - low hazard

3. CONSTRUCTION TYPES
   ✓ Type I (Non-combustible - steel/concrete)
   ✓ Type II (Non-combustible - limited)
   ✓ Type III (Ordinary - masonry/wood)
   ✓ Type V-A (Wood frame - protected)
   ✓ Type V-B (Wood frame - unprotected)

4. FIRE SUPPRESSION
   ✓ Wet pipe sprinklers (standard)
   ✓ Dry pipe sprinklers
   ✓ Pre-action sprinklers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUT OF SCOPE (NOT VALIDATED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FireCalc V8 MUST NOT be used on:

1. HIGH-RISE BUILDINGS
   ❌ Buildings > 75 feet (6+ stories)
   ❌ High-rise residential
   ❌ High-rise commercial

2. SPECIAL OCCUPANCIES
   ❌ Hazardous materials storage (H-1, H-2, H-3, H-4)
   ❌ Explosives manufacturing
   ❌ Flammable liquids/gases storage

3. CRITICAL FACILITIES
   ❌ Healthcare (I-1, I-2, I-3, I-4)
   ❌ Educational (E) - over 3 stories
   ❌ Detention/Correctional (I-3)
   ❌ Airports, train stations (> 5000 sqft)

4. SPECIAL STRUCTURES
   ❌ Atriums
   ❌ Membrane structures
   ❌ Underground structures
   ❌ Parking structures (> 1 level)
   ❌ Towers (observation, water)

5. NOVEL APPLICATIONS
   ❌ New materials (not in NFPA 72)
   ❌ Non-standard fire protection
   ❌ Alternative methods (without AHJ approval)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DECISION TREE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

START: New building permit request

Q1: Is this a high-rise?
   → YES: STOP - Manual PE review required
   → NO: Continue

Q2: Is this in approved occupancy list?
   → YES: Continue
   → NO: STOP - Requires separate validation

Q3: Is construction type in scope?
   → YES: Continue
   → NO: STOP - Requires separate validation

Q4: Is building area within scope limits?
   - Residential: ≤ 50,000 sqft per building
   - Commercial: ≤ 100,000 sqft per building
   
   → YES: Continue
   → NO: STOP - Requires separate validation

Q5: Are there unusual hazards?
   → YES: STOP - Requires separate validation
   → NO: Run FireCalc V8

RESULT: ✓ IN SCOPE / ❌ OUT OF SCOPE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE LIMITATIONS BY CONFIGURATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Configuration: IN-SCOPE ✓ / OUT-OF-SCOPE ❌

Building Area:
  < 10,000 sqft: ✓ In scope
  10,000 - 50,000 sqft: ✓ In scope  
  50,000 - 100,000 sqft: ✓ In scope
  > 100,000 sqft: ❌ Requires special approval

Stories:
  1-2 stories: ✓ In scope
  3-4 stories: ✓ In scope
  5-6 stories: ⚠️ Requires Fire Marshal approval
  6+ stories: ❌ Out of scope

Sprinkler Requirements:
  Standard (per NFPA 72): ✓ Supported
  Non-standard: ❌ Requires AHJ approval
  None: ⚠️ Check local code

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED DISCLAIMER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

All outputs MUST include:

"FireCalc V8 is a pattern-matching system. Results are based on 
historical patterns in the fire safety database. This output is valid 
only for buildings within the validated scope. Buildings outside scope 
require independent PE review.

Not valid for: high-rise, hazardous occupancies, special structures, 
or novel construction methods."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
APPROVAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Fire Safety Lead: ____________ Date: _______
AHJ Representative: ____________ Date: _______
Legal Review: ____________ Date: _______

Scope Document Version: 1.0
Status: ❌ DRAFT / ✓ APPROVED