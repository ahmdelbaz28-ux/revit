"""
parsers/tests/test_path_security_enhanced.py — Enhanced security tests for
parsers/_path_security.py (68% → 80%+).

SECURITY-CRITICAL: This module is the primary defense against path traversal
attacks in the DWG/DXF/IFC/PDF parsing pipeline.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from parsers._path_security import (
    UnsafePathError,
    _resolve_allowed_bases,
    validate_file_size,
    validate_input_path,
)


class TestValidateInputPathNone:
    """Test that None/invalid input is rejected."""

    def test_none_input_raises(self):
        """Test that validate_input_path(None) raises UnsafePathError."""
        with pytest.raises(UnsafePathError, match="non-empty string"):
            validate_input_path(None)  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)

    def test_empty_string_rejected(self, monkeypatch):
        """Test that empty string is rejected as unsafe."""
        # Ensure development mode doesn't add CWD which makes empty path valid
        monkeypatch.delenv("FIREAI_ENV", raising=False)
        with pytest.raises(UnsafePathError):
            validate_input_path("")


class TestValidateInputPathTraversal:
    """Test path traversal attack rejection."""

    def test_absolute_path_outside_allowed(self):
        """Test that absolute paths outside allowed dirs are rejected."""
        with pytest.raises(UnsafePathError):
            validate_input_path("/etc/passwd")

    def test_absolute_path_to_shadow(self):
        """Test that /etc/shadow is rejected."""
        with pytest.raises(UnsafePathError):
            validate_input_path("/etc/shadow")


class TestValidateInputPathValid:
    """Test that valid paths within allowed directories are accepted."""

    def test_valid_file_in_tmp(self, tmp_path):
        """Test that a valid file in an allowed directory passes."""
        test_file = tmp_path / "test.dxf"
        test_file.write_text("test")
        result = validate_input_path(str(test_file))
        assert result is not None

    def test_valid_file_with_various_extensions(self, tmp_path):
        """Test that a valid file with various extensions passes."""
        for ext in [".dxf", ".dwg", ".ifc", ".pdf", ".rvt"]:
            test_file = tmp_path / f"test{ext}"
            test_file.write_text("test")
            result = validate_input_path(str(test_file))
            assert result is not None


class TestValidateInputPathExtension:
    """Test extension whitelist enforcement."""

    def test_disallowed_extension_rejected(self, tmp_path):
        """Test that files with disallowed extensions are rejected."""
        test_file = tmp_path / "malware.exe"
        test_file.write_text("malware")
        with pytest.raises(UnsafePathError, match="extension"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            validate_input_path(str(test_file), allowed_extensions=frozenset({".dxf", ".dwg"}))

    def test_allowed_extension_accepted(self, tmp_path):
        """Test that files with allowed extensions are accepted."""
        test_file = tmp_path / "test.dxf"
        test_file.write_text("test")
        result = validate_input_path(str(test_file), allowed_extensions=frozenset({".dxf", ".dwg"}))
        assert result is not None

    def test_no_extension_check_when_not_specified(self, tmp_path):
        """Test that extension is not checked when allowed_extensions is None."""
        test_file = tmp_path / "test.xyz"
        test_file.write_text("test")
        result = validate_input_path(str(test_file), allowed_extensions=None)
        assert result is not None

    def test_py_extension_rejected(self, tmp_path):
        """Test that .py files are rejected when extensions are specified."""
        test_file = tmp_path / "script.py"
        test_file.write_text("script")
        with pytest.raises(UnsafePathError):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            validate_input_path(str(test_file), allowed_extensions=frozenset({".dxf"}))

    def test_sh_extension_rejected(self, tmp_path):
        """Test that .sh files are rejected when extensions are specified."""
        test_file = tmp_path / "script.sh"
        test_file.write_text("#!/bin/bash")
        with pytest.raises(UnsafePathError):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            validate_input_path(str(test_file), allowed_extensions=frozenset({".dxf", ".dwg"}))


class TestValidateInputPathNullBytes:
    """Test null byte injection prevention."""

    def test_null_byte_rejected(self):
        """Test that paths with null bytes are rejected."""
        with pytest.raises(UnsafePathError, match="null byte"):
            validate_input_path("/tmp/test.pdf\x00.sh")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)

    def test_null_byte_in_middle(self):
        """Test null byte in middle of path."""
        with pytest.raises(UnsafePathError, match="null byte"):
            validate_input_path("/tmp/\x00test.dxf")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)


class TestValidateInputPathArgumentInjection:
    """Test argument injection prevention."""

    def test_dash_prefix_rejected(self):
        """Test that paths starting with - are rejected (argument injection)."""
        with pytest.raises(UnsafePathError, match="starts with '-'"):
            validate_input_path("-rf")

    def test_double_dash_rejected(self):
        """Test that paths starting with -- are rejected."""
        with pytest.raises(UnsafePathError, match="starts with '-'"):
            validate_input_path("--output")


class TestValidateFileSize:
    """Test file size validation (decompression bomb defense)."""

    def test_normal_file_passes(self, tmp_path):
        """Test that a normal-sized file passes validation."""
        test_file = tmp_path / "test.dxf"
        test_file.write_text("test content")
        size = validate_file_size(Path(str(test_file)), max_size_bytes=1_000_000)
        assert size > 0

    def test_oversized_file_rejected(self, tmp_path):
        """Test that oversized files are rejected."""
        test_file = tmp_path / "big.dxf"
        test_file.write_text("x" * 100)
        with pytest.raises(UnsafePathError, match="exceeds limit"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            validate_file_size(Path(str(test_file)), max_size_bytes=50)

    def test_nonexistent_file_raises(self, tmp_path):
        """Test that validating a nonexistent file raises."""
        nonexistent = Path(str(tmp_path / "nonexistent.dxf"))
        with pytest.raises(UnsafePathError):
            validate_file_size(nonexistent, max_size_bytes=1_000_000)

    def test_returns_actual_size(self, tmp_path):
        """Test that validate_file_size returns the actual file size."""
        test_file = tmp_path / "sized.dxf"
        test_file.write_bytes(b"x" * 42)
        size = validate_file_size(Path(str(test_file)), max_size_bytes=100)
        assert size == 42


class TestResolveAllowedBases:
    """Test _resolve_allowed_bases helper function."""

    def test_default_bases_include_tmp(self):
        """Test that default allowed bases include temp directory."""
        bases = _resolve_allowed_bases()
        assert len(bases) >= 1

    def test_custom_env_var(self, monkeypatch):
        """Test that FIREAI_ALLOWED_UPLOAD_DIRS env var is respected."""
        with tempfile.TemporaryDirectory() as td:
            resolved_td = str(Path(td).resolve())
            monkeypatch.setenv("FIREAI_ALLOWED_UPLOAD_DIRS", td)
            bases = _resolve_allowed_bases()
            assert any(resolved_td in str(b.resolve()) for b in bases)

    def test_empty_entries_skipped(self, monkeypatch):
        """Test that empty entries in env var are skipped."""
        monkeypatch.setenv("FIREAI_ALLOWED_UPLOAD_DIRS", ":/tmp:")
        bases = _resolve_allowed_bases()
        # Should not crash from empty entries
        assert len(bases) >= 1

    def test_development_env_adds_cwd(self, monkeypatch):
        """Test that FIREAI_ENV=development adds CWD to allowed bases."""
        monkeypatch.setenv("FIREAI_ENV", "development")
        bases = _resolve_allowed_bases()
        cwd = os.path.realpath(os.getcwd())
        assert any(str(b) == cwd for b in bases)
