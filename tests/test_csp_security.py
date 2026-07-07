# NOSONAR
"""
tests/test_csp_security.py — Content-Security-Policy Header Tests
==================================================================
Validates the _build_csp() function in backend/app.py.

V119 FIX (Finding #4): Production default for CSP_UNSAFE_EVAL is now
"false" (secure-by-default). Development default remains "true" for DX.

SAFETY: A safety-critical fire alarm engineering UI must not be vulnerable
to XSS amplification via 'unsafe-eval'. Modern frontend libraries
(recharts ≥2.x, three.js ≥0.150) work without it in production builds.

This file ensures the secure default behavior cannot be silently regressed.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Import _build_csp WITHOUT triggering backend.app's heavy import chain
# (which loads all routers + database + core modules — slow and brittle).
# We exec just the function definition from backend/app.py by parsing the
# source and extracting the _build_csp function + its dependencies.
import types

import pytest

_APP_PATH = _PROJECT_ROOT / "backend" / "app.py"


def _load_build_csp_in_isolation():
    """
    Load _build_csp() from backend/app.py without the rest of app.py.

    Uses ast to extract the function and its module-level constants
    (logger, etc.). This avoids the 700+ lines of router imports.
    """
    import ast
    source = _APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Collect the _build_csp FunctionDef
    build_csp_node = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_build_csp":
            build_csp_node = node
            break
    if build_csp_node is None:
        raise RuntimeError("Could not find _build_csp() in backend/app.py")

    # Minimal module containing only what _build_csp needs: os + logger
    module = types.ModuleType("backend_app_csp_isolated")
    exec("import os; import logging; logger = logging.getLogger('backend.app')",
         module.__dict__)
    # Compile and execute just the function definition
    func_code = compile(ast.Module(body=[build_csp_node], type_ignores=[]),
                        filename=str(_APP_PATH), mode="exec")
    exec(func_code, module.__dict__)
    return module._build_csp


_build_csp = _load_build_csp_in_isolation()


# ═══════════════════════════════════════════════════════════════════════════════
# V119 — Environment-Aware Default Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCSPEnvironmentAwareDefaults:
    """V119 FIX: CSP_UNSAFE_EVAL default depends on FIREAI_ENV."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        """Each test starts with NO CSP_UNSAFE_EVAL env var set."""
        monkeypatch.delenv("CSP_UNSAFE_EVAL", raising=False)
        # Also reset FIREAI_ENV between tests
        return  # NOSONAR - python:S3626

    def test_production_defaults_to_no_unsafe_eval(self, monkeypatch):
        """
        V119 FIX: With FIREAI_ENV=production and CSP_UNSAFE_EVAL unset,
        the CSP must NOT include 'unsafe-eval' (secure-by-default).
        """
        monkeypatch.setenv("FIREAI_ENV", "production")
        csp = _build_csp()
        assert "'unsafe-eval'" not in csp, (
            f"V119 REGRESSION: production CSP contains 'unsafe-eval' by default! CSP: {csp}"
        )
        # V140 FIX: production no longer includes 'unsafe-inline' for scripts.
        # Only 'self' is allowed for script-src in production (React doesn't
        # need inline scripts). style-src still has 'unsafe-inline' (Tailwind CSS).
        assert "script-src 'self'" in csp
        assert "'unsafe-inline'" not in csp.split("style-src")[0]  # not in script-src

    def test_production_unset_env_var_also_secure(self, monkeypatch):
        """Same as above but using FIREAI_ENV default fallback."""
        monkeypatch.delenv("FIREAI_ENV", raising=False)
        # _build_csp uses os.getenv("FIREAI_ENV", "production") so unset → production
        csp = _build_csp()
        assert "'unsafe-eval'" not in csp

    def test_development_defaults_to_unsafe_eval_allowed(self, monkeypatch):
        """
        V119: Development environment preserves DX (Vite/HMR needs eval).
        With FIREAI_ENV=development and CSP_UNSAFE_EVAL unset, eval IS allowed.
        """
        monkeypatch.setenv("FIREAI_ENV", "development")
        csp = _build_csp()
        assert "'unsafe-eval'" in csp, (
            f"V119: development CSP must allow unsafe-eval by default for HMR. CSP: {csp}"
        )


class TestCSPExplicitOverrides:
    """V119: Operators must be able to explicitly override either default."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("CSP_UNSAFE_EVAL", raising=False)
        return  # NOSONAR - python:S3626

    def test_production_can_opt_in_to_unsafe_eval(self, monkeypatch):
        """
        V119: Operator may explicitly enable unsafe-eval in production
        (accepting the documented risk).
        """
        monkeypatch.setenv("FIREAI_ENV", "production")
        monkeypatch.setenv("CSP_UNSAFE_EVAL", "true")
        csp = _build_csp()
        assert "'unsafe-eval'" in csp

    def test_development_can_opt_out_of_unsafe_eval(self, monkeypatch):
        """
        V119: Operator may explicitly disable unsafe-eval even in dev
        (for testing production CSP locally).
        """
        monkeypatch.setenv("FIREAI_ENV", "development")
        monkeypatch.setenv("CSP_UNSAFE_EVAL", "false")
        csp = _build_csp()
        assert "'unsafe-eval'" not in csp

    @pytest.mark.parametrize("truthy", ["true", "TRUE", "True", "1", "yes", "YES", "Yes"])
    def test_truthy_values_enable_unsafe_eval(self, monkeypatch, truthy):
        """Backward compat: same truthy parsing as pre-V119."""
        monkeypatch.setenv("FIREAI_ENV", "production")
        monkeypatch.setenv("CSP_UNSAFE_EVAL", truthy)
        csp = _build_csp()
        assert "'unsafe-eval'" in csp, f"truthy value {truthy!r} should enable"

    @pytest.mark.parametrize("falsy", ["false", "FALSE", "0", "no", "", "anything-else"])
    def test_falsy_values_disable_unsafe_eval(self, monkeypatch, falsy):
        """Anything not in the truthy set disables eval (fail-safe parsing)."""
        monkeypatch.setenv("FIREAI_ENV", "production")
        monkeypatch.setenv("CSP_UNSAFE_EVAL", falsy)
        csp = _build_csp()
        assert "'unsafe-eval'" not in csp, f"falsy value {falsy!r} should disable"


class TestCSPLoggingEscalation:
    """V119: Production-with-unsafe-eval logs at ERROR level (not WARNING)."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("CSP_UNSAFE_EVAL", raising=False)
        return  # NOSONAR - python:S3626

    def test_production_unsafe_eval_logs_at_error_level(self, monkeypatch, caplog):
        """
        V119 FIX: Escalated from WARNING → ERROR.
        Misconfiguration must not hide in log noise.
        """
        monkeypatch.setenv("FIREAI_ENV", "production")
        monkeypatch.setenv("CSP_UNSAFE_EVAL", "true")
        with caplog.at_level(logging.ERROR, logger="backend.app"):
            _build_csp()
        error_messages = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("unsafe-eval" in m for m in error_messages), (
            f"Expected ERROR log mentioning unsafe-eval, got: {error_messages}"
        )

    def test_development_no_error_log(self, monkeypatch, caplog):
        """Development unsafe-eval is expected behavior — no ERROR log."""
        monkeypatch.setenv("FIREAI_ENV", "development")
        monkeypatch.setenv("CSP_UNSAFE_EVAL", "true")
        with caplog.at_level(logging.ERROR, logger="backend.app"):
            _build_csp()
        error_messages = [r.message for r in caplog.records
                          if r.levelno >= logging.ERROR and "unsafe-eval" in r.message]
        assert not error_messages, (
            f"Development unsafe-eval should NOT log at ERROR. Got: {error_messages}"
        )

    def test_secure_default_no_log_noise(self, monkeypatch, caplog):
        """When secure default applies (no env var, production), no error."""
        monkeypatch.setenv("FIREAI_ENV", "production")
        # CSP_UNSAFE_EVAL deliberately unset
        with caplog.at_level(logging.ERROR, logger="backend.app"):
            _build_csp()
        error_messages = [r.message for r in caplog.records
                          if r.levelno >= logging.ERROR and "unsafe-eval" in r.message]
        assert not error_messages, "Secure default should produce no error log"


class TestCSPStructuralIntegrity:
    """V119: Don't break the rest of the CSP while fixing unsafe-eval."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("CSP_UNSAFE_EVAL", raising=False)
        monkeypatch.delenv("CSP_CONNECT_SRC", raising=False)
        return  # NOSONAR - python:S3626

    def test_csp_has_default_src(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "production")
        csp = _build_csp()
        assert "default-src 'self'" in csp

    def test_csp_has_script_src(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "production")
        csp = _build_csp()
        assert "script-src 'self'" in csp

    def test_csp_has_style_src(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "production")
        csp = _build_csp()
        assert "style-src 'self' 'unsafe-inline'" in csp

    def test_csp_has_img_src(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "production")
        csp = _build_csp()
        assert "img-src 'self' data: blob:" in csp

    def test_csp_has_connect_src_self(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "production")
        csp = _build_csp()
        assert "connect-src 'self'" in csp

    def test_csp_development_allows_localhost_connect(self, monkeypatch):
        """Pre-existing behavior preserved: dev allows localhost websockets."""
        monkeypatch.setenv("FIREAI_ENV", "development")
        csp = _build_csp()
        assert "http://localhost" in csp or "ws://localhost" in csp

    def test_csp_production_connect_src_custom(self, monkeypatch):
        """Pre-existing behavior preserved: prod uses CSP_CONNECT_SRC."""
        monkeypatch.setenv("FIREAI_ENV", "production")
        monkeypatch.setenv("CSP_CONNECT_SRC", "https://api.example.com")
        csp = _build_csp()
        assert "https://api.example.com" in csp
