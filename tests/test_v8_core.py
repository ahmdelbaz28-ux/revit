"""
test_v8_core.py — End-to-end test suite for the V8 core
=========================================================
Run with:
    pytest -v tests/test_v8_core.py
or:
    python -m unittest tests.test_v8_core
or:
    python tests/test_v8_core.py
"""
from __future__ import annotations

import os
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add src to path for direct execution
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from v8_core.code_authority import (
    CodeAuthority, CodeConstant, seed_nfpa72_2019_minimum,
    sign_for_dev, CodeAuthorityError, FPEAuthorityError,
)
from v8_core.decision_provenance import (
    ConfidenceLevel, ConfidenceScore, DecisionProvenance,
    RuleApplied, ReviewStatus,
)
from v8_core.safety_optimizer import Device, optimize_panels_safety_first
from v8_core.pattern_library import (
    PatternLibrary, PatternLibraryError, GeometricFeatures,
)
from v8_core.smoke_estimator import ZoneSmokeEstimator, EstimatorInputs, LOCKED_DISCLAIMER


def _tmpdb(suffix=".db") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    os.unlink(path)  # let CodeAuthority create it
    return path


# ---------------------------------------------------------------------------
# Code Authority
# ---------------------------------------------------------------------------

class TestCodeAuthority(unittest.TestCase):

    def setUp(self):
        self.db = _tmpdb()
        self.auth = CodeAuthority(self.db)
        seed_nfpa72_2019_minimum(self.auth)
        self.auth.set_jurisdiction("US.GENERIC", "NFPA72", "2019", "2019-01-01")

    def test_resolves_seeded_constant(self):
        c = self.auth.get_constant("NFPA72.17.6.3.1.smoke_max_spacing",
                                   "US.GENERIC", "2026-01-01")
        self.assertEqual(c.value_unit, "m")
        self.assertAlmostEqual(c.value_numeric, 9.1)
        self.assertIn("Smoke detectors", c.citation_text)

    def test_unknown_jurisdiction_refuses(self):
        with self.assertRaises(CodeAuthorityError):
            self.auth.get_constant("NFPA72.17.6.3.1.smoke_max_spacing",
                                   "US.UNKNOWN", "2026-01-01")

    def test_append_only_no_delete(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.auth._conn.execute("DELETE FROM code_constants")

    def test_append_only_no_update(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.auth._conn.execute(
                "UPDATE code_constants SET value_numeric = 99.9"
            )

    def test_invalid_signature_rejected(self):
        c = CodeConstant(
            constant_id="TEST.fake", code_family="NFPA72", edition="2019",
            section="0.0", value_numeric=1.0, value_unit="m",
            value_categorical=None, citation_text="fake", source_pdf_hash="0" * 64,
            source_page=0, effective_date="2019-01-01",
            fpe_reviewer="FPE-DEV-0001", fpe_signature="deadbeef",
            added_at="2026-01-01T00:00:00Z",
        )
        with self.assertRaises(FPEAuthorityError):
            self.auth.add_constant(c)


# ---------------------------------------------------------------------------
# Decision Provenance
# ---------------------------------------------------------------------------

class TestDecisionProvenance(unittest.TestCase):

    def test_valid_dp_signs_and_verifies(self):
        rule = RuleApplied("NFPA72-2019 §17.6.3.1",
                           "NFPA72.17.6.3.1.smoke_max_spacing", 9.1, "m")
        conf = ConfidenceScore(0.9, 1.0, 0.9, ConfidenceLevel.HIGH)
        dp = DecisionProvenance.new(
            decision_type="test", value={"x": 1},
            inputs={"drawing_hash": "sha256:x", "jurisdiction": "US.GENERIC",
                    "code_versions": {"NFPA72": "2019"}},
            rules_applied=[rule], algorithm={"name": "t", "version": "1",
                                              "parameters": {}},
            confidence=conf, selected_because="test",
        )
        dp.validate()
        dp.sign_engine()
        self.assertTrue(dp.verify_engine_signature())

    def test_refuse_with_value_is_invalid(self):
        rule = RuleApplied("x", "x", 0, "m")
        conf = ConfidenceScore(0.0, 0.0, 0.0, ConfidenceLevel.REFUSE)
        dp = DecisionProvenance.new(
            decision_type="t", value={"x": 1},
            inputs={"drawing_hash": "x", "jurisdiction": "x", "code_versions": {}},
            rules_applied=[rule],
            algorithm={"name": "t", "version": "1", "parameters": {}},
            confidence=conf, selected_because="t",
        )
        with self.assertRaises(ValueError):
            dp.validate()

    def test_no_rules_no_violations_is_invalid(self):
        conf = ConfidenceScore(0.9, 1.0, 0.9, ConfidenceLevel.HIGH)
        dp = DecisionProvenance.new(
            decision_type="t", value={"x": 1},
            inputs={"drawing_hash": "x", "jurisdiction": "x", "code_versions": {}},
            rules_applied=[],
            algorithm={"name": "t", "version": "1", "parameters": {}},
            confidence=conf, selected_because="t",
        )
        with self.assertRaises(ValueError):
            dp.validate()


# ---------------------------------------------------------------------------
# Safety Optimizer
# ---------------------------------------------------------------------------

class TestSafetyOptimizer(unittest.TestCase):

    def setUp(self):
        self.db = _tmpdb()
        self.auth = CodeAuthority(self.db)
        seed_nfpa72_2019_minimum(self.auth)
        self.auth.set_jurisdiction("US.GENERIC", "NFPA72", "2019", "2019-01-01")

    def test_feasible_returns_dp_with_alternatives(self):
        devices = [
            Device("D1", 0, 0), Device("D2", 6, 0),
            Device("D3", 0, 6), Device("D4", 6, 6),
        ]
        dp = optimize_panels_safety_first(
            devices, k=1, jurisdiction_id="US.GENERIC",
            code_authority=self.auth, project_date="2026-01-01",
            grid_step=1.0,
        )
        self.assertIsNotNone(dp.value)
        self.assertIn("panels", dp.value)
        self.assertGreaterEqual(dp.feasible_alternatives_considered, 1)
        self.assertIn(dp.confidence.overall,
                      {ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM})
        self.assertTrue(dp.verify_engine_signature())

    def test_infeasible_refuses_not_silently_succeeds(self):
        # 50m apart, way beyond 9.1m spacing with one panel — no feasible solution.
        devices = [Device("D1", 0, 0), Device("D2", 50, 0)]
        dp = optimize_panels_safety_first(
            devices, k=1, jurisdiction_id="US.GENERIC",
            code_authority=self.auth, project_date="2026-01-01",
            grid_step=2.0,
        )
        self.assertEqual(dp.confidence.overall, ConfidenceLevel.REFUSE)
        self.assertIsNone(dp.value)
        self.assertGreaterEqual(len(dp.violations_detected), 1)

    def test_determinism_same_input_same_output(self):
        devices = [Device("D1", 0, 0), Device("D2", 6, 0),
                   Device("D3", 0, 6), Device("D4", 6, 6)]
        dp1 = optimize_panels_safety_first(
            devices, k=1, jurisdiction_id="US.GENERIC",
            code_authority=self.auth, project_date="2026-01-01", grid_step=1.0,
        )
        dp2 = optimize_panels_safety_first(
            devices, k=1, jurisdiction_id="US.GENERIC",
            code_authority=self.auth, project_date="2026-01-01", grid_step=1.0,
        )
        self.assertEqual(dp1.value["panels"], dp2.value["panels"])


# ---------------------------------------------------------------------------
# Pattern Library
# ---------------------------------------------------------------------------

class TestPatternLibrary(unittest.TestCase):

    def setUp(self):
        self.db = _tmpdb()
        self.lib = PatternLibrary(self.db)
        self.feats = GeometricFeatures(
            room_count=4, total_area_m2=120.0, aspect_ratio_bin="square",
            has_obstructions=False, occupancy_class="Business",
            ceiling_height_bin="3-6m",
        )

    def test_pending_not_retrievable(self):
        self.lib.submit_for_review(self.feats, {"panels": [[3, 3]]},
                                    "sha256:x", "designer-1")
        self.assertEqual(self.lib.search_similar(self.feats), [])

    def test_approval_makes_retrievable(self):
        pid = self.lib.submit_for_review(self.feats, {"panels": [[3, 3]]},
                                          "sha256:x", "designer-1")
        self.lib.approve(pid, "FPE-DEV-0001")
        hits = self.lib.search_similar(self.feats)
        self.assertEqual(len(hits), 1)
        self.assertIn("disclaimer", hits[0])
        self.assertEqual(hits[0]["approved_by_fpe"], "FPE-DEV-0001")

    def test_rejected_cannot_be_approved_later(self):
        pid = self.lib.submit_for_review(self.feats, {"panels": []},
                                          "sha256:x", "designer-1")
        self.lib.reject(pid, "FPE-DEV-0001", "violation of §17.6.3.1 spacing")
        with self.assertRaises(PatternLibraryError):
            self.lib.approve(pid, "FPE-DEV-0001")

    def test_rejection_requires_reason(self):
        pid = self.lib.submit_for_review(self.feats, {"panels": []},
                                          "sha256:x", "designer-1")
        with self.assertRaises(PatternLibraryError):
            self.lib.reject(pid, "FPE-DEV-0001", "no")

    def test_no_auto_learn_method_exists(self):
        # Hard contract: there is NO public auto-learn method.
        for name in dir(self.lib):
            self.assertFalse("auto_learn" in name.lower(),
                             f"forbidden method exposed: {name}")
            self.assertFalse("self_learn" in name.lower(),
                             f"forbidden method exposed: {name}")


# ---------------------------------------------------------------------------
# Smoke Estimator
# ---------------------------------------------------------------------------

class TestSmokeEstimator(unittest.TestCase):

    def test_output_carries_locked_disclaimer(self):
        est = ZoneSmokeEstimator()
        dp = est.estimate(EstimatorInputs(300.0, 4.0, 3.8, 500.0))
        self.assertEqual(dp.value["disclaimer"], LOCKED_DISCLAIMER)
        self.assertFalse(dp.value["claims_nfpa92"])
        self.assertFalse(dp.value["validated_against_cfd"])
        self.assertEqual(dp.value["error_band_pct"], 50)

    def test_invalid_inputs_refuse(self):
        est = ZoneSmokeEstimator()
        dp = est.estimate(EstimatorInputs(300.0, 4.0, 5.0, 500.0))  # detector above ceiling
        self.assertEqual(dp.confidence.overall, ConfidenceLevel.REFUSE)
        self.assertIsNone(dp.value)

    def test_confidence_capped_at_medium(self):
        est = ZoneSmokeEstimator()
        dp = est.estimate(EstimatorInputs(300.0, 4.0, 3.8, 500.0))
        # rule_coverage = 0 (we make no NFPA 92 claim)
        self.assertEqual(dp.confidence.rule_coverage, 0.0)
        self.assertNotEqual(dp.confidence.overall, ConfidenceLevel.HIGH)


# ---------------------------------------------------------------------------
# Linter (smoke test — runs against our own src/)
# ---------------------------------------------------------------------------

class TestLinter(unittest.TestCase):
    def test_linter_passes_on_clean_v8_core(self):
        # Import the linter and run it against the v8_core sources.
        from v8_core import linter_rules
        rc = linter_rules.run([str(ROOT / "src" / "v8_core")])
        self.assertEqual(rc, 0, "Linter should pass on clean V8 core")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
