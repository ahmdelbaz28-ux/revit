# FPE Sign-Off Review — NFPA 72 Calculations

**Document ID**: FPE-NFPA72-2026-001
**Date**: 2026-06-20
**Reviewer**: [Pending — Licensed Fire Protection Engineer (FPE)]
**Status**: ⏳ **PENDING FPE REVIEW** — This document is a self-assessment by the
development team and has NOT been reviewed or approved by a licensed FPE.
**Do NOT deploy to production** without FPE sign-off.

---

## ⚠️ Critical Disclaimer

This software calculates fire alarm system parameters per NFPA 72-2022.
**The calculations have NOT been reviewed or approved by a licensed Fire
Protection Engineer (FPE).** All outputs must be verified by a qualified
FPE before being used in any real-world fire alarm system design.

Per NFPA 72 §1.2 (Scope): "This Code covers the application, installation,
location, performance, and maintenance of fire alarm systems, fire warning
systems, and emergency communication systems."

The calculations in this software are engineering tools, NOT a substitute
for professional engineering judgment.

---

## 1. Scope of Review

This document covers the following NFPA 72 calculation modules in FireAI:

| Module | File | Lines | NFPA 72 Sections |
|--------|------|-------|------------------|
| Detector Spacing | `fireai/core/nfpa72_calculations.py:463-556` | 94 | §17.6.3.1.1 |
| Coverage Radius | `fireai/core/nfpa72_calculations.py:522-542` | 21 | §17.7.4.2.3.1 |
| Wall Distance | `fireai/core/nfpa72_calculations.py:545-556` | 12 | §17.6.3.1.1 |
| Heat Detector Coverage | `fireai/core/nfpa72_calculations.py:123-171` | 49 | §17.6.3.1 |
| Voltage Drop | `fireai/core/nfpa72_calculations.py:1005-1074` | 70 | §10.6.4, §27.4.1.2 |
| Battery Capacity | `fireai/core/nfpa72_calculations.py:1081-1142` | 62 | §10.6.7.2.1 |
| NAC Loading | `fireai/core/nfpa72_calculations.py:1273-1336` | 64 | §27.5 |
| AWG Selection | `fireai/core/nfpa72_calculations.py:1337-1437` | 101 | NEC Art. 760.71 |
| Constants (SSoT) | `fireai/constants/nfpa72.py` | 421 | All sections |

---

## 2. Detector Spacing Calculation Review

### 2.1 Smoke Detector Spacing

**NFPA 72 §17.6.3.1.1**: Listed spacing S = 30 ft (9.1 m) on smooth ceilings
≤ 3.0 m height.

**Implementation** (`calculate_max_spacing` at line 463):
- ✅ Routes through `calculate_coverage_radius_from_height()` which reads
  from `fireai/constants/nfpa72.py` (Single Source of Truth)
- ✅ Smoke spacing is flat 9.1 m at all heights (correct per NFPA 72)
- ✅ Sloped ceiling handling uses `min(low_height, high_height)` per §17.6.3.1.2

**P0.1 FIX (2026-06-20)**: Previously returned 9.1 m for ALL detector types
including heat. Now correctly branches on `detector_type`:
- SMOKE → 9.1 m (NFPA 72 Table 17.6.3.1.1 smoke column)
- HEAT → 6.1 m at h≤3.0 m (NFPA 72 Table 17.6.3.1.1 heat column)

### 2.2 Coverage Radius

**NFPA 72 §17.7.4.2.3.1**: Coverage radius R = 0.7 × S (diagonal of square grid).

**Implementation** (`calculate_coverage_radius` at line 522):
- ✅ Correctly uses `R = 0.7 × S` (not `S/2`)
- ✅ Documents distinction between R (6.37 m for smoke) and wall distance (4.55 m)

### 2.3 Wall Distance

**NFPA 72 §17.6.3.1.1**: Max wall distance = S/2.

**Implementation** (`calculate_max_wall_distance` at line 545):
- ✅ Correctly returns `S/2` (not `0.7 × S`)
- ✅ For smoke at h≤3.0 m: returns 4.55 m (correct)

### 2.4 Items Requiring FPE Verification

- [ ] **Heat detector height adjustment table**: Verify the values in
  `fireai/constants/nfpa72.py` match NFPA 72 Table 17.6.3.1.1 heat column
  for heights 3.0 m, 3.7 m, 4.6 m, 6.1 m, 7.6 m, 9.1 m, 10.7 m, 12.2 m.
- [ ] **Sloped ceiling calculation**: Verify that using `min(low, high)` is
  the correct interpretation of §17.6.3.1.2 (some FPEs use average height).
- [ ] **Beam pocket correction**: Verify `beam_pocket_correction_factor()`
  at line 858 matches §17.6.3.1.3.

---

## 3. Voltage Drop Calculation Review

### 3.1 PLFA Circuits (SLC/IDC)

**NFPA 72 §27.4.1.2**: Voltage drop on PLFA circuits ≤ 10%.

**Implementation** (`check_voltage_drop` at line 1005):
- ✅ Default `max_drop_fraction = 0.10` (10%) — correct for PLFA
- ✅ V78 FIX: Changed from 15% (no NFPA basis) to 10%
- ✅ Input validation: NaN/Inf/negative values raise `ValueError`
- ✅ Return path included: `total_resistance = R × L × 2`

### 3.2 NAC Circuits

**NFPA 72 §10.6.4**: Voltage at most remote device must be within listed range.

**Implementation**:
- ✅ Caller can pass `max_drop_fraction=0.20` for NAC circuits (per §10.6.4)
- ✅ Default is more restrictive 10% (safe default)

### 3.3 Items Requiring FPE Verification

- [ ] **Return path assumption**: Verify that `L × 2` (return path) is
  correct for all circuit topologies (Class A vs Class B).
- [ ] **Cable resistance values**: Verify AWG table at line 1153 matches
  NEC Chapter 9, Table 8 (copper at 75°C).

---

## 4. Battery Capacity Calculation Review

### 4.1 Standby + Alarm Duration

**NFPA 72 §10.6.7.2.1**: Minimum 24 h standby + 5 min alarm (most occupancies).

**Implementation** (`required_battery_capacity_ah` at line 1081):
- ✅ Default `standby_hours = 24.0` (correct)
- ✅ Default `alarm_minutes = 5.0` (correct)
- ✅ Default `safety_factor = 1.20` (20% margin for aging/temperature)
- ✅ V78 FIX: Changed parameter names from `_ma` to `_a` (Amps) — was 1000× confusion trap
- ✅ Input validation: Refuses `standby_hours < 24` (violates §10.6.7.2.1)

### 4.2 Formula

```
required_ah = (standby_current × standby_hours + alarm_current × alarm_minutes/60) × safety_factor
```

**Verification**: For a typical FACP:
- Standby: 0.5 A × 24 h = 12 Ah
- Alarm: 2.0 A × 5/60 h = 0.167 Ah
- Total: (12 + 0.167) × 1.20 = 14.6 Ah → round up to 15 Ah battery

### 4.3 Items Requiring FPE Verification

- [ ] **Safety factor**: Verify 1.20 (20%) is adequate. Some FPEs use 1.25
  or apply separate aging and temperature derating factors.
- [ ] **Alarm duration**: Verify 5 min is correct for the target occupancy
  (high-rise may require 15 min per local AHJ).
- [ ] **Battery aging**: Verify interaction with `battery_aging_derating.py`
  (separate module that applies IEEE 1188 aging curves).

---

## 5. AWG Wire Gauge Selection Review

### 5.1 Minimum Gauge

**NEC Article 760.71, NFPA 72 §27.4.1**: Minimum AWG 14 for fire alarm wiring.

**Implementation** (line 1163):
- ✅ V131 FIX: AWG 18 and 16 removed from `AVAILABLE_AWG_FOR_FA` (not permitted)
- ✅ Available gauges: 14, 12, 10 only

### 5.2 Resistance Values

**NEC Chapter 9, Table 8**: DC resistance at 75°C (stranded copper).

**Implementation** (line 1153):
- ✅ V51 FIX: Corrected from 20°C values (~18% too low, unsafe direction)
- ✅ AWG 18/16 are solid; all others are stranded (Class B)

### 5.3 Items Requiring FPE Verification

- [ ] **Temperature rating**: Verify 75°C is correct for FA wiring
  (some jurisdictions require 90°C ampacity).
- [ ] **Ampacity**: Verify `ampacity_75c` values match NEC Table 310.16.

---

## 6. NFPA 72 Constants (Single Source of Truth)

### 6.1 SSoT Principle

All NFPA 72 constants are centralized in `fireai/constants/nfpa72.py` (421 lines).
No other module may define duplicate NFPA 72 constants — all must import from
this canonical source.

### 6.2 Items Requiring FPE Verification

- [ ] **Detector spacing table**: Verify all values in `nfpa72.py` match
  NFPA 72-2022 Table 17.6.3.1.1.
- [ ] **Coverage radius factors**: Verify 0.7 (smoke) and heat-specific factors.
- [ ] **Battery duration requirements**: Verify 24h/5min defaults.
- [ ] **Voltage drop limits**: Verify 10% (PLFA) and 20% (NAC).

---

## 7. Test Coverage

### 7.1 Current State

- `tests/test_nfpa72_calculations.py`: exists but coverage is ~24%
- Property-based tests in `tests/property_based/`: limited
- **Gap**: Critical functions like `calculate_max_spacing` have only
  basic regression tests, not comprehensive coverage

### 7.2 Recommended Test Additions

Before FPE sign-off, the following tests must be added:
- [ ] Heat detector spacing at all heights (3.0, 3.7, 4.6, 6.1, 7.6, 9.1, 10.7, 12.2 m)
- [ ] Smoke detector spacing at all heights
- [ ] Sloped ceiling calculation (low point vs high point)
- [ ] Voltage drop: edge cases (zero length, max current, NaN inputs)
- [ ] Battery: all occupancy types (24h, 60h, 5min, 15min alarm)
- [ ] AWG selection: all gauges, ampacity limits

---

## 8. Known Limitations

1. **No jurisdiction-specific amendments**: NFPA 72 is adopted with local
   amendments in many jurisdictions. This software uses the base NFPA 72-2022
   — local amendments must be applied manually.

2. **No integration with AHJ submission formats**: The software calculates
   correct values but does not generate AHJ-compliant submission documents.

3. **No historical code versions**: Only NFPA 72-2022 is supported. Older
   buildings may require compliance with prior editions (2019, 2016).

4. **Single-occupancy assumption**: Battery calculations assume a single
   occupancy type. Mixed-use buildings may require different alarm durations
   per floor.

---

## 9. FPE Review Checklist

The following must be verified by a licensed FPE before production deployment:

### 9.1 Calculations
- [ ] Detector spacing (smoke + heat) matches NFPA 72 Table 17.6.3.1.1
- [ ] Coverage radius formula (R = 0.7 × S) is correct
- [ ] Wall distance (S/2) is correct
- [ ] Voltage drop formula and limits (10% PLFA, 20% NAC)
- [ ] Battery capacity formula and defaults (24h/5min)
- [ ] AWG resistance values match NEC Chapter 9, Table 8
- [ ] AWG minimum gauge (14) per NEC 760.71

### 9.2 Constants
- [ ] All values in `fireai/constants/nfpa72.py` verified against NFPA 72-2022
- [ ] No duplicate constants elsewhere in codebase
- [ ] SSoT principle enforced

### 9.3 Edge Cases
- [ ] NaN/Inf input validation on all calculation functions
- [ ] Negative value handling
- [ ] Sloped ceiling calculation
- [ ] Beam pocket correction factor

### 9.4 Documentation
- [ ] All NFPA 72 section references verified
- [ ] All formula derivations documented
- [ ] All assumptions stated explicitly

---

## 10. Sign-Off

### 10.1 Developer Self-Assessment

**Developer**: FireAI Engineering Team
**Date**: 2026-06-20
**Assessment**: The calculations appear correct based on our reading of
NFPA 72-2022. However, we are NOT licensed FPEs and cannot certify
compliance. All calculations must be verified by a licensed FPE.

### 10.2 FPE Review (PENDING)

**FPE Name**: ________________________________
**License Number**: ____________________________
**Jurisdiction**: ____________________________
**Review Date**: ____________________________

**Review Result**:
- [ ] **APPROVED** — Calculations are correct and comply with NFPA 72-2022
- [ ] **APPROVED WITH CONDITIONS** — See attached conditions
- [ ] **REJECTED** — See attached reasons

**Conditions/Reasons**:
_______________________________________________________________
_______________________________________________________________
_______________________________________________________________

**FPE Signature**: ____________________________

---

## 11. References

1. NFPA 72-2022: National Fire Alarm and Signaling Code
2. NEC (NFPA 70-2023): National Electrical Code
3. IEEE 1188: Recommended Practice for Batteries for UPS
4. IEC 60300-3-11: Reliability Centered Maintenance

---

**END OF DOCUMENT**

⚠️ **This document is NOT a substitute for professional FPE review.**
**Do NOT deploy this software to production without FPE sign-off.**
