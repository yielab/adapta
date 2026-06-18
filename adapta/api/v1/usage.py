"""Usage reporting — daily token rollups for a project's endpoint (§3.2)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.db.models import Project
from adapta.db.session import get_db
from adapta.domain.errors import NotFound
from adapta.services.auth import get_current_user, require_team_member
from adapta.services.usage import usage_by_day

router = APIRouter(prefix="/projects/{project_id}/usage", tags=["usage"])


class UsageDay(BaseModel):
    day: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    request_count: int


class UsageResponse(BaseModel):
    project_id: str
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_requests: int
    days: List[UsageDay]


@router.get("", response_model=UsageResponse)
async def get_usage(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFound(message=f"Project not found: {project_id}")
    await require_team_member(db, current_user.id, project.team_id)

    days = await usage_by_day(db, project_id)
    return UsageResponse(
        project_id=project_id,
        total_prompt_tokens=sum(d["prompt_tokens"] for d in days),
        total_completion_tokens=sum(d["completion_tokens"] for d in days),
        total_tokens=sum(d["total_tokens"] for d in days),
        total_requests=sum(d["request_count"] for d in days),
        days=[UsageDay(**d) for d in days],
    )
