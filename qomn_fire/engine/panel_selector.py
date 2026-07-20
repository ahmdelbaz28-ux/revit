# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
QOMN-FIRE FACP SELECTION ENGINE
Reference Standard: NFPA 72 (2022) §10.6.7, UL 864 10th Edition.

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
        requires_voice: bool,
        min_temperature_c: float = 20.0,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculates battery capacity per NFPA 72 §10.6.7 using IEEE 485/1188
        temperature-aware derating (delegates to fireai.core.battery_aging_derating).

        V283 SAFETY FIX: This function previously used a FLAT temperature_derating
        of 1.10 (constant) — meaning batteries were sized the SAME regardless of
        whether the installation was in a 20°C office or a -10°C unheated warehouse.
        At 0°C the real IEEE 485 derating is 1.39 (1/0.72); the old 1.10 constant
        under-sized batteries by ~27% in cold environments.

        The new implementation delegates to fireai.core.battery_aging_derating.size_battery
        — the SAME module used by facp_system.panel_selector — eliminating the
        divergence between the two parallel implementations (P0-5 in critical audit).

        Per-device currents (V54 FIX F6 — preserved):
          - Standby: 0.8 mA per device (realistic for modern addressable detectors)
          - Alarm: 5.0 mA per device (LED annunciator + alarm LED)

        Args:
            device_count: Number of addressable devices on the system.
            nac_circuit_count: Number of Notification Appliance Circuits.
            panel: FireAlarmPanel record with standby/alarm current draws.
            requires_voice: True for voice evacuation (15 min alarm), False for
                non-voice (5 min alarm per NFPA 72 §10.6.7.2.1).
            min_temperature_c: Minimum ambient temperature at the battery
                installation. Defaults to 20°C (room temperature). For unheated
                warehouses / outdoor enclosures, use the 1% winter design temp
                for the installation location per ASHRAE Handbook.

        Returns:
            Tuple of (battery_size_ah, derating_details_dict)

        Raises:
            RuntimeError: if fireai.core.battery_aging_derating is not available
                (life-safety fail-loud — no silent simplified fallback).
        """
        standby_load = (device_count * 0.0008) + panel.standby_current_amps
        alarm_load = (nac_circuit_count * 2.0) + (device_count * 0.005) + panel.alarm_current_amps
        alarm_duration_h = 0.25 if requires_voice else (5.0 / 60.0)

        # Delegate to the production battery sizing module (same as facp_system).
        # This eliminates the duplicate/divergent algorithm — P0-5 critical audit fix.
        try:
            from fireai.core.battery_aging_derating import size_battery

            result = size_battery(
                standby_load_amps=standby_load,
                alarm_load_amps=alarm_load,
                standby_hours=24.0,
                alarm_hours=alarm_duration_h,
                min_temperature_c=min_temperature_c,
                service_life_years=5,
                safety_margin_pct=0.0,  # Derating already provides >= 1.46x safety factor
            )

            derating_details = {
                "method": "NFPA_72_IEEE_485_1188_full_derating",
                "temperature_derating": result.temperature_derating,
                "aging_derating": result.aging_derating,
                "discharge_rate_correction": result.discharge_rate_correction,
                "combined_safety_factor": round(
                    1.0 / max(result.temperature_derating * result.aging_derating * result.discharge_rate_correction, 0.01),
                    2
                ),
                "standby_ah": result.standby_ah,
                "alarm_ah": result.alarm_ah,
                "total_load_ah": result.total_load_ah,
                "min_temperature_c": min_temperature_c,
                "nfpa_reference": "NFPA 72-2022 §10.6.7, IEEE 485, IEEE 1188",
            }

            return round(result.required_ah, 2), derating_details

        except ImportError as exc:
            # battery sizing module. The previous behavior used a flat
            # temperature_derating=1.10 — at 0°C this under-sized batteries
            # by ~27% compared to the IEEE 485 lookup table. In a life-safety
            # system, an under-sized battery means the FACP goes dark during
            # a fire event. ImportError on a critical module MUST fail loud.
            raise RuntimeError(
                f"fireai.core.battery_aging_derating is REQUIRED for life-safety "
                f"battery sizing. The previous 'simplified fallback' used a flat "
                f"temperature_derating=1.10 which under-sized batteries in cold "
                f"environments. Refusing to operate without the production module. "
                f"ImportError: {exc}"
            ) from exc

    @classmethod
    def select_panel(cls, req: ProjectRequirements) -> Result[PanelRecommendation, FACPSelectionError]:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        # Enforce code capacity margins (20% spare capacity per NFPA 72 §10.6.7.2)
        required_points = req.device_count * 1.2
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
                "NFPA 72 §10.6.7 Compliance"
            ),
            warnings=tuple(warnings),
            alternatives=alternatives,
            signature_hash=signature
        )
        return Result(value=rec)
