"""Auth endpoints: login, register (first user = org bootstrap)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import Org, Role, Team, TeamMember
from brain.db.session import get_db
from brain.domain.errors import InvalidRequest
from brain.services.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    org_name: str
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    org_id: str


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, body.email, body.password)
    token = create_access_token(user.id, user.org_id)
    return TokenResponse(access_token=token)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Bootstrap: creates the org, a default team, and the first admin user.
    Subsequent users are added by an admin via team management.
    """
    from sqlalchemy import func, select
    existing_orgs = await db.execute(select(func.count()).select_from(Org))
    count = existing_orgs.scalar()
    if count and count > 0:
        raise InvalidRequest(
            message="Organization already exists. Contact your admin to add new users."
        )

    org = Org(name=body.org_name)
    db.add(org)
    await db.flush()

    team = Team(org_id=org.id, name="default")
    db.add(team)
    await db.flush()

    user = await create_user(db, org.id, body.email, body.password)

    membership = TeamMember(team_id=team.id, user_id=user.id, role=Role.admin)
    db.add(membership)
    await db.flush()

    return UserResponse(id=user.id, email=user.email, org_id=user.org_id)


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return UserResponse(id=current_user.id, email=current_user.email, org_id=current_user.org_id)
