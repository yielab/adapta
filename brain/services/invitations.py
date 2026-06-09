"""Team invitation flow (§3.1).

An admin issues an invitation (token + target team/role); the invitee redeems
the token and sets a password, which creates their user and team membership
without re-bootstrapping the org.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import Invitation, InvitationStatus, Role, Team, TeamMember
from brain.domain.errors import Conflict, InvalidRequest, NotFound
from brain.services.auth import create_user, get_user_by_email

INVITE_TTL_DAYS = 7


async def create_invitation(
    db: AsyncSession, *, team_id: str, email: str, role: Role, invited_by: str
) -> Invitation:
    """Create a pending invite for `email` to join `team_id` with `role`."""
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if not team:
        raise NotFound(message=f"Team not found: {team_id}")

    existing = await get_user_by_email(db, email)
    if existing is not None:
        # If they're already on this team, nothing to do.
        member = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.user_id == existing.id
            )
        )
        if member.scalar_one_or_none() is not None:
            raise Conflict(message=f"{email} is already a member of this team")

    invite = Invitation(
        org_id=team.org_id,
        team_id=team_id,
        email=email,
        role=role,
        token=secrets.token_urlsafe(32),
        status=InvitationStatus.pending,
        invited_by=invited_by,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invite)
    await db.commit()
    return invite


async def accept_invitation(db: AsyncSession, *, token: str, password: str):
    """Redeem an invite: create the user (if needed) + team membership."""
    invite = (
        await db.execute(select(Invitation).where(Invitation.token == token))
    ).scalar_one_or_none()
    if not invite:
        raise NotFound(message="Invitation not found")
    if invite.status != InvitationStatus.pending:
        raise InvalidRequest(message="Invitation is no longer valid")
    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = InvitationStatus.revoked
        await db.commit()
        raise InvalidRequest(message="Invitation has expired")

    user = await get_user_by_email(db, invite.email)
    if user is None:
        user = await create_user(db, invite.org_id, invite.email, password)
        await db.flush()

    # Add membership if not already present.
    existing = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == invite.team_id, TeamMember.user_id == user.id
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(TeamMember(team_id=invite.team_id, user_id=user.id, role=invite.role))

    invite.status = InvitationStatus.accepted
    invite.accepted_at = datetime.now(timezone.utc)
    await db.commit()
    return user, invite
