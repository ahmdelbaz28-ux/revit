from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum


class ActionType(Enum):
    MOVE_DETECTOR = "move_detector"
    ADD_REDUNDANCY = "add_redundancy"
    RELOCATE_POWER = "relocate_power"
    ADD_ZONE = "add_zone"
    UPGRADE_PANEL = "upgrade_panel"


class EngineeringAction:
    def __init__(self, action_id: str, action_type: ActionType, target_node_id: str, 
                 priority: str, expected_benefit: float, risk_mitigation: float = 0.0):
        self.action_id = action_id
        self.action_type = action_type
        self.target_node_id = target_node_id
        self.priority = priority
        self.expected_benefit = expected_benefit
        self.risk_mitigation = risk_mitigation


class DecisionReport:
    def __init__(self, actions: List[EngineeringAction], summary: Dict,
                 critical_count: int, high_count: int, medium_count: int,
                 total_interventions: int):
        self.actions = actions
        self.summary = summary
        self.critical_count = critical_count
        self.high_count = high_count
        self.medium_count = medium_count
        self.total_interventions = total_interventions


class DifferentiableConstraintGraph:
    """placeholder for import compatibility"""
    pass


class ConstraintProjectionOperator:
    """placeholder for import compatibility"""
    pass


class SpectralEngineeringDecisionSystem:
    def __init__(self):
        self.constraint_graph = None
        self.projection_operator = None
        self._initialize_system()

    def _initialize_system(self):
        try:
            from core.risk_tensor.constraint_graph import DifferentiableConstraintGraph, ConstraintProjectionOperator
            self.constraint_graph = DifferentiableConstraintGraph()
            self.projection_operator = ConstraintProjectionOperator(self.constraint_graph)
        except ImportError:
            pass

    def generate_feasible_actions(self, topology, discretized_state: Dict, stability_report: Dict) -> Optional[DecisionReport]:
        if not self.constraint_graph or not self.projection_operator:
            return None

        raw_actions = self._generate_raw_actions(topology, discretized_state, stability_report)

        state_dict = self._topology_to_state_dict(topology, discretized_state)
        projected_state = self.projection_operator.project_to_feasible(state_dict)

        feasible_actions = []
        for action in raw_actions:
            test_state = self._apply_action_to_state(state_dict, action)
            if self.projection_operator.is_feasible(test_state):
                feasible_actions.append(action)

        critical = [a for a in feasible_actions if a.priority == "CRITICAL"]
        high = [a for a in feasible_actions if a.priority == "HIGH"]
        medium = [a for a in feasible_actions if a.priority == "MEDIUM"]
        summary = self._generate_summary(feasible_actions, critical, high)

        if not feasible_actions:
            return None

        return DecisionReport(
            actions=feasible_actions,
            summary=summary,
            critical_count=len(critical),
            high_count=len(high),
            medium_count=len(medium),
            total_interventions=len(feasible_actions)
        )

    def _generate_raw_actions(self, topology, discretized_state, stability_report) -> List[EngineeringAction]:
        actions = []
        
        if hasattr(topology, 'nodes'):
            for node in topology.nodes:
                if hasattr(node, 'node_type'):
                    action = EngineeringAction(
                        action_id=f"act_{node.node_id}",
                        action_type=ActionType.MOVE_DETECTOR,
                        target_node_id=node.node_id,
                        priority="HIGH",
                        expected_benefit=0.3,
                        risk_mitigation=0.2
                    )
                    actions.append(action)
        
        return actions[:10]

    def _topology_to_state_dict(self, topology, discretized_state) -> Dict:
        devices = []
        if hasattr(topology, 'nodes'):
            for node in topology.nodes:
                if hasattr(node, 'x') and hasattr(node, 'y'):
                    devices.append({
                        "node_id": node.node_id,
                        "x": node.x,
                        "y": node.y,
                        "type": node.node_type,
                        "zone_id": getattr(node, 'zone_id', 'unknown')
                    })
        return {
            "room_id": getattr(topology, 'room_id', 'unknown'),
            "devices": devices,
            "discretized": discretized_state
        }

    def _apply_action_to_state(self, state: Dict, action: EngineeringAction) -> Dict:
        test_state = dict(state)
        if "devices" in test_state:
            for device in test_state["devices"]:
                if device.get("node_id") == action.target_node_id:
                    if action.action_type == ActionType.MOVE_DETECTOR:
                        device["x"] = device.get("x", 0) + 1.0
                        device["y"] = device.get("y", 0) + 1.0
        return test_state

    def _generate_summary(self, actions: List[EngineeringAction], critical, high) -> Dict:
        return {
            "total_actions": len(actions),
            "top_priorities": len(critical) + len(high),
            "avg_benefit": sum(a.expected_benefit for a in actions) / max(len(actions), 1)
        }


def create_seds_engine():
    return SpectralEngineeringDecisionSystem()