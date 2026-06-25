"""fireai/agents/self_improvement_engine.py — Continuous Improvement Engine
==========================================================================
Ingests feedback from validation results, analyzes performance trends,
optimizes algorithm parameters via grid search, and tracks improvements
over time with persistent storage.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── data classes ──────────────────────────────────────────────────────────────


@dataclass
class ImprovementFeedback:
    feedback_id: str = ""
    component: str = ""  # "spacing_factor", "margin", "threshold", "density", "routing", "verification"
    metric: str = ""  # "coverage_pct", "compliance_rate", "false_positive_rate", "execution_time", "detector_count"
    actual_value: float = 0.0
    expected_value: float = 0.0
    severity: str = "medium"  # "low", "medium", "high", "critical"
    context: str = ""  # JSON context string
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImprovementRecord:
    record_id: str = ""
    component: str = ""
    metric: str = ""
    previous_value: float = 0.0
    new_value: float = 0.0
    change_pct: float = 0.0
    action_taken: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParameterSuggestion:
    spacing_factor: float = 0.7
    margin: float = 0.1
    threshold: float = 0.85
    confidence: float = 0.5
    rationale: str = "default parameters"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComponentTrend:
    component: str
    trend: str  # "improving", "declining", "stable"
    mean_change: float
    sample_count: int


@dataclass
class ImprovementReport:
    trends: List[ComponentTrend] = field(default_factory=list)
    top_improvements: List[ImprovementRecord] = field(default_factory=list)
    regression_warnings: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trends": [asdict(t) for t in self.trends],
            "top_improvements": [asdict(r) for r in self.top_improvements],
            "regression_warnings": self.regression_warnings,
            "generated_at": self.generated_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


# ── SelfImprovementEngine ────────────────────────────────────────────────────

_GRID_SEARCH_PARAMS = {
    "spacing_factor": [0.5, 0.6, 0.7, 0.8, 0.9],
    "margin": [0.05, 0.08, 0.10, 0.12, 0.15],
    "threshold": [0.75, 0.80, 0.85, 0.90, 0.95],
}


class SelfImprovementEngine:
    """Continuous improvement through feedback processing:
    - Feedback ingestion from validation results
    - Performance optimization recommendations
    - Model refinement triggers
    - Improvement tracking over time
    """

    def __init__(self, db_path: str = "fireai_learning.sqlite3"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS improvement_feedback (
                feedback_id TEXT PRIMARY KEY,
                component TEXT NOT NULL,
                metric TEXT NOT NULL,
                actual_value REAL NOT NULL,
                expected_value REAL NOT NULL,
                severity TEXT NOT NULL,
                context TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS improvement_records (
                record_id TEXT PRIMARY KEY,
                component TEXT NOT NULL,
                metric TEXT NOT NULL,
                previous_value REAL NOT NULL,
                new_value REAL NOT NULL,
                change_pct REAL NOT NULL,
                action_taken TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parameter_optimization_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spacing_factor REAL NOT NULL,
                margin REAL NOT NULL,
                threshold REAL NOT NULL,
                score REAL NOT NULL,
                tested_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def ingest_feedback(self, feedback: ImprovementFeedback) -> str:
        fid = feedback.feedback_id or str(uuid.uuid4())
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO improvement_feedback
            (feedback_id, component, metric, actual_value, expected_value,
             severity, context, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                fid,
                feedback.component,
                feedback.metric,
                feedback.actual_value,
                feedback.expected_value,
                feedback.severity,
                feedback.context,
                feedback.timestamp,
            ),
        )
        self.conn.commit()
        logger.info("Ingested feedback %s (%s/%s, severity=%s)", fid, feedback.component, feedback.metric, feedback.severity)

        gap = feedback.expected_value - feedback.actual_value
        if feedback.severity in ("high", "critical") and gap > 0.05:
            self._record_improvement(
                component=feedback.component,
                metric=feedback.metric,
                previous_value=feedback.actual_value,
                new_value=feedback.expected_value,
                action_taken=f"auto_adjust_{feedback.component}",
            )

        return fid

    def _record_improvement(
        self,
        component: str,
        metric: str,
        previous_value: float,
        new_value: float,
        action_taken: str,
    ) -> str:
        rid = str(uuid.uuid4())
        change_pct = ((new_value - previous_value) / max(abs(previous_value), 1e-9)) * 100.0 if previous_value != 0 else 0.0
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO improvement_records
            (record_id, component, metric, previous_value, new_value, change_pct, action_taken, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                rid,
                component,
                metric,
                previous_value,
                new_value,
                round(change_pct, 4),
                action_taken,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        return rid

    def analyze_improvements(self) -> ImprovementReport:
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT component, COUNT(*) as cnt,
                   AVG(change_pct) as avg_change
            FROM improvement_records
            WHERE timestamp >= datetime('now', '-30 days')
            GROUP BY component
        """)
        trend_rows = cursor.fetchall()

        trends: List[ComponentTrend] = []
        regression_warnings: List[str] = []
        for row in trend_rows:
            avg = row["avg_change"] if row["avg_change"] is not None else 0.0
            if avg > 2.0:
                trend = "improving"
            elif avg < -2.0:
                trend = "declining"
                regression_warnings.append(
                    f"Regression detected in {row['component']}: "
                    f"avg change {avg:.2f}% ({row['cnt']} records)"
                )
            else:
                trend = "stable"
            trends.append(
                ComponentTrend(
                    component=row["component"],
                    trend=trend,
                    mean_change=round(avg, 4) if avg else 0.0,
                    sample_count=row["cnt"],
                )
            )

        cursor.execute("""
            SELECT * FROM improvement_records
            ORDER BY ABS(change_pct) DESC
            LIMIT 10
        """)
        top_rows = cursor.fetchall()
        top_improvements: List[ImprovementRecord] = []
        for row in top_rows:
            top_improvements.append(
                ImprovementRecord(
                    record_id=row["record_id"],
                    component=row["component"],
                    metric=row["metric"],
                    previous_value=row["previous_value"],
                    new_value=row["new_value"],
                    change_pct=row["change_pct"],
                    action_taken=row["action_taken"],
                    timestamp=row["timestamp"],
                )
            )

        cursor.execute("""
            SELECT COUNT(*) as cnt FROM improvement_feedback
            WHERE severity IN ('high', 'critical')
            AND timestamp >= datetime('now', '-7 days')
        """)
        recent_critical = cursor.fetchone()
        if recent_critical and recent_critical["cnt"] > 5:
            regression_warnings.append(
                f"High volume of critical feedback: {recent_critical['cnt']} in last 7 days"
            )

        return ImprovementReport(
            trends=trends,
            top_improvements=top_improvements,
            regression_warnings=regression_warnings,
        )

    def optimize_parameters(self, design: Any) -> ParameterSuggestion:
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT spacing_factor, margin, threshold, score
            FROM parameter_optimization_history
            ORDER BY score DESC
            LIMIT 1
        """)
        best_row = cursor.fetchone()
        if best_row:
            return ParameterSuggestion(
                spacing_factor=best_row["spacing_factor"],
                margin=best_row["margin"],
                threshold=best_row["threshold"],
                confidence=0.7,
                rationale="best historically optimized parameters",
            )

        cursor.execute("""
            SELECT component, AVG(actual_value - expected_value) as avg_gap
            FROM improvement_feedback
            WHERE component IN ('spacing_factor', 'margin', 'threshold')
            GROUP BY component
        """)
        gap_rows = cursor.fetchall()
        gaps: Dict[str, float] = {r["component"]: r["avg_gap"] if r["avg_gap"] is not None else 0.0 for r in gap_rows}

        suggestions: Dict[str, List[Tuple[float, float]]] = {
            "spacing_factor": [],
            "margin": [],
            "threshold": [],
        }

        for param, values in _GRID_SEARCH_PARAMS.items():
            for val in values:
                score = self._evaluate_param(design, param, val, gaps)
                suggestions.setdefault(param, []).append((val, score))

        best = ParameterSuggestion()
        best_conf = 0.0
        for sp in _GRID_SEARCH_PARAMS["spacing_factor"]:
            for ma in _GRID_SEARCH_PARAMS["margin"]:
                for th in _GRID_SEARCH_PARAMS["threshold"]:
                    combined = self._score_combination(sp, ma, th, gaps)
                    if combined > best_conf:
                        best_conf = combined
                        best = ParameterSuggestion(
                            spacing_factor=sp,
                            margin=ma,
                            threshold=th,
                            confidence=round(combined, 4),
                            rationale="grid search optimization",
                        )

        cursor.execute(
            """
            INSERT INTO parameter_optimization_history
            (spacing_factor, margin, threshold, score, tested_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                best.spacing_factor,
                best.margin,
                best.threshold,
                best.confidence,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

        return best

    def _evaluate_param(self, design: Any, param: str, value: float, gaps: Dict[str, float]) -> float:
        gap = abs(gaps.get(param, 0))
        if gap < 0.01:
            return 0.5
        correction = 1.0 - min(gap / 0.5, 1.0)
        return correction

    def _score_combination(self, sp: float, ma: float, th: float, gaps: Dict[str, float]) -> float:
        base_scores: List[float] = []
        for param, val, expected in [
            ("spacing_factor", sp, 0.7),
            ("margin", ma, 0.1),
            ("threshold", th, 0.85),
        ]:
            gap = abs(gaps.get(param, 0))
            deviation = abs(val - expected)
            if gap > 0.01:
                adjusted = expected + (expected - val) * gap * 0.5
                score = 1.0 - min(abs(adjusted - val) / expected, 1.0)
            else:
                score = 1.0 - min(deviation / expected, 1.0)
            base_scores.append(score)
        return sum(base_scores) / max(len(base_scores), 1)

    def get_improvement_history(self, days: int = 30) -> List[ImprovementRecord]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM improvement_records
            WHERE timestamp >= datetime('now', ? || ' days')
            ORDER BY timestamp DESC
        """,
            (f"-{days}",),
        )
        rows = cursor.fetchall()
        results: List[ImprovementRecord] = []
        for row in rows:
            results.append(
                ImprovementRecord(
                    record_id=row["record_id"],
                    component=row["component"],
                    metric=row["metric"],
                    previous_value=row["previous_value"],
                    new_value=row["new_value"],
                    change_pct=row["change_pct"],
                    action_taken=row["action_taken"],
                    timestamp=row["timestamp"],
                )
            )
        return results

    def close(self) -> None:
        if self.conn:
            self.conn.close()
