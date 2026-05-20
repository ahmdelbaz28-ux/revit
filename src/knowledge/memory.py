"""
intelligence/knowledge_base.py
==============================
SQLite-backed persistent memory. EVERYTHING the system learns lives here.

Tables:
  files             — every file we've ever processed (sha256 indexed)
  symbols           — known symbol classes (camera, smoke_detector, sprinkler, …)
  symbol_examples   — labelled crops/embeddings, with origin & confidence
  decisions         — every classification we made + outcome (corrected? confirmed?)
  rules             — code rules as data (NFPA, IBC, local). Editable.
  feedback          — human corrections — drives active learning
"""
from __future__ import annotations
import sqlite3, json, time, os
from pathlib import Path
from typing import Any, Optional

DEFAULT_DB = Path(os.environ.get("EDA_DB", Path.home() / ".eda" / "kb.sqlite"))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    sha256 TEXT PRIMARY KEY,
    path   TEXT,
    type   TEXT,
    ts     REAL,
    meta   TEXT
);

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT,                 -- 'fire','security','electrical','mech','other'
    description TEXT,
    standard_spacing_m REAL,       -- typical max spacing (NFPA etc.)
    coverage_radius_m REAL,        -- typical coverage radius
    meta TEXT
);

CREATE TABLE IF NOT EXISTS symbol_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id INTEGER NOT NULL,
    source_sha TEXT,
    bbox TEXT,                     -- JSON [x,y,w,h]
    embedding BLOB,                -- float32 vector (numpy bytes)
    image BLOB,                    -- optional PNG bytes
    label_confidence REAL,
    ts REAL,
    FOREIGN KEY(symbol_id) REFERENCES symbols(id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_sha TEXT, page INTEGER, bbox TEXT,
    predicted_symbol TEXT, confidence REAL,
    ts REAL,
    confirmed INTEGER DEFAULT NULL,    -- 1=confirmed, 0=corrected, NULL=pending
    correction TEXT
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,           -- 'NFPA72','NFPA13','IBC','EGY_FIRE_CODE'…
    rule_key TEXT,       -- e.g. 'smoke_detector.max_spacing_m'
    value REAL,
    units TEXT,
    citation TEXT,
    notes TEXT,
    UNIQUE(code, rule_key)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER,
    user TEXT, ts REAL, comment TEXT,
    FOREIGN KEY(decision_id) REFERENCES decisions(id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_file ON decisions(file_sha);
CREATE INDEX IF NOT EXISTS idx_examples_symbol ON symbol_examples(symbol_id);
"""


class KnowledgeBase:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        # INT-1: Use db_pool for concurrent access + thread safety
        from src.v8_core.db_pool import DatabasePool
        self._pool = DatabasePool(str(self.path))
        
        # Initialize schema (execute statements one by one)
        with self._pool.get_connection() as conn:
            for stmt in _SCHEMA.split(';'):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            self._seed_if_empty(conn)
    
    def _seed_if_empty(self, conn):
        """Seed if empty. Use provided connection."""
        if conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] == 0:
            self._seed(conn)

    # ── Helper for thread-safe DB access
    def _get_conn(self):
        """Get connection from pool - use in 'with' statement."""
        return self._pool.get_connection()
    
    # ── files
    def record_file(self, sha: str, path: str, ftype: str, meta: dict):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO files(sha256,path,type,ts,meta) VALUES(?,?,?,?,?)",
                (sha, path, ftype, time.time(), json.dumps(meta, default=str)))
            conn.commit()

    # ── symbols
    # Security Fix (VULN-011): Whitelist of allowed column names to prevent SQL injection
    _SYMBOL_COLUMNS = frozenset({
        "category", "description", "standard_spacing_m", "coverage_radius_m", "meta"
    })

    def upsert_symbol(self, name: str, **kw):
        # Security Fix (VULN-011): Validate column names against whitelist
        invalid_keys = set(kw.keys()) - self._SYMBOL_COLUMNS
        if invalid_keys:
            raise ValueError(
                f"Invalid symbol columns: {invalid_keys}. "
                f"Allowed: {self._SYMBOL_COLUMNS}"
            )

        with self._get_conn() as conn:
            cur = conn.execute("SELECT id FROM symbols WHERE name=?", (name,))
            row = cur.fetchone()
            if row:
                if kw:
                    sets = ", ".join(f"{k}=?" for k in kw)
                    conn.execute(f"UPDATE symbols SET {sets} WHERE id=?",
                                      (*kw.values(), row["id"]))
                    conn.commit()
                return row["id"]
            cols = ["name"] + list(kw.keys())
            qs   = ",".join("?"*len(cols))
            cur  = conn.execute(
                f"INSERT INTO symbols({','.join(cols)}) VALUES({qs})",
                (name, *kw.values()))
            conn.commit()
            return cur.lastrowid

    @property
    def conn(self):
        """Thread-safe connection from pool. Use in 'with' statement."""
        return self._pool.get_connection()
    
    def get_symbol(self, name: str) -> Optional[dict]:
        with self._get_conn() as conn:
            r = conn.execute("SELECT * FROM symbols WHERE name=?", (name,)).fetchone()
        return dict(r) if r else None

    def list_symbols(self) -> list:
        with self._get_conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM symbols")]

    # ── examples / embeddings
    def add_example(self, symbol_name: str, embedding_bytes: bytes,
                source_sha: str, bbox: tuple, confidence: float = 1.0,
                image_bytes: bytes | None = None):
        sid = self.upsert_symbol(symbol_name)
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO symbol_examples(symbol_id,source_sha,bbox,embedding,image,label_confidence,ts) "
                "VALUES(?,?,?,?,?,?,?)",
                (sid, source_sha, json.dumps(list(bbox)), embedding_bytes,
                 image_bytes, confidence, time.time()))
            conn.commit()

    def fetch_all_embeddings(self):
        """Returns list of (symbol_name, embedding_bytes, confidence)."""
        with self._get_conn() as conn:
            q = """SELECT s.name, e.embedding, e.label_confidence
                   FROM symbol_examples e JOIN symbols s ON s.id=e.symbol_id"""
            return list(conn.execute(q))

    # ── decisions / feedback
    def record_decision(self, file_sha: str, page: int, bbox: tuple,
                    predicted: str, confidence: float) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO decisions(file_sha,page,bbox,predicted_symbol,confidence,ts) "
                "VALUES(?,?,?,?,?,?)",
                (file_sha, page, json.dumps(list(bbox)), predicted, confidence, time.time()))
            conn.commit()
            return cur.lastrowid

    def confirm(self, decision_id: int, correct: bool, correction: str | None = None):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE decisions SET confirmed=?, correction=? WHERE id=?",
                (1 if correct else 0, correction, decision_id))
            conn.commit()

    # ── code rules
    def set_rule(self, code: str, key: str, value: float, units: str,
                 citation: str = "", notes: str = ""):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO rules(code,rule_key,value,units,citation,notes) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(code,rule_key) DO UPDATE SET value=excluded.value, units=excluded.units, "
                "citation=excluded.citation, notes=excluded.notes",
                (code, key, value, units, citation, notes))
            conn.commit()

    def get_rule(self, key: str, code: str | None = None) -> Optional[dict]:
        with self._get_conn() as conn:
            if code:
                r = conn.execute(
                    "SELECT * FROM rules WHERE code=? AND rule_key=?", (code, key)).fetchone()
            else:
                r = conn.execute(
                    "SELECT * FROM rules WHERE rule_key=? ORDER BY id DESC LIMIT 1", (key,)).fetchone()
            return dict(r) if r else None

    # ── stats
    def stats(self) -> dict:
        with self._get_conn() as conn:
            c = conn.execute
            return {
                "files":     c("SELECT COUNT(*) FROM files").fetchone()[0],
                "symbols":   c("SELECT COUNT(*) FROM symbols").fetchone()[0],
                "examples":  c("SELECT COUNT(*) FROM symbol_examples").fetchone()[0],
                "decisions": c("SELECT COUNT(*) FROM decisions").fetchone()[0],
                "rules":     c("SELECT COUNT(*) FROM rules").fetchone()[0],
            }

    # ── seeding: ship with real engineering knowledge
    # FIXED: _seed_if_empty now takes conn parameter
    def _seed(self, conn):
        """Seed database with initial data. Use thread-safe connection."""
        # Symbol catalogue with typical spacings — these are STARTING values,
        # the user must verify against the governing code for their jurisdiction.
        seed_symbols = [
            ("smoke_detector",     "fire",       "Spot-type smoke detector",         9.1, 6.4),
            ("heat_detector",      "fire",       "Spot-type heat detector",          7.0, 5.0),
            ("sprinkler_pendant",  "fire",       "Pendant sprinkler (light hazard)", 4.6, 2.3),
            ("sprinkler_upright",  "fire",       "Upright sprinkler",                4.6, 2.3),
            ("manual_call_point",  "fire",       "Manual pull station",             60.0, None),
            ("exit_sign",          "fire",       "Illuminated exit sign",           30.0, None),
            ("emergency_light",    "fire",       "Emergency luminaire",             10.0, 5.0),
            ("fire_extinguisher",  "fire",       "Portable fire extinguisher",      22.9, None),
            ("camera_dome",        "security",   "Dome CCTV camera",                None, 15.0),
            ("camera_bullet",      "security",   "Bullet CCTV camera",              None, 30.0),
            ("pir_sensor",         "security",   "Passive infrared motion sensor",  None, 12.0),
            ("access_reader",      "security",   "Access control reader",           None, None),
            ("light_fixture",      "electrical", "General lighting fixture",         None, None),
            ("socket_outlet",      "electrical", "Power socket",                     None, None),
            ("distribution_board", "electrical", "Electrical distribution board",    None, None),
            ("hvac_diffuser",      "mech",       "Supply / return air diffuser",     None, None),
            ("pipe_chw",           "mech",       "Chilled-water pipe",               None, None),
            ("pipe_drainage",      "mech",       "Drainage pipe",                    None, None),
            ("cable_tray",         "electrical", "Cable tray / ladder",              None, None),
            ("conduit",            "electrical", "Electrical conduit",               None, None),
        ]
        for name, cat, desc, spacing, radius in seed_symbols:
            self.upsert_symbol(name, category=cat, description=desc,
                               standard_spacing_m=spacing, coverage_radius_m=radius)

        # Code rules (STARTING values — verify per project!)
        rules = [
            # NFPA 72 — smoke detector spot spacing
            ("NFPA72", "smoke_detector.max_spacing_m",    9.1,  "m", "NFPA 72 §17.6", ""),
            ("NFPA72", "smoke_detector.from_wall_m",      4.55, "m", "NFPA 72 §17.6.3", "≤ 0.5 × spacing"),
            ("NFPA72", "smoke_detector.beam_offset_m",    0.3,  "m", "NFPA 72", "min from beams/walls"),
            ("NFPA72", "heat_detector.max_spacing_m",     7.0,  "m", "NFPA 72 §17.6", ""),
            ("NFPA72", "manual_pull.travel_distance_m",  60.0,  "m", "NFPA 72 §17.14", "max travel"),
            # NFPA 13 — sprinklers light hazard
            ("NFPA13", "sprinkler.light_hazard.max_area_m2", 20.9, "m2", "NFPA 13 §8.6", "per head"),
            ("NFPA13", "sprinkler.light_hazard.max_spacing_m", 4.6, "m", "NFPA 13 §8.6", ""),
            ("NFPA13", "sprinkler.from_wall_m",            2.3, "m", "NFPA 13 §8.6", "max"),
            # NFPA 101 — egress
            ("NFPA101", "exit.max_travel_distance_m",     61.0, "m", "NFPA 101", "sprinklered, business"),
            ("NFPA101", "common_path.max_m",              30.5, "m", "NFPA 101", "business occupancy"),
            ("NFPA101", "dead_end_corridor.max_m",        15.2, "m", "NFPA 101", ""),
            # Electrical / mechanical clearance
            ("NEC",     "panel.clearance_front_m",         0.9, "m", "NEC 110.26", ""),
            ("MEP",     "cable_tray.from_hot_pipe_m",      0.3, "m", "good practice", "thermal sep."),
            ("MEP",     "ceiling_void.min_clearance_mm", 150.0, "mm", "good practice", ""),
        ]
        for code, key, val, units, cite, notes in rules:
            self.set_rule(code, key, val, units, cite, notes)
