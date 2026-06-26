"""backend/routers/rag_router.py — RAG API Endpoints"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from backend.services.rag_service import RAGQuery, RAGService

logger = logging.getLogger("fireai.routers.rag")

router = APIRouter(prefix="/rag", tags=["rag"])

_service = RAGService()


@router.post("/query")
async def query_rag(request: Request) -> dict:
    """Query the RAG knowledge base for building code answers."""
    body = await request.json()
    question = body.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    correlation_id = body.get("correlation_id") or request.headers.get("X-Correlation-ID")
    top_k = body.get("top_k", 5)
    sources = body.get("sources")

    query = RAGQuery(
        question=question,
        correlation_id=correlation_id,
        top_k=top_k,
        sources=sources or [],
    )
    response = _service.query(query)
    return {
        "status": "ok",
        "question": response.question,
        "answer": response.answer,
        "sources": response.sources,
        "correlation_id": response.correlation_id,
        "disclaimer": response.disclaimer,
        "confidence": response.confidence,
    }


@router.post("/seed")
async def seed_knowledge_base() -> dict:
    """Seed the RAG knowledge base with NFPA 72 and Egyptian Code."""
    count = _service.seed_nfpa72()
    return {"status": "ok", "seeded": count}


@router.get("/stats")
async def get_stats() -> dict:
    """Get knowledge base statistics."""
    return {"status": "ok", "data": _service.get_stats()}
