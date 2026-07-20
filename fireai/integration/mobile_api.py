# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
fireai/integration/mobile_api.py.
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
from typing import Any

from fireai.core.event_bus import EventBus, Events

logger = logging.getLogger(__name__)

# ===========================================================================
# Previously _hash_password() returned hashlib.sha256(password).hexdigest()
# — unsalted, fast to compute, and trivially crackable with GPU brute-force
# or rainbow tables. This violates OWASP A02:2021 (Cryptographic Failures)
# and is unacceptable for any system that stores user credentials, even a
# demo mobile API.
#
# Fix: use passlib[bcrypt] (already a project dependency — see pyproject.toml
# line 44) with the OWASP-recommended 12-round work factor. bcrypt provides:
#   - Per-hash random salt (defeats rainbow tables)
#   - Adjustable work factor (defeats GPU brute-force)
#   - Industry-standard KDF (no rolling crypto)
#
# Protocol preservation: the client still sends SHA-256(password) over the
# wire (unchanged wire protocol). The server-side bcrypt hashing is applied
# on top of the received SHA-256 hex digest — same SHA-256-pre-then-bcrypt
# pattern used in backend/api_keys.py for API keys (lines 56-75 there).
# ===========================================================================
try:
    from passlib.context import CryptContext

    _pwd_context: CryptContext | None = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=12,
    )
    HAS_BCRYPT: bool = True
except ImportError as _exc:  # pragma: no cover — defensive
    logger.warning(
        "passlib[bcrypt] not available — refusing to start mobile_api. "
        "Run `pip install 'passlib[bcrypt]>=1.7.0'` to fix. "
        "Original error: %s",
        _exc,
    )
    _pwd_context = None
    HAS_BCRYPT = False


# ===========================================================================
# Rate Limiter
# ===========================================================================


class _RateLimiter:
    """Simple sliding-window rate limiter per user."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[str, list[float]] = {}

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
    scope: list[str] = field(default_factory=lambda: ["read"])

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
    photos: list[str] = field(default_factory=list)
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
    projects: list[ProjectSummary] = field(default_factory=list)
    tasks: list[FieldTask] = field(default_factory=list)
    inspections: list[dict[str, Any]] = field(default_factory=list)
    reference_data: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""


# ===========================================================================
# Mobile API
# ===========================================================================


class MobileAPI:
    """
    Secure API layer for iOS/Android field applications.

    Features:
      - Token-based authentication with refresh token rotation
      - Rate-limited auth endpoint (60 req/min per user)
      - Field task management (inspections, surveys, punch items)
      - Report submission with validation
      - Offline sync package generation
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus or EventBus.instance()
        self._rate_limiter = _RateLimiter()
        self._tokens: dict[str, AuthToken] = {}
        self._users: dict[str, dict[str, Any]] = {}
        self._projects: dict[str, ProjectSummary] = {}
        self._tasks: dict[str, FieldTask] = {}
        self._reports: dict[str, FieldReport] = {}

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
        # instead of secrets.compare_digest on unsalted SHA-256 hashes.
        # The client still sends SHA-256(password) — _verify_password runs
        # bcrypt.checkpw on the received value against the stored bcrypt hash.
        if not self._verify_password(credentials.password_hash, stored_hash):
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
        for token_id, stored in list(self._tokens.items()):  # NOSONAR - python:S7504
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

    def validate_token(self, token: str) -> AuthToken | None:
        auth_token = self._tokens.get(token)
        if auth_token is None:
            return None
        if auth_token.is_expired:
            del self._tokens[token]
            return None
        return auth_token

    # ── Projects ────────────────────────────────────────────────────────

    def get_projects(self, _user_id: str) -> list[ProjectSummary]:  # NOSONAR — S1172: parameter retained for API stability
        return list(self._projects.values())

    def add_project(self, project: ProjectSummary) -> None:
        self._projects[project.project_id] = project

    # ── Field Tasks ─────────────────────────────────────────────────────

    def get_field_tasks(self, user_id: str) -> list[FieldTask]:
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
        self, user_id: str, _since: datetime  # NOSONAR — S1172: parameter retained for API stability
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
            return SyncPackage(
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

        except Exception as exc:
            logger.exception("Offline sync failed for user %s: %s", user_id, exc)
            raise

    # ── User Management ─────────────────────────────────────────────────

    def register_user(
        self,
        username: str,
        password: str,
        scope: list[str] | None = None,
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
        """
        Hash a password using SHA-256 pre-hash + bcrypt (salted, 12 rounds).

        V279 SECURITY FIX: Previously returned unsalted SHA-256 hex digest.
        Now applies bcrypt on top of the SHA-256 digest to add a per-user
        random salt and a slow KDF (defeats rainbow tables + GPU brute-force).

        Protocol (unchanged on the wire):
          1. Client computes SHA-256(password) → sends hex digest over TLS
          2. Server (this method) hashes the digest with bcrypt → stores result
          3. On authenticate: server calls _verify_password(SHA-256(password), stored_hash)
             which runs bcrypt.checkpw(SHA-256(password), stored_bcrypt_hash)

        Same SHA-256-pre-then-bcrypt pattern as backend/api_keys.py (lines 56-75).

        Refuses to operate if passlib[bcrypt] is not installed — fail-loud
        is safer than silently falling back to unsalted SHA-256.
        """
        if not HAS_BCRYPT or _pwd_context is None:
            raise RuntimeError(
                "passlib[bcrypt] is required for secure password hashing "
                "in mobile_api. Install with: pip install 'passlib[bcrypt]>=1.7.0'. "
                "Refusing to hash with unsalted SHA-256 (OWASP A02:2021 violation)."
            )
        # Step 1: SHA-256 pre-hash (preserves wire protocol — client sends this)
        sha256_digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        # Step 2: bcrypt with random salt + 12-round KDF
        return _pwd_context.hash(sha256_digest)

    @staticmethod
    def _verify_password(client_supplied_sha256: str, stored_bcrypt_hash: str) -> bool:
        """
        Verify a client-supplied SHA-256 digest against the stored bcrypt hash.

        V279 SECURITY FIX: Replaces secrets.compare_digest on unsalted SHA-256
        with bcrypt.checkpw — constant-time, salted, slow KDF.

        Args:
            client_supplied_sha256: SHA-256 hex digest sent by the client
                (NOT the plaintext password — wire protocol unchanged).
            stored_bcrypt_hash: bcrypt hash stored at registration time
                (output of _hash_password).

        Returns:
            True if the SHA-256 digest matches the stored bcrypt hash.
            False if verification fails, hash is malformed, or bcrypt
            is unavailable (fail-closed).
        """
        if not HAS_BCRYPT or _pwd_context is None:
            logger.error(
                "passlib[bcrypt] not available — refusing to verify password "
                "(fail-closed). Install passlib[bcrypt] to enable authentication."
            )
            return False
        try:
            return _pwd_context.verify(client_supplied_sha256, stored_bcrypt_hash)
        except (ValueError, TypeError) as exc:
            logger.warning("Password verification failed (malformed hash): %s", exc)
            return False


# ===========================================================================
# Self-Test
# ===========================================================================

if __name__ == "__main__":
    api = MobileAPI()

    api.register_user("field_engineer", "secure_pass_123!")
    # The mobile client sends SHA-256(password) over the wire (TLS-protected).
    # The server-side authenticate() runs bcrypt.checkpw on the received
    # SHA-256 digest against the stored bcrypt hash.
    client_password_hash = hashlib.sha256(b"secure_pass_123!").hexdigest()
    token = api.authenticate(
        MobileCredentials(
            username="field_engineer",
            password_hash=client_password_hash,
            device_id="DEVICE-A1",
            platform="ios",
        )
    )
    print(f"Auth token: {token.token[:20]}...")
    print(f"Expires: {token.expires_at}")

    # for the bcrypt migration — confirms we're not silently accepting
    # wrong credentials).
    bad_password_hash = hashlib.sha256(b"wrong_password").hexdigest()
    try:
        api.authenticate(
            MobileCredentials(
                username="field_engineer",
                password_hash=bad_password_hash,
                device_id="DEVICE-A1",
                platform="ios",
            )
        )
        print("FAIL: invalid password was accepted — bug in bcrypt verification")
    except PermissionError:
        print("PASS: invalid password correctly rejected")

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
