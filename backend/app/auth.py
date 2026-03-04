"""Google SSO authentication and JWT token management."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_db
from .models import User

security = HTTPBearer()


async def verify_google_token(token: str) -> dict:
    """Verify a Google ID token and return the user info payload.

    Returns dict with keys: sub, email, name, picture.
    """
    try:
        payload = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google token: {e}",
        )

    if payload.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer",
        )

    return {
        "google_id": payload["sub"],
        "email": payload.get("email", ""),
        "name": payload.get("name", ""),
        "picture_url": payload.get("picture"),
    }


def create_access_token(user_id: UUID) -> str:
    """Create a JWT access token for the given user."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from the JWT bearer token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_or_create_user(db: AsyncSession, google_info: dict) -> User:
    """Find existing user by Google ID or create a new account."""
    result = await db.execute(
        select(User).where(User.google_id == google_info["google_id"])
    )
    user = result.scalar_one_or_none()

    if user:
        user.last_login = datetime.now(timezone.utc)
        user.name = google_info["name"]
        user.picture_url = google_info.get("picture_url")
        await db.commit()
        return user

    user = User(
        google_id=google_info["google_id"],
        email=google_info["email"],
        name=google_info["name"],
        picture_url=google_info.get("picture_url"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
