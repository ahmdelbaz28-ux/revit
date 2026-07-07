# NOSONAR
"""
test_env_config.py — Tests for fireai/env_config.py.

Verifies configuration loading, validation, defaults, and environment handling.
"""
from __future__ import annotations

import pytest

from fireai.env_config import _load_config


class TestFireAIConfigDefaults:
    """Default configuration values when environment is overridden."""

    def test_development_defaults(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "development")
        monkeypatch.setenv("FIREAI_LOG_LEVEL", "INFO")
        monkeypatch.setenv("FIREAI_MAX_BATCH_SIZE", "500")
        monkeypatch.setenv("FIREAI_ENABLE_WAL", "true")
        monkeypatch.setenv("FIREAI_COVERAGE_THRESHOLD_PCT", "99.0")
        cfg = _load_config()
        assert cfg.environment == "development"
        assert cfg.log_level == "INFO"
        assert cfg.max_batch_size == 500
        assert cfg.enable_wal is True
        assert pytest.approx(cfg.coverage_threshold_pct) == pytest.approx(99.0)

    def test_is_production_property(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "production")
        cfg = _load_config()
        assert cfg.is_production is True
        assert cfg.is_testing is False

    def test_is_testing_property(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "testing")
        cfg = _load_config()
        assert cfg.is_testing is True
        assert cfg.is_production is False


class TestFireAIConfigValidation:
    """Validation of configuration values."""

    def test_invalid_environment_raises(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "invalid_env")
        with pytest.raises(ValueError, match="FIREAI_ENV"):
            _load_config()

    def test_coverage_threshold_out_of_range_raises(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "development")
        monkeypatch.setenv("FIREAI_COVERAGE_THRESHOLD_PCT", "85.0")
        with pytest.raises(ValueError, match="FIREAI_COVERAGE_THRESHOLD_PCT"):
            _load_config()

    def test_coverage_threshold_100_ok(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "development")
        monkeypatch.setenv("FIREAI_COVERAGE_THRESHOLD_PCT", "100.0")
        cfg = _load_config()
        assert cfg.coverage_threshold_pct == pytest.approx(100.0)


class TestFireAIConfigDatabasePath:
    """Database path handling."""

    def test_testing_uses_memory_db(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "testing")
        cfg = _load_config()
        assert cfg.database_path == ":memory:"

    def test_custom_db_path_is_used(self, monkeypatch, tmp_path):
        custom = str(tmp_path / "custom.db")
        monkeypatch.setenv("FIREAI_ENV", "development")
        monkeypatch.setenv("FIREAI_DB_PATH", custom)
        cfg = _load_config()
        assert cfg.database_path == custom


class TestLangfuseConfig:
    """Langfuse observability configuration."""

    def test_langfuse_disabled_without_keys(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "development")
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        cfg = _load_config()
        assert cfg.langfuse_enabled is False

    def test_langfuse_host_default(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "development")
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        cfg = _load_config()
        assert cfg.langfuse_host == "https://cloud.langfuse.com"

    def test_langfuse_custom_host(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "development")
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3000")
        cfg = _load_config()
        assert cfg.langfuse_host == "http://localhost:3000"
