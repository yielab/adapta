"""adapters — bring-your-own-adapter registry (E4.2)

Creates ``adapters`` and replaces the bare ``endpoints.adapter_path`` with a nullable FK
``endpoints.adapter_id``. Hand-written. Pre-existing endpoints carried a path no importer
produced (training was removed in E4.1), so ``adapter_path`` is dropped without a backfill;
downgrade restores the empty column.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "adapters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("base_model", sa.String(128), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("peft_dir", sa.String(512), nullable=True),
        sa.Column("gguf_path", sa.String(512), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column(
            "eval_dataset_id",
            sa.String(36),
            sa.ForeignKey("datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("eval_metrics", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_adapters_project_id", "adapters", ["project_id"])

    op.add_column("endpoints", sa.Column("adapter_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_endpoints_adapter_id", "endpoints", "adapters", ["adapter_id"], ["id"])
    op.drop_column("endpoints", "adapter_path")


def downgrade() -> None:
    op.add_column("endpoints", sa.Column("adapter_path", sa.String(512), nullable=True))
    op.drop_constraint("fk_endpoints_adapter_id", "endpoints", type_="foreignkey")
    op.drop_column("endpoints", "adapter_id")
    op.drop_index("ix_adapters_project_id", table_name="adapters")
    op.drop_table("adapters")
