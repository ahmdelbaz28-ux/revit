"""backend/services/memory_service.py — Mem0-based Memory Layer for FireAI (V76).

PROFESSIONAL NOTE:
  This module provides a long-term memory layer for the FireAI platform,
  enabling engineers and the FireAI agent to store and retrieve:
    - Previous building layouts and detector placements
    - User preferences and engineering style
    - Preferred standards (NFPA, BS, IEC)
    - Common calculations and patterns
    - Repeated device mappings
    - Engineering decisions and their rationale

CRITICAL SAFETY DESIGN PRINCIPLE:
  The memory layer is READ-ONLY CONTEXT. It MUST NEVER:
  1. Override or influence deterministic NFPA 72 calculations
  2. Replace engineering judgment with stored patterns
  3. Automatically apply past decisions without PE review
  4. Bypass verification gates or safety checks

  Memory provides CONTEXT, not COMMANDS. All engineering calculations
  remain deterministic per agent.md priority hierarchy:
    Safety > Correctness > Verification > Reliability > Determinism

ARCHITECTURE (V76 — OpenAI Primary):
  Uses Mem0 (mem0ai) with:
  - OpenAI gpt-4o as LLM provider (PRIMARY — best engineering accuracy)
  - OpenAI text-embedding-3-small as embedder (1536 dimensions)
  - Qdrant (embedded) as vector store — persistent path, NOT /tmp/
  - SQLite history DB — persistent path, NOT /tmp/
  - Custom instructions specialized for fire protection engineering
  - Multi-scoping: user_id (engineer), agent_id (fireai), run_id (project)
  - Fallback: Gemini 2.0 Flash + local embeddings (384d) if OpenAI unavailable

CRITICAL FIXES from V72:
  V76:
  1. OpenAI promoted to PRIMARY — better engineering accuracy than Gemini
  2. gpt-4o replaces gpt-4o-mini — more reliable for NFPA analysis
  3. Removed models.list() connectivity test — causes latency
  4. Consistent provider cascade with mem0_setup.py (OpenAI → Gemini → proxy)

  V72:
  1. Storage paths changed from /tmp/ to persistent data/ directory
  2. Embedding dimensions corrected to 1536 (matching text-embedding-3-small)
  3. Removed z-ai proxy — uses real OpenAI SDK
  4. API key sourced from environment variables properly
  5. Graceful degradation with clear error messages

LIFE-SAFETY DESIGN PRINCIPLE:
  - Memory is ADVISORY, not AUTHORITATIVE
  - Every memory retrieval is tagged with source="memory" to distinguish
    from authoritative calculation results (source="nfpa_engine")
  - Memory failures NEVER block calculations — fallback is empty context
  - All memory operations are logged for audit trail

Reference: agent.md Rules 1-21, Priority Hierarchy, VERIFICATION GATES
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Persistent Storage Paths ────────────────────────────────────────────────
# V72 FIX: All paths are persistent (NOT /tmp/ which clears on reboot)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MEM0_QDRANT_PATH = DATA_DIR / "mem0_qdrant_service"
MEM0_HISTORY_DB = DATA_DIR / "mem0_history_service.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MEM0_QDRANT_PATH.mkdir(parents=True, exist_ok=True)


# ── Configuration ──────────────────────────────────────────────────────────────

FIREAI_CUSTOM_INSTRUCTIONS = """
Focus on extracting and storing fire protection engineering information:
- Standard references and section numbers (NFPA 72, NFPA 13, NFPA 70/NEC, BS 5839, IEC 60079, EN 54)
- Building type, occupancy classification, and hazard levels
- Detector types, locations, spacing, and coverage areas
- Calculation methods, inputs, and results (fire load, hydraulic, egress, voltage drop)
- Equipment specifications (manufacturer, model, ratings, EPL)
- Engineering decisions and their rationale/constraints
- Client preferences and project-specific requirements
- Regulatory compliance requirements and jurisdiction
- Design methodology and software tools used
- Past project patterns that could inform future designs
- Room types and their detector placement patterns
- Cable routing preferences and conduit fill practices
- Seismic design category and bracing requirements
- Environmental conditions affecting detector selection (dust, humidity, temperature)
"""


class MemoryScope(str, Enum):
    """Memory scoping levels — determines the context boundary of stored memories."""

    USER = "user"          # Engineer's personal preferences and patterns
    PROJECT = "project"    # Project-specific context (run_id)
    AGENT = "agent"        # FireAI agent's learned procedures
    GLOBAL = "global"      # Shared knowledge across all users/projects


class MemoryCategory(str, Enum):
    """Categories of memories for structured storage and retrieval."""

    LAYOUT = "layout"                    # Building layouts and detector placements
    PREFERENCE = "preference"            # User preferences (standards, manufacturers)
    CALCULATION = "calculation"          # Calculation patterns and results
    DEVICE_MAPPING = "device_mapping"    # Repeated device selections
    DECISION = "decision"                # Engineering decisions with rationale
    STANDARD = "standard"                # Standard references and interpretations
    PROJECT_CONTEXT = "project_context"  # Project-specific context
    PROCEDURE = "procedure"              # Learned procedures and workflows


class MemoryAddRequest(BaseModel):
    """Request model for adding a memory."""

    messages: Any = Field(
        ...,
        description="Message(s) to extract memories from. Can be a string or list of message dicts."
    )
    user_id: Optional[str] = Field(None, description="Engineer/user identifier")
    agent_id: Optional[str] = Field(None, description="FireAI agent identifier")
    run_id: Optional[str] = Field(None, description="Project/run identifier")
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata (category, project_type, standard, etc.)"
    )
    memory_type: Optional[str] = Field(
        None,
        description="Memory type: semantic_memory, episodic_memory, procedural_memory"
    )


class MemorySearchRequest(BaseModel):
    """Request model for searching memories."""

    query: str = Field(..., description="Search query")
    user_id: Optional[str] = Field(None, description="Filter by engineer/user")
    agent_id: Optional[str] = Field(None, description="Filter by agent")
    run_id: Optional[str] = Field(None, description="Filter by project/run")
    top_k: int = Field(10, ge=1, le=50, description="Maximum results to return")
    threshold: float = Field(0.3, ge=0.0, le=1.0, description="Minimum similarity threshold")


class MemoryResult(BaseModel):
    """Single memory result."""

    id: str
    memory: str
    score: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    source: str = "memory"  # Always "memory" to distinguish from nfpa_engine results


class MemorySearchResponse(BaseModel):
    """Response model for memory search."""

    results: List[MemoryResult]
    query: str
    total: int
    source: str = "memory"
    disclaimer: str = (
        "Memory results are ADVISORY CONTEXT only. They MUST NOT replace "
        "deterministic NFPA 72 calculations or engineering judgment. All "
        "designs require PE review per NFPA 72."
    )


class MemoryServiceStatus(BaseModel):
    """Status of the memory service."""

    initialized: bool = False
    provider: str = "unknown"
    vector_store: str = "unknown"
    llm_provider: str = "unknown"
    embedder_provider: str = "unknown"
    embedding_dims: int = 0
    error: Optional[str] = None


# ── Memory Service ─────────────────────────────────────────────────────────────

class MemoryService:
    """FireAI Memory Service — Long-term memory layer for engineering context.

    This service wraps Mem0 (mem0ai) and provides:
    - Structured memory storage scoped by user/project/agent
    - Hybrid search (semantic + BM25 + entity boosting)
    - Fire-engineering-specific custom instructions
    - Fail-safe: memory failures NEVER block calculations
    - Full audit logging for traceability

    SAFETY CONSTRAINT:
      Memory is ADVISORY. It provides context that engineers and the
      FireAI agent can use to inform decisions, but it MUST NEVER
      override deterministic calculations or bypass verification gates.
    """

    def __init__(self):
        self._memory = None
        self._status = MemoryServiceStatus()
        self._config = None
        self._initialize()

    def _initialize(self):
        """Initialize the Mem0 memory instance with FireAI-specific configuration.

        V76 Configuration (OpenAI Primary):
        - LLM: OpenAI gpt-4o (PRIMARY — best engineering accuracy)
        - Embedder: OpenAI text-embedding-3-small (1536 dimensions)
        - Vector Store: Qdrant embedded (persistent path)
        - History DB: SQLite (persistent path)
        - Fallback: Gemini 2.0 Flash + HuggingFace local embeddings (384d)

        Falls back gracefully if API key unavailable.
        """
        try:
            # V76: Try OpenAI first (best engineering accuracy), then Gemini
            openai_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("FIREAI_OPENAI_API_KEY")
            gemini_api_key = os.getenv("GEMINI_API_KEY")

            # ── Strategy 1: OpenAI (PRIMARY — best engineering accuracy) ──
            if openai_api_key:
                logger.info("MemoryService: Configuring OpenAI gpt-4o + text-embedding-3-small")

                embedder_config = {
                    "provider": "openai",
                    "config": {
                        "model": "text-embedding-3-small",
                        "api_key": openai_api_key,
                    },
                }

                self._config = {
                    "version": "v1.1",
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": "gpt-4o",
                            "api_key": openai_api_key,
                            "temperature": 0.1,
                            "max_tokens": 2000,
                        },
                    },
                    "embedder": embedder_config,
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "path": str(MEM0_QDRANT_PATH),
                            "collection_name": "fireai_memories",
                            "embedding_model_dims": 1536,
                            "on_disk": True,
                        },
                    },
                    "history_db_path": str(MEM0_HISTORY_DB),
                    "custom_instructions": FIREAI_CUSTOM_INSTRUCTIONS,
                }

                # Initialize Mem0 with OpenAI
                try:
                    from mem0 import Memory
                    self._memory = Memory.from_config(self._config)

                    self._status = MemoryServiceStatus(
                        initialized=True,
                        provider="mem0",
                        vector_store="qdrant",
                        llm_provider="openai",
                        embedder_provider="openai",
                        embedding_dims=1536,
                    )

                    logger.info(
                        "MemoryService initialized: provider=mem0, "
                        "llm=openai/gpt-4o, "
                        "embedder=openai/text-embedding-3-small, dims=1536"
                    )
                    return  # Success — exit early
                except Exception as e:
                    logger.warning(
                        f"OpenAI Mem0 init failed ({type(e).__name__}): {e}. "
                        "Falling back to Gemini."
                    )

            # ── Strategy 2: Gemini (FALLBACK — no region blocking) ──
            if gemini_api_key:
                # Gemini LLM + HuggingFace local embeddings
                logger.info("MemoryService: Falling back to Gemini LLM + HuggingFace embeddings")

                embedder_config = {
                    "provider": "huggingface",
                    "config": {
                        "model": "sentence-transformers/all-MiniLM-L6-v2",
                    },
                }

                self._config = {
                    "version": "v1.1",
                    "llm": {
                        "provider": "gemini",
                        "config": {
                            "model": "gemini-2.0-flash",
                            "api_key": gemini_api_key,
                            "temperature": 0.1,
                            "max_tokens": 2000,
                        },
                    },
                    "embedder": embedder_config,
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "path": str(MEM0_QDRANT_PATH),
                            "collection_name": "fireai_memories_gemini",
                            "embedding_model_dims": 384,
                            "on_disk": True,
                        },
                    },
                    "history_db_path": str(MEM0_HISTORY_DB),
                    "custom_instructions": FIREAI_CUSTOM_INSTRUCTIONS,
                }

                try:
                    from mem0 import Memory
                    self._memory = Memory.from_config(self._config)

                    self._status = MemoryServiceStatus(
                        initialized=True,
                        provider="mem0",
                        vector_store="qdrant",
                        llm_provider="gemini",
                        embedder_provider="huggingface",
                        embedding_dims=384,
                    )

                    logger.info(
                        "MemoryService initialized (fallback): provider=mem0, "
                        "llm=gemini/gemini-2.0-flash, "
                        "embedder=huggingface/all-MiniLM-L6-v2, dims=384"
                    )
                    return  # Success — exit early
                except Exception as e:
                    logger.warning(
                        f"Gemini Mem0 init also failed ({type(e).__name__}): {e}. "
                        "MemoryService will not initialize."
                    )

            # ── No provider available ──
            logger.warning(
                "No API keys available or all providers failed. "
                "MemoryService will not initialize. "
                "Calculations proceed normally without memory context."
            )
            self._status = MemoryServiceStatus(
                initialized=False,
                error="No API key configured or all providers failed (OPENAI_API_KEY, GEMINI_API_KEY)",
            )
            return

        except Exception as e:
            self._status = MemoryServiceStatus(
                initialized=False,
                error=str(e),
            )
            # WARNING, not ERROR: Memory failure is expected in environments
            # without API keys. This is NOT a safety risk — calculations
            # proceed normally without memory context.
            logger.warning(
                f"MemoryService initialization failed: {e}. "
                "Calculations proceed normally without memory context."
            )

    @property
    def status(self) -> MemoryServiceStatus:
        """Get current service status."""
        return self._status

    @property
    def is_initialized(self) -> bool:
        """Check if the memory service is ready."""
        return self._status.initialized and self._memory is not None

    def add_memory(self, request: MemoryAddRequest) -> Dict[str, Any]:
        """Add a memory to the FireAI memory store.

        SAFETY: Memory addition is non-blocking. Failure NEVER prevents calculations.
        """
        if not self.is_initialized:
            logger.warning(
                "MemoryService not initialized — memory add skipped. "
                "Calculations proceed normally without memory context."
            )
            return {
                "success": False,
                "error": "Memory service not initialized",
                "source": "memory",
            }

        try:
            metadata = request.metadata or {}
            metadata["source"] = "fireai"
            metadata["added_at"] = datetime.now(timezone.utc).isoformat()
            if request.memory_type:
                metadata["memory_type"] = request.memory_type

            result = self._memory.add(
                messages=request.messages,
                user_id=request.user_id,
                agent_id=request.agent_id,
                run_id=request.run_id,
                metadata=metadata,
            )

            logger.info(
                f"Memory added: user={request.user_id}, "
                f"project={request.run_id}"
            )

            return {
                "success": True,
                "result": result,
                "source": "memory",
            }

        except Exception as e:
            logger.error("Memory add failed: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "source": "memory",
            }

    def search_memories(self, request: MemorySearchRequest) -> MemorySearchResponse:
        """Search memories using hybrid search (semantic + BM25 + entity boosting).

        SAFETY: Results are ADVISORY CONTEXT only.
        Memory search failure NEVER blocks calculations — returns empty results.
        """
        if not self.is_initialized:
            logger.warning(
                "MemoryService not initialized — returning empty results. "
                "Calculations proceed normally without memory context."
            )
            return MemorySearchResponse(
                results=[],
                query=request.query,
                total=0,
                source="memory",
            )

        try:
            raw_results = self._memory.search(
                query=request.query,
                user_id=request.user_id,
                agent_id=request.agent_id,
                run_id=request.run_id,
                top_k=request.top_k,
                threshold=request.threshold,
            )

            results = []
            if isinstance(raw_results, dict) and "results" in raw_results:
                items = raw_results["results"]
            elif isinstance(raw_results, list):
                items = raw_results
            else:
                items = []

            for item in items:
                if isinstance(item, dict):
                    results.append(MemoryResult(
                        id=item.get("id", "unknown"),
                        memory=item.get("memory", ""),
                        score=item.get("score"),
                        metadata=item.get("metadata"),
                        created_at=item.get("created_at"),
                        updated_at=item.get("updated_at"),
                        source="memory",
                    ))
                else:
                    results.append(MemoryResult(
                        id=getattr(item, "id", "unknown"),
                        memory=getattr(item, "memory", ""),
                        score=getattr(item, "score", None),
                        metadata=getattr(item, "metadata", None),
                        created_at=getattr(item, "created_at", None),
                        updated_at=getattr(item, "updated_at", None),
                        source="memory",
                    ))

            logger.info(
                f"Memory search: query='{request.query[:50]}...', "
                f"results={len(results)}"
            )

            return MemorySearchResponse(
                results=results,
                query=request.query,
                total=len(results),
                source="memory",
            )

        except Exception as e:
            logger.error("Memory search failed: %s", e, exc_info=True)
            return MemorySearchResponse(
                results=[],
                query=request.query,
                total=0,
                source="memory_error",
            )

    def get_all_memories(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get all memories for a given scope.

        V113 FIX: mem0 v2 API compatibility.
        In mem0 v1, get_all() accepted user_id/agent_id/run_id kwargs.
        In mem0 v2.0.4+, get_all() rejects those kwargs with ValueError.
        We now detect the API version and call appropriately:
          - If the method signature accepts kwargs → pass them (v1)
          - If it raises ValueError → retry without kwargs (v2)
          - For v2, we filter results in Python after retrieval
        This is a ROOT-CAUSE fix per agent.md Rule 17 — the previous
        code would silently fail on every get_all() call with mem0 v2,
        returning empty results and hiding the ValueError in the generic
        except clause. In a safety-critical system, silent data loss
        is unacceptable.
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Memory service not initialized",
                "results": [],
                "source": "memory",
            }

        try:
            # Strategy 1: Try v1 API (passes user_id/agent_id/run_id)
            # This is the original interface that works with mem0 < 2.0
            results = self._memory.get_all(
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
            )

            return {
                "success": True,
                "results": results if isinstance(results, list) else [],
                "total": len(results) if isinstance(results, list) else 0,
                "source": "memory",
            }

        except (ValueError, TypeError) as api_error:
            # Strategy 2: mem0 v2 API — get_all() doesn't accept these kwargs.
            # The v2 API returns all memories and we filter in Python.
            # ValueError: "get_all() got an unexpected keyword argument 'user_id'"
            # TypeError: similar signature mismatch
            logger.info(
                f"mem0 get_all() v1 API failed ({type(api_error).__name__}: {api_error}). "
                f"Trying v2 API (no kwargs) with Python-side filtering."
            )
            try:
                # v2 API: call without filtering kwargs
                results = self._memory.get_all()

                # Normalize results format
                if isinstance(results, dict) and "results" in results:
                    items = results["results"]
                elif isinstance(results, list):
                    items = results
                else:
                    items = []

                # Python-side filtering for v2 API
                if user_id or agent_id or run_id:
                    filtered = []
                    for item in items:
                        # v2 stores metadata differently — check both
                        # dict format and object format
                        if isinstance(item, dict):
                            meta = item.get("metadata", {})
                            item_user = meta.get("user_id") if isinstance(meta, dict) else None
                            item_agent = meta.get("agent_id") if isinstance(meta, dict) else None
                            item_run = meta.get("run_id") if isinstance(meta, dict) else None
                        else:
                            meta = getattr(item, "metadata", {}) or {}
                            item_user = meta.get("user_id")
                            item_agent = meta.get("agent_id")
                            item_run = meta.get("run_id")

                        # Match: if a filter is specified, the item must match it
                        match = True
                        if user_id and item_user != user_id:
                            match = False
                        if agent_id and item_agent != agent_id:
                            match = False
                        if run_id and item_run != run_id:
                            match = False
                        if match:
                            filtered.append(item)
                    items = filtered

                return {
                    "success": True,
                    "results": items,
                    "total": len(items),
                    "source": "memory",
                    "api_version": "v2",
                }

            except Exception as e2:
                logger.error(
                    f"Memory get_all failed with BOTH v1 and v2 APIs: {e2}",
                    exc_info=True,
                )
                return {
                    "success": False,
                    "error": f"v1 API error: {api_error}; v2 API error: {e2}",
                    "results": [],
                    "source": "memory_error",
                }

        except Exception as e:
            logger.error("Memory get_all failed: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "source": "memory_error",
            }

    def delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """Delete a specific memory by ID."""
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Memory service not initialized",
                "source": "memory",
            }

        try:
            self._memory.delete(memory_id=memory_id)
            logger.info("Memory deleted: id=%s", memory_id)
            return {
                "success": True,
                "memory_id": memory_id,
                "source": "memory",
            }

        except Exception as e:
            logger.error("Memory delete failed: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "source": "memory_error",
            }

    def get_memory_history(self, memory_id: str) -> Dict[str, Any]:
        """Get the history of a specific memory (all changes over time).

        Supports agent.md's traceability requirement (Priority 7).
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Memory service not initialized",
                "source": "memory",
            }

        try:
            history = self._memory.history(memory_id=memory_id)
            return {
                "success": True,
                "memory_id": memory_id,
                "history": history if isinstance(history, list) else [],
                "source": "memory",
            }

        except Exception as e:
            logger.error("Memory history failed: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "source": "memory_error",
            }

    async def close(self):
        """Close the memory service and release resources. Per agent.md Rule 8."""
        logger.info("MemoryService closing...")
        self._memory = None
        self._status = MemoryServiceStatus(initialized=False)
        logger.info("MemoryService closed")


# ── Singleton Management ──────────────────────────────────────────────────────

_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """Get or create the singleton MemoryService instance."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


async def close_memory_service():
    """Close the singleton MemoryService instance."""
    global _memory_service
    if _memory_service is not None:
        await _memory_service.close()
        _memory_service = None
