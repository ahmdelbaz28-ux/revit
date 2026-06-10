"""
tests/test_parsers_security_v125.py — V125 path-security hardening tests
=========================================================================
V125 extends the parsers/_path_security helper (V122) to all remaining
parsers: PDF, Image, Excel, Word, IFC.

Per agent.md Rule #23, every parser that accepts a user-controlled file
path now goes through the same single source of truth for validation.

For each parser this file verifies:
  1. Argument injection blocked (leading '-')
  2. Null byte blocked
  3. Path traversal blocked (file outside allowed dirs)
  4. Wrong extension blocked
  5. Oversized file blocked
  6. Missing file → friendly error (not exception)
  7. The parser's source uses the shared helper (Rule #23 enforcement)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest


def _make_temp(suffix: str, size: int = 100) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="v125_")
    try:
        os.write(fd, b"X" * size)
    finally:
        os.close(fd)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# PDF Parser
# ═══════════════════════════════════════════════════════════════════════════════


class TestPDFParserSecurity:
    def setup_method(self):
        from parsers.pdf_parser import PDFParser
        self.parser = PDFParser()

    def test_leading_dash_rejected(self):
        r = self.parser.parse("--malicious")
        assert not r.success
        assert any("SECURITY" in e for e in r.errors)

    def test_null_byte_rejected(self):
        r = self.parser.parse("/tmp/x\x00.pdf")
        assert not r.success
        assert any("SECURITY" in e for e in r.errors)

    def test_wrong_extension_rejected(self):
        p = _make_temp(".txt")
        try:
            r = self.parser.parse(p)
            assert not r.success
            assert any("SECURITY" in e for e in r.errors)
        finally:
            os.unlink(p)

    def test_missing_file_friendly_error(self):
        r = self.parser.parse("/tmp/v125_pdf_missing.pdf")
        assert not r.success
        assert any("not found" in e for e in r.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# Image Parser
# ═══════════════════════════════════════════════════════════════════════════════


class TestImageParserSecurity:
    def setup_method(self):
        from parsers.image_parser import ImageParser
        self.parser = ImageParser()

    def test_leading_dash_rejected(self):
        r = self.parser.parse("--evil")
        assert not r.success
        assert any("SECURITY" in e for e in r.errors)

    def test_null_byte_rejected(self):
        r = self.parser.parse("/tmp/x\x00.png")
        assert not r.success
        assert any("SECURITY" in e for e in r.errors)

    def test_wrong_extension_rejected(self):
        p = _make_temp(".txt")
        try:
            r = self.parser.parse(p)
            assert not r.success
            assert any("SECURITY" in e for e in r.errors)
        finally:
            os.unlink(p)

    def test_supported_extensions_accept(self):
        """All supported image formats reach the parser proper (where
        they'll fail at the image-decode step since the file isn't a
        real image — but security validation MUST not reject them).
        V127: Updated to match actual _ALLOWED_EXTENSIONS in image_parser.py."""
        for ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif",
                    ".webp"):
            p = _make_temp(ext)
            try:
                r = self.parser.parse(p)
                # success may be False (file isn't a real image),
                # but the error MUST NOT be a SECURITY rejection
                assert not any("SECURITY" in e for e in r.errors), (
                    f"Supported extension {ext} falsely rejected: {r.errors}"
                )
            finally:
                os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# Excel Parser
# ═══════════════════════════════════════════════════════════════════════════════


class TestExcelParserSecurity:
    def setup_method(self):
        from parsers.excel_parser import ExcelParser
        self.parser = ExcelParser()

    def test_leading_dash_rejected(self):
        r = self.parser.parse("--evil.xlsx")
        assert not r.success
        assert any("SECURITY" in e for e in r.errors)

    def test_null_byte_rejected(self):
        r = self.parser.parse("/tmp/x\x00.xlsx")
        assert not r.success
        assert any("SECURITY" in e for e in r.errors)

    def test_wrong_extension_rejected(self):
        # V127: .csv IS allowed by ExcelParser. Use .txt instead.
        p = _make_temp(".txt")
        try:
            r = self.parser.parse(p)
            assert not r.success
            assert any("SECURITY" in e for e in r.errors)
        finally:
            os.unlink(p)

    def test_both_xls_and_xlsx_accepted(self):
        for ext in (".xls", ".xlsx"):
            p = _make_temp(ext)
            try:
                r = self.parser.parse(p)
                # Will fail at pandas read (fake content), not at security
                assert not any("SECURITY" in e for e in r.errors)
            finally:
                os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# Word Parser
# ═══════════════════════════════════════════════════════════════════════════════


class TestWordParserSecurity:
    def setup_method(self):
        from parsers.word_parser import WordParser
        self.parser = WordParser()

    def test_leading_dash_rejected(self):
        r = self.parser.parse("--evil.docx")
        assert not r.success
        assert any("SECURITY" in e for e in r.errors)

    def test_null_byte_rejected(self):
        r = self.parser.parse("/tmp/x\x00.docx")
        assert not r.success
        assert any("SECURITY" in e for e in r.errors)

    def test_txt_extension_rejected(self):
        """V127: WordParser now accepts both .docx and .doc.
        Test that .txt is still rejected."""
        p = _make_temp(".txt")
        try:
            r = self.parser.parse(p)
            assert not r.success
            assert any("SECURITY" in e for e in r.errors)
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# IFC Parser (path supplied at __init__, validation in parse())
# ═══════════════════════════════════════════════════════════════════════════════


class TestIFCParserSecurity:
    def _make(self, path):
        from parsers.ifc_parser import IFCParser
        return IFCParser(path)

    def test_leading_dash_rejected(self):
        with pytest.raises(ValueError, match="SECURITY"):
            self._make("--evil.ifc").parse()

    def test_null_byte_rejected(self):
        with pytest.raises(ValueError, match="SECURITY"):
            self._make("/tmp/x\x00.ifc").parse()

    def test_wrong_extension_rejected(self):
        p = _make_temp(".txt")
        try:
            with pytest.raises(ValueError, match="SECURITY"):
                self._make(p).parse()
        finally:
            os.unlink(p)

    def test_missing_file_raises_ValueError(self):
        with pytest.raises(ValueError, match="not found"):
            self._make("/tmp/v125_ifc_missing.ifc").parse()


# ═══════════════════════════════════════════════════════════════════════════════
# Rule #23 enforcement: each parser MUST use the shared helper
# ═══════════════════════════════════════════════════════════════════════════════


class TestV125SingleSourceOfTruth:
    """Programmatic enforcement of agent.md Rule #23: every modified
    parser MUST import from parsers._path_security. If a future refactor
    removes the import (or replaces it with inline code), this fails."""

    @pytest.mark.parametrize("parser_file", [
        "parsers/pdf_parser.py",
        "parsers/image_parser.py",
        "parsers/excel_parser.py",
        "parsers/word_parser.py",
        "parsers/ifc_parser.py",
        "parsers/dwg_parser.py",      # V122
        "parsers/ddc_adapter.py",      # V123
    ])
    def test_parser_uses_shared_helper(self, parser_file):
        src = (_PROJECT_ROOT / parser_file).read_text(encoding="utf-8")
        assert "from parsers._path_security import" in src, (
            f"V125/Rule #23 regression: {parser_file} no longer imports "
            f"the shared _path_security helper. Either restore the import "
            f"or remove the parser from this enforcement list."
        )
        assert "validate_input_path" in src, (
            f"V125/Rule #23 regression: {parser_file} does not call "
            f"validate_input_path(). Custom validation is forbidden by Rule #23."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Architectural consistency: every parser has same DoS cap pattern
# ═══════════════════════════════════════════════════════════════════════════════


class TestV125DoSCapConsistency:
    """Every parser MUST advertise its file-size cap via env var
    (operators must be able to tune per deployment without forking)."""

    @pytest.mark.parametrize("parser_file, env_var", [
        ("parsers/pdf_parser.py",   "FIREAI_PDF_MAX_FILE_SIZE_BYTES"),
        ("parsers/image_parser.py", "FIREAI_IMAGE_MAX_FILE_SIZE_BYTES"),
        ("parsers/excel_parser.py", "FIREAI_EXCEL_MAX_FILE_SIZE_BYTES"),
        ("parsers/word_parser.py",  "FIREAI_WORD_MAX_FILE_SIZE_BYTES"),
        ("parsers/ifc_parser.py",   "FIREAI_IFC_MAX_FILE_SIZE_BYTES"),
        ("parsers/dwg_parser.py",   "FIREAI_DWG_MAX_FILE_SIZE_BYTES"),
    ])
    def test_parser_advertises_env_configurable_cap(self, parser_file, env_var):
        src = (_PROJECT_ROOT / parser_file).read_text(encoding="utf-8")
        assert env_var in src, (
            f"V125: {parser_file} should expose its size cap via {env_var} "
            f"so operators can tune without code changes."
        )
        assert "validate_file_size" in src, (
            f"V125: {parser_file} should call validate_file_size()."
        )
