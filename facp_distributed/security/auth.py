"""Authentication System for Distributed FACP"""
import hashlib
import secrets
import time
from enum import Enum
from typing import Any, Dict, Optional

import jwt  # PyJWT
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import os


class UserRole(Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"


class TokenManager:
    """Manages authentication tokens for distributed FACP"""

    def __init__(self, private_key_path: str = None, public_key_path: str = None):
        # Generate RSA key pair if not provided
        if private_key_path and os.path.exists(private_key_path):
            with open(private_key_path, "rb") as key_file:
                self.private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None,
                )
        else:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
        
        if public_key_path and os.path.exists(public_key_path):
            with open(public_key_path, "rb") as key_file:
                self.public_key = serialization.load_pem_public_key(key_file.read())
        else:
            self.public_key = self.private_key.public_key()
        
        self.active_tokens = {}  # token_hash -> token_data
        self.revoked_tokens = set()  # Set of revoked token hashes

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

        # Create token string using JWT with RS256 algorithm
        token_str = jwt.encode(
            token_data, 
            self.private_key, 
            algorithm="RS256"
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

            # Decode JWT token using public key (RS256)
            token_data = jwt.decode(
                token, 
                self.public_key, 
                algorithms=["RS256"],
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
            except:
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

    def __init__(self, secret_key: str = "default_secret_for_dev"):
        self.token_manager = TokenManager(secret_key)
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