# FireAI Digital Twin — Architecture Change Proposal V2.0

**Date**: 2026-06-09  
**Role**: System Architect — BIM + CAD + Electrical Engineering AI Platform  
**Classification**: Mission-Critical Engineering Platform  
**Principle**: NEVER break existing project compatibility

---

## EXECUTIVE SUMMARY

This document proposes a phased architectural evolution from the current monolithic-with-adapters design to a fully decoupled, plugin-based, versioned, and sandboxed architecture. Every proposal is backward-compatible — existing projects load unchanged on the new architecture.

**Current state**: 8 top-level packages with 17 direct cross-module imports, 3 separate audit implementations, 3 separate SQLite databases, 7 hardcoded CAD parsers, no undo/rollback for CAD operations, no canonical project state schema, no formal plugin registration mechanism.

**Target state**: Plugin registry, strict dependency inversion, unified audit chain, single project state schema with versioning, sandboxed CAD operations with undo, verified AutoCAD↔Revit transformations, and NFPA/IEC validation as non-bypassable pipeline gate.

---

## 1. CURRENT ARCHITECTURE VIOLATIONS

### 1.1 Module Coupling Map (Violations Found)

| Source Module | Target Module | Import Type | Violation |
|---|---|---|---|
| `backend/routers/qomn.py` | `fireai/core/qomn_kernel.py` | Direct class import (`QOMNKernel`, `PhysicsGuardError`, `ComputationError`, `ValidationError`, guard functions) | **CRITICAL** — router directly instantiates kernel. Should use plugin interface. |
| `backend/routers/qomn.py` | `fireai/core/pipeline.py` | Direct function import (`analyze_room`) via lazy import | **HIGH** — router calls pipeline directly. No adapter layer. |
| `backend/services/workflow_service.py` | `parsers/dwg_parser.py`, `parsers/geometry_extractor.py` | Direct import inside LangGraph nodes | **HIGH** — AI workflow directly couples to parser internals. |
| `backend/db_service.py` | `core/database.py` | Direct import (`UniversalDataModel`) | **MEDIUM** — two database systems coupled through Python import. |
| `core/models.py` | `backend/schemas.py` | Conditional import (`ChangeSource`, `ConflictType`, `ElementType`) | **CRITICAL** — bidirectional coupling between `core/` and `backend/`. `core/` should not know about `backend/`. |
| `qomn_fire/parsers/*.py` | `parsers/_path_security.py` | Direct import of shared security module | **MEDIUM** — two separate parser packages share one security module. |
| `fireai/core/pipeline.py` | `fireai/core/qomn_kernel.py` | Direct import (`PhysicsGuardError`, `QOMNKernel`, guard functions) | **ACCEPTABLE** — same package, internal coupling. But should use abstract interface for testability. |

**Good news**: `fireai/` does NOT import from `backend/` (verified: zero matches). `backend/` imports from `fireai/core/` heavily — this is the primary coupling direction.

### 1.2 Singleton/Global State Coupling

| Singleton | Location | Risk |
|---|---|---|
| `_default_kernel = QOMNKernel()` | `fireai/core/qomn_kernel.py:1000` | Module-level singleton. Not injectable. Tests must use module-level object. |
| `_db = Database()` | `backend/database.py:976` (`get_db()` function) | Module-level singleton with `check_same_thread=False`. Hot-reload keeps stale connection. |
| `DatabaseService._instance` | `backend/db_service.py:49` | Double-checked locking singleton. Not injectable for testing. |
| `_FIREAI_API_KEY = os.getenv(...)` | `backend/database.py:35`, `backend/app.py` | Global mutable env read at module level. Cannot change after import. |
| `global_audit_logger` | `fireai/core/qomn_self_healing_engine.py:1022` | Module-level global. Not injectable. |
| `global_lru_cache` | `fireai/core/qomn_self_healing_engine.py:1028` | Module-level global. Not injectable. |
| `global_circuit_breaker` | `fireai/core/qomn_self_healing_engine.py` | Module-level global. Not injectable. |

### 1.3 AI↔Kernel Coupling Analysis

**Current separation**: GOOD. The `FireAIPluginAPI` (`fireai/core/api_stability.py`) provides a versioned adapter layer between external code and the kernel. The `hazard_override.py` module provides a **NON-BYPASSABLE** deterministic safety override that intercepts ALL AI hazard classifications and enforces mandatory minimums.

**Remaining violations**:
- `backend/routers/qomn.py` bypasses `FireAIPluginAPI` and calls `qomn_kernel.py` directly (7 imports)
- `backend/services/workflow_service.py` directly imports parsers without going through a plugin interface
- The MCP server (`fireai/mcp_server/sanitized_handler.py:381`) has `verify_and_override()` which applies overrides — but the override result flows back into `sanitized_params` with `_override_rationale`, meaning AI outputs are modified but not fully replaced. This is correct behavior (override only raises classification, never lowers it).

**No validation bypass found**: AI workflow results go through the same 5-layer pipeline (L0-L4). The workflow service does NOT skip NFPA validation. However, there is a development-only human review gate bypass at `backend/routers/workflow.py:156` that must be environment-gated (it is — only available in development).

### 1.4 CAD Operation Reversibility Gap

**Current state**: NO undo/rollback mechanism for CAD operations.

- Parser operations (DXF→rooms, DWG→rooms, IFC→rooms) are **one-way transforms** with no reverse operation
- Export operations (rooms→DXF, rooms→IFC, rooms→Revit) are also **one-way**
- No snapshot/restore mechanism for project state before CAD operations
- The `twin_db.py` module has `save_snapshot()` and `diff_snapshots()` but it's not integrated into the parser pipeline

**Risk**: A malformed DWG parse could corrupt project room data with no way to revert to pre-parse state.

### 1.5 Project State Schema Gap

**Current state**: THREE different project representations exist without a canonical schema:

| System | Schema | Fields | Version |
|---|---|---|---|
| System A (`backend/database.py`) | `projects` table | `id, name, description, author, created_at, updated_at, status` | None |
| System B (`backend/db_service.py`) | `projects` table | `project_id, name, description, status, metadata, created_timestamp, last_modified_timestamp` | None |
| Bridge (`backend/project_bridge.py`) | Maps System A→B with `_mapProjectFromSystemA()` | Converts `id→project_id`, `createdAt→createdTimestamp`, etc. | None |

Neither system has a `schema_version` field. Project data created in v1.0.0 has no version marker, making future migration impossible to detect.

---

## 2. ARCHITECTURE CHANGE PROPOSALS

### Proposal 1: Dependency Inversion Layer (DIL)

**Objective**: Eliminate all direct imports between `backend/` and `fireai/core/`.

**Design**:

```
fireai/core/interfaces.py  ←  Abstract interfaces (ABC)
  ├── ComputationKernel      (abstract: compute, validate, audit)
  ├── ParserGateway           (abstract: parse, detect_format, validate_path)
  ├── ProjectRepository       (abstract: create, read, update, delete, list)
  ├── AuditChain              (abstract: append, verify, export)
  └── ValidationEngine        (abstract: validate_nfpa72, validate_iec)

fireai/core/qomn_kernel.py   →  implements ComputationKernel
backend/database.py           →  implements ProjectRepository (System A)
backend/db_service.py         →  implements ProjectRepository (System B)

backend/routers/qomn.py       →  imports from interfaces.py, NOT qomn_kernel.py
backend/app.py                →  registers implementations via DI container
```

**Migration plan**:
- Phase 1 (v1.1.0): Create `fireai/core/interfaces.py` with ABC definitions
- Phase 2 (v1.1.0): Make `QOMNKernel` implement `ComputationKernel`
- Phase 3 (v1.2.0): Refactor `backend/routers/qomn.py` to use interface
- Phase 4 (v1.2.0): Remove direct `from fireai.core.qomn_kernel import` from routers

**Backward compatibility**: `QOMNKernel` still works directly. Interface is optional. No existing project breaks.

**Risk**: LOW. Interface layer is additive. Existing imports continue working during transition.

### Proposal 2: Plugin Registry

**Objective**: Enable feature registration without modifying core code.

**Design**:

```python
# fireai/core/plugin_registry.py

class PluginRegistry:
    """Central registry for all FireAI plugins.
    
    Plugins register themselves on startup. The app.py initialization
    calls registry.discover() to load all registered plugins.
    
    Categories:
      - computation: ComputationKernel implementations
      - parser: ParserGateway implementations (DXF, DWG, IFC, PDF, etc.)
      - export: Export plugins (DXF, IFC, Revit, PDF)
      - validation: ValidationEngine implementations (NFPA72, IEC, NEC)
      - audit: AuditChain implementations
      - service: External service adapters (weather, geocoding, etc.)
    """
    
    _registry: Dict[str, Dict[str, Type]] = {}
    
    @classmethod
    def register(cls, category: str, name: str, implementation: Type) -> None:
        cls._registry.setdefault(category, {})[name] = implementation
    
    @classmethod
    def get(cls, category: str, name: str) -> Type:
        return cls._registry[category][name]
    
    @classmethod
    def discover(cls) -> None:
        """Auto-discover plugins via entry_points or explicit registration."""
        # Import all known modules that contain register() calls
        ...
```

**Registration pattern**:

```python
# Each plugin module contains a register() function:

# fireai/core/qomn_kernel.py
def register():
    PluginRegistry.register("computation", "qomn", QOMNKernel)

# parsers/dxf_parser.py  
def register():
    PluginRegistry.register("parser", "dxf", DXFParser)

# parsers/dwg_parser.py
def register():
    PluginRegistry.register("parser", "dwg", DWGParser)
```

**Router usage pattern**:

```python
# backend/routers/qomn.py (refactored)
kernel_cls = PluginRegistry.get("computation", "qomn")
kernel = kernel_cls()
```

**Migration plan**:
- Phase 1 (v1.1.0): Create `PluginRegistry` class
- Phase 2 (v1.1.0): Add `register()` functions to existing modules
- Phase 3 (v1.2.0): Call `PluginRegistry.discover()` in `backend/app.py` startup
- Phase 4 (v1.3.0): Refactor routers to use registry instead of direct imports

**Backward compatibility**: Direct imports still work. Registry is optional.

**Risk**: LOW. No existing functionality changes.

### Proposal 3: Unified Project State Schema (UPSS)

**Objective**: Canonical, versioned project representation that both System A and System B can read.

**Design**:

```python
# fireai/core/project_schema.py

PROJECT_SCHEMA_VERSION = "1.0.0"

@dataclass(frozen=True)
class ProjectState:
    """Canonical project state — single source of truth.
    
    Both System A and System B must convert to/from this format.
    schema_version enables future migration detection.
    """
    schema_version: str = PROJECT_SCHEMA_VERSION
    project_id: str          # Unified ID (was 'id' in System A, 'project_id' in System B)
    name: str
    description: str
    status: str              # "active" | "draft" | "archived"
    author: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""     # ISO 8601 UTC
    updated_at: str = ""     # ISO 8601 UTC
    element_count: int = 0
    device_count: int = 0
    connection_count: int = 0
```

**Bridge conversion**:

```python
# backend/project_bridge.py (extended)

def system_a_to_upss(system_a_project: dict) -> ProjectState:
    """Convert System A (camelCase) to canonical ProjectState."""
    return ProjectState(
        project_id=system_a_project["id"],
        name=system_a_project["name"],
        ...

def system_b_to_upss(system_b_project: dict) -> ProjectState:
    """Convert System B (snake_case timestamps) to canonical ProjectState."""
    return ProjectState(
        project_id=system_b_project["project_id"],
        ...

def upss_to_system_a(state: ProjectState) -> dict:
    """Convert canonical back to System A format."""
    ...

def upss_to_system_b(state: ProjectState) -> dict:
    """Convert canonical back to System B format."""
    ...
```

**Migration plan**:
- Phase 1 (v1.1.0): Define `ProjectState` dataclass with `schema_version`
- Phase 2 (v1.1.0): Add `schema_version` column to both database tables
- Phase 3 (v1.2.0): Refactor `project_bridge.py` to use `ProjectState`
- Phase 4 (v1.3.0): All routers return `ProjectState`-compatible JSON

**Backward compatibility**: `schema_version` defaults to `"1.0.0"`. Old projects without it are treated as v1.0.0. No data migration needed.

**Risk**: MEDIUM. Database schema change requires migration framework (Alembic).

### Proposal 4: CAD Operation Sandbox with Undo

**Objective**: All CAD operations reversible; project state protected from malformed parses.

**Design**:

```python
# fireai/core/cad_sandbox.py

class CADOperationSandbox:
    """Sandboxed, reversible CAD operation execution.
    
    Before any parser/export operation:
    1. Snapshot current project state (twin_db.save_snapshot)
    2. Execute operation in isolated context
    3. Validate result (contract check, no NaN/Inf, no negative areas)
    4. If validation fails → rollback to snapshot
    
    All operations produce a OperationRecord for audit trail.
    """
    
    def __init__(self, project_id: str, twin_db: TwinDB):
        self.project_id = project_id
        self.twin_db = twin_db
        self._operation_log: List[OperationRecord] = []
    
    def execute_parse(
        self,
        parser_name: str,
        file_path: str,
        target_rooms: List[dict],
    ) -> Tuple[List[dict], OperationRecord]:
        """Parse a CAD file with automatic rollback on failure."""
        # 1. Snapshot
        snapshot_id = self.twin_db.save_snapshot(
            {"project_id": self.project_id, "rooms": target_rooms},
            analysis={},
            envelope={},
        )
        # 2. Parse
        parser = PluginRegistry.get("parser", parser_name)
        result = parser.parse(file_path)
        # 3. Validate
        if not self._validate_parse_result(result):
            # Rollback
            self._rollback(snapshot_id)
            raise CADOperationError(...)
        # 4. Record
        record = OperationRecord(
            operation_type="parse",
            parser_name=parser_name,
            snapshot_before=snapshot_id,
            snapshot_after=...,
            timestamp=...,
        )
        self._operation_log.append(record)
        return result, record
    
    def undo(self, operation_id: str) -> None:
        """Undo a CAD operation by restoring the pre-operation snapshot."""
        record = self._find_record(operation_id)
        pre_snapshot = self.twin_db.load_snapshot_bundle(record.snapshot_before)
        # Restore project state from pre_snapshot
        ...
    
    def _validate_parse_result(self, result: Any) -> bool:
        """Post-parse validation: no NaN, no negative areas, no missing room_ids."""
        ...
```

**Integration with `twin_db.py`**: The existing `TwinDB` already has `save_snapshot()`, `load_snapshot_bundle()`, and `diff_snapshots()`. The sandbox wraps every parser call with snapshot+validate+rollback.

**Migration plan**:
- Phase 1 (v1.2.0): Create `CADOperationSandbox` class
- Phase 2 (v1.2.0): Wrap `FormatDetector` + `FileValidator` into sandbox
- Phase 3 (v1.3.0): Integrate sandbox into `workflow_service.py` parser calls
- Phase 4 (v1.3.0): Add `undo` API endpoint (`POST /api/projects/:id/undo/:operation_id`)

**Backward compatibility**: Sandbox is additive. Existing parser calls work without sandbox during transition. Sandbox only activates when explicitly enabled.

**Risk**: LOW. Sandbox adds safety, doesn't remove capability.

### Proposal 5: Verified AutoCAD↔Revit Transformation

**Objective**: Loss-minimized, verifiable CAD format transformations.

**Current transformation chain**:

```
DWG/DXF ──parse──→ Room[] ──compute──→ DetectorLayout[] ──export──→ IFC/Revit/DXF
```

**Loss analysis** (from `fireai/core/revit_exporter.py`):

| Property | DXF Input | Room[] | IFC/Revit Output | Loss |
|---|---|---|---|---|
| Room geometry | Full polygon with Z | Polygon (x,y), ceiling_height | IfcSpace with bounds | Z data flattened to ceiling_height |
| Room metadata | Layer, color, handle | room_id, name, type | IfcSpace.Name, Description | Layer/color lost |
| Wall thickness | DXF LINE entities | WALL_THICKNESS_M=0.2 (hardcoded) | IfcWall with thickness | Real thickness → hardcoded 0.2m |
| Door locations | DXF INSERT entities | Not parsed | Not exported | **COMPLETE LOSS** |
| Cable routing | Not in DXF | Computed waypoints | IfcPipeSegment/IfcPipeFitting | Preserved (if computed) |
| Detector positions | Not in DXF | Computed positions | Model Lines on workset | Preserved |

**Critical losses**: Door locations, wall thickness, room Z-geometry. These affect:
- Door entrapment calculations (NFPA 92, stairwell pressurization)
- Cable routing wall clearance (uses hardcoded 0.2m instead of real thickness)
- Multi-floor building model (Z coordinates lost)

**Design**:

```python
# fireai/core/cad_transform_verifier.py

class CADTransformVerifier:
    """Verify bidirectional CAD transformations are loss-minimized.
    
    For every DXF→Room→IFC round-trip:
    1. Compute checksum of input (DXF room properties)
    2. Compute checksum of output (IFC room properties)
    3. Report lost properties
    4. For safety-critical properties (wall thickness, door locations),
       FAIL if lost — these affect NFPA calculations.
    """
    
    CRITICAL_PROPERTIES = [
        "wall_thickness_m",   # Affects cable routing clearance
        "door_locations",     # Affects door entrapment (NFPA 92)
        "ceiling_height_m",   # Affects detector spacing (NFPA 72 §17.6.3)
    ]
    
    def verify_round_trip(
        self,
        input_rooms: List[dict],
        output_rooms: List[dict],
    ) -> TransformVerificationResult:
        """Verify that all safety-critical properties survive the transformation."""
        ...
```

**Migration plan**:
- Phase 1 (v1.1.0): Create `CADTransformVerifier` with critical property list
- Phase 2 (v1.2.0): Parse wall thickness from DXF LINE entities (replace hardcoded 0.2m)
- Phase 3 (v1.2.0): Parse door locations from DXF INSERT entities
- Phase 4 (v1.3.0): Integrate verifier into `revit_exporter.py` pipeline

**Backward compatibility**: `WALL_THICKNESS_M=0.2` remains default when real thickness unavailable. Verifier only flags losses, doesn't block operations initially.

**Risk**: MEDIUM. Parsing wall thickness and doors from DXF requires geometry analysis that could be imprecise. Must validate against known test files.

### Proposal 6: NFPA/IEC Validation as Pipeline Gate

**Objective**: Validation engine as non-bypassable gate in the computation pipeline.

**Current state**: The 5-layer pipeline (L0 guards → L1 constants → L2 compute → L3 validate → L4 audit) already provides this. The `ComplianceEngine` (`fireai/validation/compliance_engine.py`) and `NFPA72ComplianceChecker` (`fireai/core/rules_engine/compliance_bridge.py`) are separate, post-pipeline validators.

**Design**: Merge compliance checking into the pipeline as a mandatory Stage 3.5 (already exists!):

```python
# fireai/core/pipeline.py — Stage 3.5 already calls NFPA72ComplianceChecker

# Enhancement: Make compliance engine pluggable via PluginRegistry
def _stage35_rules_compliance(self, room, result, validated):
    checker_cls = PluginRegistry.get("validation", "nfpa72")
    checker = checker_cls()
    violations = checker.check(result)
    if violations:
        result.compliance_violations = violations
        result.is_safe = False  # NON-BYPASSABLE
```

**Key insight**: Stage 3.5 already exists and is already non-bypassable. The enhancement is making it pluggable so that IEC 60079 validation can be added as a second plugin without modifying pipeline code.

**Migration plan**:
- Phase 1 (v1.1.0): Register `NFPA72ComplianceChecker` as validation plugin
- Phase 2 (v1.2.0): Create `IEC60079ComplianceChecker` as validation plugin
- Phase 3 (v1.2.0): Pipeline discovers and runs all registered validation plugins

**Backward compatibility**: Existing `NFPA72ComplianceChecker` still runs. IEC is additive.

**Risk**: LOW. Plugin registration is additive.

---

## 3. PLUGIN DESIGN

### Plugin Interface Specification

```python
# fireai/core/interfaces.py — All plugin interfaces

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# ── Computation Plugin ──────────────────────────────────────────────────

class ComputationKernel(ABC):
    """Interface for deterministic computation engines.
    
    Safety guarantee: all implementations MUST go through L0-L4 pipeline.
    No implementation may skip validation (L3) or audit (L4).
    """
    
    @abstractmethod
    def compute_detector_spacing(self, room_spec: Any) -> Any:
        """Compute detector spacing for a room. Must pass through all 5 layers."""
        ...
    
    @abstractmethod
    def compute_voltage_drop(self, params: Dict[str, float]) -> Any:
        """Compute voltage drop. Must pass through L0-L4."""
        ...

# ── Parser Plugin ────────────────────────────────────────────────────────

class ParserGateway(ABC):
    """Interface for CAD/BIM file parsers.
    
    Safety guarantee: all implementations MUST validate path security.
    All implementations MUST validate input before processing.
    """
    
    @abstractmethod
    def detect_format(self, file_path: str) -> str:
        """Detect file format (dxf, dwg, ifc, pdf, etc.)."""
        ...
    
    @abstractmethod
    def parse(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse file into room specifications. Must validate path first."""
        ...
    
    @abstractmethod
    def supported_formats(self) -> List[str]:
        """Return list of supported format identifiers."""
        ...

# ── Validation Plugin ────────────────────────────────────────────────────

class ValidationEngine(ABC):
    """Interface for code-compliance validation engines.
    
    Safety guarantee: validation results are NON-BYPASSABLE.
    is_safe=False cannot be overridden by downstream code.
    """
    
    @abstractmethod
    def validate(self, context: Dict[str, Any]) -> List[Any]:
        """Validate computation results against code rules."""
        ...
    
    @abstractmethod
    def rule_count(self) -> int:
        """Return number of active validation rules."""
        ...

# ── Audit Plugin ─────────────────────────────────────────────────────────

class AuditChain(ABC):
    """Interface for tamper-evident audit logging.
    
    Safety guarantee: chain integrity is verifiable.
    append-only, no delete/update allowed.
    """
    
    @abstractmethod
    def append(self, entry: Dict[str, Any]) -> str:
        """Append entry to chain. Returns entry hash."""
        ...
    
    @abstractmethod
    def verify_chain(self) -> bool:
        """Verify entire chain integrity."""
        ...
    
    @abstractmethod
    def export(self) -> str:
        """Export chain for AHJ review."""
        ...

# ── Export Plugin ─────────────────────────────────────────────────────────

class ExportGateway(ABC):
    """Interface for CAD/BIM file exporters.
    
    Safety guarantee: exported files must include code references.
    """
    
    @abstractmethod
    def export(self, project_state: Any, output_path: str) -> str:
        """Export project state to CAD format."""
        ...
    
    @abstractmethod
    def supported_formats(self) -> List[str]:
        """Return list of supported export formats."""
        ...
```

### Plugin Registration Contract

Every plugin module MUST contain a `register()` function:

```python
# Standard registration pattern
def register():
    """Register this module's implementations with PluginRegistry."""
    PluginRegistry.register("category", "name", ImplementationClass)
```

The app startup calls:

```python
# backend/app.py — lifespan startup
def _discover_plugins():
    """Discover and register all plugins."""
    # Core plugins (always available)
    from fireai.core.qomn_kernel import register as qomn_register
    qomn_register()
    
    from fireai.core.pipeline import register as pipeline_register
    pipeline_register()
    
    # Parser plugins (always available)
    from parsers.dxf_parser import register as dxf_register
    dxf_register()
    
    # Optional plugins (conditional)
    if WORKFLOW_ROUTER_AVAILABLE:
        from backend.services.workflow_service import register as workflow_register
        workflow_register()
    
    if MEMORY_ROUTER_AVAILABLE:
        from backend.services.memory_service import register as memory_register
        memory_register()
```

---

## 4. RISK ANALYSIS

### 4.1 Risk Matrix

| Proposal | Impact on Existing Projects | Regression Risk | Rollback Complexity |
|---|---|---|---|
| P1: Dependency Inversion | **NONE** — additive interfaces | LOW — interfaces don't change behavior | Easy — remove interface layer, revert to direct imports |
| P2: Plugin Registry | **NONE** — additive registration | LOW — registry is optional, direct imports still work | Easy — remove registry calls, revert to direct imports |
| P3: Unified Project Schema | **NONE** — `schema_version` defaults to `"1.0.0"` | MEDIUM — database schema change (add column) | Medium — Alembic rollback migration |
| P4: CAD Sandbox | **NONE** — sandbox is opt-in | LOW — sandbox wraps existing parsers | Easy — remove sandbox wrapper |
| P5: Transform Verifier | **NONE** — verifier is additive | MEDIUM — parsing wall thickness/doors changes output | Medium — revert to hardcoded defaults |
| P6: Validation Plugin Gate | **NONE** — existing checker still runs | LOW — pluggable validation is additive | Easy — remove plugin registration |

### 4.2 Backward Compatibility Guarantees

1. **All v1.0.0 projects load unchanged** — no data migration needed for P1, P2, P4, P6
2. **P3 adds `schema_version` column** — default `"1.0.0"` means old projects auto-tagged
3. **P5 changes parser output** — only when wall thickness/door data is available; defaults remain unchanged
4. **No API endpoint changes** — all existing `/api/*` endpoints continue working identically
5. **No configuration changes** — all env vars remain the same

### 4.3 What Could Break

| Scenario | Impact | Mitigation |
|---|---|---|
| Interface method signature changes in future | Plugins need updating | Semantic versioning on interfaces (API_VERSION) |
| PluginRegistry.get() returns None for unregistered plugin | Runtime ImportError | Default fallback to direct import |
| Project with no `schema_version` loaded in v1.1.0 | Treated as v1.0.0 | Default value ensures compatibility |
| Wall thickness parsing returns wrong value | Incorrect cable routing clearance | Verify against known DXF files before enabling |

---

## 5. MIGRATION PLAN

### Phase 1: v1.1.0 (Foundation — ~5 days)

| Step | Task | Effort |
|---|---|---|
| 1.1 | Create `fireai/core/interfaces.py` with ABC definitions | 1 day |
| 1.2 | Make `QOMNKernel` implement `ComputationKernel` | 1 day |
| 1.3 | Create `fireai/core/plugin_registry.py` | 1 day |
| 1.4 | Add `register()` functions to 7 existing modules | 1 day |
| 1.5 | Define `ProjectState` dataclass with `schema_version` | 0.5 day |
| 1.6 | Create `CADTransformVerifier` skeleton | 0.5 day |

**No existing functionality changes. All changes are additive.**

### Phase 2: v1.2.0 (Integration — ~7 days)

| Step | Task | Effort |
|---|---|---|
| 2.1 | Add `schema_version` column to both database tables (Alembic) | 1 day |
| 2.2 | Refactor `project_bridge.py` to use `ProjectState` | 2 days |
| 2.3 | Create `CADOperationSandbox` class | 2 days |
| 2.4 | Parse wall thickness from DXF (replace hardcoded 0.2m) | 1 day |
| 2.5 | Register `IEC60079ComplianceChecker` as validation plugin | 1 day |

**Existing projects auto-tagged with `schema_version="1.0.0"`. No data loss.**

### Phase 3: v1.3.0 (Full Decoupling — ~5 days)

| Step | Task | Effort |
|---|---|---|
| 3.1 | Refactor `backend/routers/qomn.py` to use `ComputationKernel` interface | 2 days |
| 3.2 | Refactor `backend/routers/qomn.py` to use `PluginRegistry` for parsers | 1 day |
| 3.3 | Integrate sandbox into `workflow_service.py` parser calls | 1 day |
| 3.4 | Add `undo` API endpoint | 1 day |

**Direct imports still available as fallback. Interface is primary path.**

### Phase 4: v2.0.0 (Full Plugin Architecture — ~3 days)

| Step | Task | Effort |
|---|---|---|
| 4.1 | Remove all direct `fireai.core.*` imports from `backend/` routers | 2 days |
| 4.2 | Audit trail consolidation (3→1 implementation) | 1 day |

**This phase REMOVES direct import paths. All access through interfaces/registry.**

---

## 6. TEST STRATEGY

### 6.1 Regression Simulation (Before Every Phase)

For each phase, before implementation:

1. **Snapshot baseline**: Run full test suite (5,194 tests) and capture output as baseline
2. **Generate diff report**: After implementation, compare test output to baseline
3. **Backward compatibility test**: Load a v1.0.0 project file and verify it loads unchanged
4. **API contract test**: Verify all `/api/*` endpoints return identical response shapes
5. **Performance regression**: Run CI benchmark suite, compare to baseline

### 6.2 Phase-Specific Test Requirements

**P1: Dependency Inversion Layer**
- Test: `QOMNKernel` still produces identical results through interface
- Test: Router using interface returns same response as router using direct import
- Test: Interface version mismatch raises clear error (not silent failure)

**P2: Plugin Registry**
- Test: Unregistered plugin falls back gracefully (no crash)
- Test: Registered plugin overrides default implementation
- Test: Multiple plugins in same category can be selected by name
- Test: `discover()` finds all `register()` functions

**P3: Unified Project Schema**
- Test: v1.0.0 project (no `schema_version`) loads with default `"1.0.0"`
- Test: `ProjectState` → System A conversion produces identical output
- Test: `ProjectState` → System B conversion produces identical output
- Test: Round-trip conversion (A→UPSS→A) preserves all fields

**P4: CAD Sandbox**
- Test: Successful parse produces `OperationRecord`
- Test: Failed parse triggers rollback to pre-operation snapshot
- Test: `undo()` restores project state to pre-operation snapshot
- Test: Sandbox does not affect parser output for valid files

**P5: Transform Verifier**
- Test: Round-trip DXF→Room→DXF preserves wall thickness
- Test: Loss of critical property (door location) is flagged
- Test: Hardcoded fallback (0.2m wall) produces warning, not error

**P6: Validation Plugin Gate**
- Test: `NFPA72ComplianceChecker` registered as plugin produces same violations as direct call
- Test: Adding IEC validation plugin produces additional violations without blocking NFPA results
- Test: Validation result `is_safe=False` cannot be overridden by downstream code

### 6.3 Smoke Test for Every Commit

```bash
# Pre-commit smoke test (must pass before any phase commit)
python3 -m pytest tests/test_qomn_kernel.py tests/test_pipeline.py \
    tests/test_qomn_integration.py tests/test_nfpa72_engine.py \
    tests/test_voltage_drop.py tests/test_security.py \
    -x --tb=short -q
```

**Exit code 0 required. Any failure blocks the commit.**

### 6.4 Full Regression at Phase Completion

```bash
# Full regression (5,194 tests) at each phase boundary
python3 -m pytest tests/ -q --tb=short --timeout=120
```

**5,194/5,194 must pass. 0 failures. Exit code 0.**

---

## 7. DIFF REPORT TEMPLATE

For each architecture change, generate this report before committing:

```
ARCHITECTURE DIFF REPORT — Phase X.Y
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Date:           2026-06-09
Phase:          X.Y
Proposer:       System Architect
Affected Files: [list of files changed]

┌─ MODULE COUPLING CHANGES ──────────────────────────────────────────────┐
│ REMOVED: backend/routers/qomn.py → fireai/core/qomn_kernel.py (7 imports) │
│ ADDED:   backend/routers/qomn.py → fireai/core/interfaces.py (1 import)   │
│ KEPT:    fireai/core/qomn_kernel.py implements ComputationKernel           │
└──────────────────────────────────────────────────────────────────────────┘

┌─ SINGLETON CHANGES ────────────────────────────────────────────────────┐
│ CHANGED: _default_kernel → injected via PluginRegistry                    │
│ KEPT:    get_db() singleton (no change in this phase)                     │
└──────────────────────────────────────────────────────────────────────────┘

┌─ PROJECT COMPATIBILITY ────────────────────────────────────────────────┐
│ v1.0.0 projects: Load unchanged (schema_version defaults to "1.0.0")    │
│ API endpoints:    No shape changes                                         │
│ Configuration:    No env var changes                                       │
└──────────────────────────────────────────────────────────────────────────┘

┌─ REGRESSION RESULTS ───────────────────────────────────────────────────┐
│ Baseline: 5,194 passed, 1 skipped, 0 failures (before)                   │
│ Current:  5,194 passed, 1 skipped, 0 failures (after)                     │
│ Diff:     IDENTICAL                                                        │
└──────────────────────────────────────────────────────────────────────────┘

SIGN-OFF: [System Architect + PE Review Required for NFPA changes]
```

---

## 8. AUTOCAD ↔ REVIT TRANSFORMATION VERIFICATION STRATEGY

### 8.1 Round-Trip Test Suite

```python
# tests/test_cad_transform_verifier.py

class TestCADTransformVerification:
    """Verify DXF→Room→IFC/Revit round-trips preserve safety-critical data."""
    
    def test_ceiling_height_preserved(self):
        """ceiling_height_m MUST survive round-trip (NFPA 72 §17.6.3)."""
        dxf_rooms = parse_dxf(test_file)
        ifc_rooms = export_ifc(dxf_rooms)
        for room_in, room_out in zip(dxf_rooms, ifc_rooms):
            assert room_out.ceiling_height_m == room_in.ceiling_height_m
    
    def test_wall_thickness_not_hardcoded(self):
        """Wall thickness SHOULD come from DXF, not hardcoded 0.2m."""
        result = verifier.verify_round_trip(input_rooms, output_rooms)
        assert "wall_thickness_m" not in result.lost_properties
    
    def test_door_locations_preserved(self):
        """Door locations MUST survive round-trip (NFPA 92 door entrapment)."""
        result = verifier.verify_round_trip(input_rooms, output_rooms)
        critical_losses = [p for p in result.lost_properties 
                          if p in verifier.CRITICAL_PROPERTIES]
        assert len(critical_losses) == 0
    
    def test_detector_positions_survive_export(self):
        """Computed detector positions MUST appear in IFC output."""
        ...
```

### 8.2 Known Transformation Losses (Current State)

| Property | Status | Phase to Fix |
|---|---|---|
| Wall thickness | **HARDCODED** (0.2m) | Phase 2 (v1.2.0) |
| Door locations | **COMPLETE LOSS** | Phase 2 (v1.2.0) |
| Room Z-coordinates | **FLATTENED** to ceiling_height | Phase 3 (v1.3.0) |
| DXF layer/color | Lost (metadata only) | After v2.0.0 (not safety-critical) |

---

## 9. IMPLEMENTATION PRIORITY

| Proposal | Priority | Phase | Effort | Blocks Other Proposals? |
|---|---|---|---|---|
| P1: Dependency Inversion | **Critical** | v1.1.0 | 5 days | Yes — P2, P3, P6 depend on interfaces |
| P2: Plugin Registry | **Critical** | v1.1.0 | 5 days | Yes — P4, P5, P6 depend on registry |
| P3: Unified Project Schema | High | v1.2.0 | 7 days | No — but enables undo |
| P4: CAD Sandbox | High | v1.2.0 | 7 days | No — but depends on P2 |
| P5: Transform Verifier | Medium | v1.2.0 | 7 days | No — but depends on P1 |
| P6: Validation Plugin Gate | Medium | v1.1.0 | 5 days | No — depends on P2 |

**Recommended implementation order**: P1 → P2 → P6 → P3 → P4 → P5

---

## 10. PRINCIPLE ALIGNMENT CHECKLIST

| # | Principle | Current Status | After V2.0.0 |
|---|---|---|---|
| 1 | Modules fully decoupled and versioned | **VIOLATED** — 17 direct cross-module imports | **COMPLIANT** — all access through interfaces |
| 2 | No direct coupling between AI logic and core kernel | **PARTIALLY COMPLIANT** — router bypasses PluginAPI | **COMPLIANT** — all access through ComputationKernel interface |
| 3 | Plugin-based architecture for all features | **VIOLATED** — all features hardcoded | **COMPLIANT** — PluginRegistry with register() pattern |
| 4 | CAD operations reversible and sandboxed | **VIOLATED** — no undo, no rollback | **COMPLIANT** — CADOperationSandbox with snapshot+undo |
| 5 | Strict schema for project state representation | **VIOLATED** — two different project schemas | **COMPLIANT** — ProjectState with schema_version |
| 6 | Electrical outputs validated against IEC/NFPA | **COMPLIANT** — 5-layer pipeline + ComplianceEngine | **COMPLIANT** — enhanced with pluggable validation |
| 7 | AutoCAD↔Revit loss-minimized and verifiable | **VIOLATED** — hardcoded wall thickness, lost doors | **COMPLIANT** — CADTransformVerifier + real thickness parsing |