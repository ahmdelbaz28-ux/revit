"""fireai.core.audit_log — QOMN-FIRE Layer 4: Audit Log (Immutable Record)
========================================================================

Creates permanent, tamper-evident record of every computation.

QOMN-FIRE Requirements:
- Every computation logged with: timestamp, input, formula reference, output, hash
- Log format: append-only, cryptographically signed
- Retention: life of building + 7 years minimum
- Accessibility: AHJ can access without vendor cooperation
- Export format: JSON with digital signature

Implementation:
- SQLite with WAL mode for concurrent reads/writes
- Hash chain: each entry contains SHA-256 of previous entry
- HMAC-SHA256 for evidence package integrity
- Append-only: no UPDATE or DELETE operations permitted
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import List, Optional, Tuple

# Sentinel: first entry in the chain has this as prev_entry_hash
GENESIS_PREV_HASH = "0" * 64

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_entries (
    entry_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    layer INTEGER NOT NULL CHECK (layer BETWEEN 0 AND 4),
    input_hash TEXT NOT NULL,
    formula_reference TEXT NOT NULL,
    computation_description TEXT NOT NULL,
    output_value TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('COMPLIANT', 'VIOLATION', 'ERROR')),
    prev_entry_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    hmac_signature TEXT
);
"""

_INSERT_SQL = """
INSERT INTO audit_entries (
    entry_id, timestamp, analysis_id, layer,
    input_hash, formula_reference, computation_description,
    output_value, output_hash, status,
    prev_entry_hash, entry_hash, hmac_signature
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

_LAST_ENTRY_HASH_SQL = """
SELECT entry_hash FROM audit_entries ORDER BY rowid DESC LIMIT 1;
"""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def compute_entry_hash(entry: AuditEntry) -> str:
    """Compute SHA-256 hash of all entry fields *except* entry_hash and hmac_signature.

    The hash is calculated over a canonical JSON representation of the field
    values in field-declaration order, excluding ``entry_hash`` and
    ``hmac_signature`` so that the hash is deterministic and self-consistent.
    """
    # Build a deterministic ordered dict of the signable fields
    signable: dict = {}
    for f in fields(entry):
        if f.name in ("entry_hash", "hmac_signature"):
            continue
        signable[f.name] = getattr(entry, f.name)
    canonical = json.dumps(signable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_hmac(entry_hash: str, key: bytes) -> str:
    """Compute HMAC-SHA256 of *entry_hash* using *key*."""
    return hmac.new(key, entry_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def create_audit_entry(
    analysis_id: str,
    layer: int,
    input_hash: str,
    formula_reference: str,
    computation_description: str,
    output_value: str,
    output_hash: str,
    status: str,
    prev_entry_hash: Optional[str] = None,
    entry_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> AuditEntry:
    """Factory function to create an :class:`AuditEntry` with auto-computed hashes.

    Parameters
    ----------
    analysis_id : str
        UUID4 identifying the parent analysis run.
    layer : int
        QOMN-FIRE layer (0-4).
    input_hash : str
        SHA-256 hex digest of the input data.
    formula_reference : str
        NFPA/NEC section reference.
    computation_description : str
        Human-readable description of the computation.
    output_value : str
        Result value with unit (e.g. ``"125.0 ft"``).
    output_hash : str
        SHA-256 hex digest of the raw output.
    status : str
        One of ``"COMPLIANT"``, ``"VIOLATION"``, ``"ERROR"``.
    prev_entry_hash : str, optional
        Hash chain link — SHA-256 of the previous entry.  If *None* the
        genesis sentinel (64 zeros) is used.
    entry_id : str, optional
        Override the auto-generated UUID4 entry id.
    timestamp : str, optional
        Override the auto-generated ISO-8601 UTC timestamp.

    Returns
    -------
    AuditEntry
        Fully populated entry with ``entry_hash`` computed.

    """
    if prev_entry_hash is None:
        prev_entry_hash = GENESIS_PREV_HASH
    if entry_id is None:
        entry_id = str(uuid.uuid4())
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    entry = AuditEntry(
        entry_id=entry_id,
        timestamp=timestamp,
        analysis_id=analysis_id,
        layer=layer,
        input_hash=input_hash,
        formula_reference=formula_reference,
        computation_description=computation_description,
        output_value=output_value,
        output_hash=output_hash,
        status=status,
        prev_entry_hash=prev_entry_hash,
        entry_hash="",  # placeholder — computed below
        hmac_signature=None,  # filled in by AuditLog.append
    )

    # Compute and assign the entry hash
    object.__setattr__(entry, "entry_hash", compute_entry_hash(entry))
    return entry


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditEntry:
    """Immutable record of a single audited computation."""

    entry_id: str
    timestamp: str
    analysis_id: str
    layer: int
    input_hash: str
    formula_reference: str
    computation_description: str
    output_value: str
    output_hash: str
    status: str
    prev_entry_hash: str
    entry_hash: str
    hmac_signature: Optional[str]


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class AuditLog:
    """Append-only, tamper-evident audit log backed by SQLite.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.  Use ``":memory:"`` for an
        in-memory database (useful for testing).
    hmac_key : bytes, optional
        Secret key for HMAC-SHA256 signing.  If *None*, HMAC signatures
        are **not** computed (the ``hmac_signature`` field will remain
        ``NULL``).

    """

    def __init__(self, db_path: str = ":memory:", hmac_key: Optional[bytes] = None) -> None:
        self._db_path = db_path
        self._hmac_key = hmac_key
        # V69-11 FIX: Thread-safe lock for hash chain integrity
        # Without this, concurrent append() calls break the hash chain
        # because both read the same prev_entry_hash before either writes.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute(_SCHEMA_SQL)
        self._conn.commit()

    # -- Public API --------------------------------------------------------

    def _check_closed(self) -> None:
        """Raise if the log has been closed. V96 FIX."""
        if self._conn is None:
            raise RuntimeError("AuditLog is closed")

    def append(self, entry: AuditEntry) -> str:
        """Append an entry to the audit log.

        The method automatically patches the entry's ``prev_entry_hash``
        to the correct chain link value and recomputes ``entry_hash`` so
        that callers do not need to know the current log state.  If the
        entry already carries the correct ``prev_entry_hash`` and
        ``entry_hash``, no mutation occurs.

        Returns
        -------
        str
            The ``entry_id`` of the appended entry.

        Raises
        ------
        ValueError
            If the entry's ``entry_hash`` was explicitly set (not empty)
            but does not match the recomputed hash **after** fixing
            ``prev_entry_hash``.
        RuntimeError
            If the log has been closed.

        """
        # V69-11 FIX: Lock entire append for hash chain integrity
        with self._lock:
            self._check_closed()

            # --- Fix hash-chain link ---
            last_hash = self._last_entry_hash()
            expected_prev = last_hash if last_hash else GENESIS_PREV_HASH

            chain_fixed = False
            if entry.prev_entry_hash != expected_prev:
                object.__setattr__(entry, "prev_entry_hash", expected_prev)
                chain_fixed = True

            # --- Recompute entry_hash (always needed if chain was fixed) ---
            recomputed = compute_entry_hash(entry)
            if recomputed != entry.entry_hash:
                if entry.entry_hash == "" or chain_fixed:
                    object.__setattr__(entry, "entry_hash", recomputed)
                else:
                    raise ValueError(f"Entry hash mismatch: expected {recomputed}, got {entry.entry_hash}")

            # --- HMAC signature ---
            hmac_sig: Optional[str] = None
            if self._hmac_key is not None:
                hmac_sig = compute_hmac(entry.entry_hash, self._hmac_key)
                object.__setattr__(entry, "hmac_signature", hmac_sig)

            # --- Persist ---
            self._conn.execute(
                _INSERT_SQL,
                (
                    entry.entry_id,
                    entry.timestamp,
                    entry.analysis_id,
                    entry.layer,
                    entry.input_hash,
                    entry.formula_reference,
                    entry.computation_description,
                    entry.output_value,
                    entry.output_hash,
                    entry.status,
                    entry.prev_entry_hash,
                    entry.entry_hash,
                    entry.hmac_signature,
                ),
            )
            self._conn.commit()
            return entry.entry_id

    def verify_chain(self) -> Tuple[bool, List[str]]:
        """Verify the integrity of the entire hash chain.

        Returns
        -------
        Tuple[bool, List[str]]
            A two-element tuple where the first element is ``True`` if
            the chain is intact and ``False`` otherwise.  The second
            element is a list of human-readable error descriptions (empty
            when the chain is valid).

        Raises
        ------
        RuntimeError
            If the log has been closed.

        """
        with self._lock:
            self._check_closed()
            return self._verify_chain_unlocked()

    def _verify_chain_unlocked(self) -> Tuple[bool, List[str]]:
        """Internal: verify chain (caller must hold self._lock)."""
        errors: List[str] = []

        cur = self._conn.execute("SELECT entry_id, prev_entry_hash, entry_hash FROM audit_entries ORDER BY rowid ASC;")
        rows = cur.fetchall()

        if not rows:
            return True, errors

        # First entry must link to genesis
        first_id, first_prev, first_hash = rows[0]
        if first_prev != GENESIS_PREV_HASH:
            errors.append(f"Entry {first_id}: prev_entry_hash is {first_prev}, expected genesis {GENESIS_PREV_HASH}")

        # Verify each subsequent link
        prev_hash = first_hash
        for entry_id, prev_entry_hash, entry_hash in rows[1:]:
            if prev_entry_hash != prev_hash:
                errors.append(f"Entry {entry_id}: prev_entry_hash is {prev_entry_hash}, expected {prev_hash}")
            prev_hash = entry_hash

        # Additionally verify each entry's self-hash
        all_rows = self._conn.execute("SELECT * FROM audit_entries ORDER BY rowid ASC;").fetchall()
        col_names = [desc[0] for desc in self._conn.execute("SELECT * FROM audit_entries LIMIT 0;").description]

        for row in all_rows:
            row_dict = dict(zip(col_names, row, strict=False))
            try:
                entry = self._row_to_entry(row_dict)
            except Exception as exc:
                errors.append(f"Cannot reconstruct entry {row_dict.get('entry_id', '?')}: {exc}")
                continue

            recomputed = compute_entry_hash(entry)
            if recomputed != entry.entry_hash:
                errors.append(f"Entry {entry.entry_id}: entry_hash is {entry.entry_hash}, recomputed {recomputed}")

            # Verify HMAC if present and key available
            if entry.hmac_signature is not None and self._hmac_key is not None:
                expected_hmac = compute_hmac(entry.entry_hash, self._hmac_key)
                if not hmac.compare_digest(expected_hmac, entry.hmac_signature):
                    errors.append(f"Entry {entry.entry_id}: HMAC signature invalid")

        is_valid = len(errors) == 0
        return is_valid, errors

    def get_entry(self, entry_id: str) -> Optional[AuditEntry]:
        """Retrieve a single entry by its ``entry_id``.

        Returns ``None`` if the entry does not exist.

        Raises
        ------
        RuntimeError
            If the log has been closed.

        """
        with self._lock:
            self._check_closed()
            cur = self._conn.execute("SELECT * FROM audit_entries WHERE entry_id = ?;", (entry_id,))
            row = cur.fetchone()
            if row is None:
                return None
            col_names = [desc[0] for desc in cur.description]
            return self._row_to_entry(dict(zip(col_names, row, strict=False)))

    def get_analysis(self, analysis_id: str) -> List[AuditEntry]:
        """Retrieve all entries belonging to an analysis, in insertion order.

        Raises
        ------
        RuntimeError
            If the log has been closed.

        """
        with self._lock:
            self._check_closed()
            cur = self._conn.execute(
                "SELECT * FROM audit_entries WHERE analysis_id = ? ORDER BY rowid ASC;",
                (analysis_id,),
            )
            col_names = [desc[0] for desc in cur.description]
            return [self._row_to_entry(dict(zip(col_names, row, strict=False))) for row in cur.fetchall()]

    def export_json(self, analysis_id: str) -> str:
        """Export an analysis audit trail as a signed JSON string.

        The exported object contains a ``entries`` list and an
        ``export_hmac`` field which is the HMAC-SHA256 of the canonical
        JSON of the entries list (only present when an HMAC key is
        configured).

        Raises
        ------
        RuntimeError
            If the log has been closed.

        """
        # get_analysis already acquires _lock and checks closed
        entries = self.get_analysis(analysis_id)
        entries_payload = [asdict(e) for e in entries]

        export_obj: dict = {
            "analysis_id": analysis_id,
            "entries": entries_payload,
            "export_hmac": None,
        }

        if self._hmac_key is not None:
            # Canonical JSON of just the entries for deterministic signing
            entries_canonical = json.dumps(entries_payload, sort_keys=True, separators=(",", ":"))
            export_obj["export_hmac"] = compute_hmac(
                hashlib.sha256(entries_canonical.encode("utf-8")).hexdigest(),
                self._hmac_key,
            )

        return json.dumps(export_obj, indent=2, sort_keys=True)

    def verify_export(self, json_str: str) -> Tuple[bool, str]:
        """Verify the integrity of an exported JSON string.

        Returns
        -------
        Tuple[bool, str]
            ``(True, "")`` if the export is valid, or
            ``(False, description)`` otherwise.

        """
        try:
            export_obj = json.loads(json_str)
        except json.JSONDecodeError as exc:
            return False, f"Invalid JSON: {exc}"

        entries_payload = export_obj.get("entries")
        if entries_payload is None:
            return False, "Missing 'entries' field"

        stored_hmac = export_obj.get("export_hmac")

        # If HMAC key is configured and export has an HMAC, verify it
        if self._hmac_key is not None and stored_hmac is not None:
            entries_canonical = json.dumps(entries_payload, sort_keys=True, separators=(",", ":"))
            expected_hmac = compute_hmac(
                hashlib.sha256(entries_canonical.encode("utf-8")).hexdigest(),
                self._hmac_key,
            )
            if not hmac.compare_digest(expected_hmac, stored_hmac):
                return False, "Export HMAC signature mismatch — data may have been tampered with"

        # Verify individual entry hashes
        for entry_dict in entries_payload:
            try:
                entry = AuditEntry(**entry_dict)
            except Exception as exc:
                return False, f"Cannot reconstruct entry: {exc}"

            recomputed = compute_entry_hash(entry)
            if recomputed != entry.entry_hash:
                return False, (
                    f"Entry {entry.entry_id}: entry_hash mismatch (expected {recomputed}, got {entry.entry_hash})"
                )

            if entry.hmac_signature is not None and self._hmac_key is not None:
                expected_sig = compute_hmac(entry.entry_hash, self._hmac_key)
                if not hmac.compare_digest(expected_sig, entry.hmac_signature):
                    return False, f"Entry {entry.entry_id}: HMAC signature invalid"

        return True, ""

    def count(self) -> int:
        """Return the total number of entries in the log.

        Raises
        ------
        RuntimeError
            If the log has been closed.

        """
        with self._lock:
            self._check_closed()
            cur = self._conn.execute("SELECT COUNT(*) FROM audit_entries;")
            return cur.fetchone()[0]

    def close(self) -> None:
        """Close the database connection.

        V96 FIX: close() now acquires ``_lock`` to prevent a race where
        one thread closes the DB while another is mid-query.  All public
        methods check ``_conn is None`` via ``_check_closed()`` under the
        lock, so a closed log raises ``RuntimeError`` instead of the
        cryptic ``AttributeError: 'NoneType' has no attribute 'execute'``.
        """
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None  # type: ignore[assignment]

    # -- Internal helpers --------------------------------------------------

    def _last_entry_hash(self) -> Optional[str]:
        """Return the ``entry_hash`` of the most recently inserted entry."""
        cur = self._conn.execute(_LAST_ENTRY_HASH_SQL)
        row = cur.fetchone()
        return row[0] if row else None

    @staticmethod
    def _row_to_entry(d: dict) -> AuditEntry:
        """Convert a dict (from a DB row) into an :class:`AuditEntry`."""
        return AuditEntry(
            entry_id=d["entry_id"],
            timestamp=d["timestamp"],
            analysis_id=d["analysis_id"],
            layer=int(d["layer"]),
            input_hash=d["input_hash"],
            formula_reference=d["formula_reference"],
            computation_description=d["computation_description"],
            output_value=d["output_value"],
            output_hash=d["output_hash"],
            status=d["status"],
            prev_entry_hash=d["prev_entry_hash"],
            entry_hash=d["entry_hash"],
            hmac_signature=d["hmac_signature"],
        )
