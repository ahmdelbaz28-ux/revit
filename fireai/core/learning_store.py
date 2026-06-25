from __future__ import annotations

"""
learning_store.py — Experience-Based Learning Store for FireAI
=========================================================
Adaptive learning system that stores analysis experience and recalibrates
confidence thresholds based on actual performance data.

This module provides LearningStore for continuous improvement of
confidence estimation based on real-world analysis results.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Tuple

# Constants from V10 (never go below these)
_CONFIDENCE_HIGH_THRESHOLD: float = 0.90  # ≥ 90 % → HIGH
_CONFIDENCE_MEDIUM_THRESHOLD: float = 0.75  # ≥ 75 % → MEDIUM

logger = logging.getLogger(__name__)


class LearningStore:
    """Experience-based learning store with adaptive threshold calibration.

    Stores analysis experiences and recalibrates confidence thresholds
    based on actual compliant results.
    """

    def __init__(self, db_path: str = "fireai_learning.sqlite3"):
        """Initialize LearningStore with SQLite database.

        Args:
            db_path: Path to SQLite database file

        """
        # Use check_same_thread=False for single-process access
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("LearningStore initialized: %s", db_path)

    def _create_tables(self):
        """Create learning and calibration tables."""
        cursor = self.conn.cursor()

        # Experience table - stores individual analysis results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experience (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                room_id TEXT NOT NULL,
                geometry_hash TEXT NOT NULL,
                room_area_m2 REAL NOT NULL,
                occupancy TEXT NOT NULL,
                detector_type TEXT NOT NULL,
                solver_used TEXT NOT NULL,
                coverage_pct REAL NOT NULL,
                confidence_score REAL NOT NULL,
                confidence_level TEXT NOT NULL,
                resilience_pass_rate REAL,
                wall_violation_count INTEGER NOT NULL,
                greedy_retries INTEGER NOT NULL,
                proof_valid INTEGER NOT NULL,
                compliant INTEGER NOT NULL,
                timestamp_utc TEXT NOT NULL,
                UNIQUE(project_id, room_id, geometry_hash, timestamp_utc)
            )
        """)

        # Calibration metadata table - stores threshold calibration state
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calibration_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                high_threshold REAL NOT NULL,
                medium_threshold REAL NOT NULL,
                calibrated_at TEXT NOT NULL,
                records_count INTEGER NOT NULL
            )
        """)

        self.conn.commit()
        logger.info("Learning tables created/verified")

    def store(
        self,
        project_id: str,
        room_id: str,
        geometry_hash: str,
        room_area_m2: float,
        occupancy: str,
        detector_type: str,
        solver_used: str,
        coverage_pct: float,
        confidence_score: float,
        confidence_level: str,
        resilience_pass_rate: Optional[float],
        wall_violation_count: int,
        greedy_retries: int,
        proof_valid: bool,
        compliant: bool,
        timestamp_utc: str,
    ) -> bool:
        """Store a single analysis experience.

        Args:
            project_id: Project identifier
            room_id: Room identifier
            geometry_hash: Hash of room geometry
            room_area_m2: Room area in square meters
            occupancy: Occupancy type
            detector_type: Detector type used
            solver_used: Solver algorithm used
            coverage_pct: Coverage percentage
            confidence_score: Raw confidence score
            confidence_level: Confidence level (HIGH/MEDIUM/LOW)
            resilience_pass_rate: Resilience pass rate
            wall_violation_count: Number of wall distance violations
            greedy_retries: Number of greedy retries
            proof_valid: Whether proof is valid
            compliant: Whether result is compliant
            timestamp_utc: UTC timestamp

        Returns:
            True if stored successfully, False otherwise

        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO experience (
                    project_id, room_id, geometry_hash, room_area_m2,
                    occupancy, detector_type, solver_used, coverage_pct,
                    confidence_score, confidence_level, resilience_pass_rate,
                    wall_violation_count, greedy_retries, proof_valid, compliant,
                    timestamp_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    project_id,
                    room_id,
                    geometry_hash,
                    room_area_m2,
                    occupancy,
                    detector_type,
                    solver_used,
                    coverage_pct,
                    confidence_score,
                    confidence_level,
                    resilience_pass_rate,
                    wall_violation_count,
                    greedy_retries,
                    1 if proof_valid else 0,
                    1 if compliant else 0,
                    timestamp_utc,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.warning("Failed to store experience: %s", e)
            return False

    def get_calibrated_thresholds(self) -> Tuple[float, float]:
        """Get calibrated confidence thresholds.

        Returns:
            Tuple of (high_threshold, medium_threshold)
            Never returns below V10 constants.

        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT high_threshold, medium_threshold, records_count
            FROM calibration_meta WHERE id = 1
        """)
        row = cursor.fetchone()

        if row:
            high = max(row["high_threshold"], _CONFIDENCE_HIGH_THRESHOLD)
            medium = max(row["medium_threshold"], _CONFIDENCE_MEDIUM_THRESHOLD)
            return (high, medium)

        # No calibration - return V10 defaults
        return (_CONFIDENCE_HIGH_THRESHOLD, _CONFIDENCE_MEDIUM_THRESHOLD)

    def maybe_recalibrate(self, force: bool = False) -> bool:
        """Recalibrate thresholds if enough new records exist.

        Args:
            force: Force recalibration regardless of record count

        Returns:
            True if recalibrated, False otherwise

        """
        cursor = self.conn.cursor()

        # Get current experience count
        cursor.execute("SELECT COUNT(*) as cnt FROM experience WHERE compliant = 1")
        result = cursor.fetchone()
        current_count = result["cnt"] if result else 0

        # Get last calibration record count
        cursor.execute("SELECT records_count FROM calibration_meta WHERE id = 1")
        row = cursor.fetchone()
        last_count = row["records_count"] if row else 0

        # Check if threshold met
        if force or (current_count > last_count + 500):
            return self.recalibrate()

        return False

    def recalibrate(self) -> bool:
        """Recalibrate thresholds based on compliant experiences.

        Uses 10th percentile of confidence scores from compliant results.
        Never sets thresholds below V10 constants.

        Returns:
            True if recalibrated, False otherwise

        """
        cursor = self.conn.cursor()

        # Get compliant experiences
        cursor.execute("""
            SELECT confidence_score FROM experience
            WHERE compliant = 1
            ORDER BY confidence_score ASC
        """)
        rows = cursor.fetchall()

        count = len(rows)

        if count < 30:
            logger.info("Not enough compliant records for recalibration: %s < 30", count)
            return False

        # Calculate 10th percentile
        idx = int(count * 0.10)
        idx = min(idx, count - 1)
        tenth_percentile = rows[idx]["confidence_score"]

        # Calculate medium threshold (10th percentile of HIGH scores)
        # For simplicity, use tenth_percentile * 0.85 as medium
        medium = tenth_percentile * 0.85

        # Ensure we don't go below V10 constants
        high = max(tenth_percentile, _CONFIDENCE_HIGH_THRESHOLD)
        medium = max(medium, _CONFIDENCE_MEDIUM_THRESHOLD)

        # Store calibration
        cursor.execute(
            """
            INSERT OR REPLACE INTO calibration_meta (
                id, high_threshold, medium_threshold, calibrated_at, records_count
            ) VALUES (1, ?, ?, ?, ?)
        """,
            (
                high,
                medium,
                datetime.now(timezone.utc).isoformat(),  # V54 FIX (AUDIT-012): timezone-aware UTC
                count,
            ),
        )
        self.conn.commit()

        logger.info("Recalibrated: high=%s, medium=%s, records=%s", high, medium, count)
        return True

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("LearningStore connection closed")
