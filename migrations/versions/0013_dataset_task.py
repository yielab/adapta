"""dataset_task — eval task on datasets (E4.3)

Adds nullable ``datasets.task`` (``classify | extract | freeform``): the metric the CPU
eval gate scores an uploaded eval set with. Nullable because existing and synthesized
datasets have none; the API requires it on upload. Hand-written.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("task", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "task")
