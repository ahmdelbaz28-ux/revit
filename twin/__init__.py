"""
twin/ — FireAI Level 4 Digital Twin Engine
============================================

Architecture:
  StateEngine      → Deterministic state management with event sourcing
  NFPA72Bridge     → Bi-directional NFPA 72 calculation interface
  FirePhysics      → Physics-based fire simulation (zone + CFD-lite)
  AuditEventStore  → WAL-backed immutable event log with SHA-256 hash chain

Safety Classification:
  ⚠️  This module implements SIMPLIFIED fire physics, NOT full CFD.
  ⚠️  All simulation results must be verified by a licensed PE.
  ⚠️  Never use simulation output as the sole basis for life-safety decisions.

Known Limitations (documented, not hidden):
  1. Navier-Stokes uses fractional-step with missing cross-advection terms
  2. Smoke transport uses turbulent diffusivity (CFAST-calibrated)
  3. No radiation heat transfer model
  4. Multi-zone uses 2-layer zone model (not CFD)
  5. Detector model uses probabilistic noise (LCG PRNG, not crypto-grade)

Digital Twin Level: 4 (Physics-based multi-domain)
"""
