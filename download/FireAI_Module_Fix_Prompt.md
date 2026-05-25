# FireAI — Corrected Implementation Prompt for Three Pending Modules

**Project:** FireAI — NFPA 72 Fire Protection Engineering System  
**Repository:** https://github.com/ahmdelbaz28-ux/revit.git  
**Branch:** main  
**Date:** 2026-05-21  
**Classification:** Engineering Specification Document  
**NFPA Standard:** NFPA 72-2022 (National Fire Alarm and Signaling Code)  

---

## 0. Project Context — What FireAI Is and How It Works

FireAI is a **life-safety engineering system** that automates fire alarm system design per NFPA 72-2022. It is NOT a general-purpose building tool. Every module, every calculation, and every line of code directly affects whether people survive a fire. Incorrect code can kill.

### Architecture Overview

FireAI is a **monolithic Python application** with strict internal contracts. The core modules live in `fireai/core/`. Data flows through a **release gate system** — 8 verifiable gates that must ALL pass before any design output is released. A design that fails even one gate is BLOCKED.

```
Input (DXF/IFC/PDF)
    → Parser (ParsedDrawingContract)
    → Contracts Validation (validate_room_input / validate_loop_input)
    → NFPA 72 Engines (coverage, spacing, voltage, acoustics)
    → Release Gates (8 gates, verified mode)
    → BOQ / Report / Output
```

### Key Principle: STRICT_ENGINEERING Mode

FireAI operates in STRICT_ENGINEERING mode. This means:
- **No derived fields in input** — fields like `area_m2`, `spacing_m`, `is_compliant` are computed internally and MUST NEVER be accepted from external input (prevents data injection that could fake compliance).
- **Fail-safe defaults** — missing data defaults to BLOCKED, not passed.
- **Correct NFPA references** — every code citation must be verified against NFPA 72-2022. Citing the wrong section is not a cosmetic issue; it means the wrong engineering rule was applied.
- **Undefined classes are forbidden** — you cannot reference a `Device` class that does not exist in the codebase. All data structures must use the existing dataclass/contract system.

### Existing Data Structures You MUST Use

These are already defined and used throughout the codebase. Any new module MUST integrate with them, not invent new parallel structures:

| Structure | Module | Purpose |
|-----------|--------|---------|
| `RoomSpecificationContract` | `contracts.py` | Room input with polygon, ceiling spec, detector type |
| `DetectorPlacementContract` | `contracts.py` | Detector positions output with coverage fraction |
| `ComplianceReportContract` | `contracts.py` | NFPA 72 compliance result |
| `AuditEventContract` | `contracts.py` | Tamper-proof audit trail |
| `CeilingType` (Enum) | `contracts.py` | FLAT, SLOPED, BEAMED, COFFERED, DOMED, etc. |
| `DetectorType` (Enum) | `contracts.py` | SMOKE, HEAT, DUCT, FLAME, GAS, etc. |
| `IsolatorInjectionResult` | `fault_isolator_injector.py` | SLC loop with fault isolators inserted |
| `IsolatorPlacement` | `fault_isolator_injector.py` | Record of a single isolator injection |
| `FireScenario` | `semi_cfast_engine.py` | Fire scenario for ASET calculation |
| `TenabilityCriteria` | `semi_cfast_engine.py` | Temperature, visibility, CO, O2 limits |
| `ASETResult` | `semi_cfast_engine.py` | Available Safe Egress Time result |
| `RoomSpec` | `nfpa72_models.py` | Room with Shapely polygon, CeilingSpec, HVACDuct list |
| `HVACDuct` | `nfpa72_models.py` | HVAC duct descriptor (duct_id, centerline, dimensions, airflow) |
| `CeilingSpec` | `nfpa72_models.py` | Ceiling with height, slope, beam parameters |
| `DetectorPlacement` | `nfpa72_models.py` | Individual detector position (x, y, z, coverage_radius) |
| `FireAlarmPanel` | `nfpa72_models.py` | FACP with device list, zones, voltage |
| `DuctSpec` | `duct_detector.py` | Duct specification for detector placement |
| `BOQItem` | `boq_generator.py` | Bill of quantities line item |
| `BOQResult` | `boq_generator.py` | Complete BOQ with detector/isolator/cable/battery counts |
| `SPLResult` / `AudibilityResult` | `acoustic_calculator.py` | Speaker SPL and NFPA 72 §18.4 compliance |
| `RELEASE_GATES` | `release_gates.py` | 8 release gates with NFPA references |

### Release Gate System (release_gates.py)

The 8 gates that must ALL pass before a design is released:

| Gate | Name | NFPA Reference | What It Verifies |
|------|------|----------------|-----------------|
| 1 | `input_contract_valid` | General | No derived field injection, valid polygon |
| 2 | `nfpa_compliance_verified` | §17.6.3.1.1, §17.7.4.2.3.1 | All spacing/coverage checks passed |
| 3 | `evidence_chain_sealed` | §7.4 | HMAC-verified audit trail |
| 4 | `no_drift_detected` | General | Design matches current BIM |
| 5 | `stale_surfaces_removed` | General | No orphaned detectors from old runs |
| 6 | `fault_isolation_verified` | §12.3.1, §12.3.2 | All SLC loops have fault isolators |
| 7 | `aset_rset_valid` | SFPE / NFPA 101 §9.3 | ASET > RSET with safety margin |
| 8 | `battery_sized` | §10.6.7.2.1 | Battery capacity computed and adequate |

---

## 1. MEPSyncInjector — MEP Integration Module

### 1.1 Why This Module Is Needed

Currently, FireAI designs fire alarm systems in isolation — it places detectors and verifies NFPA 72 compliance, but it does NOT interact with the building's Mechanical, Electrical, and Plumbing (MEP) systems. In a real building, the fire alarm system MUST interface with:

1. **HVAC systems** — Air handling units (AHUs) must shut down upon fire alarm to prevent smoke spread through ductwork. Per NFPA 72 §21.7 and NFPA 90A, this is mandatory for units > 2000 CFM.
2. **Elevator systems** — Elevators must recall to the designated floor upon fire alarm. Per NFPA 72 §21.3 and ASME A17.1, this is a two-phase process (Phase I recall + Phase II firefighter service).
3. **Fire suppression systems** — Flow switches, tamper switches, and fire pump status must be monitored. Per NFPA 72 §21.4, these require monitor modules on the fire alarm panel.
4. **Access control / egress** — Magnetic door holders must release upon fire alarm. Per NFPA 101 §7.2.1, egress paths must remain unlocked.

Without this module, FireAI's BOQ will always be incomplete — it won't include the monitor modules, control modules, and relay outputs needed for MEP integration.

### 1.2 Problems with the Original Proposal

The original `MEPSyncInjector` code from `_studio_cod(1).txt` has the following critical defects:

**Defect 1: Uses an undefined `Device` class**

The original code creates objects like:
```python
mod = Device(type='MONITOR_MODULE', x=element.x + 0.5, y=element.y)
```

There is NO `Device` class in the FireAI codebase. This code will raise `NameError` at runtime. You MUST use the existing data structure system. The correct approach is to return a list of dicts compatible with the existing `loop_devices` format used by `fault_isolator_injector.py` and `boq_generator.py`, or create a proper dataclass.

**Defect 2: Incomplete elevator recall implementation**

The original code groups elevator controllers with access control doors:
```python
elif element.type in ['ELEVATOR_CONTROLLER', 'ACCESS_CONTROL_DOOR']:
```

This is wrong. Elevator recall is a complex, two-phase process governed by NFPA 72 §21.3 and ASME A17.1:

- **Phase I Recall**: Upon smoke detector activation in an elevator lobby, hoistway, or machine room, the elevator returns to the designated recall floor. This requires:
  - A smoke detector in each elevator lobby (per §21.3.3)
  - A smoke detector in the elevator machine room (per §21.3.4)
  - A smoke detector at the top of the elevator hoistway (per §21.3.5)
  - A control module to send the recall signal to the elevator controller
  - Different recall floors depending on which detector activates (lobby vs. machine room)

- **Phase II Emergency Operation**: After recall, firefighters can operate the elevator using a key switch inside the car. This is an elevator system function, not a fire alarm function, but the fire alarm system must NOT interfere with Phase II operation.

The original code completely misses Phase I/Phase II distinction, does not specify lobby/machine room/hoistway detector requirements, and treats elevator recall as a simple relay output — which is dangerous.

**Defect 3: Incomplete HVAC shutdown sequence**

The original code checks only `element.capacity_cfm > 2000` for AHU shutdown. While the 2000 CFM threshold is correct per NFPA 72 §17.7.5.1 and NFPA 90A §6.4, the HVAC shutdown sequence requires:

1. **Smoke detector activation** in the supply or return duct triggers AHU shutdown
2. **Motorized fire dampers** must close simultaneously (per NFPA 90A §5.3)
3. **The shutdown signal must be supervised** — per NFPA 72 §21.6, the connection between the fire alarm system and the HVAC system must be monitored for integrity
4. **Multiple AHU zones** may need staged shutdown — shutting down all AHUs at once can cause pressurization problems

The original code also misses the `FCU` (Fan Coil Unit) category — FCUs below 2000 CFM may not require duct detectors but may still need to be shut down via control module if they serve critical spaces.

**Defect 4: Missing NFPA 90A cross-reference**

The original code cites only NFPA 72 §21.3 and §21.7, but the HVAC integration requirements come primarily from NFPA 90A (Standard for the Installation of Air-Conditioning and Ventilating Systems), not NFPA 72 alone. NFPA 72 §21.7 tells you WHAT to do (shut down HVAC upon fire alarm), but NFPA 90A tells you HOW (detector placement, damper closure, shutdown sequencing).

### 1.3 What the Correct Implementation Must Do

The corrected `MEPSyncInjector` module (file: `fireai/core/mep_sync_injector.py`) must:

1. **Define proper dataclasses** for MEP interface modules that integrate with the existing contract system. Suggested structure:

```python
@dataclass(frozen=True)
class MEPInterfaceModule:
    """A monitor or control module required for MEP integration."""
    module_type: str              # "MONITOR_MODULE" or "CONTROL_MODULE"
    mep_element_type: str         # "FLOW_SWITCH", "AHU", "ELEVATOR_CONTROLLER", etc.
    position: Tuple[float, float] # (x, y) position
    address_type: str             # "INPUT" for monitor, "OUTPUT_RELAY" for control
    nfpa_citation: str            # e.g., "NFPA 72-2022 §21.7 / NFPA 90A §6.4"
    justification: str            # Human-readable reason
    supervised: bool              # Per NFPA 72 §21.6
    recall_phase: Optional[str]   # "PHASE_I" for elevator recall, None otherwise
```

2. **Implement complete elevator recall per NFPA 72 §21.3**:
   - Detect elevator controllers from MEP elements
   - For each elevator, require:
     - Smoke detector in each lobby → trigger Phase I recall to designated floor
     - Smoke detector in machine room → trigger Phase I recall to alternate floor
     - Smoke detector in hoistway → trigger Phase I recall to designated floor
     - Control module for recall signal to elevator controller
     - Verify Phase I recall does NOT interfere with Phase II firefighter service
   - Cite: NFPA 72-2022 §21.3.1 through §21.3.8, ASME A17.1

3. **Implement complete HVAC shutdown per NFPA 72 §21.7 and NFPA 90A**:
   - Detect AHUs, FCUs, and motorized fire dampers from MEP elements
   - For AHUs > 2000 CFM:
     - Duct smoke detector in supply AND return (per NFPA 90A §6.4.2)
     - Control module for AHU shutdown signal (supervised per §21.6)
     - Control module for fire damper closure (simultaneous with AHU shutdown)
   - For FCUs < 2000 CFM in critical spaces:
     - Control module for shutdown (not duct detector, but still needs shutdown)
   - Cite: NFPA 72-2022 §21.7.1 through §21.7.4, NFPA 90A-2024 §5.3, §6.4

4. **Implement fire suppression monitoring per NFPA 72 §21.4**:
   - Flow switches → Monitor module (INPUT)
   - Tamper switches → Monitor module (INPUT)
   - Fire pump status → Monitor module (INPUT)
   - All connections must be supervised per §21.4.1

5. **Implement egress control per NFPA 101 §7.2.1**:
   - Access control doors → Control module (OUTPUT_RELAY) for magnetic lock release
   - Door holders → Control module (OUTPUT_RELAY) for release upon alarm

6. **Integrate with BOQ generator** — the `generate_full_boq()` function in `boq_generator.py` must be extended to include MEP interface modules. The `UNIT_COSTS` dict already has entries for `monitor_module` ($55) and `control_module` ($65).

7. **Return results in a format compatible with the existing loop system** — MEP modules are addressable devices that go on SLC loops, so the result must be compatible with `fault_isolator_injector.py` and `verify_isolator_compliance()`.

### 1.4 Integration Points

The module must integrate with these existing files:
- `contracts.py` — Use existing enums (DetectorType, CeilingType), follow FORBIDDEN_DERIVED_FIELDS rules
- `nfpa72_models.py` — Use existing HVACDuct dataclass, extend if needed
- `duct_detector.py` — Use DuctSpec and analyse_duct() for duct detector placement
- `boq_generator.py` — Extend generate_full_boq() to include MEP modules
- `fault_isolator_injector.py` — MEP modules count as devices on SLC loops
- `release_gates.py` — Consider adding a Gate 9 for MEP integration verification

---

## 2. AutoDraftingEngine — Fire Alarm Shop Drawing Generator

### 2.1 Why This Module Is Needed

FireAI currently produces engineering calculations and compliance reports, but not actual construction documents. A fire alarm system design is useless to a contractor without shop drawings showing:
- Where each device is physically located on the floor plan
- How cables are routed between devices
- Which devices are on which SLC loop and zone
- Where fault isolators are placed
- What device types are used (with address labels)

The goal of AutoDraftingEngine is to generate DXF shop drawings from FireAI's design output that a contractor can use for installation.

### 2.2 The Critical Problem: Orthogonal Routing Through Walls

The original `AutoDraftingEngine` code from `_studio_cod(1).txt` uses this routing algorithm:

```python
# Create 90-degree orthogonal path instead of direct diagonal line
corner_pt = Vec2(end_pt.x, start_pt.y)
self.msp.add_lwpolyline([start_pt, corner_pt, end_pt], ...)
```

This creates an L-shaped path from device A to device B by going horizontally to `corner_pt` (which shares B's X coordinate and A's Y coordinate), then vertically to B. **This is catastrophically dangerous** because:

1. **The corner point is not constrained to corridors or ceiling spaces.** If device A is in Room 101 at (5, 10) and device B is in Room 205 at (30, 25), the corner point is at (30, 10) — which could be inside a structural wall, a concrete column, an elevator shaft, or a mechanical chase. Running fire alarm cable through a structural wall is:
   - Physically impossible without core drilling
   - A building code violation (cables cannot penetrate fire-rated walls without firestopping)
   - A life-safety hazard (cable damaged during construction or by building movement will disable the fire alarm circuit)

2. **Fire alarm cable routing in real buildings follows specific rules:**
   - Cables run in **corridors and ceiling plenums** where conduit is accessible
   - Cables must NOT penetrate **fire-rated walls** unless firestopped with listed penetration seals
   - Cables follow the building's **structural grid** — they run parallel to walls, not through them
   - Class A (style D) circuits require a **separate return path** that must be physically separated from the outgoing path by at least 1m (per NFPA 72 §12.2.2)

3. **The "orthogonal routing" algorithm has no awareness of the building geometry.** It does not know where walls are, where corridors are, where shafts are, or where it is safe to route cable. A proper routing algorithm requires:
   - Wall geometry from the parsed floor plan
   - A routing graph that follows corridors and plenum spaces
   - Pathfinding (e.g., A* on a grid or visibility graph) that avoids walls
   - Fire-rated wall penetration detection and firestopping annotation

### 2.3 Additional Problems with the Original Proposal

**Problem 1: Undefined DXF block references**

The original code uses:
```python
self.msp.add_blockref(f"FA_{dev.type}", insert=(dev.x, dev.y), ...)
```

These block references (`FA_SMOKE_DETECTOR`, `FA_HEAT_DETECTOR`, etc.) do not exist. The code will crash when opened in AutoCAD because the block definitions are missing. A correct implementation must either:
- Define the block definitions programmatically (simple geometric shapes + attributes)
- Use a template DXF file that contains the block definitions
- Use simple entities (circles, lines, text) instead of block references

**Problem 2: Missing critical shop drawing elements**

A fire alarm shop drawing requires far more than just device symbols and wiring:

| Element | NFPA/Standard Reference | Original Code |
|---------|------------------------|---------------|
| Device symbols (blocks) | AEC CAD Standards | Partial (undefined blocks) |
| Cable routing (polylines) | — | Broken (through walls) |
| Title block | AEC CAD Standards | ❌ Missing |
| Legend / Symbol table | AEC CAD Standards | ❌ Missing |
| Device schedule (table) | NFPA 72 §7.4 | ❌ Missing |
| Zone boundaries | NFPA 72 §12.3 | ❌ Missing |
| Fault isolator locations | NFPA 72 §12.3.1 | ❌ Missing |
| Cable type labels (FPL/FPLR/FPLP) | NEC Art. 760 | ❌ Missing |
| Address labels (loop-device) | NFPA 72 §21.2 | Partial (text only) |
| Layer standards (FA-DEVICES, FA-WIRING, etc.) | AEC CAD Standards | Partial (3 layers only) |
| North arrow | AEC CAD Standards | ❌ Missing |
| Scale bar | AEC CAD Standards | ❌ Missing |
| Revision table | AEC CAD Standards | ❌ Missing |
| Room numbers / names | — | ❌ Missing |
| Fire-rated wall indicators | IBC / Local code | ❌ Missing |
| Firestopping callouts at penetrations | IBC §714 | ❌ Missing |

**Problem 3: No wall-aware routing algorithm**

The orthogonal L-shaped routing algorithm is fundamentally inadequate. The correct approach requires:

1. **Extract wall geometry** from the parsed floor plan (already available from `ParsedDrawingContract.layers` and `ParsedDrawingContract.entities`)
2. **Build a routing graph** where edges represent traversable paths (corridors, plenum spaces, shafts)
3. **Run pathfinding** (A* or Dijkstra) on the routing graph to find the shortest wall-avoiding path
4. **Post-process** the path into orthogonal segments (Manhattan routing) with fillets at corners
5. **Check for fire-rated wall penetrations** and add firestopping callouts if unavoidable

### 2.4 What the Correct Implementation Must Do

The corrected `AutoDraftingEngine` module (file: `fireai/core/auto_drafting_engine.py`) must:

1. **Define block definitions programmatically** using ezdxf:
   - Create simple geometric symbols for each device type (circle for smoke detector, square for heat detector, triangle for pull station, diamond for monitor/control module, hexagon for fault isolator)
   - Include attribute definitions for address labels (loop ID, device address)
   - Use consistent colors per NFPA convention (red for devices, yellow for Class A wiring, green for Class B wiring, blue for notification circuits)

2. **Implement wall-aware routing**:
   - Extract wall polylines from the parsed floor plan
   - Build a routing graph with nodes at corridor intersections and device locations
   - Use A* pathfinding to find shortest paths that avoid walls
   - Convert paths to orthogonal polylines with rounded corners (fillets)
   - Flag any unavoidable fire-rated wall penetrations with firestopping callouts
   - Separate Class A outgoing and return paths by minimum 1m (NFPA 72 §12.2.2)

3. **Generate complete shop drawing sheets**:
   - Title block with project name, drawing number, scale, date, revision
   - Legend / symbol table explaining all device symbols
   - Device schedule (table) with type, address, zone, location
   - Zone boundary shading and labels
   - North arrow and scale bar
   - Revision table

4. **Use correct CAD layer structure** per AEC standards:
   - FA-DEVICES (red) — device symbols
   - FA-WIRING-CLASSA (yellow) — Class A circuit wiring
   - FA-WIRING-CLASSB (green) — Class B circuit wiring
   - FA-NAC (blue) — notification appliance circuits
   - FA-ZONES (magenta, screened) — zone boundary shading
   - FA-ISOLATORS (orange) — fault isolator symbols
   - FA-LABELS (white) — address labels
   - FA-LEGEND (white) — legend and schedule
   - FA-TITLEBLOCK (white) — title block and border
   - WALLS (gray, screened) — background floor plan walls

5. **Integrate with existing FireAI output**:
   - Accept `DetectorPlacementContract` results for device positions
   - Accept `IsolatorInjectionResult` for fault isolator positions
   - Accept `BOQResult` for device schedule generation
   - Accept `ComplianceReportContract` for compliance notes

### 2.5 Safety-Critical Requirements

- **NEVER route cable through a wall without explicit firestopping annotation**. If the routing algorithm cannot find a wall-avoiding path, it must flag the penetration and add a callout specifying the required firestopping system.
- **NEVER place a device symbol on top of a wall**. Device positions must be verified against wall geometry.
- **Class A return paths MUST be physically separated from outgoing paths** by at least 1m. Drawing them in the same conduit defeats the purpose of Class A redundancy.

---

## 3. BlockchainReadinessGate — Design Hash Anchoring Module

### 3.1 Current Status and Priority

This module is **low priority** and should be implemented LAST, after MEPSyncInjector and AutoDraftingEngine are complete and tested.

### 3.2 The Problem: It Is Not a Real Merkle Tree

The original `BlockchainReadinessGate` code from `_studio_cod(1).txt` does this:

```python
manifest_str = json.dumps(manifest, sort_keys=True, separators=(',', ':'))
project_root_hash = hashlib.sha256(manifest_str.encode('utf-8')).hexdigest()
```

This is a simple SHA-256 hash of a JSON manifest, not a Merkle tree. A Merkle tree is a binary tree where:
- Each leaf node is the hash of a data block
- Each internal node is the hash of its two children concatenated
- The root hash uniquely identifies the entire tree
- You can verify any individual data block by providing only the block's hash and the sibling hashes along the path to the root (a "Merkle proof")

The current code provides NONE of these properties. It is just a single hash of everything combined. This means:
- You cannot verify an individual component (e.g., "was this room's calculation modified?") without re-hashing the entire manifest
- There is no Merkle proof capability
- Calling it "Merkle root" is misleading — it implies capabilities the code does not have
- It provides no advantage over the existing `evidence_chain.py` which already hashes audit events with HMAC

### 3.3 What the Correct Implementation Must Do (When Prioritized)

If and when this module is implemented, it should:

1. **Build a proper Merkle tree** where each leaf is the hash of one design component:
   - Leaf 1: hash(room_1_compliance_result)
   - Leaf 2: hash(room_2_compliance_result)
   - Leaf N: hash(BOQ_result)
   - Leaf N+1: hash(MEP_interface_data)
   - Leaf N+2: hash(routing_topology)
   - etc.

2. **Support Merkle proofs** — given a room_id and the Merkle root, verify that the room's compliance result has not been tampered with, using only O(log n) sibling hashes.

3. **Integrate with the existing evidence_chain.py** — the Merkle root should be anchored into the existing audit trail, not replace it. The evidence chain already provides HMAC-signed audit events; the Merkle tree adds efficient individual-component verification on top.

4. **Use the correct terminology** — if it's just a SHA-256 hash of a manifest, call it `design_manifest_hash`, not `merkle_root`.

5. **Cite the correct standard** — the original code cites "ISO 27001 / Smart Contract Integration." ISO 27001 is an information security management standard, not a cryptographic data structure standard. The correct reference for Merkle trees is the Bitcoin whitepaper (Nakamoto, 2008) or RFC 6962 (Certificate Transparency).

### 3.4 Recommended Implementation Priority

| Priority | Module | Reason |
|----------|--------|--------|
| 1 (Highest) | MEPSyncInjector | Directly affects life safety — HVAC/elevator integration is code-mandatory |
| 2 (High) | AutoDraftingEngine | Required for contractor-useful output, but routing must be wall-aware |
| 3 (Low) | BlockchainReadinessGate | Nice-to-have audit feature, not life-safety critical; existing evidence_chain.py covers the immediate need |

---

## 4. Mandatory Development Rules

These rules apply to ALL three modules. They are non-negotiable.

### 4.1 Agent.MD Compliance

The project follows 8 mandatory rules from AGENT.MD:

1. **ABSOLUTE_TRUTH** — Never fabricate NFPA references or compliance results
2. **NO_UNAUTHORIZED_CHANGES** — Only modify the files specified in the task
3. **STOP_ON_ERRORS** — If a test fails, stop and report; do not proceed
4. **NEVER_SELF_EDIT** — Do not modify the prompt or requirements to make them easier
5. **EXPLAIN_AFTER_EACH_STEP** — Document what was done and why after each code change
6. **VERIFY_BEFORE_CHANGING** — Read and understand existing code before modifying it
7. **COMMIT_REPORTING** — Report all changes in the worklog before committing
8. **WORKSPACE** — All work must be done in `/home/z/my-project/revit/`

### 4.2 Code Quality Requirements

- **Type hints everywhere** — all function signatures must have complete type annotations
- **Docstrings with NFPA references** — every public function must cite the relevant NFPA 72 section
- **Frozen dataclasses** — all data structures must be immutable (frozen=True) unless mutation is absolutely necessary
- **No bare exceptions** — catch specific exceptions, never use bare `except:`
- **Contract validation** — all input must pass through `validate_room_input()` or `validate_loop_input()` before processing
- **Logging, not printing** — use `logging.getLogger(__name__)`, not `print()`

### 4.3 Testing Requirements

- Every module must have a corresponding test file (`test_mep_sync_injector.py`, `test_auto_drafting_engine.py`, etc.)
- Tests must cover: happy path, boundary conditions, invalid input, life-safety edge cases
- Integration tests must verify that the module works with the release gate system
- No test may pass if it relies on an undefined class or missing import

### 4.4 NFPA Citation Format

All NFPA citations must follow this format:
```
NFPA 72-2022 §<section_number>
```

Examples:
- Correct: `NFPA 72-2022 §12.3.1`
- Correct: `NFPA 72-2022 §21.7.2`
- Incorrect: `§23.6.1` (wrong chapter — this refers to Emergency Communications, not fault isolation)
- Incorrect: `NFPA 72 §12.3` (missing edition year)

When citing NFPA 90A:
```
NFPA 90A-2024 §<section_number>
```

---

## 5. Summary of Deliverables

| Module | File | Priority | Key Fix |
|--------|------|----------|---------|
| MEPSyncInjector | `fireai/core/mep_sync_injector.py` | 1 (Highest) | Proper dataclasses, complete elevator Phase I/II, complete HVAC shutdown with NFPA 90A, fire suppression monitoring, egress control |
| AutoDraftingEngine | `fireai/core/auto_drafting_engine.py` | 2 (High) | Wall-aware routing (A* pathfinding), programmatic block definitions, complete shop drawing elements, firestopping annotations |
| BlockchainReadinessGate | `fireai/core/blockchain_readiness_gate.py` | 3 (Low) | Real Merkle tree with proof capability, or honest rename to design_manifest_hash, correct standards citation |

Each module must also produce:
- A test file with comprehensive coverage
- Integration with the existing release gate system
- Extension of the BOQ generator where applicable
- Documentation of all NFPA references used
