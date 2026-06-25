---
Task ID: 1-10
Agent: Main Agent (Super Z)
Task: Execute critical modifications from Security & Compliance Audit Report (37 findings)

Work Log:
- Read all affected source files line by line (Rule 6 verification)
- Discovered BATTERY_SAFETY_FACTOR inconsistency: 1.20 in __init__.py vs 1.25 in nfpa72.py
- Fixed BATTERY_SAFETY_FACTOR to 1.25 (more conservative, Safety First per Rule #12)
- Made fireai/constants/__init__.py re-export from canonical fireai/constants/nfpa72.py
- Removed duplicate NFPA72_HEIGHT_SPACING_TABLE from __init__.py (now imported from nfpa72.py)
- Updated compute_smoke_detector_spacing() in qomn_kernel.py for V127 Phase C:
  - Replaced flat 9.1m spacing (V121) with height-adjusted table lookup
  - Uses canonical table from fireai/constants/nfpa72.py (SSoT)
  - No additional 1%/ft reduction on top of table values (fixes V120 double-reduction bug)
- Updated nfpa72_technology_dispatcher.py to import from canonical nfpa72.py
- Updated nfpa72_calculations.py to import from canonical nfpa72.py
- Added REGULATORY WARNING comments to both dispatcher and calculations files
- Fixed SYSTEM_ARCHITECTURE.md: CEILING_RANGE now shows correct two-tier system
- Completely rewrote ARCHITECTURE.md to reflect actual directory structure
- Updated V120-era tests to reflect V127 Phase C behavior
- Found and fixed f-string bug in audit_notice (literal {spacing_m:.2f} instead of value)
- All 5182 tests passing

Stage Summary:
- Critical Finding #1 (5 parallel NFPA 72 implementations): RESOLVED
  - All modules now import from fireai/constants/nfpa72.py (single source of truth)
  - __init__.py re-exports from canonical source
- Critical Finding #2 (Regulatory data without PE sign-off): ADDRESSED
  - PE_SIGNOFF_NOTICE added to nfpa72.py
  - All regulatory data now has proper NFPA section citations
- Critical Finding #3 (Architecture mismatch): RESOLVED
  - ARCHITECTURE.md completely rewritten to match actual structure
- High Finding #4 (Incorrect NFPA 72 interpretation): RESOLVED (V127 Phase C)
  - Height-adjusted table values used directly without additional 1%/ft reduction
- High Finding #5 (Height clamping): ALREADY CORRECT (18.288m hard limit)
  - SYSTEM_ARCHITECTURE.md corrected from "3.0-15.24m" to two-tier system
- High Finding #6 (Inconsistent values): RESOLVED
  - BATTERY_SAFETY_FACTOR aligned to 1.25
  - All constants verified consistent across modules
- High Finding #7 (V20 Bug #20): Already cleaned up in nec.py
- High Finding #8 (Missing src/ directory): RESOLVED (ARCHITECTURE.md updated)

Self-Criticism:
1. BUG FOUND: f-string interpolation error in audit_notice — {spacing_m:.2f} was literal
   text, not interpolated. Fixed immediately.
2. CONCERN: The V127 Phase C approach uses height-adjusted table values for smoke
   detectors even though NFPA 72 §17.7.3.2.3 specifies flat spacing. This is
   CONSERVATIVE (more detectors = safer) and widely-accepted engineering practice,
   but still requires FPE sign-off per the REGULATORY WARNING in nfpa72.py.
3. CONCERN: Some scalar constants in __init__.py are still locally defined rather
   than imported from nfpa72.py. This is pragmatic (avoids circular imports) but
   should be monitored for drift. Verified consistency with assertions.
