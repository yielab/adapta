"""
SQLAlchemy ORM models — the Postgres data model (Pillar 2 contract).
Changes here require a new Alembic migration: make migration MSG="..."
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Role(str, enum.Enum):
    admin = "admin"
    member = "member"
    viewer = "viewer"  # read-only: consume endpoints + read, no mutation


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"


class ProjectType(str, enum.Enum):
    rag = "rag"
    finetune = "finetune"


class ProjectStatus(str, enum.Enum):
    created = "created"
    indexing = "indexing"       # RAG: building collection
    ready = "ready"
    training = "training"       # finetune: job running
    failed = "failed"


class FileStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"


class DatasetStatus(str, enum.Enum):
    uploaded = "uploaded"
    validating = "validating"
    valid = "valid"
    invalid = "invalid"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class EndpointStatus(str, enum.Enum):
    pending = "pending"    # not yet servable
    active = "active"
    disabled = "disabled"


# ---------------------------------------------------------------------------
# Org / Team / User
# ---------------------------------------------------------------------------

class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teams: Mapped[list[Team]] = relationship("Team", back_populates="org", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    org: Mapped[Org] = relationship("Org", back_populates="teams")
    members: Mapped[list[TeamMember]] = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    projects: Mapped[list[Project]] = relationship("Project", back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_team_org_name"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    org: Mapped[Org] = relationship("Org")
    memberships: Mapped[list[TeamMember]] = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=16), nullable=False, default=Role.member)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    team: Mapped[Team] = relationship("Team", back_populates="members")
    user: Mapped[User] = relationship("User", back_populates="memberships")

    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[ProjectType] = mapped_column(Enum(ProjectType, native_enum=False, length=16), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus, native_enum=False, length=16), nullable=False, default=ProjectStatus.created)
    base_model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    team: Mapped[Team] = relationship("Team", back_populates="projects")
    files: Mapped[list[ProjectFile]] = relationship("ProjectFile", back_populates="project", cascade="all, delete-orphan")
    collection: Mapped[Optional[Collection]] = relationship("Collection", back_populates="project", uselist=False, cascade="all, delete-orphan")
    datasets: Mapped[list[Dataset]] = relationship("Dataset", back_populates="project", cascade="all, delete-orphan")
    jobs: Mapped[list[TrainingJob]] = relationship("TrainingJob", back_populates="project", cascade="all, delete-orphan")
    endpoint: Mapped[Optional[Endpoint]] = relationship("Endpoint", back_populates="project", uselist=False, cascade="all, delete-orphan")


class ProjectFile(Base):
    __tablename__ = "project_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[FileStatus] = mapped_column(Enum(FileStatus, native_enum=False, length=16), nullable=False, default=FileStatus.pending)
    num_chunks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship("Project", back_populates="files")


# ---------------------------------------------------------------------------
# RAG: Collection
# ---------------------------------------------------------------------------

class Collection(Base):
    """Per-project ChromaDB collection reference."""
    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    chroma_collection_name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    num_documents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped[Project] = relationship("Project", back_populates="collection")


# ---------------------------------------------------------------------------
# Fine-tuning: Dataset / TrainingJob
# ---------------------------------------------------------------------------

class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    num_samples: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[DatasetStatus] = mapped_column(Enum(DatasetStatus, native_enum=False, length=16), nullable=False, default=DatasetStatus.uploaded)
    validation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship("Project", back_populates="datasets")
    jobs: Mapped[list[TrainingJob]] = relationship("TrainingJob", back_populates="dataset")


class TrainingJob(Base):
    __tablename__ = "training_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False, length=16), nullable=False, default=JobStatus.queued)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    logs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    adapter_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    eval_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eval_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    # Full EvaluationResult.to_dict() as JSON (A4.6): score, base_score, score_delta,
    # held_out, sample_predictions, metrics — so a gate verdict is auditable, not just
    # a bare scalar. NULL until the job reaches evaluation.
    eval_metrics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    training_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Crash-recovery retry counter (A4.2): incremented when startup reconciliation
    # re-picks a job left `running` by a dead worker; bounds automatic retries.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship("Project", back_populates="jobs")
    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="jobs")


# ---------------------------------------------------------------------------
# Endpoint / ApiKey
# ---------------------------------------------------------------------------

class Endpoint(Base):
    """The servable model for a project. Created when the project is ready."""
    __tablename__ = "endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[EndpointStatus] = mapped_column(Enum(EndpointStatus, native_enum=False, length=16), nullable=False, default=EndpointStatus.pending)
    adapter_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # null = base only (RAG)
    base_model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped[Project] = relationship("Project", back_populates="endpoint")
    keys: Mapped[list[ApiKey]] = relationship("ApiKey", back_populates="endpoint", cascade="all, delete-orphan")


class ApiKey(Base):
    """Scoped key for a specific endpoint."""
    __tablename__ = "api_keys"
    # Every /v1/chat/completions call looks a key up by (key_prefix, is_active) —
    # the hottest query in the product. Index it so auth stays O(index) not O(table)
    # as key count grows (A4.4).
    __table_args__ = (
        Index("ix_apikey_prefix_active", "key_prefix", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    endpoint_id: Mapped[str] = mapped_column(String(36), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)   # first 8 chars shown to user
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)    # SHA-256 of full key
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    endpoint: Mapped[Endpoint] = relationship("Endpoint", back_populates="keys")


class Invitation(Base):
    """A pending invite for a new user to join a team with a given role (§3.1).

    The admin issues one (`POST /v1/auth/invite`); the invitee redeems the token
    and sets a password (`POST /v1/auth/accept-invite`), which creates the user
    and the team membership without re-bootstrapping the org.
    """
    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=16), nullable=False, default=Role.member)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, native_enum=False, length=16), nullable=False, default=InvitationStatus.pending
    )
    invited_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageEvent(Base):
    """Daily token-usage rollup per endpoint (one row per endpoint per day).

    Written off the response path after each served completion via an upsert that
    increments the counters, so `GET .../usage` aggregates cheaply by day.
    """
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    endpoint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[datetime] = mapped_column(Date, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("endpoint_id", "day", name="uq_usage_endpoint_day"),)
