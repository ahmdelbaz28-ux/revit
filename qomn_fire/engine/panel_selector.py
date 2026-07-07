# NOSONAR
"""
QOMN-FIRE FACP SELECTION ENGINE
Reference Standard: NFPA 72 (2022) §10.6.10, UL 864 10th Edition.

V54 Bug Fixes Preserved:
  F2: NAC capacity uses EXACT match — required_nacs = nac_circuit_count
  F3: Sort prefers SMALLEST adequate capacity on ties (right-sizing)
  F4: supports_releasing field + filter logic present
  F5: Battery sizing uses NFPA 72 compliant tiered derating (NOT flat 1.2x)
  F6: Per-device standby current = 0.8 mA (not 1.0 mA)
"""

import hashlib
from typing import Any, Dict, List, Tuple

from qomn_fire.core.errors import FACPSelectionError, Result
from qomn_fire.core.types import (
    FireAlarmPanel,
    PanelRecommendation,
    ProjectRequirements,
)
from qomn_fire.engine.panel_database import MASTER_PANEL_DATABASE


class SelectionEngine:
    @staticmethod
    def compute_battery_ah(
        device_count: int,
        nac_circuit_count: int,
        panel: FireAlarmPanel,
        requires_voice: bool
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculates battery capacity per NFPA 72 §10.6.10 with tiered derating.

        Derating methodology (V54 FIX F5 — NOT flat 1.2x):
          1. Temperature derating: 1.10 (10% compensation for capacity loss at low temp)
          2. Aging derating: 1.15 (15% compensation for battery end-of-life per IEEE 1188)
          3. NFPA margin: 1.20 (20% mandatory margin per NFPA 72 §10.6.10)

        Per-device standby current: 0.8 mA (V54 FIX F6 — NOT 1.0 mA).

        Returns:
            Tuple of (battery_size_ah, derating_details_dict)

        """
        # V54 FIX F6: Per-device standby current = 0.0008 A (0.8 mA), NOT 0.001 A
        standby_load = (device_count * 0.0008) + panel.standby_current_amps
        alarm_load = (nac_circuit_count * 2.0) + (device_count * 0.005) + panel.alarm_current_amps
        alarm_duration_h = 0.25 if requires_voice else 0.0833

        raw_capacity = (standby_load * 24.0) + (alarm_load * alarm_duration_h)

        # V54 FIX F5: Tiered derating — NOT flat 1.2x
        temperature_derating = 1.10
        aging_derating = 1.15
        nfpa_margin = 1.20
        combined_safety_factor = round(
            temperature_derating * aging_derating * nfpa_margin, 6
        )

        battery_size = round(raw_capacity * combined_safety_factor, 2)

        derating_details = {
            "method": "NFPA 72 §10.6.10 tiered derating",
            "temperature_derating": temperature_derating,
            "aging_derating": aging_derating,
            "nfpa_margin": nfpa_margin,
            "combined_safety_factor": combined_safety_factor,
            # BUG-PS1 FIX: Removed duplicate "enhanced_safety_factor" key that was
            # identical to "combined_safety_factor". Having two keys with the same value
            # creates confusion — downstream code doesn't know which to use, and neither
            # provides more information than the other. The combined_safety_factor IS the
            # enhanced/total safety factor: 1.10 (temp) × 1.15 (aging) × 1.20 (NFPA) = 1.518.
            "raw_capacity_ah": round(raw_capacity, 4),
            "per_device_standby_mA": 0.8,
        }

        return battery_size, derating_details

    @classmethod
    def select_panel(cls, req: ProjectRequirements) -> Result[PanelRecommendation, FACPSelectionError]:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        # Enforce code capacity margins (20% spare capacity per NFPA 72 §10.6.10.2)
        required_points = req.device_count * 1.2
        # V54 FIX F2: NAC circuits sized by exact count, NOT 1.2x
        required_nacs = req.nac_circuit_count

        eligible_panels: List[Tuple[FireAlarmPanel, float]] = []

        for p in MASTER_PANEL_DATABASE:
            if p.points_capacity < required_points:
                continue
            if p.nac_capacity < required_nacs:
                continue
            if req.requires_network and not p.supports_networking:
                continue
            if req.requires_voice and not p.supports_voice:
                continue
            # V54 FIX F4: Releasing service filter
            if req.requires_releasing and not p.supports_releasing:
                continue
            if req.jurisdiction == "FDNY" and "FDNY" not in p.listings:
                continue
            if req.jurisdiction == "Canada" and "ULC" not in p.listings:
                continue

            # Multi-criteria scoring
            score = 0.0
            utilization = required_points / p.points_capacity

            if 0.5 <= utilization <= 0.8:
                score += 50.0
            elif 0.3 <= utilization < 0.5:
                score += 20.0
            elif 0.8 < utilization <= 0.95:
                score += 15.0
            else:
                score += 5.0

            if req.preferred_manufacturer and req.preferred_manufacturer.upper() == p.manufacturer.upper():
                score += 100.0

            eligible_panels.append((p, score))

        if not eligible_panels:
            return Result(error=FACPSelectionError(
                message="No compliant FACP models found satisfying constraints in database.",
                code_ref="UL 864 / NFPA 72",
                remedy="Reduce required device loads or transition to a multi-node networked panel architecture."
            ))

        # V54 FIX F3: Deterministic sorting with right-sizing principle
        # Primary: highest score. Tie-break: smallest capacity (right-sizing),
        # then lowest standby draw, then model name for determinism.
        eligible_panels.sort(
            key=lambda x: (x[1], -x[0].points_capacity, -x[0].standby_current_amps, x[0].model),
            reverse=True
        )

        selected, _ = eligible_panels[0]
        alternatives = tuple([p[0].model for p in eligible_panels[1:4]])  # NOSONAR - python:S7496

        capacity_util = required_points / selected.points_capacity
        nac_util = required_nacs / selected.nac_capacity

        warnings = []
        if capacity_util > 0.90:
            warnings.append("FACP loading is close to maximum capacity limits.")
        elif capacity_util < 0.30:
            warnings.append("FACP is significantly oversized for the current device loading.")

        battery_size, derating_details = cls.compute_battery_ah(
            req.device_count,
            req.nac_circuit_count,
            selected,
            req.requires_voice
        )

        # Cryptographic checksum for deterministic outputs
        payload = f"{selected.model}:{selected.manufacturer}:{capacity_util:.4f}:{battery_size:.2f}"
        signature = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        rec = PanelRecommendation(
            recommended_model=selected.model,
            manufacturer=selected.manufacturer,
            capacity_utilization=round(capacity_util, 4),
            nac_utilization=round(nac_util, 4),
            battery_size_ah=battery_size,
            battery_derating_details=derating_details,
            power_supply_watts=selected.power_supply_watts,
            listings=selected.listings,
            code_compliance=(
                "UL 864 10th Edition",
                "NFPA 72 §10.6.10 Compliance"
            ),
            warnings=tuple(warnings),
            alternatives=alternatives,
            signature_hash=signature
        )
        return Result(value=rec)
