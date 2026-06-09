"""Auth endpoints: login, register (first user = org bootstrap), team invites."""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import Invitation, Org, Role, Team, TeamMember
from brain.db.session import get_db
from brain.domain.errors import Conflict, InvalidRequest
from brain.services.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
    require_team_admin,
)
from brain.services.invitations import accept_invitation, create_invitation

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


class TeamSummary(BaseModel):
    id: str
    name: str
    role: str


class UserResponse(BaseModel):
    id: str
    email: str
    org_id: str
    teams: List[TeamSummary] = []


async def _load_teams(db: AsyncSession, user_id: str) -> List[TeamSummary]:
    """The teams a user belongs to + their role — so a client can discover the
    team_id every /v1/projects call requires."""
    result = await db.execute(
        select(Team.id, Team.name, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
    )
    return [TeamSummary(id=tid, name=name, role=role.value) for tid, name, role in result.all()]


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
        raise Conflict(
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
    # Commit before returning so an immediate follow-up login sees the new user
    # (the get_db finalizer commits only after the response is sent — §4.4).
    await db.commit()

    return UserResponse(
        id=user.id,
        email=user.email,
        org_id=user.org_id,
        teams=[TeamSummary(id=team.id, name=team.name, role=Role.admin.value)],
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        org_id=current_user.org_id,
        teams=await _load_teams(db, current_user.id),
    )


# ---------------------------------------------------------------------------
# Team invitations (§3.1)
# ---------------------------------------------------------------------------

class InviteRequest(BaseModel):
    email: EmailStr
    team_id: str
    role: Role = Role.member


class InvitationResponse(BaseModel):
    id: str
    email: str
    team_id: str
    role: str
    status: str
    token: Optional[str] = None  # returned only at creation time
    expires_at: str


class AcceptInviteRequest(BaseModel):
    token: str
    password: str


def _invite_resp(inv: Invitation, *, include_token: bool = False) -> InvitationResponse:
    return InvitationResponse(
        id=inv.id,
        email=inv.email,
        team_id=inv.team_id,
        role=inv.role.value,
        status=inv.status.value,
        token=inv.token if include_token else None,
        expires_at=inv.expires_at.isoformat(),
    )


@router.post("/invite", response_model=InvitationResponse, status_code=201)
async def invite(
    body: InviteRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin issues an invite for a user to join one of their teams."""
    await require_team_admin(db, current_user.id, body.team_id)
    if body.role == Role.admin:
        # Inviting another admin is allowed; nothing extra to check here.
        pass
    inv = await create_invitation(
        db, team_id=body.team_id, email=body.email, role=body.role, invited_by=current_user.id
    )
    # Token is shown once, at creation (the operator delivers it out-of-band).
    return _invite_resp(inv, include_token=True)


@router.post("/accept-invite", response_model=UserResponse, status_code=201)
async def accept_invite(body: AcceptInviteRequest, db: AsyncSession = Depends(get_db)):
    """Redeem an invite token + set a password → user joins the team."""
    if not body.password or len(body.password) < 8:
        raise InvalidRequest(message="Password must be at least 8 characters")
    user, _inv = await accept_invitation(db, token=body.token, password=body.password)
    return UserResponse(
        id=user.id,
        email=user.email,
        org_id=user.org_id,
        teams=await _load_teams(db, user.id),
    )


@router.get("/invitations", response_model=List[InvitationResponse])
async def list_invitations(
    team_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List invitations for a team (admin only). Tokens are not returned."""
    await require_team_admin(db, current_user.id, team_id)
    result = await db.execute(select(Invitation).where(Invitation.team_id == team_id))
    return [_invite_resp(i) for i in result.scalars().all()]
