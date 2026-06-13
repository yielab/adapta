"""Team management — members listing."""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import TeamMember, User
from brain.db.session import get_db
from brain.services.auth import get_current_user, require_team_member

router = APIRouter(prefix="/teams", tags=["auth"])


class MemberResponse(BaseModel):
    user_id: str
    email: str
    role: str
    joined_at: str


@router.get("/{team_id}/members", response_model=List[MemberResponse])
async def list_team_members(
    team_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all members of a team. Any team member may call this."""
    await require_team_member(db, current_user.id, team_id)
    result = await db.execute(
        select(TeamMember, User)
        .join(User, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team_id)
    )
    return [
        MemberResponse(
            user_id=tm.user_id,
            email=u.email,
            role=tm.role.value,
            joined_at=tm.joined_at.isoformat(),
        )
        for tm, u in result.all()
    ]
