# Architecture Freeze Notice

This repository is under ARCHITECTURAL FREEZE as of commit 93e09ad.

## Frozen Modules (NO CHANGES ALLOWED)
- core/risk_tensor/ (Φ, Ω, SPTD, DSE, DCGE)
- core/gkil/ (GKIL, RPE, Decision Stratification)
- core/compliance_engine/ (Compliance Engine v1)
- core/monte_carlo/ (Monte Carlo)
- core/risk_graph/ (Risk Graph)
- kernel_algebra.py (Ω ∈ 𝒪_stable)
- spectral_calibration.py

## Regulatory Contract Surface (VERSIONED CHANGES ONLY)
The following commits form the architectural baseline:
- 93e09ad — RPE completion
- e6bc4fd — DSE completion
- 0096df0 — GKIL completion
- 81e5747 — DCGE completion

Any change to ontology semantics, proof schema, replay semantics, or canonical serialization MUST:
1. Go through a versioned governance process
2. Be approved by project lead
3. Include a migration plan for existing proofs

## Allowed Changes
- Adding new endpoints
- Fixing bugs without changing semantics
- Adding tests
- Documentation updates