"""
twin/ — FireAI Level 4 Digital Twin Engine
============================================

Architecture:
  StateEngine       → Deterministic state management with event sourcing
  NFPA72Bridge      → Bi-directional NFPA 72 calculation interface
  FirePhysics       → Physics-based fire simulation (zone + CFD-lite)
  SimulationLayer   → High-level simulation with detector tracking + NFPA 72
  SemiCFASTEngine   → Conservation-law-compliant Semi-CFAST physics engine
  AuditEventStore   → WAL-backed immutable event log with SHA-256 hash chain

Safety Classification:
  ⚠️  This module implements SIMPLIFIED fire physics, NOT full CFD.
  ⚠️  All simulation results must be verified by a licensed PE.
  ⚠️  Never use simulation output as the sole basis for life-safety decisions.

Semi-CFAST Engine (NEW - 2026-05-19):
  Replaces the previous event-driven visualization approach with proper
  conservation-law-compliant physics. 11 phases implemented:

  Phase 1:  LayerState + RoomCompartment (conservation of mass)
  Phase 2:  LayerEnergySolver (conservation of energy, semi-implicit)
  Phase 3:  PlumeModel (Heskestad entrainment)
  Phase 4:  VentFlowSolver (bi-directional with neutral plane)
  Phase 5:  SmokeLayerSolver (conservation-consistent interface height)
  Phase 6:  SpeciesTransport (O2, CO2, CO, soot conservation)
  Phase 7:  CombustionModel (fuel-controlled → ventilation-controlled → decay)
  Phase 8:  DetectorPhysics (RTI model per NFPA 72 §17.6.3)
  Phase 9:  WallThermalSolver (1-D transient conduction)
  Phase 10: SemiCFASTSolver (coupled multi-compartment solver)
  Phase 11: NumericalStability (adaptive timestep, mass correction, energy clipping)

Known Limitations (documented, not hidden):
  1. Two-layer zone model (not CFD) — spatial variations within layers ignored
  2. No HVAC coupling (future enhancement)
  3. No inverse modeling / data assimilation (future: Bayesian inference)
  4. Wall conduction uses 1-D implicit solve (not 3-D)
  5. Species reactions are simplified (no detailed kinetics)
  6. Radiation modeled via correlation (not ray-tracing)
  7. Navier-Stokes uses fractional-step (cross-advection fixed in V2)
  8. Detector model uses probabilistic noise (LCG PRNG, not crypto-grade)

Bug Fixes Applied (from Consultant Code Review 2026-05-19):
  BUG 3: Timer-based detector checking (not int(t) % 30) → simulation_layer.py
  BUG 4: Proper lower-layer temperature with plume impact → simulation_layer.py
  BUG 5: Grid-based coverage + ceiling height adjustment → nfpa72_bridge.py
  BUG FIX: det.x → det.y for y-axis wall distance → nfpa72_bridge.py line 310

Digital Twin Level: 4 (Physics-based multi-domain)
"""
