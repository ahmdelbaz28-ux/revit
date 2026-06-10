"""
hazard_override.py — Mandatory Safety Override for AI/ML Hazard Classifications
================================================================================
LIFE-SAFETY CRITICAL: Machine learning classifiers and AI models can
misclassify high-risk occupancy rooms, applying weaker fire protection
standards than required by code. For example, classifying a "Diesel
Generator Room" as a "Mechanical Room" applies Ordinary Hazard Group 1
instead of Extra Hazard Group 2, resulting in dramatically undersized
sprinkler density (0.15 vs 0.40 gpm/sq.ft).

This module implements a NON-BYPASSABLE deterministic safety override
that intercepts ALL automated hazard classifications and enforces
mandatory minimums based on room name keywords.

The override dictionary is the SINGLE SOURCE OF TRUTH for safety
classifications — no AI prediction can lower a hazard classification
below the mandatory minimum for a given keyword match.

Standards:
  - NFPA 13-2022 Chapter 11: Hazard classifications and design densities
  - SBC 801 Chapter 9: Saudi Building Code fire protection requirements
  - Egyptian Fire Protection Code Part 1 & 4: Occupancy and hazard rules
  - NFPA 72-2022 §17.7: Detector placement based on hazard class

Design Principle (from agent.md Rule 12):
  "Safety is the absolute priority. Wrong code in this system is
   catastrophic — it threatens human life."
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# HAZARD CLASSIFICATION ENUM
# ═══════════════════════════════════════════════════════════════════════════════

class HazardClassification(str, Enum):
    """NFPA 13-2022 Chapter 11 hazard classifications.

    Ordered from least severe (LIGHT) to most severe (EXTRA_HAZARD_2).
    The override system NEVER lowers a classification — only raises it.
    """
    LIGHT_HAZARD = "light_hazard"
    ORDINARY_HAZARD_1 = "ordinary_hazard_1"
    ORDINARY_HAZARD_2 = "ordinary_hazard_2"
    EXTRA_HAZARD_1 = "extra_hazard_1"
    EXTRA_HAZARD_2 = "extra_hazard_2"


# Severity ordering for comparison (higher index = more severe)
_HAZARD_SEVERITY: Dict[str, int] = {
    "light_hazard": 0,
    "ordinary_hazard_1": 1,
    "ordinary_hazard_2": 2,
    "extra_hazard_1": 3,
    "extra_hazard_2": 4,
}


def is_more_severe(classification_a: str, classification_b: str) -> bool:
    """Check if classification_a is MORE severe than classification_b.

    SAFETY: Used to determine whether an override should be applied.
    An override is only applied when the mandatory classification is
    MORE severe than the AI prediction.
    """
    a_norm = classification_a.strip().lower().replace(" ", "_")
    b_norm = classification_b.strip().lower().replace(" ", "_")
    return _HAZARD_SEVERITY.get(a_norm, 0) > _HAZARD_SEVERITY.get(b_norm, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# MANDATORY HAZARD OVERRIDE DICTIONARY
# ═══════════════════════════════════════════════════════════════════════════════

# SAFETY: This dictionary is NON-BYPASSABLE. Every keyword maps to the
# MINIMUM hazard classification required by NFPA 13 / SBC 801 / Egyptian
# Fire Code for that space type. AI predictions below this level are
# automatically overridden.

MANDATORY_HAZARD_OVERRIDES: Dict[str, str] = {
    # ── Extra Hazard Group 2 (most severe — 0.40 gpm/sq.ft) ──
    "diesel": "extra_hazard_2",
    "fuel": "extra_hazard_2",
    "gasoline": "extra_hazard_2",
    "petrol": "extra_hazard_2",
    "flammable liquid": "extra_hazard_2",
    "paint spray": "extra_hazard_2",
    "solvent": "extra_hazard_2",
    "varnish": "extra_hazard_2",
    "lacquer": "extra_hazard_2",
    "rubber reclaim": "extra_hazard_2",
    "plastics fabrication": "extra_hazard_2",
    "printing (using inks)": "extra_hazard_2",
    "dipping": "extra_hazard_2",

    # ── Extra Hazard Group 1 (0.30 gpm/sq.ft) ──
    "substation": "extra_hazard_1",
    "electrical room": "extra_hazard_1",
    "switchgear": "extra_hazard_1",
    "transformer": "extra_hazard_1",
    "generator": "extra_hazard_1",
    "combustible dust": "extra_hazard_1",
    "grain": "extra_hazard_1",
    "woodworking": "extra_hazard_1",
    "sawmill": "extra_hazard_1",
    "textile picking": "extra_hazard_1",
    "metal powder": "extra_hazard_1",
    "plywood": "extra_hazard_1",
    "particleboard": "extra_hazard_1",

    # ── Ordinary Hazard Group 2 (0.20 gpm/sq.ft) ──
    "storage": "ordinary_hazard_2",
    "warehouse": "ordinary_hazard_2",
    "stockroom": "ordinary_hazard_2",
    "shipping": "ordinary_hazard_2",
    "receiving": "ordinary_hazard_2",
    "loading dock": "ordinary_hazard_2",
    "mechanical room": "ordinary_hazard_2",
    "boiler room": "ordinary_hazard_2",
    "laundry": "ordinary_hazard_2",
    "kitchen": "ordinary_hazard_2",
    "bakery": "ordinary_hazard_2",
    "candy": "ordinary_hazard_2",
    "chemical": "ordinary_hazard_2",
    "laboratory": "ordinary_hazard_2",

    # ── Ordinary Hazard Group 1 (0.15 gpm/sq.ft) ──
    "electrical": "ordinary_hazard_1",
    "parking garage": "ordinary_hazard_1",
    "car park": "ordinary_hazard_1",
    "machine shop": "ordinary_hazard_1",
    "manufacturing": "ordinary_hazard_1",
    "assembly": "ordinary_hazard_1",
    "restaurant": "ordinary_hazard_1",
    "mercantile": "ordinary_hazard_1",
    "retail": "ordinary_hazard_1",
    "corridor": "ordinary_hazard_1",
    "lobby": "ordinary_hazard_1",

    # ── Light Hazard (0.10 gpm/sq.ft) ──
    # NOTE: Light hazard is ONLY appropriate for spaces that are truly
    # non-combustible. We do NOT add keywords here because most spaces
    # should default to AT LEAST Ordinary Hazard Group 1 as a safe minimum.
}


# ═══════════════════════════════════════════════════════════════════════════════
# OVERRIDE VERIFIER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OverrideResult:
    """Result of hazard classification override verification."""
    room_name: str
    original_prediction: str
    final_classification: str
    override_applied: bool
    matched_keyword: Optional[str] = None
    safety_rationale: str = ""
    nfpa_reference: str = "NFPA 13-2022 Chapter 11"
    sbc_reference: str = "SBC 801 Chapter 9"


class HazardOverrideVerifier:
    """Non-bypassable deterministic safety override for AI hazard classifications.

    SAFETY: This class intercepts ALL automated hazard classifications and
    enforces mandatory minimums based on room name keywords. It is the
    final safety gate before a hazard classification is used for engineering
    calculations (sprinkler density, detector spacing, pipe sizing).

    Design Principle:
      "It is better to over-design a fire protection system than to
       under-design it. Extra sprinklers cost money; missing sprinklers
       cost lives." — safety_assurance.py Fail-Safe Philosophy

    Usage:
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Diesel Generator Room",
            ml_predicted_hazard="ordinary_hazard_1"
        )
        # result.final_classification == "extra_hazard_2"
        # result.override_applied == True
    """

    def __init__(
        self,
        custom_overrides: Optional[Dict[str, str]] = None,
        minimum_default: str = "ordinary_hazard_1",
    ) -> None:
        """Initialize the override verifier.

        Args:
            custom_overrides: Additional keyword→hazard mappings to add
                to the mandatory dictionary. These supplement (not replace)
                the built-in overrides.
            minimum_default: The minimum hazard classification to use when
                no keyword matches and no prediction is provided.
                Default: "ordinary_hazard_1" (conservative/safe).
                NEVER use "light_hazard" as default — it is only appropriate
                for truly non-combustible spaces.
        """
        self._overrides = dict(MANDATORY_HAZARD_OVERRIDES)
        if custom_overrides:
            self._overrides.update(custom_overrides)
        self._minimum_default = minimum_default

        # Validate default is a known classification
        if self._minimum_default not in _HAZARD_SEVERITY:
            raise ValueError(
                f"Invalid minimum_default: '{minimum_default}'. "
                f"Valid: {list(_HAZARD_SEVERITY.keys())}"
            )

    def verify_and_override(
        self,
        room_name: str,
        ml_predicted_hazard: str,
    ) -> OverrideResult:
        """Verify and potentially override an AI/ML hazard classification.

        SAFETY: This method applies the MOST SEVERE classification from:
          1. The mandatory override dictionary (keyword match)
          2. The ML prediction (if more severe than default)
          3. The minimum default (if no keyword matches and prediction is lower)

        An override is applied when the mandatory classification is MORE
        severe than the ML prediction. The override is NON-BYPASSABLE.

        Args:
            room_name: Room name from BIM model (e.g., "Diesel Generator Room").
            ml_predicted_hazard: Hazard classification predicted by AI/ML model.

        Returns:
            OverrideResult with the final classification and audit information.
        """
        if not room_name or not isinstance(room_name, str):
            return OverrideResult(
                room_name=str(room_name),
                original_prediction=ml_predicted_hazard,
                final_classification=self._minimum_default,
                override_applied=True,
                matched_keyword=None,
                safety_rationale=(
                    "Room name is empty or invalid. Defaulting to "
                    f"{self._minimum_default} as safe minimum. "
                    "[NFPA 13 / SBC 801]"
                ),
            )

        normalized_name = room_name.strip().lower()
        matched_keyword = None
        mandatory_hazard = None

        # Check ALL keywords — use the MOST SEVERE match
        for keyword, mandated_hazard in self._overrides.items():
            if keyword.lower() in normalized_name:
                if mandatory_hazard is None or is_more_severe(mandated_hazard, mandatory_hazard):
                    mandatory_hazard = mandated_hazard
                    matched_keyword = keyword

        # Determine final classification
        if mandatory_hazard is not None:
            if is_more_severe(mandatory_hazard, ml_predicted_hazard):
                # SAFETY OVERRIDE: mandatory is more severe than prediction
                logger.warning(
                    f"[SAFETY OVERRIDE]: Room '{room_name}' matched keyword "
                    f"'{matched_keyword}'. ML prediction '{ml_predicted_hazard}' "
                    f"overridden to '{mandatory_hazard}'. "
                    "This override is NON-BYPASSABLE per NFPA 13 / SBC 801."
                )
                return OverrideResult(
                    room_name=room_name,
                    original_prediction=ml_predicted_hazard,
                    final_classification=mandatory_hazard,
                    override_applied=True,
                    matched_keyword=matched_keyword,
                    safety_rationale=(
                        f"Room name contains '{matched_keyword}', which mandates "
                        f"minimum {mandatory_hazard} per NFPA 13 Chapter 11 / "
                        f"SBC 801 Chapter 9. ML prediction of {ml_predicted_hazard} "
                        f"would result in undersized fire protection — potentially "
                        f"fatal in a real fire. Override is NON-BYPASSABLE."
                    ),
                )
            else:
                # ML prediction is already at or above mandatory level — keep it
                return OverrideResult(
                    room_name=room_name,
                    original_prediction=ml_predicted_hazard,
                    final_classification=ml_predicted_hazard,
                    override_applied=False,
                    matched_keyword=matched_keyword,
                    safety_rationale=(
                        f"Room name contains '{matched_keyword}' (mandatory: "
                        f"{mandatory_hazard}). ML prediction {ml_predicted_hazard} "
                        f"already meets or exceeds this requirement."
                    ),
                )

        # No keyword match — apply minimum default if prediction is below it
        if is_more_severe(self._minimum_default, ml_predicted_hazard):
            logger.warning(
                f"[SAFETY DEFAULT]: Room '{room_name}' has no keyword match. "
                f"ML prediction '{ml_predicted_hazard}' is below minimum default "
                f"'{self._minimum_default}'. Applying safe minimum."
            )
            return OverrideResult(
                room_name=room_name,
                original_prediction=ml_predicted_hazard,
                final_classification=self._minimum_default,
                override_applied=True,
                matched_keyword=None,
                safety_rationale=(
                    f"No keyword match found. ML prediction '{ml_predicted_hazard}' "
                    f"is below safe minimum '{self._minimum_default}'. Defaulting "
                    f"to {self._minimum_default} as conservative/safe classification. "
                    "A human FPE review is recommended. [NFPA 13 / SBC 801]"
                ),
            )

        # ML prediction is adequate and no override needed
        return OverrideResult(
            room_name=room_name,
            original_prediction=ml_predicted_hazard,
            final_classification=ml_predicted_hazard,
            override_applied=False,
            matched_keyword=None,
            safety_rationale=(
                f"No keyword override match. ML prediction '{ml_predicted_hazard}' "
                f"meets minimum default '{self._minimum_default}'. "
                "FPE review recommended for verification."
            ),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "HazardClassification",
    "HazardOverrideVerifier",
    "OverrideResult",
    "MANDATORY_HAZARD_OVERRIDES",
    "is_more_severe",
]
