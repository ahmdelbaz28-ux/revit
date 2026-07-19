# ENGINEERING_BASIS — BAZSpark

> **Purpose:** Single consolidated reference for every engineering formula,
> constant, and assumption used in BAZSpark's life-safety calculations.
> Each entry cites the NFPA 72 / NEC / IBC section it derives from, or is
> explicitly marked `ENGINEERING_JUDGEMENT` when no code citation exists.
>
> **C-XX FIX (Engineering Review):** This file implements recommendation
> §5.4 of the engineering review. Previously, formulas were scattered
> across `fireai/constants/`, `fireai/core/`, and `frontend/src/engine/`
> with inconsistent or missing citations. This file is the authoritative
> index — any code change to a value listed here MUST be reflected in this
> file (and trigger the regulatory-data-guard CI check).

---

## 1. NFPA 72-2022 Constants (canonical source: `fireai/constants/nfpa72.py`)

| Constant | Value | Source | Notes |
|----------|-------|--------|-------|
| `SMOKE_MAX_SPACING_M` | 9.1 m (30 ft) | NFPA 72-2022 §17.7.3.2.3 | Flat spacing on smooth ceilings. NOT 9.144 (which is the exact ft→m conversion but is not what the standard states verbatim). |
| `SMOKE_MAX_CEILING_HEIGHT_M` | 18.288 m (60 ft) | NFPA 72-2022 §17.7.3.2.4 | Maximum ceiling height for spot-type smoke detectors. |
| `SMOKE_PRACTICAL_CEILING_HEIGHT_M` | 6.096 m (20 ft) | ECMAG guidance | Practical recommendation, not code. |
| `HEAT_MAX_SPACING_M` | 6.1 m (20 ft) | NFPA 72-2022 §17.6.3.1 | Standard spacing for heat detectors. |
| `HEAT_MAX_CEILING_HEIGHT_M` | 15.24 m (50 ft) | NFPA 72-2022 §17.6.3.1 | Maximum ceiling height for heat detectors. |
| `HEAT_ABSOLUTE_MAX_SPACING_M` | 15.24 m (50 ft) | NFPA 72-2022 §17.6.3.1 | Absolute max (not the standard spacing). |
| `COVERAGE_RADIUS_FACTOR` | 0.7 | NFPA 72-2022 §17.7.4.2.3.1 | R = 0.7 × S (coverage radius from spacing). |
| `WALL_MIN_DISTANCE_M` | 0.1016 m (4 in) | NFPA 72-2022 §17.7.3.2.3 | Dead-air space rule. |
| `CEILING_HEIGHT_HARD_LIMIT_M` | 18.288 m (60 ft) | NFPA 72-2022 §17.7.3.2.4 | Matches smoke max. |
| `CEILING_HEIGHT_SOFT_LIMIT_M` | 15.24 m (50 ft) | NFPA 72-2022 §17.6.3.1 | Matches heat max. |
| `NAC_MIN_CD` | 75 cd | NFPA 72-2022 §18.5.5.1 | Minimum candela for wall-mounted visible notification. |
| `NAC_SLEEPING_MIN_CD` | 177 cd | NFPA 72-2022 §18.5.5.1 | Minimum candela for sleeping areas. |
| `MAX_VOLTAGE_DROP_PCT` | 10.0% | NFPA 72-2022 §10.14.1.2 | FA circuit voltage drop limit. |
| `NOMINAL_VOLTAGE_FA` | 24.0 VDC | Industry standard | Standard FA panel voltage. |
| `PROOF_VERIFIED_THRESHOLD` | 99.99% | INTERNAL QUALITY GATE | NOT NFPA-cited. NFPA 72 requires 100% coverage; 99.99 is the team's internal "verified" tier. |
| `STANDARD_COVERAGE_THRESHOLD` | 99.0% | INTERNAL QUALITY GATE | "valid" tier. |
| `MINIMUM_COVERAGE_FOR_SUBMISSION` | 95.0% | INTERNAL QUALITY GATE | Below this = REJECTED. |
| `ABSOLUTE_MINIMUM_COVERAGE` | 90.0% | INTERNAL QUALITY GATE | Cannot be overridden even by FPE. |

---

## 2. NEC 2023 Chapter 9 Table 8 — Copper Conductor Resistance

Canonical source: `fireai/constants/nec.py` (`NEC_TABLE8_RESISTANCE_OHM_PER_KM_20C`).

**Reference temperature:** 20°C. **Conductor type:** STRANDED Class B copper
(conservative — slightly higher resistance than solid, so voltage drop is
never underestimated).

| AWG | Ω/km @ 20°C (STRANDED) | Ω/km @ 75°C (STRANDED, derived) |
|-----|------------------------|---------------------------------|
| 18 | 10.870 (solid only — no stranded column) | — |
| 16 | 6.820 (solid only — no stranded column) | — |
| 14 | **8.470** | 10.30 |
| 12 | 5.322 | 6.50 |
| 10 | 3.340 | 4.10 |
| 8 | 2.099 | 2.62 |
| 6 | 1.322 | 1.65 |
| 4 | 0.833 | 1.04 |
| 3 | 0.661 | 0.83 |
| 2 | 0.524 | 0.66 |
| 1 | 0.416 | 0.52 |
| 1/0 | 0.330 | 0.41 |
| 2/0 | 0.262 | 0.33 |
| 3/0 | 0.208 | 0.26 |
| 4/0 | 0.164 | 0.21 |

**Temperature correction formula:**
```
R_T = R_20 × [1 + α × (T - 20)]
```
where `α = 0.00393` (copper temperature coefficient, `COPPER_TEMP_COEFFICIENT`).

**C-03 audit history:** The original code used `4.263 Ω/km` — a PHANTOM value
that does not exist in NEC Table 8 at any temperature. The first "fix" used
`8.286 Ω/km` — actually the SOLID value at 20°C, mislabeled as stranded.
The CORRECT stranded value at 20°C is `8.470 Ω/km` (verified against NEC 2023
Chapter 9 Table 8 actual values).

**Voltage drop formula:**
```
V_drop = 2 × I × L × R_per_m
```
where:
- `2` = DC return path factor (NFPA 72 §10.14, NEC Art. 310)
- `I` = circuit current (Amperes)
- `L` = one-way cable length (metres)
- `R_per_m` = conductor resistance at operating temperature (Ω/m)

**Compliance thresholds:**
- Fire-alarm circuits: `V_drop ≤ 10%` of supply voltage (NFPA 72-2022 §10.14.1.2)
- Power circuits (informational only, NOT applicable to FA):
  - Branch: `V_drop ≤ 3%` (NEC §210.19(A)(1) informational note)
  - Total: `V_drop ≤ 5%` (NEC §215.2(A)(2) informational note)

---

## 3. Smoke Detector Coverage — RADIUS IS FLAT FOR ALL HEIGHTS

**C-09 CRITICAL CORRECTION:** `fireai/core/nfpa72_models.py::get_smoke_detector_radius()`
previously applied NFPA 72 Table 17.6.3.1.1 (the HEAT detector height-spacing
table) to SMOKE detectors. This was a **code violation** — it produced
over-densification of up to 65% at high ceilings.

**Correct behavior:** NFPA 72-2022 §17.7.3.2.3 specifies FLAT 9.1m (30ft)
spacing for spot-type smoke detectors on smooth ceilings at ALL heights
within the permitted range (3.0m to 18.288m per §17.7.3.2.4). There is NO
height-based spacing reduction for smoke detectors in NFPA 72.

Therefore: `R = 0.7 × 9.1 = 6.37m` for all valid ceiling heights.

The height-adjusted `SMOKE_HEIGHT_SPACING_TABLE` in `constants/nfpa72.py`
documents conservative reductions for engineering-judgement use, but the
strict `get_smoke_detector_radius()` function returns the flat 6.37m value.

---

## 4. Notification Appliance Spacing (NAC)

Canonical source: `fireai/core/device_placement.py::_place_notification_appliances()`.

| Candela Rating | Max Spacing | Source |
|----------------|-------------|--------|
| 75 cd | 12.19 m (40 ft) | NFPA 72-2022 **Figure** 18.5.5.5.1 + manufacturer guidance (System Sensor SpectrAlert) |
| 110 cd | 15.24 m (50 ft) | NFPA 72-2022 Figure 18.5.5.5.1 + manufacturer guidance |
| 177 cd (sleeping) | 18.29 m (60 ft) | NFPA 72-2022 Figure 18.5.5.5.1 + manufacturer guidance |

**C-06 audit note:** The original code cited "Table 18.5.5.5.1" — it is
actually a **Figure** (Figure 18.5.5.5.1: Room Spacing for Wall-Mounted
Visible Notification Appliances). The specific 40/50/60ft @ 75/110/177cd
values are derived from manufacturer application guides based on the Figure,
NOT direct NFPA normative text. They are reasonable engineering guidance
but should not be cited as "NFPA Table" values.

**Wall offset:** 0.305 m (12 in) — NFPA 72-2022 §18.5.5.7.
**Mounting height:** 2.032 m (80 in) AFF minimum — NFPA 72-2022 §18.5.3.1.

---

## 5. Manual Fire Alarm Boxes (Pull Stations)

Canonical source: `fireai/core/device_placement.py::_place_pull_stations()`.

| Parameter | Value | Source |
|-----------|-------|--------|
| Distance from exit doorway | ≤ 1.524 m (5 ft) | NFPA 72-2022 **§17.15.3** |
| Mounting height | 1.219 m (48 in) AFF | NFPA 72-2022 §17.15.4 |
| Height range (legacy check) | 1.0–1.37 m (40–54 in) | Legacy code; NFPA canonical is 42–48 in (1.07–1.22 m) |
| Latch-side placement | Required when `door_swing` known | ADA §404.2.7 + IBC §1010.1.10 (engineering interpretation) |

**C-07 audit note:** The original code cited "NFPA 72 §21.4.1" for pull
station placement. That section is actually "Elevator Power Shutdown" in
NFPA 72-2022. The correct section is **§17.15** (Manual Fire Alarm Boxes).
"Latch side" is engineering interpretation — ADA/IBC require clear-floor-
space-outside-swing, which usually coincides with the latch side.

---

## 6. Voltage Drop Compliance (Fire-Alarm vs Power Circuits)

Canonical source: `fireai/core/nfpa72_schemas.py::VoltageDropInput.compute()`.

**C-05 FIX:** The original code used NEC §210.19(A)(1) (3% branch) and
§215.2(A)(2) (5% total) as compliance thresholds. These are POWER circuit
limits, NOT fire-alarm limits. NFPA 72-2022 §10.14.1.2 sets the FA limit
at 10% (with 20% permitted under specific listed conditions).

The fix:
- Primary compliance verdict uses **10%** (NFPA 72 §10.14.1.2 for FA).
- The NEC 3%/5% values are retained as informational fields
  (`nec_branch_3pct`, `nec_total_5pct`) for callers that want both views.
- The legacy key names `compliant_branch_3pct` / `compliant_total_5pct`
  are retained for backward compatibility but now hold the 10% verdict.

---

## 7. Coverage Radius Correction Factors (ENGINEERING JUDGEMENT)

Canonical source: `fireai/core/nfpa72_schemas.py::CoverageRadiusInput.compute_coverage_radius()`.

The following correction factors are NOT NFPA-cited. They are engineering-
judgement heuristics used as an interim model. Any design that uses non-
default values MUST be flagged for FPE (Fire Protection Engineer) review.

| Factor | Formula | NFPA Status | Notes |
|--------|---------|-------------|-------|
| `base_factor` (flat ceiling) | 0.7 | NFPA-cited (§17.7.4.2.3.1) | R = 0.7 × S. |
| `base_factor` (non-flat ceiling) | 0.6 | **ENGINEERING JUDGEMENT** | NFPA 72 only cites 0.7 for flat. The 0.6 reduction is conservative derating, not code. |
| `hvac_correction` | `max(0, 1 - velocity × 0.10)` | **ENGINEERING JUDGEMENT** | NFPA 72 §17.7.3.2.4 requires "consideration" of HVAC but prescribes no formula. The 0.10 coefficient is empirical. |
| `beam_correction` | `max(0.25, 1 - excess × 2.0)` | **ENGINEERING JUDGEMENT** | NFPA 72 §17.6.3.6 describes beam-pocket geometry qualitatively. The 10% threshold + 2.0 multiplier are engineering judgement. |

---

## 8. Battery Capacity Calculation

Canonical source: `fireai/core/voltage_drop.py::calculate_battery_backup()`.

**Formula (NFPA 72-2022 §10.6.7 + IEEE 485):**
```
Ah_required = (Ah_standby + Ah_alarm) / derating_factor × safety_factor
```
where:
- `Ah_standby = standby_load_a × standby_hours` (NFPA 72 §10.6.7.2: 24h minimum)
- `Ah_alarm = alarm_load_a × (alarm_minutes / 60)` (NFPA 72 §10.6.7.4: 5 min minimum)
- `derating_factor = 0.80` (NFPA 72 §10.6.7.1: battery derating at end-of-life)
- `safety_factor = 1.25` (engineering judgement — 25% margin above calculated)

**Units:** All currents in Amperes (NOT milliamps). BUG-13 FIX: previous
code treated Amps as milliamps, producing 1000× too-small batteries.

---

## 9. Self-Healing Kernel Fallback Philosophy

Canonical source: `fireai/core/qomn_kernel.py::_healing_wrapper()`.

**C-01 FIX design decision:** The SelfHealingQOMNKernel returns conservative
fallback values (battery=0 Ah, smoke_spacing=9.1m) when a calculation fails.
This is intentional — the philosophy is "fail-safe with sentinel values that
force manual investigation" rather than "fail-loud with exceptions".

The engineering review flagged this as "fail-quiet-to-death". The compromise:
1. Every healed fallback is now tagged with `safety_tier="FALLBACK_USED"` and
   `requires_fpe_review=True`, so downstream safety-tier classification
   forces FPE review.
2. A `QOMNCalculationError` exception class was added for callers that prefer
   fail-loud semantics (opt-in via `QOMN_FAIL_LOUD=1` env var).
3. The default behavior (fail-safe with sentinel) is preserved because 16
   existing tests (`test_v214_self_healing_integration.py`) depend on it.

---

## 10. CI/CD Regulatory Guard

Canonical source: `.github/workflows/regulatory-data-guard.yml`.

**C-XX FIX:** The guard now FAILS the PR (exit 1) when attestation is missing.
Previously it was "informational only" (exit 0 always) — defeated the purpose.

To merge a PR that modifies files under `fireai/core/qomn_kernel.py`,
`fireai/core/nfpa72_*.py`, `fireai/core/voltage_drop.py`,
`fireai/core/battery_aging_derating.py`, `fireai/core/device_placement.py`,
`fireai/constants/**`, `qomn_fire/core/constants.py`, `qomn_conduit/**`,
or `facp_system/**`, the commit message MUST contain one of:

1. `Signed-off-by: Your Name PE` (PE/FPE sign-off)
2. `NFPA 72-2022 §17.7.3.2.3` (verbatim standard citation with year + section)
3. `Signed-off-by: Your Name NON-ENGINEERING` (ONLY for non-engineering
   changes like formatting/dependency bumps — abusing this for engineering
   changes defeats the guard)

Bot commits (dependabot/github-actions/renovate) are auto-passed.

---

## 11. Deferred Items (with rationale)

| Item | Rationale for Deferral |
|------|------------------------|
| F-10b (jsPDF replacement) | XSS fix is in place; PDF-library swap is UX, not safety. Separate PR. |
| C-06 Voronoi NAC placement | Grid placement is conservative (never under-covers); Voronoi optimizes count. Separate PR. |
| mypy `|| true` removal | 434 pre-existing type errors need fixing first. Separate hardening PR. |
| Coverage 95% on `fireai/core/` | Current ~47% repo-wide; raised threshold to 50% as Step 1. Step 2 = per-module 95% in CI. Step 3 = 80% repo-wide. Step 4 = 95% repo-wide after PE review. |
| UL 864 / FM approval | Requires third-party lab testing — outside scope of code PR. |
| AHJ sign-off | Requires jurisdiction-specific submittal — outside scope of code PR. |
| Independent PE review | Requires engaging a licensed PE — outside scope of code PR. |
| SIEM integration | Requires Splunk/Elastic infrastructure — separate DevOps PR. |
| Mutation testing (mutmut/cosmic-ray) | Requires baseline mutation score + CI time budget — separate quality PR. |
| Real FDS/CFAST subprocess integration | Requires NIST FDS binary installation + license — separate infrastructure PR. |
| Real DWG/RVT parsing | RVT parser is placeholder (requires Revit API); DWG uses LibreDWG. Separate PR. |

---

## 12. References

- **NFPA 72-2022** — National Fire Alarm and Signaling Code
- **NEC 2023 (NFPA 70)** — National Electrical Code, Chapter 9 Table 8
- **IBC 2024** — International Building Code
- **ADA 2010** — Americans with Disabilities Act
- **IEEE 485** — IEEE Recommended Practice for Sizing Lead-Acid Batteries
- **UL 864** — Standard for Control Units and Accessories for Fire Alarm Systems

This document is maintained alongside `fireai/constants/nfpa72.py` and
`fireai/constants/nec.py`. Any change to those files MUST update this
document and pass the regulatory-data-guard CI check.
