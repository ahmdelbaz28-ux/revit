"""env_config.py — Environment Configuration with Validation
==========================================================
Replaces raw .env parsing with validated, fail-fast configuration.

FIXED (W-04): DATABASE_URL was hardcoded to /home/z/... (developer's
  personal path). In any other environment this silently fails.
  Fix: validate at startup, provide safe defaults, log clearly.

Usage:
    from fireai.env_config import config
    model = UniversalDataModel(config.database_path)
"""

from __future__ import annotations

import logging
import os
import pathlib
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

# Load .env file if python-dotenv is available (optional dependency)
try:
    from dotenv import load_dotenv

    load_dotenv(override=False)  # Never override real environment variables
except ImportError:
    pass  # dotenv is optional


@dataclass(frozen=True)
class FireAIConfig:
    """Validated, immutable application configuration.

    All values sourced from environment variables with safe defaults.
    Validation runs at construction — no invalid config object can exist.

    V80: Added Langfuse observability configuration fields.
    Langfuse is OPTIONAL — all fields have safe defaults that disable
    observability when keys are not set. This is by design: Langfuse
    is observability, not control. Pipeline MUST work without it.
    """

    database_path: str
    environment: Literal["development", "testing", "production"]
    log_level: str
    max_batch_size: int
    enable_wal: bool
    coverage_threshold_pct: float
    langfuse_enabled: bool
    langfuse_host: str

    def __post_init__(self) -> None:
        # Validate database path is writable (unless :memory: or testing)
        if self.database_path not in (":memory:",) and self.environment != "testing":
            db_dir = pathlib.Path(self.database_path).parent
            if not db_dir.exists():
                try:
                    db_dir.mkdir(parents=True, exist_ok=True)
                    logger.info("Created database directory: %s", db_dir)
                except OSError as exc:
                    raise ValueError(
                        f"Cannot create database directory '{db_dir}': {exc}. Set FIREAI_DB_PATH to a writable path."
                    ) from exc

        # Coverage threshold sanity — NFPA 72 requires 100%
        if not (90.0 <= self.coverage_threshold_pct <= 100.0):
            raise ValueError(
                f"FIREAI_COVERAGE_THRESHOLD_PCT must be between 90.0 and 100.0, "
                f"got {self.coverage_threshold_pct}. "
                "NFPA 72 requires 100% coverage — thresholds below 99.0 require FPE justification."
            )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"


def _load_config() -> FireAIConfig:
    """Load and validate configuration from environment variables."""

    def _env(key: str, default: str) -> str:
        val = os.environ.get(key, default).strip()
        if not val:
            return default
        return val

    def _env_bool(key: str, default: bool) -> bool:
        val = os.environ.get(key, "").strip().lower()
        if val in ("1", "true", "yes"):
            return True
        if val in ("0", "false", "no"):
            return False
        return default

    def _env_int(key: str, default: int, min_val: int, max_val: int) -> int:
        raw = os.environ.get(key, "").strip()
        if not raw:
            return default
        try:
            val = int(raw)
        except ValueError as exc:
            raise ValueError(f"Environment variable {key}='{raw}' must be an integer.") from exc
        if not (min_val <= val <= max_val):
            raise ValueError(f"{key}={val} out of range [{min_val}, {max_val}].")
        return val

    def _env_float(key: str, default: float, min_val: float, max_val: float) -> float:
        raw = os.environ.get(key, "").strip()
        if not raw:
            return default
        try:
            val = float(raw)
        except ValueError as exc:
            raise ValueError(f"Environment variable {key}='{raw}' must be a float.") from exc
        if not (min_val <= val <= max_val):
            raise ValueError(f"{key}={val} out of range [{min_val}, {max_val}].")
        return val

    # Detect personal developer paths and warn loudly
    raw_db_path = os.environ.get("FIREAI_DB_PATH", "").strip()
    if raw_db_path.startswith("/home/") or raw_db_path.startswith("C:\\Users\\"):
        logger.warning(
            "FIREAI_DB_PATH appears to be a developer personal path: '%s'. "
            "In production, use an absolute server path like /var/fireai/data/fireai.db",
            raw_db_path,
        )

    environment = _env("FIREAI_ENV", "development")
    if environment not in ("development", "testing", "production"):
        raise ValueError(f"FIREAI_ENV='{environment}' is invalid. Must be one of: development, testing, production.")

    # Safe default DB path — relative to CWD, always writable in dev
    default_db_path = ":memory:" if environment == "testing" else "./data/fireai.db"
    database_path = raw_db_path or default_db_path

    # V80: Langfuse observability configuration
    # Langfuse is OBSERVABILITY — not required for pipeline execution
    langfuse_public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    langfuse_secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    langfuse_host = _env("LANGFUSE_HOST", "https://cloud.langfuse.com")
    langfuse_explicitly_enabled = _env_bool("LANGFUSE_ENABLED", True)
    # Auto-detect: enabled if both keys are present
    langfuse_enabled = langfuse_explicitly_enabled and bool(langfuse_public_key) and bool(langfuse_secret_key)

    cfg = FireAIConfig(
        database_path=database_path,
        environment=environment,  # type: ignore[arg-type]
        log_level=_env("FIREAI_LOG_LEVEL", "INFO").upper(),
        max_batch_size=_env_int("FIREAI_MAX_BATCH_SIZE", 500, 10, 5000),
        enable_wal=_env_bool("FIREAI_ENABLE_WAL", True),
        coverage_threshold_pct=_env_float("FIREAI_COVERAGE_THRESHOLD_PCT", 99.0, 90.0, 100.0),
        langfuse_enabled=langfuse_enabled,
        langfuse_host=langfuse_host,
    )

    logger.info(
        "FireAI configuration loaded: env=%s, db=%s, coverage_threshold=%.2f%%, langfuse=%s",
        cfg.environment,
        cfg.database_path,
        cfg.coverage_threshold_pct,
        "ENABLED" if cfg.langfuse_enabled else "disabled",
    )
    return cfg


# Module-level singleton — import and use directly
config: FireAIConfig = _load_config()
