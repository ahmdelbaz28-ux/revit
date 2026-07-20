"""Authentication System for Distributed FACP"""
import hashlib
import os
import secrets
import time
from enum import Enum
from typing import Any, Dict, Optional

import jwt  # PyJWT
from cryptography.hazmat.primitives import serialization


class UserRole(Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"


class TokenManager:
    """Manages authentication tokens for distributed FACP"""

    def __init__(  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        self,
        private_key_path: str = None,
        public_key_path: str = None,
        secret_key: str = None,
    ):
        """
        Initialize TokenManager with either RSA key files or HMAC secret.

        V289 SAFETY FIX: Previously, if private_key_path was None or didn't
        exist, the code SILENTLY generated a random RSA key pair. This meant:
        - Every app restart generated new keys
        - ALL existing tokens became invalid after restart
        - In a distributed FACP system, nodes couldn't validate each other's
          tokens (different random keys per node)

        Now the caller must explicitly choose an authentication mode:
        1. RSA (production, distributed): pass private_key_path + public_key_path
           pointing to persistent PEM key files shared across nodes.
        2. HMAC (simpler, single-instance): pass secret_key (a strong random
           string). Uses HS256 algorithm — no key rotation issue.

        If NEITHER is provided, raises RuntimeError (fail-loud — no silent
        random key generation that would invalidate tokens on restart).
        """
        self.active_tokens = {}  # token_hash -> token_data
        self.revoked_tokens = set()  # Set of revoked token hashes
        self._signing_mode = None  # 'rsa' or 'hmac'
        self._hmac_secret = None
        self.private_key = None
        self.public_key = None

        has_rsa_paths = bool(private_key_path or public_key_path)
        has_hmac_secret = bool(secret_key)

        if has_rsa_paths and has_hmac_secret:
            raise ValueError(
                "TokenManager: cannot specify both RSA key paths and HMAC secret. "
                "Choose one authentication mode: RSA (for distributed deployments "
                "with persistent key files) or HMAC (for single-instance with "
                "shared secret)."
            )

        if not has_rsa_paths and not has_hmac_secret:
            raise RuntimeError(
                "TokenManager: no authentication credentials provided. "
                "Pass either private_key_path/public_key_path (RSA, for "
                "distributed deployments) or secret_key (HMAC, for "
                "single-instance). Refusing to generate random RSA keys — "
                "that would invalidate all existing tokens on every restart "
                "(V289 life-safety fix)."
            )

        if has_rsa_paths:
            # RSA mode (RS256) — for distributed deployments with persistent keys
            self._signing_mode = 'rsa'
            if private_key_path and os.path.exists(private_key_path):
                with open(private_key_path, "rb") as key_file:
                    self.private_key = serialization.load_pem_private_key(
                        key_file.read(),
                        password=None,
                    )
            else:
                raise FileNotFoundError(
                    f"TokenManager: private_key_path '{private_key_path}' does not exist. "
                    f"RSA mode requires a persistent PEM key file — generate one with: "
                    f"openssl genrsa -out private_key.pem 2048"
                )

            if public_key_path and os.path.exists(public_key_path):
                with open(public_key_path, "rb") as key_file:
                    self.public_key = serialization.load_pem_public_key(key_file.read())
            else:
                # Derive public key from private key (single-file mode)
                self.public_key = self.private_key.public_key()
        else:
            # HMAC mode (HS256) — for single-instance with shared secret
            self._signing_mode = 'hmac'
            self._hmac_secret = secret_key.encode("utf-8")
            if len(secret_key) < 32:
                raise ValueError(
                    f"TokenManager: HMAC secret_key must be at least 32 characters "
                    f"for adequate security (got {len(secret_key)}). Generate one with: "
                    f"python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )

    def generate_token(self, user_id: str, permissions: list, roles: list, expires_in: int = 3600) -> str:
        """
        Generate a new authentication token with expiration
        :param user_id: User identifier
        :param permissions: List of permissions
        :param roles: List of roles
        :param expires_in: Token expiration time in seconds (default 1 hour)
        :return: Generated token string
        """
        token_data = {
            "user_id": user_id,
            "permissions": permissions,
            "roles": roles,
            "exp": int(time.time()) + expires_in,  # Unix timestamp for expiration
            "iat": int(time.time()),  # Issued at time
            "jti": secrets.token_urlsafe(16),  # JWT ID for uniqueness
            "nbf": int(time.time()) - 10  # Not before (allow 10 sec clock skew)
        }

        if self._signing_mode == 'rsa':
            sign_key = self.private_key
            algorithm = "RS256"
        else:  # hmac
            sign_key = self._hmac_secret
            algorithm = "HS256"

        # Create token string using JWT
        token_str = jwt.encode(
            token_data,
            sign_key,
            algorithm=algorithm
        )

        # Store token with its data
        token_hash = hashlib.sha256(token_str.encode()).hexdigest()
        self.active_tokens[token_hash] = token_data

        return token_str

    def validate_token(self, token: str) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validate an authentication token
        :param token: Token string to validate
        :return: (is_valid, token_data)
        """
        try:
            # Check if token is revoked first (before expensive crypto operation)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            if token_hash in self.revoked_tokens:
                return False, None

            if self._signing_mode == 'rsa':
                validate_key = self.public_key
                algorithms = ["RS256"]
            else:  # hmac
                validate_key = self._hmac_secret
                algorithms = ["HS256"]

            # Decode JWT token
            token_data = jwt.decode(
                token,
                validate_key,
                algorithms=algorithms,
                options={
                    "require": ["exp", "iat", "nbf"],
                    "verify_exp": True,  # Verify expiration
                    "verify_iat": True,  # Verify issued at time
                    "verify_nbf": True,  # Verify not before time
                }
            )

            # Additional check: verify token is still in our active tokens list
            if token_hash in self.active_tokens:
                # Update active tokens if needed
                self.active_tokens[token_hash] = token_data
                return True, token_data
            else:
                # Token exists but not in our active list - might be stale
                return False, None

        except jwt.ExpiredSignatureError:
            # Clean up expired token if it exists in our records
            try:
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                if token_hash in self.active_tokens:
                    del self.active_tokens[token_hash]
            except Exception:
                pass  # Ignore errors during cleanup
            return False, None
        except jwt.InvalidTokenError:
            return False, None

    def revoke_token(self, token: str) -> bool:
        """
        Revoke a token
        :param token: Token to revoke
        :return: Success status
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self.revoked_tokens.add(token_hash)
        if token_hash in self.active_tokens:
            del self.active_tokens[token_hash]
        return True


class AuthProvider:
    """Main authentication provider for distributed FACP"""

    def __init__(self, secret_key: str = None, private_key_path: str = None, public_key_path: str = None):
        """
        Initialize AuthProvider.

        V289 FIX: Previously __init__ took `secret_key` and passed it to
        TokenManager as `private_key_path` — which was interpreted as a file
        path, not a secret. Since the "secret" was never a valid file path,
        TokenManager silently generated random RSA keys on every instantiation.

        Now AuthProvider correctly delegates to TokenManager with the right
        parameter names. The caller must provide EITHER:
        - secret_key (for HMAC/HS256 mode — single-instance), OR
        - private_key_path + public_key_path (for RSA/RS256 mode — distributed)

        If neither is provided, raises RuntimeError (fail-loud).
        """
        self.token_manager = TokenManager(
            private_key_path=private_key_path,
            public_key_path=public_key_path,
            secret_key=secret_key,
        )
        self.users = {}  # user_id -> user_data
        self.distributed_cache = {}  # For sharing auth state across nodes

    def register_user(self, user_id: str, roles: list, permissions: list, node_id: Optional[str] = None):
        """Register a new user"""
        self.users[user_id] = {
            "roles": roles,
            "permissions": permissions,
            "created_at": time.time(),
            "node_id": node_id  # Which node registered this user
        }

    def authenticate_request(self, security_block: Dict[str, Any], source_node: Optional[str] = None) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Authenticate a request based on security block
        :param security_block: Security information from request
        :param source_node: Node that originated the request
        :return: (is_authenticated, user_context)
        """
        auth_token = security_block.get("auth_token")
        if not auth_token:
            return False, None

        is_valid, token_data = self.token_manager.validate_token(auth_token)
        if not is_valid:
            return False, None

        user_id = token_data["user_id"]
        if user_id not in self.users:
            return False, None

        user_data = self.users[user_id]

        # Check if requested permissions are subset of granted permissions
        requested_perms = set(security_block.get("permissions", []))
        granted_perms = set(user_data["permissions"])

        if not requested_perms.issubset(granted_perms):
            return False, None

        return True, user_data
