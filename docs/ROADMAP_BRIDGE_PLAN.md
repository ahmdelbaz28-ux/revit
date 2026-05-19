# FireAI → Digital Twin: Realistic Implementation Roadmap

> Based on consultant's 7-bridge vision, adapted to actual codebase state.
> Date: 2026-05-18

## Current State Assessment

### ✅ Bridge 1: Foundation — COMPLETE
All critical bugs fixed:
- R = 0.7 × S (not S/2) — 96.5% more coverage area per detector
- HEAT_FIXED = 6.1m (not 15.2m)  
- Import shadowing bug discovered and fixed (stale root copies)
- 20/20 stress test PASS

### Architecture Reality Check
- **3 overlapping core systems**: `fireai/` (pip package), `src/` (V8 clean arch), `core/` (legacy)
- **IFC/BIM**: Already exists at `integration/ifc_bridge.py` with `ifcopenshell`
- **Multi-Standard**: GCC codes exist in `fire-alarm-db/standards/`
- **Digital Twin**: Started but DISABLED in V8
- **428 Python files**, 60+ test files, 60+ audit logs

---

## Bridge 2: Triple Verification (Defense-in-Depth)

**Goal**: If one engine has a bug, the other two catch it.  
**Duration**: 4-6 weeks  
**Effort**: Medium-High  

### Current State (2 layers):
1. **Coarse pass**: any-detector check (fast filter)
2. **Fine pass**: δ-conservative grid check (safe proof)

### Implementation Plan:

#### Step 2.1: Analytical Verification Engine
- Pure formula: R = 0.7 × S, check each point
- Independent of grid resolution
- Serves as "oracle" for the other two engines

#### Step 2.2: Voronoi Verification Engine  
- Uses Shapely Voronoi to find largest uncovered gap
- Independent of grid sampling
- Different failure modes from grid-based approach

#### Step 2.3: Consensus Protocol
```
3/3 PASS → VERIFIED (green)
2/3 PASS → WARNING  (yellow) — investigate discrepancy
1/3 PASS → FAIL     (red)    — DO NOT deploy
```

#### Step 2.4: Cross-Engine Test Suite
- Generate 1000 random rooms
- All 3 engines must agree
- If they disagree → that's a bug to fix

### Files to Create:
- `fireai/core/spatial_engine/analytical_verifier.py`
- `fireai/core/spatial_engine/voronoi_verifier.py`
- `fireai/core/spatial_engine/consensus_engine.py`
- `tests/test_triple_verification.py`

---

## Bridge 3: Proof Certificate (Mathematical Proof)

**Goal**: Generate a machine-readable proof that coverage is complete.  
**Duration**: 3-4 weeks  
**Effort**: High  

### Current State:
- δ-conservative grid check exists but doesn't produce a formal certificate
- The proof is implicit, not explicit

### Implementation Plan:

#### Step 3.1: Proof Certificate Data Structure
```python
@dataclass
class CoverageProof:
    room_id: str
    method: str  # "delta_conservative_grid"
    delta_m: float  # grid resolution
    coverage_radius_m: float
    effective_radius_m: float  # R - δ√2/2
    n_grid_points: int
    n_covered: int
    n_uncovered: int
    coverage_lower_bound: float  # mathematical guarantee
    proof_hash: str  # SHA-256 of all inputs + result
    timestamp: str
```

#### Step 3.2: Lower Bound Theorem
- For δ-conservative grid with cell size δ:
  - Every room point P has a grid point G within distance δ√2/2
  - If G is covered by R_eff = R - δ√2/2, then P is covered by R
  - Coverage ≥ 1 - (n_uncovered × π × (δ/2)²) / A_room

#### Step 3.3: AHJ-Ready Report
- Generate PDF with proof certificate
- Include: room dimensions, detector positions, coverage guarantee
- AHJ can verify independently

### Files to Create:
- `fireai/core/spatial_engine/proof_certificate.py`
- `fireai/core/reporting/ahj_report.py`
- `tests/test_proof_certificate.py`

---

## Bridge 4: BIM Integration (IFC Pipeline)

**Goal**: Read IFC files → extract rooms → run NFPA 72 compliance → write results back  
**Duration**: 6-8 weeks  
**Effort**: High  

### Current State:
- `integration/ifc_bridge.py` exists (18KB) with ifcopenshell
- But NOT connected to density_optimizer
- `fire-alarm-db/standards/` has multi-standard data (not used)

### Implementation Plan:

#### Step 4.1: IFC → RoomSpec Pipeline
```python
ifc_file → IfcSpace → RoomSpec → DensityOptimizer → DetectorLayout
```

#### Step 4.2: Detector Placement → IFC Export
```python
DetectorLayout → IfcDistributionElement → Write back to IFC
```

#### Step 4.3: Multi-Standard Engine
- NFPA 72 (already done)
- BS 5839-1 (UK)
- EN 54 (Europe)
- GCC codes (Saudi, UAE, etc.)

### Files to Create/Modify:
- `fireai/core/bim/ifc_pipeline.py` (new)
- `fireai/core/bim/room_extractor.py` (new)
- `fireai/core/bim/detector_writer.py` (new)
- `fireai/core/standards/bs5839_provider.py` (new)
- `fireai/core/standards/en54_provider.py` (new)
- `fireai/core/standards/standard_factory.py` (new)

---

## Bridge 5: Codebase Consolidation

**Goal**: Merge 3 overlapping systems into 1 clean architecture  
**Duration**: 4-6 weeks  
**Effort**: High (refactoring, not new features)

### Problem:
- `fireai/` (current pip package)
- `src/` (V8 clean architecture)  
- `core/` (legacy cognitive kernel)
- All 3 have overlapping NFPA72 models, coverage checks, etc.

### Plan:
1. `fireai/` is the canonical package — keep it
2. Migrate unique functionality from `src/` into `fireai/`
3. Archive `core/` as deprecated
4. Delete dead code, disabled modules, duplicate files

---

## Bridge 6-7: Simulation + Real-Time (Future)

These are long-term goals. Not practical until Bridges 2-5 are solid.

### Simulation (4-6 months):
- Smoke movement model (zone model, not full CFD)
- Detection time calculator
- "What-if" scenario analysis

### Real-Time + AI (6-12 months):
- BACnet/MQTT integration
- Live detector status monitoring
- Predictive maintenance

---

## Priority Order (Logical Dependencies)

```
Bridge 1: Foundation ✅ DONE
    ↓
Bridge 5: Codebase Consolidation ← Do this BEFORE adding more features!
    ↓
Bridge 2: Triple Verification ← Makes consolidation more valuable
    ↓
Bridge 3: Proof Certificate ← Makes verification commercially viable
    ↓
Bridge 4: BIM Integration ← Makes the system a real product
    ↓
Bridge 6: Simulation ← Future
    ↓
Bridge 7: Real-Time + AI ← Future
```

**KEY INSIGHT**: Codebase consolidation (Bridge 5) should come BEFORE
adding verification engines (Bridge 2), because adding features to
3 overlapping systems creates 3× the maintenance burden.

However, Bridge 2 (Triple Verification) is more exciting and directly
improves safety. A pragmatic approach: do both in parallel, but keep
all new code ONLY in `fireai/` package.
