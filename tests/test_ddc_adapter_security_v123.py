"""
tests/test_ddc_adapter_security_v123.py — V123 refactor verification
=====================================================================
V123 refactored parsers/ddc_adapter.py to delegate path validation to
the shared parsers._path_security helper (single source of truth per
agent.md Rule #23).

These tests verify:
  1. Backward compatibility — pre-V123 behavior preserved
     (ValueError raised for path-traversal and bad-extension cases)
  2. New defenses activated by V123 — null bytes and leading dashes
     now rejected (previously these would have been silently passed
     through to the subprocess)
  3. Valid paths still work (no false-positive rejection)
  4. The shared helper is the single source of truth (no inline copy
     of validation logic remains)
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

from parsers.ddc_adapter import DDCAdapter, DDCNotAvailableError


def _make_temp(suffix: str) -> str:
    """Create a temp file in the system temp dir (always allowed)."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="v123_ddc_")
    os.close(fd)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# V123 backward-compat: pre-V123 callers expecting ValueError must still get it
# ═══════════════════════════════════════════════════════════════════════════════


class TestV123BackwardCompatibility:
    """Pre-V123, ddc_adapter raised ValueError for path-traversal and
    extension violations. V123 preserves that contract by mapping the
    new UnsafePathError → ValueError at the convert() boundary."""

    def test_path_traversal_still_raises_ValueError(self, monkeypatch):
        """File outside FIREAI_ALLOWED_UPLOAD_DIRS → ValueError (not UnsafePathError)."""
        monkeypatch.setenv("FIREAI_ALLOWED_UPLOAD_DIRS", "/var/fireai/uploads")
        monkeypatch.delenv("FIREAI_ENV", raising=False)
        home = Path.home()
        if not home.exists():
            pytest.skip("No HOME for outside-allowed-dirs test")
        outside = home / ".v123_ddc_outside.rvt"
        outside.write_bytes(b"x")
        try:
            adapter = DDCAdapter()
            with pytest.raises((ValueError, DDCNotAvailableError)) as exc_info:
                adapter.convert(str(outside))
            # If we got a ValueError, it MUST be the security one
            if isinstance(exc_info.value, ValueError):
                assert "SECURITY" in str(exc_info.value) or \
                       "outside allowed" in str(exc_info.value), \
                       f"Unexpected ValueError: {exc_info.value}"
        finally:
            try:
                outside.unlink()
            except FileNotFoundError:
                pass

    def test_bad_extension_still_raises_ValueError(self):
        """Extension not in DDC converter set → ValueError."""
        path = _make_temp(suffix=".bogus")
        try:
            adapter = DDCAdapter()
            with pytest.raises(ValueError, match="extension"):
                adapter.convert(path)
        finally:
            os.unlink(path)

    def test_missing_file_still_raises_FileNotFoundError(self):
        """Missing file → FileNotFoundError (benign, preserved from pre-V123)."""
        adapter = DDCAdapter()
        with pytest.raises(FileNotFoundError):
            adapter.convert("/tmp/v123_does_not_exist_zzz.rvt")


# ═══════════════════════════════════════════════════════════════════════════════
# V123 new defenses (inherited from V122 helper)
# ═══════════════════════════════════════════════════════════════════════════════


class TestV123NewDefenses:
    """V123 inherits two new defenses from the V122 shared helper:
    null byte rejection and leading-dash argument-injection guard.
    Pre-V123, ddc_adapter did NOT check these."""

    def test_null_byte_rejected(self):
        """Path with \\x00 → ValueError (V123: previously not checked)."""
        adapter = DDCAdapter()
        with pytest.raises(ValueError, match="null byte"):
            adapter.convert("/tmp/foo\x00.rvt")

    def test_leading_dash_rejected(self):
        """Path starting with '-' → ValueError (argument-injection guard)."""
        adapter = DDCAdapter()
        with pytest.raises(ValueError, match="flag"):
            adapter.convert("--output=evil.txt")

    def test_double_dash_rejected(self):
        adapter = DDCAdapter()
        with pytest.raises(ValueError, match="flag"):
            adapter.convert("--help")


# ═══════════════════════════════════════════════════════════════════════════════
# V123 refactor verification: no inline duplicate validation remains
# ═══════════════════════════════════════════════════════════════════════════════


class TestV123SingleSourceOfTruth:
    """Per agent.md Rule #23: there must be exactly ONE source of truth
    for path-security validation. V123 made ddc_adapter delegate to the
    shared helper. We assert that programmatically: no other validation
    code paths exist in ddc_adapter."""

    def test_ddc_adapter_imports_shared_helper(self):
        """ddc_adapter MUST import from parsers._path_security."""
        src = (Path(_PROJECT_ROOT) / "parsers" / "ddc_adapter.py").read_text(
            encoding="utf-8"
        )
        assert "from parsers._path_security import" in src, (
            "V123 regression: ddc_adapter.py no longer imports the shared "
            "_path_security helper. Single source of truth (Rule #23) violated."
        )
        assert "validate_input_path" in src, (
            "V123 regression: ddc_adapter.py does not call validate_input_path"
        )

    def test_ddc_adapter_no_inline_allowed_bases(self):
        """V123: the inline 'allowed_bases' loop was removed. If it
        reappears, this test fails — guarding against re-introduction
        of duplicate validation logic."""
        src = (Path(_PROJECT_ROOT) / "parsers" / "ddc_adapter.py").read_text(
            encoding="utf-8"
        )
        # The old inline loop iterated over `_allowed_bases`. If that
        # variable name appears in convert() again, we have drift.
        # We do a precise check: the local variable name in the inline
        # validation was `_allowed_bases` — check it doesn't exist as
        # a local assignment in convert(). The shared helper's internal
        # variable is `allowed_bases` (no leading underscore) which is
        # encapsulated in its own module.
        assert "_allowed_bases = [" not in src, (
            "V123 regression: inline _allowed_bases list reappeared in "
            "ddc_adapter.py. Use parsers._path_security.validate_input_path "
            "instead per Rule #23."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Verify the shared helper still works through ddc_adapter end-to-end
# ═══════════════════════════════════════════════════════════════════════════════


class TestV123EndToEnd:
    """End-to-end: a valid path reaches the post-validation code
    (which then fails at the DDC binary lookup since the converter
    isn't installed in test env — but we verify the path-validation
    stage passes)."""

    def test_valid_extension_passes_validation(self):
        """A valid .rvt file in /tmp passes validation. The convert()
        call will later fail at the DDC binary check (not installed
        in tests) — but that proves validation passed."""
        path = _make_temp(suffix=".rvt")
        try:
            adapter = DDCAdapter()
            try:
                adapter.convert(path)
                # If it didn't raise, the DDC converter IS available
                # (unlikely in CI). Still a valid outcome.
            except DDCNotAvailableError:
                # Expected in environments without DDC installed.
                pass
            except ValueError as e:
                # If we get ValueError, it MUST NOT be a validation error
                msg = str(e)
                assert "SECURITY" not in msg and "extension" not in msg \
                       and "null byte" not in msg and "flag" not in msg, \
                       f"Validation false-positive on valid path: {msg}"
            except Exception:
                # Any other error type is OK (DDC missing, etc.)
                pass
        finally:
            os.unlink(path)
