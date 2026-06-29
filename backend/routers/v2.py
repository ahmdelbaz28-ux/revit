"""
v2.py — API v2 Routers for FireAI Cloud-Native Endpoints.
============================================================

MISSION TASK 3.1 — API Versioning with /api/v2/ structure
==========================================================

This module exposes the new FireAI capabilities (Generative Design,
BIM Provider abstraction, IFC 4.3 mapping, AR export, Webhooks,
Smoke Simulation state) under a versioned ``/api/v2/`` prefix.

Endpoints
---------
- ``POST /api/v2/generative/design`` — Generate 3 layout variants
- ``GET  /api/v2/bim/providers`` — List registered BIM providers
- ``POST /api/v2/bim/extract-rooms`` — Extract rooms via configured provider
- ``GET  /api/v2/bim/health`` — Health check for BIM provider
- ``POST /api/v2/ifc43/map-detector`` — Map detector to IFC 4.3
- ``POST /api/v2/ifc43/map-project`` — Map entire project to IFC 4.3
- ``POST /api/v2/ar/export`` — Export DigitalTwin to GLB/USDZ
- ``POST /api/v2/webhooks/subscribe`` — Subscribe to webhook events
- ``GET  /api/v2/webhooks/subscriptions`` — List subscriptions
- ``DELETE /api/v2/webhooks/subscriptions/{sub_id}`` — Unsubscribe
- ``POST /api/v2/webhooks/publish`` — Publish an event
- ``POST /api/v2/smoke-simulation/state`` — Create/update smoke state

Deprecation Headers
-------------------
Per HTTP standards (RFC 7234):
- v1 endpoints receive ``Deprecation: true`` header
- v1 endpoints receive ``Sunset: <date>`` header (1 year deprecation window)
- v1 endpoints receive ``Link: </api/v2/...>; rel="successor-version"``
  header pointing to the v2 equivalent

References
----------
- agent.md Rule 6/14: VERIFY BEFORE CHANGING
- RFC 7234: HTTP Caching — Deprecation and Sunset headers

"""

# V141 FIX: Removed __future__ annotations to fix Pydantic forward ref resolution.
# With __future__ annotations, Dict[str, Any] becomes ForwardRef('Dict[str, Any]')
# which Pydantic cannot resolve at runtime for FastAPI model parsing.
# Removing it forces actual type resolution at import time.

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class GenerativeDesignRequest(BaseModel):
    """
    Request body for /api/v2/generative/design.

    V138 F-13: Added upper bounds to prevent DoS via huge dimensions.
    """

    room_width: float = Field(..., gt=0, le=1000.0, description="Room width in metres (max 1000m)")
    room_length: float = Field(..., gt=0, le=1000.0, description="Room length in metres (max 1000m)")
    room_height: float = Field(3.0, gt=0, le=30.0, description="Ceiling height in metres (max 30m)")
    room_name: str = Field("API_Room", max_length=200, description="Room identifier")
    occupancy_type: str = Field("office", max_length=100, description="NFPA 101 occupancy")
    detector_type: str = Field("smoke", max_length=50, description="Detector type")
    use_multiprocessing: bool = Field(True, description="Use parallel variant generation")


class BIMExtractRoomsRequest(BaseModel):
    """Request body for /api/v2/bim/extract-rooms."""

    source: str | None = Field(None, description="File path or URL")
    provider: str | None = Field(None, description="Provider name (default: env var)")


class IFC43MapDetectorRequest(BaseModel):
    """Request body for /api/v2/ifc43/map-detector."""

    device_id: str
    type: str = "smoke"
    x: float
    y: float
    z: float = 0.0
    room_id: str = "UNASSIGNED"
    coverage_radius_m: float = 6.37
    spacing_m: float = 9.1
    ceiling_height_m: float = 3.0
    occupancy_type: str = "office"
    is_code_compliant: bool = False
    coverage_pct: float = 0.0
    run_id: str = ""
    evidence_hash: str = ""


class ARExportRequest(BaseModel):
    """Request body for /api/v2/ar/export."""

    building_id: str = "API_Building"
    format: str = Field("both", pattern="^(glb|usdz|both)$")
    nodes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="AR scene nodes (optional — empty uses DigitalTwin)",
    )


class WebhookSubscribeRequest(BaseModel):
    """Request body for /api/v2/webhooks/subscribe."""

    url: str
    secret: str = Field(..., min_length=32)  # V135 F-33: NIST SP 800-107
    event_types: list[str] = Field(default_factory=list)


class WebhookPublishRequest(BaseModel):
    """Request body for /api/v2/webhooks/publish."""

    event_type: str
    source: str
    data: dict[str, Any]
    trace_id: str | None = None


class SmokeDensityPointRequest(BaseModel):
    """V138 F-14: Pydantic model for smoke density point (was unvalidated Dict)."""

    x: float = Field(..., ge=-10000, le=10000)
    y: float = Field(..., ge=-10000, le=10000)
    z: float = Field(..., ge=-100, le=100)
    density_kg_m3: float = Field(..., ge=0, le=100)


class SmokeSimulationStateRequest(BaseModel):
    """
    Request body for /api/v2/smoke-simulation/state.

    V138 F-13: Added max_length to prevent DoS.
    V138 F-14: Use Pydantic model for smoke_density_points (was unvalidated Dict).
    """

    room_id: str = Field(..., max_length=200)
    smoke_density_points: list[SmokeDensityPointRequest] = Field(
        default_factory=list, max_length=10000
    )
    visibility_at_height: dict[float, float] = Field(default_factory=dict)
    fds_run_id: str | None = None


# ---------------------------------------------------------------------------
# Generative Design Endpoints
# ---------------------------------------------------------------------------


@router.post("/generative/design")
async def generate_design_variants(req: GenerativeDesignRequest) -> dict[str, Any]:
    """
    Generate 3 layout variants (Cost-Min, Standard, Safety-Max).

    Returns scored variants with recommendation based on occupancy.
    """
    try:
        from fireai.core.spatial_engine.density_optimizer import Room
        from fireai.core.spatial_engine.generative_layout_agent import (
            GenerativeLayoutAgent,
        )

        agent = GenerativeLayoutAgent(use_multiprocessing=req.use_multiprocessing)
        room = Room(
            name=req.room_name,
            width=req.room_width,
            length=req.room_length,
            ceiling_height=req.room_height,
        )
        result = agent.generate_variants(
            room=room,
            occupancy_type=req.occupancy_type,
            detector_type=req.detector_type,
        )
        return result.to_dict()
    except ValueError as e:
        # CodeQL: py/stack-trace-exposure — sanitize error message
        safe_msg = str(e)[:200] if "Traceback" not in str(e) else "Validation error"
        raise HTTPException(status_code=422, detail=safe_msg) from e
    except Exception as e:
        logger.error("Generative design failed: %s", e, exc_info=True)
        # CodeQL: py/stack-trace-exposure — never expose internal errors to client
        raise HTTPException(status_code=500, detail="Generation failed. Check server logs for details.") from e


# ---------------------------------------------------------------------------
# BIM Provider Endpoints
# ---------------------------------------------------------------------------


@router.get("/bim/providers")
async def list_bim_providers() -> dict[str, Any]:
    """List all registered BIM providers."""
    from fireai.bridges.bim_provider import BIMProviderRegistry

    providers = BIMProviderRegistry.list_available()
    return {
        "providers": providers,
        "active": __import__("os").environ.get("FIREAI_BIM_PROVIDER"),
        "count": len(providers),
    }


@router.post("/bim/extract-rooms")
async def extract_rooms(req: BIMExtractRoomsRequest) -> dict[str, Any]:
    """
    Extract rooms via configured BIM provider.

    V137 F-5 FIX: Added source path validation to prevent SSRF/path traversal.
    The OLD code passed ``req.source`` directly to ``provider.extract_rooms()``
    which calls ``ifcopenshell.open(source)`` — allowing arbitrary file reads.
    """
    from fireai.bridges.bim_provider import get_provider

    # V137 F-5 / V138 F-7: Validate source path if provided
    # CodeQL: py/path-injection — source is validated below with Path.resolve()
    # + is_relative_to() + null byte check + extension whitelist.
    if req.source:  # lgtm[py/path-injection] — validated below
        import os
        from pathlib import Path
        try:
            source_path = Path(req.source).resolve()
            # V138 F-7 FIX: Use Path.is_relative_to() or proper boundary check
            # instead of str.startswith() which matches "/tmp_evil" against "/tmp"
            cwd = Path.cwd().resolve()
            allowed_roots = [
                cwd,
                Path("/tmp"),
                Path("/var/tmp"),
                Path(os.environ.get("FIREAI_UPLOAD_DIR", str(cwd / "uploads"))),
            ]
            # V138 F-7: Check if source_path is within any allowed root
            # using proper path containment (not string prefix)
            def _is_within(path: Path, root: Path) -> bool:
                try:
                    path.relative_to(root)
                    return True
                except ValueError:
                    return False

            if not any(_is_within(source_path, root) for root in allowed_roots):
                raise HTTPException(
                    status_code=400,
                    detail="Source path is outside allowed directories.",
                )
            # Check for null byte injection
            if "\x00" in req.source:
                raise HTTPException(
                    status_code=400,
                    detail="Source path contains null byte (injection attempt).",
                )
            # Check file extension
            allowed_extensions = {".ifc", ".dxf", ".dwg", ".rvt", ".rfa", ".json"}
            if source_path.suffix.lower() not in allowed_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Source file extension '{source_path.suffix}' not allowed. "
                    f"Allowed: {allowed_extensions}",
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid source path: {exc}") from exc

    provider = get_provider(req.provider)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail=f"No BIM provider available. Set FIREAI_BIM_PROVIDER env var. "
            f"Registered: {__import__('fireai.bridges.bim_provider', fromlist=['BIMProviderRegistry']).BIMProviderRegistry.list_available()}",
        )

    rooms = provider.extract_rooms(source=req.source)
    return {
        "provider": provider.provider_name,
        "room_count": len(rooms),
        "rooms": [
            {
                "room_id": r.room_id,
                "name": r.name,
                "area_m2": r.area_m2,
                "ceiling_height_m": r.ceiling_height_m,
                "source": r.source,
            }
            for r in rooms
        ],
    }


@router.get("/bim/health")
async def bim_health() -> dict[str, Any]:
    """Health check for active BIM provider."""
    from fireai.bridges.bim_provider import get_provider

    provider = get_provider()
    if provider is None:
        return {
            "healthy": False,
            "details": "No BIM provider configured",
            "error": "Set FIREAI_BIM_PROVIDER env var",
        }
    return provider.health_check()


# ---------------------------------------------------------------------------
# IFC 4.3 Mapping Endpoints
# ---------------------------------------------------------------------------


@router.post("/ifc43/map-detector")
async def map_detector_to_ifc43(req: IFC43MapDetectorRequest) -> dict[str, Any]:
    """Map a FireAI detector to IFC 4.3 ADD2 representation."""
    from fireai.bridges.ifc43_mapper import IFC43Mapper

    mapper = IFC43Mapper()
    mapped = mapper.map_detector(req.model_dump())
    return {
        "global_id": mapped.global_id,
        "ifc_type": mapped.ifc_type,
        "predefined_type": mapped.predefined_type,
        "name": mapped.name,
        "location": mapped.location,
        "contained_in": mapped.contained_in,
        "property_sets": mapped.property_sets,
        "target_schema": mapped.target_schema,
    }


@router.post("/ifc43/map-project")
async def map_project_to_ifc43(req: dict[str, Any]) -> dict[str, Any]:
    """Map an entire FireAI project to IFC 4.3 ADD2."""
    from fireai.bridges.ifc43_mapper import IFC43Mapper

    mapper = IFC43Mapper()
    result = mapper.map_project(req)
    return {
        "header": result["header"],
        "statistics": result["statistics"],
        "schema_version": result["schema_version"],
        "building_global_id": result["building"].global_id,
        "rooms_count": len(result["rooms"]),
        "detectors_count": len(result["detectors"]),
    }


# ---------------------------------------------------------------------------
# AR Export Endpoints
# ---------------------------------------------------------------------------


@router.post("/ar/export")
async def export_ar_snapshot(req: ARExportRequest) -> dict[str, Any]:
    """
    Export DigitalTwin snapshot to GLB/USDZ for AR visualization.

    Returns base64-encoded file content for each requested format.
    """
    import base64

    from fireai.integration.ar_metadata_exporter import (
        ARExportFormat,
        ARMetadataExporter,
        ARSceneNode,
        ARSnapshot,
    )

    exporter = ARMetadataExporter()

    # Build snapshot from request nodes (if provided)
    if req.nodes:
        nodes = []
        for n in req.nodes:
            nodes.append(ARSceneNode(
                id=n.get("id", "unknown"),
                name=n.get("name", ""),
                node_type=n.get("node_type", "detector"),
                position=tuple(n.get("position", (0, 0, 0))),
                is_behind_wall=n.get("is_behind_wall", False),
                inspection_critical=n.get("inspection_critical", False),
            ))
        snapshot = ARSnapshot(building_id=req.building_id, nodes=nodes)
    else:
        # Without DigitalTwin access in API context, return empty snapshot
        snapshot = ARSnapshot(building_id=req.building_id)

    fmt = ARExportFormat(req.format)
    exported = exporter.export(snapshot, fmt)

    return {
        "building_id": req.building_id,
        "node_count": snapshot.node_count,
        "behind_wall_count": snapshot.behind_wall_count,
        "formats": {
            fmt_name: {
                "size_bytes": len(content),
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
            for fmt_name, content in exported.items()
        },
    }


# ---------------------------------------------------------------------------
# Webhook Endpoints
# ---------------------------------------------------------------------------


@router.post("/webhooks/subscribe")
async def subscribe_webhook(req: WebhookSubscribeRequest) -> dict[str, Any]:
    """Subscribe to webhook events."""
    from fireai.infrastructure.webhook_service import (
        WebhookSubscription,
        get_webhook_service,
    )

    service = get_webhook_service()
    try:
        sub = WebhookSubscription(
            id=f"sub-{__import__('uuid').uuid4().hex[:12]}",
            url=req.url,
            secret=req.secret,
            event_types=req.event_types,
        )
        service.subscribe(sub)
        return {
            "subscription_id": sub.id,
            "url": sub.url,
            "event_types": sub.event_types,
            "status": sub.status.value,
        }
    except ValueError as e:
        # CodeQL: py/stack-trace-exposure — sanitize error message
        safe_msg = str(e)[:200] if "Traceback" not in str(e) else "Validation error"
        raise HTTPException(status_code=422, detail=safe_msg) from e


@router.get("/webhooks/subscriptions")
async def list_webhook_subscriptions() -> dict[str, Any]:
    """List all webhook subscriptions."""
    from fireai.infrastructure.webhook_service import get_webhook_service

    service = get_webhook_service()
    subs = service.list_subscriptions()
    return {
        "count": len(subs),
        "subscriptions": [
            {
                "id": s.id,
                "url": s.url,
                "event_types": s.event_types,
                "status": s.status.value,
            }
            for s in subs
        ],
    }


@router.delete("/webhooks/subscriptions/{sub_id}")
async def unsubscribe_webhook(sub_id: str) -> dict[str, Any]:
    """Remove a webhook subscription."""
    from fireai.infrastructure.webhook_service import get_webhook_service

    service = get_webhook_service()
    removed = service.unsubscribe(sub_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Subscription {sub_id} not found")
    return {"subscription_id": sub_id, "removed": True}


@router.post("/webhooks/publish")
async def publish_webhook_event(req: WebhookPublishRequest) -> dict[str, Any]:
    """Publish an event to all matching webhook subscribers."""
    from fireai.infrastructure.webhook_service import get_webhook_service

    service = get_webhook_service()
    event_id = service.publish_event(
        event_type=req.event_type,
        source=req.source,
        data=req.data,
        trace_id=req.trace_id,
    )
    return {
        "event_id": event_id,
        "event_type": req.event_type,
        "delivered": True,
    }


# ---------------------------------------------------------------------------
# Smoke Simulation Endpoints
# ---------------------------------------------------------------------------


@router.post("/smoke-simulation/state")
async def create_smoke_state(req: SmokeSimulationStateRequest) -> dict[str, Any]:
    """
    Create or update smoke simulation state for a room.

    If FDS data is provided (fds_run_id), creates a validated state.
    Otherwise, creates a placeholder state with safety warnings.
    """
    from fireai.core.smoke_simulation_state import (
        SmokeDensityPoint,
        SmokeSimulationState,
    )

    if req.fds_run_id:
        # V137 F-6 FIX: Validate FDS run ID format to prevent fake validation.
        # The OLD code accepted ANY string as fds_run_id — a user could submit
        # arbitrary smoke data with fds_run_id="fake" and the state would be
        # marked VALIDATED, potentially tainting the legal audit chain.
        # Now we require FDS run IDs to follow a specific format (fds-YYYY-NNN)
        # and emit a WARNING if the format doesn't match. Full provenance
        # verification would require querying an FDS runner service.
        import re
        FDS_RUN_ID_PATTERN = r'^fds-\d{4}-\d{3,}$'  # e.g., "fds-2026-001"
        if not re.match(FDS_RUN_ID_PATTERN, req.fds_run_id):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid FDS run ID format: '{req.fds_run_id}'. "
                    f"Expected format: 'fds-YYYY-NNN' (e.g., 'fds-2026-001'). "
                    f"FDS run IDs must correspond to actual simulation runs — "
                    f"fake IDs are rejected to prevent audit chain contamination."
                ),
            )

        # Create validated state from FDS results
        # V138 F-14: Use Pydantic-validated points (was unvalidated Dict)
        points = [
            SmokeDensityPoint(
                x=p.x, y=p.y, z=p.z,
                density_kg_m3=p.density_kg_m3,
            )
            for p in req.smoke_density_points
        ]
        state = SmokeSimulationState.create_from_fds(
            room_id=req.room_id,
            smoke_density_points=points,
            visibility_at_height=req.visibility_at_height,
            fds_run_id=req.fds_run_id,
        )
    else:
        # Create placeholder state
        state = SmokeSimulationState.create_placeholder(req.room_id)

    return state.to_dict()


# ---------------------------------------------------------------------------
# V141: Vector Memory & Topology Endpoints
# ---------------------------------------------------------------------------


class VectorMemoryStoreRequest(BaseModel):
    """Request body for /api/v2/memory/store."""

    content: str = Field(..., min_length=1, max_length=10000)
    memory_type: str = Field("conversation", description="conversation|study_result|document|etap_knowledge")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VectorMemorySearchRequest(BaseModel):
    """Request body for /api/v2/memory/search."""

    query: str = Field(..., min_length=1, max_length=1000)
    memory_type: str = Field("conversation")
    limit: int = Field(5, ge=1, le=50)
    score_threshold: float = Field(0.0, ge=0.0, le=1.0)


class TopologyAddElementRequest(BaseModel):
    """Request body for /api/v2/topology/element."""

    element_id: str = Field(..., max_length=200)
    element_type: str = Field(..., description="Bus|Line|Transformer|Load|Breaker|Generator")
    name: str = Field("", max_length=200)
    properties: Dict[str, Any] = Field(default_factory=dict)


class TopologyAddConnectionRequest(BaseModel):
    """Request body for /api/v2/topology/connection."""

    from_element: str = Field(..., max_length=200)
    to_element: str = Field(..., max_length=200)
    relationship_type: str = Field("CONNECTED_TO")
    properties: Dict[str, Any] = Field(default_factory=dict)


class TopologyImpactRequest(BaseModel):
    """Request body for /api/v2/topology/impact."""

    breaker_id: str = Field(..., max_length=200)


@router.post("/memory/store")
async def store_memory(req: VectorMemoryStoreRequest) -> Dict[str, Any]:
    """Store a memory entry in Qdrant vector database."""
    from fireai.infrastructure.vector_memory_service import (
        MemoryType,
        get_vector_memory,
    )
    service = get_vector_memory()
    try:
        mem_type = MemoryType(req.memory_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid memory_type: {req.memory_type}")
    entry_id = service.store(content=req.content, memory_type=mem_type, metadata=req.metadata)
    if entry_id is None:
        raise HTTPException(status_code=503, detail="Qdrant unavailable — memory not stored")
    return {"entry_id": entry_id, "stored": True, "memory_type": req.memory_type}


@router.post("/memory/search")
async def search_memory(req: VectorMemorySearchRequest) -> Dict[str, Any]:
    """Search for similar memories in Qdrant."""
    from fireai.infrastructure.vector_memory_service import (
        MemoryType,
        get_vector_memory,
    )
    service = get_vector_memory()
    try:
        mem_type = MemoryType(req.memory_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid memory_type: {req.memory_type}")
    result = service.search(
        query=req.query, memory_type=mem_type,
        limit=req.limit, score_threshold=req.score_threshold,
    )
    return result.to_dict()


@router.get("/memory/health")
async def memory_health() -> Dict[str, Any]:
    """Check Qdrant vector database health."""
    from fireai.infrastructure.vector_memory_service import get_vector_memory
    return get_vector_memory().health_check()


@router.post("/topology/element")
async def add_topology_element(req: TopologyAddElementRequest) -> Dict[str, Any]:
    """Add a network element to the Neo4j topology graph."""
    from fireai.infrastructure.topology_graph_service import (
        ElementType,
        NetworkElement,
        get_topology_service,
    )
    service = get_topology_service()
    try:
        et = ElementType(req.element_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid element_type: {req.element_type}")
    element = NetworkElement(
        element_id=req.element_id, element_type=et,
        name=req.name, properties=req.properties,
    )
    added = service.add_element(element)
    return {"element_id": req.element_id, "added": added}


@router.post("/topology/connection")
async def add_topology_connection(req: TopologyAddConnectionRequest) -> Dict[str, Any]:
    """Add a connection between two network elements."""
    from fireai.infrastructure.topology_graph_service import (
        NetworkConnection,
        RelationshipType,
        get_topology_service,
    )
    service = get_topology_service()
    try:
        rt = RelationshipType(req.relationship_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid relationship_type: {req.relationship_type}")
    conn = NetworkConnection(
        from_element=req.from_element, to_element=req.to_element,
        relationship_type=rt, properties=req.properties,
    )
    added = service.add_connection(conn)
    return {"from": req.from_element, "to": req.to_element, "added": added}


@router.post("/topology/impact")
async def analyze_impact(req: TopologyImpactRequest) -> Dict[str, Any]:
    """
    Analyze the impact of tripping a breaker.

    Answers: "If I trip this breaker, which loads and buses are affected?"
    """
    from fireai.infrastructure.topology_graph_service import get_topology_service
    service = get_topology_service()
    result = service.analyze_breaker_impact(req.breaker_id)
    return result.to_dict()


@router.get("/topology/health")
async def topology_health() -> Dict[str, Any]:
    """Check Neo4j topology graph health."""
    from fireai.infrastructure.topology_graph_service import get_topology_service
    return get_topology_service().health_check()


# ---------------------------------------------------------------------------
# V142: GraphRAG Endpoints
# ---------------------------------------------------------------------------


class GraphRAGAddKnowledgeRequest(BaseModel):
    """Request body for /api/v2/graphrag/knowledge."""

    text: str = Field(..., min_length=1, max_length=50000)
    extract_entities: bool = Field(True, description="Extract entities/relationships via LLM")


class GraphRAGAskRequest(BaseModel):
    """Request body for /api/v2/graphrag/ask."""

    question: str = Field(..., min_length=1, max_length=2000)


class GraphRAGSearchRequest(BaseModel):
    """Request body for /api/v2/graphrag/search."""

    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(5, ge=1, le=50)


@router.post("/graphrag/knowledge")
async def add_graphrag_knowledge(req: GraphRAGAddKnowledgeRequest) -> Dict[str, Any]:
    """
    Add knowledge to GraphRAG (vector + entity/relationship graph).

    V142: Uses LLMGraphTransformer to extract entities and relationships
    from text, stores them in Neo4j as a knowledge graph. Also stores
    the original text as a vector for semantic search.
    """
    from fireai.infrastructure.graphrag_engine import get_graphrag_engine

    engine = get_graphrag_engine()
    if req.extract_entities:
        success = engine.add_knowledge(req.text)
    else:
        success = engine.save_to_memory(req.text)

    if not success:
        raise HTTPException(
            status_code=503,
            detail="GraphRAG engine not available (Neo4j or OpenAI not configured)",
        )
    return {"stored": True, "extract_entities": req.extract_entities, "text_length": len(req.text)}


@router.post("/graphrag/ask")
async def ask_graphrag(req: GraphRAGAskRequest) -> Dict[str, Any]:
    """
    Ask a question using GraphRAG hybrid retrieval (vector + graph).

    V142: The GraphCypherQAChain will:
    1. Generate a Cypher query from the natural language question
    2. Execute on Neo4j (graph traversal)
    3. Formulate a natural language answer
    """
    from fireai.infrastructure.graphrag_engine import get_graphrag_engine

    engine = get_graphrag_engine()
    answer = engine.ask(req.question)
    return {"question": req.question, "answer": answer}


@router.post("/graphrag/search")
async def search_graphrag(req: GraphRAGSearchRequest) -> Dict[str, Any]:
    """Semantic search in GraphRAG vector store (no LLM, fast)."""
    from fireai.infrastructure.graphrag_engine import get_graphrag_engine

    engine = get_graphrag_engine()
    results = engine.search_similar(req.query, limit=req.limit)
    return {"query": req.query, "results": results, "total": len(results)}


@router.get("/graphrag/health")
async def graphrag_health() -> Dict[str, Any]:
    """Check GraphRAG engine health."""
    from fireai.infrastructure.graphrag_engine import get_graphrag_engine

    return get_graphrag_engine().health_check()


# ---------------------------------------------------------------------------
# Health Endpoint for v2
# ---------------------------------------------------------------------------


@router.get("/health")
async def v2_health() -> dict[str, Any]:
    """Health check for v2 API endpoints."""
    return {
        "status": "ok",
        "version": "v2",
        "endpoints": [
            "/api/v2/generative/design",
            "/api/v2/bim/providers",
            "/api/v2/bim/extract-rooms",
            "/api/v2/bim/health",
            "/api/v2/ifc43/map-detector",
            "/api/v2/ifc43/map-project",
            "/api/v2/ar/export",
            "/api/v2/webhooks/subscribe",
            "/api/v2/webhooks/subscriptions",
            "/api/v2/webhooks/publish",
            "/api/v2/smoke-simulation/state",
            "/api/v2/auth/csrf-token",
            "/api/v2/health",
        ],
        "capabilities": [
            "generative_design",
            "bim_provider_abstraction",
            "ifc43_mapping",
            "ar_metadata_export",
            "webhook_delivery",
            "smoke_simulation_state",
            "csrf_protection",
        ],
    }


# ---------------------------------------------------------------------------
# CSRF Token Endpoint (PHASE 1.1)
# ---------------------------------------------------------------------------


@router.get("/auth/csrf-token")
async def get_csrf_token(request: Request) -> dict[str, Any]:
    """
    Issue a CSRF token via Double Submit Cookie pattern.

    Sets the CSRF token in:
    1. A cookie (fireai_csrf_token, SameSite=Strict)
    2. The response body (for the frontend to extract and send in X-CSRF-Token header)

    The frontend MUST call this endpoint once per session, then include the
    token in the X-CSRF-Token header for all subsequent POST/PUT/DELETE/PATCH requests.

    Per OWASP CSRF Prevention Cheat Sheet — Double Submit Cookie pattern.
    """
    from fastapi.responses import JSONResponse

    from backend.security_csrf import (
        CSRF_COOKIE_NAME,
        build_csrf_cookie_header,
        generate_csrf_token,
    )

    token = generate_csrf_token()

    # Detect HTTPS from X-Forwarded-Proto (common behind reverse proxy)
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    is_https = forwarded_proto == "https" or request.url.scheme == "https"

    cookie_header = build_csrf_cookie_header(token, is_https=is_https)

    response = JSONResponse(content={
        "csrf_token": token,
        "cookie_name": CSRF_COOKIE_NAME,
        "header_name": "X-CSRF-Token",
        "instructions": (
            "Include this token in the X-CSRF-Token header for all "
            "POST/PUT/DELETE/PATCH requests. The cookie is set automatically."
        ),
    })
    response.headers["Set-Cookie"] = cookie_header
    return response


__all__ = ["router"]
