"""dataset_kind — what a dataset is for (E4.8)

Adds ``datasets.kind`` (``upload | rag_eval | behavior``), NOT NULL, default ``upload``.
``rag_eval`` rows are golden-set retrieval questions; ``behavior`` rows are prompt/response
pairs usable as an adapter eval set. Hand-written. Follows 0017 (E4.5).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="upload"),
    )


def downgrade() -> None:
    op.drop_column("datasets", "kind")
