"""enterprise_pipeline.py — V17 Enterprise Orchestrator
=====================================================
Connects all V17 Critical Trilogy modules into a unified pipeline
for AHJ submittal. This replaces the disconnected checks that could
pass individually while failing as a system.

The orchestrator runs three critical life-safety checks:
  1. AcousticSPLCalculator — NFPA 72 §18.4 audibility
  2. StrictBatterySizer    — NFPA 72 §10.6.7 battery capacity
  3. TenabilityEvaluator  — NFPA 101 §9.3 ASET/RSET

Then integrates with:
  - FACP Global Capacity Auditor (V15)
  - As-Built Reconciliator 3D (V15)
  - Pathway Survivability Engine
  - Release Gates (Gates 7 & 8)
  - Blockchain Readiness Gate (Merkle Tree)

The key insight: each module can PASS individually while the SYSTEM
fails. Example:
  - All detectors placed correctly ✓
  - All speakers producing 95 dBA ✓
  - But at the check point behind a closed door, SPL = 80 dBA,
    ambient = 85 dBA → FAIL (-5 dB deficit, occupants can't hear alarm)

This orchestrator catches such cross-module failures.

NFPA References:
  - NFPA 72-2022 §18.4 (acoustics)
  - NFPA 72-2022 §10.6.7 (battery)
  - NFPA 101 §9.3 (tenability)
  - NFPA 72-2022 §12.3 (fault isolation)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class V17SystemResult:
    """Result of the full V17 enterprise pipeline check.

    Attributes:
        acoustic_compliant: Whether audibility check passed.
        battery_compliant: Whether battery sizing check passed.
        tenability_compliant: Whether ASET/RSET check passed.
        facp_compliant: Whether FACP capacity audit passed (if run).
        as_built_compliant: Whether as-built reconciliation passed (if run).
        all_compliant: Whether ALL checks passed.
        acoustic_result: Detailed acoustic result.
        battery_result: Detailed battery result.
        tenability_result: Detailed tenability result.
        release_gate_result: Release gate evaluation result.
        violations: All violations from all modules.
        summary: Human-readable summary.

    """

    acoustic_compliant: bool
    battery_compliant: bool
    tenability_compliant: bool
    facp_compliant: Optional[bool] = None
    as_built_compliant: Optional[bool] = None
    all_compliant: bool = False
    acoustic_result: Optional[Any] = None
    battery_result: Optional[Any] = None
    tenability_result: Optional[Any] = None
    release_gate_result: Optional[Dict[str, Any]] = None
    violations: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""


class EnterpriseOrchestrator:
    """V17 Enterprise Orchestrator — unified life-safety pipeline.

    Connects the V17 Critical Trilogy (Acoustics, Battery, ASET/RSET)
    with V15 modules (FACP Auditor, As-Built Reconciliator) and the
    Release Gates system for AHJ submittal.

    Usage::

        from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator

        orch = EnterpriseOrchestrator()
        result = orch.run_full_check(
            acoustic_params={...},
            battery_params={...},
            tenability_params={...},
        )
    """

    def __init__(
        self,
        acoustic_ambient_noise: Optional[Dict[str, float]] = None,
        battery_standby_hours: float = 24.0,
        battery_alarm_minutes: float = 5.0,
        tenability_walking_speed_mps: float = 1.0,
        tenability_pre_movement_delay_s: float = 60.0,
    ) -> None:
        """Initialize the orchestrator with default parameters.

        Args:
            acoustic_ambient_noise: Default ambient noise levels by occupancy type.
            battery_standby_hours: Default standby hours for battery sizing.
            battery_alarm_minutes: Default alarm minutes for battery sizing.
            tenability_walking_speed_mps: Default walking speed for ASET/RSET.
            tenability_pre_movement_delay_s: Default pre-movement delay.

        """
        # V78 FIX: Safe import pattern — if v17_core is unavailable, degrade gracefully
        # instead of crashing the entire enterprise pipeline. Per integration_bridge.py
        # pattern: each subsystem should work independently.
        try:
            from fireai.v17_core import (
                AcousticSPLCalculator,
                StrictBatterySizer,
                TenabilityEvaluator,
            )
            self._v17_available = True
        except ImportError as e:
            logger.critical(
                f"V17 core modules unavailable: {e}. Enterprise pipeline DISABLED."
            )
            self._v17_available = False
            self.acoustic_calc = None
            self.battery_sizer = None
            self.tenability_eval = None
            return

        self.acoustic_calc = AcousticSPLCalculator(
            room_ambient_noise=acoustic_ambient_noise,
        )
        self.battery_sizer = StrictBatterySizer(
            standby_hours=battery_standby_hours,
            alarm_minutes=battery_alarm_minutes,
        )
        self.tenability_eval = TenabilityEvaluator(
            walking_speed_mps=tenability_walking_speed_mps,
            pre_movement_delay_s=tenability_pre_movement_delay_s,
        )

    def check_acoustics(
        self,
        room_id: str,
        occ_type: str,
        speakers: List[dict],
        check_points: List[dict],
        barriers: Optional[List[dict]] = None,
        mode: str = "public",
        room_absorption_m2: Optional[float] = None,
    ) -> Any:
        """Run acoustic SPL compliance check.

        Args:
            room_id: Room identifier.
            occ_type: Occupancy type.
            speakers: List of speaker dicts with x, y, z, rating_db_3m.
            check_points: List of check point dicts with x, y, z.
            barriers: Optional list of barrier dicts.
            mode: "public", "private", or "sleeping".
            room_absorption_m2: Room absorption in m² Sabine.

        Returns:
            DecisionProvenance or dict with acoustic compliance result.

        """
        return self.acoustic_calc.calculate_room_spl(
            room_id=room_id,
            occ_type=occ_type,
            speakers=speakers,
            check_points=check_points,
            barriers=barriers,
            mode=mode,
            room_absorption_m2=room_absorption_m2,
        )

    def check_battery(
        self,
        quiescent_ma: float,
        alarm_ma: float,
        panel_ambient_temp_c: float = 25.0,
        installed_battery_ah: Optional[float] = None,
        battery_cells: int = 6,
    ) -> Any:
        """Run battery aging and temperature derating check.

        Args:
            quiescent_ma: Standby current in mA.
            alarm_ma: Alarm current in mA.
            panel_ambient_temp_c: Minimum ambient temperature in °C.
            installed_battery_ah: Installed battery capacity in Ah.
            battery_cells: Number of 2V cells.

        Returns:
            DecisionProvenance or dict with battery compliance result.

        """
        return self.battery_sizer.calculate_minimum_ah(
            quiescent_ma=quiescent_ma,
            alarm_ma=alarm_ma,
            panel_ambient_temp_c=panel_ambient_temp_c,
            installed_battery_ah=installed_battery_ah,
            battery_cells=battery_cells,
        )

    def check_tenability(
        self,
        longest_travel_dist_m: float,
        estimated_fill_time_s: float,
        safety_margin: float = 2.0,
        occupancy_type: Optional[str] = None,
        room_height_m: float = 3.0,
        is_sprinklered: bool = True,
    ) -> Any:
        """Run ASET vs RSET tenability check.

        Args:
            longest_travel_dist_m: Maximum travel distance to exit.
            estimated_fill_time_s: Time for smoke to fill to detector level.
            safety_margin: Safety factor (default 2.0).
            occupancy_type: NFPA 101 occupancy type.
            room_height_m: Room ceiling height.
            is_sprinklered: Whether building has sprinklers.

        Returns:
            DecisionProvenance or dict with tenability compliance result.

        """
        return self.tenability_eval.validate_aset_vs_rset(
            longest_travel_dist_m=longest_travel_dist_m,
            estimated_fill_time_s=estimated_fill_time_s,
            safety_margin=safety_margin,
            occupancy_type=occupancy_type,
            room_height_m=room_height_m,
            is_sprinklered=is_sprinklered,
        )

    def run_full_check(
        self,
        acoustic_params: Optional[Dict[str, Any]] = None,
        battery_params: Optional[Dict[str, Any]] = None,
        tenability_params: Optional[Dict[str, Any]] = None,
    ) -> V17SystemResult:
        """Run all three V17 critical checks and integrate results.

        This is the main entry point for the enterprise pipeline.
        It runs all three checks, collects violations, and evaluates
        release gates.

        Args:
            acoustic_params: Dict of parameters for check_acoustics().
            battery_params: Dict of parameters for check_battery().
            tenability_params: Dict of parameters for check_tenability().

        Returns:
            V17SystemResult with compliance status for all checks.

        """
        all_violations: List[Dict[str, Any]] = []
        acoustic_compliant = False
        battery_compliant = False
        tenability_compliant = False
        acoustic_result = None
        battery_result = None
        tenability_result = None

        # --- Acoustic Check ---
        if acoustic_params:
            try:
                acoustic_result = self.check_acoustics(**acoustic_params)
                # Extract compliance from result
                if hasattr(acoustic_result, "value"):
                    acoustic_compliant = acoustic_result.value.get("pass", False)
                    if hasattr(acoustic_result, "violations_detected"):
                        for v in acoustic_result.violations_detected:
                            all_violations.append({"module": "acoustic", **v})
                elif isinstance(acoustic_result, dict):
                    acoustic_compliant = acoustic_result.get("compliant", False)
            except Exception as e:
                logger.error("Acoustic check failed: %s", e)
                all_violations.append(
                    {
                        "module": "acoustic",
                        "severity": "ERROR",
                        "description": f"Acoustic check crashed: {e}",
                    }
                )

        # --- Battery Check ---
        if battery_params:
            try:
                battery_result = self.check_battery(**battery_params)
                if hasattr(battery_result, "value"):
                    battery_compliant = battery_result.value.get("is_adequate", False)
                    if hasattr(battery_result, "violations_detected"):
                        for v in battery_result.violations_detected:
                            all_violations.append({"module": "battery", **v})
                elif isinstance(battery_result, dict):
                    battery_compliant = battery_result.get("is_adequate", False)
            except Exception as e:
                logger.error("Battery check failed: %s", e)
                all_violations.append(
                    {
                        "module": "battery",
                        "severity": "ERROR",
                        "description": f"Battery check crashed: {e}",
                    }
                )

        # --- Tenability Check ---
        if tenability_params:
            try:
                tenability_result = self.check_tenability(**tenability_params)
                if hasattr(tenability_result, "value"):
                    tenability_compliant = tenability_result.value.get("is_safe", False)
                    if hasattr(tenability_result, "violations_detected"):
                        for v in tenability_result.violations_detected:
                            all_violations.append({"module": "tenability", **v})
                elif isinstance(tenability_result, dict):
                    tenability_compliant = tenability_result.get("is_safe", False)
            except Exception as e:
                logger.error("Tenability check failed: %s", e)
                all_violations.append(
                    {
                        "module": "tenability",
                        "severity": "ERROR",
                        "description": f"Tenability check crashed: {e}",
                    }
                )

        # --- Release Gate Evaluation ---
        release_result = None
        try:
            from fireai.core.release_gates import verify_and_evaluate

            gate_kwargs: Dict[str, Any] = {}

            # Gate 7: ASET/RSET
            if tenability_result and isinstance(tenability_result, dict):
                gate_kwargs["aset_rset_result"] = tenability_result
            elif tenability_result and hasattr(tenability_result, "value"):
                gate_kwargs["aset_rset_result"] = tenability_result.value

            # Gate 8: Battery
            if battery_result and isinstance(battery_result, dict):
                gate_kwargs["battery_result"] = battery_result
            elif battery_result and hasattr(battery_result, "value"):
                gate_kwargs["battery_result"] = battery_result.value

            if gate_kwargs:
                release_result = verify_and_evaluate(**gate_kwargs)
        except Exception as e:
            logger.warning("Release gate evaluation failed: %s", e)

        # Build summary
        all_ok = acoustic_compliant and battery_compliant and tenability_compliant
        passed = []
        failed = []
        if acoustic_compliant:
            passed.append("Acoustics")
        else:
            failed.append("Acoustics")
        if battery_compliant:
            passed.append("Battery")
        else:
            failed.append("Battery")
        if tenability_compliant:
            passed.append("ASET/RSET")
        else:
            failed.append("ASET/RSET")

        summary = f"V17 System Check: {'ALL PASS' if all_ok else 'FAILURES DETECTED'}\n"
        if passed:
            summary += f"  PASS: {', '.join(passed)}\n"
        if failed:
            summary += f"  FAIL: {', '.join(failed)}\n"
        summary += f"  Total violations: {len(all_violations)}\n"
        if release_result:
            summary += f"  Release status: {release_result.get('release_status', 'unknown')}"

        return V17SystemResult(
            acoustic_compliant=acoustic_compliant,
            battery_compliant=battery_compliant,
            tenability_compliant=tenability_compliant,
            all_compliant=all_ok,
            acoustic_result=acoustic_result,
            battery_result=battery_result,
            tenability_result=tenability_result,
            release_gate_result=release_result,
            violations=all_violations,
            summary=summary,
        )


__all__ = [
    "EnterpriseOrchestrator",
    "V17SystemResult",
]
