"""
Authentication API routes for NeuroRoute.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import (
    UserRole,
    UserCreate,
    UserResponse,
    Token,
    TokenData,
    login,
    refresh_access_token,
    get_current_user,
    require_admin,
    init_default_users,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Login request model."""
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class RefreshTokenRequest(BaseModel):
    """Refresh token request model."""
    refresh_token: str = Field(..., description="Refresh token")


@router.post("/login", response_model=Token)
async def login_endpoint(request: LoginRequest):
    """Authenticate user and return access/refresh tokens."""
    return await login(request.username, request.password)


@router.post("/refresh", response_model=Token)
async def refresh_token_endpoint(request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    return await refresh_access_token(request.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(get_current_user)):
    """Get current authenticated user info."""
    from app.auth import _users_db
    if current_user is None:
        # Auth disabled - return dev user
        return UserResponse(
            id="dev",
            username="developer",
            roles=[UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER],
            created_at=None,
        )
    
    user = _users_db.get(current_user.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=user.id,
        username=user.username,
        roles=user.roles,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(request: UserCreate, _: TokenData = Depends(require_admin)):
    """Create a new user (admin only)."""
    from app.auth import _users_db, get_password_hash
    
    if request.username in _users_db:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user = UserResponse(
        id=request.username,
        username=request.username,
        roles=request.roles,
        is_active=True,
        created_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc),
    )
    
    # Store with hashed password
    from app.auth import UserInDB
    user_in_db = UserInDB(
        id=user.id,
        username=user.username,
        hashed_password=get_password_hash(request.password),
        roles=user.roles,
        is_active=user.is_active,
        created_at=user.created_at,
    )
    _users_db[user.username] = user_in_db
    
    return user


@router.get("/users", response_model=list[UserResponse])
async def list_users(_: TokenData = Depends(require_admin)):
    """List all users (admin only)."""
    from app.auth import _users_db
    
    return [
        UserResponse(
            id=user.id,
            username=user.username,
            roles=user.roles,
            is_active=user.is_active,
            created_at=user.created_at,
        )
        for user in _users_db.values()
    ]


@router.delete("/users/{username}")
async def delete_user(username: str, _: TokenData = Depends(require_admin)):
    """Delete a user (admin only)."""
    from app.auth import _users_db
    
    if username not in _users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    if username == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete admin user")
    
    del _users_db[username]
    return {"message": f"User {username} deleted"}


# Initialize default users on module import (for testing)
init_default_users()