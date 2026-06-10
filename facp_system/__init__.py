"""
FACP Selection Engine — Fire Alarm Control Panel Selection & Compliance System
=============================================================================
Standards: NFPA 72 (2022) SS10.6.10, UL 864 10th Edition, CSFM, FDNY COA

This package provides deterministic FACP selection, battery sizing per
NFPA 72 SS10.6.7 with proper temperature/aging/Peukert derating, and
compliance verification against UL/FDNY/local AHJ listings.

V54 Bug Fixes Applied (vs. original user-submitted code):
  F1: Missing hashlib/dataclass imports in panel_selector.py (HIGH)
  F2: NAC 1.2x margin rejects valid panels (CRITICAL)
  F3: Sort key prefers oversized panels on ties (HIGH)
  F4: requires_releasing never checked (CRITICAL)
  F5: Battery calc uses flat 1.2x instead of NFPA 72 derating (HIGH)
  F6: Per-device standby current 1mA unrealistically low (MEDIUM)
"""
