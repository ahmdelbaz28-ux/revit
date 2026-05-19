from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Callable, Optional
from math import sqrt, exp
import numpy as np


@dataclass
class ConstraintNode:
    constraint_id: str
    constraint_type: str
    weight: float
    priority: str
    evaluate_fn: Callable
    gradient_fn: Optional[Callable] = None


@dataclass
class ConstraintEdge:
    from_constraint: str
    to_constraint: str
    coupling_type: str
    coupling_strength: float


class DifferentiableConstraintGraph:
    def __init__(self):
        self.nodes: Dict[str, ConstraintNode] = {}
        self.edges: List[ConstraintEdge] = []
        self._build_default_graph()

    def _build_default_graph(self):
        self.add_node(ConstraintNode(
            "COLLISION_DETECT", "hard_geometric", weight=10.0, priority="CRITICAL",
            evaluate_fn=self._eval_collision,
            gradient_fn=self._grad_collision
        ))
        self.add_node(ConstraintNode(
            "MIN_SPACING", "nfpa_spatial", weight=8.0, priority="CRITICAL",
            evaluate_fn=self._eval_spacing,
            gradient_fn=self._grad_spacing
        ))
        self.add_node(ConstraintNode(
            "COVERAGE_RADIUS", "nfpa_coverage", weight=7.0, priority="HIGH",
            evaluate_fn=self._eval_coverage,
            gradient_fn=self._grad_coverage
        ))
        self.add_node(ConstraintNode(
            "MOUNTING_FEASIBILITY", "geometric", weight=5.0, priority="MEDIUM",
            evaluate_fn=self._eval_mounting,
            gradient_fn=None
        ))
        self.add_node(ConstraintNode(
            "CONNECTIVITY_VALID", "topology", weight=6.0, priority="HIGH",
            evaluate_fn=self._eval_connectivity,
            gradient_fn=None
        ))

    def add_node(self, node: ConstraintNode):
        self.nodes[node.constraint_id] = node

    def evaluate(self, state: Dict) -> Dict:
        results = {}
        for node_id, node in self.nodes.items():
            try:
                value = node.evaluate_fn(state)
                results[node_id] = {
                    "value": value,
                    "violation": max(0.0, value - 0.95) if value > 0 else 0.0,
                    "weight": node.weight,
                    "priority": node.priority,
                    "passed": value < 0.95 if value > 0 else True
                }
            except Exception:
                results[node_id] = {
                    "value": 0.0,
                    "violation": 0.0,
                    "weight": node.weight,
                    "priority": node.priority,
                    "passed": True
                }
        return results

    def compute_energy(self, state: Dict) -> float:
        results = self.evaluate(state)
        total_energy = 0.0
        for constraint_id, result in results.items():
            total_energy += result["weight"] * (result["violation"] ** 2)
        return total_energy

    def compute_gradient(self, state: Dict) -> Dict:
        gradient = {}
        for node_id, node in self.nodes.items():
            if node.gradient_fn:
                try:
                    grad = node.gradient_fn(state)
                    gradient[node_id] = grad
                except Exception:
                    gradient[node_id] = {"dx": 0.0, "dy": 0.0}
        return gradient

    def soft_project(self, state: Dict, step_size: float = 0.1) -> Dict:
        energy = self.compute_energy(state)
        if energy < 0.01:
            return state

        gradient = self.compute_gradient(state)

        updated_state = dict(state)
        if "devices" in updated_state:
            for i, device in enumerate(updated_state["devices"]):
                dx = 0.0
                dy = 0.0
                for constraint_id, grad in gradient.items():
                    if "dx" in grad and "dy" in grad:
                        node = self.nodes.get(constraint_id)
                        if node:
                            weight = node.weight
                            dx += weight * grad.get("dx", 0.0) * step_size
                            dy += weight * grad.get("dy", 0.0) * step_size

                updated_state["devices"][i]["x"] = device.get("x", 0) - dx
                updated_state["devices"][i]["y"] = device.get("y", 0) - dy

        return updated_state

    def hard_repair(self, state: Dict) -> Dict:
        repaired = dict(state)

        if "devices" in repaired:
            positions = []
            for i, device in enumerate(repaired["devices"]):
                x = device.get("x", 0)
                y = device.get("y", 0)

                for j, other_device in enumerate(repaired["devices"]):
                    if j <= i:
                        continue
                    ox = other_device.get("x", 0)
                    oy = other_device.get("y", 0)
                    dist = sqrt((x - ox)**2 + (y - oy)**2)

                    if dist < 3.0 and dist > 0:
                        nx = (x - ox) / dist
                        ny = (y - oy) / dist
                        overlap = 3.0 - dist
                        x += nx * overlap * 0.6
                        y += ny * overlap * 0.6
                        ox -= nx * overlap * 0.4
                        oy -= ny * overlap * 0.4
                        repaired["devices"][j]["x"] = ox
                        repaired["devices"][j]["y"] = oy

                repaired["devices"][i]["x"] = x
                repaired["devices"][i]["y"] = y

        return repaired

    def project(self, state: Dict, step_size: float = 0.1, max_iterations: int = 10) -> Dict:
        current_state = dict(state)

        for iteration in range(max_iterations):
            energy_before = self.compute_energy(current_state)
            soft_state = self.soft_project(current_state, step_size)
            current_state = self.hard_repair(soft_state)
            energy_after = self.compute_energy(current_state)

            if energy_after < 0.01 or abs(energy_after - energy_before) < 0.001:
                break

        return current_state

    def _eval_collision(self, state: Dict) -> float:
        devices = state.get("devices", [])
        if len(devices) < 2:
            return 0.0

        min_dist = float("inf")
        for i, d1 in enumerate(devices):
            for j, d2 in enumerate(devices):
                if j <= i:
                    continue
                dist = sqrt((d1.get("x", 0) - d2.get("x", 0))**2 + (d1.get("y", 0) - d2.get("y", 0))**2)
                min_dist = min(min_dist, dist)

        if min_dist < 0.1:
            return 10.0
        if min_dist < 1.0:
            return 5.0
        if min_dist < 3.0:
            return 1.0 - (min_dist - 1.0) / 2.0
        return 0.0

    def _grad_collision(self, state: Dict) -> Dict:
        return {"dx": 0.1, "dy": 0.1}

    def _eval_spacing(self, state: Dict) -> float:
        devices = state.get("devices", [])
        if len(devices) < 2:
            return 0.0

        max_spacing = 15.0
        max_violation = 0.0
        for i, d1 in enumerate(devices):
            for j, d2 in enumerate(devices):
                if j <= i:
                    continue
                dist = sqrt((d1.get("x", 0) - d2.get("x", 0))**2 + (d1.get("y", 0) - d2.get("y", 0))**2)
                if dist > max_spacing:
                    violation = (dist - max_spacing) / max_spacing
                    max_violation = max(max_violation, violation)

        return max_violation

    def _grad_spacing(self, state: Dict) -> Dict:
        return {"dx": 0.05, "dy": 0.05}

    def _eval_coverage(self, state: Dict) -> float:
        devices = state.get("devices", [])
        if not devices:
            return 5.0
        return max(0.0, 1.0 - len(devices) * 0.3)

    def _grad_coverage(self, state: Dict) -> Dict:
        return {"dx": -0.05, "dy": -0.05}

    def _eval_mounting(self, state: Dict) -> float:
        return 0.0

    def _eval_connectivity(self, state: Dict) -> float:
        devices = state.get("devices", [])
        if len(devices) <= 1:
            return 0.0
        return max(0.0, 1.0 - len(devices) * 0.15)


class ConstraintProjectionOperator:
    def __init__(self, constraint_graph: DifferentiableConstraintGraph):
        self.graph = constraint_graph

    def project_to_feasible(self, state: Dict, max_iterations: int = 20, step_size: float = 0.1) -> Dict:
        return self.graph.project(state, step_size=step_size, max_iterations=max_iterations)

    def is_feasible(self, state: Dict) -> bool:
        energy = self.graph.compute_energy(state)
        return energy < 0.05

    def get_violations(self, state: Dict) -> List[Dict]:
        results = self.graph.evaluate(state)
        violations = []
        for constraint_id, result in results.items():
            if not result["passed"]:
                violations.append({
                    "constraint_id": constraint_id,
                    "violation_value": result["violation"],
                    "priority": result["priority"],
                    "weight": result["weight"]
                })
        return sorted(violations, key=lambda v: v["weight"], reverse=True)