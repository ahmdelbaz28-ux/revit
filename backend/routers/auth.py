"""
backend/routers/auth.py — Authentication Endpoints
=================================================

REST API endpoints for authentication and authorization.
Provides login, register, token refresh, and API key management.

ENDPOINTS:
- POST /api/v1/auth/login - Login with username/password
- POST /api/v1/auth/register - Register new user
- POST /api/v1/auth/refresh - Refresh access token
- POST /api/v1/auth/api-key - Create new API key
- GET /api/v1/auth/me - Get current user info
- DELETE /api/v1/auth/api-key/{key_id} - Revoke API key

USAGE:
    # Login
    curl -X POST http://localhost:8000/api/v1/auth/login \
      -H "Content-Type: application/json" \
      -d '{"username": "admin", "password": "admin123"}'
    
    # Use token
    curl http://localhost:8000/api/v1/health \
      -H "Authorization: Bearer <token>"
    
    # Use API key
    curl http://localhost:8000/api/v1/health \
      -H "X-API-Key: <api_key>"
"""

import logging
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from backend.rbac import Permission, Role, has_permission

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Authentication"])

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ═══════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "viewer"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # 30 minutes


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    disabled: bool = False


class APIKeyCreateResponse(BaseModel):
    api_key: str
    key_id: str
    message: str = "Store this key securely. It will not be shown again."


class APIKeyInfo(BaseModel):
    key_id: str
    name: str
    created_at: float
    last_used: Optional[float] = None
    disabled: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# IN-MEMORY USER STORE (Replace with database in production)
# ═══════════════════════════════════════════════════════════════════════════

class User:
    """User data structure."""
    def __init__(
        self,
        id: str,
        username: str,
        email: str,
        role: Role,
        disabled: bool = False,
        hashed_password: str = "",
        created_at: float = 0.0,
        last_login: float = 0.0
    ):
        self.id = id
        self.username = username
        self.email = email
        self.role = role
        self.disabled = disabled
        self.hashed_password = hashed_password
        self.created_at = created_at or time.time()
        self.last_login = last_login

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "disabled": self.disabled,
            "created_at": self.created_at,
            "last_login": self.last_login
        }


# Demo users (password = username + "123")
# These hashes are SHA-256 of the passwords
_users_db: dict[str, User] = {
    "admin": User(
        id="admin-001",
        username="admin",
        email="admin@fireai.local",
        role=Role.ADMIN,
        hashed_password="240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"  # admin123
    ),
    "engineer": User(
        id="engineer-001",
        username="engineer",
        email="engineer@fireai.local",
        role=Role.ENGINEER,
        hashed_password="80ca306ac6e68366dd0a26125c9647e0c61fac6668cec6016f5fe30fb12e99bd"  # engineer123
    ),
    "viewer": User(
        id="viewer-001",
        username="viewer",
        email="viewer@fireai.local",
        role=Role.VIEWER,
        hashed_password="65375049b9e4d7cad6c9ba286fdeb9394b28135a3e84136404cfccfdcc438894"  # viewer123
    ),
}

# API Keys store (key_id -> {user_id, hashed_key, name, created_at, last_used, disabled})
_api_keys_db: dict[str, dict] = {}

# JWT Configuration
import os
SECRET_KEY = os.environ.get("SECRET_KEY", "INSECURE_DEV_KEY_CHANGE_IN_PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# ═══════════════════════════════════════════════════════════════════════════
# TOKEN UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def create_access_token(data: dict) -> str:
    """Create JWT access token."""
    import jwt
    from datetime import datetime, timedelta, timezone
    
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire.timestamp(), "iat": datetime.now(timezone.utc).timestamp()})
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token."""
    import jwt
    from datetime import datetime, timedelta, timezone
    
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire.timestamp(), "iat": datetime.now(timezone.utc).timestamp()})
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode JWT token."""
    import jwt
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None


def hash_password(password: str) -> str:
    """Hash password (simple for demo, use bcrypt in production)."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against hash."""
    return hash_password(plain) == hashed


def generate_api_key() -> tuple[str, str]:
    """Generate new API key. Returns (plain_key, key_id)."""
    plain_key = f"sk_{secrets.token_urlsafe(32)}"
    key_id = f"key_{secrets.token_hex(8)}"
    return plain_key, key_id


def hash_api_key(api_key: str) -> str:
    """Hash API key for storage."""
    import hashlib
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(api_key: str) -> Optional[User]:
    """Verify API key and return user."""
    import hmac
    hashed = hash_api_key(api_key)
    
    for key_id, key_data in _api_keys_db.items():
        if key_data["disabled"]:
            continue
        if hmac.compare_digest(hashed, key_data["hashed_key"]):
            key_data["last_used"] = time.time()
            user = _users_db.get(key_data["user_id"])
            return user
    return None


# ═══════════════════════════════════════════════════════════════════════════
# DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header)
) -> User:
    """Get current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Try API key first
    if api_key:
        user = verify_api_key(api_key)
        if user:
            return user
    
    # Try bearer token
    if credentials:
        payload = verify_token(credentials.credentials)
        if payload:
            user = _users_db.get(payload.get("sub"))
            if user:
                return user
    
    raise credentials_exception


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT tokens.
    
    Demo credentials:
    - admin / admin123
    - engineer / engineer123
    - viewer / viewer123
    """
    user = _users_db.get(request.username)
    
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    # Update last login
    user.last_login = time.time()
    
    # Create tokens
    token_data = {"sub": user.username, "role": user.role.value, "user_id": user.id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    logger.info(f"User {user.username} logged in successfully")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/register", response_model=UserResponse)
async def register(request: RegisterRequest):
    """Register a new user (admin only in production)."""
    # Check if username exists
    if request.username in _users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Validate role
    try:
        role = Role(request.role.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {[r.value for r in Role]}"
        )
    
    # Create user
    user_id = f"user-{secrets.token_hex(4)}"
    user = User(
        id=user_id,
        username=request.username,
        email=request.email,
        role=role,
        hashed_password=hash_password(request.password),
        created_at=time.time()
    )
    
    _users_db[request.username] = user
    
    logger.info(f"New user registered: {user.username} with role {user.role.value}")
    
    return UserResponse(**user.to_dict())


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest):
    """Refresh access token using refresh token."""
    payload = verify_token(request.refresh_token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    user = _users_db.get(payload.get("sub"))
    if not user or user.disabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled"
        )
    
    # Create new tokens
    token_data = {"sub": user.username, "role": user.role.value, "user_id": user.id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/api-key", response_model=APIKeyCreateResponse)
async def create_api_key(current_user: User = Depends(get_current_user)):
    """Create a new API key for the current user."""
    plain_key, key_id = generate_api_key()
    hashed_key = hash_api_key(plain_key)
    
    _api_keys_db[key_id] = {
        "user_id": current_user.username,
        "name": f"Key for {current_user.username}",
        "hashed_key": hashed_key,
        "created_at": time.time(),
        "last_used": None,
        "disabled": False
    }
    
    logger.info(f"API key created for user {current_user.username}")
    
    return APIKeyCreateResponse(
        api_key=plain_key,
        key_id=key_id
    )


@router.get("/api-keys", response_model=list[APIKeyInfo])
async def list_api_keys(current_user: User = Depends(get_current_user)):
    """List all API keys for the current user."""
    keys = []
    for key_id, key_data in _api_keys_db.items():
        if key_data["user_id"] == current_user.username:
            keys.append(APIKeyInfo(
                key_id=key_id,
                name=key_data["name"],
                created_at=key_data["created_at"],
                last_used=key_data.get("last_used"),
                disabled=key_data.get("disabled", False)
            ))
    return keys


@router.delete("/api-key/{key_id}")
async def revoke_api_key(key_id: str, current_user: User = Depends(get_current_user)):
    """Revoke an API key."""
    if key_id not in _api_keys_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    if _api_keys_db[key_id]["user_id"] != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot revoke API key belonging to another user"
        )
    
    _api_keys_db[key_id]["disabled"] = True
    logger.info(f"API key {key_id} revoked by {current_user.username}")
    
    return {"message": "API key revoked successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(**current_user.to_dict())
