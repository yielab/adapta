"""Project CRUD endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adapta.core.model_catalog import allowed_names, is_valid
from adapta.db.models import Project, ProjectStatus, ProjectType
from adapta.db.session import get_db
from adapta.domain.errors import InvalidRequest, NotFound
from adapta.models.generated import (
    ProjectCreate,
    ProjectResponse,
)
from adapta.models.generated import (
    ProjectSummary as ApiProjectSummary,
)
from adapta.models.generated import (
    ProjectType as ApiProjectType,
)
from adapta.services.auth import (
    get_current_user,
    require_team_admin,
    require_team_member,
    require_team_writer,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _proj_resp(p: Project, summary: Optional[Dict[str, Any]] = None) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        name=p.name,
        type=ApiProjectType(p.type.value),
        status=p.status.value,
        base_model=p.base_model,
        description=p.description,
        team_id=p.team_id,
        created_at=p.created_at.isoformat(),
        summary=ApiProjectSummary.model_validate(summary) if summary is not None else None,
    )


def _summary_to_dict(s: Any) -> Dict[str, Any]:
    """Serialize a ProjectSummary dataclass to a plain dict for the API response.

    ``last_activity_at`` is a datetime in the dataclass; the generated
    ProjectSummary model types it as an ISO string, so stringify it here.
    """
    from dataclasses import asdict

    d = asdict(s)
    la = d.get("last_activity_at")
    d["last_activity_at"] = la.isoformat() if la else None
    return d


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_team_writer(db, current_user.id, body.team_id)
    # Validate base_model against the single catalog (A3.3): the same entry must
    # both train (HF id) and serve (GGUF), so an operator can't pick a value that
    # only works in one runtime — it would otherwise surface as a runtime failure.
    if not is_valid(body.base_model):
        allowed = ", ".join(allowed_names())
        raise InvalidRequest(
            message=f"Unknown base_model '{body.base_model}'. Allowed values: {allowed}.",
            internal_detail=f"base_model not in catalog: {body.base_model!r}",
        )
    project = Project(
        team_id=body.team_id,
        name=body.name,
        # body.type is the generated ProjectType enum; the ORM column wants the
        # DB enum — convert by value (distinct classes, same string values).
        type=ProjectType(body.type.value),
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
    if not projects:
        return []
    from adapta.services.project_summary import compute_summaries

    summaries = await compute_summaries(db, [p.id for p in projects])
    return [
        _proj_resp(p, _summary_to_dict(summaries[p.id]) if p.id in summaries else None)
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    await require_team_member(db, current_user.id, project.team_id)
    from adapta.services.project_summary import compute_summary

    summary = await compute_summary(db, project_id)
    return _proj_resp(project, _summary_to_dict(summary))


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
            from adapta.services.rag import get_rag_service

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
