from __future__ import annotations

import dataclasses
import os
import shutil
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Literal

START_TIME = time.monotonic()


@dataclass
class HealthStatus:
    status: Literal["healthy", "degraded", "unhealthy"]
    checks: dict[str, dict[str, Any]]
    version: str
    uptime_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), indent=2)


CheckFn = Callable[[], Dict[str, Any]]


class HealthRegistry:
    def __init__(self, version: str = "1.0.0") -> None:
        self._checks: list[dict[str, Any]] = []
        self._version = version

    def register(self, name: str, check: CheckFn, critical: bool = True) -> None:
        self._checks.append(
            {
                "name": name,
                "check": check,
                "critical": critical,
            }
        )

    def check_all(self) -> HealthStatus:
        results: dict[str, dict[str, Any]] = {}
        has_critical_failure = False
        has_degraded = False

        for entry in self._checks:
            name = entry["name"]
            critical = entry["critical"]
            try:
                result = entry["check"]()
                results[name] = result
                ok = result.get("ok", False)
                if critical and not ok:
                    has_critical_failure = True
                if not ok:
                    has_degraded = True
            except Exception as exc:
                results[name] = {
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": str(exc),
                }
                if critical:
                    has_critical_failure = True
                has_degraded = True

        if has_critical_failure:
            status: Literal["healthy", "degraded", "unhealthy"] = "unhealthy"
        elif has_degraded:
            status = "degraded"
        else:
            status = "healthy"

        return HealthStatus(
            status=status,
            checks=results,
            version=self._version,
            uptime_seconds=time.monotonic() - START_TIME,
        )


def check_redis(
    host: str = "localhost", port: int = 6379, password: str | None = None
) -> dict[str, Any]:
    try:
        import redis as redis_mod

        r = redis_mod.Redis(host=host, port=port, password=password, socket_timeout=5)
        info = r.info()
        return {
            "ok": True,
            "connected_slaves": info.get("connected_slaves", 0),
            "used_memory_human": info.get("used_memory_human", ""),
            "uptime_in_seconds": info.get("uptime_in_seconds", 0),
        }
    except ImportError:
        return {"ok": False, "error": "redis package not installed"}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def check_database(dsn: str | None = None) -> dict[str, Any]:
    try:
        from sqlalchemy import create_engine, text

        dsn = dsn or os.getenv("DATABASE_URL", "sqlite:///data/fireai.db")
        engine = create_engine(
            dsn, connect_args={"check_same_thread": False} if "sqlite" in dsn else {}
        )
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            return {"ok": row is not None and row[0] == 1, "dsn": dsn.split("://")[0] + "://***"}
    except ImportError:
        return {"ok": False, "error": "sqlalchemy not installed"}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def check_disk_space(path: str | None = None, threshold_pct: float = 90.0) -> dict[str, Any]:
    path = path or os.path.dirname(os.path.abspath(__file__))
    try:
        usage = shutil.disk_usage(path)
        pct = (usage.used / usage.total) * 100
        return {
            "ok": pct < threshold_pct,
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "used_pct": round(pct, 1),
            "threshold_pct": threshold_pct,
        }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def check_memory(threshold_pct: float = 90.0) -> dict[str, Any]:
    try:
        import psutil

        mem = psutil.virtual_memory()
        return {
            "ok": mem.percent < threshold_pct,
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_pct": mem.percent,
            "threshold_pct": threshold_pct,
        }
    except ImportError:
        return {"ok": False, "error": "psutil not installed"}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def check_api_reachability(url: str, timeout: int = 10) -> dict[str, Any]:
    try:
        import requests

        resp = requests.get(url, timeout=timeout)
        return {
            "ok": resp.ok,
            "status_code": resp.status_code,
            "latency_ms": round(resp.elapsed.total_seconds() * 1000, 1),
        }
    except ImportError:
        return {"ok": False, "error": "requests not installed"}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


_default_registry: HealthRegistry | None = None


def get_default_registry(version: str = "1.0.0") -> HealthRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = HealthRegistry(version=version)
    return _default_registry
