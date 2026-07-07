# NOSONAR
"""
conftest.py — Shared Pytest Fixtures for FireAI Test Suite
===========================================================

This module provides shared fixtures for ALL test files in the FireAI
safety-critical fire protection system. Every test file can use these
fixtures without explicit imports.

SAFETY NOTE: This is a safety-critical system. Test fixtures MUST NOT:
  - Weaken assertions (Rule 10)
  - Mock critical safety behavior deceptively (Testing Policy)
  - Bypass validation logic (Testing Policy)
  - Remove failing tests dishonestly (Rule 1, Rule 10)

Usage:
    # In any test file:
    def test_example(safe_room_polygon, sample_obstruction):
        ...
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

import pytest

# ─── Path Setup ─────────────────────────────────────────────────────────────
# Ensure project root is first in sys.path for correct module resolution.
# This prevents namespace collisions between fireai/core/ and top-level core/.
_PROJECT_ROOT = Path(__file__).parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# test_mip_solver replaces sys.modules["fireai"] with a mock at import time,
# which corrupts the import system for all other tests. It must run in isolation.
# Excluding from collection here so the full suite can run without cascade failures.
collect_ignore = ["test_mip_solver.py"]

# V142 SAFETY: Prevent MCP server tests from hanging on stdin in CI.
# In CI runners, sys.stdin has no EOF, so _stdin_loop()'s `for line in sys.stdin`
# blocks forever. Setting FIREAI_MCP_NO_STDIN=1 globally makes _stdin_loop()
# a no-op wait on _running instead. Production deployments do NOT set this.
# This MUST be set before any test imports the MCP server module.
import os as _os

_os.environ.setdefault("FIREAI_MCP_NO_STDIN", "1")
_os.environ.setdefault("FIREAI_HMAC_SECRET_KEY", "test_hmac_secret_key_123456")

# Clean up namespace pollution from fireai/ subdirectory
# (V27 fix: Python import machinery re-adds fireai/ to sys.path)
_fireai_dir = str(_PROJECT_ROOT / "fireai")
if _fireai_dir in sys.path:
    sys.path.remove(_fireai_dir)

# Clear cached 'core' module if it resolved to fireai/core/ instead of project root
if 'core' in sys.modules:
    mod_file = getattr(sys.modules['core'], '__file__', '')
    if mod_file and 'fireai/core' in mod_file:
        del sys.modules['core']


# ─── Logging Configuration ──────────────────────────────────────────────────
@pytest.fixture(autouse=True, scope="session")
def _configure_logging():
    """Set up logging for test session with appropriate levels."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # Reduce noise from third-party libraries during tests
    logging.getLogger("ezdxf").setLevel(logging.ERROR)
    logging.getLogger("PIL").setLevel(logging.ERROR)
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)


# ─── Audit Store Reset ─────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_audit_store():
    """
    Reset audit store between tests to prevent state leakage.

    This fixture runs before EVERY test to ensure a clean audit state.
    Without it, audit entries from one test could contaminate another,
    producing false PASS/FAIL results in a safety-critical system.
    """
    try:
        import fireai.core.audit_store as _as
        if hasattr(_as, '_store'):
            _as._store.clear()
        if hasattr(_as, 'reset'):
            _as.reset()
    except (ImportError, AttributeError):
        pass

    # Post-import cleanup (V27: Python re-adds fireai/ to sys.path)
    if _fireai_dir in sys.path:
        sys.path.remove(_fireai_dir)
    if 'core' in sys.modules:
        mod_file = getattr(sys.modules['core'], '__file__', '')
        if mod_file and 'fireai/core' in mod_file:
            del sys.modules['core']

    yield  # Test runs here

    # Cleanup after test
    try:
        import fireai.core.audit_store as _as
        if hasattr(_as, '_store'):
            _as._store.clear()
        if hasattr(_as, 'reset'):
            _as.reset()
    except (ImportError, AttributeError):
        pass


# ─── Geometry Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def safe_room_polygon():
    """
    A valid 10m x 8m rectangular room polygon (Shapely).

    This is a simple, well-formed polygon suitable for basic coverage
    and NFPA compliance tests. Does NOT contain obstructions.
    """
    from shapely.geometry import Polygon
    return Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])


@pytest.fixture
def large_room_polygon():
    """
    A valid 30m x 30m room (atrium/lobby scale).

    At 900 m2, this tests detector placement in spaces requiring
    multiple detectors per NFPA 72 spacing rules.
    """
    from shapely.geometry import Polygon
    return Polygon([(0, 0), (30, 0), (30, 30), (0, 30)])


@pytest.fixture
def corridor_polygon():
    """
    A 2m x 20m corridor polygon.

    Tests corridor-specific NFPA 72 spacing rules (narrow width).
    """
    from shapely.geometry import Polygon
    return Polygon([(0, 0), (20, 0), (20, 2), (0, 2)])


@pytest.fixture
def l_shaped_polygon():
    """
    An L-shaped room polygon.

    Tests coverage calculations for non-rectangular geometries
    where a single detector may not cover all corners.
    """
    from shapely.geometry import Polygon
    return Polygon([
        (0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)
    ])


@pytest.fixture
def sample_obstruction():
    """
    A 2m x 2m obstruction polygon inside a room.

    Obstructions create dead air spaces and require detectors
    to be placed away from them per NFPA 72.
    """
    from shapely.geometry import Polygon
    return Polygon([(4, 4), (6, 4), (6, 6), (4, 6)])


# ─── NFPA 72 Standard Value Fixtures ───────────────────────────────────────

@pytest.fixture
def smoke_detector_radius():
    """
    NFPA 72-2022 coverage radius for smoke detectors.

    R = 0.7 x S = 0.7 x 9.1m = 6.37m
    Reference: NFPA 72-2022 Section 17.7.4.2.3.1
    """
    return 6.37


@pytest.fixture
def heat_detector_radius():
    """
    NFPA 72-2022 coverage radius for heat detectors.

    R = 0.7 x S = 0.7 x 7.0m = 4.9m
    Reference: NFPA 72-2022 Section 17.7.3.2.3.1
    """
    return 4.9


@pytest.fixture
def max_smoke_spacing():
    """
    NFPA 72-2022 maximum spacing for smoke detectors.

    Reference: NFPA 72-2022 Section 17.7.4.2.3.1
    """
    return 9.1


@pytest.fixture
def max_heat_spacing():
    """
    NFPA 72-2022 maximum spacing for heat detectors.

    Reference: NFPA 72-2022 Section 17.7.3.2.3.1
    """
    return 7.0


# ─── Electrical Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def standard_wire_resistances():
    """
    NEC Chapter 9 Table 8 — DC resistance for common fire alarm wire gauges.

    Values in ohms per 1000 feet at 25C.
    Reference: NFPA 70-2023 (NEC) Chapter 9, Table 8
    """
    return {
        "AWG_18": 8.082,
        "AWG_16": 5.074,
        "AWG_14": 3.186,
        "AWG_12": 2.003,
        "AWG_10": 1.258,
    }


@pytest.fixture
def standard_supply_voltages():
    """
    Standard fire alarm power supply voltages per NFPA 72.

    Reference: NFPA 72-2022 Chapter 10
    """
    return {
        "24VDC": 24.0,
        "12VDC": 12.0,
        "min_nac_voltage": 16.0,  # Minimum NAC operating voltage (2/3 of 24V)
    }


# ─── Environment Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def clean_env(monkeypatch):
    """
    Provides a clean environment with no API keys or secrets.

    Use this fixture for tests that should NOT depend on external
    services or environment variables.
    """
    env_keys = [
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "FIREAI_API_KEY",
        "FIREAI_EVIDENCE_HMAC_KEY",
        "AUDIT_HMAC_KEY",
        "FIREAI_MEMORY_LLM_PROVIDER",
        "FIREAI_MEMORY_LLM_MODEL",
        "FIREAI_ENV",
        "CORS_ORIGINS",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def test_env(clean_env, monkeypatch):
    """
    Test environment with safe, non-production configuration.

    Provides deterministic values for environment-dependent code
    without requiring real API keys or external services.
    """
    monkeypatch.setenv("FIREAI_ENV", "development")
    monkeypatch.setenv("FIREAI_API_KEY", "test-api-key-for-testing-only")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    return {
        "env": "development",
        "api_key": "test-api-key-for-testing-only",  # NOSONAR: S6418 — synthetic test fixture, not a real secret  # NOSONAR — S7632: test function documented via class name / module path
    }


@pytest.fixture
def temp_directory():
    """
    Temporary directory that is automatically cleaned up after the test.

    Use for tests that need to write files (logs, databases, reports).
    """
    with tempfile.TemporaryDirectory(prefix="fireai_test_") as tmpdir:
        yield Path(tmpdir)


# ─── Database Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def in_memory_db():
    """
    In-memory SQLite database for testing.

    No file I/O, automatic cleanup. Use for tests that need
    database operations without persistence.
    """
    try:
        from fireai.core.database import UniversalDataModel
        db = UniversalDataModel(db_path=":memory:")
        yield db
        if hasattr(db, 'close'):
            db.close()
    except ImportError:
        pytest.skip("UniversalDataModel not available")


# ─── Safety-Critical Markers ────────────────────────────────────────────────

def pytest_collection_modifyitems(config, items):
    """
    Automatically mark tests based on their file location.

    Tests in files containing 'security' get marked as security tests.
    Tests in files containing 'safety' get marked as safety_critical.
    """
    for item in items:
        filepath = str(item.fspath)
        if "security" in filepath:
            item.add_marker(pytest.mark.security)
        if "safety" in filepath:
            item.add_marker(pytest.mark.safety_critical)
