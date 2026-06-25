"""
Authentication System for Distributed FACP
"""
import hashlib
import secrets
import time
from enum import Enum
from typing import Any, Dict, Optional

import jwt  # PyJWT


class UserRole(Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"


class TokenManager:
    """
    Manages authentication tokens for distributed FACP
    """
    def __init__(self, secret_key: str = "default_secret_for_dev"):
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
        self.active_tokens = {}  # token_hash -> token_data
        self.revoked_tokens = set()  # Set of revoked token hashes

    def generate_token(self, user_id: str, permissions: list, roles: list, expires_in: int = 3600) -> str:
        """
        Generate a new authentication token
        :param user_id: User identifier
        :param permissions: List of permissions
        :param roles: List of roles
        :param expires_in: Token expiration time in seconds
        :return: Generated token string
        """
        token_data = {
            "user_id": user_id,
            "permissions": permissions,
            "roles": roles,
            "exp": time.time() + expires_in,
            "iat": time.time(),
            "jti": secrets.token_urlsafe(16)  # JWT ID for uniqueness
        }

        # Create token string using JWT
        token_str = jwt.encode(token_data, self.secret_key, algorithm="HS256")

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
            # Decode JWT token
            token_data = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            # Check if token is revoked
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            if token_hash in self.revoked_tokens:
                return False, None

            # Check if token is expired (JWT decode handles this automatically)
            # But we also check our own records
            if time.time() > token_data["exp"]:
                # Clean up expired token
                self.revoke_token(token)
                return False, None

            return True, token_data

        except jwt.ExpiredSignatureError:
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
    """
    Main authentication provider for distributed FACP
    """
    def __init__(self, secret_key: str = "default_secret_for_dev"):
        self.token_manager = TokenManager(secret_key)
        self.users = {}  # user_id -> user_data
        self.distributed_cache = {}  # For sharing auth state across nodes

    def register_user(self, user_id: str, roles: list, permissions: list, node_id: str = None):
        """Register a new user"""
        self.users[user_id] = {
            "roles": roles,
            "permissions": permissions,
            "created_at": time.time(),
            "node_id": node_id  # Which node registered this user
        }

    def authenticate_request(self, security_block: Dict[str, Any], source_node: str = None) -> tuple[bool, Optional[Dict[str, Any]]]:
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

        # Return user context with distributed information
        return True, {
            "user_id": user_id,
            "roles": user_data["roles"],
            "permissions": list(granted_perms),
            "token_data": token_data,
            "source_node": source_node,
            "authenticated_at": time.time()
        }

    def create_session_token(self, user_id: str, permissions: list = None,
                           roles: list = None, expires_in: int = 3600) -> Optional[str]:
        """Create a session token for a user"""
        if user_id not in self.users:
            return None

        user_perms = self.users[user_id]["permissions"]
        user_roles = self.users[user_id]["roles"]

        perms_to_grant = permissions if permissions is not None else user_perms
        roles_to_assign = roles if roles is not None else user_roles

        # Ensure requested permissions are subset of user's allowed permissions
        if permissions and not set(permissions).issubset(set(user_perms)):
            return None

        return self.token_manager.generate_token(user_id, perms_to_grant, roles_to_assign, expires_in)

    def distribute_auth_state(self, target_nodes: list):
        """
        Distribute authentication state to other nodes in the cluster
        """
        auth_state = {
            "users": self.users,
            "active_tokens": dict(self.active_tokens.items()),
            "revoked_tokens": list(self.revoked_tokens),
            "timestamp": time.time()
        }

        # In a real implementation, this would send the state to other nodes
        # via the message bus or other distributed mechanism
        for node in target_nodes:
            self.distributed_cache[node] = auth_state

    def sync_with_cluster(self, cluster_auth_state: Dict[str, Any]):
        """
        Sync authentication state with cluster
        """
        # Merge cluster state with local state
        for user_id, user_data in cluster_auth_state.get("users", {}).items():
            if user_id not in self.users:
                self.users[user_id] = user_data

        for token_hash, token_data in cluster_auth_state.get("active_tokens", {}).items():
            if token_hash not in self.active_tokens:
                self.active_tokens[token_hash] = token_data

        self.revoked_tokens.update(cluster_auth_state.get("revoked_tokens", []))


class DistributedTokenManager(TokenManager):
    """
    Token manager for distributed environments with shared state
    """
    def __init__(self, secret_key: str = "default_secret_for_dev", node_id: str = "node_0"):
        super().__init__(secret_key)
        self.node_id = node_id
        self.cluster_tokens = {}  # Shared tokens across cluster
        self.token_sync_callback = None

    def set_sync_callback(self, callback):
        """Set callback for syncing token state with cluster"""
        self.token_sync_callback = callback

    def generate_token(self, user_id: str, permissions: list, roles: list, expires_in: int = 3600) -> str:
        """Generate token and sync with cluster"""
        token = super().generate_token(user_id, permissions, roles, expires_in)

        # Sync with cluster if callback is available
        if self.token_sync_callback:
            self.token_sync_callback({
                "action": "token_generated",
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "token_data": self.active_tokens[hashlib.sha256(token.encode()).hexdigest()],
                "node_id": self.node_id,
                "timestamp": time.time()
            })

        return token

    def revoke_token(self, token: str) -> bool:
        """Revoke token and sync with cluster"""
        result = super().revoke_token(token)

        # Sync with cluster if callback is available
        if self.token_sync_callback:
            self.token_sync_callback({
                "action": "token_revoked",
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "node_id": self.node_id,
                "timestamp": time.time()
            })

        return result
