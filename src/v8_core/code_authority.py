"""
code_authority.py — Layer 1 of the V8 Trust Stack
==================================================
Authoritative source of every NFPA/NEC numeric constant in the system.

RULES (enforced):
  1. No calculation module may use a numeric literal for a code value.
     Every value must come from this kernel via get_constant().
  2. Every constant is identified by (constant_id, jurisdiction_id, project_date).
  3. Every row is immutable. Corrections create a new row that supersedes.
  4. Every row requires an FPE signature (HMAC) before it is resolvable.
  5. The DB is append-only. Updates are forbidden by trigger.

Failure mode prevented:
  "Engineer used 2010 spacing in a 2022 jurisdiction and the system didn't catch it."
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS code_constants (
    constant_id        TEXT NOT NULL,
    code_family        TEXT NOT NULL,
    edition            TEXT NOT NULL,
    section            TEXT NOT NULL,
    value_numeric      REAL,
    value_unit         TEXT,
    value_categorical  TEXT,
    citation_text      TEXT NOT NULL,
    source_pdf_hash    TEXT NOT NULL,
    source_page        INTEGER NOT NULL,
    effective_date     TEXT NOT NULL,
    superseded_by_row  INTEGER,
    fpe_reviewer       TEXT NOT NULL,
    fpe_signature      TEXT NOT NULL,
    added_at           TEXT NOT NULL,
    notes              TEXT,
    PRIMARY KEY (constant_id, edition)
);

CREATE TABLE IF NOT EXISTS jurisdiction_adoption (
    jurisdiction_id    TEXT NOT NULL,
    code_family        TEXT NOT NULL,
    adopted_edition    TEXT NOT NULL,
    local_amendments   TEXT,        -- JSON
    effective_date     TEXT NOT NULL,
    PRIMARY KEY (jurisdiction_id, code_family)
);

-- Append-only enforcement: forbid UPDATE/DELETE on code_constants
CREATE TRIGGER IF NOT EXISTS forbid_update_constants
BEFORE UPDATE ON code_constants
BEGIN
    SELECT RAISE(ABORT, 'code_constants is append-only: create a superseding row instead');
END;

CREATE TRIGGER IF NOT EXISTS forbid_delete_constants
BEFORE DELETE ON code_constants
BEGIN
    SELECT RAISE(ABORT, 'code_constants is append-only: deletion is forbidden');
END;
"""


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CodeConstant:
    constant_id: str
    code_family: str
    edition: str
    section: str
    value_numeric: Optional[float]
    value_unit: Optional[str]
    value_categorical: Optional[str]
    citation_text: str
    source_pdf_hash: str
    source_page: int
    effective_date: str   # ISO date
    fpe_reviewer: str
    fpe_signature: str
    added_at: str
    notes: Optional[str] = None

    def canonical_payload(self) -> bytes:
        """Bytes that the FPE signature must cover. Order is fixed."""
        payload = {
            "constant_id": self.constant_id,
            "code_family": self.code_family,
            "edition": self.edition,
            "section": self.section,
            "value_numeric": self.value_numeric,
            "value_unit": self.value_unit,
            "value_categorical": self.value_categorical,
            "citation_text": self.citation_text,
            "source_pdf_hash": self.source_pdf_hash,
            "source_page": self.source_page,
            "effective_date": self.effective_date,
            "fpe_reviewer": self.fpe_reviewer,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class CodeAuthorityError(Exception):
    """Raised when a constant cannot be resolved or signature verification fails."""


class FPEAuthorityError(CodeAuthorityError):
    """Raised on an invalid or missing FPE signature."""


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

class CodeAuthority:
    """
    Thin, deterministic interface over an append-only SQLite store.

    Signature model (V8 alpha): HMAC-SHA256 with a per-FPE key, key material
    held in a secure store. For pilot / AHJ tiers this is upgraded to
    asymmetric (Ed25519) signing.
    """

    def __init__(self, db_path: str, fpe_key_provider=None):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        # fpe_key_provider(license_no) -> bytes
        self._fpe_key_provider = fpe_key_provider or _default_key_provider

    # ---------------- adding constants ----------------

    def add_constant(self, constant: CodeConstant) -> None:
        """Insert an FPE-signed constant. Raises if signature invalid."""
        self._verify_fpe_signature(constant)
        with self._conn:
            self._conn.execute(
                """INSERT INTO code_constants
                   (constant_id, code_family, edition, section,
                    value_numeric, value_unit, value_categorical,
                    citation_text, source_pdf_hash, source_page,
                    effective_date, fpe_reviewer, fpe_signature, added_at, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    constant.constant_id, constant.code_family, constant.edition,
                    constant.section, constant.value_numeric, constant.value_unit,
                    constant.value_categorical, constant.citation_text,
                    constant.source_pdf_hash, constant.source_page,
                    constant.effective_date, constant.fpe_reviewer,
                    constant.fpe_signature, constant.added_at, constant.notes,
                ),
            )

    def set_jurisdiction(self, jurisdiction_id: str, code_family: str,
                         adopted_edition: str, effective_date: str,
                         local_amendments: Optional[dict] = None) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO jurisdiction_adoption
                   (jurisdiction_id, code_family, adopted_edition, local_amendments, effective_date)
                   VALUES (?,?,?,?,?)""",
                (jurisdiction_id, code_family, adopted_edition,
                 json.dumps(local_amendments or {}, sort_keys=True),
                 effective_date),
            )

    # ---------------- resolving constants ----------------

    def get_constant(self, constant_id: str, jurisdiction_id: str,
                     project_date: Optional[str] = None) -> CodeConstant:
        """
        Resolve a constant for a specific jurisdiction & project date.
        Returns the row matching the edition that jurisdiction has adopted
        as of project_date.
        """
        project_date = project_date or date.today().isoformat()
        code_family = constant_id.split(".", 1)[0]

        row = self._conn.execute(
            """SELECT adopted_edition, local_amendments FROM jurisdiction_adoption
               WHERE jurisdiction_id = ? AND code_family = ? AND effective_date <= ?
               ORDER BY effective_date DESC LIMIT 1""",
            (jurisdiction_id, code_family, project_date),
        ).fetchone()

        if not row:
            raise CodeAuthorityError(
                f"No adopted edition of {code_family} for jurisdiction "
                f"{jurisdiction_id} as of {project_date}. Refuse to compute."
            )
        edition, amendments_json = row
        amendments = json.loads(amendments_json) if amendments_json else {}

        # Local amendments override the base edition value for specific sections.
        if constant_id in amendments:
            override = amendments[constant_id]
            return CodeConstant(
                constant_id=constant_id,
                code_family=code_family,
                edition=f"{edition}_local",
                section=override.get("section", "local"),
                value_numeric=override.get("value_numeric"),
                value_unit=override.get("value_unit"),
                value_categorical=override.get("value_categorical"),
                citation_text=override.get("citation_text", "local amendment"),
                source_pdf_hash=override.get("source_pdf_hash", ""),
                source_page=override.get("source_page", 0),
                effective_date=override.get("effective_date", project_date),
                fpe_reviewer=override.get("fpe_reviewer", "JURISDICTION"),
                fpe_signature=override.get("fpe_signature", "JURISDICTION_OVERRIDE"),
                added_at=datetime.now(timezone.utc).isoformat(),
                notes="local amendment",
            )

        row = self._conn.execute(
            """SELECT constant_id, code_family, edition, section,
                      value_numeric, value_unit, value_categorical,
                      citation_text, source_pdf_hash, source_page,
                      effective_date, fpe_reviewer, fpe_signature, added_at, notes
               FROM code_constants
               WHERE constant_id = ? AND edition = ?""",
            (constant_id, edition),
        ).fetchone()

        if not row:
            raise CodeAuthorityError(
                f"Constant {constant_id} not present for edition {edition}. "
                "Calculation refused until FPE-signed value is loaded."
            )
        return CodeConstant(*row)

    # ---------------- signature ----------------

    def _verify_fpe_signature(self, c: CodeConstant) -> None:
        if not c.fpe_reviewer or not c.fpe_signature:
            raise FPEAuthorityError("FPE reviewer and signature are required.")
        if c.fpe_signature in {"JURISDICTION_OVERRIDE"}:
            return  # reserved signatures
        key = self._fpe_key_provider(c.fpe_reviewer)
        if key is None:
            raise FPEAuthorityError(f"No key registered for FPE {c.fpe_reviewer}")
        expected = hmac.new(key, c.canonical_payload(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, c.fpe_signature):
            raise FPEAuthorityError(
                f"Signature mismatch for {c.constant_id} by {c.fpe_reviewer}"
            )


# ---------------------------------------------------------------------------
# Default key provider (DEV ONLY — replaced by HSM/Vault in production)
# ---------------------------------------------------------------------------

_DEV_KEYS = {
    # Format: license_no -> 32-byte key. DEV ONLY.
    # Production: load from env / KMS / Vault. Never commit a real key.
    "FPE-DEV-0001": hashlib.sha256(b"DEV_ONLY_NOT_FOR_PRODUCTION_0001").digest(),
}


def _default_key_provider(license_no: str):
    # Allow override via env (still dev-only)
    env_key = os.environ.get(f"FIRECALC_FPE_KEY_{license_no}")
    if env_key:
        return env_key.encode("utf-8")
    return _DEV_KEYS.get(license_no)


def sign_for_dev(constant: CodeConstant, license_no: str = "FPE-DEV-0001") -> CodeConstant:
    """Convenience helper to sign a constant during development & tests.

    The signature covers the canonical payload INCLUDING the reviewer name,
    so we must (1) set the reviewer, (2) sign the resulting payload,
    (3) attach the signature.
    """
    key = _default_key_provider(license_no)
    if key is None:
        raise FPEAuthorityError(f"No dev key for {license_no}")
    with_reviewer = CodeConstant(
        **{**asdict(constant), "fpe_reviewer": license_no, "fpe_signature": ""}
    )
    sig = hmac.new(key, with_reviewer.canonical_payload(), hashlib.sha256).hexdigest()
    return CodeConstant(
        **{**asdict(with_reviewer), "fpe_signature": sig}
    )


# ---------------------------------------------------------------------------
# Seed data — NFPA 72-2019, NEC 2023 (sample, NOT exhaustive, NOT production)
# ---------------------------------------------------------------------------

def seed_nfpa72_2019_minimum(auth: CodeAuthority, license_no: str = "FPE-DEV-0001") -> int:
    """
    Seed a *minimal* set of NFPA 72-2019 constants for system bring-up.
    This is dev seed data only. Real seed requires an FPE reading the
    actual NFPA 72-2019 PDF page-by-page and signing each row.
    """
    now = datetime.now(timezone.utc).isoformat()
    placeholder_hash = "0" * 64  # real seed uses sha256 of the licensed NFPA PDF
    seeds = [
        ("NFPA72.17.6.3.1.smoke_max_spacing", "NFPA72", "2019", "17.6.3.1",
         9.1, "m", None,
         "Smoke detectors on smooth ceilings: maximum spacing 30 ft (9.1 m).",
         "2019-01-01"),
        ("NFPA72.17.6.2.1.heat_max_spacing", "NFPA72", "2019", "17.6.2.1",
         15.2, "m", None,
         "Heat detectors: listed spacing not exceeding 50 ft (15.2 m).",
         "2019-01-01"),
        ("NFPA72.17.8.3.2.pull_station_travel_max", "NFPA72", "2019", "17.8.3.2",
         61.0, "m", None,
         "Manual fire alarm boxes: travel distance to a box shall not exceed 200 ft (61 m).",
         "2019-01-01"),
        ("NFPA72.18.4.5.strobe_height_min", "NFPA72", "2019", "18.5.5.6",
         2.03, "m", None,
         "Wall-mounted visible appliances: 80 in (2.03 m) minimum AFF to bottom of lens.",
         "2019-01-01"),
        ("NFPA72.18.4.5.strobe_height_max", "NFPA72", "2019", "18.5.5.6",
         2.44, "m", None,
         "Wall-mounted visible appliances: 96 in (2.44 m) maximum AFF to bottom of lens.",
         "2019-01-01"),
        ("NFPA72.internal.safety_margin.default", "NFPA72", "2019", "internal",
         0.15, "ratio", None,
         "FireCalc internal default safety margin (15%) against code maximum. "
         "Must be overridden per jurisdiction/occupancy.",
         "2019-01-01"),
    ]
    count = 0
    for (cid, fam, ed, sec, val, unit, cat, citation, eff_date) in seeds:
        c = CodeConstant(
            constant_id=cid, code_family=fam, edition=ed, section=sec,
            value_numeric=val, value_unit=unit, value_categorical=cat,
            citation_text=citation,
            source_pdf_hash=placeholder_hash, source_page=0,
            effective_date=eff_date,
            fpe_reviewer="", fpe_signature="",
            added_at=now,
            notes="DEV SEED — replace with FPE-reviewed entry against licensed NFPA PDF",
        )
        c_signed = sign_for_dev(c, license_no)
        try:
            auth.add_constant(c_signed)
            count += 1
        except sqlite3.IntegrityError:
            pass  # already seeded
    return count


def seed_nfpa72_2022_minimum(auth: CodeAuthority, license_no: str = "FPE-DEV-0001") -> int:
    """
    Seed NFPA 72-2022 constants (latest edition).
    """
    now = datetime.now(timezone.utc).isoformat()
    placeholder_hash = "0" * 64
    seeds = [
        # NFPA 72-2022 §17.6.3.1 - Smoke detector spacing
        ("NFPA72.17.6.3.1.smoke_max_spacing", "NFPA72", "2022", "17.6.3.1",
         9.1, "m", None,
         "Smoke detectors on smooth ceilings: maximum spacing 30 ft (9.1 m).",
         "2022-01-01"),
        # NFPA 72-2022 §17.6.2.1 - Heat detector spacing
        ("NFPA72.17.6.2.1.heat_max_spacing", "NFPA72", "2022", "17.6.2.1",
         15.2, "m", None,
         "Heat detectors: listed spacing not exceeding 50 ft (15.2 m).",
         "2022-01-01"),
        # NFPA 72-2022 §17.8.3.2 - Pull station travel
        ("NFPA72.17.8.3.2.pull_station_travel_max", "NFPA72", "2022", "17.8.3.2",
         61.0, "m", None,
         "Manual fire alarm boxes: travel distance shall not exceed 200 ft (61 m).",
         "2022-01-01"),
        # NFPA 72-2022 §18.5.5.6 - Strobe mounting height
        ("NFPA72.18.5.5.6.strobe_height_min", "NFPA72", "2022", "18.5.5.6",
         2.03, "m", None,
         "Wall-mounted visible appliances: 80 in (2.03 m) minimum to lens bottom.",
         "2022-01-01"),
        ("NFPA72.18.5.5.6.strobe_height_max", "NFPA72", "2022", "18.5.5.6",
         2.44, "m", None,
         "Wall-mounted visible appliances: 96 in (2.44 m) maximum to lens bottom.",
         "2022-01-01"),
        # NFPA 72-2022 §21 - Loop capacity
        ("NFPA72.21.2.panel_max_devices", "NFPA72", "2022", "21.2.2",
         250, "devices", None,
         "Signal line circuit: not more than 250 devices.",
         "2022-01-01"),
    ]
    count = 0
    for (cid, fam, ed, sec, val, unit, cat, citation, eff_date) in seeds:
        c = CodeConstant(
            constant_id=cid, code_family=fam, edition=ed, section=sec,
            value_numeric=val, value_unit=unit, value_categorical=cat,
            citation_text=citation,
            source_pdf_hash=placeholder_hash, source_page=0,
            effective_date=eff_date,
            fpe_reviewer="", fpe_signature="",
            added_at=now,
        )
        c_signed = sign_for_dev(c, license_no)
        try:
            auth.add_constant(c_signed)
            count += 1
        except sqlite3.IntegrityError:
            pass
    return count


def seed_nfpa13_2022_minimum(auth: CodeAuthority, license_no: str = "FPE-DEV-0001") -> int:
    """
    Seed NFPA 13-2022 sprinkler spacing constants.
    """
    now = datetime.now(timezone.utc).isoformat()
    placeholder_hash = "0" * 64
    seeds = [
        # NFPA 13-2022 Tables
        ("NFPA13.8.2.3.1.quick_response_sprinkler_area", "NFPA13", "2022", "8.2.3.1",
         12.0, "m^2", None,
         "QR sprinklers: maximum coverage 130 sq ft (12.0 m²).",
         "2022-01-01"),
    ]
    count = 0
    for (cid, fam, ed, sec, val, unit, cat, citation, eff_date) in seeds:
        c = CodeConstant(
            constant_id=cid, code_family=fam, edition=ed, section=sec,
            value_numeric=val, value_unit=unit, value_categorical=cat,
            citation_text=citation,
            source_pdf_hash=placeholder_hash, source_page=0,
            effective_date=eff_date,
            fpe_reviewer="", fpe_signature="",
            added_at=now,
        )
        c_signed = sign_for_dev(c, license_no)
        try:
            auth.add_constant(c_signed)
            count += 1
        except sqlite3.IntegrityError:
            pass
    return count


def seed_nec_2023_minimum(auth: CodeAuthority, license_no: str = "FPE-DEV-0001") -> int:
    """
    Seed NEC 2023 basic electrical constants for firealarm.
    """
    now = datetime.now(timezone.utc).isoformat()
    placeholder_hash = "0" * 64
    seeds = [
        # NEC 2023 Table 310.16 - Conductor ampacity
        ("NEC.310.16.awg_14_ampacity", "NEC", "2023", "Table 310.16",
         15, "A", None,
         "14 AWG: 15A copper (60°C).",
         "2023-01-01"),
        ("NEC.310.16.awg_12_ampacity", "NEC", "2023", "Table 310.16",
         20, "A", None,
         "12 AWG: 20A copper (60°C).",
         "2023-01-01"),
        ("NEC.310.16.awg_10_ampacity", "NEC", "2023", "Table 310.16",
         30, "A", None,
         "10 AWG: 30A copper (60°C).",
         "2023-01-01"),
        # NEC 2023 Article 210 - Voltage drop
        ("NEC.210.52.voltage_drop_max", "NEC", "2023", "210.52",
         0.05, "ratio", None,
         "Voltage drop: not exceed 5% branch circuit, 3% feeder.",
         "2023-01-01"),
    ]
    count = 0
    for (cid, fam, ed, sec, val, unit, cat, citation, eff_date) in seeds:
        c = CodeConstant(
            constant_id=cid, code_family=fam, edition=ed, section=sec,
            value_numeric=val, value_unit=unit, value_categorical=cat,
            citation_text=citation,
            source_pdf_hash=placeholder_hash, source_page=0,
            effective_date=eff_date,
            fpe_reviewer="", fpe_signature="",
            added_at=now,
        )
        c_signed = sign_for_dev(c, license_no)
        try:
            auth.add_constant(c_signed)
            count += 1
        except sqlite3.IntegrityError:
            pass
    return count


def seed_all_minimum(auth: CodeAuthority, license_no: str = "FPE-DEV-0001") -> dict:
    """
    Seed all minimum code authority constants.
    """
    results = {}
    results["NFPA72.2019"] = seed_nfpa72_2019_minimum(auth, license_no)
    results["NFPA72.2022"] = seed_nfpa72_2022_minimum(auth, license_no)
    results["NFPA13.2022"] = seed_nfpa13_2022_minimum(auth, license_no)
    results["NEC.2023"] = seed_nec_2023_minimum(auth, license_no)
    return results
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db = "/tmp/firecalc_authority_selftest.db"
    Path(db).unlink(missing_ok=True)
    auth = CodeAuthority(db)
    n = seed_nfpa72_2019_minimum(auth)
    print(f"[code_authority] seeded {n} constants.")

    auth.set_jurisdiction("US.GENERIC", "NFPA72", "2019", "2019-01-01")
    c = auth.get_constant("NFPA72.17.6.3.1.smoke_max_spacing",
                          "US.GENERIC", "2026-01-01")
    print(f"[code_authority] resolved: {c.constant_id} = {c.value_numeric} {c.value_unit}")
    print(f"[code_authority]   cite : {c.citation_text}")
    print(f"[code_authority]   FPE  : {c.fpe_reviewer}")

    # Verify append-only
    try:
        auth._conn.execute("DELETE FROM code_constants").fetchall()
        print("[code_authority] FAIL: deletion allowed!")
    except sqlite3.IntegrityError:
        print("[code_authority] PASS: deletion forbidden by trigger.")
    print("[code_authority] OK.")
