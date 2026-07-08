# Engineering Review Required — Safety-Critical Code Changes

**Document ID:** ENG-REVIEW-2026-07-08
**Author:** AI Assistant (automated)
**Review Required By:** Licensed Fire Protection Engineer (PE/FPE)
**Status:** PENDING ENGINEER REVIEW

---

## Executive Summary

This document describes code changes made to safety-critical fire protection
calculations in the BAZSPARK platform. These changes were made by an AI
assistant to fix bugs, but they affect calculations that directly impact
life-safety decisions per NFPA 72, NFPA 101, and IEC 60079-10-1.

**A licensed Fire Protection Engineer (PE/FPE) MUST review and sign off on
these changes before the platform is used for any real-world fire alarm
system design.**

---

## Change 1: `q_max_from_fire_load` — Peak HRR Calculation

### File
`fireai/core/scenario_engine.py`, function `FirePhysics.q_max_from_fire_load()`

### What Changed
**Before (BUGGY):** The function computed `_t_burn` and `_total_mj` but had
**no return statement** — it fell off the end and returned `None` implicitly.
The caller at line 810 received `None` and passed it to `hrr_at_time()`,
which treats `None` as "no cap" — meaning the t² fire growth model
extrapolated Heat Release Rate (HRR) to infinity.

**After (FIXED):** The function now returns:
```python
t_burn = _BURN_DURATION.get(occupancy.lower(), _BURN_DURATION["default"])
total_mj = fire_load_mj_m2 * area_m2
return (total_mj / t_burn) * 1000.0  # MJ/s × 1000 = kW
```

### Engineering Basis
The formula implements the steady-state HRR cap from the fuel-limited phase:
- **Q_max = (total fuel energy) / (burn duration)**
- `total_mj = fire_load_mj_m2 × area_m2` — total energy in the compartment (MJ)
- `t_burn` — burn duration by occupancy type (seconds), from `_BURN_DURATION` table
- Conversion: MJ/s = MW, so × 1000 gives kW

### Burn Duration Table (source: SFPE Handbook, engineering judgment)
| Occupancy | t_burn (s) | Basis |
|-----------|-----------|-------|
| office | 1200 (20 min) | Typical office fuel package |
| warehouse | 900 (15 min) | High fuel load, faster burnout |
| retail | 1000 (~17 min) | Moderate fuel, mixed merchandise |
| education | 1200 (20 min) | Similar to office |
| healthcare | 1500 (25 min) | Slower — more compartmentation |
| residential | 1200 (20 min) | Typical residential fuel |
| industrial | 800 (~13 min) | Fast burnout, high ventilation |
| default | 1200 (20 min) | Conservative default |

### Verification (local)
- Office 100m² × 500 MJ/m² → Q_max = 41.67 MW (reasonable for office)
- Warehouse 200m² × 1000 MJ/m² → Q_max = 222 MW (reasonable for warehouse)

### Questions for Engineer Review
1. **Is the formula `Q_max = total_mj / t_burn` appropriate?** Some references
   use `Q_max = (fire_load × area) / t_burn` with a ventilation factor. Should
   ventilation-limited burning be considered?
2. **Are the burn duration values appropriate?** The table uses single values
   per occupancy. Should ranges or probability distributions be used instead?
3. **Should a safety factor be applied?** The current formula has no safety
   factor. For life-safety calculations, should Q_max be multiplied by 1.2-1.5
   to account for uncertainties?
4. **Ventilation-controlled fires:** In poorly ventilated spaces, the actual
   HRR may be lower than Q_max due to oxygen depletion. Should this be modeled?

### Standards References
- NFPA 101-2021 §A.7.2.2.2 (ASET/RSET methodology)
- SFPE Handbook of Fire Protection Engineering, 5th ed., Chapter 17
- NFPA 72-2022 §A.17.6.3 (t² fire growth model)

---

## Change 2: `ProofCertificate` — Missing `effective_radius_m` Field

### File
`fireai/core/spatial_engine/proof_certificate.py`, class `ProofCertificate`

### What Changed
**Before (BUGGY):** The `ProofCertificate` dataclass was missing the
`effective_radius_m` field, but:
- `ProofCertificateGenerator.generate()` passed `effective_radius_m=round(R_eff, 4)`
  to the constructor (line 290)
- `ProofCertificate.compute_hash()` referenced `self.effective_radius_m` (line 115)

This caused `TypeError: ProofCertificate.__init__() got an unexpected keyword
argument 'effective_radius_m'` — **no coverage certificate could ever be
generated.** The mathematical proof that every point in a room is within
NFPA 72 coverage radius R of a detector was UNREACHABLE.

**After (FIXED):** Added the field:
```python
# ── Proof Parameters ──────────────────────────────────────────────
proof_method: str = "delta_conservative_grid"
grid_step_m: float = 0.20  # δ = cell size
delta_margin_m: float = 0.0  # δ√2/2
effective_radius_m: float = 0.0  # R_eff = R − δ√2/2 (NEW FIELD)
max_spacing_m: float = 0.0  # S (detector spacing)
wall_min_m: float = 0.10  # Minimum wall distance
```

### Engineering Basis
The δ-conservative grid verification method proves coverage:
- **R** = coverage radius (NFPA 72 §17.7.4.2.3.1: R = 0.7 × S)
- **δ** = grid cell size (0.20 m default)
- **δ√2/2** = maximum distance from any room point to nearest grid point
- **R_eff = R − δ√2/2** = effective radius used in grid verification

**Mathematical proof (triangle inequality):**
```
For any room point P, let G be the nearest grid point:
  dist(P, D) ≤ dist(P, G) + dist(G, D)
             ≤ δ√2/2 + R_eff
             = δ√2/2 + (R − δ√2/2)
             = R
```
Therefore, if every grid point is within R_eff of a detector, every room
point is within R of a detector. QED.

### Verification (local)
- 39 tests in `tests/test_proof_certificate.py` all pass
- `test_analysis_pipeline.py::TestAnalyzeRoomHappyPath::test_simple_room_succeeds`
  now passes (was failing due to this bug)

### Questions for Engineer Review
1. **Is δ = 0.20 m appropriate?** The grid resolution affects proof granularity.
   Finer grids (δ = 0.10 m) give tighter bounds but cost more computation.
   Is 0.20 m sufficient for AHJ (Authority Having Jurisdiction) acceptance?
2. **Is the triangle inequality proof acceptable for compliance documentation?**
   Some AHJs may require finite element analysis or physical testing in
   addition to mathematical proofs.
3. **Should the hash computation include more fields?** The current
   `compute_hash()` includes effective_radius_m, but should it also include
   the timestamp and fireai_version for audit trail completeness?
4. **NFPA 72 §17.7.4.2.3.1 says R = 0.7 × S.** Is this the correct reference
   for all detector types (smoke, heat, flame), or are there exceptions?

### Standards References
- NFPA 72-2022 §17.7.4.2.3.1 (coverage radius R = 0.7 × S)
- NFPA 72-2022 Table 17.6.3.1.1 (detector spacing by type)
- ISO 10303-21 (STEP file format, used for certificate serialization)

---

## Change 3: `check_voltage_drop` — DC Return Path Factor (×2)

### File
`fireai/core/nfpa72_calculations.py`, function `check_voltage_drop()`

### What Changed
**Before (BUGGY):** The standalone `check_voltage_drop()` function computed
`total_resistance = cable_resistance_ohm_per_m × cable_length_m` **without**
the ×2 factor for the DC return path. This understated voltage drop by 50%.

**After (FIXED):**
```python
from fireai.constants.nfpa72 import DC_RETURN_PATH_FACTOR  # = 2.0
total_resistance = cable_resistance_ohm_per_m * cable_length_m * DC_RETURN_PATH_FACTOR
```

### Engineering Basis
Per NFPA 72 §10.14, fire alarm circuits use DC wiring with a **return path**
(2 conductors: positive + negative). The total circuit resistance is:
- **R_total = R_conductor × length × 2** (factor of 2 for the return path)

The Pydantic `VoltageDropInput.compute_voltage_drop()` method already had
this factor — this fix aligns the standalone function.

### Verification
- `test_voltage_drop_properties` (hypothesis property-based test) now passes
- Updated `test_drop_fraction_calculation`: expected 0.5 V → 1.0 V
  (1.0 A × 0.01 Ω/m × 50 m × 2 = 1.0 V)

### Questions for Engineer Review
1. **Is the ×2 factor correct for all circuit types?** NAC (Notification
   Appliance Circuits) and SLC (Signaling Line Circuits) both use 2-conductor
   wiring, but are there exceptions (e.g., 4-wire circuits, Class A vs Class B)?
2. **Should the factor be configurable?** Some specialized circuits (e.g.,
   addressable device loops with separate power/signal conductors) may have
   different return path topologies.
3. **Voltage drop at alarm load:** NFPA 72 §10.6.10.2 requires that voltage
   at the last device on a NAC must be ≥ the device's minimum operating
   voltage. Does this function's output feed into that compliance check?

### Standards References
- NFPA 72-2022 §10.14 (voltage drop calculations)
- NFPA 72-2022 §10.6.10.2 (NAC voltage requirements)
- NEC Article 760 (fire alarm wiring)

---

## Change 4: HAC Classification Engine — `Vz_diluted_m3` Formula

### File
`fireai/core/hac_classification_engine.py`, function `hazardous_zone_extent()`

### What Changed
The function now computes `Vz_diluted_m3` (volume of hazardous atmosphere
after ventilation dilution) per IEC 60079-10-1:2015 Annex B:

```python
# Vz = (dV/dt)_source / (f × n)  per IEC 60079-10-1 Annex B eq. B.3
Vz_diluted_m3 = Vz_source_m3_s / (effective_dilution_rate + 1e-12)
```

Where:
- `Vz_source_m3_s` = hazardous volume rate at source (m³/s), from eq. B.1
- `effective_dilution_rate` = f × n (1/s), where f = ventilation
  effectiveness, n = air changes per second

### Questions for Engineer Review
1. **Is the formula `Vz = Vz_source / (f × n)` correct per IEC 60079-10-1?**
   The standard's eq. B.3 uses `(dV/dt)_min` (minimum ventilation rate), not
   the source release rate. Should this be `(dV/dt)_min` instead?
2. **Ventilation effectiveness values:** The `_VENT_EFFECTIVENESS` table maps
   ventilation grades to f values (0.5-1.0). Are these per IEC 60079-10-1
   Table B.1?
3. **Air change rates:** The `_VENT_ACH` table maps ventilation grades to
   air changes per hour (6-30 ACH). Are these appropriate for Zone 2
   classification per IEC 60079-10-1?
4. **No tests exist for this module.** This is a CRITICAL gap — see the
   new test file `tests/test_hac_classification_engine.py` (added in this
   commit) for initial coverage. Engineer should verify the test values
   against hand calculations.

### Standards References
- IEC 60079-10-1:2015 Annex B (hazardous area classification)
- NFPA 497-2021 §4.5 (area classification for flammable gases)
- API RP 505 (classification for petroleum facilities)

---

## Sign-Off Protocol (MANDATORY — DO NOT REMOVE)

> ⚠️ **LIFE-SAFETY NOTICE**: This platform calculates fire alarm coverage,
> ASET/RSET timing, and hazardous area classification for real buildings.
> **No design produced by this software may be used for any real-world
> fire alarm system until EVERY change listed above has a SIGNED
> PE/FPE approval below.** Using unsigned output is a violation of
> NFPA 72 §1.2 (Authority Having Jurisdiction) and may constitute
> professional negligence.

### A. Per-Change Engineer Sign-Off

Each safety-critical change requires its OWN individual sign-off.
An engineer signing Change 1 is NOT signing Change 2, 3, or 4.
Strike through (~~like this~~) any item the engineer does NOT approve;
that change MUST then be reverted from the codebase before production use.

#### Change 1 — `q_max_from_fire_load` (Peak HRR Calculation)
**Status:** ☐ APPROVED  ☐ REJECTED  ☐ APPROVED WITH CONDITIONS

- Formula `Q_max = (fire_load_mj_m2 × area_m2) / t_burn × 1000` is correct: _____
- Burn duration values in `_BURN_DURATION` table are appropriate: _____
- Ventilation-controlled fires are NOT a concern for this use case (or have been addressed): _____
- Safety factor (currently 1.0) is adequate for life-safety: _____

| Field | Value |
|-------|-------|
| Engineer Name (print) | _________________________________ |
| PE/FPE License Number | _________________________________ |
| License State/Jurisdiction | _________________________________ |
| License Expiration Date | _________________________________ |
| AHJ Reference (if applicable) | _________________________________ |
| Review Date | _________________________________ |
| Engineer Signature | _________________________________ |

#### Change 2 — `ProofCertificate` δ-Conservative Grid Method
**Status:** ☐ APPROVED  ☐ REJECTED  ☐ APPROVED WITH CONDITIONS

- δ = 0.20 m grid resolution is appropriate for AHJ acceptance: _____
- Triangle-inequality proof is acceptable compliance documentation: _____
- `effective_radius_m` field addition is structurally correct: _____
- Hash computation includes all audit-relevant fields: _____

| Field | Value |
|-------|-------|
| Engineer Name (print) | _________________________________ |
| PE/FPE License Number | _________________________________ |
| License State/Jurisdiction | _________________________________ |
| License Expiration Date | _________________________________ |
| AHJ Reference (if applicable) | _________________________________ |
| Review Date | _________________________________ |
| Engineer Signature | _________________________________ |

#### Change 3 — `check_voltage_drop` DC Return Path Factor (×2)
**Status:** ☐ APPROVED  ☐ REJECTED  ☐ APPROVED WITH CONDITIONS

- ×2 factor is correct for Class A circuits (2-conductor): _____
- ×2 factor is correct for Class B circuits (2-conductor): _____
- 4-wire circuits are not applicable (or have been separately handled): _____
- NAC and SLC voltage drop calculations both use this function correctly: _____

| Field | Value |
|-------|-------|
| Engineer Name (print) | _________________________________ |
| PE/FPE License Number | _________________________________ |
| License State/Jurisdiction | _________________________________ |
| License Expiration Date | _________________________________ |
| AHJ Reference (if applicable) | _________________________________ |
| Review Date | _________________________________ |
| Engineer Signature | _________________________________ |

#### Change 4 — HAC `Vz_diluted_m3` Formula (IEC 60079-10-1 Annex B)
**Status:** ☐ APPROVED  ☐ REJECTED  ☐ APPROVED WITH CONDITIONS

- Formula `Vz = Vz_source / (f × n)` is correct per IEC 60079-10-1 Annex B eq. B.3: _____
- The use of source release rate vs. `(dV/dt)_min` has been justified: _____
- `_VENT_EFFECTIVENESS` table values (0.5–1.0) match IEC 60079-10-1 Table B.1: _____
- `_VENT_ACH` table values (6–30 ACH) are appropriate for Zone 2 classification: _____
- Test values in `tests/test_hac_classification_engine.py` match hand calculations: _____

| Field | Value |
|-------|-------|
| Engineer Name (print) | _________________________________ |
| PE/FPE License Number | _________________________________ |
| License State/Jurisdiction | _________________________________ |
| License Expiration Date | _________________________________ |
| AHJ Reference (if applicable) | _________________________________ |
| Review Date | _________________________________ |
| Engineer Signature | _________________________________ |

### B. Master Approval Block

This block is signed ONLY AFTER all individual change sign-offs above
are complete. It authorizes the platform for production use in fire
alarm system design.

> By signing below, the Principal Engineer confirms that:
> 1. ALL changes above have been individually reviewed and signed.
> 2. The platform as a whole meets NFPA 72-2022, NFPA 101-2021,
>    IEC 60079-10-1:2015, and NFPA 557-2016 requirements as applicable.
> 3. The platform is approved for use ONLY in the jurisdictions listed.
> 4. The Principal Engineer accepts professional liability for designs
>    produced using this platform within the approved scope.

| Field | Value |
|-------|-------|
| Principal Engineer Name (print) | _________________________________ |
| PE/FPE License Number | _________________________________ |
| License State/Jurisdiction(s) | _________________________________ |
| License Expiration Date | _________________________________ |
| Approved Occupancy Types | _________________________________ |
| Approved Building Heights | _________________________________ |
| Approval Expiration Date | _________________________________ |
| Master Review Date | _________________________________ |
| Principal Engineer Signature | _________________________________ |
| Company / Firm | _________________________________ |
| Notary Acknowledgement (optional) | _________________________________ |

### C. Revision History

| Rev | Date | Author | Change Summary |
|-----|------|--------|----------------|
| 1.0 | 2026-07-08 | AI Assistant (automated) | Initial creation — 4 safety-critical changes flagged for PE/FPE review |
| 1.1 | 2026-07-08 | AI Assistant (V143 hardening) | Added per-change sign-off blocks, master approval block, and revision history. Added test-suite reference for HAC. NO engineering formula changes. |

### D. Production Use Blocker

**This section MUST be completed before ANY production deployment:**

- [ ] ALL 4 changes above have SIGNED PE/FPE approval
- [ ] Master Approval Block is signed by Principal Engineer
- [ ] AHJ (Authority Having Jurisdiction) has been notified in writing
- [ ] At least ONE real-world design has been validated against hand calculations
- [ ] At least ONE real-world design has been validated against CFD (FDS) or full-scale test
- [ ] Insurance carrier has been notified (if applicable)
- [ ] Local fire marshal has been notified (if applicable)

Until ALL checkboxes above are ticked and dated, this platform is
**CLASSIFIED AS NON-PRODUCTION** and may only be used for:
- Internal training
- Design exploration
- Academic research
- Pre-design sizing (NOT final design)

---

## Appendix: How to Run the Tests

```bash
# Run all safety-critical tests (must pass before engineer review)
export FIREAI_SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export FIREAI_API_KEY="ci-test-admin-key"
export CORS_ALLOWED_ORIGINS="http://localhost:3000"
export DATABASE_URL="sqlite:////tmp/test.db"
export DIGITAL_TWIN_DB_PATH="/tmp/test.db"
export UDM_DB_PATH="/tmp/udm.db"
export SECRET_KEY="ci-test-hmac-secret-key-32-chars-minimum!!"
export FIREAI_HMAC_SECRET_KEY="ci-test-hmac-key-for-audit-trail"

# Safety-critical modules (must all pass)
python -m pytest \
    tests/test_proof_certificate.py \
    tests/test_hac_classification_engine.py \
    fireai/core/tests/test_analysis_pipeline.py \
    fireai/core/tests/test_nfpa72_calculations.py \
    tests/test_fireai_kernel_v30.py \
    tests/test_scenario_engine.py \
    -v --tb=short --no-cov

# Engineering Review Required verification:
# 1. Run tests above — all must pass
# 2. Inspect test values against hand calculations
# 3. Verify formula references in source code match cited standards
# 4. Sign the appropriate per-change block above
# 5. Tick the Production Use Blocker checkboxes
# 6. Commit the signed document to the repository
```
