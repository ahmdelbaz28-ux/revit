from dataclasses import dataclass, field
from typing import List, Dict, Any
from math import sqrt, exp
import copy
import json


@dataclass
class DSLNode:
    node_type: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DSLEdge:
    from_type: str
    to_type: str
    relationship: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DSLRule:
    rule_id: str
    trigger_type: str
    trigger_state: str
    propagation_direction: str
    scope: str
    effect_type: str
    target_type: str
    probability_factor: float
    decay_function_ref: str
    conditions: List[Dict] = field(default_factory=list)


@dataclass
class DSLDecay:
    decay_id: str
    decay_type: str
    formula: str
    lambda_value: float


@dataclass
class DSLProgram:
    nodes: List[DSLNode] = field(default_factory=list)
    edges: List[DSLEdge] = field(default_factory=list)
    rules: List[DSLRule] = field(default_factory=list)
    decays: List[DSLDecay] = field(default_factory=list)


DEFAULT_DSL_PROGRAM = DSLProgram(
    nodes=[
        DSLNode("smoke_detector", {"sensitivity": 0.85, "zone_affinity": 1.0}),
        DSLNode("heat_detector", {"sensitivity": 0.75, "zone_affinity": 1.2}),
        DSLNode("cable", {"failure_rate": 0.02, "signal_latency": 0.3}),
        DSLNode("panel", {"failure_rate": 0.01, "control_capacity": 1.0}),
        DSLNode("power_panel", {"failure_rate": 0.01, "supply_capacity": 1.0}),
        DSLNode("zone", {"type": "generic", "risk_weight": 1.0}),
    ],
    edges=[
        DSLEdge("power_panel", "panel", "supplies", {}),
        DSLEdge("power_panel", "smoke_detector", "supplies", {}),
        DSLEdge("power_panel", "heat_detector", "supplies", {}),
        DSLEdge("panel", "cable", "controls", {}),
        DSLEdge("cable", "smoke_detector", "connects", {}),
        DSLEdge("cable", "heat_detector", "connects", {}),
        DSLEdge("smoke_detector", "zone", "monitors", {}),
        DSLEdge("heat_detector", "zone", "monitors", {}),
    ],
    rules=[
        DSLRule("POWER_CASCADE_DETECTOR", "power_panel", "failed", "downstream", "system-wide", "probability_shift", "smoke_detector", 1.8, "threshold", []),
        DSLRule("POWER_CASCADE_CABLE", "power_panel", "failed", "downstream", "system-wide", "probability_shift", "cable", 1.5, "threshold", []),
        DSLRule("CABLE_SIGNAL_LOSS_DETECTOR", "cable", "failed", "downstream", "local", "probability_shift", "smoke_detector", 1.4, "exponential", []),
        DSLRule("CABLE_SIGNAL_LOSS_PANEL", "cable", "failed", "downstream", "local", "probability_shift", "panel", 1.3, "exponential", []),
        DSLRule("DETECTOR_COVERAGE_LOSS", "smoke_detector", "failed", "spatial", "zone-wide", "spatial_field", "zone", 1.6, "inverse_square", []),
        DSLRule("DETECTOR_COVERAGE_LOSS_HEAT", "heat_detector", "failed", "spatial", "zone-wide", "spatial_field", "zone", 1.4, "inverse_square", []),
        DSLRule("PANEL_CONTROL_LOSS", "panel", "failed", "downstream", "system-wide", "state_transition", "smoke_detector", 1.7, "exponential", []),
        DSLRule("EXIT_BLOCKAGE", "zone", "blocked", "spatial", "zone-wide", "state_transition", "zone", 1.9, "threshold", []),
    ],
    decays=[
        DSLDecay("exponential", "EXPONENTIAL", "exp(-lambda * distance)", 0.35),
        DSLDecay("inverse_square", "INVERSE_SQUARE", "1 / (distance^2 + 1)", 1.0),
        DSLDecay("threshold", "THRESHOLD", "1 if distance <= 10 else 0", 10.0),
    ]
)


def apply_decay(decay: DSLDecay, distance: float) -> float:
    if decay.decay_type == "EXPONENTIAL":
        return exp(-decay.lambda_value * distance)
    elif decay.decay_type == "INVERSE_SQUARE":
        return 1.0 / (distance**2 + 1)
    elif decay.decay_type == "THRESHOLD":
        return 1.0 if distance <= decay.lambda_value else 0.0
    return 1.0


class DSLEngine:
    def __init__(self, program: DSLProgram = None):
        self.program = program or DEFAULT_DSL_PROGRAM
        self.decay_map = {d.decay_id: d for d in self.program.decays}
        self.rule_map = {r.rule_id: r for r in self.program.rules}

    def load_program_from_json(self, json_path: str):
        with open(json_path, 'r') as f:
            data = json.load(f)

        self.program = DSLProgram(
            nodes=[DSLNode(**n) for n in data.get("nodes", [])],
            edges=[DSLEdge(**e) for e in data.get("edges", [])],
            rules=[DSLRule(**r) for r in data.get("rules", [])],
            decays=[DSLDecay(**d) for d in data.get("decays", [])]
        )
        self.decay_map = {d.decay_id: d for d in self.program.decays}
        self.rule_map = {r.rule_id: r for r in self.program.rules}

    def execute_rules(self, topology, failure_scenario: dict, max_steps: int = 5):
        topology_copy = copy.deepcopy(topology)
        evolution_history = []
        active_rules = self.program.rules

        failed_count = failure_scenario.get("failed_count", 0)
        active_nodes = [n for n in topology_copy.nodes if n.status == "operational"]
        for i in range(min(failed_count, len(active_nodes))):
            active_nodes[i].status = "failed"

        if failure_scenario.get("power_failed"):
            for node in topology_copy.nodes:
                if node.node_type in ["power_panel", "panel"]:
                    node.status = "failed"

        for step in range(1, max_steps + 1):
            new_failures = []

            for rule in active_rules:
                source_nodes = [n for n in topology_copy.nodes if n.node_type == rule.trigger_type and n.status == rule.trigger_state]

                for source in source_nodes:
                    if rule.propagation_direction == "downstream":
                        target_nodes = [n for n in topology_copy.nodes if n.node_type == rule.target_type and n.status == "operational"]
                    elif rule.propagation_direction == "spatial":
                        target_nodes = [n for n in topology_copy.nodes if n.node_type == rule.target_type and n.status == "operational"]
                    else:
                        target_nodes = [n for n in topology_copy.nodes if n.node_type == rule.target_type]

                    for target in target_nodes:
                        if hasattr(source, 'x') and hasattr(target, 'x'):
                            dist = sqrt((source.x - target.x)**2 + (source.y - target.y)**2)
                        else:
                            dist = 5.0

                        decay = self.decay_map.get(rule.decay_function_ref)
                        if decay:
                            decay_factor = apply_decay(decay, dist)
                        else:
                            decay_factor = 1.0

                        adjusted_prob = rule.probability_factor * 0.12 * decay_factor

                        if rule.effect_type == "probability_shift":
                            target.failure_probability = min(1.0, target.failure_probability + adjusted_prob)
                        elif rule.effect_type == "state_transition":
                            if adjusted_prob > 0.3:
                                target.status = "failed"
                                new_failures.append(target.node_id)

            if not new_failures:
                break

            evolution_history.append({"step": step, "new_failures": new_failures})

        return topology_copy, evolution_history

    def get_program_summary(self) -> dict:
        return {
            "nodes_count": len(self.program.nodes),
            "edges_count": len(self.program.edges),
            "rules_count": len(self.program.rules),
            "decays_count": len(self.program.decays),
            "rule_ids": [r.rule_id for r in self.program.rules],
            "decay_ids": [d.decay_id for d in self.program.decays]
        }