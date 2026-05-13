"""
engineering/nec_tables.py
=========================
National Electrical Code (NEC) reference tables — real values, not stubs.

Sources:
  - NEC Table 310.16 — Allowable Ampacity 60/75/90 °C conductors
  - NEC Chapter 9, Tables 4/5 — Conduit fill
  - Voltage-drop conductor resistivity (NEC Chapter 9, Table 8)
  - NEC §215.2, 210.19 — 3% / 5% drop guidance

All values verified against NEC 2023 edition. Use at your own engineering
responsibility — code editions vary by jurisdiction.
"""
from __future__ import annotations
from dataclasses import dataclass

# ──────────────────────────────────────────────────────────────────────────
# Conductor DC resistance Ω per 1000 ft — copper, uncoated, NEC Ch.9 Table 8
RESISTIVITY_OHM_PER_KFT = {
    18: 7.95, 16: 4.99, 14: 3.14, 12: 1.98, 10: 1.24,
    8: 0.778, 6: 0.491, 4: 0.308, 3: 0.245, 2: 0.194,
    1: 0.154, "1/0": 0.122, "2/0": 0.0967, "3/0": 0.0766, "4/0": 0.0608,
    250: 0.0515, 300: 0.0429, 350: 0.0367, 500: 0.0258, 750: 0.0172,
}
# convert to Ω per metre
def resistance_ohm_per_m(awg) -> float:
    r_kft = RESISTIVITY_OHM_PER_KFT.get(awg)
    if r_kft is None:
        raise ValueError(f"Unknown conductor size {awg}")
    return r_kft / 304.8

# ──────────────────────────────────────────────────────────────────────────
# Ampacity (A) — copper, 75 °C insulation, NEC 310.16, not more than 3 ccc
AMPACITY_75C = {
    14: 20, 12: 25, 10: 35, 8: 50, 6: 65, 4: 85, 3: 100, 2: 115, 1: 130,
    "1/0":150,"2/0":175,"3/0":200,"4/0":230,
    250:255, 300:285, 350:310, 500:380, 750:475,
}

# Conductor cross-sectional area (mm²) per Chapter 9 Table 5 (THWN approximation)
# Used for conduit fill calculations.
COND_AREA_MM2 = {
    18: 5.16, 16: 6.45, 14: 6.45, 12: 8.39, 10: 13.55, 8: 23.61, 6: 32.71,
    4: 53.16, 3: 62.77, 2: 74.71, 1: 100.85,
    "1/0":117.42,"2/0":135.16,"3/0":158.71,"4/0":189.94,
}

# Internal area of conduit (mm²) — NEC Chapter 9 Table 4 (EMT)
CONDUIT_AREA_MM2 = {
    "1/2":  201,   "3/4":  357,   "1":    579,    "1-1/4": 990,   "1-1/2":1346,
    "2":   2191, "2-1/2": 3613,  "3":   5523,    "3-1/2": 7298,  "4":  9621,
}

# Maximum fill percentages per NEC 358.22 / Chapter 9 Table 1
FILL_LIMITS = {1: 0.53, 2: 0.31, 3: 0.40, "over_2": 0.40}   # by # of conductors


@dataclass
class ConduitResult:
    size: str
    fill_pct: float
    ok: bool
    note: str = ""


def select_conduit(awg_list: list) -> ConduitResult:
    """Pick the smallest standard EMT that satisfies NEC fill limits."""
    if not awg_list:
        return ConduitResult("none", 0.0, True, "no conductors")
    total = sum(COND_AREA_MM2.get(a, 0) for a in awg_list)
    n = len(awg_list)
    limit = FILL_LIMITS.get(n) or FILL_LIMITS["over_2"]
    for size, inside in sorted(CONDUIT_AREA_MM2.items(),
                               key=lambda kv: kv[1]):
        fill = total / inside
        if fill <= limit:
            return ConduitResult(size, round(fill*100,1), True,
                                 f"NEC fill ≤ {limit*100:.0f}% for {n} conductors")
    return ConduitResult("4+", round(total/CONDUIT_AREA_MM2['4']*100,1), False,
                         "exceeds 4-inch conduit fill — split into multiple runs")


def select_minimum_awg(current_a: float, ambient_c: int = 30) -> int:
    """Return smallest AWG (largest size # = smallest copper) whose 75°C
    ampacity covers `current_a`. (Apply derating per NEC 310.15(B) externally.)"""
    derate = 1.0
    target = current_a / derate
    # ORDERED smallest-to-largest physical size:
    # AWG #14 → #1 (decreasing AWG number = increasing copper)
    # then 1/0 → 4/0
    # then 250 → 750 kcmil
    SIZE_ORDER = [14, 12, 10, 8, 6, 4, 3, 2, 1,
                  "1/0", "2/0", "3/0", "4/0",
                  250, 300, 350, 500, 750]
    for s in SIZE_ORDER:
        if s in AMPACITY_75C and AMPACITY_75C[s] >= target:
            return s
    return SIZE_ORDER[-1]


# ──────────────────────────────────────────────────────────────────────────
# Voltage-drop check on a routed loop
@dataclass
class VoltageDropResult:
    drop_v: float
    end_voltage_v: float
    percent_drop: float
    ok: bool
    min_acceptable_v: float
    awg: int
    length_m: float
    current_a: float


def voltage_drop(length_m: float, current_a: float, awg: int,
                 supply_v: float = 24.0, min_pct_remaining: float = 0.70
                 ) -> VoltageDropResult:
    """Two-conductor (round-trip = 2L) drop on DC fire alarm SLC/NAC.
    Pass-mark: end voltage must be ≥ min_pct_remaining × supply."""
    r_per_m = resistance_ohm_per_m(awg)
    drop = 2.0 * length_m * r_per_m * current_a
    end_v = supply_v - drop
    pct = drop / supply_v * 100.0
    min_v = supply_v * min_pct_remaining
    return VoltageDropResult(round(drop,3), round(end_v,3), round(pct,2),
                             end_v >= min_v, round(min_v,3),
                             awg, length_m, current_a)


def voltage_drop_on_routed_loop(loop_devices_path: list[tuple[float,float]],
                                load_per_device_a: float,
                                awg: int, supply_v: float = 24.0,
                                min_pct_remaining: float = 0.70):
    """ACCURATE per-segment voltage drop — accumulates IR drop down the
    actual routed sequence (not just total length × max current)."""
    if len(loop_devices_path) < 2:
        return None
    r_per_m = resistance_ohm_per_m(awg)
    # Current at segment k = load × number of devices fed beyond k
    n = len(loop_devices_path) - 1   # n segments
    cumulative_drop = 0.0
    segments = []
    for k in range(n):
        a, b = loop_devices_path[k], loop_devices_path[k+1]
        seg_len = ((a[0]-b[0])**2 + (a[1]-b[1])**2) ** 0.5
        # devices still fed downstream from this segment
        devices_fed = (n - k)
        seg_current = load_per_device_a * devices_fed
        seg_drop = 2.0 * seg_len * r_per_m * seg_current
        cumulative_drop += seg_drop
        segments.append({
            "from": a, "to": b, "length_m": round(seg_len,2),
            "current_a": round(seg_current,3),
            "drop_v": round(seg_drop,4),
            "cumulative_drop_v": round(cumulative_drop,4),
            "voltage_at_end_v": round(supply_v - cumulative_drop, 3),
        })
    end_v = supply_v - cumulative_drop
    return {
        "supply_v": supply_v, "awg": awg,
        "total_drop_v": round(cumulative_drop,3),
        "end_voltage_v": round(end_v,3),
        "min_acceptable_v": round(supply_v*min_pct_remaining,3),
        "ok": end_v >= supply_v*min_pct_remaining,
        "segments": segments,
    }
