# NOSONAR
"""
backend/admin_protection.py — V240 Strong admin endpoint protection.

THREE-LAYER DEFENSE for /api/v1/admin/* endpoints:

  Layer 1: API Key authentication (existing — require_permission(Permission.USER_MANAGE))
           → Verifies the caller has an admin-role API key

  Layer 2: Master Admin Token (NEW — BAZSPARK_MASTER_ADMIN_TOKEN env var)
           → A SEPARATE secret token that ONLY the admin knows
           → Required in X-Master-Admin-Token header for ALL admin/keys operations
           → Different from FIREAI_API_KEY (which is for login)
           → If not set in env, admin operations are BLOCKED (fail-closed)

  Layer 3: Rate limiting (NEW — 10 operations per minute per IP)
           → Prevents brute force on master token
           → Logs repeated failures for monitoring

  Layer 4: Audit logging (NEW — every admin operation logged)
           → Timestamp, IP, operation, target key hash, success/failure
           → Written to db/admin_audit.log (JSONL format)

USAGE:
  # To generate a key, admin must provide BOTH:
  curl -X POST "https://api/admin/keys" \
    -H "X-API-Key: fireai_admin_key" \
    -H "X-Master-Admin-Token: master_token_here" \
    -d '{"role":"engineer","description":"John"}'

SECURITY:
  - Master token is 64 chars (256 bits entropy) — brute-force impossible
  - Master token is stored ONLY in HF Space secret (never in code/db)
  - If BAZSPARK_MASTER_ADMIN_TOKEN is unset → ALL admin ops return 403
  - Failed attempts are rate-limited (10/min) and logged
  - All operations (success + failure) are audit-logged
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, Request, status

logger = logging.getLogger(__name__)

# ═══ Configuration ═══════════════════════════════════════════════════════
MASTER_TOKEN_ENV = "BAZSPARK_MASTER_ADMIN_TOKEN"

# Rate limiting: 10 attempts per minute per IP
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_ATTEMPTS = 10

# Audit log file
AUDIT_LOG_FILE = os.getenv(
    "BAZSPARK_ADMIN_AUDIT_LOG",
    os.path.join(os.getenv("FIREAI_API_KEYS_FILE", "db/api_keys.json").rsplit("/", 1)[0] or ".",
                 "admin_audit.log"),
)

# In-memory rate limit counter (per IP)
_rate_limit_counter: dict[str, list[float]] = defaultdict(list)


# ═══ Helpers ═════════════════════════════════════════════════════════════
def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> bool:
    """Return True if IP is within rate limit, False otherwise."""
    now = time.time()
    # Clean old entries
    _rate_limit_counter[ip] = [t for t in _rate_limit_counter[ip] if now - t < RATE_LIMIT_WINDOW]
    # Check limit
    if len(_rate_limit_counter[ip]) >= RATE_LIMIT_MAX_ATTEMPTS:
        return False
    _rate_limit_counter[ip].append(now)
    return True


def _audit_log(
    ip: str,
    operation: str,
    success: bool,
    target: str = "",
    detail: str = "",
) -> None:
    """Write an audit log entry (JSONL format) without exposing PII."""
    try:
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "epoch": time.time(),
            "ip": ip,
            "operation": operation,
            "target": target[:64],  # truncate to avoid log bloat
            "success": success,
            # Sanitize detail to remove any potential PII/sensitive info
            "detail": _sanitize_log_detail(detail)[:200],
        }
        log_path = Path(AUDIT_LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logging.exception("Failed to write audit log: %s", e)  # NOSONAR — S8572: logging.exception is appropriate here


def _sanitize_log_detail(detail: str) -> str:
    """Sanitize log details to prevent PII exposure."""
    if not detail:
        return detail
    
    # Remove potentially sensitive information
    import re
    
    # Remove anything that looks like API keys, tokens, passwords, etc.
    sanitized = re.sub(r'[A-Z0-9]{32,}', '[REDACTED_LONG_TOKEN]', detail, flags=re.IGNORECASE)
    sanitized = re.sub(r'(?:api[_-]?key|token|password|secret|auth)[\s:=]+[^\s,;.!]+', r'\1: [REDACTED]', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'bearer\s+[a-zA-Z0-9\-\._~\+\/]+=*', 'Bearer [REDACTED]', sanitized, flags=re.IGNORECASE)
    
    return sanitized


def _verify_master_token(provided: Optional[str]) -> bool:
    """
    Verify the master admin token using constant-time comparison.

    Returns True if the token matches the env var.
    Returns False if:
      - BAZSPARK_MASTER_ADMIN_TOKEN is not set (fail-closed)
      - Provided token is None/empty
      - Token doesn't match
    """
    expected = os.getenv(MASTER_TOKEN_ENV, "").strip()
    if not expected:
        # Fail-closed: if master token not configured, ALL admin ops blocked
        logger.error("BAZSPARK_MASTER_ADMIN_TOKEN not set — admin operations blocked")
        return False
    if not provided:
        return False
    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(provided, expected)


# ═══ FastAPI Dependency ═══════════════════════════════════════════════════
async def require_master_admin(  # NOSONAR — S7503: async required by FastAPI Depends injection contract
    request: Request,
    x_master_admin_token: Optional[str] = Header(None, alias="X-Master-Admin-Token"),
) -> str:
    """
    FastAPI dependency that enforces master admin token + rate limit + audit.

    Usage in router:
        @router.post("")
        async def create_key(
            request: Request,
            body: GenerateKeyRequest,
            _role: Role = Depends(require_permission(Permission.USER_MANAGE)),
            ip: str = Depends(require_master_admin),
        ):

    Returns the client IP (for logging).
    Raises HTTPException(403) if:
      - Rate limit exceeded
      - Master token missing/invalid
    """
    ip = _get_client_ip(request)

    # Layer 3: Rate limit check
    if not _check_rate_limit(ip):
        _audit_log(ip, "rate_limit_exceeded", False, detail="Too many admin attempts")
        logger.warning("Admin rate limit exceeded for IP=%s", ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many admin operations. Wait 60 seconds.",
        )

    # Layer 2: Master token verification
    if not _verify_master_token(x_master_admin_token):
        _audit_log(ip, "master_token_invalid", False, detail="Missing or wrong master token")
        logger.warning("Invalid master admin token from IP=%s", ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master admin token required. Contact the system owner.",
        )

    # Success — return IP for the endpoint to use in audit log
    return ip


async def audit_operation(  # NOSONAR — S7503: async required by FastAPI Depends injection contract
    ip: str,
    operation: str,
    success: bool,
    target: str = "",
    detail: str = "",
) -> None:
    """Convenience wrapper for _audit_log (for use in endpoints)."""
    _audit_log(ip, operation, success, target, detail)


# ═══ Health check (for the admin to verify token is set) ═══════════════════
def is_master_token_configured() -> bool:
    """Return True if BAZSPARK_MASTER_ADMIN_TOKEN is set in env."""
    return bool(os.getenv(MASTER_TOKEN_ENV, "").strip())


def generate_master_token() -> str:
    """
    Generate a new 64-char master admin token (256 bits entropy).

    The admin should:
      1. Run this function to get a new token
      2. Set it as BAZSPARK_MASTER_ADMIN_TOKEN in HF Space secrets
      3. Restart the Space
      4. Save the token securely (it cannot be retrieved from env)
    """
    import secrets as _secrets
    return f"master_{_secrets.token_urlsafe(48)}"


if __name__ == "__main__":
    # CLI: generate a new master token
    print("🔐 BAZSPARK Master Admin Token Generator")
    print("=" * 60)
    print()
    token = generate_master_token()
    print("Your new master admin token:")
    print()
    print(f"  {token}")
    print()
    print("⚠️  SAVE THIS NOW — it cannot be retrieved later.")
    print()
    print("To activate:")
    print("  1. Go to: https://huggingface.co/spaces/ahmdelbaz28/BAZSPARK/settings")
    print("  2. Add secret: BAZSPARK_MASTER_ADMIN_TOKEN = <token above>")
    print("  3. Restart the Space")
    print("  4. Use this token in X-Master-Admin-Token header for admin ops")
    print("=" * 60)
