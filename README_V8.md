# FireCalc Pro V8.0 — Core Safety Modules

> **FireCalc Pro is a deterministic engineering calculator and audit-trail system
> for NFPA 72 and NEC 2023 fire-alarm design tasks. It accelerates the work of a
> licensed Fire Protection Engineer; it does not substitute for one.**

This package replaces the dangerous parts of FireAI / FireSafetyGenius V7.6 with
six modules that together enforce the V8 Trust Stack. The modules are:

| Module | Replaces / Adds | Purpose |
|---|---|---|
| `code_authority.py` | Hardcoded literals | Versioned, FPE-signed, jurisdiction-aware NFPA/NEC constants |
| `decision_provenance.py` | Black-box outputs | Structured, signed, auditable output objects (XAI) |
| `safety_optimizer.py` | V7.6 `panel_optimizer.py` | Safety-first constrained k-median with trade frontier |
| `pattern_library.py` | V7.6 `self_learner.py` | Manually FPE-curated precedent library — NOT self-learning |
| `smoke_estimator.py` | V7.6 `smoke_simulator.py` | Pre-screening estimate (±50%), walled off, locked disclaimer |
| `linter_rules.py` | (new) | CI gates that fail builds on banned words, literals, unannotated returns |

## What this package guarantees

1. **No banned marketing claims** in any V8 artifact (`AI`, `self-learning`,
   `digital twin`, `predictive`, `consciousness`, `NFPA 92 simulation`, etc.).
2. **No literal NFPA/NEC values** anywhere outside `code_authority`.
3. **No engineering function returns a bare scalar** — every output is a
   `DecisionProvenance` object with citations, confidence, and engine signature.
4. **No silent failure** — when feasibility is impossible, the engine refuses
   with `ConfidenceLevel.REFUSE` and lists the violated rule.
5. **No automatic learning** — patterns enter the library only through an
   explicit FPE approval with a cryptographic signature.

## What this package does NOT do

- It does **not** stamp a design as compliant. Only a licensed PE can.
- It does **not** replace CFD / FDS for performance-based smoke analysis.
- It does **not** assert beam-detector line-of-sight or floor segmentation
  (these are explicitly out of scope until the V&V dataset is built).

## Minimum hands-on test

```bash
PYTHONPATH=src python -m unittest tests.test_v8_core -v
```

If anything is red, do not proceed.

## Reading order for new contributors

1. `decision_provenance.py` — understand the output contract.
2. `code_authority.py` — understand where every number comes from.
3. `safety_optimizer.py` — understand how the two are combined.
4. `pattern_library.py` — understand what we deliberately do NOT do.
5. `smoke_estimator.py` — understand what is walled off and why.
6. `linter_rules.py` — understand what CI will refuse to merge.

Then read `docs/INSTALL.md` and the V8 Master Blueprint (separate document).
