"""
ETAP Expert Skill — Extended Simulations (V131 Phase 3).
========================================================
Three additional simulations added per Operator request:
    8. Motor Starting (IEEE 399 — Voltage Dip + Acceleration Time)
    9. Cable Pulling (3D Tension Calculations per NEC Chapter 9)
    10. Ground Grid Design (IEEE 80-2013 — Touch/Step Voltage)

These complement the existing 7 simulations in internal_simulation_engine.py.
Kept in a separate module to avoid bloating the main engine file.

Author: FireAI Project
Version: 1.0.0
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION 8: MOTOR STARTING (IEEE 399 — Voltage Dip + Acceleration Time)
# ═══════════════════════════════════════════════════════════════════════════
#
# Per skill Section 7.3 (Motor Starting Analysis):
#   - Starting methods: DOL (6-8×FLA), Star-Delta (2-3×FLA), VFD (1-1.5×FLA)
#   - Voltage dip limits: Lighting 5%, Computers 10%, Motors running 15%
#   - Acceleration time: t_acc = ∫(J×dω)/(T_motor - T_load)


@dataclass
class MotorStartingResult:
    """Result of motor starting analysis."""

    motor_hp: float
    motor_voltage_v: float
    motor_fla_a: float
    starting_method: str
    starting_current_a: float
    starting_multiple: float  # Multiple of FLA
    source_impedance_ohm: float
    voltage_dip_pct: float
    voltage_dip_limit_pct: float
    voltage_dip_compliant: bool
    acceleration_time_s: float
    safe_stall_time_s: float
    acceleration_compliant: bool
    load_inertia_kg_m2: float
    motor_torque_nm: float
    load_torque_nm: float
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Starting method multipliers (per skill Section 7.3 Table)
STARTING_METHOD_MULTIPLIERS = {
    "DOL": (6.0, 8.0),       # Direct-On-Line: 6-8× FLA
    "star-delta": (2.0, 3.0),  # Star-Delta: 2-3× FLA
    "autotransformer": (2.0, 4.0),  # Autotransformer: 2-4× FLA
    "soft-starter": (2.0, 4.0),  # Soft Starter: 2-4× FLA
    "VFD": (1.0, 1.5),       # VFD: 1-1.5× FLA
}

# Voltage dip limits per skill Section 7.3 (IEEE 141, ITIC, NEMA MG-1)
VOLTAGE_DIP_LIMITS = {
    "lighting": 5.0,         # IEEE 141
    "computers": 10.0,       # ITIC Curve
    "motors_running": 15.0,  # NEMA MG-1
    "motors_starting": 20.0,  # IEEE 399 (less stringent during starting)
    "process_control": 10.0,  # ISA
}


def simulate_motor_starting(
    motor_hp: float = 500.0,
    motor_voltage_v: float = 4160.0,
    pf: float = 0.9,
    efficiency: float = 0.93,
    starting_method: str = "DOL",
    source_mva: float = 50.0,  # Source short-circuit MVA
    source_xr_ratio: float = 10.0,
    load_inertia_kg_m2: float = 50.0,
    motor_torque_nm: float = 1500.0,
    load_torque_nm: float = 800.0,
    safe_stall_time_s: float = 12.0,
    load_type: str = "motors_starting",
) -> MotorStartingResult:
    """
    Simulate motor starting per skill Section 7.3 and IEEE 399.

    Steps:
        1. Calculate motor FLA: FLA = P / (√3 × V × PF × η)
        2. Get starting current based on method
        3. Calculate voltage dip: VD = I_start × Z_source / V_nominal × 100
        4. Calculate acceleration time: t_acc = J × ω / (T_motor - T_load)
        5. Check against voltage dip and stall time limits
    """
    if starting_method not in STARTING_METHOD_MULTIPLIERS:
        raise ValueError(
            f"Unknown starting method: {starting_method}. "
            f"Supported: {list(STARTING_METHOD_MULTIPLIERS.keys())}"
        )

    assumptions = [
        f"Motor: {motor_hp} HP, {motor_voltage_v}V, PF={pf}, η={efficiency}",
        f"Starting method: {starting_method}",
        f"Source: {source_mva} MVA, X/R={source_xr_ratio}",
        f"Load inertia: {load_inertia_kg_m2} kg·m²",
        f"Motor torque: {motor_torque_nm} N·m, Load torque: {load_torque_nm} N·m",
        f"Safe stall time: {safe_stall_time_s}s",
        f"Voltage dip limit ({load_type}): {VOLTAGE_DIP_LIMITS[load_type]}%",
    ]

    warnings: list[str] = []

    # Step 1: Motor FLA
    power_w = motor_hp * 746.0
    fla = power_w / (math.sqrt(3) * motor_voltage_v * pf * efficiency)

    # Step 2: Starting current
    mult_min, mult_max = STARTING_METHOD_MULTIPLIERS[starting_method]
    starting_multiple = (mult_min + mult_max) / 2.0  # Use midpoint
    starting_current = fla * starting_multiple

    # Step 3: Source impedance (from MVA and X/R)
    # Z_source = V² / S_sc (in per-unit, then convert to ohms)
    # |Z| = V² / (S_sc × √3) for 3-phase
    z_source_mag = (motor_voltage_v ** 2) / (source_mva * 1e6)
    # Account for X/R ratio: Z = R + jX, |Z| = sqrt(R² + X²), X/R = tan(θ)
    # R = |Z| / sqrt(1 + (X/R)²), X = |Z| × (X/R) / sqrt(1 + (X/R)²)
    # For voltage dip, we need |Z| (magnitude)
    z_source = z_source_mag

    # Voltage dip during starting (simplified)
    # VD = I_start × Z_source / V_nominal × 100%
    # More accurate: VD = I_start × Z_source / (V_nominal + I_start × Z_source) × 100
    v_drop = starting_current * z_source
    voltage_dip_pct = (v_drop / motor_voltage_v) * 100.0

    # Step 4: Acceleration time
    # t_acc = J × ω / (T_motor - T_load)
    # ω = 2π × n / 60 where n = synchronous speed (assume 1800 RPM for 4-pole 60Hz)
    n_sync = 1800.0  # RPM (4-pole, 60 Hz)
    omega = 2.0 * math.pi * n_sync / 60.0
    net_torque = motor_torque_nm - load_torque_nm
    if net_torque <= 0:
        acceleration_time = float("inf")
        warnings.append(
            f"⚠️ Motor torque ({motor_torque_nm} N·m) ≤ load torque ({load_torque_nm} N·m) "
            "— motor cannot start (insufficient accelerating torque)"
        )
    else:
        acceleration_time = (load_inertia_kg_m2 * omega) / net_torque

    # Step 5: Compliance check
    vd_limit = VOLTAGE_DIP_LIMITS[load_type]
    voltage_dip_compliant = voltage_dip_pct <= vd_limit
    acceleration_compliant = acceleration_time < safe_stall_time_s

    if not voltage_dip_compliant:
        warnings.append(
            f"⚠️ Voltage dip {voltage_dip_pct:.2f}% exceeds {load_type} limit {vd_limit}% "
            f"— consider reduced-voltage starting (soft starter, VFD, or star-delta)"
        )
    if not acceleration_compliant and math.isfinite(acceleration_time):
        warnings.append(
            f"⚠️ Acceleration time {acceleration_time:.2f}s exceeds safe stall time "
            f"{safe_stall_time_s}s — motor may overheat during start"
        )

    return MotorStartingResult(
        motor_hp=motor_hp,
        motor_voltage_v=motor_voltage_v,
        motor_fla_a=fla,
        starting_method=starting_method,
        starting_current_a=starting_current,
        starting_multiple=starting_multiple,
        source_impedance_ohm=z_source,
        voltage_dip_pct=voltage_dip_pct,
        voltage_dip_limit_pct=vd_limit,
        voltage_dip_compliant=voltage_dip_compliant,
        acceleration_time_s=acceleration_time,
        safe_stall_time_s=safe_stall_time_s,
        acceleration_compliant=acceleration_compliant,
        load_inertia_kg_m2=load_inertia_kg_m2,
        motor_torque_nm=motor_torque_nm,
        load_torque_nm=load_torque_nm,
        assumptions=assumptions,
        warnings=warnings,
    )


# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION 9: CABLE PULLING (3D TENSION CALCULATIONS)
# ═══════════════════════════════════════════════════════════════════════════
#
# Per skill Section A7 (Cable & Conductor Analysis):
#   "Cable Pulling — 3D tension calculations"
#
# Tension calculations per NEC Chapter 9 + IEEE 835:
#   T_out = T_in × exp(μ × θ) + W × L × sin(α)  (for straight pulls)
#   Sidewall pressure = T / R (must be < manufacturer limit)


@dataclass
class CablePullingResult:
    """Result of cable pulling tension calculation."""

    cable_weight_lb_per_ft: float
    conduit_length_ft: float
    conduit_bends_deg: float  # Total degrees of bends
    bend_radius_ft: float
    friction_coefficient: float
    incoming_tension_lb: float
    outgoing_tension_lb: float
    sidewall_pressure_lb_per_ft: float
    sidewall_pressure_limit_lb_per_ft: float
    sidewall_compliant: bool
    tension_limit_lb: float
    tension_compliant: bool
    pull_speed_ft_per_min: float
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Typical cable pulling limits (per manufacturer specs, IEEE 835)
DEFAULT_TENSION_LIMIT_LB = 1000.0  # Typical for 500 kcmil copper
DEFAULT_SIDEWALL_LIMIT_LB_PER_FT = 500.0  # Typical for medium-voltage cables


def simulate_cable_pulling(
    cable_weight_lb_per_ft: float = 2.5,  # Typical 500 kcmil Cu
    conduit_length_ft: float = 500.0,
    conduit_bends_deg: float = 90.0,  # One 90° bend
    bend_radius_ft: float = 5.0,  # Standard bend radius
    friction_coefficient: float = 0.5,  # Typical for cable in PVC conduit
    incoming_tension_lb: float = 50.0,  # From reel
    tension_limit_lb: float = DEFAULT_TENSION_LIMIT_LB,
    sidewall_limit_lb_per_ft: float = DEFAULT_SIDEWALL_LIMIT_LB_PER_FT,
    pull_speed_ft_per_min: float = 25.0,  # Recommended max
    incline_angle_deg: float = 0.0,  # 0 = horizontal pull
) -> CablePullingResult:
    """
    Simulate cable pulling tension per skill Section A7 + IEEE 835.

    Steps:
        1. Calculate straight-section tension: T = T_in + W × L × (μ × cos α + sin α)
        2. Calculate bend tension: T_out = T_in × exp(μ × θ)
        3. Calculate sidewall pressure: P = T / R
        4. Check against manufacturer limits
    """
    assumptions = [
        f"Cable weight: {cable_weight_lb_per_ft} lb/ft",
        f"Conduit length: {conduit_length_ft} ft",
        f"Total bends: {conduit_bends_deg}°",
        f"Bend radius: {bend_radius_ft} ft",
        f"Friction coefficient: {friction_coefficient} (typical for PVC conduit)",
        f"Incoming tension (from reel): {incoming_tension_lb} lb",
        f"Tension limit: {tension_limit_lb} lb",
        f"Sidewall pressure limit: {sidewall_limit_lb_per_ft} lb/ft",
        f"Pull speed: {pull_speed_ft_per_min} ft/min (IEEE 835 recommended max)",
    ]

    warnings: list[str] = []

    # Step 1: Straight-section tension (with friction + incline)
    # T_straight = T_in + W × L × (μ × cos α + sin α)
    alpha = math.radians(incline_angle_deg)
    weight_component = friction_coefficient * math.cos(alpha) + math.sin(alpha)
    straight_tension = incoming_tension_lb + cable_weight_lb_per_ft * conduit_length_ft * weight_component

    # Step 2: Bend tension (Poisson's equation)
    # T_out = T_in × exp(μ × θ) where θ is in radians
    theta_rad = math.radians(conduit_bends_deg)
    if theta_rad > 0:
        # For simplicity, apply all bends as one effective bend at the end
        outgoing_tension = straight_tension * math.exp(friction_coefficient * theta_rad)
    else:
        outgoing_tension = straight_tension

    # Step 3: Sidewall pressure at bends
    # P = T / R (tension divided by bend radius)
    if conduit_bends_deg > 0 and bend_radius_ft > 0:
        sidewall_pressure = outgoing_tension / bend_radius_ft
    else:
        sidewall_pressure = 0.0

    # Step 4: Compliance check
    tension_compliant = outgoing_tension <= tension_limit_lb
    sidewall_compliant = sidewall_pressure <= sidewall_limit_lb_per_ft

    if not tension_compliant:
        warnings.append(
            f"⚠️ Pulling tension {outgoing_tension:.0f} lb exceeds limit {tension_limit_lb} lb "
            "— reduce pull length, use puller with tension monitoring, or use lower-friction lubricant"
        )
    if not sidewall_compliant:
        warnings.append(
            f"⚠️ Sidewall pressure {sidewall_pressure:.0f} lb/ft exceeds limit "
            f"{sidewall_limit_lb_per_ft} lb/ft — increase bend radius or reduce pull tension"
        )
    if pull_speed_ft_per_min > 25.0:
        warnings.append(
            f"⚠️ Pull speed {pull_speed_ft_per_min} ft/min exceeds IEEE 835 recommended max (25 ft/min)"
        )

    return CablePullingResult(
        cable_weight_lb_per_ft=cable_weight_lb_per_ft,
        conduit_length_ft=conduit_length_ft,
        conduit_bends_deg=conduit_bends_deg,
        bend_radius_ft=bend_radius_ft,
        friction_coefficient=friction_coefficient,
        incoming_tension_lb=incoming_tension_lb,
        outgoing_tension_lb=outgoing_tension,
        sidewall_pressure_lb_per_ft=sidewall_pressure,
        sidewall_pressure_limit_lb_per_ft=sidewall_limit_lb_per_ft,
        sidewall_compliant=sidewall_compliant,
        tension_limit_lb=tension_limit_lb,
        tension_compliant=tension_compliant,
        pull_speed_ft_per_min=pull_speed_ft_per_min,
        assumptions=assumptions,
        warnings=warnings,
    )


# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION 10: GROUND GRID DESIGN (IEEE 80-2013)
# ═══════════════════════════════════════════════════════════════════════════
#
# Per skill Section A8 (Grounding & Earthing):
#   "Ground Grid Design — IEEE 80 compliance"
#   "Touch/step voltage per IEC"
#
# IEEE 80-2013 equations:
#   - Touch voltage limit: V_touch = (R_B + R_f) × I_b
#     where R_B = body resistance (1000Ω), R_f = foot resistance
#   - Step voltage limit: V_step = (R_B + 2×R_f) × I_b
#   - Foot resistance: R_f = ρ_s × C / 4×b (where b = foot radius, C = correction)


@dataclass
class GroundGridResult:
    """Result of ground grid design per IEEE 80-2013."""

    grid_area_m2: float
    soil_resistivity_ohm_m: float
    fault_current_a: float
    fault_duration_s: float
    grid_conductor_m: float  # Total conductor length
    grid_spacing_m: float
    body_resistance_ohm: float
    foot_resistance_ohm: float
    touch_voltage_limit_v: float
    step_voltage_limit_v: float
    grid_resistance_ohm: float
    ground_potential_rise_v: float
    touch_voltage_compliant: bool
    step_voltage_compliant: bool
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# IEEE 80-2013 constants
BODY_RESISTANCE_OHM = 1000.0  # Adult body resistance (hand-to-foot)
FOOT_RADIUS_M = 0.08  # 8cm equivalent radius for human foot
CURRENT_DURATIONS = {
    "fibrillation_threshold": 0.116,  # 116ms for 50kg body weight (IEC 60479-1)
    "safe_touch": 1.0,  # 1s typical fault clearing
}


def simulate_ground_grid(
    grid_area_m2: float = 1000.0,  # 31.6m × 31.6m grid
    soil_resistivity_ohm_m: float = 100.0,  # Typical sandy loam
    fault_current_a: float = 5000.0,  # 5kA ground fault
    fault_duration_s: float = 0.5,  # 500ms clearing time
    grid_conductor_m: float = 200.0,  # Total grid conductor length
    grid_spacing_m: float = 5.0,  # 5m between conductors
    body_weight_kg: float = 50.0,  # 50kg (conservative per IEEE 80)
) -> GroundGridResult:
    """
    Simulate ground grid design per IEEE 80-2013.

    Steps:
        1. Calculate foot resistance: R_f = ρ_s × C / (4 × b)
        2. Calculate touch voltage limit: V_touch = (R_B + R_f) × I_b
        3. Calculate step voltage limit: V_step = (R_B + 2×R_f) × I_b
        4. Calculate grid resistance: R_g = ρ × [1/L + 1/√(20×A)]
        5. Calculate GPR: V_gpr = I_g × R_g
        6. Verify GPR < touch/step limits
    """
    assumptions = [
        f"Grid area: {grid_area_m2} m² ({math.sqrt(grid_area_m2):.1f}m × {math.sqrt(grid_area_m2):.1f}m)",
        f"Soil resistivity: {soil_resistivity_ohm_m} Ω·m (typical sandy loam)",
        f"Fault current: {fault_current_a} A",
        f"Fault duration: {fault_duration_s} s",
        f"Total conductor length: {grid_conductor_m} m",
        f"Grid spacing: {grid_spacing_m} m",
        f"Body weight: {body_weight_kg} kg (IEEE 80 conservative)",
        f"Body resistance: {BODY_RESISTANCE_OHM} Ω (IEEE 80 standard)",
        f"Foot radius: {FOOT_RADIUS_M} m",
    ]

    warnings: list[str] = []

    # Step 1: Foot resistance (IEEE 80 §12.5)
    # R_f = ρ_s × C / (4 × b) where C ≈ 1 for surface layer correction
    # Simplified: R_f = ρ_s / (4 × b) when C=1 (no surface layer)
    C = 1.0  # No crushed rock surface layer
    foot_resistance = (soil_resistivity_ohm_m * C) / (4.0 * FOOT_RADIUS_M)

    # Step 2: Fibrillation current (IEEE 80 §6, Dalziel's equation)
    # I_b = 0.116 / sqrt(t) for 50kg body weight
    # For 70kg: I_b = 0.157 / sqrt(t)
    if body_weight_kg <= 50.0:
        i_fib = 0.116 / math.sqrt(fault_duration_s)
    else:
        i_fib = 0.157 / math.sqrt(fault_duration_s)

    # Step 3: Touch and step voltage limits (IEEE 80 §22)
    # V_touch = (R_B + R_f) × I_b
    # V_step = (R_B + 2×R_f) × I_b
    v_touch_limit = (BODY_RESISTANCE_OHM + foot_resistance) * i_fib
    v_step_limit = (BODY_RESISTANCE_OHM + 2.0 * foot_resistance) * i_fib

    # Step 4: Grid resistance (IEEE 80 §14)
    # R_g = ρ × [1/L + 1/√(20×A)]
    # Simplified formula for rectangular grid
    grid_resistance = soil_resistivity_ohm_m * (
        1.0 / grid_conductor_m + 1.0 / math.sqrt(20.0 * grid_area_m2)
    )

    # Step 5: Ground Potential Rise
    gpr = fault_current_a * grid_resistance

    # Step 6: Compliance check
    # For safety: GPR must be less than touch voltage limit
    # (Assuming worst case: person touching grounded equipment at edge of grid)
    touch_compliant = gpr <= v_touch_limit
    step_compliant = gpr <= v_step_limit  # Simplified (actual step V < GPR)

    if not touch_compliant:
        warnings.append(
            f"⚠️ GPR {gpr:.0f}V exceeds touch voltage limit {v_touch_limit:.0f}V "
            "— add more grid conductor, reduce spacing, or add crushed rock surface layer"
        )
    if not step_compliant:
        warnings.append(
            f"⚠️ GPR {gpr:.0f}V exceeds step voltage limit {v_step_limit:.0f}V "
            "— enlarge grid area or add ground rods"
        )

    return GroundGridResult(
        grid_area_m2=grid_area_m2,
        soil_resistivity_ohm_m=soil_resistivity_ohm_m,
        fault_current_a=fault_current_a,
        fault_duration_s=fault_duration_s,
        grid_conductor_m=grid_conductor_m,
        grid_spacing_m=grid_spacing_m,
        body_resistance_ohm=BODY_RESISTANCE_OHM,
        foot_resistance_ohm=foot_resistance,
        touch_voltage_limit_v=v_touch_limit,
        step_voltage_limit_v=v_step_limit,
        grid_resistance_ohm=grid_resistance,
        ground_potential_rise_v=gpr,
        touch_voltage_compliant=touch_compliant,
        step_voltage_compliant=step_compliant,
        assumptions=assumptions,
        warnings=warnings,
    )


# ═══════════════════════════════════════════════════════════════════════════
# MASTER RUNNER
# ═══════════════════════════════════════════════════════════════════════════


def run_extended_simulations() -> dict:
    """Run all 3 extended simulations and return results as dict."""
    return {
        "motor_starting": simulate_motor_starting().__dict__,
        "cable_pulling": simulate_cable_pulling().__dict__,
        "ground_grid": simulate_ground_grid().__dict__,
    }


if __name__ == "__main__":
    import json

    results = run_extended_simulations()

    print("═" * 70)
    print("ETAP Expert Skill — Extended Simulations (V131 Phase 3)")
    print("═" * 70)
    print()

    for name, result in results.items():
        print(f"━━━ {name.upper().replace('_', ' ')} ━━━")
        clean = {k: v for k, v in result.items() if not isinstance(v, (list, dict))}
        print(json.dumps(clean, indent=2, default=str))
        if result.get("warnings"):
            print(f"  ⚠️  Warnings: {len(result['warnings'])}")
            for w in result["warnings"]:
                print(f"    - {w}")
        print()
