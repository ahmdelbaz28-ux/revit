"""fireai/integration/mobile_api.py
==================================
Mobile Platform — Secure API layer for iOS/Android field applications.

Provides token-based authentication, project listing, field task
management, report submission, and offline sync package generation.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fireai.core.event_bus import EventBus, Events

logger = logging.getLogger(__name__)


# ===========================================================================
# Rate Limiter
# ===========================================================================


class _RateLimiter:
    """Simple sliding-window rate limiter per user."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._buckets: Dict[str, List[float]] = {}

    def allow(self, user_id: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        bucket = self._buckets.setdefault(user_id, [])
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True


# ===========================================================================
# Enums
# ===========================================================================


class TaskType(str, Enum):
    INSPECTION = "INSPECTION"
    SURVEY = "SURVEY"
    PUNCH_ITEM = "PUNCH_ITEM"
    MAINTENANCE = "MAINTENANCE"
    COMMISSIONING = "COMMISSIONING"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"


class AuthScheme(str, Enum):
    BEARER = "BEARER"
    API_KEY = "API_KEY"  # Auth scheme name, not an actual key value


# ===========================================================================
# Data Models
# ===========================================================================


@dataclass(frozen=True)
class MobileCredentials:
    username: str
    password_hash: str
    device_id: str
    app_version: str = "1.0.0"
    platform: str = ""  # "ios", "android"

    def __post_init__(self) -> None:
        if not self.username.strip():
            raise ValueError("username is required")
        if not self.password_hash.strip():
            raise ValueError("password_hash is required")
        if not self.device_id.strip():
            raise ValueError("device_id is required")


@dataclass(frozen=True)
class AuthToken:
    token: str
    refresh_token: str
    expires_at: datetime
    user_id: str
    scope: List[str] = field(default_factory=lambda: ["read"])

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    name: str
    building_count: int
    status: str  # ACTIVE, COMPLETED, ON_HOLD
    last_updated: datetime
    role: str = ""  # viewer, editor, admin


@dataclass(frozen=True)
class FieldTask:
    task_id: str
    project_id: str
    task_type: TaskType
    title: str
    description: str
    assigned_to: str
    due_date: datetime
    status: TaskStatus = TaskStatus.PENDING
    location: str = ""
    asset_id: str = ""
    priority: str = "MEDIUM"


@dataclass(frozen=True)
class FieldReport:
    report_id: str
    task_id: str
    user_id: str
    findings: str
    submitted_at: datetime
    photos: List[str] = field(default_factory=list)
    status: str = "SUBMITTED"


@dataclass(frozen=True)
class ReportResult:
    report_id: str
    accepted: bool
    message: str = ""


@dataclass(frozen=True)
class SyncPackage:
    user_id: str
    generated_at: datetime
    projects: List[ProjectSummary] = field(default_factory=list)
    tasks: List[FieldTask] = field(default_factory=list)
    inspections: List[Dict[str, Any]] = field(default_factory=list)
    reference_data: Dict[str, Any] = field(default_factory=dict)
    checksum: str = ""


# ===========================================================================
# Mobile API
# ===========================================================================


class MobileAPI:
    """Secure API layer for iOS/Android field applications.

    Features:
      - Token-based authentication with refresh token rotation
      - Rate-limited auth endpoint (60 req/min per user)
      - Field task management (inspections, surveys, punch items)
      - Report submission with validation
      - Offline sync package generation
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus or EventBus.instance()
        self._rate_limiter = _RateLimiter()
        self._tokens: Dict[str, AuthToken] = {}
        self._users: Dict[str, Dict[str, Any]] = {}
        self._projects: Dict[str, ProjectSummary] = {}
        self._tasks: Dict[str, FieldTask] = {}
        self._reports: Dict[str, FieldReport] = {}

    # ── Authentication ──────────────────────────────────────────────────

    def authenticate(self, credentials: MobileCredentials) -> AuthToken:
        if not self._rate_limiter.allow(credentials.username):
            raise PermissionError(
                f"Rate limit exceeded for user {credentials.username}"
            )

        user = self._users.get(credentials.username)
        if user is None:
            raise PermissionError("Invalid username or password")

        stored_hash = user.get("password_hash", "")
        if not secrets.compare_digest(
            credentials.password_hash, stored_hash
        ):
            raise PermissionError("Invalid username or password")

        token_str = self._generate_token()
        refresh_str = self._generate_token()
        expires = datetime.now(timezone.utc) + timedelta(hours=24)

        auth_token = AuthToken(
            token=token_str,
            refresh_token=refresh_str,
            expires_at=expires,
            user_id=credentials.username,
            scope=user.get("scope", ["read"]),
        )
        self._tokens[token_str] = auth_token

        self._event_bus.publish(
            "mobile.auth.login",
            data={
                "user_id": credentials.username,
                "device_id": credentials.device_id,
            },
            source="mobile_api",
        )
        return auth_token

    def refresh_token(self, refresh_token: str) -> AuthToken:
        for token_id, stored in list(self._tokens.items()):
            if stored.refresh_token == refresh_token:
                new_token = self._generate_token()
                new_refresh = self._generate_token()
                new_expires = datetime.now(timezone.utc) + timedelta(hours=24)

                auth_token = AuthToken(
                    token=new_token,
                    refresh_token=new_refresh,
                    expires_at=new_expires,
                    user_id=stored.user_id,
                    scope=stored.scope,
                )
                self._tokens[new_token] = auth_token
                del self._tokens[token_id]
                return auth_token

        raise PermissionError("Invalid refresh token")

    def validate_token(self, token: str) -> Optional[AuthToken]:
        auth_token = self._tokens.get(token)
        if auth_token is None:
            return None
        if auth_token.is_expired:
            del self._tokens[token]
            return None
        return auth_token

    # ── Projects ────────────────────────────────────────────────────────

    def get_projects(self, user_id: str) -> List[ProjectSummary]:
        return list(self._projects.values())

    def add_project(self, project: ProjectSummary) -> None:
        self._projects[project.project_id] = project

    # ── Field Tasks ─────────────────────────────────────────────────────

    def get_field_tasks(self, user_id: str) -> List[FieldTask]:
        return [
            task
            for task in self._tasks.values()
            if task.assigned_to == user_id
        ]

    def assign_task(self, task: FieldTask) -> None:
        self._tasks[task.task_id] = task

    def update_task_status(
        self, task_id: str, status: TaskStatus
    ) -> bool:
        if task_id not in self._tasks:
            return False
        task = self._tasks[task_id]
        self._tasks[task_id] = FieldTask(
            task_id=task.task_id,
            project_id=task.project_id,
            task_type=task.task_type,
            title=task.title,
            description=task.description,
            assigned_to=task.assigned_to,
            due_date=task.due_date,
            status=status,
            location=task.location,
            asset_id=task.asset_id,
            priority=task.priority,
        )
        return True

    # ── Field Reports ───────────────────────────────────────────────────

    def submit_field_report(self, report: FieldReport) -> ReportResult:
        if report.report_id in self._reports:
            return ReportResult(
                report_id=report.report_id,
                accepted=False,
                message="Report already exists",
            )

        self._reports[report.report_id] = report

        self._event_bus.publish(
            "mobile.report.submitted",
            data={
                "report_id": report.report_id,
                "task_id": report.task_id,
                "user_id": report.user_id,
                "photos_count": len(report.photos),
            },
            source="mobile_api",
        )

        if report.status == "SUBMITTED":
            self._event_bus.publish(
                Events.ROOM_ANALYSIS_START,
                data={
                    "source": "mobile_field_report",
                    "report_id": report.report_id,
                },
                source="mobile_api",
            )

        return ReportResult(
            report_id=report.report_id,
            accepted=True,
            message="Report accepted",
        )

    # ── Offline Sync ────────────────────────────────────────────────────

    def get_offline_sync(
        self, user_id: str, since: datetime
    ) -> SyncPackage:
        try:
            user_tasks = self.get_field_tasks(user_id)
            updated_tasks = list(user_tasks)

            projects = list(self._projects.values())

            sync_data = SyncPackage(
                user_id=user_id,
                generated_at=datetime.now(timezone.utc),
                projects=projects,
                tasks=updated_tasks,
                inspections=list(self._reports.values()),  # type: ignore[arg-type]
                reference_data={
                    "task_types": [t.value for t in TaskType],
                    "task_statuses": [s.value for s in TaskStatus],
                    "sync_version": "1.0",
                },
                checksum="",  # computed below
            )

            raw = (
                str(sync_data.projects)
                + str(sync_data.tasks)
                + str(sync_data.generated_at.isoformat())
            )
            sync_data = SyncPackage(
                user_id=sync_data.user_id,
                generated_at=sync_data.generated_at,
                projects=sync_data.projects,
                tasks=sync_data.tasks,
                inspections=sync_data.inspections,
                reference_data=sync_data.reference_data,
                checksum=hashlib.sha256(
                    raw.encode("utf-8")
                ).hexdigest()[:16],
            )

            return sync_data
        except Exception as exc:
            logger.error("Offline sync failed for user %s: %s", user_id, exc)
            raise

    # ── User Management ─────────────────────────────────────────────────

    def register_user(
        self,
        username: str,
        password: str,
        scope: Optional[List[str]] = None,
    ) -> None:
        if username in self._users:
            raise ValueError(f"User {username} already exists")
        self._users[username] = {
            "password_hash": self._hash_password(password),
            "scope": scope or ["read"],
        }

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _generate_token() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ===========================================================================
# Self-Test
# ===========================================================================

if __name__ == "__main__":
    api = MobileAPI()

    api.register_user("field_engineer", "secure_pass_123!")
    token = api.authenticate(
        MobileCredentials(
            username="field_engineer",
            password_hash=api._hash_password("secure_pass_123!"),
            device_id="DEVICE-A1",
            platform="ios",
        )
    )
    print(f"Auth token: {token.token[:20]}...")
    print(f"Expires: {token.expires_at}")

    api.add_project(
        ProjectSummary(
            project_id="PRJ-001",
            name="Hospital Tower B",
            building_count=3,
            status="ACTIVE",
            last_updated=datetime.now(timezone.utc),
            role="editor",
        )
    )
    projects = api.get_projects("field_engineer")
    print(f"Projects: {len(projects)}")

    report = FieldReport(
        report_id="RPT-001",
        task_id="TASK-001",
        user_id="field_engineer",
        findings="All detectors operational",
        submitted_at=datetime.now(timezone.utc),
    )
    result = api.submit_field_report(report)
    print(f"Report accepted: {result.accepted}")

    sync = api.get_offline_sync(
        "field_engineer",
        datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    print(f"Sync package: {len(sync.tasks)} tasks, checksum={sync.checksum}")
