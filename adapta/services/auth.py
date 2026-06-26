"""JWT authentication, password hashing, RBAC, and API-key helpers."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.config import settings
from adapta.db.models import Role, TeamMember, User
from adapta.domain.errors import Conflict, NotFound, Unauthorized

# ---------------------------------------------------------------------------
# Password helpers — bcrypt directly (passlib is unmaintained and breaks on
# bcrypt >= 4.1).  We SHA-256 + base64 pre-hash so any-length password
# collapses to a fixed 44-byte input, sidestepping bcrypt's hard 72-byte
# limit without silent truncation.  Same construction as Django's
# BCryptSHA256 hasher.
# ---------------------------------------------------------------------------


def _prehash(plain: str) -> bytes:
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    """Hash a plaintext password for storage.

    Returns a bcrypt string (not a hex digest).  Verify with
    ``verify_password`` — a plain bcrypt check would bypass the SHA-256
    pre-hash and reject valid passwords.
    """
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    Returns False (fail-closed) on malformed hash strings rather than
    raising — an invalid hash in the DB must not crash the auth path.
    """
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(user_id: str, org_id: str) -> str:
    """Issue a signed JWT for the given user.

    Payload shape: ``{sub: user_id, org: org_id, exp: <UTC datetime>}``.
    ``decode_access_token`` pattern-matches on ``"sub"`` and ``"org"``.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "org": org_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)  # type: ignore[no-any-return]


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT.  Raises ``Unauthorized`` on any failure.

    Never returns None — callers must handle the exception, not a falsy result.
    """
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])  # type: ignore[no-any-return]
    except JWTError as exc:
        raise Unauthorized(message="Invalid or expired token", internal_detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Look up a user by email address.  Returns None if not found.

    Callers that need a guaranteed result (or want a typed 404) should use
    ``get_user_by_id``, which raises ``NotFound``.
    """
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User:
    """Look up a user by primary key.  Raises ``NotFound`` if absent.

    Asymmetric with ``get_user_by_email`` which returns None — use this when
    you already know the ID and expect the user to exist.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFound(message="User not found")
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """Validate credentials.  Raises ``Unauthorized`` on any mismatch."""
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        raise Unauthorized(message="Incorrect email or password")
    if not user.is_active:
        raise Unauthorized(message="User account is disabled")
    return user


async def create_user(db: AsyncSession, org_id: str, email: str, password: str) -> User:
    """Insert a new user and flush (not commit) to the session.

    The caller is responsible for committing.  ``db.flush()`` makes the row
    visible within the same session for subsequent lookups before the commit.
    """
    if await get_user_by_email(db, email):
        raise Conflict(message=f"Email already registered: {email}")
    user = User(org_id=org_id, email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------


async def get_user_role_in_team(db: AsyncSession, user_id: str, team_id: str) -> Optional[Role]:
    """Return the caller's role in a team, or None if not a member."""
    result = await db.execute(
        select(TeamMember.role).where(
            TeamMember.user_id == user_id,
            TeamMember.team_id == team_id,
        )
    )
    row = result.scalar_one_or_none()
    return row


async def require_team_member(db: AsyncSession, user_id: str, team_id: str) -> Role:
    """Assert the caller belongs to the team.  Raises Forbidden (403) if not.

    403 rather than 401: the caller is authenticated (valid token), they just
    lack rights on this team.  401 would wrongly prompt clients to re-authenticate.
    """
    role = await get_user_role_in_team(db, user_id, team_id)
    if role is None:
        from adapta.domain.errors import Forbidden

        raise Forbidden(message="Not a member of this team")
    return role


async def require_team_writer(db: AsyncSession, user_id: str, team_id: str) -> Role:
    """Allow mutation: admin or member, but NOT viewer (read-only)."""
    role = await require_team_member(db, user_id, team_id)
    if role == Role.viewer:
        from adapta.domain.errors import Forbidden

        raise Forbidden(message="Read-only (viewer) role cannot perform this action")
    return role


async def require_team_admin(db: AsyncSession, user_id: str, team_id: str) -> None:
    """Assert the caller is a team admin.  Raises Forbidden otherwise."""
    role = await require_team_member(db, user_id, team_id)
    if role != Role.admin:
        from adapta.domain.errors import Forbidden

        raise Forbidden(message="Admin role required")


# ---------------------------------------------------------------------------
# API key helpers (scoped to endpoints)
# ---------------------------------------------------------------------------


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new scoped API key.  Returns ``(full_key, prefix, hash)``.

    ``full_key`` (``adp_<32-char token>``) is returned once and never stored
    in plaintext — show it to the user immediately or it is lost.  ``prefix``
    (first 8 chars) is stored for fast index lookup.  ``hash`` is the SHA-256
    digest stored for constant-time verification.
    """
    raw = "adp_" + secrets.token_urlsafe(32)
    return raw, raw[:8], _hash_key(raw)


def verify_api_key(raw: str, stored_hash: str) -> bool:
    """Compare a raw API key to its stored hash in constant time.

    Uses ``secrets.compare_digest`` to prevent timing attacks that could
    otherwise reveal prefix information from variable-length comparisons.
    """
    return secrets.compare_digest(_hash_key(raw), stored_hash)


# ---------------------------------------------------------------------------
# FastAPI dependency: current user from Bearer JWT
# ---------------------------------------------------------------------------

from fastapi import Depends  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402

from adapta.db.session import get_db  # noqa: E402

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: resolve and validate the Bearer JWT.

    Reads the ``Authorization: Bearer <token>`` header, decodes the JWT,
    loads the user from the DB, and asserts the account is active.
    Raises ``Unauthorized`` on any failure — never returns None.
    """
    if not credentials:
        raise Unauthorized(message="Authentication required")
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise Unauthorized(message="Invalid or expired token")
    user = await get_user_by_id(db, user_id)
    if not user.is_active:
        raise Unauthorized(message="User account is disabled")
    return user
