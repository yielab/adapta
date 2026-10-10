"""drop_chunk_counters — chunk counts are read from ``chunks`` (F2.1)

Drops the stored counters nothing reads any more since E3.1/E3.2:
``project_files.num_chunks``, ``collections.num_documents``, ``collections.num_chunks``.
The API still reports ``num_chunks`` per file, now computed with ``count(*)`` over ``chunks``.
Hand-written. Follows 0021 (E5.4).

Downgrade re-adds the columns (``project_files.num_chunks`` nullable, the collection
counters ``server_default 0``) and backfills them from ``chunks``.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("project_files", "num_chunks")
    op.drop_column("collections", "num_chunks")
    op.drop_column("collections", "num_documents")


def downgrade() -> None:
    op.add_column("collections", sa.Column("num_documents", sa.Integer, nullable=False, server_default="0"))
    op.add_column("collections", sa.Column("num_chunks", sa.Integer, nullable=False, server_default="0"))
    op.add_column("project_files", sa.Column("num_chunks", sa.Integer, nullable=True))
    op.execute(
        "UPDATE project_files SET num_chunks = c.n "
        "FROM (SELECT file_id, count(*) AS n FROM chunks GROUP BY file_id) c "
        "WHERE project_files.id = c.file_id"
    )
    op.execute(
        "UPDATE collections SET "
        "num_chunks = COALESCE((SELECT count(*) FROM chunks WHERE chunks.project_id = collections.project_id), 0), "
        "num_documents = COALESCE((SELECT count(DISTINCT file_id) FROM chunks "
        "WHERE chunks.project_id = collections.project_id), 0)"
    )
