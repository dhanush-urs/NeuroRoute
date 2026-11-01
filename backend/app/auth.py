"""
Authentication module for NeuroRoute.
Provides JWT-based authentication and authorization.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from enum import Enum

import jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.core.config import get_settings


class UserRole(str, Enum):
    """User roles for authorization."""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class TokenData(BaseModel):
    """Decoded token data."""
    sub: str  # user_id
    username: str
    roles: List[UserRole] = Field(default_factory=list)
    exp: int
    iat: int
    token_type: str = "access"


class Token(BaseModel):
    """Token response model."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserCreate(BaseModel):
    """User creation model."""
    username: str
    password: str
    roles: List[UserRole] = Field(default_factory=lambda: [UserRole.VIEWER])


class UserResponse(BaseModel):
    """User response model."""
    id: str
    username: str
    roles: List[UserRole]
    is_active: bool = True
    created_at: datetime


class UserInDB(UserResponse):
    """User model with hashed password."""
    hashed_password: str


# Simple in-memory user store for development
# In production, this would be a database
_users_db: Dict[str, UserInDB] = {}


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    import bcrypt
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    token_type: str = "access",
) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.auth_access_token_expire_minutes))
    to_encode.update({
        "exp": expire,
        "iat": now,
        "token_type": token_type,
    })
    return jwt.encode(to_encode, settings.auth_secret_key, algorithm=settings.auth_algorithm)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a JWT refresh token."""
    settings = get_settings()
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.auth_refresh_token_expire_days)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "token_type": "refresh",
    })
    return jwt.encode(to_encode, settings.auth_secret_key, algorithm=settings.auth_algorithm)


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=[settings.auth_algorithm],
        )
        return TokenData(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# FastAPI security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenData]:
    """Get current user from token (returns None if no auth enabled or no token)."""
    settings = get_settings()
    
    # If auth is disabled, return None (public access)
    if not settings.auth_enabled:
        return None
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return decode_token(credentials.credentials)


async def require_auth(
    current_user: Optional[TokenData] = Depends(get_current_user),
) -> Optional[TokenData]:
    """Require authentication (raises 401 if not authenticated and auth is enabled)."""
    settings = get_settings()
    
    # If auth is disabled, allow public access
    if not settings.auth_enabled:
        return None
    
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def require_role(*allowed_roles: UserRole):
    """Dependency factory for role-based access control."""
    async def role_checker(current_user: Optional[TokenData] = Depends(require_auth)) -> Optional[TokenData]:
        settings = get_settings()
        
        # If auth is disabled, allow public access
        if not settings.auth_enabled:
            return None
            
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        if not any(role in current_user.roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker


# Pre-defined role dependencies
require_admin = require_role(UserRole.ADMIN)
require_operator = require_role(UserRole.ADMIN, UserRole.OPERATOR)
require_viewer = require_role(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER)


# Initialize default users for development
def init_default_users():
    """Initialize default users for development."""
    if not get_settings().auth_enabled:
        return
    
    if not _users_db:
        # Create default admin user
        admin_user = UserInDB(
            id="admin",
            username="admin",
            hashed_password=get_password_hash("admin123"),
            roles=[UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        _users_db[admin_user.username] = admin_user
        
        # Create operator user
        operator_user = UserInDB(
            id="operator",
            username="operator",
            hashed_password=get_password_hash("operator123"),
            roles=[UserRole.OPERATOR, UserRole.VIEWER],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        _users_db[operator_user.username] = operator_user
        
        # Create viewer user
        viewer_user = UserInDB(
            id="viewer",
            username="viewer",
            hashed_password=get_password_hash("viewer123"),
            roles=[UserRole.VIEWER],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        _users_db[viewer_user.username] = viewer_user


def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    """Authenticate a user with username and password."""
    user = _users_db.get(username)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def login(username: str, password: str) -> Token:
    """Login endpoint - authenticate and return tokens."""
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": user.id, "username": user.username, "roles": [r.value for r in user.roles]},
    )
    refresh_token = create_refresh_token(
        data={"sub": user.id, "username": user.username},
    )
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=get_settings().auth_access_token_expire_minutes * 60,
    )


async def refresh_access_token(refresh_token: str) -> Token:
    """Refresh access token using refresh token."""
    payload = decode_token(refresh_token)
    if payload.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    
    user = _users_db.get(payload.username)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    new_access_token = create_access_token(
        data={"sub": user.id, "username": user.username, "roles": [r.value for r in user.roles]},
    )
    new_refresh_token = create_refresh_token(
        data={"sub": user.id, "username": user.username},
    )
    
    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=get_settings().auth_access_token_expire_minutes * 60,
    )


# Dependency for optional auth (allows public access if auth disabled)
async def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenData]:
    """Get current user if authenticated, otherwise None."""
    settings = get_settings()
    
    if not settings.auth_enabled:
        return None
    
    if not credentials:
        return None
    
    try:
        return decode_token(credentials.credentials)
    except HTTPException:
        return None