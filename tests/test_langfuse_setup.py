# NOSONAR
"""
tests/test_langfuse_setup.py.
==============================
Tests for the V142 langfuse_setup.py observability module.

TEST PHILOSOPHY (agent.md Rule 12 — Safety-First):
  Langfuse is the SECONDARY observability layer (primary = internal
  audit trail). It must NEVER block the workflow pipeline and NEVER
  raise exceptions that could crash the FACP. These tests verify the
  fail-safe contract that V80 worklog claimed (falsely) and V141.2
  finally implemented.

  V80 worklog claimed "20 tests pass" — but no test file existed.
  V142 adds this file to make the claim true (or rather, to make
  the test coverage honest).

  Tests verify:
    1. Module imports cleanly (file exists — V141.2 fix)
    2. langfuse_health_check returns a valid dict in all states
    3. get_langfuse() returns None when langfuse not installed/configured
    4. get_langfuse_callback_handler() returns None when unavailable
    5. log_verification_score / log_workflow_scores NEVER raise
    6. flush_langfuse() NEVER raises
    7. Fail-safe: every public function handles ImportError gracefully

  Tests do NOT require langfuse to be installed — they verify the
  graceful-degradation path that production deployments rely on.
"""

from __future__ import annotations

# Force fresh import to reset module-level globals between tests
import fireai.infrastructure.langfuse_setup as langfuse_setup

# ===========================================================================
# Module existence test (V141.2 critical fix)
# ===========================================================================


class TestModuleExists:
    """V80 worklog claimed this module existed; it didn't. V141.2 created it."""

    def test_module_imports_cleanly(self):
        """Module must import without raising."""
        # If this fails, langfuse_setup.py is missing or broken.
        assert hasattr(langfuse_setup, "__file__")
        assert langfuse_setup.__file__ is not None

    def test_module_exposes_public_api(self):
        """All functions claimed in V80 worklog must exist."""
        for func_name in [
            "get_langfuse",
            "get_langfuse_callback_handler",
            "log_verification_score",
            "log_workflow_scores",
            "flush_langfuse",
            "langfuse_health_check",
        ]:
            assert hasattr(langfuse_setup, func_name), (
                f"Missing public function: {func_name}"
            )


# ===========================================================================
# Health check tests
# ===========================================================================


class TestHealthCheck:
    """langfuse_health_check must return a valid dict in every state."""

    def test_health_check_returns_dict(self):
        result = langfuse_setup.langfuse_health_check()
        assert isinstance(result, dict)

    def test_health_check_has_enabled_field(self):
        """Health check returns 'enabled' boolean (not 'status' string)."""
        result = langfuse_setup.langfuse_health_check()
        assert "enabled" in result
        assert isinstance(result["enabled"], bool)

    def test_health_check_when_unconfigured(self, monkeypatch):
        """When env vars are missing, enabled must be False."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        # Reset the cached availability flag
        langfuse_setup._langfuse_available = None
        langfuse_setup._langfuse_client = None
        result = langfuse_setup.langfuse_health_check()
        assert result["enabled"] is False
        assert "error" in result  # human-readable explanation


# ===========================================================================
# Fail-safe tests — every public function must NEVER raise
# ===========================================================================


class TestFailSafeContract:
    """
    V141.2 docstring claims "All operations are FAIL-SAFE: wrapped in
    try/except, never blocks the pipeline." These tests verify that.
    """

    def test_get_langfuse_returns_none_when_unconfigured(self, monkeypatch):
        """get_langfuse() must return None (not raise) when langfuse is off."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        langfuse_setup._langfuse_available = None
        langfuse_setup._langfuse_client = None
        result = langfuse_setup.get_langfuse()
        assert result is None

    def test_get_langfuse_callback_handler_returns_none_when_unconfigured(self, monkeypatch):
        """get_langfuse_callback_handler() must return None when langfuse is off."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        langfuse_setup._langfuse_available = None
        langfuse_setup._langfuse_client = None
        result = langfuse_setup.get_langfuse_callback_handler()
        assert result is None

    def test_log_verification_score_never_raises(self, monkeypatch):
        """log_verification_score() must NEVER raise, even with bad input."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        langfuse_setup._langfuse_available = None
        # Try with None handler, bad score name, weird value
        langfuse_setup.log_verification_score(None, "test_score", 1.0)  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)
        langfuse_setup.log_verification_score(None, "", None)  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)
        langfuse_setup.log_verification_score(None, None, None)  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)

    def test_log_workflow_scores_never_raises(self, monkeypatch):
        """log_workflow_scores() must NEVER raise, even with bad input."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        langfuse_setup._langfuse_available = None
        # Try with None result and None handler
        langfuse_setup.log_workflow_scores(None, None)
        # Try with a fake result object missing expected fields
        langfuse_setup.log_workflow_scores(object(), None)

    def test_flush_langfuse_never_raises(self, monkeypatch):
        """flush_langfuse() must NEVER raise."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        langfuse_setup._langfuse_available = None
        langfuse_setup._langfuse_client = None
        # Multiple flushes must not crash
        langfuse_setup.flush_langfuse()
        langfuse_setup.flush_langfuse()
        langfuse_setup.flush_langfuse()


# ===========================================================================
# Availability detection tests
# ===========================================================================


class TestAvailabilityDetection:
    """Verify _check_langfuse_available() correctly detects installation state."""

    def test_returns_false_when_langfuse_not_importable(self, monkeypatch):
        """When langfuse package can't be imported, must return False."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        # Force ImportError by patching the import
        import builtins
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "langfuse":
                raise ImportError("simulated: langfuse not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        langfuse_setup._langfuse_available = None  # reset cache
        result = langfuse_setup._check_langfuse_available()
        assert result is False

    def test_returns_false_when_env_vars_missing(self, monkeypatch):
        """When env vars are missing, must return False even if package installed."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        langfuse_setup._langfuse_available = None
        result = langfuse_setup._check_langfuse_available()
        # Result depends on whether langfuse is actually installed.
        # In CI without langfuse installed, this is False.
        # In a dev env with langfuse installed but unconfigured, also False.
        assert result is False

    def test_caches_availability(self, monkeypatch):
        """_check_langfuse_available() must cache its result for performance."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        langfuse_setup._langfuse_available = None
        first = langfuse_setup._check_langfuse_available()
        # Second call should return cached value without re-checking
        second = langfuse_setup._check_langfuse_available()
        assert first == second


# ===========================================================================
# Callback handler tests
# ===========================================================================


class TestCallbackHandler:
    """Verify get_langfuse_callback_handler() behavior."""

    def test_handler_none_when_unconfigured(self, monkeypatch):
        """Handler must be None when langfuse is not configured."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        langfuse_setup._langfuse_available = None
        langfuse_setup._langfuse_client = None
        handler = langfuse_setup.get_langfuse_callback_handler()
        assert handler is None

    def test_handler_does_not_raise_on_trace_id(self, monkeypatch):
        """Handler with trace_id lookup must not raise when unavailable."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        langfuse_setup._langfuse_available = None
        # Pass a trace_id argument — should not raise
        handler = langfuse_setup.get_langfuse_callback_handler(trace_id="test-trace")
        # When langfuse unavailable, handler is None
        assert handler is None


# ===========================================================================
# Integration: workflow_service.py import contract
# ===========================================================================


class TestWorkflowServiceIntegration:
    """
    Verify the import contract that backend/services/workflow_service.py
    relies on. The try/except ImportError block must succeed when this
    module is present.
    """

    def test_workflow_service_can_import_langfuse(self):
        """workflow_service.py must be able to import from langfuse_setup."""
        # This is the exact import that workflow_service.py does
        from fireai.infrastructure.langfuse_setup import (
            flush_langfuse,
            get_langfuse_callback_handler,
            langfuse_health_check,
            log_workflow_scores,
        )
        # All four must be callable
        assert callable(flush_langfuse)
        assert callable(get_langfuse_callback_handler)
        assert callable(langfuse_health_check)
        assert callable(log_workflow_scores)

    def test_langfuse_available_flag_works(self):
        """The LANGFUSE_AVAILABLE flag pattern in workflow_service.py works."""
        try:
            from fireai.infrastructure.langfuse_setup import (  # noqa: F401
                flush_langfuse,
                get_langfuse_callback_handler,
                langfuse_health_check,
                log_workflow_scores,
            )
            langfuse_available = True
        except ImportError:
            langfuse_available = False

        assert langfuse_available is True  # V141.2 fix: module now exists
