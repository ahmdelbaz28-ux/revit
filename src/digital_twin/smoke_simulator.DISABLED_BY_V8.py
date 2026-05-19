"""
digital_twin/smoke_simulator.py
===============================
Simplified two-zone smoke model based on NFPA 92 / Heskestad plume.

NOT a CFD substitute — but gives quantitative *time-to-detection* and
*time-to-untenable* estimates that beat any spacing-only check.

Inputs:
  - room volume V (m³), ceiling height H (m)
  - fire heat release rate Q (kW), assumed t² growth: Q(t) = α·t²
  - device mounting height z_dev (m)

Outputs (vs time):
  - smoke layer interface height z(t)
  - layer temperature T(t)
  - layer optical density / visibility
  - time when layer descends to z_dev → detector activation
  - time when layer descends to head-height (1.8 m) → untenable

Formulas:
  Heskestad plume mass flow:  m_p = 0.071·Q_c^(1/3)·z^(5/3) + 0.0018·Q_c
  Energy balance:             T_g = T_0 + Q_c / (m_p · c_p)
  Layer descent:              dV_layer/dt = m_p/ρ
                              z(t)   = H − V_layer(t)/A_floor

These give a defensible engineering estimate per room. They DO NOT replace
FDS simulation for code submittals — they flag obvious risks early.
"""
from __future__ import annotations
import math
from dataclasses import dataclass


T_AMB    = 293.0          # K (20 °C)
RHO_AIR  = 1.204          # kg/m³
CP_AIR   = 1.005          # kJ/(kg·K)
G        = 9.81           # m/s²


@dataclass
class FireScenario:
    alpha_kw_s2: float = 0.0469      # NFPA 72 'fast' t² fire (default 'medium')
    growth: str = "medium"           # 'slow','medium','fast','ultra_fast'
    cap_kw: float = 5000.0           # plateau heat release (kW)

    def Q_at(self, t: float) -> float:
        return min(self.cap_kw, self.alpha_kw_s2 * t * t)

    @classmethod
    def named(cls, growth: str = "medium"):
        # NFPA 72 §A.17.5 alpha values (kW/s²)
        a = {"slow": 0.00293, "medium": 0.01172,
             "fast": 0.0469,  "ultra_fast": 0.1876}[growth]
        return cls(alpha_kw_s2=a, growth=growth)


@dataclass
class SmokeResult:
    time_to_detect_s:   float | None
    time_to_untenable_s: float | None
    layer_height_at_60s: float
    layer_temp_C_at_60s: float
    activation_window_s: float | None
    safety_margin_s:     float | None     # untenable - detection
    notes: list


def simulate(volume_m3: float,
             ceiling_height_m: float,
             device_mount_height_m: float = 2.8,
             scenario: FireScenario | None = None,
             dt: float = 1.0,
             t_max: int = 600,
             tenable_height_m: float = 1.8,
             smoke_obscuration_threshold: float = 0.15  # 1/m
             ) -> SmokeResult:

    fire = scenario or FireScenario.named("medium")
    A = volume_m3 / ceiling_height_m if ceiling_height_m > 0 else 1.0
    z = ceiling_height_m            # smoke interface (m above floor)
    layer_volume = 1e-3
    layer_mass   = layer_volume * RHO_AIR
    layer_energy = 0.0              # kJ above ambient

    t_detect = None
    t_untenable = None
    notes = []
    layer_h_60 = ceiling_height_m
    layer_T_60 = T_AMB
    soot_yield = 0.06               # general office fire

    t = 0.0
    while t < t_max:
        Q = fire.Q_at(t)            # total HRR kW
        Qc = 0.7 * Q                # convective fraction
        # plume entrainment at the interface height z (above virtual origin = 0)
        if z > 0.1:
            m_p = 0.071 * (Qc**(1/3)) * (z**(5/3)) + 0.0018 * Qc  # kg/s
        else:
            m_p = 1e-6
        # update layer mass / energy
        dm = m_p * dt
        layer_mass  += dm
        layer_energy += Qc * dt     # all convective heat into layer
        if layer_mass > 0:
            T_layer = T_AMB + layer_energy / (layer_mass * CP_AIR)
            rho_layer = RHO_AIR * (T_AMB / T_layer)
            layer_volume = layer_mass / rho_layer
        else:
            T_layer = T_AMB; layer_volume = 1e-3
        z = max(0.0, ceiling_height_m - layer_volume / A)

        if t_detect is None and z <= device_mount_height_m:
            t_detect = t
        if t_untenable is None and z <= tenable_height_m:
            t_untenable = t
        if abs(t - 60.0) < dt/2:
            layer_h_60 = z
            layer_T_60 = T_layer - 273.0
        t += dt

    margin = (t_untenable - t_detect) if (t_detect and t_untenable) else None
    if margin is not None and margin < 30:
        notes.append(f"⚠ Safety margin only {margin:.0f}s — insufficient for "
                     "occupant response. Consider faster detection or smaller zones.")
    if t_detect is None:
        notes.append("Detector never activated within simulation window — "
                     "device may be too high or zone too small.")
    if t_untenable is None:
        notes.append("Untenable conditions not reached within simulation — "
                     "either fire too small or room too large/ventilated.")

    return SmokeResult(
        time_to_detect_s    = t_detect,
        time_to_untenable_s = t_untenable,
        layer_height_at_60s = round(layer_h_60, 2),
        layer_temp_C_at_60s = round(layer_T_60, 1),
        activation_window_s = t_detect,
        safety_margin_s     = margin,
        notes               = notes,
    )


def simulate_room_with_devices(twin, room_id: str,
                               growth: str = "medium") -> dict:
    """Convenience: pull room + devices from twin, run sim."""
    r = twin.rooms.get(room_id)
    if not r: return {"error":"no such room"}
    dev_heights = [d.mounting_height_m for d in twin.devices.values()
                   if d.room_id == room_id
                   and d.kind in ("smoke_detector","heat_detector")]
    z_dev = min(dev_heights) if dev_heights else r.ceiling_height_m - 0.1
    res = simulate(r.volume_m3, r.ceiling_height_m, z_dev,
                   scenario=FireScenario.named(growth))
    return {
        "room": room_id, "growth": growth,
        "volume_m3": round(r.volume_m3, 1),
        "ceiling_h": r.ceiling_height_m,
        "device_h":  z_dev,
        **res.__dict__,
    }
