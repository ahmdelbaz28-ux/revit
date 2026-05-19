from dataclasses import dataclass
from math import sqrt, exp
import copy


@dataclass
class PropagationRule:
    rule_id: str
    source_type: str
    target_type: str
    relationship: str
    probability_multiplier: float
    decay_function: str


@dataclass
class EvolvedState:
    node_id: str
    node_type: str
    status: str
    failure_probability: float
    propagated_from: str
    propagation_step: int


DEFAULT_PROPAGATION_RULES = [
    PropagationRule("POWER_CASCADE", "power_panel", "detector", "supplies", 1.8, "threshold"),
    PropagationRule("POWER_CASCADE", "power_panel", "cable", "supplies", 1.5, "threshold"),
    PropagationRule("CABLE_SIGNAL_LOSS", "cable", "detector", "connects", 1.4, "exponential"),
    PropagationRule("CABLE_SIGNAL_LOSS", "cable", "panel", "connects", 1.3, "exponential"),
    PropagationRule("DETECTOR_COVERAGE_LOSS", "detector", "zone", "monitors", 1.6, "inverse_square"),
    PropagationRule("EXIT_BLOCKAGE", "exit", "zone", "evacuation_path", 1.9, "threshold"),
    PropagationRule("PANEL_CONTROL_LOSS", "panel", "detector", "controls", 1.7, "exponential"),
    PropagationRule("PANEL_CONTROL_LOSS", "panel", "zone", "controls", 1.5, "exponential"),
]


def exponential_decay(distance: float, lam: float = 0.3) -> float:
    return exp(-lam * distance)


def inverse_square_decay(distance: float, min_distance: float = 1.0) -> float:
    return 1.0 / (max(distance, min_distance) ** 2)


def threshold_decay(distance: float, threshold: float = 10.0) -> float:
    return 1.0 if distance <= threshold else 0.0


DECAY_FUNCTIONS = {
    "exponential": exponential_decay,
    "inverse_square": inverse_square_decay,
    "threshold": threshold_decay
}


class PropagationEngine:
    def __init__(self):
        self.rules = DEFAULT_PROPAGATION_RULES
        self.evolution_history = []

    def run_propagation(self, topology, failure_scenario: dict, max_steps: int = 5):
        self.evolution_history = []

        topology_copy = copy.deepcopy(topology)

        evolved_states = []
        for node in topology_copy.nodes:
            evolved_states.append(EvolvedState(
                node_id=node.node_id, node_type=node.node_type,
                status=node.status, failure_probability=0.0,
                propagated_from="none", propagation_step=0
            ))

        failed_count = failure_scenario.get("failed_count", 0)
        active_nodes = [n for n in topology_copy.nodes if n.status == "operational"]

        for i in range(min(failed_count, len(active_nodes))):
            active_nodes[i].status = "failed"
            for state in evolved_states:
                if state.node_id == active_nodes[i].node_id:
                    state.status = "failed"
                    state.failure_probability = 1.0
                    state.propagated_from = "scenario"
                    state.propagation_step = 0

        if failure_scenario.get("power_failed"):
            for node in topology_copy.nodes:
                if node.node_type in ["power_panel", "panel"]:
                    node.status = "failed"
                    for state in evolved_states:
                        if state.node_id == node.node_id:
                            state.status = "failed"
                            state.failure_probability = 1.0
                            state.propagated_from = "power_failure"
                            state.propagation_step = 0

        for step in range(1, max_steps + 1):
            new_failures = []

            for rule in self.rules:
                source_nodes = [n for n in topology_copy.nodes if n.node_type == rule.source_type and n.status == "failed"]

                for source in source_nodes:
                    target_nodes = [n for n in topology_copy.nodes if n.node_type == rule.target_type and n.status == "operational"]

                    for target in target_nodes:
                        dist = sqrt((source.x - target.x)**2 + (source.y - target.y)**2) if hasattr(source, 'x') and hasattr(target, 'x') else 5.0

                        decay_fn = DECAY_FUNCTIONS.get(rule.decay_function, exponential_decay)
                        decay_factor = decay_fn(dist)

                        base_prob = rule.probability_multiplier * 0.15
                        adjusted_prob = base_prob * decay_factor

                        if adjusted_prob > 0.3:
                            target.status = "failed"
                            target.failure_probability = min(1.0, adjusted_prob)
                            new_failures.append(target.node_id)

                            for state in evolved_states:
                                if state.node_id == target.node_id:
                                    state.status = "failed"
                                    state.failure_probability = adjusted_prob
                                    state.propagated_from = source.node_id
                                    state.propagation_step = step

            if not new_failures:
                break

            self.evolution_history.append({
                "step": step,
                "new_failures": new_failures,
                "total_failed": len([n for n in topology_copy.nodes if n.status == "failed"])
            })

        for node in topology_copy.nodes:
            if node.status == "failed":
                affected = [n for n in topology_copy.nodes if n.status == "operational"]
                for target in affected:
                    if hasattr(node, 'x') and hasattr(target, 'x'):
                        dist = sqrt((node.x - target.x)**2 + (node.y - target.y)**2)
                        decay = exponential_decay(dist)
                        target_prob_increase = 0.08 * decay

                        for state in evolved_states:
                            if state.node_id == target.node_id and state.status == "operational":
                                state.failure_probability = min(0.3, state.failure_probability + target_prob_increase)

        return evolved_states

    def get_evolution_summary(self) -> dict:
        if not self.evolution_history:
            return {"total_steps": 0, "final_failed_count": 0, "cascading_failures": 0, "max_step_reached": 0}

        return {
            "total_steps": len(self.evolution_history),
            "final_failed_count": self.evolution_history[-1]["total_failed"] if self.evolution_history else 0,
            "cascading_failures": sum(len(h["new_failures"]) for h in self.evolution_history),
            "max_step_reached": max(h["step"] for h in self.evolution_history) if self.evolution_history else 0
        }