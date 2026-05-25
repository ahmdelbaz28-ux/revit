from dataclasses import dataclass
from typing import List, Dict, Tuple
from math import sqrt, exp


@dataclass
class SystemNode:
    node_id: str
    node_type: str
    zone_id: str
    x: float
    y: float
    influence_radius: float
    coverage_strength: float
    status: str = "operational"


@dataclass
class SystemEdge:
    from_node: str
    to_node: str
    relationship: str
    weight: float


@dataclass
class InfluenceField:
    detector_id: str
    x: float
    y: float
    radius: float
    strength: float

    def influence_at(self, px: float, py: float) -> float:
        dist = sqrt((self.x - px)**2 + (self.y - py)**2)
        if dist > self.radius:
            return 0.0
        normalized_dist = dist / self.radius
        return self.strength * exp(-2.0 * normalized_dist)


@dataclass
class SystemTopology:
    room_id: str
    room_type: str
    room_polygon: List[Tuple[float, float]]
    nodes: List[SystemNode]
    edges: List[SystemEdge]
    influence_fields: List[InfluenceField]
    spatial_index: Dict[str, List[Tuple[float, float]]]
    room_type_risk_factor: float
    geometry_risk_factor: float


def build_system_topology(room: dict, devices: list) -> SystemTopology:
    room_id = room.get("id", "unknown")
    room_type = room.get("type", "office")
    polygon = room.get("polygon", [])

    room_devices = [d for d in devices if d.get("room_id") == room_id]

    room_type_risk = 1.0
    if room_type in ["electrical", "storage"]:
        room_type_risk = 1.8
    elif room_type in ["mechanical", "kitchen"]:
        room_type_risk = 1.5
    elif room_type == "corridor":
        room_type_risk = 1.2

    if polygon and len(polygon) >= 4:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        area = width * height
    else:
        area = room.get("area", 100)

    geometry_risk = 0.0
    if area > 200:
        geometry_risk += 0.2
    if polygon and len(polygon) >= 4:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if width / max(height, 0.1) > 3 or height / max(width, 0.1) > 3:
            geometry_risk += 0.15
    if len(room_devices) == 0:
        geometry_risk += 0.5
    elif area / len(room_devices) > 80:
        geometry_risk += 0.25

    nodes = []
    influence_fields = []

    for i, d in enumerate(room_devices):
        node_id = f"detector_{room_id}_{i}"
        radius = 7.5 if d.get("type") == "smoke" else 6.0

        strength = 1.0
        for j, other in enumerate(room_devices):
            if i != j:
                dist = sqrt((d.get("x", 0) - other.get("x", 0))**2 + (d.get("y", 0) - other.get("y", 0))**2)
                if dist < radius * 2:
                    strength = min(2.0, strength + 0.3)

        nodes.append(SystemNode(
            node_id=node_id, node_type="detector", zone_id=room_id,
            x=d.get("x", 0), y=d.get("y", 0),
            influence_radius=radius, coverage_strength=strength
        ))

        influence_fields.append(InfluenceField(
            detector_id=node_id, x=d.get("x", 0), y=d.get("y", 0),
            radius=radius, strength=strength
        ))

    edges = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            dist = sqrt((nodes[i].x - nodes[j].x)**2 + (nodes[i].y - nodes[j].y)**2)
            if dist < 30.0:
                edges.append(SystemEdge(
                    from_node=nodes[i].node_id, to_node=nodes[j].node_id,
                    relationship="signal", weight=round(1.0 / max(dist, 1.0), 4)
                ))

    spatial_index = {}
    if polygon and len(polygon) >= 4:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        step_x = (max_x - min_x) / 10
        step_y = (max_y - min_y) / 10

        for i in range(11):
            for j in range(11):
                x = min_x + i * step_x
                y = min_y + j * step_y
                key = f"{round(x, 1)}_{round(y, 1)}"
                spatial_index[key] = [(x, y)]

    return SystemTopology(
        room_id=room_id, room_type=room_type,
        room_polygon=polygon, nodes=nodes, edges=edges,
        influence_fields=influence_fields, spatial_index=spatial_index,
        room_type_risk_factor=room_type_risk, geometry_risk_factor=geometry_risk
    )


def apply_perturbation(topology: SystemTopology, failure_scenario: dict) -> SystemTopology:
    import copy
    perturbed = copy.deepcopy(topology)

    failed_count = failure_scenario.get("failed_count", 0)

    if failed_count > 0:
        active_nodes = [n for n in perturbed.nodes if n.status == "operational"]
        for i in range(min(failed_count, len(active_nodes))):
            active_nodes[i].status = "failed"

    if failure_scenario.get("power_failed"):
        for node in perturbed.nodes:
            node.coverage_strength *= 0.6

    if failure_scenario.get("exit_blocked"):
        perturbed.room_type_risk_factor *= 1.3

    perturbed.influence_fields = []
    for node in perturbed.nodes:
        if node.status == "operational":
            perturbed.influence_fields.append(InfluenceField(
                detector_id=node.node_id, x=node.x, y=node.y,
                radius=node.influence_radius, strength=node.coverage_strength
            ))

    return perturbed


def calculate_risk_field(topology: SystemTopology, px: float, py: float) -> float:
    if not topology.influence_fields:
        return 0.7 * topology.room_type_risk_factor

    total_influence = 0.0
    for field in topology.influence_fields:
        inf = field.influence_at(px, py)
        total_influence += inf

    max_possible = 1.0
    protection = min(1.0, total_influence / max_possible)
    base_risk = 1.0 - protection

    risk = base_risk * topology.room_type_risk_factor + topology.geometry_risk_factor * 0.1
    return min(1.0, risk)