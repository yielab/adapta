"""Platform settings — DB-backed whitelisted org-scoped overrides."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.db.session import get_db
from adapta.models.generated import SettingResponse, SettingWriteRequest, SettingWriteResult
from adapta.services.app_settings import delete_setting, resolve_all, upsert_setting
from adapta.services.auth import get_current_user, require_team_admin, require_team_member

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=List[SettingResponse])
async def get_settings(
    team_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all whitelisted settings with their effective value and provenance."""
    await require_team_member(db, current_user.id, team_id)
    return await resolve_all(db, team_id)


@router.put("", response_model=SettingWriteResult)
async def put_setting(
    body: SettingWriteRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Override a whitelisted setting (admin only). Out-of-bounds → 422."""
    await require_team_admin(db, current_user.id, body.team_id)
    return await upsert_setting(db, body.team_id, body.key, body.value, current_user.id)


@router.delete("/{key}", status_code=204)
async def delete_setting_route(
    key: str,
    team_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset a setting to its default by removing the DB override row (admin only)."""
    await require_team_admin(db, current_user.id, team_id)
    await delete_setting(db, team_id, key)
