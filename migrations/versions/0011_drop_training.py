"""drop_training — remove in-product training (E4.1)

Drops ``training_jobs`` and the image-bundle columns ``datasets.modality`` /
``datasets.num_images``, and retires the ``training`` project status. Hand-written:
autogenerate would not move projects off the removed status.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `ProjectStatus.training` no longer exists; a project left in it would fail to load.
    op.execute("UPDATE projects SET status = 'created' WHERE status = 'training'")
    op.drop_table("training_jobs")
    op.drop_column("datasets", "num_images")
    op.drop_column("datasets", "modality")


def downgrade() -> None:
    # Recreates the schema only — training rows are not recoverable.
    op.add_column(
        "datasets",
        sa.Column("modality", sa.String(16), nullable=False, server_default="text"),
    )
    op.add_column("datasets", sa.Column("num_images", sa.Integer, nullable=True))
    op.create_table(
        "training_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress", sa.Float, nullable=False),
        sa.Column("logs", sa.Text, nullable=True),
        sa.Column("adapter_path", sa.String(512), nullable=True),
        sa.Column("eval_score", sa.Float, nullable=True),
        sa.Column("eval_passed", sa.Boolean, nullable=True),
        sa.Column("eval_metrics", sa.Text, nullable=True),
        sa.Column("training_config", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
