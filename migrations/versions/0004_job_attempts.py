"""training_jobs.attempts — crash-recovery retry counter (A4.2)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Counts how many times crash-recovery has re-picked this job. A hard worker
    # crash leaves a job `running` with no live worker; startup reconciliation
    # requeues it once (attempts -> 1) and fails it on the next loss, so a job
    # that crashes the worker can't loop forever.
    op.add_column(
        "training_jobs",
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("training_jobs", "attempts")
