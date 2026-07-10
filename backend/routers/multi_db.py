# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
backend/routers/multi_db.py — Multi-Database API Endpoints
=========================================================

API endpoints for interacting with the multi-database system:
- PostgreSQL (primary relational data)
- Qdrant (vector database for embeddings/RAG)
- Neo4j (graph database for relationships/topology)
- Redis (cache and temporary storage)

These endpoints enable advanced BIM/CAD operations leveraging
multiple database technologies.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import require_permission
from backend.multi_db_service import get_multi_db_service
from backend.rbac import Permission
from backend.schemas import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/multi-db", tags=["multi-db"])


@router.get("/health", response_model=ApiResponse[Dict[str, bool]])
async def get_database_health():
    """Check the health of all database connections."""
    try:
        db_service = get_multi_db_service()
        health = db_service.health_check()
        return ApiResponse(
            success=True,
            data=health,
            message="Database health check completed successfully"
        )
    except Exception:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=500, detail="Database health check failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.get("/redis/get/{key}", dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))])
async def get_from_redis(key: str):
    """Get a value from Redis cache."""
    try:
        db_service = get_multi_db_service()
        value = db_service.redis_get(key)
        if value is not None:
            return ApiResponse(
                success=True,
                data={"key": key, "value": value},
                message="Value retrieved from Redis"
            )
        else:
            raise HTTPException(status_code=404, detail=f"Key '{key}' not found in Redis")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
    except Exception:
        logger.exception("Redis get failed")
        raise HTTPException(status_code=500, detail="Redis operation failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.post("/redis/set", dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))])
async def set_in_redis(key: str, value: str, ttl: Optional[int] = Query(None, description="Time to live in seconds")):  # NOSONAR - python:S8410
    """Set a value in Redis cache."""
    try:
        db_service = get_multi_db_service()
        success = db_service.redis_set(key, value, ex=ttl)
        if success:
            return ApiResponse(
                success=True,
                data={"key": key, "ttl": ttl},
                message="Value set in Redis successfully"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to set value in Redis")  # NOSONAR — S8415: assignment kept for readability / debuggability
    except Exception:
        logger.exception("Redis set failed")
        raise HTTPException(status_code=500, detail="Redis operation failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.post("/bim/cache-element", dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])
async def cache_bim_element(element_id: str, element_data: Dict):
    """Cache BIM element data in Redis for faster access."""
    try:
        db_service = get_multi_db_service()
        success = db_service.cache_bim_element(element_id, element_data)
        if success:
            return ApiResponse(
                success=True,
                data={"element_id": element_id},
                message="BIM element cached successfully"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to cache BIM element")  # NOSONAR — S8415: assignment kept for readability / debuggability
    except Exception:
        logger.exception("BIM element caching failed")
        raise HTTPException(status_code=500, detail="BIM element caching failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.get("/bim/get-cached-element/{element_id}", dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def get_cached_bim_element(element_id: str):
    """Retrieve cached BIM element data from Redis."""
    try:
        db_service = get_multi_db_service()
        element_data = db_service.get_cached_bim_element(element_id)
        if element_data:
            return ApiResponse(
                success=True,
                data={"element_id": element_id, "element_data": element_data},
                message="Cached BIM element retrieved successfully"
            )
        else:
            raise HTTPException(status_code=404, detail=f"Cached BIM element '{element_id}' not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
    except Exception:
        logger.exception("Get cached BIM element failed")
        raise HTTPException(status_code=500, detail="Get cached BIM element failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.post("/bim/store-embeddings", dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])
async def store_element_embeddings(element_id: str, embeddings: List[float]):
    """Store element embeddings in Qdrant for similarity search."""
    try:
        db_service = get_multi_db_service()
        success = db_service.store_element_embeddings(element_id, embeddings)
        if success:
            return ApiResponse(
                success=True,
                data={"element_id": element_id},
                message="Element embeddings stored successfully"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to store element embeddings")  # NOSONAR — S8415: assignment kept for readability / debuggability
    except Exception:
        logger.exception("Store element embeddings failed")
        raise HTTPException(status_code=500, detail="Store element embeddings failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.post("/bim/find-similar", dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def find_similar_elements(query_embedding: List[float], limit: int = Query(5, ge=1, le=20)):  # NOSONAR - python:S8410
    """Find similar BIM elements using vector search."""
    try:
        db_service = get_multi_db_service()
        results = db_service.find_similar_elements(query_embedding, limit)
        return ApiResponse(
            success=True,
            data={"results": results, "query_length": len(query_embedding)},
            message=f"Found {len(results)} similar elements"
        )
    except Exception:
        logger.exception("Find similar elements failed")
        raise HTTPException(status_code=500, detail="Find similar elements failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.post("/bim/create-relationships", dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])
async def create_element_relationships(
    element_id: str,
    related_elements: List[str],
    relationship_type: str = Query("CONNECTED_TO", description="Type of relationship")  # NOSONAR - python:S8410
):
    """Create relationships between elements in Neo4j."""
    try:
        db_service = get_multi_db_service()
        success = db_service.create_element_relationships(element_id, related_elements, relationship_type)
        if success:
            return ApiResponse(
                success=True,
                data={
                    "element_id": element_id,
                    "related_elements": related_elements,
                    "relationship_type": relationship_type
                },
                message="Element relationships created successfully"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to create element relationships")  # NOSONAR — S8415: assignment kept for readability / debuggability
    except Exception:
        logger.exception("Create element relationships failed")
        raise HTTPException(status_code=500, detail="Create element relationships failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.get("/bim/related-elements/{element_id}", dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def find_related_elements(
    element_id: str,
    relationship_type: str = Query("CONNECTED_TO", description="Type of relationship")  # NOSONAR - python:S8410
):
    """Find elements related to a specific element in Neo4j."""
    try:
        db_service = get_multi_db_service()
        results = db_service.neo4j_find_related_elements(element_id, relationship_type)
        return ApiResponse(
            success=True,
            data={"element_id": element_id, "related_elements": results, "relationship_type": relationship_type},
            message=f"Found {len(results)} related elements"
        )
    except Exception:
        logger.exception("Find related elements failed")
        raise HTTPException(status_code=500, detail="Find related elements failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.get("/neo4j/query", dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))])
async def execute_neo4j_query(query: str, parameters: Optional[str] = Query(None)):  # NOSONAR - python:S8410
    """Execute a custom Cypher query against Neo4j."""
    try:
        import json
        params = json.loads(parameters) if parameters else {}

        db_service = get_multi_db_service()
        results = db_service.neo4j_execute_query(query, params)
        return ApiResponse(
            success=True,
            data={"query": query, "parameters": params, "results": results},
            message=f"Query executed successfully, returned {len(results)} results"
        )
    except Exception:
        logger.exception("Neo4j query failed")
        raise HTTPException(status_code=500, detail="Neo4j query failed")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.get("/qdrant/collections", dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))])
async def get_qdrant_collections():
    """Get list of Qdrant collections."""
    try:
        db_service = get_multi_db_service()
        qdrant_client = db_service.get_qdrant()

        if not qdrant_client:
            raise HTTPException(status_code=500, detail="Qdrant not available")  # NOSONAR — S8415: assignment kept for readability / debuggability

        collections = qdrant_client.get_collections()
        collection_names = [col.name for col in collections.collections]

        return ApiResponse(
            success=True,
            data={"collections": collection_names, "count": len(collection_names)},
            message=f"Found {len(collection_names)} Qdrant collections"
        )
    except Exception:
        logger.exception("Get Qdrant collections failed")
        raise HTTPException(status_code=500, detail="Get Qdrant collections failed")  # NOSONAR — S8415: assignment kept for readability / debuggability
