"""Auth endpoints: login, register (first user = org bootstrap), team invites.

Request/response models are generated from specs/openapi.yaml (the API contract)
and imported from adapta.models.generated — never hand-redefined here.
"""

from typing import List

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.db.models import Invitation, Org, Role, Team, TeamMember, User
from adapta.db.session import get_db
from adapta.domain.errors import Conflict, InvalidRequest
from adapta.models.generated import (
    AcceptInviteRequest,
    ChangePasswordRequest,
    InvitationResponse,
    InviteRequest,
    LoginRequest,
    RegisterRequest,
    TeamSummary,
    TokenResponse,
    UserResponse,
)
from adapta.models.generated import (
    InvitationStatus as ApiInvitationStatus,
)
from adapta.models.generated import (
    Role as ApiRole,
)
from adapta.services.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
    hash_password,
    require_team_admin,
    verify_password,
)
from adapta.services.invitations import accept_invitation, create_invitation
from adapta.services.rate_limit import enforce_auth

router = APIRouter(prefix="/auth", tags=["auth"])


async def _load_teams(db: AsyncSession, user_id: str) -> List[TeamSummary]:
    """The teams a user belongs to + their role — so a client can discover the
    team_id every /v1/projects call requires."""
    result = await db.execute(
        select(Team.id, Team.name, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
    )
    return [
        TeamSummary(id=tid, name=name, role=ApiRole(role.value)) for tid, name, role in result.all()
    ]


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_auth(request, body.email)
    user = await authenticate_user(db, body.email, body.password)
    token = create_access_token(user.id, user.org_id)
    return TokenResponse(access_token=token)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Creates an organization, its default team, and its admin user. Anyone can
    register a new org at any time; additional users join an EXISTING org via
    the invite flow. Conflicts: a duplicate email (create_user → 409) and a
    duplicate org name (`orgs.name` is unique → 409, never a raw 500).
    """
    await enforce_auth(request, body.email)
    if not body.password or len(body.password) < 8:
        raise InvalidRequest(message="Password must be at least 8 characters")
    if not body.org_name.strip():
        raise InvalidRequest(message="Organization name must not be empty")

    try:
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
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict(
            message="An organization with this name already exists",
            internal_detail=f"IntegrityError registering org {body.org_name!r}: {exc}",
        ) from exc

    return UserResponse(
        id=user.id,
        email=user.email,
        org_id=user.org_id,
        teams=[TeamSummary(id=team.id, name=team.name, role=ApiRole(Role.admin.value))],
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


def _invite_resp(inv: Invitation, *, include_token: bool = False) -> InvitationResponse:
    return InvitationResponse(
        id=inv.id,
        email=inv.email,
        team_id=inv.team_id,
        role=ApiRole(inv.role.value),
        status=ApiInvitationStatus(inv.status.value),
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
    # The contract leaves role optional; default a missing one to member. Convert
    # the generated enum to the DB enum by value (they are distinct classes).
    role = Role(body.role.value) if body.role is not None else Role.member
    inv = await create_invitation(
        db, team_id=body.team_id, email=body.email, role=role, invited_by=current_user.id
    )
    # Token is shown once, at creation (the operator delivers it out-of-band).
    return _invite_resp(inv, include_token=True)


@router.post("/accept-invite", response_model=UserResponse, status_code=201)
async def accept_invite(
    body: AcceptInviteRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Redeem an invite token + set a password → user joins the team."""
    await enforce_auth(request)
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


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password. Verifies the current password first."""
    user_row = await db.execute(select(User).where(User.id == current_user.id))
    user = user_row.scalar_one_or_none()
    if not user or not verify_password(body.current_password, user.hashed_password):
        raise InvalidRequest(
            message="Current password is incorrect.",
            internal_detail="change-password: incorrect current password",
        )
    # Password length is a domain rule (400 invalid_request, friendly message) —
    # the same enforcement register/accept-invite apply. It is NOT a schema
    # constraint, so it must be checked here, not left to a structural 422.
    if not body.new_password or len(body.new_password) < 8:
        raise InvalidRequest(message="Password must be at least 8 characters")
    user.hashed_password = hash_password(body.new_password)
    await db.commit()
