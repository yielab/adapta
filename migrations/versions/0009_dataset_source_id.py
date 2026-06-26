"""dataset_source_id — track curated-dataset lineage (D6 review)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("source_dataset_id", sa.String(36), nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "source_dataset_id")
