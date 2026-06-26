"""Scoped API key management for endpoints."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.db.models import ApiKey, Endpoint, Project
from adapta.db.session import get_db
from adapta.domain.errors import NotFound
from adapta.models.generated import KeyCreatedResponse, KeyCreateRequest, KeyResponse
from adapta.services.auth import (
    generate_api_key,
    get_current_user,
    require_team_member,
    require_team_writer,
)

router = APIRouter(prefix="/projects/{project_id}/keys", tags=["keys"])


async def _get_active_endpoint(db: AsyncSession, project_id: str) -> Endpoint:
    result = await db.execute(select(Endpoint).where(Endpoint.project_id == project_id))
    ep = result.scalar_one_or_none()
    if not ep:
        raise NotFound(message="No endpoint for this project. Create one first.")
    return ep


async def _get_project(db: AsyncSession, project_id: str) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFound(message=f"Project not found: {project_id}")
    return project


@router.post("", response_model=KeyCreatedResponse, status_code=201)
async def create_key(
    project_id: str,
    body: KeyCreateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    endpoint = await _get_active_endpoint(db, project_id)

    raw_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        endpoint_id=endpoint.id,
        name=body.name,
        key_prefix=prefix,
        key_hash=key_hash,
        is_active=True,
    )
    db.add(api_key)
    await db.commit()  # durable before response so the key works immediately

    return KeyCreatedResponse(id=api_key.id, name=api_key.name, key=raw_key, prefix=prefix)


@router.get("", response_model=List[KeyResponse])
async def list_keys(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    endpoint = await _get_active_endpoint(db, project_id)

    result = await db.execute(select(ApiKey).where(ApiKey.endpoint_id == endpoint.id))
    keys = result.scalars().all()
    return [
        KeyResponse(
            id=k.id,
            name=k.name,
            prefix=k.key_prefix,
            is_active=k.is_active,
            created_at=k.created_at.isoformat(),
        )
        for k in keys
    ]


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    project_id: str,
    key_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_writer(db, current_user.id, project.team_id)
    endpoint = await _get_active_endpoint(db, project_id)

    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.endpoint_id == endpoint.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise NotFound(message="Key not found")
    key.is_active = False
    await db.commit()  # revocation must take effect immediately
