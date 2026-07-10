"""
test_version.py — Tests for fireai/version.py.

Verifies version constants, header generation, and consistency checks.
"""
from __future__ import annotations

import platform
import sys

from fireai.version import (
    ATEX_EDITION,
    FIREAI_VERSION,
    FIREAI_VERSION_FULL,
    IEC_HAC_EDITION,
    MAJOR,
    MINOR,
    NEC_EDITION,
    NFPA_EDITION,
    PATCH,
    __package_version__,
    assert_version_consistency,
    build_version_header,
)


class TestVersionConstants:
    """Package version metadata."""

    def test_major_minor_patch_are_ints(self):
        assert isinstance(MAJOR, int)
        assert isinstance(MINOR, int)
        assert isinstance(PATCH, int)
        assert MAJOR >= 0
        assert MINOR >= 0
        assert PATCH >= 0

    def test_fireai_version_format(self):
        assert FIREAI_VERSION.startswith("V")
        assert f"{MAJOR}.{MINOR}.{PATCH}" in FIREAI_VERSION

    def test_fireai_version_full_format(self):
        assert FIREAI_VERSION_FULL.startswith("FireAI ")
        assert FIREAI_VERSION in FIREAI_VERSION_FULL

    def test_package_version_string(self):
        assert __package_version__ == "1.0.0"

    def test_edition_strings_non_empty(self):
        assert NFPA_EDITION.startswith("NFPA")
        assert IEC_HAC_EDITION.startswith("IEC")
        assert NEC_EDITION.startswith("NFPA")
        assert ATEX_EDITION.startswith("ATEX")


class TestBuildVersionHeader:
    """Version header used in audit reports and API responses."""

    def test_header_contains_version(self):
        header = build_version_header()
        assert header["fireai_version"] == FIREAI_VERSION_FULL

    def test_header_contains_standards(self):
        header = build_version_header()
        assert header["nfpa_edition"] == NFPA_EDITION
        assert header["iec_hac_edition"] == IEC_HAC_EDITION
        assert header["nec_edition"] == NEC_EDITION
        assert header["atex_edition"] == ATEX_EDITION

    def test_header_contains_runtime(self):
        header = build_version_header()
        assert header["python_version"] == sys.version.split()[0]
        assert header["platform"] == platform.system()

    def test_header_keys_are_strings(self):
        header = build_version_header()
        for key, value in header.items():
            assert isinstance(key, str)
            assert isinstance(value, str)


class TestVersionConsistency:
    """Runtime consistency checks."""

    def test_assert_version_consistency_passes(self):
        """No conflicting versions declared → should not raise."""
        assert_version_consistency()
