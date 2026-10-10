"""rag_eval_runs — the RAG gate's run history + projects.golden_dataset_id (E5.2)

Hand-written. Follows 0019 (E5.1).

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("golden_dataset_id", sa.String(36), nullable=True))
    op.create_table(
        "rag_eval_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dataset_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("k", sa.Integer, nullable=False),
        sa.Column("n_questions", sa.Integer, nullable=True),
        sa.Column("recall", sa.Float, nullable=True),
        sa.Column("mrr", sa.Float, nullable=True),
        sa.Column("p50_ms", sa.Float, nullable=True),
        sa.Column("baseline_recall", sa.Float, nullable=True),
        sa.Column("delta", sa.Float, nullable=True),
        sa.Column("regression", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("questions", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_rag_eval_runs_project_id", "rag_eval_runs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_rag_eval_runs_project_id", table_name="rag_eval_runs")
    op.drop_table("rag_eval_runs")
    op.drop_column("projects", "golden_dataset_id")
