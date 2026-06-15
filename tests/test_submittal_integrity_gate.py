"""
tests/test_submittal_integrity_gate.py
========================================
Comprehensive test suite for fireai/core/submittal_integrity_gate.py

SAFETY CRITICAL: TOCTOU (CWE-367) detection — file modified between
pre-calculation and final submittal.

References: CWE-367, NFPA 72-2022 Documentation Integrity
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import tempfile

import pytest

import fireai.core.submittal_integrity_gate as _sig_mod


# Force fallback to IntegrityCheckResult (not DecisionProvenance)
@pytest.fixture(autouse=True)
def _disable_provenance():
    originals = {}
    for attr in ("DecisionProvenance", "RuleApplied", "Violation",
                "ConfidenceScore", "ConfidenceLevel"):
        originals[attr] = getattr(_sig_mod, attr, None)
        setattr(_sig_mod, attr, None)
    yield
    for attr, val in originals.items():
        setattr(_sig_mod, attr, val)

from fireai.core.submittal_integrity_gate import (
    HashRecord,
    IntegrityCheckResult,
    SubmittalIntegrityGate,
)


@pytest.fixture
def gate() -> SubmittalIntegrityGate:
    return SubmittalIntegrityGate()


@pytest.fixture
def temp_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dxf", delete=False) as f:
        f.write("TEST DXF CONTENT")
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def temp_file_2():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dxf", delete=False) as f:
        f.write("SECOND FILE CONTENT")
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# HashRecord & IntegrityCheckResult
# ─────────────────────────────────────────────────────────────────────────────


class TestHashRecord:

    def test_creation(self):
        r = HashRecord("test.dxf", "abc123", 1000.0, "pre_calculation")
        assert r.file_path == "test.dxf"
        assert r.sha256_hex == "abc123"

    def test_frozen(self):
        r = HashRecord("test.dxf", "abc123", 1000.0, "pre_calculation")
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.sha256_hex = "changed"


class TestIntegrityCheckResult:

    def test_match_result(self):
        r = IntegrityCheckResult("test.dxf", "abc", "abc", True)
        assert r.match is True
        assert len(r.violations) == 0

    def test_mismatch_result(self):
        violations = [{"severity": "CRITICAL"}]
        r = IntegrityCheckResult("test.dxf", "abc", "def", False, violations)
        assert r.match is False


# ─────────────────────────────────────────────────────────────────────────────
# record_hash
# ─────────────────────────────────────────────────────────────────────────────


class TestRecordHash:

    def test_returns_record(self, gate, temp_file):
        record = gate.record_hash(temp_file, "pre_calculation")
        assert isinstance(record, HashRecord)
        assert record.file_path == temp_file
        assert record.phase == "pre_calculation"
        assert len(record.sha256_hex) == 64

    def test_deterministic(self, gate, temp_file):
        r1 = gate.record_hash(temp_file, "pre_calculation")
        r2 = gate.record_hash(temp_file, "post_draft")
        assert r1.sha256_hex == r2.sha256_hex

    def test_nonexistent_file(self, gate):
        with pytest.raises(FileNotFoundError):
            gate.record_hash("/nonexistent/file.dxf", "pre_calculation")

    def test_multiple_phases(self, gate, temp_file):
        gate.record_hash(temp_file, "pre_calculation")
        gate.record_hash(temp_file, "post_draft")
        history = gate.get_hash_history(temp_file)
        assert len(history) == 2


# ─────────────────────────────────────────────────────────────────────────────
# verify_integrity — Match
# ─────────────────────────────────────────────────────────────────────────────


class TestVerifyIntegrityMatch:

    def test_unchanged_file_matches(self, gate, temp_file):
        pre = gate.record_hash(temp_file, "pre_calculation")
        result = gate.verify_integrity(temp_file, pre.sha256_hex)
        assert isinstance(result, IntegrityCheckResult)
        assert result.match is True
        assert len(result.violations) == 0

    def test_correct_sha256(self, gate, temp_file):
        pre = gate.record_hash(temp_file, "pre_calculation")
        sha256 = hashlib.sha256()
        with open(temp_file, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)
        assert pre.sha256_hex == sha256.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# verify_integrity — Mismatch / TOCTOU
# ─────────────────────────────────────────────────────────────────────────────


class TestVerifyIntegrityMismatch:

    def test_modified_file_detected(self, gate, temp_file):
        pre = gate.record_hash(temp_file, "pre_calculation")
        with open(temp_file, "w") as f:
            f.write("MODIFIED CONTENT — TOCTOU ATTACK")
        result = gate.verify_integrity(temp_file, pre.sha256_hex)
        assert isinstance(result, IntegrityCheckResult)
        assert result.match is False
        assert len(result.violations) > 0
        assert result.violations[0]["severity"] == "CRITICAL"

    def test_mismatch_cites_cwe367(self, gate, temp_file):
        pre = gate.record_hash(temp_file, "pre_calculation")
        with open(temp_file, "w") as f:
            f.write("MODIFIED CONTENT")
        result = gate.verify_integrity(temp_file, pre.sha256_hex)
        assert isinstance(result, IntegrityCheckResult)
        assert "CWE-367" in result.violations[0]["citation"]

    def test_wrong_hash_detected(self, gate, temp_file):
        result = gate.verify_integrity(temp_file, "0" * 64)
        assert isinstance(result, IntegrityCheckResult)
        assert result.match is False

    def test_file_deleted_after_pre_check(self, gate, temp_file):
        pre = gate.record_hash(temp_file, "pre_calculation")
        os.unlink(temp_file)
        with pytest.raises(FileNotFoundError):
            gate.verify_integrity(temp_file, pre.sha256_hex)


# ─────────────────────────────────────────────────────────────────────────────
# get_hash_history & clear
# ─────────────────────────────────────────────────────────────────────────────


class TestHashHistory:

    def test_empty_history(self, gate):
        assert gate.get_hash_history("nonexistent.dxf") == []

    def test_history_after_record(self, gate, temp_file):
        gate.record_hash(temp_file, "pre_calculation")
        assert len(gate.get_hash_history(temp_file)) == 1

    def test_separate_files(self, gate, temp_file, temp_file_2):
        gate.record_hash(temp_file, "pre_calculation")
        gate.record_hash(temp_file_2, "pre_calculation")
        assert len(gate.get_hash_history(temp_file)) == 1
        assert len(gate.get_hash_history(temp_file_2)) == 1


class TestClear:

    def test_clear_removes_all(self, gate, temp_file):
        gate.record_hash(temp_file, "pre_calculation")
        gate.clear()
        assert gate.get_hash_history(temp_file) == []

    def test_clear_empty_ok(self, gate):
        gate.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Integration
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrationPipeline:

    def test_full_pipeline_unchanged(self, gate, temp_file):
        pre = gate.record_hash(temp_file, "pre_calculation")
        result = gate.verify_integrity(temp_file, pre.sha256_hex)
        assert result.match is True

    def test_full_pipeline_tampered(self, gate, temp_file):
        pre = gate.record_hash(temp_file, "pre_calculation")
        with open(temp_file, "a") as f:
            f.write("\nTAMPERED")
        result = gate.verify_integrity(temp_file, pre.sha256_hex)
        assert result.match is False

    def test_multiple_files(self, gate, temp_file, temp_file_2):
        pre1 = gate.record_hash(temp_file, "pre_calculation")
        pre2 = gate.record_hash(temp_file_2, "pre_calculation")
        r1 = gate.verify_integrity(temp_file, pre1.sha256_hex)
        r2 = gate.verify_integrity(temp_file_2, pre2.sha256_hex)
        assert r1.match is True
        assert r2.match is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
