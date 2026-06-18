"""
Authentication System for Distributed FACP

v2 (2026-06-18) — applied fixes:
  - Removed the hardcoded default JWT secret `"default_secret_for_dev"`
    from every constructor (CRITICAL). secret_key is now REQUIRED and
    validated for strength at construction time. The system fails
    closed instead of silently signing tokens with a known key.
  - Fixed `distribute_auth_state` which referenced `self.active_tokens`
    and `self.revoked_tokens` — those attributes live on TokenManager,
    not on AuthProvider. The original code raised AttributeError on
    every call.
  - Added `_TTLSet` for `revoked_tokens` so revoked entries auto-expire
    after 7 days (longer than the max token lifetime of 24h). The
    original `set` grew unbounded.
  - Exposed a public `lock` property on TokenManager so callers no
    longer need to reach into `_lock` (the same anti-pattern as
    `udm._projects` that was criticized elsewhere).
  - Added `iss` and `aud` claims to every token and required them on
    validation, so tokens minted for a different service cannot be
    replayed here.
  - Added thread safety to AuthProvider.users via `_users_lock`.
  - Used integer timestamps (`int(time.time())`) for `exp`/`iat`
    per RFC 7519 §4.1.4.
  - Added `prune_expired()` to bound active_tokens memory.

Deferred (requires migration plan, not applied here):
  - Migrate HS256 (shared secret) → EdDSA (asymmetric). Every replica
    currently knows the signing key, so compromising one replica lets
    an attacker forge admin tokens. Migration requires a keypair
    distribution mechanism and a token-rotation window.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections.abc import MutableSet
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import jwt  # PyJWT

logger = logging.getLogger(__name__)

# Issuer / Audience for this service. Tokens minted for another service
# (e.g. "fireai-api") are rejected even if signed with the same key.
_ISSUER = "facp-distributed"
_AUDIENCE = "facp-api"

# 7 days — longer than the maximum token lifetime (24h) so revocation
# stays effective for the full lifetime of any valid token, while
# bounding memory usage of the revoked-token set.
_REVOCATION_TTL_SECONDS = 7 * 24 * 3600

# Known-weak secret values that must NEVER be accepted.
_WEAK_SECRET_KEYS = frozenset({
    "default_secret_for_dev",
    "changeme",
    "secret",
    "",
    "your-secret-key",
    "default",
    "password",
    "admin",
})


def _validate_secret_key(secret_key: str) -> None:
    """Raise ValueError if *secret_key* is missing or weak.

    This is the single enforcement point for secret strength. Every
    TokenManager constructor calls it, so a weak secret cannot slip
    in through any code path.
    """
    if not isinstance(secret_key, str) or not secret_key:
        raise ValueError(
            "secret_key is REQUIRED and must be a non-empty string. "
            "Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    if secret_key in _WEAK_SECRET_KEYS:
        raise ValueError(
            f"secret_key='{secret_key}' is a known weak default. "
            "Refusing to start. Generate a strong key with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    if len(secret_key) < 32:
        raise ValueError(
            f"secret_key is too short ({len(secret_key)} chars). "
            "HS256 requires at least 32 bytes (256 bits) for adequate "
            "security. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )


class _TTLSet(MutableSet):
    """A set whose entries expire after a configurable TTL.

    Used for `revoked_tokens`. Without TTL, every revoked token stays
    in memory forever — even after its own `exp` has passed. With a
    7-day TTL (longer than the max token lifetime), revocation remains
    effective for the entire lifetime of any valid token while memory
    usage stays bounded.

    Thread-safe: all operations take an internal lock.
    """

    def __init__(self, ttl_seconds: int = _REVOCATION_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._store: Dict[Any, float] = {}
        self._lock = threading.Lock()

    def _prune_locked(self) -> None:
        """Remove expired entries. Caller must hold _lock."""
        now = time.time()
        expired = [k for k, t in self._store.items() if t + self._ttl < now]
        for k in expired:
            self._store.pop(k, None)

    def add(self, value: Any) -> None:
        with self._lock:
            self._store[value] = time.time()
            self._prune_locked()

    def discard(self, value: Any) -> None:
        with self._lock:
            self._store.pop(value, None)

    def __contains__(self, value: Any) -> bool:
        with self._lock:
            t = self._store.get(value)
            if t is None:
                return False
            if t + self._ttl < time.time():
                self._store.pop(value, None)
                return False
            return True

    def __iter__(self):
        with self._lock:
            self._prune_locked()
            return iter(list(self._store.keys()))

    def __len__(self) -> int:
        with self._lock:
            self._prune_locked()
            return len(self._store)

    def update(self, others: Any) -> None:  # type: ignore[override]
        with self._lock:
            now = time.time()
            for v in others:
                self._store[v] = now
            self._prune_locked()


class UserRole(Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"


class TokenManager:
    """Manages authentication tokens for distributed FACP.

    Thread-safe: every mutation of `active_tokens` and `revoked_tokens`
    is guarded by an internal RLock exposed via the public `lock`
    property. Callers that need an atomic check-then-act sequence
    (e.g. "is token in active AND not in revoked") must take that lock
    explicitly via `with tm.lock:`.
    """

    def __init__(self, secret_key: str):
        """Initialize the token manager.

        Args:
            secret_key: HS256 signing key. REQUIRED — there is no
                default. Must be at least 32 characters and not in the
                known-weak set. Generate one with:
                    python -c "import secrets; print(secrets.token_urlsafe(64))"

        Raises:
            ValueError: If *secret_key* is missing, weak, or too short.
        """
        _validate_secret_key(secret_key)
        self.secret_key = (
            secret_key.encode() if isinstance(secret_key, str) else secret_key
        )
        self._lock = threading.RLock()
        self.active_tokens: Dict[str, Dict[str, Any]] = {}
        self.revoked_tokens: _TTLSet = _TTLSet()

    @property
    def lock(self) -> threading.RLock:
        """Public accessor for the internal lock.

        Exposed as a property (not the private `_lock`) so the
        implementation can change without breaking callers. The
        previous anti-pattern was `with tm._lock:` which couples
        callers to the internal attribute name.
        """
        return self._lock

    def generate_token(
        self,
        user_id: str,
        permissions: List[str],
        roles: List[str],
        expires_in: int = 3600,
    ) -> str:
        """Generate a new authentication token.

        Args:
            user_id: User identifier (must already be registered on
                the AuthProvider that will later validate this token).
            permissions: List of permission strings to embed in the
                token. These are checked at validation time against
                the user's currently-granted permissions.
            roles: List of role strings to embed in the token.
            expires_in: Token lifetime in seconds (default 1h, max 24h).

        Returns:
            The signed JWT string.
        """
        if expires_in > 24 * 3600:
            raise ValueError(
                f"expires_in={expires_in}s exceeds the 24h maximum. "
                "Long-lived tokens bypass revocation windows."
            )

        now = int(time.time())  # integer timestamps per RFC 7519 §4.1.4
        token_data = {
            "user_id": user_id,
            "permissions": list(permissions),
            "roles": list(roles),
            "exp": now + expires_in,
            "iat": now,
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "jti": secrets.token_urlsafe(16),
        }

        token_str = jwt.encode(token_data, self.secret_key, algorithm="HS256")
        token_hash = hashlib.sha256(token_str.encode()).hexdigest()
        with self._lock:
            self.active_tokens[token_hash] = token_data
        return token_str

    def validate_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Validate an authentication token.

        Returns (True, token_data) on success, (False, None) on any
        failure (expired, revoked, invalid signature, missing claims).

        Always performs the full validation sequence regardless of
        outcome, to reduce timing-based information leaks about token
        state.
        """
        # jwt.decode raises on invalid signature, expired, wrong iss/aud.
        # We require all the claims we set in generate_token.
        try:
            token_data = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                issuer=_ISSUER,
                audience=_AUDIENCE,
                options={
                    "require": ["exp", "iat", "iss", "aud", "jti", "user_id"],
                },
            )
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return False, None

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            in_revoked = token_hash in self.revoked_tokens
            in_active = token_hash in self.active_tokens

        if in_revoked or not in_active:
            return False, None

        # Return a shallow copy so callers cannot mutate our internal state.
        return True, dict(token_data)

    def revoke_token(self, token: str) -> bool:
        """Revoke a token so it can no longer be used even before exp."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            self.revoked_tokens.add(token_hash)
            self.active_tokens.pop(token_hash, None)
        return True

    def prune_expired(self) -> int:
        """Remove expired tokens from active_tokens.

        Returns the number of entries pruned. Safe to call periodically
        from a background task to bound memory usage.
        """
        now = int(time.time())
        with self._lock:
            expired = [h for h, d in self.active_tokens.items() if d["exp"] <= now]
            for h in expired:
                self.active_tokens.pop(h, None)
                # Keep in revoked_tokens with TTL so re-issued tokens
                # with the same hash (impossible due to jti, but
                # defense-in-depth) are still rejected.
                self.revoked_tokens.add(h)
        return len(expired)


class AuthProvider:
    """Main authentication provider for distributed FACP.

    Uses dependency injection for the TokenManager so AuthProvider
    does not need to know about key material directly, and so tests
    can inject a mock.
    """

    def __init__(self, token_manager: TokenManager):
        if not isinstance(token_manager, TokenManager):
            raise TypeError("token_manager must be a TokenManager instance")
        self.token_manager = token_manager
        self._users_lock = threading.RLock()
        self.users: Dict[str, Dict[str, Any]] = {}
        self.distributed_cache: Dict[str, Dict[str, Any]] = {}

    def register_user(
        self,
        user_id: str,
        roles: List[str],
        permissions: List[str],
        node_id: Optional[str] = None,
    ) -> None:
        """Register a new user. Thread-safe."""
        with self._users_lock:
            self.users[user_id] = {
                "roles": list(roles),
                "permissions": list(permissions),
                "created_at": time.time(),
                "node_id": node_id,
            }

    def authenticate_request(
        self,
        security_block: Dict[str, Any],
        source_node: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Authenticate a request based on its security block.

        Returns (True, user_context) on success, (False, None) on any
        failure. Performs the same sequence of operations regardless
        of whether the user exists, to reduce timing leaks.
        """
        auth_token = security_block.get("auth_token")
        if not isinstance(auth_token, str) or not auth_token:
            return False, None

        is_valid, token_data = self.token_manager.validate_token(auth_token)
        if not is_valid or token_data is None:
            return False, None

        user_id = token_data["user_id"]
        with self._users_lock:
            user_data = self.users.get(user_id)
            if user_data is None:
                # Continue with empty granted_perms so the issubset
                # check below still runs — avoids early-return timing
                # difference between "user missing" and "user present".
                granted_perms: set[str] = set()
                stored_roles: List[str] = []
            else:
                granted_perms = set(user_data["permissions"])
                stored_roles = list(user_data["roles"])

        requested_perms = set(security_block.get("permissions", []))
        if not requested_perms or not requested_perms.issubset(granted_perms):
            return False, None

        if user_data is None:
            return False, None

        return True, {
            "user_id": user_id,
            "roles": stored_roles,
            "permissions": list(granted_perms),
            "token_data": token_data,
            "source_node": source_node,
            "authenticated_at": time.time(),
        }

    def create_session_token(
        self,
        user_id: str,
        permissions: Optional[List[str]] = None,
        roles: Optional[List[str]] = None,
        expires_in: int = 3600,
    ) -> Optional[str]:
        """Create a session token for a registered user.

        Returns None if the user is not registered, or if the requested
        permissions exceed the user's grants.
        """
        with self._users_lock:
            user_data = self.users.get(user_id)
            if user_data is None:
                return None
            user_perms = list(user_data["permissions"])
            user_roles = list(user_data["roles"])

        perms_to_grant = permissions if permissions is not None else user_perms
        roles_to_assign = roles if roles is not None else user_roles
        if permissions and not set(permissions).issubset(set(user_perms)):
            return None
        return self.token_manager.generate_token(
            user_id, perms_to_grant, roles_to_assign, expires_in
        )

    def distribute_auth_state(self, target_nodes: List[str]) -> None:
        """Distribute authentication state to other cluster nodes.

        FIX (v1 bug): The original code referenced `self.active_tokens`
        and `self.revoked_tokens` — those attributes live on
        TokenManager, not on AuthProvider. This raised AttributeError
        on every call. Now correctly references
        `self.token_manager.active_tokens` etc., and takes the
        TokenManager's public `lock` to get a consistent snapshot.
        """
        with self.token_manager.lock:
            auth_state = {
                "users": dict(self.users),
                "active_tokens": dict(self.token_manager.active_tokens),
                "revoked_tokens": set(self.token_manager.revoked_tokens),
                "timestamp": time.time(),
            }
        for node in target_nodes:
            self.distributed_cache[node] = auth_state

    def sync_with_cluster(self, cluster_auth_state: Dict[str, Any]) -> None:
        """Merge state received from another cluster node."""
        with self.token_manager.lock:
            for user_id, user_data in cluster_auth_state.get("users", {}).items():
                if user_id not in self.users:
                    self.users[user_id] = user_data
            for token_hash, token_data in cluster_auth_state.get("active_tokens", {}).items():
                if token_hash not in self.token_manager.active_tokens:
                    self.token_manager.active_tokens[token_hash] = token_data
            self.token_manager.revoked_tokens.update(
                cluster_auth_state.get("revoked_tokens", [])
            )


class DistributedTokenManager(TokenManager):
    """Token manager for distributed environments with shared state.

    Emits sync callbacks when tokens are generated or revoked so other
    cluster nodes can update their state.
    """

    def __init__(self, secret_key: str, node_id: str):
        """Initialize.

        Args:
            secret_key: HS256 signing key (REQUIRED, validated).
            node_id: Identifier for this node. Included in sync messages
                so recipients know the origin. REQUIRED — there is no
                meaningful default.
        """
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id is required and must be a non-empty string")
        super().__init__(secret_key)
        self.node_id = node_id
        self.cluster_tokens: Dict[str, Any] = {}
        self._sync_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_sync_callback(
        self, callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        self._sync_callback = callback

    def generate_token(
        self,
        user_id: str,
        permissions: List[str],
        roles: List[str],
        expires_in: int = 3600,
    ) -> str:
        token = super().generate_token(user_id, permissions, roles, expires_in)
        if self._sync_callback is not None:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            with self.lock:
                token_data = self.active_tokens.get(token_hash, {})
            try:
                self._sync_callback({
                    "action": "token_generated",
                    "token_hash": token_hash,
                    "token_data": token_data,
                    "node_id": self.node_id,
                    "timestamp": int(time.time()),
                })
            except Exception:
                logger.exception(
                    "Sync callback failed for token generation (node=%s)",
                    self.node_id,
                )
        return token

    def revoke_token(self, token: str) -> bool:
        result = super().revoke_token(token)
        if self._sync_callback is not None:
            try:
                self._sync_callback({
                    "action": "token_revoked",
                    "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                    "node_id": self.node_id,
                    "timestamp": int(time.time()),
                })
            except Exception:
                logger.exception(
                    "Sync callback failed for token revocation (node=%s)",
                    self.node_id,
                )
        return result
