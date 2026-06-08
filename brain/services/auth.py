"""
Real JWT authentication + RBAC service.
Replaces the dummy "dummy" key from brain/api/auth.py.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.config import settings
from brain.db.models import Role, TeamMember, User
from brain.domain.errors import InvalidRequest, NotFound, Unauthorized

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)  # type: ignore[no-any-return]


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(user_id: str, org_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "org": org_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)  # type: ignore[no-any-return]


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])  # type: ignore[no-any-return]
    except JWTError as exc:
        raise Unauthorized(message="Invalid or expired token", internal_detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFound(message="User not found")
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        raise Unauthorized(message="Incorrect email or password")
    if not user.is_active:
        raise Unauthorized(message="User account is disabled")
    return user


async def create_user(db: AsyncSession, org_id: str, email: str, password: str) -> User:
    if await get_user_by_email(db, email):
        raise InvalidRequest(message=f"Email already registered: {email}")
    user = User(org_id=org_id, email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------

async def get_user_role_in_team(db: AsyncSession, user_id: str, team_id: str) -> Optional[Role]:
    result = await db.execute(
        select(TeamMember.role).where(
            TeamMember.user_id == user_id,
            TeamMember.team_id == team_id,
        )
    )
    row = result.scalar_one_or_none()
    return row


async def require_team_member(db: AsyncSession, user_id: str, team_id: str) -> Role:
    role = await get_user_role_in_team(db, user_id, team_id)
    if role is None:
        raise Unauthorized(message="Not a member of this team")
    return role


async def require_team_admin(db: AsyncSession, user_id: str, team_id: str) -> None:
    role = await require_team_member(db, user_id, team_id)
    if role != Role.admin:
        from brain.domain.errors import Forbidden
        raise Forbidden(message="Admin role required")


# ---------------------------------------------------------------------------
# API key helpers (scoped to endpoints)
# ---------------------------------------------------------------------------

def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix, hash)."""
    raw = "brn_" + secrets.token_urlsafe(32)
    return raw, raw[:8], _hash_key(raw)


def verify_api_key(raw: str, stored_hash: str) -> bool:
    return secrets.compare_digest(_hash_key(raw), stored_hash)


# ---------------------------------------------------------------------------
# FastAPI dependency: current user from Bearer JWT
# ---------------------------------------------------------------------------

from fastapi import Depends  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402

from brain.db.session import get_db  # noqa: E402

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise Unauthorized(message="Authentication required")
    payload = decode_access_token(credentials.credentials)
    user = await get_user_by_id(db, payload["sub"])
    if not user.is_active:
        raise Unauthorized(message="User account is disabled")
    return user
