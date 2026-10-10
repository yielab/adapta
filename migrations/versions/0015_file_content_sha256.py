"""project_files.content_sha256 — raw-bytes duplicate check (E3.3b)

Duplicate uploads are detected from the sha256 of the saved bytes instead of parsing the
file in the request. Nullable: files uploaded earlier have no hash. Hand-written.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("project_files", sa.Column("content_sha256", sa.String(64), nullable=True))
    op.create_index(
        "ix_project_files_project_sha", "project_files", ["project_id", "content_sha256"]
    )


def downgrade() -> None:
    op.drop_index("ix_project_files_project_sha", table_name="project_files")
    op.drop_column("project_files", "content_sha256")
