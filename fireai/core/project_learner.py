"""fireai/core/project_learner.py  V1.0
=====================================
Standalone ProjectLearner -- pure Python, no external deps.
Designed to be imported by BuildingEngine and its output
attached as BuildingReport.project_profile.

DO NOT modify DensityOptimizer, FloorAnalyser, or BuildingEngine.

Integration with BuildingEngine
--------------------------------
After BuildingEngine finishes analysing all floors:

    from fireai.core.project_learner import ProjectLearner

    learner = ProjectLearner(building_id=building_report.building_id)
    for floor in building_report.floor_reports:
        for s in floor.room_summaries:
            eff = (
                s.detector_count / s.theoretical_lower_bound
                if s.theoretical_lower_bound > 0 else 1.0
            )
            learner.record(
                name       = s.name,
                width      = s.width,
                length     = s.length,
                strategy   = s.method,
                efficiency = eff,
            )
    building_report.project_profile = learner.profile()

hint_for() is provided for future use (e.g. warm-starting new rooms
added to the same building). It is NOT called during automated design.

Persistence
-----------
Pass persist_path to save/reload room records between sessions.
The profile is always recomputed from raw records (no stale cache).
"""

from __future__ import annotations

import datetime
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

# ── data classes ─────────────────────────────────────────────


@dataclass
class RoomRecord:
    """One analysed room fed into the learner."""

    name: str
    width: float
    length: float
    strategy: str  # e.g. "hexG_x", "rect_4x3"
    efficiency: float  # actual_count / theoretical_lower_bound


@dataclass
class RoomCluster:
    """A cluster of similar rooms in (width, length) space."""

    cluster_id: int
    centroid_w: float
    centroid_l: float
    member_names: List[str]
    dominant_strategy: str
    avg_efficiency: float
    aspect_min: float
    aspect_max: float
    hint_strategy: str  # recommended strategy for new rooms near this cluster


@dataclass
class BuildingProjectProfile:
    """Attached as BuildingReport.project_profile after BuildingEngine finishes.
    Purely statistical -- no design decisions are made from this data.
    """

    building_id: str
    total_rooms: int
    n_clusters: int
    clusters: List[RoomCluster]
    global_dominant_strategy: str
    strategy_distribution: Dict[str, float]  # strategy -> win %
    avg_efficiency: float
    generated_at: str  # ISO UTC


# ── ProjectLearner ────────────────────────────────────────────


class ProjectLearner:
    """Learns room-pattern clusters for one building.

    Algorithm: k-means++ on (width, length) space.
    k chosen automatically via elbow method (max k=5).
    Pure Python -- no numpy, scipy, or sklearn.
    """

    def __init__(
        self,
        building_id: str = "default",
        persist_path: Optional[str] = None,
    ):
        self.building_id = building_id
        self.persist_path = persist_path
        self._records: List[RoomRecord] = []

        if persist_path and os.path.exists(persist_path):
            self._load()

    # ── public API ────────────────────────────────────────────

    def record(
        self,
        name: str,
        width: float,
        length: float,
        strategy: str,
        efficiency: float,
    ) -> None:
        """Feed one analysed room into the learner."""
        self._records.append(
            RoomRecord(
                name=name,
                width=width,
                length=length,
                strategy=strategy,
                efficiency=round(efficiency, 4),
            )
        )
        if self.persist_path:
            self._save()

    def profile(self) -> BuildingProjectProfile:
        """Compute and return the building profile.
        Always recomputed from raw records -- no stale state.
        """
        return self._build_profile()

    def hint_for(self, width: float, length: float) -> Optional[str]:
        """Return the dominant strategy of the nearest cluster.
        Returns None if fewer than 3 rooms recorded.
        For engineer information only -- not called during automated design.
        """
        if len(self._records) < 3:
            return None
        p = self._build_profile()
        best = min(
            p.clusters,
            key=lambda c: (width - c.centroid_w) ** 2 + (length - c.centroid_l) ** 2,
        )
        return best.hint_strategy

    def summary(self) -> str:
        """Return a human-readable summary of the profile."""
        n = len(self._records)
        if n < 3:
            return f"ProjectLearner '{self.building_id}': {n} room(s) recorded (need >=3 to profile)"
        p = self._build_profile()
        lines = [
            f"ProjectLearner '{self.building_id}': "
            f"{p.total_rooms} rooms | {p.n_clusters} clusters | "
            f"dominant={p.global_dominant_strategy} | "
            f"avg_eff={p.avg_efficiency:.2f}",
        ]
        for c in p.clusters:
            lines.append(
                f"  Cluster {c.cluster_id}: "
                f"centroid=({c.centroid_w:.1f}x{c.centroid_l:.1f})m  "
                f"n={len(c.member_names)}  "
                f"strategy={c.dominant_strategy}  "
                f"eff={c.avg_efficiency:.2f}  "
                f"aspect=[{c.aspect_min:.2f},{c.aspect_max:.2f}]"
            )
        return "\n".join(lines)

    # ── profile builder ───────────────────────────────────────

    def _build_profile(self) -> BuildingProjectProfile:
        records = self._records
        if not records:
            return BuildingProjectProfile(
                building_id=self.building_id,
                total_rooms=0,
                n_clusters=0,
                clusters=[],
                global_dominant_strategy="unknown",
                strategy_distribution={},
                avg_efficiency=0.0,
                generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )

        pts = [(r.width, r.length) for r in records]
        k = self._elbow_k(pts, max_k=min(5, len(records)))
        labels, centroids = self._kmeans(pts, k)

        clusters: List[RoomCluster] = []
        for cid in range(k):
            idxs = [i for i, lbl in enumerate(labels) if lbl == cid]
            if not idxs:
                continue
            members = [records[i].name for i in idxs]
            strategies = [records[i].strategy for i in idxs]
            effs = [records[i].efficiency for i in idxs]
            aspects = [
                max(records[i].width, records[i].length) / max(min(records[i].width, records[i].length), 0.01)
                for i in idxs
            ]
            dom = Counter(strategies).most_common(1)[0][0]
            clusters.append(
                RoomCluster(
                    cluster_id=cid,
                    centroid_w=round(centroids[cid][0], 2),
                    centroid_l=round(centroids[cid][1], 2),
                    member_names=members,
                    dominant_strategy=dom,
                    avg_efficiency=round(sum(effs) / len(effs), 4),
                    aspect_min=round(min(aspects), 3),
                    aspect_max=round(max(aspects), 3),
                    hint_strategy=dom,
                )
            )

        all_strategies = [r.strategy for r in records]
        strategy_counts = Counter(all_strategies)
        total = len(records)
        strategy_dist = {s: round(100.0 * c / total, 1) for s, c in strategy_counts.most_common()}
        global_dom = strategy_counts.most_common(1)[0][0]
        avg_eff = sum(r.efficiency for r in records) / total

        return BuildingProjectProfile(
            building_id=self.building_id,
            total_rooms=total,
            n_clusters=len(clusters),
            clusters=clusters,
            global_dominant_strategy=global_dom,
            strategy_distribution=strategy_dist,
            avg_efficiency=round(avg_eff, 4),
            generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    # ── k-means++ ─────────────────────────────────────────────

    def _kmeans(
        self,
        pts: List[Tuple[float, float]],
        k: int,
        max_iter: int = 150,
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        import random

        random.seed(42)
        n = len(pts)
        if n <= k:
            return list(range(n)), list(pts)

        # k-means++ initialisation
        centroids = [pts[random.randint(0, n - 1)]]
        while len(centroids) < k:
            d2 = [min((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 for c in centroids) for p in pts]
            total = sum(d2) + 1e-9
            r = random.random() * total
            cum = 0.0
            chosen = pts[-1]
            for p, d in zip(pts, d2, strict=False):
                cum += d
                if cum >= r:
                    chosen = p
                    break
            centroids.append(chosen)

        labels = [0] * n
        for _ in range(max_iter):
            new_labels = [
                min(range(k), key=lambda c: (pts[i][0] - centroids[c][0]) ** 2 + (pts[i][1] - centroids[c][1]) ** 2)
                for i in range(n)
            ]
            if new_labels == labels:
                break
            labels = new_labels
            for c in range(k):
                mems = [pts[i] for i, lbl in enumerate(labels) if lbl == c]
                if mems:
                    centroids[c] = (
                        sum(m[0] for m in mems) / len(mems),
                        sum(m[1] for m in mems) / len(mems),
                    )
        return labels, centroids

    def _elbow_k(
        self,
        pts: List[Tuple[float, float]],
        max_k: int,
    ) -> int:
        """Choose k via elbow method (max second derivative of inertia)."""
        if max_k <= 1 or len(pts) <= 2:
            return 1
        inertias = []
        for k in range(1, max_k + 1):
            labels, centroids = self._kmeans(pts, k)
            inertia = sum(
                min((p[0] - centroids[c][0]) ** 2 + (p[1] - centroids[c][1]) ** 2 for c in range(k)) for p in pts
            )
            inertias.append(inertia)

        best_k, best_dd = 1, 0.0
        for i in range(1, len(inertias) - 1):
            dd = abs(inertias[i - 1] - 2 * inertias[i] + inertias[i + 1])
            if dd > best_dd:
                best_dd, best_k = dd, i + 1
        return max(1, best_k)

    # ── persistence ───────────────────────────────────────────

    def _save(self) -> None:
        data: dict = {}
        if os.path.exists(self.persist_path):
            with open(self.persist_path) as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}
        data[f"project_{self.building_id}"] = {
            "building_id": self.building_id,
            "records": [asdict(r) for r in self._records],
        }
        with open(self.persist_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        try:
            with open(self.persist_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, OSError):
            return  # empty or missing file — start fresh
        key = f"project_{self.building_id}"
        if key in data:
            raw = data[key].get("records", [])
            self._records = [RoomRecord(**r) for r in raw]
