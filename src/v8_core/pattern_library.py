"""
pattern_library.py — Bounded Curated Library
=============================================
REPLACES the V7.6 `self_learner.py`, which auto-memorized engineer outputs
as "golden" patterns without any truth filter — the single most dangerous
component of V7.6.

DESIGN INVARIANTS (any violation is a CI failure):
  1. No auto-learn. There is no function that ingests a project into the
     library without an explicit FPE approval.
  2. The library is NEVER an authority. It surfaces *human-readable
     precedents*. The engine still recalculates from rules.
  3. Patterns are append-only. Rejected patterns are kept (with reason)
     for audit; they are never silently dropped.
  4. The retrieval index is by *explicit geometric features* — not by
     learned embeddings. Every retrieval is explainable.

Workflow:
    submit_for_review(pattern)  ->  pending queue
    FPE opens record, compares against source drawing
    approve(pattern_id, fpe_license, signature)  ->  immutable library
        OR
    reject(pattern_id, reason)  ->  audit log, not retrievable
    search_similar(features)  ->  approved patterns only
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PatternStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS patterns (
    pattern_id      TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    submitted_at    TEXT NOT NULL,
    submitted_by    TEXT NOT NULL,
    features_json   TEXT NOT NULL,
    solution_json   TEXT NOT NULL,
    source_drawing_hash TEXT NOT NULL,
    fpe_reviewer    TEXT,
    fpe_signature   TEXT,
    decided_at      TEXT,
    rejection_reason TEXT,
    notes           TEXT
);

CREATE TRIGGER IF NOT EXISTS patterns_no_resurrect
BEFORE UPDATE OF status ON patterns
WHEN OLD.status = 'rejected' AND NEW.status != 'rejected'
BEGIN
    SELECT RAISE(ABORT, 'rejected patterns are immutable — re-submit a new pattern instead');
END;
"""


@dataclass
class GeometricFeatures:
    """Explicit, explainable similarity features. NOT embeddings."""
    room_count: int
    total_area_m2: float
    aspect_ratio_bin: str          # e.g. "square" | "elongated" | "irregular"
    has_obstructions: bool
    occupancy_class: str           # NFPA 101 occupancy class
    ceiling_height_bin: str        # "<3m" | "3-6m" | "6-10m" | ">10m"

    def to_query_key(self) -> str:
        d = asdict(self)
        # Bin continuous values to make similarity tractable
        d["total_area_m2_bin"] = _area_bin(self.total_area_m2)
        del d["total_area_m2"]
        return json.dumps(d, sort_keys=True)


def _area_bin(a: float) -> str:
    for upper, label in [(50, "tiny"), (200, "small"), (500, "medium"),
                         (2000, "large"), (10000, "huge")]:
        if a <= upper:
            return label
    return "mega"


@dataclass
class Pattern:
    pattern_id: str
    status: PatternStatus
    submitted_at: str
    submitted_by: str
    features: GeometricFeatures
    solution: dict
    source_drawing_hash: str
    fpe_reviewer: Optional[str] = None
    fpe_signature: Optional[str] = None
    decided_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None

    def canonical_payload(self) -> bytes:
        d = {
            "pattern_id": self.pattern_id,
            "features": asdict(self.features),
            "solution": self.solution,
            "source_drawing_hash": self.source_drawing_hash,
            "submitted_by": self.submitted_by,
        }
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


class PatternLibrary:
    """Append-only library of FPE-approved precedents."""

    def __init__(self, db_path: str, fpe_key_provider=None):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._fpe_key_provider = fpe_key_provider or _default_key_provider

    # ---------------- submission ----------------

    def submit_for_review(self, features: GeometricFeatures, solution: dict,
                          source_drawing_hash: str, submitted_by: str,
                          notes: Optional[str] = None) -> str:
        pid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                """INSERT INTO patterns
                   (pattern_id, status, submitted_at, submitted_by,
                    features_json, solution_json, source_drawing_hash, notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (pid, PatternStatus.PENDING.value, now, submitted_by,
                 json.dumps(asdict(features), sort_keys=True),
                 json.dumps(solution, sort_keys=True),
                 source_drawing_hash, notes),
            )
        return pid

    # ---------------- review ----------------

    def list_pending(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT pattern_id, submitted_at, submitted_by, source_drawing_hash "
            "FROM patterns WHERE status = ? ORDER BY submitted_at",
            (PatternStatus.PENDING.value,),
        ).fetchall()
        return [{"pattern_id": r[0], "submitted_at": r[1],
                 "submitted_by": r[2], "source_drawing_hash": r[3]} for r in rows]

    def approve(self, pattern_id: str, fpe_license: str) -> None:
        """
        FPE approval. Signature is generated using the FPE's key (DEV) or
        Vault-resident key (prod). Pattern becomes immutably retrievable.
        """
        row = self._conn.execute(
            "SELECT status, features_json, solution_json, source_drawing_hash, "
            "submitted_by FROM patterns WHERE pattern_id = ?",
            (pattern_id,),
        ).fetchone()
        if not row:
            raise PatternLibraryError(f"No such pattern: {pattern_id}")
        if row[0] != PatternStatus.PENDING.value:
            raise PatternLibraryError(
                f"Pattern {pattern_id} is {row[0]}, cannot approve.")

        features = GeometricFeatures(**json.loads(row[1]))
        solution = json.loads(row[2])
        pattern = Pattern(
            pattern_id=pattern_id,
            status=PatternStatus.PENDING,
            submitted_at="",
            submitted_by=row[4],
            features=features,
            solution=solution,
            source_drawing_hash=row[3],
        )

        key = self._fpe_key_provider(fpe_license)
        if key is None:
            raise PatternLibraryError(f"No key for FPE {fpe_license}")
        sig = hmac.new(key, pattern.canonical_payload(), hashlib.sha256).hexdigest()

        with self._conn:
            self._conn.execute(
                """UPDATE patterns SET status = ?, fpe_reviewer = ?,
                   fpe_signature = ?, decided_at = ? WHERE pattern_id = ?""",
                (PatternStatus.APPROVED.value, fpe_license, sig,
                 datetime.now(timezone.utc).isoformat(), pattern_id),
            )

    def reject(self, pattern_id: str, fpe_license: str, reason: str) -> None:
        if not reason or len(reason) < 10:
            raise PatternLibraryError("Rejection reason must be ≥10 characters.")
        row = self._conn.execute(
            "SELECT status FROM patterns WHERE pattern_id = ?",
            (pattern_id,),
        ).fetchone()
        if not row:
            raise PatternLibraryError(f"No such pattern: {pattern_id}")
        if row[0] != PatternStatus.PENDING.value:
            raise PatternLibraryError(
                f"Pattern {pattern_id} is {row[0]}, cannot reject.")
        with self._conn:
            self._conn.execute(
                """UPDATE patterns SET status = ?, fpe_reviewer = ?,
                   rejection_reason = ?, decided_at = ? WHERE pattern_id = ?""",
                (PatternStatus.REJECTED.value, fpe_license, reason,
                 datetime.now(timezone.utc).isoformat(), pattern_id),
            )

    # ---------------- retrieval ----------------

    def search_similar(self, features: GeometricFeatures, limit: int = 5) -> list[dict]:
        """
        Returns ONLY approved patterns whose bucketed features match.
        This is *not* a recommender — it is a precedent-surface for the PE.
        """
        target_key = features.to_query_key()
        rows = self._conn.execute(
            """SELECT pattern_id, features_json, solution_json, fpe_reviewer,
                      source_drawing_hash, decided_at
               FROM patterns WHERE status = ? ORDER BY decided_at DESC""",
            (PatternStatus.APPROVED.value,),
        ).fetchall()
        matches = []
        for r in rows:
            feats = GeometricFeatures(**json.loads(r[1]))
            if feats.to_query_key() == target_key:
                matches.append({
                    "pattern_id": r[0],
                    "solution": json.loads(r[2]),
                    "approved_by_fpe": r[3],
                    "source_drawing_hash": r[4],
                    "decided_at": r[5],
                    "disclaimer": ("PRECEDENT ONLY — does not authorize re-use. "
                                   "PE must independently verify against current "
                                   "drawings and current code edition."),
                })
                if len(matches) >= limit:
                    break
        return matches

    def stats(self) -> dict:
        out = {}
        for status in PatternStatus:
            n = self._conn.execute(
                "SELECT COUNT(*) FROM patterns WHERE status = ?",
                (status.value,),
            ).fetchone()[0]
            out[status.value] = n
        return out


class PatternLibraryError(Exception):
    pass


def _default_key_provider(license_no: str):
    env = os.environ.get(f"FIRECALC_FPE_KEY_{license_no}")
    if env:
        return env.encode("utf-8")
    # DEV ONLY
    if license_no == "FPE-DEV-0001":
        return hashlib.sha256(b"DEV_ONLY_NOT_FOR_PRODUCTION_0001").digest()
    return None


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path
    db = "/tmp/firecalc_patternlib_selftest.db"
    Path(db).unlink(missing_ok=True)
    lib = PatternLibrary(db)

    feats = GeometricFeatures(
        room_count=4, total_area_m2=120.0, aspect_ratio_bin="square",
        has_obstructions=False, occupancy_class="Business",
        ceiling_height_bin="3-6m",
    )
    pid = lib.submit_for_review(
        feats, {"panels": [[3, 3]], "loops": 1},
        source_drawing_hash="sha256:abc", submitted_by="designer-001",
    )
    assert lib.stats()["pending"] == 1

    # No auto-approval — search must return nothing yet.
    assert lib.search_similar(feats) == []

    lib.approve(pid, fpe_license="FPE-DEV-0001")
    assert lib.stats()["approved"] == 1

    hits = lib.search_similar(feats)
    assert len(hits) == 1
    assert hits[0]["approved_by_fpe"] == "FPE-DEV-0001"
    print("[pattern_library] PASS — pending→approved→retrievable, no auto-learn")

    # Test rejection immutability
    pid2 = lib.submit_for_review(feats, {"panels": []}, "sha256:xyz", "designer-002")
    lib.reject(pid2, "FPE-DEV-0001", "non-compliant spacing per §17.6.3.1")
    try:
        lib.approve(pid2, "FPE-DEV-0001")
        print("[pattern_library] FAIL — rejected pattern was approved")
    except PatternLibraryError:
        print("[pattern_library] PASS — rejected patterns cannot be resurrected")
