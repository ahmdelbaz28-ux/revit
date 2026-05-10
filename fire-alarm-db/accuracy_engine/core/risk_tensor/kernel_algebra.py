import numpy as np
from math import sqrt
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Callable
from enum import Enum


class InteractionMode(Enum):
    COMMUTATIVE = "commutative"
    DOMINANCE = "dominance"
    SUPPRESSION = "suppression"
    SATURATION = "saturation"


@dataclass
class KernelInteraction:
    mode: InteractionMode
    blend_weight: float = 0.5
    override_priority: int = 0
    attenuation_factor: float = 1.0
    saturation_cap: float = 1.0


@dataclass
class StabilityConstraints:
    beta: float = 0.95
    epsilon: float = 0.05
    lip_constant: float = 0.98
    graph_commutativity_tolerance: float = 0.1

    def validate_operator_norm(self, interaction_matrix: Dict) -> bool:
        if not interaction_matrix:
            return True
        norms = []
        for interaction in interaction_matrix.values():
            w = getattr(interaction, 'blend_weight', 0.5)
            att = getattr(interaction, 'attenuation_factor', 1.0)
            cap = getattr(interaction, 'saturation_cap', 1.0)
            op_norm = max(w, att, cap)
            norms.append(op_norm)
        avg_norm = sum(norms) / len(norms) if norms else 0
        return avg_norm <= self.beta

    def validate_spectral_separation(self, eigenvalues: np.ndarray) -> Tuple[bool, List[str]]:
        if len(eigenvalues) < 2:
            return True, []
        warnings = []
        sorted_ev = sorted(abs(ev) for ev in eigenvalues)
        for i in range(len(sorted_ev) - 1):
            if abs(sorted_ev[i+1] - sorted_ev[i]) < self.epsilon:
                warnings.append(f"Spectral clustering: |λ_{i+1}| - |λ_{i}| = {abs(sorted_ev[i+1] - sorted_ev[i]):.4f} < {self.epsilon}")
        return len(warnings) == 0, warnings

    def validate_lipschitz(self, interaction_matrix: Dict) -> bool:
        if not interaction_matrix:
            return True
        max_lip = 0.0
        for interaction in interaction_matrix.values():
            w = getattr(interaction, 'blend_weight', 0.5)
            priority = getattr(interaction, 'override_priority', 0)
            lip_est = w + (priority / 10.0) * 0.3
            max_lip = max(max_lip, lip_est)
        return max_lip <= self.lip_constant


class KernelInteractionAlgebra:
    def __init__(self):
        self.interaction_matrix: Dict[Tuple[str, str], KernelInteraction] = {}
        self._build_default_algebra()

    def _build_default_algebra(self):
        fire = "fire"
        smoke = "smoke"
        electrical = "electrical"
        structural = "structural"

        self.add_interaction(smoke, smoke, InteractionMode.COMMUTATIVE, blend_weight=0.5)
        self.add_interaction(smoke, electrical, InteractionMode.COMMUTATIVE, blend_weight=0.6)
        self.add_interaction(smoke, structural, InteractionMode.COMMUTATIVE, blend_weight=0.4)

        self.add_interaction(fire, smoke, InteractionMode.DOMINANCE, override_priority=10)
        self.add_interaction(fire, electrical, InteractionMode.DOMINANCE, override_priority=8)
        self.add_interaction(fire, structural, InteractionMode.DOMINANCE, override_priority=9)
        self.add_interaction(fire, fire, InteractionMode.SATURATION, saturation_cap=1.0)

        self.add_interaction(electrical, smoke, InteractionMode.COMMUTATIVE, blend_weight=0.5)
        self.add_interaction(electrical, electrical, InteractionMode.SATURATION, saturation_cap=0.8)
        self.add_interaction(electrical, structural, InteractionMode.COMMUTATIVE, blend_weight=0.3)

        self.add_interaction(structural, smoke, InteractionMode.COMMUTATIVE, blend_weight=0.2)
        self.add_interaction(structural, electrical, InteractionMode.COMMUTATIVE, blend_weight=0.2)
        self.add_interaction(structural, structural, InteractionMode.SATURATION, saturation_cap=0.7)

    def add_interaction(self, kernel_a: str, kernel_b: str, mode: InteractionMode, **kwargs):
        key = (kernel_a, kernel_b)
        self.interaction_matrix[key] = KernelInteraction(mode=mode, **kwargs)

    def get_interaction(self, kernel_a: str, kernel_b: str) -> KernelInteraction:
        key = (kernel_a, kernel_b)
        if key in self.interaction_matrix:
            return self.interaction_matrix[key]
        reverse_key = (kernel_b, kernel_a)
        if reverse_key in self.interaction_matrix:
            return self.interaction_matrix[reverse_key]
        return KernelInteraction(mode=InteractionMode.COMMUTATIVE, blend_weight=0.5)

    def compose(self, kernel_a: str, kernel_b: str, value_a: float, value_b: float) -> float:
        interaction = self.get_interaction(kernel_a, kernel_b)

        if interaction.mode == InteractionMode.COMMUTATIVE:
            w = interaction.blend_weight
            return w * value_a + (1 - w) * value_b

        elif interaction.mode == InteractionMode.DOMINANCE:
            if interaction.override_priority >= 5:
                return value_a
            else:
                return value_b

        elif interaction.mode == InteractionMode.SUPPRESSION:
            return value_a * interaction.attenuation_factor

        elif interaction.mode == InteractionMode.SATURATION:
            return min(value_a + value_b, interaction.saturation_cap)

        return (value_a + value_b) / 2.0

    def compose_multi(self, kernels: List[str], values: List[float]) -> float:
        if not kernels:
            return 0.0
        if len(kernels) == 1:
            return values[0]

        result = values[0]
        for i in range(1, len(kernels)):
            result = self.compose(kernels[0], kernels[i], result, values[i])

        return result

    def enforce_stability_constraints(self) -> Dict[str, float]:
        corrections = {}

        for (ka, kb), interaction in self.interaction_matrix.items():
            mode = interaction.mode

            if mode == InteractionMode.DOMINANCE:
                if interaction.override_priority > 8:
                    interaction.override_priority = 7
                    corrections[f"{ka}_{kb}_dominance"] = 7.0

            if mode == InteractionMode.COMMUTATIVE:
                if interaction.blend_weight > 0.8:
                    interaction.blend_weight = 0.7
                    corrections[f"{ka}_{kb}_blend"] = 0.7

            if mode == InteractionMode.SATURATION:
                if interaction.saturation_cap > 0.95:
                    interaction.saturation_cap = 0.9
                    corrections[f"{ka}_{kb}_saturation"] = 0.9

            if mode == InteractionMode.SUPPRESSION:
                if interaction.attenuation_factor < 0.1:
                    interaction.attenuation_factor = 0.15
                    corrections[f"{ka}_{kb}_attenuation"] = 0.15

        return corrections

    def project_to_stable_manifold(self) -> Tuple[bool, Dict]:
        corrections = self.enforce_stability_constraints()

        constraints = StabilityConstraints()
        is_bounded = constraints.validate_operator_norm(self.interaction_matrix)
        is_lipschitz = constraints.validate_lipschitz(self.interaction_matrix)

        interaction_count = len(self.interaction_matrix)
        dominance_count = sum(1 for v in self.interaction_matrix.values() if v.mode == InteractionMode.DOMINANCE)

        if dominance_count > interaction_count * 0.4:
            for (ka, kb), interaction in self.interaction_matrix.items():
                if interaction.mode == InteractionMode.DOMINANCE:
                    interaction.override_priority = max(1, interaction.override_priority - 3)
                    corrections[f"{ka}_{kb}_dominance_reduced"] = interaction.override_priority

        is_valid = is_bounded and is_lipschitz

        return is_valid, {
            "is_bounded": is_bounded,
            "is_lipschitz": is_lipschitz,
            "dominance_ratio": dominance_count / max(interaction_count, 1),
            "corrections_applied": corrections
        }

    @property
    def is_stable(self) -> bool:
        constraints = StabilityConstraints()
        return (constraints.validate_operator_norm(self.interaction_matrix) and
                constraints.validate_lipschitz(self.interaction_matrix))