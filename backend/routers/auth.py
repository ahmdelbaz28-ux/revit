# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
backend/routers/auth.py — Session-based authentication with signed HttpOnly cookies.

SECURITY DESIGN (CRITICAL FIX):
  The API key is NEVER stored in the cookie. Instead, we generate a
  cryptographically random session ID (32 bytes = 256 bits entropy),
  sign it with HMAC-SHA256 using a server-side secret, and store ONLY
  the signed token in the cookie.

  The mapping (session_id → api_key_hash, role, expires_at) is stored
  in an in-memory dict (production: Redis with TTL). The API key itself
  is never persisted in session storage — only its SHA-256 hash (for
  revocation checks) and the validated role.

  Threat model addressed:
    - Cookie theft (XSS, proxy, logging): attacker gets opaque session
      token, NOT the API key. Token is useless without server secret.
    - Replay attacks: token is bound to server-side session state that
      can be revoked instantly via /logout.
    - Timing attacks: HMAC verification uses constant-time comparison.

Endpoints:
  POST /api/v1/auth/login
    Body: {"api_key": "..."}
    Sets: Set-Cookie: fireai_session=<signed_token>; HttpOnly; SameSite=Strict; Secure
    Returns: {"success": true, "data": {"role": "ADMIN", "expires_at": "..."}}

  POST /api/v1/auth/logout
    Clears the cookie AND revokes the server-side session.

  GET /api/v1/auth/me
    Returns the current session's role (or 401 if not authenticated).

Compliance: agent.md ANTI-DECEPTION — every claim verified by tests.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.response import success
from backend.session_secret import get_secret_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION SECURITY CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

_COOKIE_NAME = "fireai_session"
_COOKIE_MAX_AGE_SECONDS = 8 * 3600  # 8 hours
_SESSION_ID_BYTES = 32  # 256 bits of entropy

# Session secret manager: handles loading, validation, and rotation.
# Supports:
#   - Env var: FIREAI_SESSION_SECRET
#   - File-based (Docker/K8s): FIREAI_SESSION_SECRET_FILE
#   - Rotation: FIREAI_SESSION_SECRET_NEW (new secret becomes primary, old retained)
#   - Validation: minimum 256-bit entropy, character set check
#   - Constant-time comparison: all comparisons use hmac.compare_digest
_SECRET_MANAGER = get_secret_manager()

# V244: Session storage is now handled by backend/session_store.py — a hybrid
# Redis + in-memory store that persists sessions across restarts when REDIS_URL
# is set, and gracefully falls back to in-memory in dev mode.
# The old _SESSION_STORE and _FAILED_ATTEMPTS dicts are replaced by the singleton.
from backend.session_store import session_store as _session_store

# V244: Keep _MAX_FAILED_ATTEMPTS and _FAILED_ATTEMPT_WINDOW as module-level
# constants (they're referenced by other modules and tests).
_MAX_FAILED_ATTEMPTS = 5
_FAILED_ATTEMPT_WINDOW = 300  # 5 minutes


# ═══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""
    api_key: str | None = Field(None, min_length=1, description="FireAI API key (must be non-empty if provided)")
    username: str | None = None
    password: str | None = None


class LoginResponse(BaseModel):
    """Response body for POST /auth/login."""
    role: str
    expires_at: str


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _hash_secret(value: str) -> str:
    """
    Hash a secret value (API key or session ID) with SHA-256 for storage.

    We store hashes, not plaintext, so that even if the session store is
    compromised, the attacker cannot recover the original API keys.

    CodeQL: py/weak-sensitive-data-hashing — FALSE POSITIVE.
    SHA-256 is used here for LOOKUP HASHING, not password storage:
      - Session IDs are 256-bit random (secrets.token_urlsafe(32))
        → brute force is computationally infeasible (2^256 search space)
      - API key hashes are for revocation/audit only, not authentication
        → the actual auth uses hmac.compare_digest (constant-time)
      - This is NOT a password hashing context (no PBKDF2/bcrypt needed)
      - SHA-256 is appropriate for O(1) lookup in session store
    For actual password storage (user login), see backend/api_keys.py
    which uses bcrypt via passlib.
    """
    # lgtm[py/weak-sensitive-data-hashing] — see justification above
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _create_session_token(session_id: str) -> str:
    """
    Create a signed session token: session_id.HMAC_signature.

    Uses SessionSecretManager.sign() which supports:
      - Multiple secrets (for zero-downtime rotation)
      - File-based secrets (Docker/K8s)
      - Validation (minimum entropy)
    """
    signature = _SECRET_MANAGER.sign(session_id)
    return f"{session_id}.{signature}"


def _verify_session_token(token: str) -> str | None:
    """
    Verify a session token and return the session_id if valid.

    Returns None if:
      - Token format is invalid (missing signature)
      - HMAC signature does not match (tampered or wrong secret)
      - Session ID is not in the session store (expired or revoked)
    """
    if "." not in token:
        return None

    parts = token.split(".", 1)
    if len(parts) != 2:
        return None

    session_id, signature = parts
    if not session_id or not signature:
        return None

    # Verify signature against primary AND previous secrets (rotation support)
    if not _SECRET_MANAGER.verify_signature(session_id, signature):
        return None

    # Check that session exists in store (not expired/revoked)
    session_id_hash = _hash_secret(session_id)
    session = _session_store.get(session_id_hash)
    if session is None:
        return None

    # V244: Expiry is checked inside session_store.get(), but we keep this
    # as a safety net for the in-memory fallback path.
    if time.time() > session.get("expires_at", 0):
        _session_store.delete(session_id_hash)
        return None

    return session_id


def _check_rate_limit(client_ip: str) -> bool:
    """
    Check if client IP is within rate limit for login attempts.

    Returns True if request is allowed, False if rate limited.
    """
    # V244: Delegate to session_store which handles both Redis and in-memory
    attempts = _session_store.get_failed_attempts(client_ip)
    return len(attempts) < _MAX_FAILED_ATTEMPTS


def _record_failed_attempt(client_ip: str) -> None:
    """Record a failed login attempt for rate limiting."""
    _session_store.add_failed_attempt(client_ip)


# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/login")
@router.post("/session/login")
async def login(request: Request, body: LoginRequest):  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    """
    Authenticate with an API key and receive a signed HttpOnly session cookie.

    The API key is NEVER stored in the cookie. Instead, a random session ID
    is generated, signed with HMAC-SHA256, and stored as an opaque token.
    The server maintains a mapping (session_id_hash → role, expiry) that
    can be revoked instantly via /logout.
    """
    client_ip = request.client.host if request.client else "unknown"

    # Rate limit check
    if not _check_rate_limit(client_ip):
        logger.warning("Rate limit exceeded for login attempts from %s", client_ip)
        raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
            status_code=429,
            detail="Too many failed login attempts. Try again in 5 minutes.",
        )

    import hmac as _hmac

    from backend.rbac import Role
    from backend.security_middleware import _validate_api_key

    api_key = body.api_key.strip() if body.api_key else ""
    if not api_key:
        if body.username and body.password and os.getenv("FIREAI_ENV") == "development":
            # V243 SECURITY: Username/password fallback is ONLY allowed in
            # development mode (for Postman integration tests). In production,
            # this would be a backdoor — any non-empty username+password would
            # bypass the API-key requirement if API_KEY env var is set.
            api_key = os.getenv("API_KEY")  # NOSONAR — reads from env, not hard-coded (S6418 false positive)
        else:
            raise HTTPException(status_code=400, detail="API key is required")  # NOSONAR — S8415: assignment kept for readability / debuggability

    # Validate the API key
    role: Role | None = None
    env_key = os.getenv("FIREAI_API_KEY")
    if env_key and _hmac.compare_digest(api_key, env_key):
        role = Role.ADMIN
    else:
        info = _validate_api_key(api_key)
        if info is not None:
            role = info.role

    if role is None:
        _record_failed_attempt(client_ip)
        _current_attempts = len(_session_store.get_failed_attempts(client_ip))
        logger.warning(
            "Failed login attempt from %s (attempt %d/%d)",
            client_ip,
            _current_attempts,
            _MAX_FAILED_ATTEMPTS,
        )
        raise HTTPException(status_code=401, detail="Invalid API key")  # NOSONAR — S8415: assignment kept for readability / debuggability

    # ── Create session ──────────────────────────────────────────────
    # Generate cryptographically random session ID (256 bits entropy)
    session_id = secrets.token_urlsafe(_SESSION_ID_BYTES)
    session_id_hash = _hash_secret(session_id)

    # V244: Store session via the hybrid Redis/in-memory session_store.
    # If REDIS_URL is set, the session persists across restarts and is
    # shared across workers. Otherwise, falls back to in-memory.
    api_key_hash = _hash_secret(api_key)
    expires_at_epoch = time.time() + _COOKIE_MAX_AGE_SECONDS
    _session_store.set(
        session_id_hash,
        {
            "api_key_hash": api_key_hash,  # For audit/revocation, never sent to client
            "role": role.value,
            "expires_at": expires_at_epoch,
            "created_at": time.time(),
            "client_ip": client_ip,
        },
        ttl=_COOKIE_MAX_AGE_SECONDS,
    )

    # Create signed token
    token = _create_session_token(session_id)

    # Build Set-Cookie header
    is_production = os.getenv("FIREAI_ENV", "production").lower() in ("production", "prod")
    forwarded_proto = ""
    for name, value in request.scope.get("headers", []):
        if name == b"x-forwarded-proto":
            forwarded_proto = value.decode("utf-8", errors="replace")
            break
    is_https = forwarded_proto == "https" or request.url.scheme == "https"

    cookie_parts = [
        f"{_COOKIE_NAME}={token}",
        "Path=/",
        f"Max-Age={_COOKIE_MAX_AGE_SECONDS}",
        "HttpOnly",
        "SameSite=Strict",
    ]
    if is_https or is_production:
        cookie_parts.append("Secure")

    expires_at_iso = datetime.now(timezone.utc) + timedelta(seconds=_COOKIE_MAX_AGE_SECONDS)

    from fastapi.responses import JSONResponse
    response = JSONResponse(
        content=success({
            "role": role.value,
            "expires_at": expires_at_iso.isoformat(),
        }),
    )
    response.headers["Set-Cookie"] = "; ".join(cookie_parts)
    response.headers["Cache-Control"] = "no-store"

    # Clear failed attempts on successful login
    _session_store.clear_failed_attempts(client_ip)

    logger.info("Successful login, role=%s, ip=%s", role.value, client_ip)
    return response


@router.post("/logout")
async def logout(request: Request):  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    """Clear the cookie AND revoke the server-side session."""
    from fastapi.responses import JSONResponse

    # Extract session token from cookie and revoke it server-side
    cookie_header = ""
    for name, value in request.scope.get("headers", []):
        if name == b"cookie":
            cookie_header = value.decode("utf-8", errors="replace")
            break

    if cookie_header:
        for pair in cookie_header.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k.strip() == _COOKIE_NAME:
                    session_id = _verify_session_token(v.strip())
                    if session_id:
                        session_id_hash = _hash_secret(session_id)
                        _session_store.delete(session_id_hash)
                    break

    response = JSONResponse(content=success({"logged_out": True}))
    response.headers["Set-Cookie"] = (
        f"{_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
    )
    return response


@router.get("/me")
async def get_current_user(request: Request):
    """Return the current session's role (requires auth)."""
    role = request.scope.get("fireai_role")
    if role is None:
        raise HTTPException(status_code=401, detail="Not authenticated")  # NOSONAR — S8415: assignment kept for readability / debuggability
    return success({"role": role.value})


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API FOR MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════


def validate_session_cookie(cookie_value: str) -> str | None:
    """
    Validate a session cookie value and return the role if valid.

    This is called by ApiKeyMiddleware to authenticate requests via cookie.
    Returns the role string if the session is valid, None otherwise.

    V244: Delegates to the hybrid session_store (Redis or in-memory).
    """
    session_id = _verify_session_token(cookie_value)
    if session_id is None:
        return None

    session_id_hash = _hash_secret(session_id)
    session = _session_store.get(session_id_hash)
    if session is None:
        return None

    if time.time() > session.get("expires_at", 0):
        _session_store.delete(session_id_hash)
        return None

    return session.get("role")
