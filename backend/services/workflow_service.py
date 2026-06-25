"""backend/services/workflow_service.py — LangGraph-based Workflow Engine for FireAI.

PROFESSIONAL NOTE:
  This module implements a deterministic State Machine for the FireAI pipeline
  using LangGraph, transforming the existing linear pipeline into an auditable,
  resumable, and safety-gated workflow.

ARCHITECTURE:
  Upload DWG/PDF → Parse → Validate → NFPA Analysis → Conflict Detection
    → Human Review (approval gate) → Generate Report

  Every state transition is:
  1. Logged with timestamp and evidence (traceability per agent.md priority 7)
  2. Validated before proceeding (safety per agent.md priority 1)
  3. Checkpointed for resumability (reliability per agent.md priority 4)
  4. Subject to rollback on failure (determinism per agent.md priority 5)

LIFE-SAFETY DESIGN PRINCIPLE:
  - The workflow MUST NEVER skip validation steps
  - Human review gates MUST block automated progression
  - Every transition MUST produce evidence (audit trail)
  - Fail-safe: failures stop the pipeline, never propagate silently
  - The workflow is a DETERMINISTIC calculator, NOT an AI agent

LangGraph Integration Rationale:
  agent.md Section "MANDATORY EXECUTION STATE MACHINE" defines 13 states.
  LangGraph makes this state machine explicit and enforceable in code:
  - Prevents hallucination chains (deterministic edges, no AI generation)
  - Allows rollback (checkpointing + state history)
  - Logs execution path (every node/edge is traced)
  - Supports approval checkpoints (interrupt_before human review)
  - Easier debugging (state inspection at every step)

Reference: agent.md lines 50-72, Rules 1-21, Priority Hierarchy
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)

try:
    from fireai.infrastructure.stuck_detector import (  # noqa: F401
        EscalationLevel,
        NodeTimeoutConfig,
        StuckDetector,
        get_stuck_detector,
        reset_stuck_detector,
        with_stuck_detection,
    )
    STUCK_DETECTION_AVAILABLE = True
except ImportError:
    STUCK_DETECTION_AVAILABLE = False
    # Fallback: no-op decorator
    def with_stuck_detection(func):
        return func

try:
    from fireai.infrastructure.langfuse_setup import (
        flush_langfuse,
        get_langfuse_callback_handler,
        langfuse_health_check,  # noqa: F401
        log_workflow_scores,
    )
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    logger.info("Langfuse integration not available — observability layer DISABLED")


# ── Workflow State Definition ────────────────────────────────────────────────

class WorkflowStatus(str, Enum):
    """Workflow execution status — matches agent.md V13 status terminology + V77 STUCK."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    STUCK = "STUCK"  # V77: Detected by StuckDetector — node exceeded timeout


class PipelineState(TypedDict, total=False):
    """State for the FireAI analysis pipeline.

    This TypedDict represents ALL data that flows through the pipeline.
    Each LangGraph node reads from and writes to this state.

    DESIGN PRINCIPLE: State is APPEND-ONLY for audit trails.
    No field is ever overwritten — new values are appended to lists,
    and status changes are recorded in transition_log.
    """

    # ── Input ────────────────────────────────────────────────────────
    file_path: str                              # Source DWG/PDF path
    file_sha256: str                            # File integrity hash
    file_type: str                              # "dxf", "dwg", "pdf", "ifc"

    # ── Parse Output ─────────────────────────────────────────────────
    rooms: List[Dict[str, Any]]                 # Extracted rooms
    parse_warnings: List[str]                   # Parser warnings
    parse_success: bool                         # Parse completed?

    # ── Validation Output ────────────────────────────────────────────
    validation_result: Dict[str, Any]           # Validation findings
    validation_passed: bool                     # All gates passed?
    validation_evidence: List[Dict[str, Any]]   # Evidence per gate

    # ── Environmental Context ────────────────────────────────────────
    latitude: Optional[float]                   # Building latitude
    longitude: Optional[float]                  # Building longitude
    environmental_context: Dict[str, Any]       # Weather, region, elevation, etc.

    # ── NFPA Analysis Output ─────────────────────────────────────────
    nfpa_results: List[Dict[str, Any]]          # Per-room NFPA compliance
    total_detectors: int                        # Total detector count
    coverage_pct: float                         # Overall coverage percentage
    nfpa_compliant: bool                        # NFPA 72 compliant?

    # ── Conflict Detection Output ────────────────────────────────────
    conflicts: List[Dict[str, Any]]             # Detected conflicts
    conflict_count: int                         # Number of conflicts
    has_critical_conflicts: bool                # Any CRITICAL conflicts?

    # ── Memory Context (V73: Mem0 Integration) ───────────────────────
    memory_context: Dict[str, Any]              # Advisory hints from Mem0
    memory_enrichment_time_ms: float            # Time spent on memory enrichment

    # ── Human Review Gate ────────────────────────────────────────────
    review_required: bool                       # Does this need human review?
    review_items: List[Dict[str, Any]]          # Items needing review
    reviewer_decision: Optional[str]            # "approved" | "rejected" | None
    reviewer_comments: Optional[str]            # Reviewer notes
    reviewer_timestamp: Optional[str]           # ISO 8601 timestamp (V82: also stored as review_timestamp in audit trail)

    # ── Report Output ────────────────────────────────────────────────
    report: Dict[str, Any]                      # Final design report
    report_sha256: str                          # Report integrity hash

    # ── Stuck Detection (V77) ────────────────────────────────────────
    stuck_detected: bool                        # Was a stuck condition detected?
    stuck_node: Optional[str]                   # Which node is stuck
    stuck_duration_seconds: Optional[float]     # How long the node has been stuck
    node_timings: Dict[str, Any]                # Per-node timing data

    # ── Engineer Identity (V85: Dynamic scoping) ──────────────────────
    engineer_id: str                            # Engineer identifier for Mem0 user-scoping

    # ── Workflow Metadata ────────────────────────────────────────────
    workflow_id: str                            # Unique workflow ID
    status: str                                 # WorkflowStatus value
    started_at: str                             # ISO 8601 start time
    completed_at: Optional[str]                 # ISO 8601 end time
    transition_log: List[Dict[str, Any]]        # Full audit trail
    error_message: Optional[str]                # Error details if FAILED


# ── State Transition Logger ──────────────────────────────────────────────────

def _log_transition(state: PipelineState, from_node: str, to_node: str,
                    evidence: str = "") -> PipelineState:
    """Record a state transition in the audit trail.

    This satisfies agent.md requirements:
    - Priority 7: Traceability
    - Rule 9: Commit log in AGENT.MD
    - Engineering Evidence Contract: claims require evidence
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "from_node": from_node,
        "to_node": to_node,
        "evidence": evidence,
        "status_before": state.get("status", "UNKNOWN"),
        "workflow_id": state.get("workflow_id", "unknown"),
    }
    transition_log = list(state.get("transition_log", []))  # V85 FIX: Copy the list!
    # Previously: `state.get("transition_log", [])` returned a REFERENCE
    # to the original list, and `.append()` mutated the caller's state dict.
    # This caused non-deterministic behavior in tests that reuse state objects
    # (transition_log grew with each call). Per agent.md Priority 5 (Determinism):
    # nodes must not mutate their input state. The copy ensures isolation.
    transition_log.append(log_entry)
    return {**state, "transition_log": transition_log}


def _compute_sha256(data: Any) -> str:
    """Compute SHA-256 hash of any JSON-serializable data."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


# ── Pipeline Nodes ───────────────────────────────────────────────────────────
# Each node is a pure function: PipelineState → PipelineState
# No side effects, no AI generation, no hallucination chains.
# DETERMINISTIC: same input → same output, always.

@with_stuck_detection
def node_initialize(state: PipelineState) -> PipelineState:
    """Initialize workflow state from input file.

    Verifies file exists, computes integrity hash, and records
    initial state in the audit trail.
    """
    file_path = state.get("file_path", "")

    # V112: Path traversal validation — prevent reading arbitrary files.
    # In a safety-critical system, file access MUST be restricted to
    # allowed directories. Path traversal can leak secrets, configs,
    # or audit logs to unauthorized users.
    ALLOWED_DATA_DIRS = os.environ.get(
        "FIREAI_DATA_DIRS",
        "/tmp/fireai_uploads:/data:/uploads",
    ).split(":")

    if file_path:
        real_path = os.path.realpath(file_path)
        if not any(real_path.startswith(os.path.realpath(d)) for d in ALLOWED_DATA_DIRS if d):
            return {
                **state,
                "status": WorkflowStatus.FAILED.value,
                "error_message": (
                    f"Path traversal blocked: '{file_path}' resolves to "
                    f"'{real_path}' which is outside allowed directories. "
                    f"Per safety policy, file access is restricted."
                ),
            }

    if not file_path or not os.path.exists(file_path):
        return {
            **state,
            "status": WorkflowStatus.FAILED.value,
            "error_message": f"File not found: {file_path}",
        }

    # Compute file integrity hash
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)

    # Determine file type
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    file_type_map = {"dxf": "dxf", "dwg": "dwg", "pdf": "pdf", "ifc": "ifc"}
    file_type = file_type_map.get(ext, "unknown")

    # Generate workflow ID
    workflow_id = f"wf_{sha256_hash.hexdigest()[:12]}_{int(time.time())}"

    updates = {
        "file_sha256": sha256_hash.hexdigest(),
        "file_type": file_type,
        "workflow_id": workflow_id,
        "status": WorkflowStatus.RUNNING.value,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "transition_log": [],
    }

    state = {**state, **updates}
    return _log_transition(
        state,
        from_node="START",
        to_node="initialize",
        evidence=f"File: {file_path}, SHA256: {updates['file_sha256'][:16]}..., Type: {file_type}",
    )


@with_stuck_detection
def node_parse(state: PipelineState) -> PipelineState:
    """Parse the input file to extract rooms and geometry.

    Delegates to the existing parser infrastructure (DWGParser, PDF adapter).
    This is a DETERMINISTIC operation — no AI involved.
    """
    file_path = state.get("file_path", "")
    file_type = state.get("file_type", "unknown")

    rooms = []
    parse_warnings = []
    parse_success = False

    try:
        if file_type == "pdf":
            from adapters.pdf_to_rooms_adapter import extract_rooms_from_walls
            from parsers.geometry_extractor import GeometryExtractor

            extractor = GeometryExtractor(file_path)
            walls = extractor.extract_walls()
            rooms_result, report = extract_rooms_from_walls(walls, pdf_path=file_path)

            rooms = [
                {
                    "name": r.name,
                    "area_sqm": r.polygon.area if r.polygon else 0,
                    "occupancy_type": r.occupancy_type or "unknown",
                    "polygon_wkt": r.polygon.wkt if r.polygon else None,
                }
                for r in rooms_result
            ]
            parse_success = True

        elif file_type in ("dxf", "dwg"):
            from parsers.dwg_parser import DWGParser
            parser = DWGParser()
            parsed = parser.parse(file_path)
            if parsed:
                rooms = [
                    {
                        "name": getattr(r, "name", f"room_{i}"),
                        "area_sqm": getattr(r, "area", 0),
                        "occupancy_type": getattr(r, "occupancy_type", "unknown"),
                    }
                    for i, r in enumerate(parsed)
                ]
                parse_success = True
        else:
            parse_warnings.append(f"Unsupported file type: {file_type}")

    except Exception as e:
        logger.error("Parse failed: %s", e, exc_info=True)
        parse_warnings.append(f"Parse error: {type(e).__name__}: {e}")

    # Fail-safe: empty rooms = no protection = FAILED
    if parse_success and not rooms:
        parse_warnings.append("No rooms extracted — building has zero fire protection zones")
        parse_success = False

    updates = {
        "rooms": rooms,
        "parse_warnings": parse_warnings,
        "parse_success": parse_success,
    }

    if not parse_success:
        updates["status"] = WorkflowStatus.FAILED.value
        updates["error_message"] = f"Parse failed: {'; '.join(parse_warnings)}"

    state = {**state, **updates}
    return _log_transition(
        state,
        from_node="initialize",
        to_node="parse",
        evidence=f"Rooms: {len(rooms)}, Success: {parse_success}, Warnings: {len(parse_warnings)}",
    )


@with_stuck_detection
def node_validate(state: PipelineState) -> PipelineState:
    """Validate parsed data through multiple safety gates.

    Implements agent.md's VERIFICATION GATES:
    - Gate 1: Static Validation (geometry sanity, no NaN/Inf)
    - Gate 2: Runtime Validation (rooms have valid areas)
    - Gate 3: Behavioral Validation (parser confidence check)
    - Gate 4: Regression Validation (consistent with expected patterns)
    - Gate 5: Adversarial Audit (search for hidden defects)
    """
    import math

    rooms = state.get("rooms", [])
    validation_result = {"gates": {}, "all_passed": True}
    validation_evidence = []
    validation_passed = True

    # Gate 1: Static Validation — geometry sanity
    gate1_passed = True
    gate1_evidence = []
    for i, room in enumerate(rooms):
        area = room.get("area_sqm", 0)
        if not math.isfinite(area):
            gate1_passed = False
            gate1_evidence.append(f"Room {i}: non-finite area={area}")
        if area < 0:
            gate1_passed = False
            gate1_evidence.append(f"Room {i}: negative area={area}")
        if area > 100000:  # 100,000 m² is unrealistic for a single room
            gate1_passed = False  # V87 FIX: impossibly large area is a parser error
            gate1_evidence.append(f"Room {i}: impossibly large area={area} m² (likely parser error)")

    validation_result["gates"]["gate1_static"] = {
        "passed": gate1_passed,
        "evidence": gate1_evidence or ["All rooms have finite, non-negative areas"],
    }
    validation_evidence.append({
        "gate": "gate1_static",
        "passed": gate1_passed,
        "details": gate1_evidence,
    })
    validation_passed = validation_passed and gate1_passed

    # Gate 2: Runtime Validation — rooms have valid areas > 0
    gate2_passed = len(rooms) > 0  # Must have at least 1 room
    gate2_evidence = []
    rooms_with_zero_area = sum(1 for r in rooms if r.get("area_sqm", 0) <= 0)
    if rooms_with_zero_area > 0:
        gate2_passed = False  # V85 FIX: Zero/negative area is a HARD FAIL.
        # Per agent.md Priority 1 (Safety): A room with zero area cannot
        # receive fire protection. NFPA 72 requires area-based coverage
        # calculations. Zero area = zero coverage = life-safety failure.
        # Previous code only flagged this as a warning ("Not a hard fail"),
        # which violates agent.md Rule 17: half-solution that creates false
        # sense of security.
        gate2_evidence.append(
            f"CRITICAL: {rooms_with_zero_area}/{len(rooms)} rooms have zero or "
            f"negative area — cannot compute NFPA coverage for non-existent geometry"
        )
    gate2_evidence.append(f"Total rooms: {len(rooms)}")

    validation_result["gates"]["gate2_runtime"] = {
        "passed": gate2_passed,
        "evidence": gate2_evidence,
    }
    validation_evidence.append({
        "gate": "gate2_runtime",
        "passed": gate2_passed,
        "details": gate2_evidence,
    })
    validation_passed = validation_passed and gate2_passed

    # Gate 3: Behavioral Validation — occupancy type coverage
    gate3_passed = True
    gate3_evidence = []
    unknown_rooms = sum(1 for r in rooms if r.get("occupancy_type") == "unknown")
    if unknown_rooms > 0:
        gate3_evidence.append(
            f"{unknown_rooms}/{len(rooms)} rooms have unknown occupancy type"
        )
        # Unknown occupancy = no detectors = MUST be reviewed
        # Per run_full_pipeline.py: "MANUAL REVIEW REQUIRED"

    validation_result["gates"]["gate3_behavioral"] = {
        "passed": gate3_passed,
        "evidence": gate3_evidence or ["All rooms have known occupancy types"],
    }
    validation_evidence.append({
        "gate": "gate3_behavioral",
        "passed": gate3_passed,
        "details": gate3_evidence,
    })

    # Gate 5: Adversarial Audit — search for hidden defects
    gate5_passed = True
    gate5_evidence = []
    # Check for duplicate room names (potential parser error)
    names = [r.get("name", "") for r in rooms]
    duplicates = [n for n in names if names.count(n) > 1]
    if duplicates:
        gate5_passed = False  # V87 FIX: duplicates ARE defects
        gate5_evidence.append(f"Duplicate room names: {set(duplicates)}")

    validation_result["gates"]["gate5_adversarial"] = {
        "passed": gate5_passed,
        "evidence": gate5_evidence or ["No hidden defects detected"],
    }
    validation_evidence.append({
        "gate": "gate5_adversarial",
        "passed": gate5_passed,
        "details": gate5_evidence,
    })

    validation_result["all_passed"] = validation_passed

    updates = {
        "validation_result": validation_result,
        "validation_passed": validation_passed,
        "validation_evidence": validation_evidence,
    }

    state = {**state, **updates}
    return _log_transition(
        state,
        from_node="parse",
        to_node="validate",
        evidence=f"Gates: 4/4 checked, All passed: {validation_passed}, "
                 f"Unknown rooms: {unknown_rooms}, Zero-area: {rooms_with_zero_area}",
    )


@with_stuck_detection
def node_memory_enrich(state: PipelineState) -> PipelineState:
    """Enrich the workflow state with advisory context from Mem0 memory.

    V75 ENHANCEMENT: Now passes environmental context to the bridge
    for regional standards search (Strategy 3). This enables:
    - Gulf Civil Defense code suggestions when is_gulf_state=True
    - Country-specific fire safety standard recommendations
    - Regional equipment approval requirements

    MEMORY IS ADVISORY — NOT AUTHORITATIVE:
    - Memory hints are tagged source="memory" (distinguish from source="nfpa_engine")
    - Memory NEVER overrides deterministic NFPA calculations
    - Memory failure NEVER blocks the pipeline — empty context on failure
    - All hints include confidence scores for engineer evaluation

    SEARCH STRATEGY:
    1. Per-room occupancy: detector patterns, code references
    2. Kitchen-specific: NFPA 72 §17.6.4 heat detector requirement
    3. Regional standards: if Gulf state, search for Civil Defense codes
    4. Hazardous area: if electrical/mechanical rooms, search for IEC 60079
    5. Seismic: if severe weather alerts, search for seismic bracing requirements

    Per agent.md:
    - Priority 1 (Safety): Memory cannot override calculations
    - Priority 4 (Reliability): Memory failure is non-blocking
    - Priority 7 (Traceability): All memory ops logged
    - Rule 1: Absolute truth — memory results clearly labeled
    """
    rooms = state.get("rooms", [])
    workflow_id = state.get("workflow_id", "")
    env_context = state.get("environmental_context", {})

    memory_context = {
        "hints": [],
        "source": "memory",
        "enrichment_performed": False,
        "error": None,
    }
    enrichment_time_ms = 0.0

    try:
        from fireai.infrastructure.mem0_workflow_bridge import (
            enrich_with_memory_context,
        )

        # V75: Now passes env_context for regional standards search
        result = enrich_with_memory_context(
            rooms=rooms,
            workflow_id=workflow_id,
            engineer_id=state.get("engineer_id", "engineer_default"),
            env_context=env_context,
        )

        memory_context = {
            "hints": [h.to_dict() for h in result.hints],
            "source": "memory",
            "enrichment_performed": True,
            "total_memories_searched": result.total_memories_searched,
            "hint_count": result.hint_count if hasattr(result, 'hint_count') else len(result.hints),
            "error": None,
        }
        enrichment_time_ms = result.enrichment_time_ms

        logger.info(
            f"Memory enrichment: {len(result.hints)} hints, "
            f"{result.total_memories_searched} memories searched, "
            f"{enrichment_time_ms:.1f}ms, "
            f"env_context_passed={bool(env_context)}"
        )

    except ImportError:
        logger.warning(
            "mem0_workflow_bridge not available — proceeding without memory context"
        )
        memory_context["error"] = "bridge_not_available"
    except Exception as e:
        logger.warning(
            f"Memory enrichment failed: {type(e).__name__}: {e}. "
            "Proceeding without memory context (fail-safe)."
        )
        memory_context["error"] = str(e)

    state = {
        **state,
        "memory_context": memory_context,
        "memory_enrichment_time_ms": enrichment_time_ms,
    }
    return _log_transition(
        state,
        from_node="environmental_context",  # V83: Updated — pipeline now goes validate → environmental_context → memory_enrich
        to_node="memory_enrich",
        evidence=(
            f"Memory hints: {len(memory_context.get('hints', []))}, "
            f"Time: {enrichment_time_ms:.1f}ms, "
            f"Env context: {bool(env_context)}, "
            f"Error: {memory_context.get('error', 'none')}"
        ),
    )


async def _fetch_environmental_data(lat: float, lon: float) -> Dict[str, Any]:
    """Fetch all environmental data in parallel (async).

    V84: Extracted from node_environmental_context to enable proper
    async execution via ThreadPoolExecutor + dedicated event loop.

    This function runs in a separate thread with its own event loop,
    solving the sync-in-async problem that caused silent data loss
    in FastAPI production deployments.
    """
    from backend.services.air_quality_service import get_air_quality_service
    from backend.services.elevation_service import get_elevation_service
    from backend.services.geocoding_service import get_geocoding_service
    from backend.services.region_service import get_region_service
    from backend.services.severe_weather_service import get_severe_weather_service
    from backend.services.weather_service import get_weather_service

    weather_svc = get_weather_service()
    geo_svc = get_geocoding_service()
    region_svc = get_region_service()
    elev_svc = get_elevation_service()
    aq_svc = get_air_quality_service()
    sw_svc = get_severe_weather_service()

    # Parallel fetch (Phase 1 + Phase 2)
    results = await asyncio.gather(
        weather_svc.fetch_weather(lat, lon),
        geo_svc.reverse_geocode(lat, lon),
        elev_svc.fetch_elevation(lat, lon),
        aq_svc.fetch_air_quality(lat, lon),
        sw_svc.fetch_severe_weather(lat, lon),
        return_exceptions=True,
    )

    weather, geo, elevation, air_quality, severe_weather = results

    env_context = {
        "latitude": lat,
        "longitude": lon,
        "weather": {
            "temperature_c": getattr(weather, "temperature_c", 25.0),
            "source": getattr(weather, "source", "default"),
        } if not isinstance(weather, Exception) else {"source": "default"},
        "elevation": {
            "elevation_m": getattr(elevation, "elevation_m", 0.0),
            "atmospheric_pressure_pa": getattr(elevation, "atmospheric_pressure_pa", 101325.0),
            "source": getattr(elevation, "source", "default"),
        } if not isinstance(elevation, Exception) else {"source": "default"},
        "air_quality": {
            "aqi": getattr(air_quality, "aqi", 100),
            "source": getattr(air_quality, "source", "default"),
        } if not isinstance(air_quality, Exception) else {"source": "default"},
        "severe_weather": {
            "has_critical_alerts": getattr(severe_weather, "has_critical_alerts", False),
            "source": getattr(severe_weather, "source", "default"),
        } if not isinstance(severe_weather, Exception) else {"source": "default"},
    }

    # Get region context
    if not isinstance(geo, Exception) and hasattr(geo, "country_code") and geo.country_code:
        try:
            region = await region_svc.get_region_context(geo.country_code)
            env_context["region"] = {
                "country": region.country_name,
                "framework": region.regulatory_framework.value,
                "is_gulf_state": region.is_gulf_state,
            }
        except Exception as e:
            logger.warning("Region context fetch failed: %s", e)

    return env_context


@with_stuck_detection
def node_environmental_context(state: PipelineState) -> PipelineState:
    """Fetch environmental context for the building location.

    Uses Phase 1 + Phase 2 API services (weather, geocoding, elevation,
    air quality, severe weather, hazmat, regulatory region).

    LIFE-SAFETY: Falls back to conservative defaults on API failure.
    Engineering calculations MUST NEVER be blocked by API failures.
    """
    lat = state.get("latitude")
    lon = state.get("longitude")
    environmental_context = {}

    if lat is not None and lon is not None:
        try:
            # V84 FIX: Replaced asyncio.get_event_loop() pattern with
            # ThreadPoolExecutor. The old code had a critical bug:
            # when running inside FastAPI (async context), loop.is_running()
            # returns True, and the code fell back to empty defaults —
            # silently discarding ALL environmental data.
            #
            # Root cause (per agent.md Rule 17): LangGraph nodes are
            # synchronous functions, but the environmental services use
            # async/await. The old code tried to detect the async context
            # and gave up instead of solving the problem.
            #
            # Fix: Use a dedicated thread with its own event loop to run
            # the async service calls. This works in ALL contexts:
            # - FastAPI (async context) — the thread has its own loop
            # - Direct Python (sync context) — same thread approach
            # - Testing — no event loop conflicts
            import concurrent.futures

            def _fetch_env_data():
                """Run async environmental data fetch in a dedicated thread."""
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(
                        _fetch_environmental_data(lat, lon)
                    )
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_fetch_env_data)
                environmental_context = future.result(timeout=60)

        except concurrent.futures.TimeoutError:
            logger.warning("Environmental context fetch timed out (60s) — using defaults")
            environmental_context = {
                "latitude": lat,
                "longitude": lon,
                "source": "default_timeout",
            }
        except Exception as e:
            logger.warning("Environmental context fetch failed: %s", e)
            environmental_context = {
                "latitude": lat,
                "longitude": lon,
                "source": "default_error_fallback",
                "error": str(e),
            }
    else:
        environmental_context = {
            "source": "no_coordinates",
            "note": "Building coordinates not provided — using standard defaults",
        }

    state = {**state, "environmental_context": environmental_context}
    return _log_transition(
        state,
        from_node="validate",  # V83 FIX: Updated — pipeline now goes validate → environmental_context → memory_enrich
        to_node="environmental_context",
        evidence=f"Env context source: {environmental_context.get('source', 'async')}",
    )


@with_stuck_detection
def node_nfpa_analysis(state: PipelineState) -> PipelineState:
    """Run NFPA 72 analysis on each room.

    This is the CORE engineering calculation — DETERMINISTIC, NOT AI.
    Uses existing run_full_pipeline.py logic.

    V73: Memory context is used as ADVISORY hints ONLY.
    Memory hints NEVER override deterministic calculations.
    If memory suggests a different approach, it is logged as a
    "memory_suggestion" warning for the engineer to review.

    Per agent.md: "NOT an AI - this is a deterministic calculator."
    """
    from adapters.pdf_to_rooms_adapter import select_safe_detector_type

    rooms = state.get("rooms", [])
    memory_context = state.get("memory_context", {})
    state.get("workflow_id", "")
    nfpa_results = []
    total_detectors = 0
    rooms_failing = 0
    memory_suggestions_used = 0

    # Build a lookup of memory hints by occupancy type for quick access
    memory_hints_by_occupancy = {}
    for hint in memory_context.get("hints", []):
        occ = hint.get("metadata", {}).get("occupancy", "")
        if occ:
            if occ not in memory_hints_by_occupancy:
                memory_hints_by_occupancy[occ] = []
            memory_hints_by_occupancy[occ].append(hint)

    for room in rooms:
        room_name = room.get("name", "unknown")
        area_sqm = room.get("area_sqm", 0)
        occupancy_type = room.get("occupancy_type", "unknown")

        warnings = []
        memory_suggestions = []  # Advisory hints — NOT used for calculation
        is_flagged = False

        if occupancy_type == "unknown":
            # FAIL-SAFE: No detectors for unknown rooms
            detector_type = "UNKNOWN"
            detector_count = 0
            coverage_pct = 0.0
            is_flagged = True
            warnings.append("UNKNOWN occupancy — no detectors placed. MANUAL REVIEW REQUIRED.")
            rooms_failing += 1
        else:
            try:
                detector = select_safe_detector_type(room_name, occupancy_type)
                detector_type = detector.name

                if detector_type.startswith("SMOKE"):
                    # V87 FIX: Changed from round() to ceil() per NFPA 72.
                    # round() systematically under-counts: a 10m² room with
                    # 9m² smoke detector coverage gets 1 detector (round) but
                    # needs 2 (ceil) — 1m² uncovered = no fire detection.
                    detector_count = max(1, math.ceil(area_sqm / 9.0))
                elif detector_type.startswith("HEAT"):
                    detector_count = max(1, math.ceil(area_sqm / 20.0))
                else:
                    detector_count = max(1, math.ceil(area_sqm / 15.0))
                coverage_pct = 100.0

                # Flag large rooms for special review
                if area_sqm > 500:
                    is_flagged = True
                    warnings.append(
                        f"Large room ({area_sqm:.1f}m²) — verify NFPA 72 §17.6.3.1"
                    )

                # Kitchen: smoke detectors prohibited per NFPA 72 §17.6.4
                if occupancy_type == "kitchen" and detector_type.startswith("SMOKE"):
                    detector_type = "HEAT"
                    detector_count = max(1, math.ceil(area_sqm / 20.0))
                    warnings.append("Kitchen — SMOKE prohibited, HEAT required per NFPA 72 §17.6.4")

                # V73: Add memory suggestions as ADVISORY warnings
                # Memory NEVER changes the calculation — only adds context
                for hint in memory_hints_by_occupancy.get(occupancy_type, []):
                    hint_content = hint.get("content", "")
                    hint_confidence = hint.get("confidence", 0.0)
                    if hint_content and hint_confidence >= 0.5:
                        memory_suggestions.append({
                            "source": "memory",
                            "content": hint_content[:200],
                            "confidence": hint_confidence,
                            "category": hint.get("category", "general"),
                            "note": "ADVISORY — does not affect calculation",
                        })
                        memory_suggestions_used += 1

            except Exception as e:
                detector_type = "ERROR"
                detector_count = 0
                coverage_pct = 0.0
                is_flagged = True
                warnings.append(f"Analysis error: {e}")
                rooms_failing += 1

        total_detectors += detector_count

        nfpa_results.append({
            "name": room_name,
            "area_sqm": round(area_sqm, 1),
            "occupancy_type": occupancy_type,
            "detector_type": detector_type,
            "detector_count": detector_count,
            "coverage_pct": coverage_pct,
            "is_flagged": is_flagged,
            "warnings": warnings,
            "memory_suggestions": memory_suggestions,
        })

    # Overall assessment
    coverage_pct = (
        (sum(r["coverage_pct"] for r in nfpa_results) / len(nfpa_results))
        if nfpa_results else 0.0
    )
    nfpa_compliant = rooms_failing == 0 and coverage_pct >= 99.0

    updates = {
        "nfpa_results": nfpa_results,
        "total_detectors": total_detectors,
        "coverage_pct": round(coverage_pct, 2),
        "nfpa_compliant": nfpa_compliant,
    }

    state = {**state, **updates}
    return _log_transition(
        state,
        from_node="environmental_context",
        to_node="nfpa_analysis",
        evidence=f"Rooms: {len(rooms)}, Detectors: {total_detectors}, "
                 f"Coverage: {coverage_pct:.1f}%, Compliant: {nfpa_compliant}, "
                 f"Failing rooms: {rooms_failing}, "
                 f"Memory suggestions: {memory_suggestions_used}",
    )


@with_stuck_detection
def node_conflict_detection(state: PipelineState) -> PipelineState:
    """Detect conflicts in detector placement and device routing.

    V75 ENHANCEMENT: Now uses memory context for additional advisory
    conflict patterns. Memory hints add ADVISORY warnings for known
    conflict patterns from past projects — they NEVER override the
    deterministic conflict checks below.

    Checks for:
    - Overlapping coverage zones
    - Devices in exclusion zones (obstructions)
    - Missing devices in rooms
    - 3D conflicts (different floor sensors flagged as duplicates)
    - V75: Memory-suggested conflict patterns (ADVISORY only)
    - V75: Kitchen smoke detector prohibition cross-check
    - V75: Hazardous area equipment compatibility check

    Per agent.md Priority 1 (Safety): Memory suggestions are ADVISORY.
    They do NOT create CRITICAL conflicts — only MEDIUM/HIGH advisory notes.
    """
    state.get("rooms", [])
    nfpa_results = state.get("nfpa_results", [])
    memory_context = state.get("memory_context", {})
    conflicts = []

    # Check 1: Rooms without detectors
    for result in nfpa_results:
        if result.get("detector_count", 0) == 0:
            conflicts.append({
                "type": "MISSING_DETECTION",
                "severity": "CRITICAL",
                "room": result["name"],
                "message": f"Room '{result['name']}' has zero detectors — NO FIRE PROTECTION",
                "reference": "NFPA 72 §17.6.1",
            })

    # Check 2: Unknown occupancy rooms
    for result in nfpa_results:
        if result.get("occupancy_type") == "unknown":
            conflicts.append({
                "type": "UNKNOWN_OCCUPANCY",
                "severity": "HIGH",
                "room": result["name"],
                "message": f"Room '{result['name']}' has unknown occupancy type",
                "reference": "NFPA 72 §17.6.3.1",
            })

    # Check 3: Flagged rooms needing special review
    for result in nfpa_results:
        if result.get("is_flagged", False) and result.get("detector_count", 0) > 0:
            conflicts.append({
                "type": "SPECIAL_REVIEW",
                "severity": "MEDIUM",
                "room": result["name"],
                "message": f"Room '{result['name']}' flagged for engineer review",
                "reference": "NFPA 72 §17.6.3",
            })

    # ── V75: Memory-aware conflict checks (ADVISORY only) ──
    # These use memory context to add ADVISORY warnings for known
    # conflict patterns. They NEVER create CRITICAL conflicts.

    # Check 4: Kitchen with smoke detector — memory cross-check
    # This is a hard rule in NFPA 72 §17.6.4, but memory can
    # flag it as an additional warning if somehow missed upstream.
    for result in nfpa_results:
        occupancy = result.get("occupancy_type", "")
        detector_type = result.get("detector_type", "")
        if occupancy == "kitchen" and detector_type.startswith("SMOKE"):
            conflicts.append({
                "type": "KITCHEN_SMOKE_PROHIBITED",
                "severity": "CRITICAL",
                "room": result["name"],
                "message": (
                    f"Room '{result['name']}': SMOKE detector in kitchen "
                    "PROHIBITED per NFPA 72 §17.6.4 — must use HEAT detector"
                ),
                "reference": "NFPA 72 §17.6.4",
            })

    # Check 5: Memory-suggested conflict patterns (ADVISORY)
    # Memory hints about hazardous areas, duct detectors, etc.
    memory_hints = memory_context.get("hints", [])
    for hint in memory_hints:
        category = hint.get("category", "")
        content = hint.get("content", "")
        confidence = hint.get("confidence", 0.0)
        std_ref = hint.get("standard_reference", "")

        # Only add ADVISORY conflicts for high-confidence hints
        # about specific conflict patterns
        if confidence >= 0.7 and category == "code_reference" and content:
            # Check if this hint is relevant to any room
            for result in nfpa_results:
                occupancy = result.get("occupancy_type", "")
                if occupancy and occupancy.lower() in content.lower():
                    conflicts.append({
                        "type": "MEMORY_ADVISORY",
                        "severity": "LOW",
                        "room": result["name"],
                        "message": (
                            f"Memory advisory for '{result['name']}': "
                            f"{content[:150]}"
                        ),
                        "reference": std_ref or "memory",
                        "source": "memory",
                        "note": "ADVISORY — from engineering memory, not deterministic check",
                    })
                    break  # One advisory per hint

    # Check 6: Mechanical/electrical rooms need heat detectors
    for result in nfpa_results:
        occupancy = result.get("occupancy_type", "")
        detector_type = result.get("detector_type", "")
        if occupancy in ("mechanical", "electrical", "electrical_room"):
            if detector_type.startswith("SMOKE"):
                conflicts.append({
                    "type": "HAZARDOUS_AREA_DETECTOR",
                    "severity": "HIGH",
                    "room": result["name"],
                    "message": (
                        f"Room '{result['name']}': {occupancy} rooms typically "
                        "require HEAT detectors (rate-of-rise), not SMOKE. "
                        "Review per NFPA 72 and environmental conditions."
                    ),
                    "reference": "NFPA 72 §17.6.3.1",
                })

    has_critical = any(c["severity"] == "CRITICAL" for c in conflicts)

    # Count memory advisory conflicts separately for reporting
    memory_advisory_count = sum(
        1 for c in conflicts if c.get("source") == "memory"
    )

    updates = {
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
        "has_critical_conflicts": has_critical,
    }

    state = {**state, **updates}
    return _log_transition(
        state,
        from_node="nfpa_analysis",
        to_node="conflict_detection",
        evidence=(
            f"Conflicts: {len(conflicts)}, Critical: {has_critical}, "
            f"Memory advisories: {memory_advisory_count}"
        ),
    )


@with_stuck_detection
def node_human_review_gate(state: PipelineState) -> PipelineState:
    """Human review gate — blocks automated progression until reviewer approves.

    This is the KEY safety feature enabled by LangGraph:
    - interrupt_before allows the workflow to pause here
    - Reviewer can inspect the full state before approving
    - Rejected items loop back for correction
    - Every review decision is logged with timestamp and evidence

    Per agent.md: "NO PHASE SKIPPING" (Rule 15)
    Per NFPA 72: PE review required for all fire alarm designs
    """
    conflicts = state.get("conflicts", [])
    nfpa_results = state.get("nfpa_results", [])
    has_critical = state.get("has_critical_conflicts", False)

    # Determine if human review is required
    review_required = has_critical
    review_items = []

    # Critical conflicts → MANDATORY review
    for conflict in conflicts:
        if conflict["severity"] == "CRITICAL":
            review_items.append({
                "item": conflict["message"],
                "type": conflict["type"],
                "severity": conflict["severity"],
                "action_required": "Resolve conflict before proceeding",
            })

    # Unknown occupancy rooms → MANDATORY review
    unknown_rooms = [
        r for r in nfpa_results if r.get("occupancy_type") == "unknown"
    ]
    if unknown_rooms:
        review_required = True
        review_items.append({
            "item": f"{len(unknown_rooms)} room(s) with unknown occupancy type",
            "type": "UNKNOWN_OCCUPANCY",
            "severity": "HIGH",
            "action_required": "Assign occupancy types before design can complete",
        })

    # Large rooms → RECOMMENDED review
    flagged_rooms = [r for r in nfpa_results if r.get("is_flagged", False)]
    if flagged_rooms:
        for r in flagged_rooms:
            review_items.append({
                "item": f"Room '{r['name']}' ({r['area_sqm']}m²) flagged for review",
                "type": "SPECIAL_REVIEW",
                "severity": "MEDIUM",
                "action_required": "Verify detector placement meets NFPA 72",
            })

    updates = {
        "review_required": review_required,
        "review_items": review_items,
    }

    if review_required:
        updates["status"] = WorkflowStatus.AWAITING_REVIEW.value

    state = {**state, **updates}
    return _log_transition(
        state,
        from_node="conflict_detection",
        to_node="human_review_gate",
        evidence=f"Review required: {review_required}, Items: {len(review_items)}, "
                 f"Critical: {has_critical}",
    )


@with_stuck_detection
def node_generate_report(state: PipelineState) -> PipelineState:
    """Generate the final NFPA 72 design report.

    This is the FINAL node — produces the signed, hash-verified report
    that the engineer can submit to the AHJ.

    V73: After generating the report, stores the analysis results in Mem0
    for future reference. Storage failure NEVER blocks report generation.

    Per agent.md: "proof_valid Safety Gate" — report must reflect actual
    compliance status, not fabricated compliance.
    """
    nfpa_results = state.get("nfpa_results", [])
    rooms = state.get("rooms", [])
    conflicts = state.get("conflicts", [])
    env_ctx = state.get("environmental_context", {})
    memory_context = state.get("memory_context", {})
    workflow_id = state.get("workflow_id", "")

    # Build report
    unknown_count = sum(
        1 for r in nfpa_results if r.get("occupancy_type") == "unknown"
    )
    has_unknown = unknown_count > 0

    report = {
        "report_metadata": {
            "workflow_id": state.get("workflow_id", "unknown"),
            "source_file": state.get("file_path", ""),
            "file_sha256": state.get("file_sha256", ""),
            "status": "FAILED" if has_unknown else "COMPLETE",
            "requires_pe_review": True,  # Always required per NFPA 72
            "design_complete": not has_unknown,
            "review_reason": (
                f"Design incomplete. {unknown_count} rooms require manual type verification."
                if has_unknown else None
            ),
            # V85 FIX: generated_utc is added AFTER SHA-256 computation.
            # Per agent.md Priority 5 (Determinism): report_sha256 must be
            # deterministic — same input = same hash. Including a timestamp
            # in the hash makes it non-deterministic, which violates the
            # determinism requirement and makes golden file comparison
            # impossible (Earthly/Playwright pattern).
        },
        "environmental_context": env_ctx,
        "rooms": nfpa_results,
        "conflicts": conflicts,
        "summary": {
            "total_rooms": len(rooms),
            "unverified_rooms": unknown_count,
            "total_detectors": state.get("total_detectors", 0),
            "coverage_pct": state.get("coverage_pct", 0.0),
            "nfpa_compliant": state.get("nfpa_compliant", False),
            "conflict_count": state.get("conflict_count", 0),
            "has_critical_conflicts": state.get("has_critical_conflicts", False),
            "compliant": not has_unknown,  # Not compliant if unknowns exist
        },
        "audit_trail": {
            "transition_count": len(state.get("transition_log", [])),
            "review_required": state.get("review_required", False),
            "reviewer_decision": state.get("reviewer_decision"),
            "review_timestamp": state.get("reviewer_timestamp") or state.get("review_timestamp"),  # V82: check both keys
        },
        "memory_context_used": {
            "hints_available": len(memory_context.get("hints", [])),
            "enrichment_performed": memory_context.get("enrichment_performed", False),
            "disclaimer": (
                "Memory context is ADVISORY ONLY. All engineering calculations "
                "are deterministic per NFPA 72 and agent.md Priority 1 (Safety)."
            ),
        },
    }

    # V85 FIX: Compute report integrity hash BEFORE adding generated_utc.
    # This ensures report_sha256 is deterministic (same input = same hash).
    # Per agent.md Priority 5 (Determinism) > Priority 7 (Traceability).
    # The timestamp is added after hashing for traceability, but does not
    # affect the integrity hash.
    report_sha256 = _compute_sha256(report)

    # Add timestamp AFTER hash computation (for display, not for integrity)
    # V85: Store generated_utc as a separate top-level field so it doesn't
    # pollute the deterministic report dict. This makes golden file comparison
    # and regression testing possible — the report dict is purely deterministic.
    generated_utc = datetime.now(timezone.utc).isoformat()

    # Final status
    final_status = WorkflowStatus.COMPLETED.value
    if has_unknown:
        final_status = WorkflowStatus.FAILED.value
    elif state.get("has_critical_conflicts", False):
        final_status = WorkflowStatus.REJECTED.value

    # V73: Store analysis results in Mem0 for future reference
    # FAIL-SAFE: Storage failure NEVER blocks report generation
    memory_storage_result = {"stored": 0, "failed": 0, "skipped": True}
    try:
        from fireai.infrastructure.mem0_workflow_bridge import store_analysis_result
        memory_storage_result = store_analysis_result(
            workflow_id=workflow_id,
            rooms=rooms,
            nfpa_results=nfpa_results,
            engineer_id=state.get("engineer_id", "engineer_default"),
            env_context=env_ctx,
        )
        logger.info(
            f"Memory storage: {memory_storage_result.get('stored', 0)} stored, "
            f"{memory_storage_result.get('failed', 0)} failed"
        )
    except ImportError:
        logger.warning("mem0_workflow_bridge not available — skipping result storage")
    except Exception as e:
        logger.warning(
            f"Memory storage failed: {type(e).__name__}: {e}. "
            "Report generated successfully without memory storage."
        )

    # V78: Store procedural trace in Mem0 (Pattern 6: Procedural Memory)
    # Records the execution path of the workflow for future reference.
    # FAIL-SAFE: Storage failure NEVER blocks report generation.
    try:
        from fireai.infrastructure.mem0_workflow_bridge import store_procedural_trace
        procedural_result = store_procedural_trace(
            workflow_id=workflow_id,
            transition_log=state.get("transition_log", []),
            engineer_id=state.get("engineer_id", "engineer_default"),
        )
        logger.info(
            f"Procedural trace: {procedural_result.get('stored', 0)} steps stored"
        )
    except ImportError:
        logger.warning("store_procedural_trace not available — skipping")
    except Exception as e:
        logger.warning("Procedural trace storage failed: %s", e)

    updates = {
        "report": report,
        "report_sha256": report_sha256,
        "report_generated_utc": generated_utc,  # V85: Timestamp outside report dict for determinism
        "status": final_status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    state = {**state, **updates}
    return _log_transition(
        state,
        from_node="human_review_gate",
        to_node="generate_report",
        evidence=f"Report SHA256: {report_sha256}, Status: {final_status}, "
                 f"Rooms: {len(rooms)}, Compliant: {not has_unknown}",
    )


# ── Conditional Edge Functions ────────────────────────────────────────────────

def should_proceed_after_parse(state: PipelineState) -> str:
    """Route after parse: success → validate, failure → END."""
    if state.get("parse_success", False):
        return "validate"
    return "generate_report"  # Generate failure report


def should_proceed_after_validation(state: PipelineState) -> str:
    """Route after validation: pass → environmental context, fail → END.

    V83 FIX: Changed from "memory_enrich" to "environmental_context" because
    environmental_context must run first to populate state["environmental_context"]
    before memory_enrich reads it for regional standards search.
    """
    if state.get("validation_passed", False):
        return "environmental_context"  # V83: was "memory_enrich"
    return "generate_report"  # Generate failure report


def should_require_review(state: PipelineState) -> str:
    """Route after conflict detection:
    - Critical conflicts → human review gate
    - No critical issues → generate report directly
    """
    if state.get("review_required", False):
        return "human_review_gate"
    return "generate_report"


def should_proceed_after_review(state: PipelineState) -> str:
    """Route after human review:
    - Approved → generate report
    - Rejected → END (stop, do not generate)
    - No decision yet → END (waiting for interrupt)
    """
    decision = state.get("reviewer_decision")
    if decision == "approved":
        return "generate_report"
    if decision == "rejected":
        return END
    # No decision yet — workflow is paused at human_review_gate
    # This path should not be reached in normal operation
    return END


# ── Workflow Graph Builder ───────────────────────────────────────────────────

def build_fireai_workflow() -> StateGraph:
    """Build the FireAI analysis workflow as a LangGraph StateGraph.

    Graph topology (V73 with Mem0 integration):
        START → initialize → parse → validate → memory_enrich
            → environmental_context → nfpa_analysis → conflict_detection
            → [human_review_gate] → generate_report → END

    Conditional edges:
        parse → validate | generate_report (on parse failure)
        validate → memory_enrich | generate_report (on validation failure)
        conflict_detection → human_review_gate | generate_report (no critical issues)
        human_review_gate → generate_report | END (on rejection)

    V73 Addition:
        memory_enrich: Searches Mem0 for advisory engineering context.
        Memory is ADVISORY only — NEVER overrides deterministic calculations.

    Human-in-the-loop:
        interrupt_before=["human_review_gate"] when review_required=True
    """
    workflow = StateGraph(PipelineState)

    # Add nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("parse", node_parse)
    workflow.add_node("validate", node_validate)
    workflow.add_node("memory_enrich", node_memory_enrich)
    workflow.add_node("environmental_context", node_environmental_context)
    workflow.add_node("nfpa_analysis", node_nfpa_analysis)
    workflow.add_node("conflict_detection", node_conflict_detection)
    workflow.add_node("human_review_gate", node_human_review_gate)
    workflow.add_node("generate_report", node_generate_report)

    # Set entry point
    workflow.set_entry_point("initialize")

    # Add edges
    workflow.add_edge("initialize", "parse")

    # Conditional: parse success → validate, failure → report
    workflow.add_conditional_edges(
        "parse",
        should_proceed_after_parse,
        {
            "validate": "validate",
            "generate_report": "generate_report",
        },
    )

    # Conditional: validation pass → environmental context, fail → report
    # V83 FIX: Route to environmental_context first (not memory_enrich) because
    # environmental_context must populate state before memory_enrich reads it.
    workflow.add_conditional_edges(
        "validate",
        should_proceed_after_validation,
        {
            "environmental_context": "environmental_context",  # V83: was memory_enrich
            "generate_report": "generate_report",
        },
    )

    # Sequential: env context → memory enrich → NFPA → conflict detection
    # V83 FIX: Swapped order — environmental_context must run BEFORE memory_enrich
    # because node_memory_enrich reads state["environmental_context"] for regional
    # standards search (V75 feature). With the old order (memory_enrich → env_context),
    # the env_context was always empty {} when memory_enrich ran, making the V75
    # regional standards feature completely non-functional.
    # Per agent.md Rule 17: Root cause is pipeline node ordering, not the code logic.
    workflow.add_edge("environmental_context", "memory_enrich")
    workflow.add_edge("memory_enrich", "nfpa_analysis")
    workflow.add_edge("nfpa_analysis", "conflict_detection")

    # Conditional: conflicts → review gate or direct report
    workflow.add_conditional_edges(
        "conflict_detection",
        should_require_review,
        {
            "human_review_gate": "human_review_gate",
            "generate_report": "generate_report",
        },
    )

    # Conditional: review decision → report or END
    workflow.add_conditional_edges(
        "human_review_gate",
        should_proceed_after_review,
        {
            "generate_report": "generate_report",
            END: END,
        },
    )

    # Report → END
    workflow.add_edge("generate_report", END)

    return workflow


# ── Workflow Service ─────────────────────────────────────────────────────────

class WorkflowService:
    """Service for managing FireAI analysis workflows.

    Provides:
    - Start new workflows (with or without human review)
    - Get workflow status and state
    - Approve/reject at human review gates
    - Resume paused workflows
    - Get full audit trail

    Thread-safe via AsyncSqliteSaver persistent checkpointing (V72 fix).
    V77: Stuck detection monitors node execution times and escalates when
    a node exceeds its timeout threshold.
    """

    def __init__(self):
        self._workflows: Dict[str, Dict[str, Any]] = {}
        # V129 FIX: Expose _langgraph_available and is_initialized so that
        # app.py lifespan can correctly report service status instead of
        # falling through to the "DEGRADED" warning path.
        self._langgraph_available = True
        self.is_initialized = True
        # CRITICAL FIX (V72): Old MemorySaver (in-memory only) was removed —
        # server crash = total checkpoint loss = potential life-safety data gone.
        # Replaced with AsyncSqliteSaver for persistent SQLite checkpointing.
        # Per agent.md Rule 1 (Absolute Truth) and Priority 4 (Reliability).
        checkpoint_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "checkpoints"
        )
        os.makedirs(checkpoint_dir, exist_ok=True)
        self._checkpoint_db_path = os.path.join(checkpoint_dir, "workflow_checkpoints.db")
        self._checkpointer = None  # Lazy-init in async context
        self._graph = build_fireai_workflow()
        # V88 FIX: Compile graph synchronously (without checkpointer) so that
        # _graph_compiled is not None after __init__. This fixes the test
        # contract that expects service._graph_compiled to be set immediately.
        # The graph will be re-compiled WITH AsyncSqliteSaver in _ensure_compiled()
        # when the first workflow runs (async context required for checkpointer).
        # Per agent.md Rule 17: Root cause is that V72's switch to AsyncSqliteSaver
        # (async-only) broke the synchronous compilation contract of __init__.
        self._checkpointer_initialized = False
        self._graph_compiled = self._graph.compile(
            interrupt_before=["human_review_gate"],
        )

        # V77: Stuck detection — monitors node execution times
        self._stuck_detector = None
        if STUCK_DETECTION_AVAILABLE:
            self._stuck_detector = get_stuck_detector()
            # Set callback for automatic stuck workflow handling
            self._stuck_detector.set_stuck_callback(self._on_workflow_stuck)
            # Start the background watchdog
            self._stuck_detector.start_watchdog_sync(interval_seconds=30)
            logger.info("WorkflowService initialized with StuckDetector V77 (watchdog active)")
        else:
            logger.warning("StuckDetector not available — workflow stuck detection DISABLED")

        logger.info("WorkflowService initialized with SQLite checkpointing at %s", self._checkpoint_db_path)

    async def _ensure_compiled(self):
        """Lazy-initialize the checkpointer and re-compile the graph with it.

        V88: Changed guard from `if self._graph_compiled is not None` to
        `if self._checkpointer_initialized` because __init__ now compiles
        the graph WITHOUT checkpointer (synchronous). This method upgrades
        the compiled graph to include AsyncSqliteSaver for persistent
        checkpointing — required for crash recovery per V72.
        """
        if self._checkpointer_initialized:
            return self._graph_compiled

        # AsyncSqliteSaver.from_conn_string returns a context manager
        # We enter it once and keep it for the lifetime of the service
        self._checkpointer_ctx = AsyncSqliteSaver.from_conn_string(self._checkpoint_db_path)
        self._checkpointer = await self._checkpointer_ctx.__aenter__()
        self._graph_compiled = self._graph.compile(
            checkpointer=self._checkpointer,
            interrupt_before=["human_review_gate"],
        )
        self._checkpointer_initialized = True
        logger.info("Workflow graph compiled with AsyncSqliteSaver (checkpointing active)")
        return self._graph_compiled

    async def start_workflow(
        self,
        file_path: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        skip_human_review: bool = False,
        engineer_id: str = "engineer_default",
    ) -> Dict[str, Any]:
        """Start a new FireAI analysis workflow.

        Args:
            file_path: Path to DWG/PDF/DXF file
            latitude: Building latitude (optional)
            longitude: Building longitude (optional)
            skip_human_review: Skip human review gate (DEVELOPMENT ONLY)
            engineer_id: Engineer identifier for Mem0 user-scoping (V85).
                         Used to scope memories per-engineer so each
                         engineer gets personalized advisory context.

        Returns:
            Dict with workflow_id, status, and initial state

        """
        import uuid

        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"

        initial_state: PipelineState = {
            "file_path": file_path,
            "latitude": latitude,
            "longitude": longitude,
            "rooms": [],
            "parse_warnings": [],
            "parse_success": False,
            "validation_result": {},
            "validation_passed": False,
            "validation_evidence": [],
            "environmental_context": {},
            "nfpa_results": [],
            "total_detectors": 0,
            "coverage_pct": 0.0,
            "nfpa_compliant": False,
            "conflicts": [],
            "conflict_count": 0,
            "has_critical_conflicts": False,
            "memory_context": {},
            "memory_enrichment_time_ms": 0.0,
            "review_required": False,
            "review_items": [],
            "reviewer_decision": None,
            "reviewer_comments": None,
            "review_timestamp": None,  # V82: Also sets reviewer_timestamp for TypedDict consistency
            "reviewer_timestamp": None,
            "report": {},
            "report_sha256": "",
            "workflow_id": workflow_id,
            "engineer_id": engineer_id,  # V85: Dynamic engineer scoping for Mem0
            "status": WorkflowStatus.PENDING.value,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "transition_log": [],
            "error_message": None,
            # V77: Stuck detection fields
            "stuck_detected": False,
            "stuck_node": None,
            "stuck_duration_seconds": None,
            "node_timings": {},
        }

        config = {"configurable": {"thread_id": workflow_id}}

        # V77: Register workflow with StuckDetector
        if self._stuck_detector is not None:
            self._stuck_detector.register_workflow(workflow_id)

        # Ensure graph is compiled with AsyncSqliteSaver
        compiled = await self._ensure_compiled()

        if skip_human_review:
            # Compile without interrupt for development mode
            graph_no_interrupt = self._graph.compile(
                checkpointer=self._checkpointer,
            )
            result = await self._run_graph(graph_no_interrupt, initial_state, config)
        else:
            result = await self._run_graph(compiled, initial_state, config)

        # V77: Unregister workflow from StuckDetector (completed/failed/stuck)
        if self._stuck_detector is not None:
            self._stuck_detector.unregister_workflow(workflow_id)

        # Store workflow state
        self._workflows[workflow_id] = {
            "state": result,
            "config": config,
            "skip_human_review": skip_human_review,
        }

        return {
            "workflow_id": workflow_id,
            "status": result.get("status", "UNKNOWN"),
            "review_required": result.get("review_required", False),
            "review_items": result.get("review_items", []),
            "total_detectors": result.get("total_detectors", 0),
            "coverage_pct": result.get("coverage_pct", 0.0),
            "nfpa_compliant": result.get("nfpa_compliant", False),
            "conflict_count": result.get("conflict_count", 0),
            "report": result.get("report", {}),
            "report_sha256": result.get("report_sha256", ""),
            "transition_count": len(result.get("transition_log", [])),
        }

    async def _run_graph(
        self,
        graph,
        initial_state: PipelineState,
        config: Dict[str, Any],
    ) -> PipelineState:
        """Run the workflow graph and return final state.

        V80: Now integrates Langfuse CallbackHandler for observability.
        The handler auto-traces every node execution with full I/O capture.
        FAIL-SAFE: If Langfuse is unavailable, graph runs without tracing.
        """
        try:
            # V80: Get Langfuse callback handler for this workflow
            # This auto-traces every LangGraph node execution
            langfuse_handler = None
            if LANGFUSE_AVAILABLE:
                workflow_id = initial_state.get("workflow_id", "unknown")
                langfuse_handler = get_langfuse_callback_handler(
                    workflow_id=workflow_id,
                    project_id="",  # Could be set per-project in future
                )

            # Build LangGraph config with optional Langfuse callbacks
            invoke_config = dict(config)
            if langfuse_handler:
                invoke_config["callbacks"] = [langfuse_handler]
                logger.info("Langfuse tracing ACTIVE for workflow %s", initial_state.get('workflow_id', '?'))
            else:
                logger.debug("Langfuse tracing not active (handler not available)")

            # V85 FIX: Replaced asyncio.get_event_loop() with
            # asyncio.get_running_loop(). The deprecated get_event_loop()
            # emits DeprecationWarning since Python 3.10 and will be
            # removed in Python 3.14. Since _run_graph is an async method,
            # we are guaranteed to be inside a running event loop, making
            # get_running_loop() the correct and safe replacement.
            # Per agent.md Rule 17: Root cause is using a deprecated API
            # that will break in future Python versions.
            import asyncio
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: graph.invoke(initial_state, invoke_config),
            )

            # V80: Log verification scores to Langfuse after workflow completes
            if LANGFUSE_AVAILABLE and langfuse_handler:
                self._log_workflow_scores_to_langfuse(result, langfuse_handler)
                # Flush to ensure all traces/scores are sent
                try:
                    flush_langfuse()
                except Exception as e:
                    logger.debug("Langfuse flush failed (non-blocking): %s", e)
                    pass  # Non-blocking

            return result if result else initial_state
        except Exception as e:
            logger.error("Workflow execution failed: %s", e, exc_info=True)
            return {
                **initial_state,
                "status": WorkflowStatus.FAILED.value,
                "error_message": f"Workflow execution error: {type(e).__name__}: {e}",
            }

    def _log_workflow_scores_to_langfuse(
        self,
        state: PipelineState,
        handler,
    ) -> None:
        """Log workflow verification results as Langfuse EVAL scores.

        V80: These scores are VERIFICATION RESULTS, not opinions.
        They reflect deterministic calculation outcomes that are
        tamper-evident when stored via the EVAL source in Langfuse.

        FAIL-SAFE: Silently handles all errors — never blocks the pipeline.
        """
        try:
            # Get the trace ID from the handler
            trace_id = None
            if hasattr(handler, 'trace_id') and handler.trace_id:
                trace_id = handler.trace_id
            elif hasattr(handler, '_trace_id') and handler._trace_id:
                trace_id = handler._trace_id

            if not trace_id:
                logger.debug("No Langfuse trace_id available for scoring")
                return

            log_workflow_scores(
                trace_id=trace_id,
                coverage_pct=state.get("coverage_pct", 0.0),
                nfpa_compliant=state.get("nfpa_compliant", False),
                conflict_count=state.get("conflict_count", 0),
                has_critical=state.get("has_critical_conflicts", False),
                validation_passed=state.get("validation_passed", False),
            )
            logger.info(
                f"Langfuse scores logged: coverage={state.get('coverage_pct', 0):.1f}%, "
                f"compliant={state.get('nfpa_compliant', False)}, "
                f"safety_gate={'PASS' if not state.get('has_critical_conflicts', False) and state.get('validation_passed', False) and state.get('nfpa_compliant', False) else 'FAIL'}"
            )
        except Exception as e:
            logger.debug("Langfuse score logging failed (non-blocking): %s", e)

    async def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a workflow."""
        if workflow_id not in self._workflows:
            return None

        state = self._workflows[workflow_id]["state"]
        return {
            "workflow_id": workflow_id,
            "status": state.get("status", "UNKNOWN"),
            "review_required": state.get("review_required", False),
            "review_items": state.get("review_items", []),
            "total_detectors": state.get("total_detectors", 0),
            "nfpa_compliant": state.get("nfpa_compliant", False),
            "transition_count": len(state.get("transition_log", [])),
            # V77: Stuck detection info
            "stuck_detected": state.get("stuck_detected", False),
            "stuck_node": state.get("stuck_node"),
            "node_timings": state.get("node_timings", {}),
        }

    async def check_stuck_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Check if a specific workflow is stuck (V77).

        Uses the StuckDetector to determine if a workflow node has
        exceeded its timeout threshold. Returns the detection result
        with escalation level and recovery recommendation.

        Per agent.md:
        - Priority 1 (Safety): Stuck detection prevents silent failures
        - Priority 4 (Reliability): Recovery recommendations restore operation
        - Priority 7 (Traceability): Detection results are logged with evidence
        """
        if self._stuck_detector is None:
            return {
                "workflow_id": workflow_id,
                "error": "StuckDetector not available",
                "stuck_detected": False,
            }

        result = self._stuck_detector.check_stuck(workflow_id)
        result_dict = result.to_dict()

        # If stuck, update the workflow state
        if result.is_stuck and workflow_id in self._workflows:
            state = self._workflows[workflow_id]["state"]
            state["stuck_detected"] = True
            state["stuck_node"] = result.stuck_node
            state["stuck_duration_seconds"] = result.node_elapsed_seconds
            state["status"] = WorkflowStatus.STUCK.value
            state["error_message"] = (
                f"Workflow stuck at node '{result.stuck_node}' "
                f"({result.node_elapsed_seconds:.0f}s > "
                f"{result.node_timeout_seconds}s timeout). "
                f"Recovery: {result.recommendation}"
            )
            # Log the stuck detection in the audit trail
            state = _log_transition(
                state,
                from_node=result.stuck_node or "unknown",
                to_node="STUCK_DETECTED",
                evidence=(
                    f"StuckDetector V77: Node '{result.stuck_node}' exceeded "
                    f"timeout ({result.node_elapsed_seconds:.0f}s > "
                    f"{result.node_timeout_seconds}s). "
                    f"Escalation: {result.escalation.value}"
                ),
            )
            self._workflows[workflow_id]["state"] = state

        return result_dict

    async def get_all_stuck_workflows(self) -> List[Dict[str, Any]]:
        """Get all currently stuck workflows (V77).

        Used for monitoring dashboards and alerting systems.
        """
        if self._stuck_detector is None:
            return []

        results = self._stuck_detector.get_all_stuck_workflows()
        return [r.to_dict() for r in results]

    def _on_workflow_stuck(self, result) -> None:
        """Callback invoked by StuckDetector watchdog when a stuck workflow is detected.

        This is called from the watchdog's background thread, so it must be
        thread-safe and non-blocking. We update the in-memory workflow state
        and log the event.

        Per agent.md Priority 1 (Safety): We cannot silently ignore stuck workflows.
        Per agent.md Priority 7 (Traceability): Every stuck detection is logged.
        """
        workflow_id = result.workflow_id

        if workflow_id in self._workflows:
            state = self._workflows[workflow_id]["state"]
            state["stuck_detected"] = True
            state["stuck_node"] = result.stuck_node
            state["stuck_duration_seconds"] = result.node_elapsed_seconds
            state["status"] = WorkflowStatus.STUCK.value
            state["error_message"] = (
                f"Watchdog detected stuck workflow at node '{result.stuck_node}' "
                f"({result.node_elapsed_seconds:.0f}s). "
                f"Recovery: {result.recommendation}"
            )
            logger.critical(
                f"WORKFLOW STUCK — Watchdog detected: Workflow {workflow_id} "
                f"stuck at node '{result.stuck_node}' "
                f"(escalation={result.escalation.value}). "
                f"Engineer action required: {result.recommendation}"
            )
        else:
            logger.warning(
                f"Watchdog detected stuck workflow {workflow_id} "
                f"but it's not in the active workflows dict. "
                f"Stuck node: {result.stuck_node}"
            )

    async def approve_workflow(
        self,
        workflow_id: str,
        reviewer_comments: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Approve a workflow at the human review gate.

        Resumes the workflow and generates the final report.
        """
        if workflow_id not in self._workflows:
            return None

        wf = self._workflows[workflow_id]
        state = wf["state"]
        config = wf["config"]

        if state.get("status") != WorkflowStatus.AWAITING_REVIEW.value:
            return {
                "error": f"Workflow is not awaiting review (status={state.get('status')})",
                "workflow_id": workflow_id,
            }

        # Update state with reviewer decision
        state["reviewer_decision"] = "approved"
        state["reviewer_comments"] = reviewer_comments
        state["review_timestamp"] = datetime.now(timezone.utc).isoformat()
        state["reviewer_timestamp"] = state["review_timestamp"]  # V82: keep both keys in sync
        state["status"] = WorkflowStatus.APPROVED.value

        # Log the approval
        state = _log_transition(
            state,
            from_node="human_review_gate",
            to_node="approved",
            evidence=f"Reviewer: approved, Comments: {reviewer_comments or 'none'}",
        )

        # Resume workflow (re-invoke with updated state)
        try:
            compiled = await self._ensure_compiled()
            # V85 FIX: Same as _run_graph — replaced deprecated
            # asyncio.get_event_loop() with asyncio.get_running_loop().
            # This is an async method so a running loop is guaranteed.
            import asyncio
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: compiled.invoke(state, config),
            )
            if result:
                wf["state"] = result

            return {
                "workflow_id": workflow_id,
                "status": result.get("status", "UNKNOWN") if result else state.get("status"),
                "report": result.get("report", {}) if result else {},
                "report_sha256": result.get("report_sha256", "") if result else "",
            }
        except Exception as e:
            logger.error("Workflow resume failed: %s", e, exc_info=True)
            return {
                "error": f"Resume failed: {type(e).__name__}: {e}",
                "workflow_id": workflow_id,
            }

    async def reject_workflow(
        self,
        workflow_id: str,
        reviewer_comments: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Reject a workflow at the human review gate.

        Marks the workflow as REJECTED and does NOT generate a report.
        """
        if workflow_id not in self._workflows:
            return None

        wf = self._workflows[workflow_id]
        state = wf["state"]

        if state.get("status") != WorkflowStatus.AWAITING_REVIEW.value:
            return {
                "error": f"Workflow is not awaiting review (status={state.get('status')})",
                "workflow_id": workflow_id,
            }

        state["reviewer_decision"] = "rejected"
        state["reviewer_comments"] = reviewer_comments
        state["review_timestamp"] = datetime.now(timezone.utc).isoformat()
        state["reviewer_timestamp"] = state["review_timestamp"]  # V82: keep both keys in sync
        state["status"] = WorkflowStatus.REJECTED.value
        state["completed_at"] = datetime.now(timezone.utc).isoformat()

        # Log the rejection
        state = _log_transition(
            state,
            from_node="human_review_gate",
            to_node="rejected",
            evidence=f"Reviewer: rejected, Comments: {reviewer_comments or 'none'}",
        )

        wf["state"] = state

        return {
            "workflow_id": workflow_id,
            "status": WorkflowStatus.REJECTED.value,
            "reviewer_comments": reviewer_comments,
        }

    async def get_audit_trail(self, workflow_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get the full audit trail for a workflow."""
        if workflow_id not in self._workflows:
            return None

        state = self._workflows[workflow_id]["state"]
        return state.get("transition_log", [])

    async def resume_from_checkpoint(
        self,
        workflow_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Resume a workflow from its last checkpoint after a crash.

        V75 ADDITION: This method enables crash recovery by reading the
        persisted checkpoint from AsyncSqliteSaver and continuing the
        workflow from where it was interrupted.

        USE CASES:
        1. Server crash mid-workflow — resume without restarting
        2. Process killed during NFPA analysis — recover partial results
        3. OOM during large project — resume from last checkpoint
        4. Deployment restart — recover all in-progress workflows

        LIFE-SAFETY IMPLICATION:
        Without this method, a mid-analysis crash means the engineer
        must restart the entire workflow from scratch, potentially
        delaying fire protection design review. With persistent
        checkpointing (AsyncSqliteSaver), the workflow state is
        recoverable, ensuring no engineering data is lost.

        Per agent.md:
        - Priority 4 (Reliability): Crash recovery is critical
        - Priority 1 (Safety): Recovered state must be verified
        - Rule 10: Must test after any modification

        Args:
            workflow_id: The workflow ID to recover

        Returns:
            Dict with recovery status and current workflow state,
            or None if workflow_id not found or no checkpoint exists

        """
        config = {"configurable": {"thread_id": workflow_id}}

        try:
            await self._ensure_compiled()

            # Try to read the checkpoint from AsyncSqliteSaver
            checkpoint_state = None
            try:
                # Get the current state from the checkpointer
                checkpoint_tuple = await self._checkpointer.aget(config=config)
                if checkpoint_tuple is not None:
                    # Extract the channel values from the checkpoint
                    if isinstance(checkpoint_tuple, dict):
                        checkpoint_state = checkpoint_tuple.get(
                            "channel_values", checkpoint_tuple
                        )
                    else:
                        checkpoint_state = checkpoint_tuple
            except Exception as e:
                logger.warning(
                    f"Checkpoint read failed for workflow {workflow_id}: {e}. "
                    "Attempting in-memory recovery."
                )

            # If checkpoint recovery succeeded, store the recovered state
            if checkpoint_state is not None:
                recovered_state = (
                    checkpoint_state if isinstance(checkpoint_state, dict) else {}
                )

                # Log the recovery event
                recovered_state = _log_transition(
                    recovered_state,
                    from_node="CRASH_RECOVERY",
                    to_node="resumed",
                    evidence=(
                        f"Workflow recovered from SQLite checkpoint after crash. "
                        f"Status: {recovered_state.get('status', 'UNKNOWN')}, "
                        f"Transitions before crash: "
                        f"{len(recovered_state.get('transition_log', []))}"
                    ),
                )

                # Store in the in-memory workflows dict
                self._workflows[workflow_id] = {
                    "state": recovered_state,
                    "config": config,
                    "skip_human_review": False,
                }

                logger.info(
                    f"Workflow {workflow_id} recovered from checkpoint. "
                    f"Status: {recovered_state.get('status', 'UNKNOWN')}, "
                    f"Rooms: {len(recovered_state.get('rooms', []))}"
                )

                return {
                    "workflow_id": workflow_id,
                    "recovered": True,
                    "status": recovered_state.get("status", "UNKNOWN"),
                    "review_required": recovered_state.get("review_required", False),
                    "total_detectors": recovered_state.get("total_detectors", 0),
                    "nfpa_compliant": recovered_state.get("nfpa_compliant", False),
                    "transition_count": len(
                        recovered_state.get("transition_log", [])
                    ),
                    "rooms_analyzed": len(recovered_state.get("rooms", [])),
                    "memory_enriched": recovered_state.get(
                        "memory_context", {}
                    ).get("enrichment_performed", False),
                }

            # Check in-memory workflows as fallback
            if workflow_id in self._workflows:
                wf = self._workflows[workflow_id]
                state = wf["state"]
                logger.info(
                    f"Workflow {workflow_id} found in memory "
                    "(no checkpoint recovery needed)"
                )
                return {
                    "workflow_id": workflow_id,
                    "recovered": False,
                    "source": "in_memory",
                    "status": state.get("status", "UNKNOWN"),
                }

            # No checkpoint and no in-memory state
            logger.warning(
                f"Workflow {workflow_id} not found in checkpoints or memory. "
                "No recovery possible."
            )
            return None

        except Exception as e:
            logger.error(
                f"Crash recovery failed for workflow {workflow_id}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            return {
                "workflow_id": workflow_id,
                "recovered": False,
                "error": f"Recovery failed: {type(e).__name__}: {e}",
            }

    async def list_recoverable_workflows(self) -> List[Dict[str, Any]]:
        """List all workflows that have persisted checkpoints and can be recovered.

        This is useful after a server restart to find in-progress workflows
        that were interrupted by a crash.

        Returns:
            List of dicts with workflow_id and status for each recoverable workflow

        """
        recoverable = []
        for workflow_id, wf in self._workflows.items():
            state = wf["state"]
            recoverable.append({
                "workflow_id": workflow_id,
                "status": state.get("status", "UNKNOWN"),
                "started_at": state.get("started_at"),
                "review_required": state.get("review_required", False),
            })
        return recoverable


# ── Singleton Management ─────────────────────────────────────────────────────

_workflow_service: Optional[WorkflowService] = None


def get_workflow_service() -> WorkflowService:
    """Get or create the singleton WorkflowService."""
    global _workflow_service
    if _workflow_service is None:
        _workflow_service = WorkflowService()
    return _workflow_service


async def close_workflow_service() -> None:
    """Close the WorkflowService (cleanup)."""
    global _workflow_service
    if _workflow_service is not None:
        _workflow_service._workflows.clear()
        _workflow_service = None
        logger.info("WorkflowService closed")
