"""Authentication routes — Google SSO sign-in."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    create_access_token,
    get_current_user,
    get_or_create_user,
    verify_google_token,
)
from ..database import get_db
from ..models import User
from ..schemas import AuthResponse, GoogleAuthRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=AuthResponse)
async def google_sign_in(
    request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Sign in or create account with a Google ID token.

    The client obtains the ID token from Google Sign-In SDK, then sends it here.
    We verify it, create/update the user, and return a JWT.
    """
    google_info = await verify_google_token(request.id_token)
    user = await get_or_create_user(db, google_info)
    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get the current authenticated user's profile."""
    return UserResponse.model_validate(user)
