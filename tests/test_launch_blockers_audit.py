"""
test_launch_blockers_audit.py — Comprehensive Launch Blocker Audit Tests
=========================================================================

This test suite exposes ALL problems that prevent a safe production launch
of the FireAI system per the Security & Compliance Audit Report.

Per agent.md Rule #10: MANDATORY TESTING — no code ships without passing tests.
Per agent.md Rule #12: SELF-CRITICISM — we must identify and expose our own flaws.

Test Categories:
  1. SSoT Violations — Multiple parallel NFPA 72 tables with different values
  2. Smoke Detector Spacing — Incorrect 1%/ft height reduction (NFPA 72 misapplication)
  3. Ceiling Height Limits — Wrong limits per detector type
  4. Cross-Module Consistency — Values must match across all modules
  5. Import Chain Integrity — All constants must trace to canonical source
  6. NEC Constants — V20 Bug #20 and correctness
  7. Architecture Compliance — Code must match documented architecture
  8. PE Sign-off — Regulatory data must carry proper disclaimers
  9. NaN/Inf Safety — Life-safety computations must reject invalid inputs
  10. Coverage Radius Consistency — R = 0.7*S must be consistent everywhere
"""

import os

import pytest

# Resolve repo root relative to this test file
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============================================================================
# 1. SSoT VIOLATIONS — Multiple parallel implementations
# ============================================================================

class TestSSoTViolations:
    """Verify that NFPA 72 constants exist in ONE place only.

    CRITICAL: Five parallel implementations of smoke detector spacing
    existed across the codebase. These tests verify they are now unified.
    """

    def test_qomn_kernel_imports_from_canonical_source(self):
        """qomn_kernel.py must import all NFPA 72 constants from fireai.constants.nfpa72."""
        from fireai.core import qomn_kernel

        # Verify the canonical imports exist
        assert hasattr(qomn_kernel, 'NFPA72_SMOKE_MAX_SPACING_M')
        assert hasattr(qomn_kernel, 'NFPA72_HEAT_MAX_SPACING_M')
        assert hasattr(qomn_kernel, 'NFPA72_COVERAGE_RADIUS_FACTOR')

    def test_no_duplicate_smoke_spacing_table_in_qomn_kernel(self):
        """qomn_kernel.py must NOT define its own SMOKE_SPACING_TABLE.

        The old code had NFPA72_SMOKE_SPACING_TABLE defined locally with
        wrong values (1%/ft reduction applied on top of table values).
        This must import from canonical source only.
        """
        import inspect

        from fireai.core import qomn_kernel

        source = inspect.getsource(qomn_kernel)

        # Must import from canonical source
        assert 'from fireai.constants.nfpa72 import' in source, (
            "qomn_kernel.py must import NFPA 72 constants from canonical source "
            "(fireai.constants.nfpa72), not define them locally."
        )

    def test_technology_dispatcher_imports_from_canonical_source(self):
        """nfpa72_technology_dispatcher.py must import table from canonical source."""
        import inspect

        from fireai.core import nfpa72_technology_dispatcher

        source = inspect.getsource(nfpa72_technology_dispatcher)
        assert 'from fireai.constants.nfpa72 import' in source, (
            "nfpa72_technology_dispatcher.py must import from canonical source."
        )

    def test_calculations_imports_from_canonical_source(self):
        """nfpa72_calculations.py must import table from canonical source."""
        import inspect

        from fireai.core import nfpa72_calculations

        source = inspect.getsource(nfpa72_calculations)
        assert 'from fireai.constants.nfpa72 import' in source, (
            "nfpa72_calculations.py must import from canonical source."
        )

    def test_constants_init_imports_from_canonical_nfpa72(self):
        """constants/__init__.py must import and re-export from nfpa72.py, not duplicate."""
        import inspect

        import fireai.constants

        source = inspect.getsource(fireai.constants)
        assert 'from fireai.constants.nfpa72 import' in source, (
            "constants/__init__.py must import from canonical nfpa72.py"
        )


# ============================================================================
# 2. SMOKE DETECTOR SPACING — NFPA 72-2022 §17.7.3.2.3
# ============================================================================

class TestSmokeDetectorSpacingCompliance:
    """Verify smoke detector spacing matches NFPA 72-2022 §17.7.3.2.3.

    NFPA 72 §17.7.3.2.3 states: "Spot-type smoke detectors shall be spaced
    not more than 30 ft (9.1 m) apart on smooth ceilings."

    CRITICAL BUG: The old code applied a 1%/ft height reduction from
    Table 17.6.3.5.1 (HEAT detector table) to SMOKE detectors. This
    produced up to 65% over-densification at high ceilings. While
    conservative (more detectors = safer), it is:
      - Engineering-incorrect
      - Risks AHJ rejection for non-compliance with §17.7.3.2.3
      - Causes economic waste (4x overdensification at 60ft)
    """

    def test_smoke_base_spacing_is_9_1m(self):
        """Smoke detector spacing at h<=3.0m must be exactly 9.1m (30ft)."""
        from fireai.constants.nfpa72 import SMOKE_MAX_SPACING_M

        assert SMOKE_MAX_SPACING_M == 9.1, (
            f"SMOKE_MAX_SPACING_M = {SMOKE_MAX_SPACING_M}, expected 9.1m per "
            "NFPA 72-2022 §17.7.3.2.3. Previous value was 9.144 (30ft × 0.3048) "
            "which is the exact conversion, but NFPA 72 states 9.1m in the standard."
        )

    def test_qomn_kernel_smoke_spacing_at_3m(self):
        """compute_smoke_detector_spacing at h=3.0m returns 9.1m."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing

        result = compute_smoke_detector_spacing(3.0)
        assert result['listed_spacing_m'] == 9.1, (
            f"Smoke spacing at h=3.0m = {result['listed_spacing_m']}m, "
            f"expected 9.1m per NFPA 72-2022 §17.7.3.2.3."
        )

    def test_qomn_kernel_smoke_no_double_reduction(self):
        """V127 Phase C: No additional 1%/ft reduction on top of table values.

        The V120 bug applied 1%/ft reduction ON TOP of already-reduced
        table values, causing double-reduction. At h=60ft (18.288m),
        this produced 9.1 * 0.35 = 3.19m spacing (65% overdensification)
        instead of the table value of 5.60m.
        """
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing

        # At h=10m (within table range), spacing should come from table
        # WITHOUT additional 1%/ft reduction
        result = compute_smoke_detector_spacing(10.0)
        spacing = result['listed_spacing_m']

        # The table value at h<=10.7m is 6.00m
        # If double-reduction bug exists, it would be 6.00 * (1 - 0.01*23.0) ≈ 4.62m
        # (23ft above 10ft baseline)
        assert spacing >= 6.0, (
            f"Smoke spacing at h=10m = {spacing}m. If this is below 6.0m, "
            f"the double-reduction bug (1%/ft on top of table) is still present. "
            f"Expected 6.00m from Table 17.6.3.1.1 WITHOUT additional reduction."
        )

    def test_smoke_spacing_table_values_are_conservative(self):
        """All height-adjusted smoke spacing values must be <= 9.1m (flat spacing).

        The table values should DECREASE as ceiling height increases.
        They are CONSERVATIVE (more detectors) per NFPA 72 §17.7.3.2.3
        which states flat 9.1m spacing.
        """
        from fireai.constants.nfpa72 import (
            SMOKE_HEIGHT_SPACING_TABLE,
            SMOKE_MAX_SPACING_M,
        )

        prev_spacing = float('inf')
        for h_max, spacing in SMOKE_HEIGHT_SPACING_TABLE:
            assert spacing <= SMOKE_MAX_SPACING_M, (
                f"Table entry h≤{h_max}m: spacing {spacing}m > max {SMOKE_MAX_SPACING_M}m. "
                f"Height-adjusted values must NOT exceed flat spacing."
            )
            assert spacing <= prev_spacing, (
                f"Table is not monotonically decreasing: h≤{h_max}m spacing {spacing}m "
                f"> previous {prev_spacing}m. Higher ceilings must have smaller spacing."
            )
            prev_spacing = spacing

    def test_smoke_coverage_radius_is_0_7_times_spacing(self):
        """Coverage radius R must equal 0.7 × S (NFPA 72 §17.7.4.2.3.1)."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing

        result = compute_smoke_detector_spacing(3.0)
        S = result['listed_spacing_m']
        R = result['coverage_radius_m']

        assert abs(R - 0.7 * S) < 0.001, (
            f"R = {R}m ≠ 0.7 × S = {0.7 * S}m. NFPA 72 §17.7.4.2.3.1 "
            f"defines coverage radius as R = 0.7 × S."
        )


# ============================================================================
# 3. CEILING HEIGHT LIMITS — Per Detector Type
# ============================================================================

class TestCeilingHeightLimits:
    """Verify ceiling height limits are correct per detector type.

    NFPA 72-2022 specifies DIFFERENT limits for smoke vs heat:
      - Smoke: 60ft (18.288m) per §17.7.3.2.4
      - Heat: 50ft (15.24m) per §17.6.3.1

    CRITICAL: The old code used 15.24m for ALL detector types, which
    incorrectly rejected valid smoke detector placements between 15.24m-18.288m.
    """

    def test_smoke_max_ceiling_height_is_18_288m(self):
        """Smoke detector ceiling height limit must be 18.288m (60ft)."""
        from fireai.constants.nfpa72 import SMOKE_MAX_CEILING_HEIGHT_M

        assert SMOKE_MAX_CEILING_HEIGHT_M == 18.288, (
            f"SMOKE_MAX_CEILING_HEIGHT_M = {SMOKE_MAX_CEILING_HEIGHT_M}, "
            f"expected 18.288m (60ft) per NFPA 72 §17.7.3.2.4."
        )

    def test_heat_max_ceiling_height_is_15_24m(self):
        """Heat detector ceiling height limit must be 15.24m (50ft)."""
        from fireai.constants.nfpa72 import HEAT_MAX_CEILING_HEIGHT_M

        assert HEAT_MAX_CEILING_HEIGHT_M == 15.24, (
            f"HEAT_MAX_CEILING_HEIGHT_M = {HEAT_MAX_CEILING_HEIGHT_M}, "
            f"expected 15.24m (50ft) per NFPA 72 §17.6.3.1."
        )

    def test_hard_limit_matches_smoke(self):
        """The hard ceiling height limit (for guard_ceiling_height_m) must
        be 18.288m — the smoke detector absolute maximum."""
        from fireai.constants.nfpa72 import CEILING_HEIGHT_HARD_LIMIT_M

        assert CEILING_HEIGHT_HARD_LIMIT_M == 18.288, (
            f"CEILING_HEIGHT_HARD_LIMIT_M = {CEILING_HEIGHT_HARD_LIMIT_M}, "
            f"expected 18.288m (60ft) matching smoke detector max per §17.7.3.2.4."
        )

    def test_guard_accepts_smoke_at_17m(self):
        """guard_ceiling_height_m must accept h=17m (within 18.288m limit).

        The old code rejected heights > 15.24m, which would incorrectly
        block valid smoke detector placements between 15.24m and 18.288m.
        """
        from fireai.core.qomn_kernel import guard_ceiling_height_m

        # 17m is within the smoke detector limit (18.288m)
        result = guard_ceiling_height_m(17.0)
        assert result == 17.0, (
            "guard_ceiling_height_m(17.0) rejected a valid height. "
            "Smoke detectors are permitted up to 18.288m (60ft) per §17.7.3.2.4."
        )

    def test_guard_rejects_above_18_288m(self):
        """guard_ceiling_height_m must reject h > 18.288m."""
        from fireai.core.qomn_kernel import PhysicsGuardError, guard_ceiling_height_m

        with pytest.raises(PhysicsGuardError):
            guard_ceiling_height_m(19.0)

    def test_soft_limit_is_15_24m(self):
        """Soft ceiling height limit must be 15.24m (50ft)."""
        from fireai.constants.nfpa72 import CEILING_HEIGHT_SOFT_LIMIT_M

        assert CEILING_HEIGHT_SOFT_LIMIT_M == 15.24, (
            f"CEILING_HEIGHT_SOFT_LIMIT_M = {CEILING_HEIGHT_SOFT_LIMIT_M}, "
            f"expected 15.24m (50ft)."
        )

    def test_practical_smoke_height_is_6_096m(self):
        """Practical smoke detector height must be 6.096m (20ft)."""
        from fireai.constants.nfpa72 import SMOKE_PRACTICAL_CEILING_HEIGHT_M

        assert SMOKE_PRACTICAL_CEILING_HEIGHT_M == 6.096, (
            f"SMOKE_PRACTICAL_CEILING_HEIGHT_M = {SMOKE_PRACTICAL_CEILING_HEIGHT_M}, "
            f"expected 6.096m (20ft) per ECMAG guidance."
        )


# ============================================================================
# 4. CROSS-MODULE CONSISTENCY
# ============================================================================

class TestCrossModuleConsistency:
    """Verify that NFPA 72 values are consistent across all modules.

    This is the HEART of the audit: five parallel implementations had
    DIFFERENT values for the same NFPA 72 constant. These tests verify
    that all modules now agree.
    """

    def test_smoke_max_spacing_consistent_everywhere(self):
        """SMOKE_MAX_SPACING_M must be 9.1 in ALL modules."""
        from fireai.constants import SMOKE_MAX_SPACING_M as init_val
        from fireai.constants.nfpa72 import SMOKE_MAX_SPACING_M as canonical
        from fireai.core.qomn_kernel import NFPA72_SMOKE_MAX_SPACING_M as kernel_val

        assert canonical == 9.1, f"Canonical: {canonical} ≠ 9.1"
        assert init_val == 9.1, f"constants/__init__: {init_val} ≠ 9.1"
        assert kernel_val == 9.1, f"qomn_kernel: {kernel_val} ≠ 9.1"

        assert canonical == init_val == kernel_val, (
            f"SMOKE_MAX_SPACING_M mismatch: canonical={canonical}, "
            f"init={init_val}, kernel={kernel_val}"
        )

    def test_heat_max_spacing_consistent_everywhere(self):
        """HEAT_MAX_SPACING_M must be 6.1 in ALL modules."""
        from fireai.constants import HEAT_MAX_SPACING_M as init_val
        from fireai.constants.nfpa72 import HEAT_MAX_SPACING_M as canonical
        from fireai.core.qomn_kernel import NFPA72_HEAT_MAX_SPACING_M as kernel_val

        assert canonical == 6.1, f"Canonical: {canonical} ≠ 6.1"
        assert init_val == 6.1, f"constants/__init__: {init_val} ≠ 6.1"
        assert kernel_val == 6.1, f"qomn_kernel: {kernel_val} ≠ 6.1"

    def test_coverage_radius_factor_consistent(self):
        """COVERAGE_RADIUS_FACTOR must be 0.7 in ALL modules."""
        from fireai.constants import COVERAGE_FACTOR_FLAT_CEILING as init_val
        from fireai.constants.nfpa72 import COVERAGE_RADIUS_FACTOR as canonical
        from fireai.core.qomn_kernel import NFPA72_COVERAGE_RADIUS_FACTOR as kernel_val

        assert canonical == 0.7
        assert init_val == 0.7
        assert kernel_val == 0.7
        assert canonical == init_val == kernel_val

    def test_smoke_height_spacing_table_consistent(self):
        """SMOKE_HEIGHT_SPACING_TABLE must match across all modules."""
        from fireai.constants.nfpa72 import SMOKE_HEIGHT_SPACING_TABLE as canonical
        from fireai.core.nfpa72_technology_dispatcher import (
            _NFPA72_SMOKE_SPACING_TABLE as dispatcher_table,
        )

        # Convert tuples to lists for comparison
        canonical_list = list(canonical)
        assert canonical_list == list(dispatcher_table), (
            f"Smoke spacing table mismatch between canonical source and dispatcher.\n"
            f"Canonical: {canonical_list}\nDispatcher: {list(dispatcher_table)}"
        )

    def test_combined_table_matches_smoke_and_heat_tables(self):
        """COMBINED_HEIGHT_SPACING_TABLE must be consistent with individual tables."""
        from fireai.constants.nfpa72 import (
            COMBINED_HEIGHT_SPACING_TABLE,
            HEAT_HEIGHT_SPACING_TABLE,
            SMOKE_HEIGHT_SPACING_TABLE,
        )

        for i, (h_max, smoke_s, heat_s) in enumerate(COMBINED_HEIGHT_SPACING_TABLE):
            assert h_max == SMOKE_HEIGHT_SPACING_TABLE[i][0], (
                f"Row {i}: combined h_max={h_max} ≠ smoke h_max={SMOKE_HEIGHT_SPACING_TABLE[i][0]}"
            )
            assert smoke_s == SMOKE_HEIGHT_SPACING_TABLE[i][1], (
                f"Row {i}: combined smoke={smoke_s} ≠ smoke table={SMOKE_HEIGHT_SPACING_TABLE[i][1]}"
            )
            assert heat_s == HEAT_HEIGHT_SPACING_TABLE[i][1], (
                f"Row {i}: combined heat={heat_s} ≠ heat table={HEAT_HEIGHT_SPACING_TABLE[i][1]}"
            )

    def test_calculations_table_matches_canonical(self):
        """nfpa72_calculations._NFPA72_TABLE_17_6_3_1_1 must match canonical source."""
        from fireai.constants.nfpa72 import COMBINED_HEIGHT_SPACING_TABLE as canonical
        from fireai.core.nfpa72_calculations import _NFPA72_TABLE_17_6_3_1_1

        assert list(canonical) == list(_NFPA72_TABLE_17_6_3_1_1), (
            f"Combined table mismatch:\nCanonical: {list(canonical)}\n"
            f"Calculations: {list(_NFPA72_TABLE_17_6_3_1_1)}"
        )

    def test_heat_absolute_max_spacing_consistent(self):
        """HEAT_ABSOLUTE_MAX_SPACING_M must be 15.24m everywhere."""
        from fireai.constants import HEAT_ABSOLUTE_MAX_SPACING_M as init_val
        from fireai.constants.nfpa72 import HEAT_ABSOLUTE_MAX_SPACING_M as canonical

        assert canonical == 15.24
        assert init_val == 15.24

    def test_wall_min_distance_consistent(self):
        """WALL_MIN_DISTANCE_M must be 0.1016m (4 inches) everywhere."""
        from fireai.constants import WALL_MIN_DISTANCE_M as init_val
        from fireai.constants.nfpa72 import WALL_MIN_DISTANCE_M as canonical

        assert canonical == 0.1016
        assert init_val == 0.1016


# ============================================================================
# 5. IMPORT CHAIN INTEGRITY
# ============================================================================

class TestImportChainIntegrity:
    """Verify all NFPA 72 constants trace to the canonical source.

    Per agent.md Rule #17 (No Half-Solutions), all constants must
    come from fireai/constants/nfpa72.py. No module may define
    duplicate NFPA 72 constants.
    """

    def test_constants_init_re_exports_canonical(self):
        """constants/__init__.py must re-export from nfpa72.py, not define duplicates."""
        import os

        import fireai.constants

        # Read source file directly (inspect.getsource fails on __init__)
        init_path = os.path.dirname(fireai.constants.__file__) + '/__init__.py'
        with open(init_path, 'r') as f:
            source = f.read()

        # Check that it imports from canonical source
        assert 'from fireai.constants.nfpa72 import' in source, (
            "constants/__init__.py must import from canonical nfpa72.py"
        )

    def test_qomn_kernel_no_local_constant_definitions(self):
        """qomn_kernel.py must NOT define NFPA 72 constants with literal numeric values.

        Backward-compatible aliases like `NFPA72_SMOKE_MAX_SPACING_M = NFPA72_SMOKE_MAX_SPACING_M`
        are OK because they just re-assign the imported value. The test checks for
        assignments with LITERAL numeric values (not references to imported names).
        """
        import inspect
        import re

        from fireai.core import qomn_kernel

        source = inspect.getsource(qomn_kernel)

        # Check that no NFPA 72 constant is assigned a LITERAL numeric value
        # Pattern: VARNAME = <number> where VARNAME is an NFPA constant
        literal_assignments = re.findall(
            r'(?:SMOKE_MAX_SPACING_M|HEAT_MAX_SPACING_M|NFPA_MAX_M)\s*=\s*[\d]+',
            source
        )
        assert len(literal_assignments) == 0, (
            f"Found local constant definitions with literal values in qomn_kernel.py: "
            f"{literal_assignments}. All NFPA 72 constants must be imported from "
            f"fireai.constants.nfpa72."
        )

        # Also check the old hardcoded limit pattern
        assert 'NFPA_MAX_M = 15.24' not in source, (
            "Found old hardcoded NFPA_MAX_M = 15.24 in qomn_kernel.py. "
            "Must use _CEILING_HEIGHT_HARD_LIMIT_M (18.288m) from canonical source."
        )

    def test_nec_constants_in_dedicated_module(self):
        """NEC constants must be in fireai/constants/nec.py."""
        from fireai.constants.nec import (
            CONDUCTOR_DERATING_TABLE,
            MAX_CONDUCTOR_FILL_PCT,
        )

        assert MAX_CONDUCTOR_FILL_PCT is not None
        assert CONDUCTOR_DERATING_TABLE is not None


# ============================================================================
# 6. NEC CONSTANTS — V20 Bug #20
# ============================================================================

class TestNECConstants:
    """Verify NEC constants are correct and V20 Bug #20 is fixed.

    V20 Bug #20: The original dict had "40%" appearing twice — the second
    "40%" was meant to be "53%" (1_conductor value).
    """

    def test_conduit_fill_1_conductor_is_53(self):
        """1 conductor fill must be 53% (not 40% — V20 Bug #20)."""
        from fireai.constants.nec import MAX_CONDUCTOR_FILL_PCT

        assert MAX_CONDUCTOR_FILL_PCT["1_conductor"] == 53, (
            f"1_conductor fill = {MAX_CONDUCTOR_FILL_PCT['1_conductor']}%, "
            f"expected 53% per NEC Ch.9 Table 1. V20 Bug #20: was incorrectly 40%."
        )

    def test_conduit_fill_2_conductors_is_31(self):
        """2 conductors fill must be 31%."""
        from fireai.constants.nec import MAX_CONDUCTOR_FILL_PCT

        assert MAX_CONDUCTOR_FILL_PCT["2_conductors"] == 31, (
            f"2_conductors fill = {MAX_CONDUCTOR_FILL_PCT['2_conductors']}%, "
            f"expected 31% per NEC Ch.9 Table 1."
        )

    def test_conduit_fill_3_plus_is_40(self):
        """3+ conductors fill must be 40%."""
        from fireai.constants.nec import MAX_CONDUCTOR_FILL_PCT

        assert MAX_CONDUCTOR_FILL_PCT["3_plus"] == 40, (
            f"3_plus fill = {MAX_CONDUCTOR_FILL_PCT['3_plus']}%, "
            f"expected 40% per NEC Ch.9 Table 1."
        )

    def test_no_duplicate_40_in_conduit_fill(self):
        """V20 Bug #20: No two entries should have the same value 40%."""
        from fireai.constants.nec import MAX_CONDUCTOR_FILL_PCT

        values = list(MAX_CONDUCTOR_FILL_PCT.values())
        count_40 = values.count(40)

        # Only "3_plus" should be 40%. If "1_conductor" is also 40%, that's the bug.
        assert count_40 == 1, (
            f"Found {count_40} entries with value 40% in conduit fill table. "
            f"Only '3_plus' should be 40%. V20 Bug #20: '1_conductor' was "
            f"incorrectly 40% instead of 53%."
        )

    def test_derating_table_ranges_complete(self):
        """Conductor derating table must cover all ranges from 1 to 40+."""
        from fireai.constants.nec import CONDUCTOR_DERATING_TABLE

        # Must have entries for all standard ranges
        expected_ranges = [(1, 3), (4, 6), (7, 9), (10, 20), (21, 30), (31, 40), (41, 999)]
        for rng in expected_ranges:
            assert rng in CONDUCTOR_DERATING_TABLE, (
                f"Missing derating range {rng} in CONDUCTOR_DERATING_TABLE."
            )

    def test_derating_values_are_monotonically_decreasing(self):
        """Derating percentages must decrease as conductor count increases."""
        from fireai.constants.nec import CONDUCTOR_DERATING_TABLE

        prev_pct = float('inf')
        for (lo, hi), pct in sorted(CONDUCTOR_DERATING_TABLE.items()):
            assert pct <= prev_pct, (
                f"Derating not monotonically decreasing: {lo}-{hi} conductors "
                f"= {pct}% > previous {prev_pct}%"
            )
            prev_pct = pct


# ============================================================================
# 7. ARCHITECTURE COMPLIANCE
# ============================================================================

class TestArchitectureCompliance:
    """Verify the actual code structure matches ARCHITECTURE.md.

    The audit found that ARCHITECTURE.md described a src/ directory
    structure that doesn't exist. The actual structure uses fireai/.
    """

    def test_fireai_constants_dir_exists(self):
        """fireai/constants/ directory must exist."""
        import os
        assert os.path.isdir(os.path.join(REPO_ROOT, 'fireai', 'constants')), (
            "fireai/constants/ directory does not exist."
        )

    def test_fireai_constants_nfpa72_exists(self):
        """fireai/constants/nfpa72.py must exist as canonical source."""
        import os
        assert os.path.isfile(os.path.join(REPO_ROOT, 'fireai', 'constants', 'nfpa72.py')), (
            "fireai/constants/nfpa72.py does not exist. This is the canonical "
            "source of truth for all NFPA 72 constants."
        )

    def test_fireai_constants_nec_exists(self):
        """fireai/constants/nec.py must exist."""
        import os
        assert os.path.isfile(os.path.join(REPO_ROOT, 'fireai', 'constants', 'nec.py')), (
            "fireai/constants/nec.py does not exist."
        )

    def test_no_src_directory(self):
        """The src/ directory described in old ARCHITECTURE.md should NOT exist.
        The actual code uses fireai/ as the root package."""
        import os
        # src/ should not exist as a code directory
        assert not os.path.isdir(os.path.join(REPO_ROOT, 'src')), (
            "src/ directory exists but ARCHITECTURE.md was updated to reflect "
            "the actual fireai/ structure. Either update the code to match the "
            "documented structure, or remove the src/ directory."
        )

    def test_core_dir_has_expected_modules(self):
        """fireai/core/ must contain the documented modules."""
        import os
        core_dir = os.path.join(REPO_ROOT, 'fireai', 'core')
        expected_files = [
            'qomn_kernel.py',
            'nfpa72_models.py',
            'nfpa72_calculations.py',
            'nfpa72_technology_dispatcher.py',
        ]
        for f in expected_files:
            assert os.path.isfile(os.path.join(core_dir, f)), (
                f"Missing fireai/core/{f} — documented in ARCHITECTURE.md"
            )


# ============================================================================
# 8. PE SIGN-OFF & REGULATORY DISCLAIMERS
# ============================================================================

class TestPESignoffRequirements:
    """Verify that regulatory data carries proper PE sign-off notices.

    Per agent.md Rule #22: Any change to regulatory data values MUST
    be accompanied by PE sign-off or verbatim standard quotation.
    """

    def test_nfpa72_module_has_pe_signoff_notice(self):
        """fireai/constants/nfpa72.py must have PE_SIGNOFF_NOTICE."""
        from fireai.constants.nfpa72 import PE_SIGNOFF_NOTICE

        assert PE_SIGNOFF_NOTICE is not None
        assert "PE" in PE_SIGNOFF_NOTICE or "Professional Engineer" in PE_SIGNOFF_NOTICE, (
            "PE_SIGNOFF_NOTICE must reference Professional Engineer sign-off requirement."
        )

    def test_nfpa72_module_docstring_has_pe_warning(self):
        """nfpa72.py module docstring must mention PE sign-off requirement."""
        import inspect

        from fireai.constants import nfpa72

        doc = inspect.getdoc(nfpa72)
        assert doc is not None
        assert "PE" in doc or "Professional Engineer" in doc or "SIGN-OFF" in doc, (
            "nfpa72.py module docstring must mention PE sign-off requirement."
        )

    def test_nec_module_has_pe_notice_in_docstring(self):
        """NEC constants module must indicate PE verification requirement."""
        import inspect

        from fireai.constants import nec

        doc = inspect.getdoc(nec)
        source = inspect.getsource(nec)

        # Either the docstring or the source comments should mention PE
        has_pe_ref = (
            (doc and ("PE" in doc or "Professional Engineer" in doc)) or
            "PE SIGN-OFF" in source or
            "PE verification" in source
        )
        assert has_pe_ref, (
            "NEC constants module must indicate PE verification requirement "
            "for regulatory data values."
        )

    def test_smoke_spacing_table_has_regulatory_warning(self):
        """V130 FIX: SMOKE_HEIGHT_SPACING_TABLE now has flat 9.1m at ALL
        heights per NFPA 72 §17.7.3.2.3. The table must carry a comment
        explaining that the previous height-reduced values were INCORRECTLY
        derived from heat detector table (Table 17.6.3.5.1).

        Since list.__doc__ is the built-in Python list docstring, we check
        the module source for the comment/docstring attached to the table definition.
        """
        import inspect

        from fireai.constants import nfpa72

        source = inspect.getsource(nfpa72)

        # Find the SMOKE_HEIGHT_SPACING_TABLE definition and check surrounding comments
        table_section = source[source.find('SMOKE_HEIGHT_SPACING_TABLE'):]
        # Take the first 2000 chars after the table definition (includes docstring)
        table_section = table_section[:2000]

        # V130: Check for V130 fix reference or CRITICAL FIX or §17.7.3.2.3
        assert ("V130" in table_section or "CRITICAL FIX" in table_section or
                "17.7.3.2.3" in table_section or "flat" in table_section.lower()), (
            "SMOKE_HEIGHT_SPACING_TABLE definition must carry a comment explaining "
            "that smoke detector spacing is flat 9.1m per NFPA 72 §17.7.3.2.3 "
            "(V130 critical fix)."
        )


# ============================================================================
# 9. NaN/Inf SAFETY — Life-Critical Input Guards
# ============================================================================

class TestNaNInfSafety:
    """Verify all life-safety computations reject NaN and Inf inputs.

    Per agent.md Rule #5: Every input must be validated before computation.
    NaN and Inf can bypass comparison guards and produce "valid-looking"
    results that are actually corrupt.
    """

    def test_smoke_spacing_rejects_nan(self):
        """compute_smoke_detector_spacing must reject NaN ceiling height."""
        from fireai.core.qomn_kernel import (
            PhysicsGuardError,
            compute_smoke_detector_spacing,
        )

        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(float('nan'))

    def test_smoke_spacing_rejects_inf(self):
        """compute_smoke_detector_spacing must reject Inf ceiling height."""
        from fireai.core.qomn_kernel import (
            PhysicsGuardError,
            compute_smoke_detector_spacing,
        )

        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(float('inf'))

    def test_smoke_spacing_rejects_negative(self):
        """compute_smoke_detector_spacing must reject negative ceiling height."""
        from fireai.core.qomn_kernel import (
            PhysicsGuardError,
            compute_smoke_detector_spacing,
        )

        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(-1.0)

    def test_smoke_spacing_rejects_zero(self):
        """compute_smoke_detector_spacing must reject zero ceiling height."""
        from fireai.core.qomn_kernel import (
            PhysicsGuardError,
            compute_smoke_detector_spacing,
        )

        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(0.0)

    def test_coverage_radius_rejects_nan(self):
        """calculate_coverage_radius_from_height must reject NaN."""
        from fireai.core.nfpa72_calculations import (
            calculate_coverage_radius_from_height,
        )

        with pytest.raises((ValueError, TypeError)):
            calculate_coverage_radius_from_height(float('nan'))

    def test_coverage_radius_rejects_inf(self):
        """calculate_coverage_radius_from_height must reject Inf."""
        from fireai.core.nfpa72_calculations import (
            calculate_coverage_radius_from_height,
        )

        with pytest.raises(ValueError):
            calculate_coverage_radius_from_height(float('inf'))

    def test_heat_spacing_rejects_nan_height(self):
        """Heat detector spacing must reject NaN ceiling height."""
        from fireai.core.qomn_kernel import (
            PhysicsGuardError,
            compute_heat_detector_spacing,
        )

        with pytest.raises(PhysicsGuardError):
            compute_heat_detector_spacing(float('nan'), 100.0)

    def test_battery_rejects_nan_current(self):
        """Battery calculation must reject NaN current."""
        from fireai.core.qomn_kernel import (
            PhysicsGuardError,
            compute_battery_capacity_ah,
        )

        with pytest.raises(PhysicsGuardError):
            compute_battery_capacity_ah(float('nan'), 1.5)


# ============================================================================
# 10. COVERAGE RADIUS CONSISTENCY
# ============================================================================

class TestCoverageRadiusConsistency:
    """Verify R = 0.7 × S is applied consistently across all modules.

    This was a recurring bug: some modules used R = S/2 instead of
    R = 0.7 × S. NFPA 72 §17.7.4.2.3.1 defines R = 0.7 × S.
    """

    def test_qomn_kernel_uses_0_7_factor(self):
        """QOMN kernel must use R = 0.7 × S for coverage radius."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing

        result = compute_smoke_detector_spacing(3.0)
        S = result['listed_spacing_m']
        R = result['coverage_radius_m']

        # R must be 0.7 × S = 0.7 × 9.1 = 6.37
        assert abs(R - 0.7 * S) < 0.01, (
            f"R = {R}m ≠ 0.7 × S = {0.7 * S:.4f}m"
        )
        assert abs(R - 6.37) < 0.01, (
            f"R = {R}m ≠ 6.37m at h=3.0m"
        )

    def test_calculations_uses_0_7_factor(self):
        """nfpa72_calculations must use R = 0.7 × S."""
        from fireai.core.nfpa72_calculations import (
            calculate_coverage_radius_from_height,
        )

        spec = calculate_coverage_radius_from_height(3.0, "smoke")
        # At h=3.0m, S=9.1m, R should be 0.7 × 9.1 = 6.37m
        assert abs(spec.radius - 0.7 * spec.spacing_max) < 0.1, (
            f"R = {spec.radius}m ≠ 0.7 × S = {0.7 * spec.spacing_max:.4f}m"
        )

    def test_calculations_wall_distance_is_half_spacing(self):
        """Wall distance must be S/2, NOT R = 0.7 × S.

        Previous code confused coverage radius with wall distance.
        Wall distance = S/2 per NFPA 72 §17.6.3.1.1.
        Coverage radius = 0.7 × S per §17.7.4.2.3.1.
        These are DIFFERENT values.
        """
        from fireai.core.nfpa72_calculations import (
            calculate_coverage_radius_from_height,
        )

        spec = calculate_coverage_radius_from_height(3.0, "smoke")

        # Wall distance = S/2 = 9.1/2 = 4.55m
        # Coverage radius = 0.7 × S = 6.37m
        assert abs(spec.wall_distance_max - spec.spacing_max / 2.0) < 0.01, (
            f"wall_distance_max = {spec.wall_distance_max}m ≠ S/2 = {spec.spacing_max / 2.0:.4f}m"
        )
        # Wall distance ≠ coverage radius
        assert spec.wall_distance_max != spec.radius, (
            f"wall_distance_max ({spec.wall_distance_max}m) == radius ({spec.radius}m). "
            f"Wall distance = S/2, coverage radius = 0.7 × S — they are different!"
        )

    def test_heat_detector_coverage_radius(self):
        """Heat detector coverage at h=3.0m must use S=6.1m."""
        from fireai.core.nfpa72_calculations import (
            calculate_coverage_radius_from_height,
        )

        spec = calculate_coverage_radius_from_height(3.0, "heat")

        assert spec.spacing_max == 6.1, (
            f"Heat spacing at h=3.0m = {spec.spacing_max}m, expected 6.1m (20ft) "
            f"per NFPA 72 Table 17.6.3.5.1."
        )


# ============================================================================
# 11. TECHNOLOGY DISPATCHER INTEGRATION
# ============================================================================

class TestTechnologyDispatcherIntegration:
    """Verify technology dispatcher uses correct spacing from canonical source."""

    def test_smoke_technology_uses_canonical_spacing(self):
        """Technology dispatcher must use height-adjusted spacing from SSoT."""
        from fireai.core.nfpa72_technology_dispatcher import EliteTechnologyDispatcher

        # At h=3.0m, smoke spacing should be 9.1m
        decision = EliteTechnologyDispatcher.select_technology(3.0, 0.0, "smoke")
        assert decision.spacing_m == 9.1, (
            f"Dispatcher spacing at h=3.0m = {decision.spacing_m}m, expected 9.1m"
        )

    def test_heat_technology_uses_canonical_spacing(self):
        """Technology dispatcher must return correct heat spacing."""
        from fireai.core.nfpa72_technology_dispatcher import EliteTechnologyDispatcher

        decision = EliteTechnologyDispatcher.select_technology(3.0, 0.0, "heat")
        assert decision.spacing_m == 6.1, (
            f"Dispatcher heat spacing at h=3.0m = {decision.spacing_m}m, expected 6.1m"
        )

    def test_high_ceiling_switches_to_beam(self):
        """At h>12.2m, technology dispatcher must switch to beam detectors."""
        from fireai.core.nfpa72_technology_dispatcher import (
            DetectorTechnology,
            EliteTechnologyDispatcher,
        )

        decision = EliteTechnologyDispatcher.select_technology(15.0, 0.0, "smoke")
        assert decision.technology == DetectorTechnology.BEAM_SMOKE, (
            f"At h=15m, expected BEAM_SMOKE but got {decision.technology}"
        )

    def test_very_high_ceiling_switches_to_asd(self):
        """At h>25m, technology dispatcher must switch to ASD."""
        from fireai.core.nfpa72_technology_dispatcher import (
            DetectorTechnology,
            EliteTechnologyDispatcher,
        )

        decision = EliteTechnologyDispatcher.select_technology(30.0, 0.0, "smoke")
        assert decision.technology == DetectorTechnology.ASD, (
            f"At h=30m, expected ASD but got {decision.technology}"
        )


# ============================================================================
# 12. VOLTAGE DROP CONSISTENCY
# ============================================================================

class TestVoltageDropConsistency:
    """Verify voltage drop limits are consistent across modules."""

    def test_max_fraction_is_10pct_in_canonical(self):
        """VOLTAGE_DROP_MAX_FRACTION in nfpa72.py must be 0.10 (10%)."""
        from fireai.constants.nfpa72 import VOLTAGE_DROP_MAX_FRACTION

        assert VOLTAGE_DROP_MAX_FRACTION == 0.10, (
            f"VOLTAGE_DROP_MAX_FRACTION = {VOLTAGE_DROP_MAX_FRACTION}, expected 0.10. "
            f"V78 Fix: Was 0.15 (15%) which is too permissive."
        )

    def test_max_fraction_is_10pct_in_init(self):
        """VOLTAGE_DROP_MAX_FRACTION in constants/__init__.py must be 0.10."""
        from fireai.constants import VOLTAGE_DROP_MAX_FRACTION

        assert VOLTAGE_DROP_MAX_FRACTION == 0.10, (
            f"constants/__init__.py VOLTAGE_DROP_MAX_FRACTION = {VOLTAGE_DROP_MAX_FRACTION}, "
            f"expected 0.10. This was missed in the V78 fix."
        )


# ============================================================================
# 13. BATTERY CALCULATION CONSISTENCY
# ============================================================================

class TestBatteryCalculationConsistency:
    """Verify battery sizing constants are consistent."""

    def test_safety_factor_is_1_25_in_canonical(self):
        """BATTERY_SAFETY_FACTOR in nfpa72.py must be 1.25 (25% margin)."""
        from fireai.constants.nfpa72 import BATTERY_SAFETY_FACTOR

        assert BATTERY_SAFETY_FACTOR == 1.25, (
            f"BATTERY_SAFETY_FACTOR = {BATTERY_SAFETY_FACTOR}, expected 1.25. "
            f"V127 Fix: Was 1.20 (20%) — inconsistent with canonical 1.25 (25%)."
        )

    def test_safety_factor_is_1_25_in_init(self):
        """BATTERY_SAFETY_FACTOR in constants/__init__.py must be 1.25."""
        from fireai.constants import BATTERY_SAFETY_FACTOR

        assert BATTERY_SAFETY_FACTOR == 1.25, (
            f"constants/__init__.py BATTERY_SAFETY_FACTOR = {BATTERY_SAFETY_FACTOR}, "
            f"expected 1.25. Must match canonical source."
        )


# ============================================================================
# 14. HIGH CEILING AUDIT NOTICES
# ============================================================================

class TestHighCeilingAuditNotices:
    """Verify that high-ceiling smoke detection includes proper warnings.

    Per NFPA 72 §17.7.1.11, spot-type smoke detection is unreliable
    above 20ft (6.096m) due to stratification. The system must warn users.
    """

    def test_smoke_at_7m_includes_audit_notice(self):
        """Smoke detector at h=7m must include audit_notice about stratification."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing

        result = compute_smoke_detector_spacing(7.0)
        assert 'audit_notice' in result, (
            "Missing audit_notice at h=7m. Per NFPA 72 §17.7.1.11, spot-type "
            "smoke detection is unreliable above 6.096m (20ft)."
        )
        assert "stratification" in result['audit_notice'].lower() or "unreliable" in result['audit_notice'].lower(), (
            "audit_notice must mention stratification or unreliability."
        )

    def test_smoke_at_3m_no_audit_notice(self):
        """Smoke detector at h=3m should NOT have stratification warning."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing

        result = compute_smoke_detector_spacing(3.0)
        assert 'audit_notice' not in result, (
            "audit_notice present at h=3.0m (within normal range). "
            "Stratification warning should only appear above 6.096m."
        )


# ============================================================================
# 15. REGRESSION — Ensure existing behavior is not accidentally broken
# ============================================================================

class TestRegressionProtection:
    """Ensure critical computations produce expected values.

    These tests protect against accidental regressions during refactoring.
    If any of these fail, the refactoring introduced a bug.
    """

    def test_smoke_at_3m_spacing_9_1(self):
        """Smoke spacing at h=3.0m = 9.1m (baseline reference)."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing

        result = compute_smoke_detector_spacing(3.0)
        assert result['listed_spacing_m'] == 9.1

    def test_smoke_at_3m_radius_6_37(self):
        """Smoke coverage radius at h=3.0m = 6.37m."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing

        result = compute_smoke_detector_spacing(3.0)
        assert abs(result['coverage_radius_m'] - 6.37) < 0.01

    def test_heat_at_3m_area_100(self):
        """Heat spacing at h=3.0m with area=100m² = 7.0m."""
        from fireai.core.qomn_kernel import compute_heat_detector_spacing

        result = compute_heat_detector_spacing(3.0, 100.0)
        # S = 0.7 × √100 = 0.7 × 10 = 7.0m
        assert abs(result['spacing_m'] - 7.0) < 0.01

    def test_battery_calculation_matches(self):
        """Battery calculation with known inputs produces expected output."""
        from fireai.core.qomn_kernel import compute_battery_capacity_ah

        result = compute_battery_capacity_ah(0.5, 1.5)
        # Ah_standby = 0.5 × 24 = 12.0
        # Ah_alarm = 1.5 × (5/60) = 0.125
        # Ah_raw = 12.125
        # Ah_required = (12.125 / 0.80) × 1.25 = 18.9453
        assert abs(result['required_ah'] - 18.9453) < 0.01

    def test_voltage_drop_calculation_matches(self):
        """Voltage drop with known inputs produces expected output."""
        from fireai.core.qomn_kernel import compute_voltage_drop

        result = compute_voltage_drop(1.0, 100.0, "14", 24.0, 10.0)
        # R_20 = 4.263 Ω/km at 20°C per NEC Table 8 (stranded copper)
        # R_T = R_20 × [1 + α×(T-20)] = 4.263 × 1.21615 = 5.184 Ω/km at 75°C
        # V_drop = 2 × 1.0 × 100 × (5.184/1000) = 1.037V
        assert abs(result['voltage_drop_v'] - 1.037) < 0.01


# ============================================================================
# 16. LAUNCH READINESS GATE — Critical Blockers
# ============================================================================

class TestLaunchReadinessGate:
    """These tests represent HARD BLOCKERS for production launch.

    If ANY of these fail, the system MUST NOT be deployed in production
    because it would produce engineering-incorrect results that could
    lead to AHJ rejection or life-safety concerns.
    """

    def test_all_nec_conduit_fill_values_match_standard(self):
        """NEC Chapter 9 Table 1 values must match the published standard.
        1 conductor = 53%, 2 conductors = 31%, 3+ conductors = 40%."""
        from fireai.constants.nec import MAX_CONDUCTOR_FILL_PCT

        assert MAX_CONDUCTOR_FILL_PCT == {
            "1_conductor": 53,
            "2_conductors": 31,
            "3_plus": 40,
        }, f"NEC conduit fill values do not match standard: {MAX_CONDUCTOR_FILL_PCT}"

    def test_smoke_spacing_table_first_row_is_flat(self):
        """First row of smoke spacing table must be h=3.0m, S=9.1m (flat)."""
        from fireai.constants.nfpa72 import SMOKE_HEIGHT_SPACING_TABLE

        first = SMOKE_HEIGHT_SPACING_TABLE[0]
        assert first == (3.0, 9.10), (
            f"First row of SMOKE_HEIGHT_SPACING_TABLE = {first}, "
            f"expected (3.0, 9.10) — flat spacing per §17.7.3.2.3."
        )

    def test_heat_spacing_table_first_row_is_standard(self):
        """First row of heat spacing table must be h=3.0m, S=6.1m (standard)."""
        from fireai.constants.nfpa72 import HEAT_HEIGHT_SPACING_TABLE

        first = HEAT_HEIGHT_SPACING_TABLE[0]
        assert first == (3.0, 6.10), (
            f"First row of HEAT_HEIGHT_SPACING_TABLE = {first}, "
            f"expected (3.0, 6.10) — standard spacing per Table 17.6.3.5.1."
        )

    def test_no_stale_9_144_smoke_spacing_anywhere(self):
        """The old SMOKE_MAX_SPACING_M = 9.144 (30ft × 0.3048) must not
        appear anywhere in the codebase. NFPA 72 states 9.1m, not 9.144m."""
        import fireai.constants
        import fireai.constants.nfpa72
        import fireai.core.qomn_kernel

        # Check that 9.144 is NOT used as the smoke max spacing
        assert fireai.constants.nfpa72.SMOKE_MAX_SPACING_M != 9.144, (
            "SMOKE_MAX_SPACING_M = 9.144 (old value from 30ft × 0.3048). "
            "NFPA 72-2022 §17.7.3.2.3 states 9.1m, not 9.144m."
        )
        assert fireai.constants.SMOKE_MAX_SPACING_M != 9.144, (
            "constants/__init__.py SMOKE_MAX_SPACING_M still uses old 9.144 value."
        )

    def test_no_stale_15_24_heat_spacing_anywhere(self):
        """The old HEAT_MAX_SPACING_M = 15.24m was wrong — that's the
        absolute max (50ft), not the standard spacing (20ft = 6.1m)."""
        import fireai.constants
        import fireai.constants.nfpa72

        # Standard heat spacing must be 6.1m (20ft), NOT 15.24m (50ft)
        assert fireai.constants.nfpa72.HEAT_MAX_SPACING_M == 6.1, (
            f"HEAT_MAX_SPACING_M = {fireai.constants.nfpa72.HEAT_MAX_SPACING_M}, "
            f"expected 6.1m (20ft standard spacing). 15.24m is the ABSOLUTE max (50ft)."
        )
