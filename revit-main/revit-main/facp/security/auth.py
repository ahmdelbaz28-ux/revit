"""
FACP Authentication System
"""
from typing import Optional, Dict, Any
import secrets
import time
from datetime import datetime, timedelta
import hashlib
import hmac


class TokenManager:
    """
    Manages authentication tokens for FACP
    """
    def __init__(self, secret_key: str = "default_secret_for_dev"):
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
        self.active_tokens = {}  # token_hash -> token_data

    def generate_token(self, user_id: str, permissions: list, expires_in: int = 3600) -> str:
        """
        Generate a new authentication token
        :param user_id: User identifier
        :param permissions: List of permissions
        :param expires_in: Token expiration time in seconds
        :return: Generated token string
        """
        token_data = {
            "user_id": user_id,
            "permissions": permissions,
            "issued_at": time.time(),
            "expires_at": time.time() + expires_in
        }
        
        # Create token string
        token_str = secrets.token_urlsafe(32)
        
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
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        if token_hash not in self.active_tokens:
            return False, None
            
        token_data = self.active_tokens[token_hash]
        
        # Check if token is expired
        if time.time() > token_data["expires_at"]:
            # Clean up expired token
            del self.active_tokens[token_hash]
            return False, None
            
        return True, token_data

    def revoke_token(self, token: str) -> bool:
        """
        Revoke a token
        :param token: Token to revoke
        :return: Success status
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        if token_hash in self.active_tokens:
            del self.active_tokens[token_hash]
            return True
        return False


class AuthProvider:
    """
    Main authentication provider for FACP
    """
    def __init__(self):
        self.token_manager = TokenManager()
        self.users = {}  # user_id -> user_data

    def register_user(self, user_id: str, role: str, permissions: list):
        """Register a new user"""
        self.users[user_id] = {
            "role": role,
            "permissions": permissions,
            "created_at": time.time()
        }

    def authenticate_request(self, security_block: Dict[str, Any]) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Authenticate a request based on security block
        :param security_block: Security information from request
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

        # Return user context
        return True, {
            "user_id": user_id,
            "role": user_data["role"],
            "permissions": list(granted_perms),
            "token_data": token_data
        }

    def create_session_token(self, user_id: str, permissions: list = None, 
                           expires_in: int = 3600) -> Optional[str]:
        """Create a session token for a user"""
        if user_id not in self.users:
            return None
            
        user_perms = self.users[user_id]["permissions"]
        perms_to_grant = permissions if permissions is not None else user_perms
        
        # Ensure requested permissions are subset of user's allowed permissions
        if permissions and not set(permissions).issubset(set(user_perms)):
            return None
            
        return self.token_manager.generate_token(user_id, perms_to_grant, expires_in)