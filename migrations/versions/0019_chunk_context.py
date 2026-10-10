"""chunk_context — contextual retrieval (E5.1)

Adds ``chunks.context`` (LLM situating sentence, NULL unless the project opted in) and
``projects.contextual_retrieval`` (default false). ``chunks.tsv`` is a GENERATED column, so it
is dropped and re-added over ``coalesce(context,'') || ' ' || text`` (PG cannot alter a
generated expression in place before 17); with ``context`` NULL the vector is identical to the
old ``to_tsvector('simple', text)``. Hand-written. Follows 0018 (E4.8).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _regenerate_tsv(expr: str) -> None:
    op.drop_index("ix_chunks_tsv", table_name="chunks")
    op.drop_column("chunks", "tsv")
    op.add_column(
        "chunks",
        sa.Column("tsv", postgresql.TSVECTOR, sa.Computed(expr, persisted=True), nullable=True),
    )
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")


def upgrade() -> None:
    op.add_column("chunks", sa.Column("context", sa.Text(), nullable=True))
    _regenerate_tsv("to_tsvector('simple', coalesce(context, '') || ' ' || text)")
    op.add_column(
        "projects",
        sa.Column("contextual_retrieval", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("projects", "contextual_retrieval")
    _regenerate_tsv("to_tsvector('simple', text)")
    op.drop_column("chunks", "context")
