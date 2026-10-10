"""collection_dim — record the embedding dimension per collection (E3.6)

Adds nullable ``collections.embedding_dim``. Set on the first indexing under a
model and checked afterwards, so a same-named model that now yields a different
vector size (or a model swapped under an unchanged name) is a typed 409, not a
Chroma dimension error. ``NULL`` = recorded before this column existed; the next
indexing or ``scripts/reembed.py`` fills it.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("collections", sa.Column("embedding_dim", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("collections", "embedding_dim")
