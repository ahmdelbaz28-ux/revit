"""fireai/agents/learning_agent.py — Knowledge Accumulation Agent
=================================================================
Persistent memory store using SQLite. Stores design experiences,
discovers and registers design patterns, retrieves similar scenarios
via weighted feature comparison.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── data classes ──────────────────────────────────────────────────────────────


@dataclass
class DesignExperience:
    experience_id: str = ""
    room_config: str = ""  # JSON string of room geometry/config
    detector_count: int = 0
    coverage_pct: float = 0.0
    compliance_passed: bool = False
    patterns_used: List[str] = field(default_factory=list)
    outcome: str = ""  # "success", "partial", "failure"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


@dataclass
class DesignPattern:
    pattern_id: str = ""
    room_type: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)
    solution_summary: str = ""
    effectiveness_score: float = 0.0
    usage_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── similarity matching ─────────────────────────────────────────────────────


def _extract_features_from_config(config_json: str) -> Dict[str, float]:
    try:
        config = json.loads(config_json) if isinstance(config_json, str) else {}
    except (json.JSONDecodeError, TypeError):
        config = {}
    return {
        "room_area": float(config.get("room_area", 0)),
        "ceiling_height": float(config.get("ceiling_height", 3.0)),
        "width": float(config.get("width", 0)),
        "length": float(config.get("length", 0)),
        "obstruction_count": float(config.get("obstruction_count", 0)),
        "ceiling_type": 1.0 if config.get("ceiling_type") in ("flat", "FLAT") else (
            2.0 if config.get("ceiling_type") in ("sloped", "SLOPED", "beam", "BEAM") else 3.0
        ),
    }


def _extract_room_features(design: Any) -> Dict[str, float]:
    if isinstance(design, dict):
        return {
            "room_area": float(design.get("area", design.get("room_area", 0))),
            "ceiling_height": float(design.get("ceiling_height", 3.0)),
            "width": float(design.get("width", 0)),
            "length": float(design.get("length", 0)),
            "obstruction_count": float(design.get("obstruction_count", 0)),
            "ceiling_type": 1.0,
        }
    return {
        "room_area": 0.0,
        "ceiling_height": 3.0,
        "width": 0.0,
        "length": 0.0,
        "obstruction_count": 0.0,
        "ceiling_type": 1.0,
    }


def _compute_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    weights = {
        "room_area": 0.25,
        "ceiling_height": 0.20,
        "width": 0.15,
        "length": 0.15,
        "obstruction_count": 0.15,
        "ceiling_type": 0.10,
    }
    total_weight = 0.0
    total = 0.0
    for key, weight in weights.items():
        va = a.get(key, 0)
        vb = b.get(key, 0)
        if va == 0 and vb == 0:
            continue
        denom = max(va, vb, 0.01)
        diff = abs(va - vb) / denom
        sim = max(0.0, 1.0 - diff)
        total += weight * sim
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return total / total_weight


# ── LearningAgent ────────────────────────────────────────────────────────────


class LearningAgent:
    """Agent that accumulates knowledge across sessions:
    - Persistent memory store (SQLite)
    - Experience storage (design decisions, outcomes)
    - Knowledge accumulation pattern library
    - Experience retrieval for similar scenarios
    """

    def __init__(self, db_path: str = "fireai_learning.sqlite3"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                experience_id TEXT PRIMARY KEY,
                room_config TEXT NOT NULL,
                detector_count INTEGER NOT NULL,
                coverage_pct REAL NOT NULL,
                compliance_passed INTEGER NOT NULL,
                patterns_used TEXT NOT NULL,
                outcome TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                pattern_id TEXT PRIMARY KEY,
                room_type TEXT NOT NULL,
                constraints TEXT NOT NULL,
                solution_summary TEXT NOT NULL,
                effectiveness_score REAL NOT NULL,
                usage_count INTEGER NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pattern_experience_links (
                pattern_id TEXT NOT NULL,
                experience_id TEXT NOT NULL,
                PRIMARY KEY (pattern_id, experience_id)
            )
        """)
        self.conn.commit()

    def store_experience(self, experience: DesignExperience) -> str:
        exp_id = experience.experience_id or str(uuid.uuid4())
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO experiences
            (experience_id, room_config, detector_count, coverage_pct,
             compliance_passed, patterns_used, outcome, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                exp_id,
                experience.room_config,
                experience.detector_count,
                experience.coverage_pct,
                1 if experience.compliance_passed else 0,
                json.dumps(experience.patterns_used),
                experience.outcome,
                experience.timestamp,
            ),
        )
        for pid in experience.patterns_used:
            cursor.execute(
                "INSERT OR IGNORE INTO pattern_experience_links (pattern_id, experience_id) VALUES (?, ?)",
                (pid, exp_id),
            )
        self.conn.commit()
        logger.info("Stored experience %s", exp_id)
        return exp_id

    def retrieve_similar(self, design: Any, top_k: int = 5) -> List[DesignExperience]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM experiences ORDER BY timestamp DESC")
        rows = cursor.fetchall()

        query_features = _extract_room_features(design)

        scored: List[tuple] = []
        for row in rows:
            exp_features = _extract_features_from_config(row["room_config"])
            sim = _compute_similarity(query_features, exp_features)
            scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: List[DesignExperience] = []
        for _sim, row in scored[:top_k]:
            results.append(
                DesignExperience(
                    experience_id=row["experience_id"],
                    room_config=row["room_config"],
                    detector_count=row["detector_count"],
                    coverage_pct=row["coverage_pct"],
                    compliance_passed=bool(row["compliance_passed"]),
                    patterns_used=json.loads(row["patterns_used"]),
                    outcome=row["outcome"],
                    timestamp=row["timestamp"],
                )
            )
        return results

    def get_pattern(self, pattern_id: str) -> Optional[DesignPattern]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM patterns WHERE pattern_id = ?", (pattern_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return DesignPattern(
            pattern_id=row["pattern_id"],
            room_type=row["room_type"],
            constraints=json.loads(row["constraints"]),
            solution_summary=row["solution_summary"],
            effectiveness_score=row["effectiveness_score"],
            usage_count=row["usage_count"],
        )

    def register_pattern(self, pattern: DesignPattern) -> str:
        pid = pattern.pattern_id or str(uuid.uuid4())
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO patterns
            (pattern_id, room_type, constraints, solution_summary,
             effectiveness_score, usage_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                pid,
                pattern.room_type,
                json.dumps(pattern.constraints),
                pattern.solution_summary,
                pattern.effectiveness_score,
                pattern.usage_count,
            ),
        )
        self.conn.commit()
        logger.info("Registered pattern %s (type=%s, score=%.3f)", pid, pattern.room_type, pattern.effectiveness_score)
        return pid

    def suggest_patterns(self, design: Any) -> List[DesignPattern]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM patterns ORDER BY effectiveness_score DESC, usage_count DESC")
        rows = cursor.fetchall()
        if not rows:
            return []

        query_features = _extract_room_features(design)

        scored: List[tuple] = []
        for row in rows:
            constraints = json.loads(row["constraints"]) if isinstance(row["constraints"], str) else row["constraints"]
            pat_features = {
                "room_area": float(constraints.get("max_area", constraints.get("min_area", 0))),
                "ceiling_height": float(constraints.get("max_ceiling", constraints.get("min_ceiling", 0))),
                "obstruction_count": float(constraints.get("max_obstructions", 100)),
                "ceiling_type": 2.0 if constraints.get("ceiling_type") in ("sloped", "SLOPED", "beam", "BEAM") else 1.0,
                "width": 0.0,
                "length": 0.0,
            }
            sim = _compute_similarity(query_features, pat_features)

            eff = row["effectiveness_score"]
            usage = min(row["usage_count"] / 100.0, 1.0)
            combined = 0.6 * sim + 0.3 * eff + 0.1 * usage
            scored.append((combined, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: List[DesignPattern] = []
        for _score, row in scored[:5]:
            results.append(
                DesignPattern(
                    pattern_id=row["pattern_id"],
                    room_type=row["room_type"],
                    constraints=json.loads(row["constraints"]),
                    solution_summary=row["solution_summary"],
                    effectiveness_score=row["effectiveness_score"],
                    usage_count=row["usage_count"],
                )
            )
        return results

    def close(self) -> None:
        if self.conn:
            self.conn.close()
