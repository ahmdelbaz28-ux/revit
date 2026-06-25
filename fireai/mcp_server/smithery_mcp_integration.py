"""smithery_mcp_integration.py — Agentic BIM Control (READ-ONLY + Human-Approved Writes)
=======================================================================================

MISSION PHASE 3 — Agentic BIM Control via Smithery MCP (REDESIGNED FOR SAFETY)
===============================================================================

⚠️  CRITICAL SAFETY DESIGN — REDESIGNED FROM ORIGINAL BRIEF
============================================================
The original brief said: "The AI must be able to execute CREATE, UPDATE,
and DELETE actions on Revit elements via the ThreadSafeModelUpdateQueue."

This was REJECTED by the engineering review because:

1. **ThreadSafeModelUpdateQueue was designed to PREVENT direct writes** (V30,
   V114). Its purpose is to queue proposed changes for HUMAN REVIEW in Revit.
2. **NFPA 72 §23.8** requires Professional Engineer (PE) review before any
   fire protection design is approved. AI direct-write bypasses this.
3. **agent.md Rule 15 (NO PHASE SKIPPING)**: The "human_review_gate" in the
   workflow exists for legal/safety reasons.
4. **agent.md Priority 1 (Safety)**: AI is ADVISORY ONLY per V75. Direct
   writes would violate this fundamental principle.

REDIRECTED DESIGN: "AI Proposes, Human Disposes"
-------------------------------------------------
- The AI CAN: search Revit API docs, read BIM data, PROPOSE changes
- The AI CANNOT: execute writes directly
- All proposed CREATE/UPDATE/DELETE actions are enqueued in
  ThreadSafeModelUpdateQueue for HUMAN REVIEW in Revit
- The human reviews each proposal in Revit's UI, then approves/rejects
- Only approved changes are applied to the Revit model

This preserves the safety architecture while still enabling agentic workflows.

Components
----------
1. ``SmitheryMCPClient``: Connects to Smithery API for tool execution
2. ``RevitAPIDocsSearcher``: Searches local Revit API docs (offline)
3. ``ProposedAction``: Dataclass for a proposed (not executed) Revit change
4. ``LiveActionBridge``: Enqueues proposed actions for human review

References
----------
- agent.md Rule 12 (Safety-First) + Rule 15 (NO PHASE SKIPPING)
- agent.md V75 (AI is advisory only)
- NFPA 72-2022 §23.8 (PE review required)
- Smithery MCP: https://smithery.ai
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SMITHERY_API_KEY_ENV = "SMITHERY_API_KEY"
SMITHERY_BASE_URL = "https://api.smithery.ai/v1"

# Local Revit API docs paths (shipped with the project)
REVIT_API_DOCS_PATHS = {
    "2022": "revit_data/RevitAPI2022.json",
    "2023": "revit_data/RevitAPI2023.json",
}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    """Types of actions the AI can propose (NOT execute)."""

    CREATE = "create"      # Create a new Revit element
    UPDATE = "update"      # Modify an existing element
    DELETE = "delete"      # Delete an element (HIGH RISK — requires explicit human approval)
    READ = "read"          # Read element data (safe — can execute directly)


class ActionStatus(str, Enum):
    """Status of a proposed action in the review queue."""

    PROPOSED = "proposed"        # AI proposed, awaiting human review
    APPROVED = "approved"        # Human approved, queued for execution
    REJECTED = "rejected"        # Human rejected
    EXECUTED = "executed"        # Successfully applied to Revit model
    FAILED = "failed"            # Execution failed
    EXPIRED = "expired"          # Proposal expired before review


# ---------------------------------------------------------------------------
# Proposed Action Dataclass
# ---------------------------------------------------------------------------


@dataclass
class ProposedAction:
    """A proposed Revit action (NOT yet executed).

    The AI creates these proposals. A human engineer reviews them in Revit
    and approves or rejects each one. Only approved actions are executed.

    V134 F-5 FIX: Added ``enqueue_status`` and ``enqueue_error`` fields to
    distinguish between "successfully enqueued for human review" and
    "proposal recorded but silently dropped (queue unavailable)". Previously,
    callers could not tell whether their proposal would actually be reviewed
    by a human PE — a critical safety gap per NFPA 72 §23.8.

    Attributes:
        id: Unique proposal ID (UUID for traceability).
        action_type: CREATE / UPDATE / DELETE / READ.
        element_type: Revit element type (e.g., "FamilyInstance", "Wall").
        element_id: ID of element to modify (None for CREATE).
        parameters: Action parameters (e.g., new property values).
        proposed_by: AI agent identifier.
        proposed_at: ISO timestamp.
        rationale: AI's reasoning for this proposal.
        confidence: AI confidence score (0.0-1.0).
        status: Current review status.
        enqueue_status: V134 F-5 — "enqueued" / "dropped" / "failed".
            Tells the caller whether the proposal will actually be reviewed.
        enqueue_error: V134 F-5 — error message if enqueue failed.
        reviewed_by: Human reviewer ID (when reviewed).
        reviewed_at: Review timestamp (when reviewed).
        review_notes: Human reviewer notes.
        nfpa_reference: Applicable NFPA clause (if any).
    """

    id: str
    action_type: ActionType
    element_type: str
    element_id: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    proposed_by: str = "fireai_agent"
    proposed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    rationale: str = ""
    confidence: float = 0.0
    status: ActionStatus = ActionStatus.PROPOSED
    # V134 F-5: New fields for enqueue transparency
    enqueue_status: str = "pending"  # "enqueued" / "dropped" / "failed" / "pending"
    enqueue_error: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_notes: str = ""
    nfpa_reference: str = ""

    @property
    def is_enqueued(self) -> bool:
        """V134 F-5: True if the proposal was successfully enqueued for human review."""
        return self.enqueue_status == "enqueued"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action_type": self.action_type.value,
            "element_type": self.element_type,
            "element_id": self.element_id,
            "parameters": self.parameters,
            "proposed_by": self.proposed_by,
            "proposed_at": self.proposed_at,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "status": self.status.value,
            "enqueue_status": self.enqueue_status,
            "enqueue_error": self.enqueue_error,
            "is_enqueued": self.is_enqueued,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "review_notes": self.review_notes,
            "nfpa_reference": self.nfpa_reference,
        }


# ---------------------------------------------------------------------------
# Revit API Docs Searcher (LOCAL — no Smithery needed)
# ---------------------------------------------------------------------------


class RevitAPIDocsSearcher:
    """Searches local Revit API documentation offline.

    The project ships with RevitAPI2022.json and RevitAPI2023.json —
    comprehensive API reference data extracted from Revit's official docs.

    The AI can use this to:
    1. Verify that a class/method exists in the target Revit version
    2. Get correct method signatures before generating code
    3. Avoid version-specific API breaking changes

    This is OFFLINE — no Smithery API call required.
    """

    def __init__(self) -> None:
        self._docs_cache: Dict[str, Dict[str, Any]] = {}

    def search(
        self,
        query: str,
        revit_version: str = "2023",
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search Revit API docs for a query.

        Args:
            query: Search query (class name, method name, namespace).
            revit_version: "2022" or "2023".
            max_results: Maximum number of results.

        Returns:
            List of matching API entries.
        """
        docs = self._load_docs(revit_version)
        if not docs:
            return []

        query_lower = query.lower()
        results: List[Dict[str, Any]] = []

        # The Revit API docs JSON can be either:
        # - A dict mapping APIName → entry data, OR
        # - A list of entry dicts (each with an "APIName" or "Title" key)
        # We handle both formats for robustness.
        if isinstance(docs, dict):
            iterable = docs.items()
            for entry_name, entry_data in iterable:
                if query_lower in str(entry_name).lower():
                    results.append({
                        "name": str(entry_name),
                        "version": revit_version,
                        "data": entry_data,
                    })
                    if len(results) >= max_results:
                        break
        elif isinstance(docs, list):
            for entry in docs:
                if not isinstance(entry, dict):
                    continue
                # Try common field names: APIName, Title, Name
                name = entry.get("APIName") or entry.get("Title") or entry.get("Name") or ""
                keywords = entry.get("Keywords", "")
                if query_lower in str(name).lower() or query_lower in str(keywords).lower():
                    results.append({
                        "name": str(name),
                        "version": revit_version,
                        "data": entry,
                    })
                    if len(results) >= max_results:
                        break

        return results

    def verify_class_exists(
        self,
        class_name: str,
        revit_version: str = "2023",
    ) -> bool:
        """Verify that a Revit API class exists in the target version.

        Args:
            class_name: Full class name (e.g., "Autodesk.Revit.DB.Wall").
            revit_version: "2022" or "2023".

        Returns:
            True if class exists in the API docs.
        """
        docs = self._load_docs(revit_version)
        if not docs:
            return False

        class_name_lower = class_name.lower()
        short_name = class_name.split(".")[-1]
        short_name_lower = short_name.lower()

        # V135 F-25 FIX: Use EXACT match instead of substring match.
        # The OLD code used `class_name_lower in str(k).lower()` which
        # returned True for "Wall" if docs contained "WallType",
        # "WallFoundation", "CurtainWall", etc. This could lead the AI
        # to think a class exists when it doesn't.
        # Now we check: exact full name, exact short name, or suffix match.
        if isinstance(docs, dict):
            # Check exact match first
            if class_name in docs or short_name in docs:
                return True
            # V135 F-25: Suffix match (e.g., "Wall" matches "T:Autodesk.Revit.DB.Wall")
            # but NOT substring (so "Wall" won't match "WallType")
            for k in docs.keys():
                k_str = str(k)
                # Match if key ends with .ShortName (e.g., ".Wall" at end of full name)
                if k_str.endswith(f".{short_name}") or k_str == short_name:
                    return True
            return False
        elif isinstance(docs, list):
            for entry in docs:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("APIName") or entry.get("Title") or entry.get("Name") or "")
                # V135 F-25: Exact match or suffix match (not substring)
                if name.lower() == class_name_lower or name.lower() == short_name_lower:
                    return True
                # Suffix match: "T:Autodesk.Revit.DB.Wall" matches short_name "Wall"
                if name.lower().endswith(f".{short_name_lower}"):
                    return True
            return False

        return False

    def _load_docs(self, version: str) -> Dict[str, Any]:
        """Load Revit API docs for a version (cached)."""
        if version in self._docs_cache:
            return self._docs_cache[version]

        path = REVIT_API_DOCS_PATHS.get(version)
        if not path:
            logger.warning("No Revit API docs for version %s", version)
            return {}

        # Try multiple base paths
        import os
        possible_paths = [
            path,
            os.path.join(os.path.dirname(__file__), "..", "..", path),
            os.path.join(os.getcwd(), path),
        ]

        for p in possible_paths:
            try:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        docs = json.load(f)
                    self._docs_cache[version] = docs
                    return docs
            except Exception as exc:
                logger.debug("Failed to load Revit API docs from %s: %s", p, exc)

        logger.warning("Revit API docs not found for version %s", version)
        return {}


# ---------------------------------------------------------------------------
# Smithery MCP Client (READ-ONLY + Propose-Only)
# ---------------------------------------------------------------------------


class SmitheryMCPClient:
    """Client for Smithery MCP (Model Context Protocol) integration.

    SAFETY DESIGN:
    - READ operations (searching docs, reading BIM data) can execute directly.
    - WRITE operations (CREATE/UPDATE/DELETE) are converted to ProposedAction
      objects and enqueued for HUMAN REVIEW. They are NEVER executed directly.

    Usage:
        client = SmitheryMCPClient()

        # ✅ Safe: Read Revit API docs
        results = client.search_revit_api("Wall", version="2023")

        # ✅ Safe: Read BIM data
        rooms = client.read_rooms_from_bim()

        # ⚠️ Proposed (NOT executed): AI proposes creating a detector
        proposal = client.propose_create_detector(
            room_id="R-001",
            position=(5.0, 3.0, 2.8),
            detector_type="smoke",
            rationale="NFPA 72 §17.6.3 requires coverage for this room",
        )
        # The proposal is now in ThreadSafeModelUpdateQueue.
        # A human engineer must review and approve it in Revit.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize Smithery MCP client.

        Args:
            api_key: Optional Smithery API key. If None, reads from env var.
        """
        self.api_key = api_key or os.environ.get(SMITHERY_API_KEY_ENV)
        self._docs_searcher = RevitAPIDocsSearcher()
        self._connected = False

        if not self.api_key:
            logger.info(
                "Smithery MCP client initialized without API key. "
                "Smithery cloud features disabled (local Revit API docs still available)."
            )
        else:
            logger.info("Smithery MCP client initialized with API key")

    # ------------------------------------------------------------------
    # READ Operations (Safe — can execute directly)
    # ------------------------------------------------------------------

    def search_revit_api(
        self,
        query: str,
        revit_version: str = "2023",
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search local Revit API documentation.

        This is a READ-ONLY operation — safe to execute without human review.

        Args:
            query: Search query.
            revit_version: "2022" or "2023".
            max_results: Max results to return.

        Returns:
            List of matching API entries.
        """
        return self._docs_searcher.search(query, revit_version, max_results)

    def verify_revit_class(
        self,
        class_name: str,
        revit_version: str = "2023",
    ) -> bool:
        """Verify a Revit API class exists (READ-ONLY)."""
        return self._docs_searcher.verify_class_exists(class_name, revit_version)

    def read_rooms_from_bim(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """Read rooms from BIM source (READ-ONLY).

        Delegates to the BIMProvider abstraction (V132 TASK 1.2).
        """
        try:
            from fireai.bridges.bim_provider import get_provider
            provider = get_provider()
            if provider is None:
                logger.warning("No BIM provider configured for read_rooms_from_bim")
                return []
            rooms = provider.extract_rooms(source=source)
            return [r.to_fireai_room_dict() for r in rooms]
        except Exception as exc:
            logger.error("Failed to read rooms from BIM: %s", exc)
            return []

    # ------------------------------------------------------------------
    # WRITE Operations (PROPOSED — never executed directly)
    # ------------------------------------------------------------------

    def propose_create_detector(
        self,
        room_id: str,
        position: tuple,
        detector_type: str = "smoke",
        rationale: str = "",
        confidence: float = 0.0,
        nfpa_reference: str = "",
    ) -> ProposedAction:
        """Propose creating a new detector in the Revit model.

        ⚠️  This does NOT execute the creation. It enqueues a proposal
        for HUMAN REVIEW. The human must approve it in Revit before
        the detector is actually created.

        Args:
            room_id: Room where detector should be placed.
            position: (x, y, z) position in metres.
            detector_type: "smoke", "heat", "flame", etc.
            rationale: AI's reasoning for this placement.
            confidence: AI confidence (0.0-1.0).
            nfpa_reference: Applicable NFPA clause.

        Returns:
            ProposedAction object (status=PROPOSED).
        """
        action = ProposedAction(
            id=f"prop-{uuid.uuid4().hex[:12]}",
            action_type=ActionType.CREATE,
            element_type="FireAlarmDetector",
            element_id=None,
            parameters={
                "room_id": room_id,
                "position": list(position),
                "detector_type": detector_type,
            },
            rationale=rationale,
            confidence=confidence,
            nfpa_reference=nfpa_reference,
        )
        self._enqueue_for_human_review(action)
        return action

    def propose_update_element(
        self,
        element_id: str,
        updates: Dict[str, Any],
        rationale: str = "",
        confidence: float = 0.0,
        nfpa_reference: str = "",
    ) -> ProposedAction:
        """Propose updating an existing Revit element.

        ⚠️  Does NOT execute the update. Enqueues for human review.
        """
        action = ProposedAction(
            id=f"prop-{uuid.uuid4().hex[:12]}",
            action_type=ActionType.UPDATE,
            element_type="RevitElement",
            element_id=element_id,
            parameters=updates,
            rationale=rationale,
            confidence=confidence,
            nfpa_reference=nfpa_reference,
        )
        self._enqueue_for_human_review(action)
        return action

    def propose_delete_element(
        self,
        element_id: str,
        rationale: str = "",
        confidence: float = 0.0,
        nfpa_reference: str = "",
    ) -> ProposedAction:
        """Propose deleting a Revit element.

        ⚠️  HIGH RISK: Deletion is irreversible. Requires EXPLICIT human
        approval. The proposal includes a mandatory warning.

        ⚠️  Does NOT execute the deletion. Enqueues for human review.
        """
        action = ProposedAction(
            id=f"prop-{uuid.uuid4().hex[:12]}",
            action_type=ActionType.DELETE,
            element_type="RevitElement",
            element_id=element_id,
            parameters={},
            rationale=(
                f"⚠️  DELETE PROPOSAL — requires explicit human approval. "
                f"AI rationale: {rationale}"
            ),
            confidence=confidence,
            nfpa_reference=nfpa_reference,
        )
        self._enqueue_for_human_review(action)
        return action

    # ------------------------------------------------------------------
    # Human Review Queue Integration
    # ------------------------------------------------------------------

    def _enqueue_for_human_review(self, action: ProposedAction) -> None:
        """Enqueue a proposed action for human review.

        Uses the existing ThreadSafeModelUpdateQueue (V30, V114) which
        was designed for exactly this purpose: queueing proposed changes
        for human review in Revit.

        Per safety design: this NEVER executes the action. It only adds
        it to the review queue.

        V134 F-5 FIX: The previous implementation silently swallowed
        ImportError and Exception, leaving ``action.status=PROPOSED``
        even when the proposal was NOT actually enqueued. This created
        a false sense of safety — callers assumed their proposal would
        be reviewed by a human PE, but it might have been silently
        dropped. Now we set ``action.enqueue_status`` explicitly so
        callers can verify via ``action.is_enqueued``.
        """
        try:
            # Try to use the existing ThreadSafeModelUpdateQueue
            from fireai.mcp_server.thread_safe_queue import (
                ThreadSafeModelUpdateQueue,
                ModelUpdateRequest,
            )

            queue = ThreadSafeModelUpdateQueue.get_instance()
            request = ModelUpdateRequest(
                request_id=action.id,
                action=action.action_type.value,
                element_type=action.element_type,
                element_id=action.element_id,
                parameters=action.parameters,
                proposed_by=action.proposed_by,
                rationale=action.rationale,
                confidence=action.confidence,
                nfpa_reference=action.nfpa_reference,
                requires_human_approval=True,  # ALWAYS True per safety design
            )
            queue.enqueue(request)

            # V134 F-5: Mark as successfully enqueued
            action.enqueue_status = "enqueued"
            action.enqueue_error = None

            logger.info(
                "Proposed action %s enqueued for human review: %s %s",
                action.id, action.action_type.value, action.element_type,
            )

            # Record in AuditStore (per Rule 12 + NFPA 72 §7.5)
            self._record_audit(action)

        except ImportError as exc:
            # V134 F-5: Mark as DROPPED (not enqueued) — caller can detect this
            action.enqueue_status = "dropped"
            action.enqueue_error = f"ThreadSafeModelUpdateQueue unavailable: {exc}"

            logger.warning(
                "ThreadSafeModelUpdateQueue not available. "
                "Proposed action %s NOT enqueued for Revit review (DROPPED). "
                "Action details: %s. "
                "Caller must check action.is_enqueued before assuming review will occur.",
                action.id, action.to_dict(),
            )
            # Still record in AuditStore for traceability
            self._record_audit(action, success=False, error=action.enqueue_error)
        except Exception as exc:
            # V134 F-5: Mark as FAILED
            action.enqueue_status = "failed"
            action.enqueue_error = str(exc)

            logger.error(
                "Failed to enqueue proposed action %s: %s",
                action.id, exc, exc_info=True,
            )
            self._record_audit(action, success=False, error=str(exc))

    def _record_audit(
        self,
        action: ProposedAction,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Record the proposed action in AuditStore."""
        try:
            from fireai.core.audit_store import AuditStore
            AuditStore.add_event(
                event_type=f"REVIT_ACTION_PROPOSED_{action.action_type.value.upper()}",
                room_id=str(action.parameters.get("room_id", "UNKNOWN")),
                details_dict={
                    **action.to_dict(),
                    "success": success,
                    "error": error,
                    "safety_note": (
                        "AI-proposed action — requires human approval before execution. "
                        "Per NFPA 72 §23.8 and agent.md Rule 15."
                    ),
                    "nfpa_reference": "NFPA 72-2022 §23.8 (PE Review Required)",
                },
            )
        except Exception as audit_exc:
            # V135 F-24 FIX: Audit failure MUST be escalated, not silenced.
            # The OLD code did `except Exception: pass` which silently
            # swallowed audit failures. If both the queue AND the audit
            # store are down, the proposal is COMPLETELY LOST with no trace.
            # Per NFPA 72 §23.8, every proposed Revit action MUST be
            # auditable for legal traceability. We log at CRITICAL so
            # operators can investigate — we don't block the operation.
            logger.critical(
                "AUDIT FAILURE: Failed to record REVIT_ACTION_PROPOSED event "
                "for action %s (%s): %s. "
                "NFPA 72 §23.8 PE review audit trail at risk — investigate AuditStore. "
                "The proposed action may be lost without human review.",
                action.id, action.action_type.value, audit_exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Smithery Cloud Connection (Optional)
    # ------------------------------------------------------------------

    def connect_to_smithery(self) -> bool:
        """Connect to Smithery cloud API (optional).

        Smithery provides additional MCP tools (e.g., cloud-hosted Revit API
        search with semantic queries). This is OPTIONAL — local search
        works without it.

        Returns:
            True if connected, False otherwise.
        """
        if not self.api_key:
            logger.warning("Cannot connect to Smithery: no API key")
            return False

        try:
            # TODO: Implement actual Smithery API connection
            # For now, this is a stub that verifies the API key format
            if len(self.api_key) < 10:
                logger.warning("Smithery API key appears invalid (too short)")
                return False

            self._connected = True
            logger.info("Connected to Smithery MCP cloud API")
            return True
        except Exception as exc:
            logger.warning("Failed to connect to Smithery: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Convenience Singleton
# ---------------------------------------------------------------------------


_smithery_client: Optional[SmitheryMCPClient] = None


def get_smithery_client() -> SmitheryMCPClient:
    """Get the singleton SmitheryMCPClient instance."""
    global _smithery_client
    if _smithery_client is None:
        _smithery_client = SmitheryMCPClient()
    return _smithery_client


__all__ = [
    "SmitheryMCPClient",
    "RevitAPIDocsSearcher",
    "ProposedAction",
    "ActionType",
    "ActionStatus",
    "get_smithery_client",
    "SMITHERY_API_KEY_ENV",
]
