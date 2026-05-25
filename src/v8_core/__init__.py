"""
FireCalc Pro V8.0 — Core Safety Modules
========================================
⚠️ LIFE-SAFETY WARNING ⚠️
========================================

THIS IS A PATTERN-MATCHING TOOL, NOT AN AI.

Every output REQUIRES:
  1. Licensed PE verification and signature
  2. Independent calculation (not just FireCalc output)
  3. Site-specific review

NOT GUARANTEED TO BE CORRECT:
  - Patterns may be outdated
  - New construction types not covered
  - Edge cases may fail silently

WRONG OUTPUT MAY RESULT IN DEATH.

See docs/VALIDATION_STUDY_PROTOCOL.md
See docs/SCOPE_DOCUMENT.md
See docs/PE_LIABILITY_PROTOCOL.md

USE ONLY IF:
  - You understand the limitations
  - PE reviews every output
  - Building is within validated scope

========================================
Module map:
  code_authority       — Versioned, FPE-signed code constants (NFPA 72, NEC).
  decision_provenance  — Structured output objects with citations + confidence.
  safety_optimizer     — Constrained optimization (safety-margin first, cost second).
  pattern_library      — Manually curated, FPE-approved precedent library.
  smoke_estimator      — Pre-screening estimator (±50%). NOT a simulation.
  linter_rules         — CI lint gates (banned words, literal constants, etc.).
"""
__version__ = "8.0.0"
__product_name__ = "FireCalc Pro"
__authority_model__ = "Software Vendor / Human-in-the-Loop / PE Required"
