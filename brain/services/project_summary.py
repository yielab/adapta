"""Project summary read-model (§C2.1).

Computes the ProjectSummary aggregate for one or many projects via a fixed set
of GROUP-BY queries — O(1) extra queries per list call, independent of project
count (no N+1 problem).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.db.models import (
    ApiKey,
    Dataset,
    DatasetStatus,
    Endpoint,
    FileStatus,
    JobStatus,
    Project,
    ProjectFile,
    TrainingJob,
    UsageEvent,
)


@dataclass
class FileSummary:
    total: int = 0
    indexed: int = 0
    chunks: int = 0


@dataclass
class DatasetSummary:
    total: int = 0
    valid: int = 0


@dataclass
class JobSummary:
    total: int = 0
    running: int = 0
    last_status: Optional[str] = None
    last_eval_score: Optional[float] = None
    gate_passed: Optional[bool] = None


@dataclass
class EndpointSummary:
    exists: bool = False
    slug: Optional[str] = None
    status: Optional[str] = None


@dataclass
class UsageSummary:
    requests: int = 0
    total_tokens: int = 0


@dataclass
class ProjectSummary:
    stage: str
    files: FileSummary = field(default_factory=FileSummary)
    datasets: DatasetSummary = field(default_factory=DatasetSummary)
    jobs: JobSummary = field(default_factory=JobSummary)
    endpoint: EndpointSummary = field(default_factory=EndpointSummary)
    keys_active: int = 0
    usage_7d: UsageSummary = field(default_factory=UsageSummary)
    last_activity_at: Optional[datetime] = None


def _derive_stage(
    project_type: str,
    files: FileSummary,
    datasets: DatasetSummary,
    jobs: JobSummary,
    endpoint: EndpointSummary,
) -> str:
    """Server-side stage derivation so the logic isn't duplicated in every client."""
    if endpoint.exists and endpoint.status == "active":
        return "live"
    if endpoint.exists:
        return "ready_to_serve"
    if project_type == "finetune":
        if jobs.running > 0:
            return "training"
        if jobs.last_status == "failed" and jobs.gate_passed is False:
            return "gate_blocked"
        if jobs.total == 0 and datasets.valid == 0:
            return "awaiting_data"
        return "awaiting_data"
    # RAG
    if files.indexed > 0:
        return "ready_to_serve"
    if files.total > 0 and files.indexed == 0:
        return "indexing"
    return "awaiting_data"


async def compute_summaries(db: AsyncSession, project_ids: List[str]) -> Dict[str, ProjectSummary]:
    """Compute ProjectSummary for a list of project IDs in O(1) extra queries."""
    if not project_ids:
        return {}

    pid_set = project_ids

    # ── files ──────────────────────────────────────────────────────────────
    file_rows = await db.execute(
        select(
            ProjectFile.project_id,
            func.count(ProjectFile.id).label("total"),
            func.sum(case((ProjectFile.status == FileStatus.indexed.value, 1), else_=0)).label(
                "indexed"
            ),
            func.coalesce(func.sum(ProjectFile.num_chunks), 0).label("chunks"),
        )
        .where(ProjectFile.project_id.in_(pid_set))
        .group_by(ProjectFile.project_id)
    )
    file_map: Dict[str, FileSummary] = {}
    for row in file_rows:
        file_map[row.project_id] = FileSummary(
            total=row.total or 0,
            indexed=row.indexed or 0,
            chunks=row.chunks or 0,
        )

    # ── datasets ────────────────────────────────────────────────────────────
    ds_rows = await db.execute(
        select(
            Dataset.project_id,
            func.count(Dataset.id).label("total"),
            func.sum(case((Dataset.status == DatasetStatus.valid.value, 1), else_=0)).label(
                "valid"
            ),
        )
        .where(Dataset.project_id.in_(pid_set))
        .group_by(Dataset.project_id)
    )
    ds_map: Dict[str, DatasetSummary] = {}
    for row in ds_rows:
        ds_map[row.project_id] = DatasetSummary(
            total=row.total or 0,
            valid=row.valid or 0,
        )

    # ── jobs — totals + most-recent completed ──────────────────────────────
    job_totals = await db.execute(
        select(
            TrainingJob.project_id,
            func.count(TrainingJob.id).label("total"),
            func.sum(case((TrainingJob.status == JobStatus.running.value, 1), else_=0)).label(
                "running"
            ),
        )
        .where(TrainingJob.project_id.in_(pid_set))
        .group_by(TrainingJob.project_id)
    )
    job_map: Dict[str, JobSummary] = {
        row.project_id: JobSummary(total=row.total or 0, running=row.running or 0)
        for row in job_totals
    }
    # Latest terminal job per project for gate info.
    latest_jobs = await db.execute(
        select(TrainingJob)
        .where(
            and_(
                TrainingJob.project_id.in_(pid_set),
                TrainingJob.status.in_([JobStatus.succeeded.value, JobStatus.failed.value]),
            )
        )
        .order_by(TrainingJob.created_at.desc())
    )
    seen_latest: set[str] = set()
    for job in latest_jobs.scalars():
        if job.project_id not in seen_latest:
            seen_latest.add(job.project_id)
            js = job_map.setdefault(job.project_id, JobSummary())
            js.last_status = job.status.value if hasattr(job.status, "value") else str(job.status)
            js.last_eval_score = job.eval_score
            js.gate_passed = job.eval_passed

    # ── endpoints ───────────────────────────────────────────────────────────
    ep_rows = await db.execute(select(Endpoint).where(Endpoint.project_id.in_(pid_set)))
    ep_map: Dict[str, EndpointSummary] = {}
    for ep in ep_rows.scalars():
        status_val = ep.status.value if hasattr(ep.status, "value") else str(ep.status)
        ep_map[ep.project_id] = EndpointSummary(exists=True, slug=ep.slug, status=status_val)

    # ── active keys (via endpoints) ─────────────────────────────────────────
    key_rows = await db.execute(
        select(Endpoint.project_id, func.count(ApiKey.id).label("cnt"))
        .join(ApiKey, ApiKey.endpoint_id == Endpoint.id)
        .where(
            and_(
                Endpoint.project_id.in_(pid_set),
                ApiKey.is_active.is_(True),
            )
        )
        .group_by(Endpoint.project_id)
    )
    keys_map: Dict[str, int] = {row.project_id: row.cnt for row in key_rows}

    # ── usage last 7 days ───────────────────────────────────────────────────
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
    usage_rows = await db.execute(
        select(
            Endpoint.project_id,
            func.coalesce(func.sum(UsageEvent.request_count), 0).label("requests"),
            func.coalesce(
                func.sum(UsageEvent.prompt_tokens + UsageEvent.completion_tokens), 0
            ).label("total_tokens"),
        )
        .join(UsageEvent, UsageEvent.endpoint_id == Endpoint.id)
        .where(
            and_(
                Endpoint.project_id.in_(pid_set),
                UsageEvent.day >= cutoff,
            )
        )
        .group_by(Endpoint.project_id)
    )
    usage_map: Dict[str, UsageSummary] = {
        row.project_id: UsageSummary(requests=row.requests, total_tokens=row.total_tokens)
        for row in usage_rows
    }

    # ── project type lookup ─────────────────────────────────────────────────
    proj_rows = await db.execute(
        select(Project.id, Project.type, Project.updated_at).where(Project.id.in_(pid_set))
    )
    proj_type_map: Dict[str, tuple] = {
        row.id: (row.type.value if hasattr(row.type, "value") else str(row.type), row.updated_at)
        for row in proj_rows
    }

    # ── assemble ────────────────────────────────────────────────────────────
    result: Dict[str, ProjectSummary] = {}
    for pid in pid_set:
        ptype, updated_at = proj_type_map.get(pid, ("rag", None))
        files = file_map.get(pid, FileSummary())
        datasets = ds_map.get(pid, DatasetSummary())
        jobs = job_map.get(pid, JobSummary())
        endpoint = ep_map.get(pid, EndpointSummary())
        keys_active = keys_map.get(pid, 0)
        usage_7d = usage_map.get(pid, UsageSummary())
        stage = _derive_stage(ptype, files, datasets, jobs, endpoint)
        result[pid] = ProjectSummary(
            stage=stage,
            files=files,
            datasets=datasets,
            jobs=jobs,
            endpoint=endpoint,
            keys_active=keys_active,
            usage_7d=usage_7d,
            last_activity_at=updated_at,
        )
    return result


async def compute_summary(db: AsyncSession, project_id: str) -> ProjectSummary:
    summaries = await compute_summaries(db, [project_id])
    return summaries[project_id]
