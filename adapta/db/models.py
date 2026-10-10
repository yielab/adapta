"""
SQLAlchemy ORM models — the Postgres data model (Pillar 2 contract).

Changes here require a new Alembic migration: ``make migration MSG="..."``.

``native_enum=False`` invariant: every Enum column uses ``native_enum=False``
with ``length=16`` (matching the ``String(16)`` migration columns).  Never use
the default ``native_enum=True`` — it would create a Postgres ENUM type that
Alembic cannot drop/alter without a manual migration, and it would diverge from
the existing ``String(16)`` columns in ``migrations/versions/0001_initial_schema.py``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
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
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models.  All tables must inherit from this."""

    pass


def _uuid() -> str:
    """Generate a new UUID string (str, not UUID object — columns are String(36))."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Role(str, enum.Enum):
    admin = "admin"
    member = "member"
    # viewers can call /v1/chat/completions and read project data, but cannot
    # create/update/delete any resource.  Enforced by require_team_writer().
    viewer = "viewer"


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"


class ProjectType(str, enum.Enum):
    rag = "rag"
    finetune = "finetune"


class ProjectStatus(str, enum.Enum):
    created = "created"
    indexing = "indexing"  # RAG: building collection
    ready = "ready"
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


class AdapterFormat(str, enum.Enum):
    gguf = "gguf"
    peft = "peft"


class AdapterStatus(str, enum.Enum):
    """uploaded -> processing -> passed | failed. Upload (E4.2) writes `uploaded`; the
    adapter job (E4.4) drives the rest. Only `passed` adapters can back an endpoint."""

    uploaded = "uploaded"
    processing = "processing"
    passed = "passed"
    failed = "failed"


class AdapterAction(str, enum.Enum):
    """promote: the endpoint was bound to an adapter that had not served before (the first
    binding at creation included). rollback: re-bound to one that had."""

    promote = "promote"
    rollback = "rollback"


class EndpointStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    disabled = "disabled"


# ---------------------------------------------------------------------------
# Org / Team / User
# ---------------------------------------------------------------------------


class Org(Base):
    """Top-level tenant.  One Org is created atomically with the first admin on
    ``POST /v1/auth/register``; subsequent users join via invite, never by
    registering a new Org with the same name."""

    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teams: Mapped[list[Team]] = relationship(
        "Team", back_populates="org", cascade="all, delete-orphan"
    )


class Team(Base):
    """Workspace within an Org.  Registration seeds a ``"default"`` team; admins
    may create additional teams to isolate projects across business units."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    org: Mapped[Org] = relationship("Org", back_populates="teams")
    members: Mapped[list[TeamMember]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(
        "Project", back_populates="team", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_team_org_name"),)


class User(Base):
    """Application user.  Belongs to exactly one Org and never moves between Orgs.
    ``hashed_password`` stores a bcrypt hash of a SHA-256 pre-hash — see
    ``adapta/services/auth.py`` for the construction and why.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    org: Mapped[Org] = relationship("Org")
    memberships: Mapped[list[TeamMember]] = relationship(
        "TeamMember", back_populates="user", cascade="all, delete-orphan"
    )


class TeamMember(Base):
    """Join table between Team and User, carrying the role within that team.

    Role hierarchy: admin > member > viewer.  Rights are enforced in
    ``adapta/services/auth.py`` via ``require_team_member``,
    ``require_team_writer``, and ``require_team_admin``.
    """

    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=16), nullable=False, default=Role.member
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    team: Mapped[Team] = relationship("Team", back_populates="members")
    user: Mapped[User] = relationship("User", back_populates="memberships")

    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class Project(Base):
    """Core work unit.  Every project produces exactly one Endpoint.

    ``type`` determines the data pipeline: ``rag`` projects index uploaded
    documents into a ChromaDB collection; ``finetune`` projects train LoRA
    adapters from JSONL datasets.  A finetune project may also index documents
    — its endpoint then composes RAG retrieval with the adapter in one call.

    ``status`` state machine (transitions set by the service layer, never by
    the client):
      created → indexing (RAG file upload started)
      created / indexing → ready (RAG collection built, or finetune dataset valid)
      ready → training (job enqueued)
      training → ready (job succeeded) | failed (job failed)
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # (E3.5) Operator prompt, rendered first in the system message at serving time.
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[ProjectType] = mapped_column(
        Enum(ProjectType, native_enum=False, length=16), nullable=False
    )
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=16),
        nullable=False,
        default=ProjectStatus.created,
    )
    base_model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    team: Mapped[Team] = relationship("Team", back_populates="projects")
    files: Mapped[list[ProjectFile]] = relationship(
        "ProjectFile", back_populates="project", cascade="all, delete-orphan"
    )
    collection: Mapped[Optional[Collection]] = relationship(
        "Collection", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    datasets: Mapped[list[Dataset]] = relationship(
        "Dataset", back_populates="project", cascade="all, delete-orphan"
    )
    adapters: Mapped[list[Adapter]] = relationship(
        "Adapter", back_populates="project", cascade="all, delete-orphan"
    )
    endpoint: Mapped[Optional[Endpoint]] = relationship(
        "Endpoint", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )


class ProjectFile(Base):
    """An uploaded document (PDF, DOCX, TXT, MD, HTML) attached to a project.

    ``storage_path`` is an absolute path under ``settings.uploads_dir``; it is
    the authoritative location for backup and restore.  ``size_bytes`` is
    written before the file is persisted (set to 0 at row creation, updated
    after the upload completes) — a value of 0 indicates an upload in flight.
    """

    __tablename__ = "project_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[FileStatus] = mapped_column(
        Enum(FileStatus, native_enum=False, length=16), nullable=False, default=FileStatus.pending
    )
    num_chunks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # sha256 of the raw uploaded bytes — the synchronous duplicate check (E3.3b). NULL for
    # files uploaded before it existed.
    content_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_project_files_project_sha", "project_id", "content_sha256"),)

    project: Mapped[Project] = relationship("Project", back_populates="files")


# ---------------------------------------------------------------------------
# RAG: Chunk
# ---------------------------------------------------------------------------


class ProjectChunk(Base):
    """One indexed chunk of a file — the Postgres source of truth for page, text,
    hash and chunk counts (Chroma holds only the vectors).

    ``id`` is ``"{file_id}_{chunk_index}"``, identical to the Chroma id. Rows go with
    their file via ``ON DELETE CASCADE``. ``tsv`` is a GENERATED column (never written)
    that feeds the full-text leg (E3.2).
    """

    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_files.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ocr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    tsv: Mapped[Optional[str]] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("file_id", "chunk_index", name="uq_chunks_file_index"),
        Index("ix_chunks_project_id", "project_id"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )


# ---------------------------------------------------------------------------
# RAG: Collection
# ---------------------------------------------------------------------------


class Collection(Base):
    """Per-project ChromaDB collection reference."""

    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    chroma_collection_name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    # Vector size of `embedding_model`; NULL until first indexing/re-embed records it (E3.6).
    embedding_dim: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    num_documents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship("Project", back_populates="collection")


# ---------------------------------------------------------------------------
# Fine-tuning: Dataset
# ---------------------------------------------------------------------------


class Dataset(Base):
    """An SFT dataset attached to a finetune project; ``storage_path`` is the JSONL file.

    ``source_dataset_id`` is set when this dataset was produced by
    ``POST .../curate`` from another dataset (D6 lineage).
    """

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    num_samples: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[DatasetStatus] = mapped_column(
        Enum(DatasetStatus, native_enum=False, length=16),
        nullable=False,
        default=DatasetStatus.uploaded,
    )
    validation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_dataset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    # Eval task (classify | extract | freeform): which metric the eval gate scores this set
    # with. Required on upload; NULL on datasets that predate it or were synthesized.
    task: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # What the dataset is: upload | rag_eval (synthesized golden-set questions) | behavior
    # (synthesized prompt/response rows). Curated datasets inherit their source's kind.
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="upload", server_default="upload"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship("Project", back_populates="datasets")


# ---------------------------------------------------------------------------
# Adapters (bring your own LoRA)
# ---------------------------------------------------------------------------


class Adapter(Base):
    """An imported LoRA adapter of a finetune project (E4.2).

    ``format`` gguf: ``gguf_path`` is the uploaded file. ``peft``: ``peft_dir`` holds
    ``adapter_model.safetensors`` + ``adapter_config.json`` and ``gguf_path`` stays NULL until the
    adapter job converts it (E4.4). ``sha256``/``size_bytes`` describe the uploaded file.
    ``eval_dataset_id`` is the held-out set the gate scores it on; ``eval_metrics`` is the
    ``services/eval_gate.evaluate`` dict. Files live under ``settings.adapters_dir/{id}/``.
    """

    __tablename__ = "adapters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_model: Mapped[str] = mapped_column(String(128), nullable=False)
    format: Mapped[AdapterFormat] = mapped_column(
        Enum(AdapterFormat, native_enum=False, length=8), nullable=False
    )
    peft_dir: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    gguf_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    eval_dataset_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[AdapterStatus] = mapped_column(
        Enum(AdapterStatus, native_enum=False, length=16),
        nullable=False,
        default=AdapterStatus.uploaded,
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    eval_metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship("Project", back_populates="adapters")


# ---------------------------------------------------------------------------
# Endpoint / ApiKey
# ---------------------------------------------------------------------------


class Endpoint(Base):
    """The servable model for a project. Created when the project is ready."""

    __tablename__ = "endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[EndpointStatus] = mapped_column(
        Enum(EndpointStatus, native_enum=False, length=16),
        nullable=False,
        default=EndpointStatus.pending,
    )
    # null for RAG and base-only endpoints; the `passed` adapter the endpoint serves otherwise.
    # No ON DELETE action: an adapter bound to an endpoint cannot be deleted (409 at the API).
    adapter_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("adapters.id"), nullable=True
    )
    base_model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship("Project", back_populates="endpoint")
    # selectin: the async session cannot lazy-load; this also orders the ORM's project-cascade
    # delete (endpoint before adapter) now that endpoints.adapter_id references adapters.
    adapter: Mapped[Optional[Adapter]] = relationship("Adapter", lazy="selectin")
    keys: Mapped[list[ApiKey]] = relationship(
        "ApiKey", back_populates="endpoint", cascade="all, delete-orphan"
    )


class AdapterEvent(Base):
    """Audit trail of which adapter an endpoint served and who switched it (E4.5).
    ``adapter_id`` goes NULL if the adapter is later deleted; the event stays."""

    __tablename__ = "adapter_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    endpoint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    adapter_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("adapters.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[AdapterAction] = mapped_column(
        Enum(AdapterAction, native_enum=False, length=16), nullable=False
    )
    actor_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    adapter: Mapped[Optional[Adapter]] = relationship("Adapter", lazy="selectin")
    actor: Mapped[Optional[User]] = relationship("User", lazy="selectin")


class ApiKey(Base):
    """Scoped key for a specific endpoint."""

    __tablename__ = "api_keys"
    # Every /v1/chat/completions call looks a key up by (key_prefix, is_active) —
    # the hottest query in the product. Index it so auth stays O(index) not O(table)
    # as key count grows (A4.4).
    __table_args__ = (Index("ix_apikey_prefix_active", "key_prefix", "is_active"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    endpoint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(
        String(8), nullable=False
    )  # first 8 chars shown to user
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 of full key
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
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=16), nullable=False, default=Role.member
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, native_enum=False, length=16),
        nullable=False,
        default=InvitationStatus.pending,
    )
    invited_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
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


class AppSetting(Base):
    """DB-backed org-scoped override for a whitelisted runtime knob (§C4.4).

    Precedence: DB override → env/config default. The whitelist is enforced in
    `adapta.services.app_settings`; the table stores only JSON-encoded scalars.
    """

    __tablename__ = "app_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (UniqueConstraint("team_id", "key", name="uq_app_settings_team_key"),)
