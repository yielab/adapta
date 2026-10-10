"""chunks — persist indexed chunks in Postgres (E3.1)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "file_id",
            sa.String(36),
            sa.ForeignKey("project_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("section", sa.Text, nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("ocr", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ocr_confidence", sa.Float, nullable=True),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR,
            sa.Computed("to_tsvector('simple', text)", persisted=True),
            nullable=True,
        ),
        sa.UniqueConstraint("file_id", "chunk_index", name="uq_chunks_file_index"),
    )
    op.create_index("ix_chunks_project_id", "chunks", ["project_id"])
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_chunks_tsv", table_name="chunks")
    op.drop_index("ix_chunks_project_id", table_name="chunks")
    op.drop_table("chunks")
