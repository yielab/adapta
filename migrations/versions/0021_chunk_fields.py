"""chunk_fields — visual extraction (E5.4)

Adds ``chunks.fields`` (JSONB, structured metadata read by the vision base; NULL unless the
file was extracted) and ``projects.extraction_schema`` (JSON, not JSONB: key order is the header order; NULL = off). Both
nullable, no backfill. Hand-written. Follows 0020 (E5.2).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("fields", postgresql.JSONB(), nullable=True))
    op.add_column("projects", sa.Column("extraction_schema", postgresql.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "extraction_schema")
    op.drop_column("chunks", "fields")
