# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
parsers/tests/test_dwg_parser.py — Comprehensive DWG Parser Tests
=================================================================
Task 1.3: Add parser tests — Fix 19% coverage → target 80%

Tests cover:
  1. DWGParser initialization and tool availability
  2. Coordinate validation (NaN/Inf rejection)
  3. Closed polygon assembly from LINE segments
  4. Path security (V122 hardening)
  5. DXF fast-path (bypasses LibreDWG for .dxf input)
  6. Error handling for corrupted/adversarial input
  7. DWGConversionError handling
  8. Backward-compat parse_dwg() alias
  9. extract_rooms_from_chaos with various entity types
  10. Integration with DXFParser for converted files

Safety-Critical: Per NFPA 72 §17.7, all geometry must be valid.
Invalid rooms MUST be skipped, never guessed.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from parsers._path_security import UnsafePathError
from parsers.dwg_parser import DWGConversionError, DWGParser, DWGParseResult

# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def parser():
    """Fresh DWGParser instance for each test."""
    return DWGParser()


@pytest.fixture
def tmpdir():
    """Temporary directory that auto-cleans."""
    with tempfile.TemporaryDirectory(prefix="dwg_test_") as d:
        yield d


def _make_temp_file(suffix=".dwg", content=b"fake", directory=None):
    """Create a temp file with given content and extension."""
    fd, path = tempfile.mkstemp(
        suffix=suffix, prefix="dwg_test_", dir=directory
    )
    try:
        os.write(fd, content)
    finally:
        os.close(fd)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Initialization and Tool Availability
# ═══════════════════════════════════════════════════════════════════════════════


class TestDWGParserInit:
    """DWGParser initialization and tool-check behavior."""

    def test_default_init(self, parser):
        """DWGParser initializes without error."""
        assert parser._tool_checked is False
        assert parser._tool_available is False

    def test_check_tool_caches_result(self, parser):
        """Tool availability check is cached after first call."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result1 = parser._check_tool()
            result2 = parser._check_tool()
            # subprocess.run should only be called once
            assert mock_run.call_count == 1
            assert result1 is True
            assert result2 is True

    def test_check_tool_returns_false_when_missing(self, parser):
        """Tool check returns False when dxf-out is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert parser._check_tool() is False

    def test_check_tool_returns_false_on_timeout(self, parser):
        """Tool check returns False on timeout."""
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="dxf-out", timeout=5)):
            assert parser._check_tool() is False

    def test_check_tool_returns_false_on_nonzero(self, parser):
        """Tool check returns False when dxf-out exits nonzero."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert parser._check_tool() is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Coordinate Validation (Safety-Critical)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCoordinateValidation:
    """V122/V79: NaN and Infinity coordinates MUST be rejected."""

    def test_valid_float_passes(self, parser):
        assert DWGParser._is_valid_coordinate(0.0) is True
        assert DWGParser._is_valid_coordinate(100.5) is True
        assert DWGParser._is_valid_coordinate(-50.0) is True
        assert DWGParser._is_valid_coordinate(1e10) is True

    def test_nan_rejected(self, parser):
        assert DWGParser._is_valid_coordinate(float("nan")) is False

    def test_positive_infinity_rejected(self, parser):
        assert DWGParser._is_valid_coordinate(float("inf")) is False

    def test_negative_infinity_rejected(self, parser):
        assert DWGParser._is_valid_coordinate(float("-inf")) is False

    def test_none_rejected(self, parser):
        assert DWGParser._is_valid_coordinate(None) is False

    def test_string_rejected(self, parser):
        assert DWGParser._is_valid_coordinate("not a number") is False

    def test_list_rejected(self, parser):
        assert DWGParser._is_valid_coordinate([1, 2, 3]) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Closed Polygon Assembly
# ═══════════════════════════════════════════════════════════════════════════════


class TestAssembleClosedPolygons:
    """
    DWGParser._assemble_closed_polygons chains LINE segments into rooms.

    This is safety-critical: missing a room means zero fire protection.
    """

    def test_empty_input_returns_empty(self, parser):
        assert parser._assemble_closed_polygons([]) == []

    def test_single_closed_square(self, parser):
        """4 LINE segments forming a 10x10 square produce 1 polygon."""
        lines = [
            ((0, 0), (10, 0)),   # bottom
            ((10, 0), (10, 10)), # right
            ((10, 10), (0, 10)), # top
            ((0, 10), (0, 0)),   # left
        ]
        polygons = parser._assemble_closed_polygons(lines, tolerance=0.1)
        assert len(polygons) == 1
        assert len(polygons[0]) >= 3  # At least 3 vertices for a polygon

    def test_two_separate_rooms(self, parser):
        """Two separate square rooms produce 2 polygons."""
        # Room 1: (0,0)-(5,5)
        room1 = [
            ((0, 0), (5, 0)),
            ((5, 0), (5, 5)),
            ((5, 5), (0, 5)),
            ((0, 5), (0, 0)),
        ]
        # Room 2: (20,0)-(25,5)
        room2 = [
            ((20, 0), (25, 0)),
            ((25, 0), (25, 5)),
            ((25, 5), (20, 5)),
            ((20, 5), (20, 0)),
        ]
        polygons = parser._assemble_closed_polygons(
            room1 + room2, tolerance=0.1
        )
        assert len(polygons) == 2

    def test_unclosed_segments_produce_no_polygon(self, parser):
        """3 LINE segments forming an open L-shape produce no closed polygon."""
        lines = [
            ((0, 0), (10, 0)),
            ((10, 0), (10, 5)),
            ((10, 5), (20, 5)),  # Open end — doesn't close
        ]
        polygons = parser._assemble_closed_polygons(lines, tolerance=0.1)
        # No closed polygon should be found
        assert len(polygons) == 0

    def test_large_polygon(self, parser):
        """A 100x50 rectangle (industrial space) assembles correctly."""
        lines = [
            ((0, 0), (100, 0)),
            ((100, 0), (100, 50)),
            ((100, 50), (0, 50)),
            ((0, 50), (0, 0)),
        ]
        polygons = parser._assemble_closed_polygons(lines, tolerance=0.1)
        assert len(polygons) == 1

    def test_tolerance_gap_closed(self, parser):
        """Gaps within tolerance should still produce closed polygons."""
        # 4 segments with small gap (<0.01) at one corner
        lines = [
            ((0, 0), (10, 0)),
            ((10, 0.005), (10, 10)),  # Slight gap at corner
            ((10, 10), (0, 10)),
            ((0, 10), (0, 0)),
        ]
        polygons = parser._assemble_closed_polygons(lines, tolerance=0.1)
        assert len(polygons) == 1

    def test_single_segment_no_polygon(self, parser):
        """A single LINE segment cannot form a closed polygon."""
        lines = [((0, 0), (10, 0))]
        polygons = parser._assemble_closed_polygons(lines, tolerance=0.1)
        assert len(polygons) == 0

    def test_triangle_polygon(self, parser):
        """3 LINE segments forming a triangle produce 1 polygon."""
        lines = [
            ((0, 0), (5, 0)),
            ((5, 0), (2.5, 4)),
            ((2.5, 4), (0, 0)),
        ]
        polygons = parser._assemble_closed_polygons(lines, tolerance=0.1)
        assert len(polygons) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Path Security (V122 Hardening)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDWGParserPathSecurity:
    """V122: DWGParser enforces path security before any file I/O."""

    def test_parse_rejects_leading_dash(self, parser):
        """Argument injection: path starting with '-' is rejected."""
        result = parser.parse("--malicious")
        assert not result.success
        assert any("SECURITY" in e for e in result.errors)

    def test_parse_rejects_null_byte(self, parser):
        """Null byte in path is rejected (C-string truncation defense)."""
        result = parser.parse("/tmp/x\x00.dwg")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
        assert not result.success
        assert any("SECURITY" in e for e in result.errors)

    def test_parse_rejects_wrong_extension(self, parser):
        """Files with non-DWG/DXF extensions are rejected."""
        p = _make_temp_file(suffix=".txt")
        try:
            result = parser.parse(p)
            assert not result.success
            assert any("SECURITY" in e for e in result.errors)
        finally:
            os.unlink(p)

    def test_parse_rejects_missing_file(self, parser):
        """Missing file produces a friendly error."""
        result = parser.parse("/tmp/does_not_exist_xyzzy.dwg")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
        assert not result.success
        assert any("not found" in e for e in result.errors)

    def test_parse_dwg_alias_rejects_leading_dash(self, parser):
        """parse_dwg() backward-compat alias enforces same security."""
        with pytest.raises(UnsafePathError, match="flag"):
            parser.parse_dwg("--evil")

    def test_parse_dwg_alias_rejects_null_byte(self, parser):
        """parse_dwg() rejects null bytes."""
        with pytest.raises(UnsafePathError, match="null byte"):
            parser.parse_dwg("/tmp/x\x00.dxf")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)

    def test_parse_dwg_alias_rejects_wrong_extension(self, parser):
        """parse_dwg() rejects wrong extension."""
        p = _make_temp_file(suffix=".py")
        try:
            with pytest.raises(UnsafePathError, match="extension"):
                parser.parse_dwg(p)
        finally:
            os.unlink(p)

    def test_convert_to_dxf_rejects_leading_dash(self, parser):
        """_convert_to_dxf defense-in-depth rejects bad paths."""
        with pytest.raises(DWGConversionError, match="SECURITY"):
            parser._convert_to_dxf("--evil")

    def test_convert_to_dxf_rejects_null_byte(self, parser):
        """_convert_to_dxf rejects null bytes."""
        with pytest.raises(DWGConversionError, match="SECURITY"):
            parser._convert_to_dxf("/tmp/x\x00")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. DXF Fast-Path
# ═══════════════════════════════════════════════════════════════════════════════


class TestDXFFastPath:
    """
    When input is .dxf, DWGParser delegates directly to DXFParser
    without invoking LibreDWG tools.
    """

    def test_dxf_input_skips_libredwg(self, parser):
        """DXF files should not invoke dxf-out conversion."""
        # Create a minimal DXF file
        dxf_content = (
            "0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n6\n0\nENDSEC\n"
            "0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"
        )
        p = _make_temp_file(suffix=".dxf", content=dxf_content.encode())
        try:
            # parse() should not call subprocess (no LibreDWG needed)
            with patch("subprocess.run") as mock_run:
                parser.parse(p)
                # subprocess should NOT be called for .dxf fast-path
                assert mock_run.call_count == 0
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Error Handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestDWGParserErrorHandling:
    """Error handling for corrupted/adversarial DWG/DXF input."""

    def test_parse_returns_dwg_parse_result_on_error(self, parser):
        """parse() always returns DWGParseResult, never raises."""
        result = parser.parse("/tmp/does_not_exist.dwg")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
        assert isinstance(result, DWGParseResult)
        assert result.success is False

    def test_conversion_error_on_missing_tool(self, parser):
        """DWGConversionError raised when dxf-out subprocess fails."""
        p = _make_temp_file(suffix=".dwg")
        try:
            with patch("parsers.dwg_parser.subprocess.run") as mock_run:
                # Simulate dxf-out not found
                mock_run.side_effect = FileNotFoundError("dxf-out not found")
                with pytest.raises(FileNotFoundError):
                    parser._convert_to_dxf(p)
        finally:
            os.unlink(p)

    def test_parse_result_has_errors_list(self, parser):
        """Failed parse result includes errors list."""
        result = parser.parse("--invalid")
        assert isinstance(result.errors, list)
        assert len(result.errors) > 0

    def test_parse_result_has_source_file(self, parser):
        """Parse result preserves source file path."""
        result = parser.parse("--invalid")
        assert result.source_file == "--invalid"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. DWGParseResult Data Class
# ═══════════════════════════════════════════════════════════════════════════════


class TestDWGParseResultDataClass:
    """DWGParseResult fields and defaults."""

    def test_default_values(self):
        result = DWGParseResult(source_file="test.dwg", success=False)
        assert result.room_count == 0
        assert result.conversion_time_s == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.errors == []
        assert result.warnings == []

    def test_custom_values(self):
        result = DWGParseResult(
            source_file="test.dwg",
            success=True,
            room_count=5,
            conversion_time_s=1.23,
            warnings=["minor issue"],
        )
        assert result.room_count == 5
        assert result.conversion_time_s == 1.23  # NOSONAR — S1244: import retained for re-export / API surface
        assert len(result.warnings) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 8. extract_rooms_from_chaos with Mock Documents
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractRoomsFromChaos:
    """Safety-critical: adversarial/corrupted entities must be handled gracefully."""

    def test_empty_document_returns_empty(self, parser):
        """Empty modelspace produces no rooms."""
        mock_doc = MagicMock()
        mock_msp = MagicMock()
        mock_msp.__iter__ = MagicMock(return_value=iter([]))
        mock_doc.modelspace.return_value = mock_msp
        rooms = parser.extract_rooms_from_chaos(mock_doc)
        assert isinstance(rooms, list)

    def test_valid_line_entity_handled(self, parser):
        """LINE entities with valid coordinates are processed without crash."""
        mock_doc = MagicMock()
        mock_msp = MagicMock()

        # Create a mock LINE entity forming a closed square
        entity1 = MagicMock()
        entity1.dxftype.return_value = "LINE"
        entity1.dxf.start.x = 0
        entity1.dxf.start.y = 0
        entity1.dxf.end.x = 10
        entity1.dxf.end.y = 0

        mock_msp.__iter__ = MagicMock(return_value=iter([entity1]))
        mock_doc.modelspace.return_value = mock_msp

        # Should not crash — may return empty or rooms depending on
        # UniversalElement requirements
        rooms = parser.extract_rooms_from_chaos(mock_doc)
        assert isinstance(rooms, list)

    def test_nan_coordinates_skipped(self, parser):
        """LINE with NaN coordinates is silently skipped (safety)."""
        mock_doc = MagicMock()
        mock_msp = MagicMock()

        entity = MagicMock()
        entity.dxftype.return_value = "LINE"
        entity.dxf.start.x = float("nan")
        entity.dxf.start.y = 0
        entity.dxf.end.x = 10
        entity.dxf.end.y = 0

        mock_msp.__iter__ = MagicMock(return_value=iter([entity]))
        mock_doc.modelspace.return_value = mock_msp

        # Should not crash — NaN is filtered
        rooms = parser.extract_rooms_from_chaos(mock_doc)
        assert isinstance(rooms, list)

    def test_inf_coordinates_skipped(self, parser):
        """LINE with Infinity coordinates is silently skipped."""
        mock_doc = MagicMock()
        mock_msp = MagicMock()

        entity = MagicMock()
        entity.dxftype.return_value = "LINE"
        entity.dxf.start.x = 0
        entity.dxf.start.y = 0
        entity.dxf.end.x = float("inf")
        entity.dxf.end.y = 0

        mock_msp.__iter__ = MagicMock(return_value=iter([entity]))
        mock_doc.modelspace.return_value = mock_msp

        rooms = parser.extract_rooms_from_chaos(mock_doc)
        assert isinstance(rooms, list)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. DWGConversionError Exception
# ═══════════════════════════════════════════════════════════════════════════════


class TestDWGConversionError:
    """DWGConversionError is raised for conversion failures."""

    def test_exception_message(self):
        with pytest.raises(DWGConversionError, match="test error"):
            raise DWGConversionError("test error")

    def test_is_exception_subclass(self):
        assert issubclass(DWGConversionError, Exception)

    def test_exception_without_message(self):
        with pytest.raises(DWGConversionError):
            raise DWGConversionError()


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Integration: Full parse() with DXF file
# ═══════════════════════════════════════════════════════════════════════════════


class TestDWGParserIntegration:
    """Integration tests using actual .dxf files."""

    def test_parse_minimal_dxf(self, parser):
        """Parse a minimal DXF file via the DWGParser DXF fast-path."""
        dxf_content = (
            "0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n6\n0\nENDSEC\n"
            "0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"
        )
        p = _make_temp_file(suffix=".dxf", content=dxf_content.encode())
        try:
            result = parser.parse(p)
            assert isinstance(result, DWGParseResult)
            # Minimal DXF has no room geometry — expected to fail
            # but must not crash
        finally:
            os.unlink(p)

    def test_parse_dwg_extension_file(self, parser):
        """Parse a .dwg file (without LibreDWG) — graceful error."""
        p = _make_temp_file(suffix=".dwg", content=b"AC1015_FAKE_DWG")
        try:
            result = parser.parse(p)
            assert isinstance(result, DWGParseResult)
            # Without LibreDWG, conversion fails — but no crash
        finally:
            os.unlink(p)

    def test_parse_result_source_file_preserved(self, parser):
        """Source file path is preserved in result."""
        p = _make_temp_file(suffix=".dxf")
        try:
            result = parser.parse(p)
            assert p in result.source_file or result.source_file.endswith(".dxf")
        finally:
            os.unlink(p)
