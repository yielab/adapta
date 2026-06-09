"""Project CRUD endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import Project, ProjectStatus, ProjectType
from brain.db.session import get_db
from brain.domain.errors import NotFound
from brain.services.auth import (
    get_current_user,
    require_team_admin,
    require_team_member,
    require_team_writer,
)

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    type: ProjectType
    base_model: str
    description: Optional[str] = None
    team_id: str


class ProjectResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    base_model: str
    description: Optional[str]
    team_id: str
    created_at: str

    model_config = {"from_attributes": True}


def _proj_resp(p: Project) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        name=p.name,
        type=p.type.value,
        status=p.status.value,
        base_model=p.base_model,
        description=p.description,
        team_id=p.team_id,
        created_at=p.created_at.isoformat(),
    )


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_team_writer(db, current_user.id, body.team_id)
    project = Project(
        team_id=body.team_id,
        name=body.name,
        type=body.type,
        base_model=body.base_model,
        description=body.description,
        status=ProjectStatus.created,
    )
    db.add(project)
    await db.commit()
    return _proj_resp(project)


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    team_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_team_member(db, current_user.id, team_id)
    result = await db.execute(select(Project).where(Project.team_id == team_id))
    projects = result.scalars().all()
    return [_proj_resp(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    return _proj_resp(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_admin(db, current_user.id, project.team_id)

    # Clean up ChromaDB collection if RAG project
    if project.type == ProjectType.rag:
        try:
            from brain.services.rag import get_rag_service
            get_rag_service().delete_collection(project_id)
        except Exception:
            pass

    await db.delete(project)
    await db.commit()  # durable before response so an immediate re-list reflects it (§4.4)


async def _get_project(db: AsyncSession, project_id: str) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFound(message=f"Project not found: {project_id}")
    return project
