from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Set, Optional
import numpy as np
from math import sqrt


@dataclass
class DecisionClass:
    class_id: str
    decision_type: str
    state_indices: List[int]
    centroid: Dict[str, float]
    boundary_distance: float


@dataclass
class DecisionStratum:
    stratum_id: str
    decision_class: str
    invariant_metrics: Dict[str, float]
    state_count: int


@dataclass
class SufficientStatistics:
    metric_name: str
    importance_score: float
    decision_correlation: float
    preserves_boundary: bool


class DecisionStratificationEngine:
    def __init__(self):
        self.decision_classes: List[DecisionClass] = []
        self.strata: List[DecisionStratum] = []
        self.sufficient_stats: List[SufficientStatistics] = []
        self.boundary_metrics: Dict[str, float] = {}

    def derive_equivalence_relation(self, states: List[Dict], decisions: List[str]) -> np.ndarray:
        unique_decisions = list(set(decisions))
        equivalence_matrix = np.zeros((len(states), len(states)))

        for i in range(len(states)):
            for j in range(len(states)):
                if decisions[i] == decisions[j]:
                    equivalence_matrix[i][j] = 1.0

        self.decision_classes = []
        for dec in unique_decisions:
            indices = [i for i, d in enumerate(decisions) if d == dec]
            centroid = self._compute_centroid([states[i] for i in indices])
            boundary_dist = self._compute_boundary_distance(states, indices)

            self.decision_classes.append(DecisionClass(
                class_id=f"DC_{dec}",
                decision_type=dec,
                state_indices=indices,
                centroid=centroid,
                boundary_distance=boundary_dist
            ))

        return equivalence_matrix

    def find_sufficient_statistics(self, states: List[Dict], decisions: List[str]) -> List[SufficientStatistics]:
        all_metrics = self._extract_all_metrics(states)

        self.sufficient_stats = []
        for metric_name, values in all_metrics.items():
            correlation = self._compute_decision_correlation(values, decisions)
            preserves = self._check_boundary_preservation(values, decisions)

            importance = correlation * (1.5 if preserves else 0.5)

            self.sufficient_stats.append(SufficientStatistics(
                metric_name=metric_name,
                importance_score=importance,
                decision_correlation=correlation,
                preserves_boundary=preserves
            ))

        self.sufficient_stats.sort(key=lambda s: s.importance_score, reverse=True)

        threshold = 0.6
        for stat in self.sufficient_stats:
            if stat.importance_score >= threshold and stat.preserves_boundary:
                self.boundary_metrics[stat.metric_name] = stat.importance_score

        return self.sufficient_stats

    def construct_quotient_map(self, states: List[Dict], decisions: List[str]) -> Dict[str, List[int]]:
        self.derive_equivalence_relation(states, decisions)
        self.find_sufficient_statistics(states, decisions)

        strata_map = {}

        for i, state in enumerate(states):
            dec = decisions[i]
            stratum_key = self._compute_stratum_key(state, dec)

            if stratum_key not in strata_map:
                strata_map[stratum_key] = {
                    "decision_class": dec,
                    "state_indices": [],
                    "invariant_metrics": {}
                }

            strata_map[stratum_key]["state_indices"].append(i)

            for metric_name in self.boundary_metrics:
                if metric_name in state:
                    strata_map[stratum_key]["invariant_metrics"][metric_name] = state[metric_name]

        self.strata = []
        for stratum_key, data in strata_map.items():
            self.strata.append(DecisionStratum(
                stratum_id=stratum_key,
                decision_class=data["decision_class"],
                invariant_metrics=data["invariant_metrics"],
                state_count=len(data["state_indices"])
            ))

        return strata_map

    def validate_stratification(self) -> Dict:
        violations = []
        seen_pairs = set()

        for i, stratum_a in enumerate(self.strata):
            for j, stratum_b in enumerate(self.strata):
                if j <= i:
                    continue
                if stratum_a.decision_class != stratum_b.decision_class:
                    overlap = self._check_metric_overlap(stratum_a.invariant_metrics, stratum_b.invariant_metrics)
                    if overlap:
                        pair_key = f"{stratum_a.stratum_id}_{stratum_b.stratum_id}"
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            violations.append({
                                "stratum_a": stratum_a.stratum_id,
                                "stratum_b": stratum_b.stratum_id,
                                "class_a": stratum_a.decision_class,
                                "class_b": stratum_b.decision_class,
                                "overlap_metrics": overlap
                            })

        return {
            "is_valid": len(violations) == 0,
            "violations": violations,
            "total_strata": len(self.strata),
            "decision_classes": len(set(s.decision_class for s in self.strata)),
            "boundary_metrics_count": len(self.boundary_metrics)
        }

    def _compute_centroid(self, state_group: List[Dict]) -> Dict[str, float]:
        if not state_group:
            return {}

        centroid = {}
        numeric_keys = set()
        for state in state_group:
            for key, value in state.items():
                if isinstance(value, (int, float)):
                    numeric_keys.add(key)

        for key in numeric_keys:
            values = [s.get(key, 0.0) for s in state_group if isinstance(s.get(key), (int, float))]
            if values:
                centroid[key] = sum(values) / len(values)

        return centroid

    def _compute_boundary_distance(self, all_states: List[Dict], class_indices: List[int]) -> float:
        if not class_indices:
            return 0.0

        min_dist = float("inf")
        for i in class_indices:
            for j, state in enumerate(all_states):
                if j not in class_indices:
                    dist = self._state_distance(all_states[i], state)
                    min_dist = min(min_dist, dist)

        return min_dist if min_dist != float("inf") else 0.0

    def _state_distance(self, state_a: Dict, state_b: Dict) -> float:
        diff_sum = 0.0
        count = 0

        for key in set(state_a.keys()) | set(state_b.keys()):
            val_a = state_a.get(key, 0.0)
            val_b = state_b.get(key, 0.0)
            if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                diff_sum += (val_a - val_b) ** 2
                count += 1

        return sqrt(diff_sum) if count > 0 else 0.0

    def _extract_all_metrics(self, states: List[Dict]) -> Dict[str, List[float]]:
        metrics = {}

        for state in states:
            for key, value in state.items():
                if isinstance(value, (int, float)):
                    if key not in metrics:
                        metrics[key] = []
                    metrics[key].append(value)

        return metrics

    def _compute_decision_correlation(self, metric_values: List[float], decisions: List[str]) -> float:
        if len(set(decisions)) <= 1:
            return 0.0

        decision_groups = {}
        for val, dec in zip(metric_values, decisions):
            if dec not in decision_groups:
                decision_groups[dec] = []
            decision_groups[dec].append(val)

        group_means = {}
        for dec, vals in decision_groups.items():
            group_means[dec] = sum(vals) / len(vals) if vals else 0.0

        overall_mean = sum(metric_values) / len(metric_values) if metric_values else 0.0

        between_var = 0.0
        for dec, vals in decision_groups.items():
            between_var += len(vals) * (group_means[dec] - overall_mean) ** 2

        within_var = 0.0
        for dec, vals in decision_groups.items():
            for v in vals:
                within_var += (v - group_means[dec]) ** 2

        total_var = between_var + within_var
        return between_var / total_var if total_var > 0 else 0.0

    def _check_boundary_preservation(self, metric_values: List[float], decisions: List[str]) -> bool:
        if len(set(decisions)) <= 1:
            return True

        decision_groups = {}
        for val, dec in zip(metric_values, decisions):
            if dec not in decision_groups:
                decision_groups[dec] = {"min": val, "max": val}
            else:
                decision_groups[dec]["min"] = min(decision_groups[dec]["min"], val)
                decision_groups[dec]["max"] = max(decision_groups[dec]["max"], val)

        unique_decisions = list(decision_groups.keys())
        for i in range(len(unique_decisions)):
            for j in range(i + 1, len(unique_decisions)):
                range_a = decision_groups[unique_decisions[i]]
                range_b = decision_groups[unique_decisions[j]]
                if range_a["min"] <= range_b["max"] and range_b["min"] <= range_a["max"]:
                    return False

        return True

    def _compute_stratum_key(self, state: Dict, decision: str) -> str:
        stable_metrics = []
        for metric_name in sorted(self.boundary_metrics.keys()):
            if metric_name in state:
                stable_metrics.append(f"{metric_name}={state[metric_name]:.2f}")

        return f"{decision}|{'_'.join(stable_metrics)}" if stable_metrics else decision

    def _check_metric_overlap(self, metrics_a: Dict, metrics_b: Dict) -> List[str]:
        overlap = []
        for key in set(metrics_a.keys()) & set(metrics_b.keys()):
            if abs(metrics_a[key] - metrics_b[key]) < 0.2:
                overlap.append(key)
        return overlap