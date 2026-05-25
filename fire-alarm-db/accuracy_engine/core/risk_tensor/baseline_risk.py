from dataclasses import dataclass
from typing import List
from math import sqrt


@dataclass
class DetectorInfluenceZone:
    detector_id: int
    x: float
    y: float
    radius: float
    coverage_strength: float


@dataclass
class BaselineRiskPoint:
    x: float
    y: float
    risk_value: float
    distance_to_nearest_detector: float
    covered_by_count: int
    zone_id: str


@dataclass
class BaselineRiskField:
    room_id: str
    room_type: str
    points: List[BaselineRiskPoint]
    overall_baseline_risk: float
    detector_influence_zones: List[DetectorInfluenceZone]
    geometry_risk_factor: float
    room_type_risk_factor: float


def calculate_baseline_risk_field(room: dict, devices: list) -> BaselineRiskField:
    polygon = room.get("polygon", [])
    room_type = room.get("type", "office")
    room_id = room.get("id", "unknown")

    room_devices = [d for d in devices if d.get("room_id") == room_id]

    if not polygon or len(polygon) < 4:
        return BaselineRiskField(
            room_id=room_id, room_type=room_type,
            points=[], overall_baseline_risk=0.0,
            detector_influence_zones=[], geometry_risk_factor=0.0,
            room_type_risk_factor=0.0
        )

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    area = width * height

    influence_zones = []
    for i, d in enumerate(room_devices):
        radius = 7.5 if d.get("type") == "smoke" else 6.0
        strength = 1.0
        for other_d in room_devices:
            if other_d != d:
                dist = sqrt((d.get("x", 0) - other_d.get("x", 0))**2 + (d.get("y", 0) - other_d.get("y", 0))**2)
                if dist < radius * 2:
                    strength = min(2.0, strength + 0.3)

        influence_zones.append(DetectorInfluenceZone(
            detector_id=i, x=d.get("x", 0), y=d.get("y", 0),
            radius=radius, coverage_strength=strength
        ))

    room_type_risk = 1.0
    if room_type in ["electrical", "storage"]:
        room_type_risk = 1.8
    elif room_type in ["mechanical", "kitchen"]:
        room_type_risk = 1.5
    elif room_type == "corridor":
        room_type_risk = 1.2

    geometry_risk = 0.0
    if area > 200:
        geometry_risk += 0.2
    if width / max(height, 0.1) > 3 or height / max(width, 0.1) > 3:
        geometry_risk += 0.15
    if len(room_devices) == 0:
        geometry_risk += 0.5
    elif area / len(room_devices) > 80:
        geometry_risk += 0.25

    step_x = width / 10
    step_y = height / 10
    points = []

    for i in range(11):
        for j in range(11):
            x = min_x + i * step_x
            y = min_y + j * step_y

            inside = (min_x <= x <= max_x and min_y <= y <= max_y) if width > 0 and height > 0 else True
            if not inside:
                continue

            distances = []
            for zone in influence_zones:
                dist = sqrt((x - zone.x)**2 + (y - zone.y)**2)
                distances.append((dist, zone))

            distances.sort()
            nearest_dist = distances[0][0] if distances else 999
            covered_by = sum(1 for d, z in distances if d <= z.radius)

            base_risk = 0.0
            if len(influence_zones) == 0:
                base_risk = 0.8
            elif covered_by == 0:
                farthest = max(distances, key=lambda t: t[0]) if distances else (999, None)
                base_risk = min(0.7, farthest[0] / 20.0)
            elif covered_by == 1:
                base_risk = 0.15
            else:
                base_risk = 0.05

            coverage_strength = sum(z.coverage_strength for d, z in distances if d <= z.radius)
            if coverage_strength > 1.0:
                base_risk *= 0.7

            adjusted_risk = base_risk * room_type_risk + geometry_risk * 0.1

            points.append(BaselineRiskPoint(
                x=round(x, 2), y=round(y, 2),
                risk_value=round(min(1.0, adjusted_risk), 4),
                distance_to_nearest_detector=round(nearest_dist, 2),
                covered_by_count=covered_by,
                zone_id=room_id
            ))

    avg_risk = sum(p.risk_value for p in points) / len(points) if points else 0

    return BaselineRiskField(
        room_id=room_id, room_type=room_type,
        points=points, overall_baseline_risk=round(avg_risk, 4),
        detector_influence_zones=influence_zones,
        geometry_risk_factor=geometry_risk,
        room_type_risk_factor=room_type_risk
    )


def perturb_baseline(baseline: BaselineRiskField, failure_scenario: dict) -> List[BaselineRiskPoint]:
    failed_count = failure_scenario.get("failed_count", 0)
    total_devices = failure_scenario.get("total_devices", 1)
    failure_ratio = failed_count / max(total_devices, 1)

    perturbed_points = []
    for point in baseline.points:
        perturbation = 0.0

        if failure_ratio > 0:
            perturbation = point.risk_value * failure_ratio * 1.5

        if failure_scenario.get("power_failed"):
            perturbation += 0.15

        if failure_scenario.get("exit_blocked"):
            if point.risk_value > 0.2:
                perturbation += 0.1

        new_risk = min(1.0, point.risk_value + perturbation)
        perturbed_points.append(BaselineRiskPoint(
            x=point.x, y=point.y,
            risk_value=round(new_risk, 4),
            distance_to_nearest_detector=point.distance_to_nearest_detector,
            covered_by_count=point.covered_by_count,
            zone_id=point.zone_id
        ))

    return perturbed_points