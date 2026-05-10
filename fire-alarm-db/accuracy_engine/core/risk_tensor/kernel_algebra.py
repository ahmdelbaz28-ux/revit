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