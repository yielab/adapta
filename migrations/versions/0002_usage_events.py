"""usage events (daily token rollup per endpoint)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "endpoint_id",
            sa.String(36),
            sa.ForeignKey("endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("endpoint_id", "day", name="uq_usage_endpoint_day"),
    )
    op.create_index("ix_usage_endpoint_day", "usage_events", ["endpoint_id", "day"])


def downgrade() -> None:
    op.drop_index("ix_usage_endpoint_day", table_name="usage_events")
    op.drop_table("usage_events")
