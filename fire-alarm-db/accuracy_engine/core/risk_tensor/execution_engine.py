from dataclasses import dataclass, field
from typing import List, Dict
from math import sqrt, exp
import copy


@dataclass
class SystemState:
    nodes: Dict[str, Dict] = field(default_factory=dict)
    edges: Dict[str, Dict] = field(default_factory=dict)
    spatial_fields: Dict[str, List[float]] = field(default_factory=dict)
    timestep: int = 0


class ExecutionEngine:
    def __init__(self, ir_graph, decay_functions: dict, topology):
        self.ir = ir_graph
        self.decay_functions = decay_functions
        self.topology = topology
        self.state = SystemState()
        self.state_history: List[SystemState] = []

    def initialize_state(self, topology):
        for node in topology.nodes:
            self.state.nodes[node.node_id] = {
                "status": node.status,
                "failure_probability": getattr(node, 'failure_probability', 0.0),
                "node_type": node.node_type
            }

    def apply_failures(self, failure_scenario: dict):
        failed_count = failure_scenario.get("failed_count", 0)
        active_nodes = [(nid, s) for nid, s in self.state.nodes.items() if s["status"] == "operational"]

        for i in range(min(failed_count, len(active_nodes))):
            node_id, _ = active_nodes[i]
            self.state.nodes[node_id]["status"] = "failed"
            self.state.nodes[node_id]["failure_probability"] = 1.0

        if failure_scenario.get("power_failed"):
            for nid, s in self.state.nodes.items():
                if s["node_type"] in ["power_panel", "panel"]:
                    s["status"] = "failed"
                    s["failure_probability"] = 1.0

    def execute_rules(self) -> List[str]:
        triggered_rules = []

        for ir_rule in self.ir.rules:
            trigger_type = ir_rule.trigger_node.node_type
            trigger_state = ir_rule.trigger_node.trigger_state

            matching_nodes = [
                nid for nid, s in self.state.nodes.items()
                if s["node_type"] == trigger_type and s["status"] == trigger_state
            ]

            if matching_nodes:
                triggered_rules.append(ir_rule.rule_id)

                effect = ir_rule.effect_node
                decay_fn = self.decay_functions.get(effect.decay_function)

                target_nodes = [
                    (nid, s) for nid, s in self.state.nodes.items()
                    if s["node_type"] == effect.target_type and s["status"] == "operational"
                ]

                for target_id, target_state in target_nodes:
                    source_node = self._find_topology_node(matching_nodes[0])
                    target_node = self._find_topology_node(target_id)

                    if source_node and target_node:
                        dist = sqrt((source_node.x - target_node.x)**2 + (source_node.y - target_node.y)**2)
                    else:
                        dist = 5.0

                    decay_factor = 1.0
                    if decay_fn:
                        decay_factor = self._compute_decay(decay_fn, dist)

                    prob = effect.probability_factor * 0.12 * decay_factor

                    if effect.effect_type == "probability_shift":
                        target_state["failure_probability"] = min(1.0, target_state["failure_probability"] + prob)
                    elif effect.effect_type == "state_transition":
                        if prob > 0.3:
                            target_state["status"] = "failed"

        return triggered_rules

    def evolve(self, max_steps: int = 5) -> List[SystemState]:
        self.state_history = [copy.deepcopy(self.state)]

        for step in range(1, max_steps + 1):
            self.state.timestep = step
            triggered = self.execute_rules()

            if not triggered:
                break

            self.state_history.append(copy.deepcopy(self.state))

        return self.state_history

    def _find_topology_node(self, node_id: str):
        for node in self.topology.nodes:
            if node.node_id == node_id:
                return node
        return None

    def _compute_decay(self, decay_obj, distance: float) -> float:
        decay_type = getattr(decay_obj, 'decay_type', 'EXPONENTIAL')
        lambda_val = getattr(decay_obj, 'lambda_value', 0.35)

        if decay_type == "EXPONENTIAL":
            return exp(-lambda_val * distance)
        elif decay_type == "INVERSE_SQUARE":
            return 1.0 / (distance**2 + 1)
        elif decay_type == "THRESHOLD":
            return 1.0 if distance <= lambda_val else 0.0
        return 1.0

    def get_final_state(self) -> dict:
        total_nodes = len(self.state.nodes)
        failed_nodes = len([s for s in self.state.nodes.values() if s["status"] == "failed"])
        avg_risk = failed_nodes / max(total_nodes, 1)

        return {
            "total_nodes": total_nodes,
            "failed_nodes": failed_nodes,
            "average_risk": avg_risk,
            "evolution_steps": len(self.state_history),
            "final_timestep": self.state.timestep
        }