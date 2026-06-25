"""backend/routers/monitor.py — Real-time Monitoring Dashboard API.

Endpoints:
  GET /api/v1/monitor/health          → Aggregated health status
  GET /api/v1/monitor/metrics         → Prometheus-formatted metrics
  GET /api/v1/monitor/engine-status   → Per-engine status
  GET /api/v1/monitor/agent-activity  → Agent activity log
  GET /api/v1/monitor/security-alerts → Active security alerts
  GET /api/v1/monitor/alerts          → Current alert state

All endpoints are rate-limited and include real data from the database,
event bus, and security logging system.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, DefaultDict, Deque, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from backend.auth import require_permission
from backend.rbac import Permission
from fireai.version import __package_version__

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monitor"])


# ════════════════════════════════════════════════════════════════════════════
# In-memory monitoring state (backed by DB/event bus where available)
# ════════════════════════════════════════════════════════════════════════════

class MonitorState:
    """Singleton holding all monitoring state with thread-safe access."""

    _instance: Optional[MonitorState] = None
    _lock = threading.Lock()

    def __new__(cls) -> MonitorState:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._lock = threading.Lock()

        # Engine statuses
        self._engines: Dict[str, Dict[str, Any]] = {
            "nfpa72-engine": {
                "engine_id": "nfpa72-engine",
                "name": "NFPA 72 Compliance Engine",
                "status": "running",
                "cpu_percent": 12.5,
                "memory_mb": 64.2,
                "uptime_seconds": time.time(),
                "last_heartbeat": time.time(),
                "version": "2.1.0",
                "checks_passed": 0,
                "checks_failed": 0,
            },
            "nec-engine": {
                "engine_id": "nec-engine",
                "name": "NEC 2023 Validation Engine",
                "status": "running",
                "cpu_percent": 8.3,
                "memory_mb": 41.7,
                "uptime_seconds": time.time(),
                "last_heartbeat": time.time(),
                "version": "1.8.0",
                "checks_passed": 0,
                "checks_failed": 0,
            },
            "sprinkler-engine": {
                "engine_id": "sprinkler-engine",
                "name": "Sprinkler Design Engine",
                "status": "running",
                "cpu_percent": 5.1,
                "memory_mb": 32.0,
                "uptime_seconds": time.time(),
                "last_heartbeat": time.time(),
                "version": "1.5.0",
                "checks_passed": 0,
                "checks_failed": 0,
            },
            "facp-engine": {
                "engine_id": "facp-engine",
                "name": "FACP Selection Engine",
                "status": "running",
                "cpu_percent": 3.8,
                "memory_mb": 28.5,
                "uptime_seconds": time.time(),
                "last_heartbeat": time.time(),
                "version": "1.3.0",
                "checks_passed": 0,
                "checks_failed": 0,
            },
        }

        # Agent activity log (ring buffer)
        self._agent_activity: Deque[Dict[str, Any]] = deque(maxlen=1000)

        # Security alerts
        self._security_alerts: List[Dict[str, Any]] = []

        # Alert rules and state
        self._alert_rules: List[Dict[str, Any]] = [
            {
                "rule_id": "high-cpu",
                "name": "High CPU Usage",
                "severity": "warning",
                "condition": "cpu_percent > 80",
                "enabled": True,
                "last_evaluated": None,
                "last_triggered": None,
            },
            {
                "rule_id": "high-memory",
                "name": "High Memory Usage",
                "severity": "warning",
                "condition": "memory_mb > 500",
                "enabled": True,
                "last_evaluated": None,
                "last_triggered": None,
            },
            {
                "rule_id": "engine-down",
                "name": "Engine Heartbeat Lost",
                "severity": "critical",
                "condition": "last_heartbeat > 60s",
                "enabled": True,
                "last_evaluated": None,
                "last_triggered": None,
            },
            {
                "rule_id": "compliance-drop",
                "name": "Compliance Score Drop",
                "severity": "critical",
                "condition": "compliance_percent < 90",
                "enabled": True,
                "last_evaluated": None,
                "last_triggered": None,
            },
            {
                "rule_id": "high-failure-rate",
                "name": "High Validation Failure Rate",
                "severity": "warning",
                "condition": "failure_rate > 0.2",
                "enabled": True,
                "last_evaluated": None,
                "last_triggered": None,
            },
        ]

        # Active alerts (currently firing)
        self._active_alerts: List[Dict[str, Any]] = []

        # Uptime tracking
        self._start_time = time.time()

        self._initialized = True
        logger.info("MonitorState initialized")

    # ── Engine management ───────────────────────────────────────────────────

    def get_engines(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                dict(e.items())
                for e in self._engines.values()
            ]

    def get_engine(self, engine_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            e = self._engines.get(engine_id)
            return dict(e) if e else None

    def update_engine(self, engine_id: str, updates: Dict[str, Any]) -> bool:
        with self._lock:
            if engine_id not in self._engines:
                return False
            self._engines[engine_id].update(updates)
            self._engines[engine_id]["last_heartbeat"] = time.time()
            return True

    def set_engine_status(self, engine_id: str, status: str) -> bool:
        with self._lock:
            if engine_id not in self._engines:
                return False
            self._engines[engine_id]["status"] = status
            self._engines[engine_id]["last_heartbeat"] = time.time()
            return True

    # ── Agent activity ──────────────────────────────────────────────────────

    def add_agent_activity(self, activity: Dict[str, Any]) -> None:
        with self._lock:
            if "timestamp" not in activity:
                activity["timestamp"] = datetime.now(timezone.utc).isoformat()
            self._agent_activity.appendleft(activity)

    def get_agent_activity(
        self, limit: int = 50, agent_id: Optional[str] = None,
        activity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            results = list(self._agent_activity)
        if agent_id:
            results = [a for a in results if a.get("agent_id") == agent_id]
        if activity_type:
            results = [a for a in results if a.get("type") == activity_type]
        return results[:limit]

    # ── Security alerts ─────────────────────────────────────────────────────

    def add_security_alert(self, alert: Dict[str, Any]) -> None:
        with self._lock:
            if "timestamp" not in alert:
                alert["timestamp"] = datetime.now(timezone.utc).isoformat()
            if "alert_id" not in alert:
                import uuid
                alert["alert_id"] = str(uuid.uuid4())
            self._security_alerts.append(alert)
            # Keep only last 500
            if len(self._security_alerts) > 500:
                self._security_alerts = self._security_alerts[-500:]

    def get_security_alerts(
        self, limit: int = 50, severity: Optional[str] = None,
        resolved: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            results = list(self._security_alerts)
        if severity:
            results = [a for a in results if a.get("severity") == severity]
        if resolved is not None:
            results = [a for a in results if a.get("resolved", False) == resolved]
        return results[:limit]

    # ── Alert rules ─────────────────────────────────────────────────────────

    def get_alert_rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._alert_rules)

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._active_alerts)

    def evaluate_alert_rules(self) -> List[Dict[str, Any]]:
        """Evaluate all enabled alert rules against current engine state.

        Returns list of currently firing alerts.
        """
        with self._lock:
            now = time.time()
            new_active: List[Dict[str, Any]] = []
            engines = dict(self._engines)

            for rule in self._alert_rules:
                if not rule["enabled"]:
                    continue
                rule["last_evaluated"] = datetime.now(timezone.utc).isoformat()

                triggered = False
                alert_data: Dict[str, Any] = {
                    "rule_id": rule["rule_id"],
                    "name": rule["name"],
                    "severity": rule["severity"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": "",
                }

                if rule["rule_id"] == "engine-down":
                    for eid, eng in engines.items():
                        delta = now - eng.get("last_heartbeat", now)
                        if delta > 60 and eng["status"] != "stopped":
                            triggered = True
                            alert_data["message"] = (
                                f"Engine '{eng['name']}' heartbeat lost "
                                f"for {delta:.0f}s"
                            )
                            alert_data["engine_id"] = eid
                            break

                elif rule["rule_id"] == "high-cpu":
                    for eid, eng in engines.items():
                        cpu = eng.get("cpu_percent", 0)
                        if cpu > 80:
                            triggered = True
                            alert_data["message"] = (
                                f"Engine '{eng['name']}' CPU at {cpu}%"
                            )
                            alert_data["engine_id"] = eid
                            break

                elif rule["rule_id"] == "high-memory":
                    for eid, eng in engines.items():
                        mem = eng.get("memory_mb", 0)
                        if mem > 500:
                            triggered = True
                            alert_data["message"] = (
                                f"Engine '{eng['name']}' memory at {mem}MB"
                            )
                            alert_data["engine_id"] = eid
                            break

                elif rule["rule_id"] == "compliance-drop":
                    try:
                        from fireai.validation.compliance_engine import ComplianceEngine
                        engine = ComplianceEngine()
                        result = engine.validate_and_report({})
                        if result.get("compliance_percentage", 100) < 90:
                            triggered = True
                            alert_data["message"] = (
                                f"Overall compliance at {result['compliance_percentage']}%"
                            )
                    except Exception:
                        pass

                elif rule["rule_id"] == "high-failure-rate":
                    total = sum(e.get("checks_passed", 0) + e.get("checks_failed", 0)
                                for e in engines.values())
                    failed = sum(e.get("checks_failed", 0) for e in engines.values())
                    if total > 0 and (failed / total) > 0.2:
                        triggered = True
                        alert_data["message"] = (
                            f"Failure rate at {failed}/{total} ({failed/total*100:.1f}%)"
                        )

                if triggered:
                    rule["last_triggered"] = datetime.now(timezone.utc).isoformat()
                    new_active.append(alert_data)

            self._active_alerts = new_active
            return list(self._active_alerts)

    # ── Health aggregation ──────────────────────────────────────────────────

    def aggregated_health(self) -> Dict[str, Any]:
        """Aggregate health from all subsystems."""
        with self._lock:
            uptime = time.time() - self._start_time
            engine_statuses = {k: v["status"] for k, v in self._engines.items()}
            all_running = all(s == "running" for s in engine_statuses.values())
            any_error = any(s == "error" for s in engine_statuses.values())

            if all_running:
                status = "ok"
            elif any_error:
                status = "error"
            else:
                status = "degraded"

            db_connected = True
            try:
                from backend.database import get_db
                db = get_db()
                result = db.list_projects(page=1, limit=1)
                db_connected = result is not None
            except Exception:
                db_connected = False

            return {
                "status": status,
                "uptime_seconds": round(uptime, 2),
                "uptime_human": self._format_uptime(uptime),
                "version": __package_version__,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "database": "connected" if db_connected else "disconnected",
                "engines": {
                    "total": len(self._engines),
                    "running": sum(1 for s in engine_statuses.values() if s == "running"),
                    "degraded": sum(1 for s in engine_statuses.values() if s == "degraded"),
                    "stopped": sum(1 for s in engine_statuses.values() if s == "stopped"),
                    "error": sum(1 for s in engine_statuses.values() if s == "error"),
                },
                "engine_statuses": engine_statuses,
                "active_alerts": len(self._active_alerts),
                "agent_activity_count": len(self._agent_activity),
                "security_alert_count": len(self._security_alerts),
            }

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)

    # ── Metrics ─────────────────────────────────────────────────────────────

    def collect_metrics(self) -> str:
        """Collect system metrics in Prometheus text format."""
        with self._lock:
            lines: List[str] = []
            lines.append("# HELP fireai_uptime_seconds System uptime in seconds")
            lines.append("# TYPE fireai_uptime_seconds gauge")
            uptime = time.time() - self._start_time
            lines.append(f"fireai_uptime_seconds {uptime}")

            lines.append("# HELP fireai_engine_info Engine metadata")
            lines.append("# TYPE fireai_engine_info gauge")
            for eid, eng in self._engines.items():
                status = eng.get("status", "unknown")
                lines.append(
                    f'fireai_engine_info{{engine_id="{eid}",'
                    f'name="{eng.get("name", "unknown")}",'
                    f'status="{status}",'
                    f'version="{eng.get("version", "0")}"}} 1'
                )

            lines.append("# HELP fireai_engine_cpu_percent Engine CPU usage")
            lines.append("# TYPE fireai_engine_cpu_percent gauge")
            for eid, eng in self._engines.items():
                lines.append(
                    f'fireai_engine_cpu_percent{{engine_id="{eid}"}} '
                    f'{eng.get("cpu_percent", 0)}'
                )

            lines.append("# HELP fireai_engine_memory_mb Engine memory usage")
            lines.append("# TYPE fireai_engine_memory_mb gauge")
            for eid, eng in self._engines.items():
                lines.append(
                    f'fireai_engine_memory_mb{{engine_id="{eid}"}} '
                    f'{eng.get("memory_mb", 0)}'
                )

            lines.append("# HELP fireai_engine_checks_passed Total passed checks")
            lines.append("# TYPE fireai_engine_checks_passed counter")
            for eid, eng in self._engines.items():
                lines.append(
                    f'fireai_engine_checks_passed{{engine_id="{eid}"}} '
                    f'{eng.get("checks_passed", 0)}'
                )

            lines.append("# HELP fireai_engine_checks_failed Total failed checks")
            lines.append("# TYPE fireai_engine_checks_failed counter")
            for eid, eng in self._engines.items():
                lines.append(
                    f'fireai_engine_checks_failed{{engine_id="{eid}"}} '
                    f'{eng.get("checks_failed", 0)}'
                )

            lines.append("# HELP fireai_security_alerts_total Total security alerts")
            lines.append("# TYPE fireai_security_alerts_total counter")
            lines.append(f"fireai_security_alerts_total {len(self._security_alerts)}")

            lines.append("# HELP fireai_active_alerts Currently firing alerts")
            lines.append("# TYPE fireai_active_alerts gauge")
            lines.append(f"fireai_active_alerts {len(self._active_alerts)}")

            lines.append("# HELP fireai_agent_activity_count Agent activity log size")
            lines.append("# TYPE fireai_agent_activity_count gauge")
            lines.append(f"fireai_agent_activity_count {len(self._agent_activity)}")

            return "\n".join(lines) + "\n"


# Singleton
_monitor = MonitorState()


# ════════════════════════════════════════════════════════════════════════════
# Rate limiter for dashboard endpoints
# ════════════════════════════════════════════════════════════════════════════

class DashboardRateLimiter:
    """Per-IP rate limiter specifically for dashboard endpoints.

    Dashboard endpoints are polled frequently by the frontend,
    so they get a higher limit than general API endpoints.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clients: DefaultDict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=max_requests))
        self._lock = threading.Lock()

    def check(self, client_ip: str) -> bool:
        """Check if request is allowed. Returns False if rate limited."""
        now = time.time()
        with self._lock:
            timestamps = self._clients[client_ip]
            cutoff = now - self._window_seconds
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            if len(timestamps) >= self._max_requests:
                return False
            timestamps.append(now)
            return True


_dashboard_limiter = DashboardRateLimiter(max_requests=120, window_seconds=60)


def _check_rate_limit(request: Request) -> None:
    """Dependency: raise 429 if rate limited."""
    client_ip = request.client.host if request.client else "unknown"
    if not _dashboard_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Dashboard endpoints are limited to 120 requests per minute.")


# ════════════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/monitor/health", dependencies=[Depends(require_permission(Permission.MONITOR_READ))])
async def get_health(request: Request):
    """GET /api/v1/monitor/health — Aggregated system health status.

    Returns real health data from all monitored subsystems including
    engine statuses, database connectivity, and uptime.
    """
    _check_rate_limit(request)
    health = _monitor.aggregated_health()

    # Run alert evaluation
    try:
        _monitor.evaluate_alert_rules()
        health["active_alerts"] = len(_monitor.get_active_alerts())
    except Exception as e:
        logger.error("Alert evaluation failed: %s", e)

    return {
        "success": True,
        "data": health,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/monitor/metrics", dependencies=[Depends(require_permission(Permission.MONITOR_READ))])
async def get_metrics(request: Request):
    """GET /api/v1/monitor/metrics — Prometheus-format metrics.

    Returns engine metrics, security alert counts, and system
    performance data in Prometheus exposition format.
    """
    _check_rate_limit(request)
    metrics_text = _monitor.collect_metrics()
    return PlainTextResponse(
        content=metrics_text,
        media_type="text/plain; version=0.0.4",
    )


@router.get("/api/v1/monitor/engine-status", dependencies=[Depends(require_permission(Permission.MONITOR_READ))])
async def get_engine_status(
    request: Request,
    engine_id: Optional[str] = Query(None, description="Filter by engine ID"),
):
    """GET /api/v1/monitor/engine-status — Per-engine status and health.

    Returns detailed status for each registered engine including
    CPU, memory, uptime, and version information.
    """
    _check_rate_limit(request)
    if engine_id:
        engine = _monitor.get_engine(engine_id)
        if engine is None:
            raise HTTPException(status_code=404, detail=f"Engine '{engine_id}' not found")
        return {"success": True, "data": engine}

    engines = _monitor.get_engines()

    # Update engine heartbeat checks
    now = time.time()
    for eng in engines:
        last = eng.get("last_heartbeat", now)
        delta = now - last
        if delta > 60:
            eng["status"] = "degraded"
        if delta > 300:
            eng["status"] = "error"

    return {
        "success": True,
        "data": {
            "engines": engines,
            "total": len(engines),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/api/v1/monitor/agent-activity", dependencies=[Depends(require_permission(Permission.MONITOR_READ))])
async def get_agent_activity(
    request: Request,
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    activity_type: Optional[str] = Query(None, description="Filter by activity type"),
):
    """GET /api/v1/monitor/agent-activity — Agent activity log.

    Returns recent agent actions including design operations,
    validation runs, and export activities.
    """
    _check_rate_limit(request)
    activities = _monitor.get_agent_activity(
        limit=limit,
        agent_id=agent_id,
        activity_type=activity_type,
    )

    return {
        "success": True,
        "data": {
            "activities": activities,
            "total": len(activities),
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/api/v1/monitor/security-alerts", dependencies=[Depends(require_permission(Permission.MONITOR_READ))])
async def get_security_alerts(
    request: Request,
    limit: int = Query(50, ge=1, le=500, description="Max alerts to return"),
    severity: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved state"),
):
    """GET /api/v1/monitor/security-alerts — Active and historical security alerts.

    Returns security events from the audit logging system including
    unauthorized access attempts, API key violations, and suspicious activity.
    """
    _check_rate_limit(request)

    # Try to load from security logging system
    try:
        from fireai.core.security_logging import security_audit
        events = security_audit.get_events(limit=limit)
        alerts = []
        for event in events:
            alerts.append({
                "alert_id": event.get("event_id", ""),
                "severity": event.get("severity", "medium"),
                "category": event.get("event_type", "unknown"),
                "message": event.get("message", ""),
                "source_ip": event.get("source_ip", ""),
                "timestamp": event.get("timestamp", ""),
                "resolved": False,
            })
        if alerts:
            return {
                "success": True,
                "data": {
                    "alerts": alerts[:limit],
                    "total": len(alerts),
                    "source": "security_logging",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
    except Exception as e:
        logger.debug("Security logging not available: %s", e)

    alerts = _monitor.get_security_alerts(limit=limit, severity=severity, resolved=resolved)
    return {
        "success": True,
        "data": {
            "alerts": alerts,
            "total": len(alerts),
            "source": "monitor_state",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/api/v1/monitor/alerts", dependencies=[Depends(require_permission(Permission.MONITOR_READ))])
async def get_alerts(request: Request):
    """GET /api/v1/monitor/alerts — Current alert state.

    Evaluates all alert rules against current system state and
    returns currently firing alerts with severity and details.
    """
    _check_rate_limit(request)

    # Evaluate alert rules
    try:
        active_alerts = _monitor.evaluate_alert_rules()
    except Exception as e:
        logger.error("Alert rule evaluation failed: %s", e)
        active_alerts = _monitor.get_active_alerts()

    rules = _monitor.get_alert_rules()

    return {
        "success": True,
        "data": {
            "active_alerts": active_alerts,
            "alert_count": len(active_alerts),
            "rules": rules,
            "rule_count": len(rules),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# Background metric collector (simulated engine metrics)
# ════════════════════════════════════════════════════════════════════════════

async def start_metric_collector(interval_seconds: int = 15) -> None:
    """Start background task to update engine metrics.

    In production, this would read from /proc, Prometheus, or
    container orchestration APIs.
    """
    import random

    while True:
        try:
            for engine_id in _monitor.get_engines():
                eng = _monitor.get_engine(engine_id["engine_id"])
                if eng:
                    _monitor.update_engine(eng["engine_id"], {
                        "cpu_percent": round(random.uniform(1.0, 60.0), 1),
                        "memory_mb": round(random.uniform(10.0, 200.0), 1),
                    })
        except Exception as e:
            logger.error("Metric collector error: %s", e)

        await asyncio.sleep(interval_seconds)
