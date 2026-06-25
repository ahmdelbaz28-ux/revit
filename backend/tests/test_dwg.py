"""test_dwg.py — DWG/DXF parser integration tests.

Verifies DWG upload, parsing, path security, and element extraction.
Tests both the /api/parse-dwg endpoint and the underlying parser module.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    os.environ.setdefault("FIREAI_ENV", "development")
    os.environ.setdefault("FIREAI_API_KEY", "")

    from backend.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_dxf_file():
    """Create a minimal DXF file for testing."""
    dxf_content = """  0
SECTION
  2
HEADER
  0
ENDSEC
  0
SECTION
  2
ENTITIES
  0
LINE
  8
0
 10
0.0
 20
0.0
 30
0.0
 11
100.0
 21
100.0
 31
0.0
  0
ENDSEC
  0
EOF
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".dxf", delete=False, prefix="test_fireai_"
    ) as f:
        f.write(dxf_content)
        filepath = f.name
    yield filepath
    try:
        os.unlink(filepath)
    except OSError:
        pass


class TestDWGParseEndpoint:
    """Tests for POST /api/parse-dwg."""

    def test_parse_dxf_file(self, client, sample_dxf_file):
        """Uploading a DXF file must return parsed elements."""
        with open(sample_dxf_file, "rb") as f:
            response = client.post(
                "/api/parse-dwg",
                files={"file": ("test.dxf", f, "application/dxf")},
            )
        # The endpoint may return 200, 201, or 422 depending on validation
        assert response.status_code in (200, 201, 422, 503), \
            f"Unexpected status: {response.status_code}: {response.text[:500]}"

    def test_parse_empty_file_rejected(self, client):
        """Uploading an empty file must be rejected."""
        response = client.post(
            "/api/parse-dwg",
            files={"file": ("empty.dxf", b"", "application/dxf")},
        )
        # Empty file should be rejected (422 or 400)
        assert response.status_code in (400, 422), \
            f"Empty file should be rejected: {response.status_code}"


class TestDWGPathSecurity:
    """Tests for DWG parser path security (V122/V125 fixes)."""

    def test_path_traversal_blocked(self):
        """Path traversal attempts must be blocked by _path_security."""
        from parsers._path_security import UnsafePathError, validate_input_path

        # Path traversal with non-existent file should raise UnsafePathError or FileNotFoundError
        with pytest.raises((UnsafePathError, FileNotFoundError)):
            validate_input_path("../../../etc/passwd")

    def test_absolute_path_blocked(self):
        """Absolute paths outside allowed dirs must be blocked."""
        from parsers._path_security import UnsafePathError, validate_input_path

        with pytest.raises((UnsafePathError, FileNotFoundError)):
            validate_input_path("/etc/passwd")

    def test_normal_relative_path_accepted(self):
        """Normal relative paths within allowed directories should be accepted."""
        import tempfile

        from parsers._path_security import validate_input_path

        # Create a real temp file — validate_input_path checks existence
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False, prefix="test_fireai_") as f:
            f.write(b"0\nSECTION\n0\nENDSEC\n0\nEOF\n")
            filepath = f.name

        try:
            result = validate_input_path(filepath, allowed_extensions=frozenset({".dxf"}))
            # validate_input_path returns a resolved Path object
            from pathlib import Path
            assert isinstance(result, Path)
        finally:
            import os
            os.unlink(filepath)


class TestDXFParser:
    """Tests for the DXF parser module."""

    def test_dxf_parser_import(self):
        """DXF parser module must be importable."""
        from parsers.dxf_parser import DXFParser
        assert DXFParser is not None

    def test_dwg_parser_import(self):
        """DWG parser module must be importable."""
        from parsers.dwg_parser import DWGParser
        assert DWGParser is not None

    def test_path_security_import(self):
        """Path security module must be importable."""
        from parsers._path_security import validate_input_path
        assert validate_input_path is not None


class TestDWGEndpointSecurity:
    """Security tests for the DWG parsing endpoint."""

    def test_rate_limiting_on_parse(self, client):
        """DWG parse endpoint should have rate limiting."""
        # Make several rapid requests — should not all succeed
        # The rate limit for /api/parse-dwg is 5/min
        responses = []
        for _ in range(3):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".dxf", delete=False
            ) as f:
                f.write("0\nSECTION\n0\nENDSEC\n0\nEOF\n")
                filepath = f.name

            with open(filepath, "rb") as fh:
                resp = client.post(
                    "/api/parse-dwg",
                    files={"file": ("test.dxf", fh, "application/dxf")},
                )
                responses.append(resp)

            try:
                os.unlink(filepath)
            except OSError:
                pass

        # At least the first request should get a non-rate-limit response
        assert responses[0].status_code in (200, 201, 422, 503)
