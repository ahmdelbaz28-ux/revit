"""
tests/test_bim_input_sanitizer.py
==================================
Comprehensive test suite for:
  fireai/core/bim_input_sanitizer.py

SAFETY CRITICAL: Unsanitized inputs to BIM parameters can cause:
  1. Remote Code Execution (RCE) via eval()/exec()
  2. SQL Injection via unsanitized room names
  3. Path Traversal via file paths
  4. XSS in web dashboards
  5. Corrupted BIM model parameters

OWASP Top 10 (A03:2021-Injection): Input injection is the #3 most
critical web application security risk.

This test suite validates whitelist-based sanitization for all
parameters that flow from external sources into BIM models.
"""

from __future__ import annotations

import math
import pytest

from fireai.core.bim_input_sanitizer import (
    sanitize_bim_parameter,
    sanitize_room_name,
    sanitize_file_path,
    validate_numeric_parameter,
)


# ─────────────────────────────────────────────────────────────────────────────
# sanitize_bim_parameter
# ─────────────────────────────────────────────────────────────────────────────


class TestSanitizeBIMParameter:
    """BIM parameter string sanitization — injection prevention."""

    def test_safe_string_passes_through(self):
        """Normal engineering text should pass through unchanged."""
        result = sanitize_bim_parameter("Office Room 101")
        assert result == "Office Room 101"

    def test_alphanumeric_passes(self):
        """Pure alphanumeric passes through."""
        result = sanitize_bim_parameter("Room42")
        assert result == "Room42"

    def test_special_chars_stripped(self):
        """Non-whitelisted characters are stripped."""
        result = sanitize_bim_parameter("Room@#$%101")
        # @#$% should be removed
        assert "@" not in result
        assert "#" not in result
        assert "$" not in result
        assert "%" not in result

    def test_spaces_preserved(self):
        """Spaces should be preserved in BIM parameters."""
        result = sanitize_bim_parameter("Main Corridor B")
        assert " " in result

    def test_hyphens_preserved(self):
        """Hyphens should be preserved."""
        result = sanitize_bim_parameter("Room-A-101")
        assert "-" in result

    def test_dots_preserved(self):
        """Dots should be preserved (for decimal values in names)."""
        result = sanitize_bim_parameter("Room.2.1")
        assert "." in result

    def test_underscores_preserved(self):
        """Underscores should be preserved."""
        result = sanitize_bim_parameter("room_id_42")
        assert "_" in result

    def test_parentheses_preserved(self):
        """Parentheses should be preserved (e.g., 'Room (Backup)')."""
        result = sanitize_bim_parameter("Room (Backup)")
        assert "(" in result
        assert ")" in result

    def test_non_string_raises(self):
        """Non-string input must raise ValueError."""
        with pytest.raises(ValueError, match="string"):
            sanitize_bim_parameter(42)

    def test_none_input_raises(self):
        """None input must raise ValueError."""
        with pytest.raises(ValueError, match="string"):
            sanitize_bim_parameter(None)

    def test_integer_input_raises(self):
        """Integer input must raise ValueError."""
        with pytest.raises(ValueError, match="string"):
            sanitize_bim_parameter(100)

    # ── Injection attack patterns ──

    def test_python_injection_blocked(self):
        """Python code injection via semicolon must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("; import os; os.system('rm -rf /')")

    def test_eval_injection_blocked(self):
        """eval() injection must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("__import__('os').system('whoami')")

    def test_getattr_injection_blocked(self):
        """getattr() injection must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("getattr(os, 'system')('ls')")

    def test_xss_script_tag_blocked(self):
        """XSS <script> tag must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("<script>alert('xss')</script>")

    def test_javascript_protocol_blocked(self):
        """javascript: protocol must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("javascript:alert(1)")

    def test_sql_drop_blocked(self):
        """SQL DROP statement must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("DROP TABLE rooms")

    def test_sql_delete_blocked(self):
        """SQL DELETE statement must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("DELETE FROM rooms WHERE 1=1")

    def test_sql_insert_blocked(self):
        """SQL INSERT statement must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("INSERT INTO rooms VALUES ('evil')")

    def test_sql_update_blocked(self):
        """SQL UPDATE statement must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("UPDATE rooms SET name='hacked'")

    def test_sql_union_select_blocked(self):
        """SQL UNION SELECT must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("' UNION SELECT * FROM users--")

    def test_empty_string_passes(self):
        """Empty string should pass (nothing to sanitize)."""
        result = sanitize_bim_parameter("")
        assert result == ""

    def test_subprocess_injection_blocked(self):
        """subprocess injection must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_bim_parameter("; import subprocess; subprocess.run(['ls'])")


# ─────────────────────────────────────────────────────────────────────────────
# sanitize_room_name
# ─────────────────────────────────────────────────────────────────────────────


class TestSanitizeRoomName:
    """Room name sanitization — injection + XSS prevention."""

    def test_normal_room_name_passes(self):
        """Normal room name should pass through unchanged."""
        result = sanitize_room_name("Diesel Generator Room")
        assert result == "Diesel Generator Room"

    def test_room_with_parentheses(self):
        """Room with parentheses should pass."""
        result = sanitize_room_name("Mechanical Room (Floor 3)")
        assert "Floor 3" in result

    def test_room_with_slash(self):
        """Room with slash should pass."""
        result = sanitize_room_name("Supply/Return Duct")
        assert "/" in result

    def test_room_with_ampersand(self):
        """Room with ampersand should pass."""
        result = sanitize_room_name("Kitchen & Dining")
        assert "&" in result

    def test_room_with_apostrophe(self):
        """Room with apostrophe should pass."""
        result = sanitize_room_name("Men's Restroom")
        assert "'" in result

    def test_room_with_colon(self):
        """Room with colon should pass."""
        result = sanitize_room_name("Room 101: Office")
        assert ":" in result

    def test_room_with_comma(self):
        """Room with comma should pass."""
        result = sanitize_room_name("Storage, Level 2")
        assert "," in result

    def test_non_string_raises(self):
        """Non-string input must raise ValueError."""
        with pytest.raises(ValueError, match="string"):
            sanitize_room_name(42)

    def test_none_raises(self):
        """None input must raise ValueError."""
        with pytest.raises(ValueError, match="string"):
            sanitize_room_name(None)

    def test_xss_blocked(self):
        """XSS in room name must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_room_name("<script>alert('xss')</script>")

    def test_sql_injection_blocked(self):
        """SQL injection in room name must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_room_name("'; DROP TABLE rooms;--")

    def test_python_injection_blocked(self):
        """Python code injection in room name must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_room_name("; import os")

    def test_special_chars_stripped(self):
        """Non-whitelisted characters in room name are stripped."""
        result = sanitize_room_name("Room@#$101")
        assert "@" not in result
        assert "#" not in result

    def test_leading_trailing_whitespace_stripped(self):
        """Leading/trailing whitespace should be stripped."""
        result = sanitize_room_name("  Office Room  ")
        assert result == "Office Room"

    def test_empty_string_passes(self):
        """Empty string should pass through."""
        result = sanitize_room_name("")
        assert result == ""

    def test_backslash_in_room_name(self):
        """Backslash should be preserved."""
        result = sanitize_room_name("Room\\Section")
        assert "\\" in result

    def test_path_traversal_blocked(self):
        """Path traversal (..) in room name must be blocked."""
        with pytest.raises(ValueError, match="[Ii]njection"):
            sanitize_room_name("../../etc/passwd")


# ─────────────────────────────────────────────────────────────────────────────
# sanitize_file_path
# ─────────────────────────────────────────────────────────────────────────────


class TestSanitizeFilePath:
    """File path sanitization — path traversal prevention."""

    def test_simple_path_passes(self):
        """Simple file path should pass through."""
        result = sanitize_file_path("reports/output.json")
        assert result == "reports/output.json"

    def test_windows_path_passes(self):
        """Windows-style path should pass through."""
        result = sanitize_file_path("reports\\output.json")
        assert "\\" in result

    def test_path_with_dots_passes(self):
        """Single dots in filenames (version numbers) should pass."""
        result = sanitize_file_path("report_v1.2.json")
        assert "1.2" in result

    def test_path_traversal_raises(self):
        """Path traversal (..) must raise ValueError."""
        with pytest.raises(ValueError, match="[Tt]raversal"):
            sanitize_file_path("../../etc/passwd")

    def test_path_traversal_mixed_raises(self):
        """Mixed path traversal must raise ValueError."""
        with pytest.raises(ValueError, match="[Tt]raversal"):
            sanitize_file_path("reports/../../../etc/shadow")

    def test_non_string_raises(self):
        """Non-string input must raise ValueError."""
        with pytest.raises(ValueError, match="string"):
            sanitize_file_path(42)

    def test_none_raises(self):
        """None input must raise ValueError."""
        with pytest.raises(ValueError, match="string"):
            sanitize_file_path(None)

    def test_special_chars_stripped(self):
        """Non-whitelisted characters are stripped from paths."""
        result = sanitize_file_path("reports/output@file.json")
        assert "@" not in result

    def test_absolute_path_passes(self):
        """Absolute paths should pass (no ..)."""
        result = sanitize_file_path("/home/user/reports/output.json")
        assert result == "/home/user/reports/output.json"

    def test_path_with_hyphens(self):
        """Paths with hyphens should pass."""
        result = sanitize_file_path("fire-alarm-report.json")
        assert "-" in result

    def test_path_with_underscores(self):
        """Paths with underscores should pass."""
        result = sanitize_file_path("fire_alarm_report.json")
        assert "_" in result


# ─────────────────────────────────────────────────────────────────────────────
# validate_numeric_parameter
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateNumericParameter:
    """Numeric parameter validation for engineering calculations."""

    def test_valid_integer_string(self):
        """Integer string should parse correctly."""
        result = validate_numeric_parameter("7")
        assert result == 7.0

    def test_valid_float_string(self):
        """Float string should parse correctly."""
        result = validate_numeric_parameter("7.5")
        assert result == 7.5

    def test_negative_value(self):
        """Negative value string should parse."""
        result = validate_numeric_parameter("-5.0")
        assert result == -5.0

    def test_scientific_notation(self):
        """Scientific notation should parse."""
        result = validate_numeric_parameter("1.5e2")
        assert result == 150.0

    def test_scientific_notation_uppercase(self):
        """Uppercase E in scientific notation."""
        result = validate_numeric_parameter("1.5E2")
        assert result == 150.0

    def test_min_value_boundary(self):
        """Value at min boundary should pass."""
        result = validate_numeric_parameter("0.0", min_value=0.0)
        assert result == 0.0

    def test_below_min_raises(self):
        """Value below min should raise ValueError."""
        with pytest.raises(ValueError, match="below minimum"):
            validate_numeric_parameter("-1.0", min_value=0.0, param_name="pressure")

    def test_max_value_boundary(self):
        """Value at max boundary should pass."""
        result = validate_numeric_parameter("10.0", max_value=10.0)
        assert result == 10.0

    def test_above_max_raises(self):
        """Value above max should raise ValueError."""
        with pytest.raises(ValueError, match="exceeds maximum"):
            validate_numeric_parameter("15.0", max_value=10.0, param_name="pressure")

    def test_non_string_raises(self):
        """Non-string input must raise ValueError."""
        with pytest.raises(ValueError, match="string"):
            validate_numeric_parameter(42.0)

    def test_none_raises(self):
        """None input must raise ValueError."""
        with pytest.raises(ValueError, match="string"):
            validate_numeric_parameter(None)

    def test_invalid_numeric_string_raises(self):
        """Non-numeric string must raise ValueError."""
        with pytest.raises(ValueError, match="not a valid numeric"):
            validate_numeric_parameter("abc")

    def test_empty_string_raises(self):
        """Empty string must raise ValueError."""
        with pytest.raises(ValueError, match="not a valid numeric"):
            validate_numeric_parameter("")

    def test_nan_value_raises(self):
        """NaN value must raise ValueError."""
        # 'nan' does not match the numeric regex pattern, so it raises
        # 'not a valid numeric value' before reaching the finite check
        with pytest.raises(ValueError):
            validate_numeric_parameter("nan")

    def test_inf_value_raises(self):
        """Infinity value must raise ValueError."""
        with pytest.raises(ValueError):
            validate_numeric_parameter("inf")

    def test_negative_infinity_raises(self):
        """Negative infinity value must raise ValueError."""
        with pytest.raises(ValueError):
            validate_numeric_parameter("-inf")

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace should be stripped."""
        result = validate_numeric_parameter("  7.5  ")
        assert result == 7.5

    def test_param_name_in_error_message(self):
        """Custom param_name should appear in error messages."""
        with pytest.raises(ValueError, match="pipe_diameter"):
            validate_numeric_parameter("-1.0", min_value=0.0, param_name="pipe_diameter")

    def test_both_min_and_max(self):
        """Both min and max constraints applied."""
        result = validate_numeric_parameter("5.0", min_value=0.0, max_value=10.0)
        assert result == 5.0

    def test_integer_value_string(self):
        """Integer value as string."""
        result = validate_numeric_parameter("24")
        assert result == 24.0
        assert isinstance(result, float)

    def test_decimal_without_leading_zero(self):
        """Decimal value without leading zero (like '.5') — depends on regex."""
        # The regex r'^-?\d+\.?\d*([eE][+-]?\d+)?$' requires at least one digit before dot
        with pytest.raises(ValueError, match="not a valid numeric"):
            validate_numeric_parameter(".5")

    def test_trailing_dot(self):
        """Trailing dot like '5.' should be valid per regex."""
        result = validate_numeric_parameter("5.")
        assert result == 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
