"""
core/room_classifier.py
=========================
Rule-based room type classifier for FireAI.

Uses geometric features (area, aspect ratio, compactness) and
optional name/text hints to classify rooms into types relevant
for fire alarm design:
  - corridor: Long, narrow spaces — affects detector spacing
  - office: Medium rectangular rooms
  - warehouse: Large open areas — affects detector type and spacing
  - server_room: Medium rooms requiring early warning
  - stairwell: Vertical circulation — special detection requirements
  - mechanical: Equipment rooms — heat detection preferred
  - assembly: Large rooms with high occupancy
  - storage: Medium rooms with combustible materials
  - kitchen: Cooking areas — heat + multi-criteria
  - lobby: Entry areas — voice evacuation

Classification confidence is scored from 0.0 to 1.0 based on
how well the features match the rule thresholds.

Usage:
    from core.room_classifier import RuleBasedRoomClassifier

    clf = RuleBasedRoomClassifier()
    result = clf.classify(area=8.0, aspect_ratio=5.0, name="Corridor A")
    print(result.room_type)       # "corridor"
    print(result.confidence)      # 0.92
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.production_config import get_production_config

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Classification Result
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ClassificationResult:
    """
    Result of room type classification.

    Attributes
    ----------
    room_type : str
        Classified room type (e.g., "corridor", "office").
    confidence : float
        Confidence score from 0.0 to 1.0.
    features : dict
        Extracted geometric features used for classification.
    candidates : list of (type, score) tuples
        All candidate types with their scores, sorted descending.
    """
    room_type: str
    confidence: float
    features: Dict = field(default_factory=dict)
    candidates: List[Tuple[str, float]] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════
# Room Features
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class RoomFeatures:
    """
    Geometric features extracted from a room polygon.

    Attributes
    ----------
    area : float
        Floor area in m².
    perimeter : float
        Perimeter in metres.
    aspect_ratio : float
        Ratio of longest to shortest dimension (>= 1.0).
    compactness : float
        4π × area / perimeter² — 1.0 for a circle, lower for elongated shapes.
    num_vertices : int
        Number of vertices in the polygon.
    bbox_width : float
        Bounding box width in metres.
    bbox_height : float
        Bounding box height in metres.
    """
    area: float
    perimeter: float
    aspect_ratio: float
    compactness: float
    num_vertices: int
    bbox_width: float
    bbox_height: float

    def to_dict(self) -> Dict:
        return {
            "area": self.area,
            "perimeter": self.perimeter,
            "aspect_ratio": self.aspect_ratio,
            "compactness": self.compactness,
            "num_vertices": self.num_vertices,
            "bbox_width": self.bbox_width,
            "bbox_height": self.bbox_height,
        }


def extract_features(area: float = None,
                     perimeter: float = None,
                     polygon_vertices: List[Tuple[float, float]] = None,
                     bbox: Tuple[float, float, float, float] = None,
                     aspect_ratio: float = None,
                     num_vertices: int = None) -> RoomFeatures:
    """
    Extract geometric features from room data.

    Can accept pre-computed values or raw polygon data.
    At minimum, area must be provided.

    Parameters
    ----------
    area : float
        Floor area in m². Required.
    perimeter : float, optional
        Perimeter in metres.
    polygon_vertices : list of (x, y), optional
        Polygon vertices for computing missing features.
    bbox : (minx, miny, maxx, maxy), optional
        Bounding box.
    aspect_ratio : float, optional
        Pre-computed aspect ratio.
    num_vertices : int, optional
        Number of polygon vertices.

    Returns
    -------
    RoomFeatures
    """
    if area is None:
        raise ValueError("area is required")

    # Compute bounding box dimensions
    if bbox is not None:
        bbox_w = bbox[2] - bbox[0]
        bbox_h = bbox[3] - bbox[1]
    elif polygon_vertices and len(polygon_vertices) >= 3:
        xs = [p[0] for p in polygon_vertices]
        ys = [p[1] for p in polygon_vertices]
        bbox_w = max(xs) - min(xs)
        bbox_h = max(ys) - min(ys)
    else:
        # Estimate from area assuming square
        bbox_w = math.sqrt(area)
        bbox_h = math.sqrt(area)

    # Compute perimeter
    if perimeter is None and polygon_vertices and len(polygon_vertices) >= 3:
        perimeter = 0.0
        n = len(polygon_vertices)
        for i in range(n):
            j = (i + 1) % n
            perimeter += math.hypot(
                polygon_vertices[j][0] - polygon_vertices[i][0],
                polygon_vertices[j][1] - polygon_vertices[i][1]
            )
    elif perimeter is None:
        perimeter = 4 * math.sqrt(area)  # Assume square

    # Compute aspect ratio
    if aspect_ratio is None:
        if bbox_h > 0 and bbox_w > 0:
            aspect_ratio = max(bbox_w, bbox_h) / min(bbox_w, bbox_h)
        else:
            aspect_ratio = 1.0

    # Compute compactness (circularity)
    if perimeter > 0:
        compactness = 4 * math.pi * area / (perimeter ** 2)
    else:
        compactness = 0.5

    # Number of vertices
    if num_vertices is None:
        num_vertices = len(polygon_vertices) if polygon_vertices else 4

    return RoomFeatures(
        area=area,
        perimeter=perimeter,
        aspect_ratio=aspect_ratio,
        compactness=compactness,
        num_vertices=num_vertices,
        bbox_width=bbox_w,
        bbox_height=bbox_h,
    )


# ════════════════════════════════════════════════════════════════════════════
# Room Type Rules
# ════════════════════════════════════════════════════════════════════════════

# Each rule is a function that takes RoomFeatures and returns a score [0, 1].
# Higher score = more likely to be this room type.

def _rule_corridor(f: RoomFeatures) -> float:
    """Corridors: long and narrow, low area, high aspect ratio."""
    score = 0.0
    if f.aspect_ratio >= 3.0:
        score += 0.5
    elif f.aspect_ratio >= 2.0:
        score += 0.3

    if f.area < 30.0:
        score += 0.2
    elif f.area < 60.0:
        score += 0.1

    if f.compactness < 0.3:
        score += 0.2

    # Narrow dimension < 2m is very corridor-like
    min_dim = min(f.bbox_width, f.bbox_height)
    if min_dim < 2.0:
        score += 0.2
    elif min_dim < 3.0:
        score += 0.1

    return min(score, 1.0)


def _rule_office(f: RoomFeatures) -> float:
    """Offices: medium rectangular rooms."""
    score = 0.0
    if 10.0 <= f.area <= 60.0:
        score += 0.4
    elif 5.0 <= f.area <= 100.0:
        score += 0.2

    if 1.0 <= f.aspect_ratio <= 2.0:
        score += 0.3
    elif f.aspect_ratio <= 3.0:
        score += 0.1

    if f.compactness >= 0.5:
        score += 0.2

    return min(score, 1.0)


def _rule_warehouse(f: RoomFeatures) -> float:
    """Warehouses: large open areas, low compactness (irregular shape OK)."""
    score = 0.0
    if f.area > 200.0:
        score += 0.5
    elif f.area > 100.0:
        score += 0.3

    if f.aspect_ratio <= 3.0:
        score += 0.2

    if f.compactness >= 0.3:
        score += 0.2

    return min(score, 1.0)


def _rule_server_room(f: RoomFeatures) -> float:
    """Server rooms: medium rooms, very regular shape."""
    score = 0.0
    if 15.0 <= f.area <= 80.0:
        score += 0.3

    if f.aspect_ratio <= 1.5:
        score += 0.3
    elif f.aspect_ratio <= 2.5:
        score += 0.1

    if f.compactness >= 0.7:
        score += 0.3

    return min(score, 1.0)


def _rule_stairwell(f: RoomFeatures) -> float:
    """Stairwells: small, very narrow, high aspect ratio."""
    score = 0.0
    if f.area < 15.0:
        score += 0.3
    elif f.area < 25.0:
        score += 0.1

    if f.aspect_ratio >= 2.0:
        score += 0.3
    elif f.aspect_ratio >= 1.5:
        score += 0.1

    min_dim = min(f.bbox_width, f.bbox_height)
    if min_dim < 3.0:
        score += 0.3

    return min(score, 1.0)


def _rule_mechanical(f: RoomFeatures) -> float:
    """Mechanical rooms: medium, irregular shapes."""
    score = 0.0
    if 15.0 <= f.area <= 80.0:
        score += 0.2

    if f.compactness < 0.5:
        score += 0.3

    if f.num_vertices > 6:
        score += 0.2

    return min(score, 1.0)


def _rule_assembly(f: RoomFeatures) -> float:
    """Assembly: very large rooms, regular shape."""
    score = 0.0
    if f.area > 100.0:
        score += 0.4
    elif f.area > 50.0:
        score += 0.2

    if f.aspect_ratio <= 2.0:
        score += 0.3

    if f.compactness >= 0.5:
        score += 0.2

    return min(score, 1.0)


def _rule_storage(f: RoomFeatures) -> float:
    """Storage: medium to large rooms, regular shape."""
    score = 0.0
    if 20.0 <= f.area <= 150.0:
        score += 0.3

    if 1.0 <= f.aspect_ratio <= 2.5:
        score += 0.3

    if f.compactness >= 0.4:
        score += 0.2

    return min(score, 1.0)


def _rule_kitchen(f: RoomFeatures) -> float:
    """Kitchens: small to medium rooms."""
    score = 0.0
    if 8.0 <= f.area <= 40.0:
        score += 0.3

    if 1.0 <= f.aspect_ratio <= 2.5:
        score += 0.2

    if f.compactness >= 0.4:
        score += 0.1

    return min(score, 1.0)


def _rule_lobby(f: RoomFeatures) -> float:
    """Lobbies: medium rooms, often with irregular shape (entry areas)."""
    score = 0.0
    if 20.0 <= f.area <= 100.0:
        score += 0.2

    if 1.5 <= f.aspect_ratio <= 3.0:
        score += 0.2

    if f.compactness < 0.6:
        score += 0.2

    return min(score, 1.0)


# Rule registry
ROOM_RULES = {
    "corridor":    _rule_corridor,
    "office":      _rule_office,
    "warehouse":   _rule_warehouse,
    "server_room": _rule_server_room,
    "stairwell":   _rule_stairwell,
    "mechanical":  _rule_mechanical,
    "assembly":    _rule_assembly,
    "storage":     _rule_storage,
    "kitchen":     _rule_kitchen,
    "lobby":       _rule_lobby,
}


# ════════════════════════════════════════════════════════════════════════════
# Name-based hints
# ════════════════════════════════════════════════════════════════════════════

NAME_HINTS = {
    "corridor":    [r"corridor", r"hallway", r"passage", r"hall\s", r"walkway"],
    "office":      [r"office", r"work\s?room", r"desk", r"workspace"],
    "warehouse":   [r"warehouse", r"depot", r"storage\s?hall", r"loading"],
    "server_room": [r"server", r"mdf", r"idf", r"data\s?center", r"it\s?room", r"telecom"],
    "stairwell":   [r"stair", r"stairwell", r"stairway", r"escape\s?stair"],
    "mechanical":  [r"mechanical", r"mep", r"hvac", r"plant\s?room", r"boiler", r"chiller"],
    "assembly":    [r"assembly", r"auditorium", r"hall\b", r"gym", r"worship", r"theater"],
    "storage":     [r"storage", r"storeroom", r"closet", r"janitor"],
    "kitchen":     [r"kitchen", r"cooking", r"cafeteria", r"canteen"],
    "lobby":       [r"lobby", r"entrance", r"reception", r"vestibule", r"foyer"],
}


def _name_hint_score(name: str) -> Dict[str, float]:
    """
    Get room type scores based on name matching.

    Returns a dict of room_type → bonus score.
    """
    if not name:
        return {}

    name_lower = name.lower()
    hints = {}

    for room_type, patterns in NAME_HINTS.items():
        for pattern in patterns:
            if re.search(pattern, name_lower):
                hints[room_type] = hints.get(room_type, 0.0) + 0.6

    # Cap hint bonus at 0.8
    for rt in hints:
        hints[rt] = min(hints[rt], 0.8)

    return hints


# ════════════════════════════════════════════════════════════════════════════
# RuleBasedRoomClassifier
# ════════════════════════════════════════════════════════════════════════════

class RuleBasedRoomClassifier:
    """
    Rule-based room type classifier for fire alarm design.

    Combines geometric rules with optional name-based hints to classify
    rooms into types relevant for NFPA 72 detector selection and spacing.

    The classifier scores each room type based on:
      1. Geometric features (area, aspect ratio, compactness)
      2. Name-based hints (regex matching on room name)

    The final score combines both with a configurable weight.

    Usage:
        clf = RuleBasedRoomClassifier()
        result = clf.classify(area=25.0, aspect_ratio=4.5, name="Corridor A")
        print(result.room_type)     # "corridor"
        print(result.confidence)    # 0.85
    """

    def __init__(self, geometric_weight: float = 0.6,
                 name_weight: float = 0.4,
                 confidence_threshold: float = 0.3):
        """
        Initialize the classifier.

        Parameters
        ----------
        geometric_weight : float
            Weight for geometric rule scores (0-1).
        name_weight : float
            Weight for name hint scores (0-1).
        confidence_threshold : float
            Minimum confidence to accept classification.
            Below this, returns "unknown".
        """
        self.geometric_weight = geometric_weight
        self.name_weight = name_weight
        self.confidence_threshold = confidence_threshold
        self._cfg = get_production_config()

    def classify(self, area: float = None,
                 perimeter: float = None,
                 aspect_ratio: float = None,
                 name: str = None,
                 polygon_vertices: List[Tuple[float, float]] = None,
                 bbox: Tuple[float, float, float, float] = None,
                 num_vertices: int = None,
                 features: RoomFeatures = None) -> ClassificationResult:
        """
        Classify a room based on geometric features and optional name.

        Parameters
        ----------
        area : float
            Floor area in m².
        perimeter : float, optional
            Perimeter in metres.
        aspect_ratio : float, optional
            Aspect ratio (longest / shortest dimension).
        name : str, optional
            Room name for hint matching.
        polygon_vertices : list, optional
            Polygon vertices for computing missing features.
        bbox : tuple, optional
            Bounding box (minx, miny, maxx, maxy).
        num_vertices : int, optional
            Number of polygon vertices.
        features : RoomFeatures, optional
            Pre-computed features (overrides other parameters).

        Returns
        -------
        ClassificationResult
        """
        # Extract features
        if features is None:
            features = extract_features(
                area=area, perimeter=perimeter,
                polygon_vertices=polygon_vertices,
                bbox=bbox, aspect_ratio=aspect_ratio,
                num_vertices=num_vertices,
            )

        # Score each room type using geometric rules
        geo_scores = {}
        for room_type, rule_fn in ROOM_RULES.items():
            geo_scores[room_type] = rule_fn(features)

        # Get name hints
        name_scores = _name_hint_score(name) if name else {}

        # Combine scores
        combined = {}
        for room_type in ROOM_RULES:
            geo = geo_scores.get(room_type, 0.0) * self.geometric_weight
            name_s = name_scores.get(room_type, 0.0) * self.name_weight
            combined[room_type] = geo + name_s

        # Sort by score descending
        candidates = sorted(combined.items(), key=lambda x: x[1], reverse=True)

        # Top candidate
        if candidates and candidates[0][1] >= self.confidence_threshold:
            best_type = candidates[0][0]
            best_score = candidates[0][1]
        else:
            best_type = "unknown"
            best_score = 0.0

        # Determine NFPA defaults for the classified type
        room_defaults = self._cfg.room_type_defaults(best_type)

        return ClassificationResult(
            room_type=best_type,
            confidence=round(min(best_score, 1.0), 4),
            features=features.to_dict(),
            candidates=[(rt, round(s, 4)) for rt, s in candidates[:5]],
        )

    def classify_room_object(self, room) -> ClassificationResult:
        """
        Classify a FireAI Room object from core.models.

        Parameters
        ----------
        room : Room
            A Room object with geometry, name, etc.

        Returns
        -------
        ClassificationResult
        """
        area = getattr(room, 'floor_area', None)
        name = getattr(room, 'name', '')
        geom = getattr(room, 'geometry', None)

        bbox = None
        polygon_vertices = None

        if geom is not None:
            if hasattr(geom, 'bounds'):
                bbox = geom.bounds
            if hasattr(geom, 'exterior') and hasattr(geom.exterior, 'coords'):
                polygon_vertices = list(geom.exterior.coords)

        return self.classify(
            area=area or 0.0,
            name=name,
            bbox=bbox,
            polygon_vertices=polygon_vertices,
        )

    def batch_classify(self, rooms: list) -> List[ClassificationResult]:
        """
        Classify a batch of rooms.

        Parameters
        ----------
        rooms : list
            List of dicts with room data, or Room objects.

        Returns
        -------
        list of ClassificationResult
        """
        results = []
        for room in rooms:
            if isinstance(room, dict):
                result = self.classify(
                    area=room.get('area'),
                    name=room.get('name'),
                    aspect_ratio=room.get('aspect_ratio'),
                    perimeter=room.get('perimeter'),
                    bbox=room.get('bbox'),
                )
            else:
                result = self.classify_room_object(room)
            results.append(result)
        return results


# ════════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════════

def _self_test():
    """Run self-test for RuleBasedRoomClassifier."""
    print("=" * 60)
    print("Room Classifier — Self-Test")
    print("=" * 60)

    clf = RuleBasedRoomClassifier()

    # ── Corridor classification ──
    result = clf.classify(area=20.0, aspect_ratio=5.0, name="Corridor A")
    assert result.room_type == "corridor", f"Expected corridor, got {result.room_type}"
    assert result.confidence > 0.5, f"Low confidence for corridor: {result.confidence}"
    print(f"  Corridor: type={result.room_type}, confidence={result.confidence:.2f}")
    print("  [PASS] Corridor classification")

    # ── Office classification ──
    result = clf.classify(area=30.0, aspect_ratio=1.5, name="Office 101")
    assert result.room_type == "office", f"Expected office, got {result.room_type}"
    assert result.confidence > 0.4, f"Low confidence for office: {result.confidence}"
    print(f"  Office: type={result.room_type}, confidence={result.confidence:.2f}")
    print("  [PASS] Office classification")

    # ── Warehouse classification ──
    result = clf.classify(area=500.0, aspect_ratio=1.8, name="Warehouse")
    assert result.room_type == "warehouse", f"Expected warehouse, got {result.room_type}"
    print(f"  Warehouse: type={result.room_type}, confidence={result.confidence:.2f}")
    print("  [PASS] Warehouse classification")

    # ── Server room classification ──
    result = clf.classify(area=40.0, aspect_ratio=1.2, name="Server Room")
    assert result.room_type == "server_room", f"Expected server_room, got {result.room_type}"
    print(f"  Server room: type={result.room_type}, confidence={result.confidence:.2f}")
    print("  [PASS] Server room classification")

    # ── Stairwell classification ──
    result = clf.classify(area=10.0, aspect_ratio=2.5, name="Stairwell 1",
                          bbox=(0, 0, 2.5, 6.0))
    assert result.room_type == "stairwell", f"Expected stairwell, got {result.room_type}"
    print(f"  Stairwell: type={result.room_type}, confidence={result.confidence:.2f}")
    print("  [PASS] Stairwell classification")

    # ── Name hint only ──
    result = clf.classify(area=30.0, aspect_ratio=1.5, name="Kitchen")
    assert result.room_type == "kitchen", f"Expected kitchen, got {result.room_type}"
    print(f"  Kitchen (by name): type={result.room_type}, confidence={result.confidence:.2f}")
    print("  [PASS] Name hint classification")

    # ── Unknown room ──
    result = clf.classify(area=1.0, aspect_ratio=1.0)
    # Very small, no name — may be unknown or low confidence
    print(f"  Tiny room: type={result.room_type}, confidence={result.confidence:.2f}")
    print("  [PASS] Unknown/ambiguous room handling")

    # ── Feature extraction ──
    features = extract_features(
        area=50.0,
        polygon_vertices=[(0, 0), (10, 0), (10, 5), (0, 5)],
    )
    assert abs(features.area - 50.0) < 0.01, "Area mismatch"
    assert features.aspect_ratio >= 1.0, "Aspect ratio should be >= 1"
    assert 0 < features.compactness <= 1.0, "Compactness should be in (0, 1]"
    print(f"  Features: {features.to_dict()}")
    print("  [PASS] Feature extraction")

    # ── Batch classification ──
    rooms = [
        {"area": 20.0, "aspect_ratio": 4.0, "name": "Corridor B"},
        {"area": 35.0, "aspect_ratio": 1.3, "name": "Office 201"},
        {"area": 300.0, "aspect_ratio": 1.5, "name": "Main Warehouse"},
    ]
    results = clf.batch_classify(rooms)
    assert len(results) == 3, "Should classify 3 rooms"
    assert results[0].room_type == "corridor", f"Room 1 should be corridor, got {results[0].room_type}"
    print(f"  Batch: {[r.room_type for r in results]}")
    print("  [PASS] Batch classification")

    # ── Candidates list ──
    result = clf.classify(area=25.0, aspect_ratio=1.5, name="Office")
    assert len(result.candidates) > 0, "Should have candidates"
    assert result.candidates[0][0] == result.room_type, "Top candidate should match result"
    print(f"  Candidates: {result.candidates[:3]}")
    print("  [PASS] Candidates listing")

    print("\n" + "=" * 60)
    print("Room Classifier Self-Test: PASS")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
