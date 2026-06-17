"""tests/test_auth.py — Authentication Tests.
=======================================

Unit tests for authentication module.
Tests JWT tokens, password hashing, and user management.
"""

import os
import time

import pytest

# Set environment before importing
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_hash_password_returns_string(self) -> None:
        """Test that hash_password returns a string."""
        from backend.routers.auth import hash_password
        result = hash_password("testpassword")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_password_is_different_each_time(self) -> None:
        """Test that same password produces different hashes (salt)."""
        from backend.routers.auth import hash_password
        hash1 = hash_password("testpassword")
        hash2 = hash_password("testpassword")
        assert hash1 != hash2  # Different salts

    def test_verify_password_correct(self) -> None:
        """Test that verify_password returns True for correct password."""
        from backend.routers.auth import hash_password, verify_password
        password = "MySecurePassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """Test that verify_password returns False for incorrect password."""
        from backend.routers.auth import hash_password, verify_password
        hashed = hash_password("CorrectPassword")
        assert verify_password("WrongPassword", hashed) is False


class TestAPIKeyHashing:
    """Test API key hashing functions."""

    def test_hash_api_key_returns_string(self) -> None:
        """Test that hash_api_key returns a string."""
        from backend.routers.auth import hash_api_key
        result = hash_api_key("sk_test_api_key_12345")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 produces 64 hex chars

    def test_hash_api_key_is_consistent(self) -> None:
        """Test that same key produces same hash."""
        from backend.routers.auth import hash_api_key
        key = "sk_test_api_key_12345"
        assert hash_api_key(key) == hash_api_key(key)

    def test_verify_api_key_hash_correct(self) -> None:
        """Test that verify_api_key_hash returns True for correct key."""
        from backend.routers.auth import hash_api_key, verify_api_key_hash
        key = "sk_test_api_key_12345"
        hashed = hash_api_key(key)
        assert verify_api_key_hash(key, hashed) is True

    def test_verify_api_key_hash_incorrect(self) -> None:
        """Test that verify_api_key_hash returns False for incorrect key."""
        from backend.routers.auth import hash_api_key, verify_api_key_hash
        hashed = hash_api_key("correct_key")
        assert verify_api_key_hash("wrong_key", hashed) is False


class TestJWTTokens:
    """Test JWT token functions."""

    def test_create_access_token_returns_string(self) -> None:
        """Test that create_access_token returns a JWT string."""
        from backend.routers.auth import create_access_token
        token = create_access_token({"sub": "testuser", "role": "admin"})
        assert isinstance(token, str)
        assert "." in token  # JWT has 3 parts separated by dots

    def test_create_refresh_token_returns_string(self) -> None:
        """Test that create_refresh_token returns a JWT string."""
        from backend.routers.auth import create_refresh_token
        token = create_refresh_token({"sub": "testuser"})
        assert isinstance(token, str)
        assert "." in token

    def test_verify_token_valid(self) -> None:
        """Test that verify_token returns payload for valid token."""
        from backend.routers.auth import create_access_token, verify_token
        data = {"sub": "testuser", "role": "admin", "user_id": "123"}
        token = create_access_token(data)
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["role"] == "admin"

    def test_verify_token_invalid(self) -> None:
        """Test that verify_token returns None for invalid token."""
        from backend.routers.auth import verify_token
        payload = verify_token("invalid.token.here")
        assert payload is None

    def test_verify_token_expired(self) -> None:
        """Test that verify_token returns None for expired token."""
        import jwt

        from backend.routers.auth import ALGORITHM, SECRET_KEY, verify_token
        # Create an expired token
        payload = {
            "sub": "testuser",
            "exp": time.time() - 3600,  # Expired 1 hour ago
            "iat": time.time() - 7200
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        result = verify_token(token)
        assert result is None


class TestGenerateAPIKey:
    """Test API key generation."""

    def test_generate_api_key_returns_tuple(self) -> None:
        """Test that generate_api_key returns (plain_key, key_id)."""
        from backend.routers.auth import generate_api_key
        plain_key, key_id = generate_api_key()
        assert isinstance(plain_key, str)
        assert isinstance(key_id, str)
        assert plain_key.startswith("sk_")
        assert key_id.startswith("key_")

    def test_generate_api_key_is_unique(self) -> None:
        """Test that each generated key is unique."""
        from backend.routers.auth import generate_api_key
        keys = [generate_api_key() for _ in range(10)]
        plain_keys = [k[0] for k in keys]
        key_ids = [k[1] for k in keys]
        assert len(set(plain_keys)) == 10
        assert len(set(key_ids)) == 10


class TestUserClass:
    """Test User class."""

    def test_user_to_dict(self) -> None:
        """Test User.to_dict() returns correct dictionary."""
        from backend.rbac import Role
        from backend.routers.auth import User
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            role=Role.ADMIN,
            disabled=False
        )
        user_dict = user.to_dict()
        assert user_dict["id"] == "test-id"
        assert user_dict["username"] == "testuser"
        assert user_dict["email"] == "test@example.com"
        assert user_dict["role"] == "admin"
        assert user_dict["disabled"] is False

    def test_user_to_dict_with_string_role(self) -> None:
        """Test User.to_dict() handles string role."""
        from backend.routers.auth import User
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            role="viewer",  # String role
            disabled=False
        )
        user_dict = user.to_dict()
        assert user_dict["role"] == "viewer"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
