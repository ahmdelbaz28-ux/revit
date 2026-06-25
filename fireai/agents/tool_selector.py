"""fireai/agents/tool_selector.py — Dynamic Tool Routing with Capability Scoring
================================================================================
Scores available tools by capability match, provides context-aware
orchestration, and adaptive routing based on historical success.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── data classes ──────────────────────────────────────────────────────────────


@dataclass
class Capability:
    name: str
    version: str = "1.0"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Task:
    task_id: str = ""
    description: str = ""
    required_capabilities: List[str] = field(default_factory=list)
    complexity: float = 0.5  # 0.0 (simple) to 1.0 (very complex)
    time_constraint: float = 0.5  # 0.0 (no rush) to 1.0 (urgent)
    required_standards: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Context:
    design_complexity: float = 0.5
    time_constraints: float = 0.5
    required_standards: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RoutingLog:
    task_id: str
    selected_tool: str
    scores: List[Tuple[str, float]]
    context: str  # JSON
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {"task_id": self.task_id, "selected_tool": self.selected_tool, "scores": self.scores, "context": self.context, "timestamp": self.timestamp}


# ── ToolSelector ─────────────────────────────────────────────────────────────


class ToolSelector:
    """Dynamic tool routing with capability scoring:
    - Scores available tools by capability match
    - Context-aware orchestration (picks best tool for job)
    - Adaptive routing based on historical success
    """

    DIRECTNESS_WEIGHT = 0.4
    ACCURACY_WEIGHT = 0.3
    PERFORMANCE_WEIGHT = 0.2
    AVAILABILITY_WEIGHT = 0.1

    def __init__(self, db_path: str = "fireai_learning.sqlite3"):
        self.db_path = db_path
        self._tools: Dict[str, dict] = {}
        self._score_fns: Dict[str, Callable] = {}
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tool_routing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                selected_tool TEXT NOT NULL,
                scores TEXT NOT NULL,
                context TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tool_success_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                task_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                execution_time_ms REAL NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def register_tool(
        self,
        name: str,
        capabilities: List[Capability],
        score_fn: Optional[Callable] = None,
    ) -> None:
        self._tools[name] = {
            "capabilities": {c.name for c in capabilities},
            "capability_details": capabilities,
            "registered_at": time.time(),
        }
        if score_fn is not None:
            self._score_fns[name] = score_fn
        else:

            def _default_score(task: Task, ctx: Context) -> float:
                return 0.5

            self._score_fns[name] = _default_score
        logger.info("Registered tool '%s' with %d capabilities", name, len(capabilities))

    def select_tool(self, task: Task, context: Context) -> Optional[str]:
        scored = self.score_tools(task, context)
        if not scored:
            return None
        best_tool = scored[0][0]

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tool_routing_log
            (task_id, selected_tool, scores, context, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                task.task_id or str(uuid.uuid4()),
                best_tool,
                json.dumps([(name, round(s, 4)) for name, s in scored]),
                json.dumps(asdict(context)),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

        logger.info("Selected tool '%s' for task '%s' (score=%.4f)", best_tool, task.description, scored[0][1])
        return best_tool

    def score_tools(self, task: Task, context: Context) -> List[Tuple[str, float]]:
        if not self._tools:
            return []

        results: List[Tuple[str, float]] = []
        for name, tool_info in self._tools.items():
            score = self._compute_score(name, tool_info, task, context)
            results.append((name, round(score, 4)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def _compute_score(self, name: str, tool_info: dict, task: Task, context: Context) -> float:
        tool_caps = tool_info["capabilities"]
        required = set(task.required_capabilities)

        if not required:
            directness = 0.5
        else:
            matched = required & tool_caps
            directness = len(matched) / max(len(required), 1) if required else 0.5

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT AVG(success) as avg_success, COUNT(*) as cnt
            FROM tool_success_history
            WHERE tool_name = ?
        """,
            (name,),
        )
        hist_row = cursor.fetchone()
        accuracy = float(hist_row["avg_success"]) if hist_row and hist_row["avg_success"] is not None else 0.5

        cursor.execute(
            """
            SELECT AVG(execution_time_ms) as avg_time
            FROM tool_success_history
            WHERE tool_name = ?
        """,
            (name,),
        )
        perf_row = cursor.fetchone()
        avg_time = perf_row["avg_time"] if perf_row and perf_row["avg_time"] is not None else 100.0
        performance = max(0.0, 1.0 - avg_time / 10000.0)  # normalize: 10s = 0

        availability = 1.0

        custom_score = self._score_fns.get(name, lambda t, c: 0.5)(task, context)
        custom_score = max(0.0, min(1.0, custom_score))

        scores = [directness, accuracy, performance, availability]
        weights = [self.DIRECTNESS_WEIGHT, self.ACCURACY_WEIGHT, self.PERFORMANCE_WEIGHT, self.AVAILABILITY_WEIGHT]

        weighted = sum(s * w for s, w in zip(scores, weights, strict=False))
        blended = 0.7 * weighted + 0.3 * custom_score

        complexity_factor = 1.0 - context.design_complexity * 0.2
        return blended * complexity_factor

    def record_result(
        self,
        tool_name: str,
        task: Task,
        success: bool,
        execution_time_ms: float = 0.0,
    ) -> None:
        cursor = self.conn.cursor()
        task_type = task.description[:100]
        cursor.execute(
            """
            INSERT INTO tool_success_history
            (tool_name, task_type, success, execution_time_ms, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                tool_name,
                task_type,
                1 if success else 0,
                execution_time_ms,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        logger.info("Recorded result for tool '%s': success=%s (%.0fms)", tool_name, success, execution_time_ms)

    def get_tool_summary(self) -> Dict[str, Dict[str, Any]]:
        summary: Dict[str, Dict[str, Any]] = {}
        for name, info in self._tools.items():
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) as runs,
                       AVG(success) as success_rate,
                       AVG(execution_time_ms) as avg_time
                FROM tool_success_history
                WHERE tool_name = ?
            """,
                (name,),
            )
            row = cursor.fetchone()
            summary[name] = {
                "capabilities": sorted(info["capabilities"]),
                "runs": row["runs"] if row else 0,
                "success_rate": round(float(row["success_rate"]), 4) if row and row["success_rate"] is not None else 0.0,
                "avg_execution_time_ms": round(float(row["avg_time"]), 2) if row and row["avg_time"] is not None else 0.0,
            }
        return summary

    def close(self) -> None:
        if self.conn:
            self.conn.close()
