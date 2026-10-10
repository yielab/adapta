"""adapter_events — promotion / rollback audit trail (E4.5)

Hand-written.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "adapter_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "endpoint_id",
            sa.String(36),
            sa.ForeignKey("endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "adapter_id",
            sa.String(36),
            sa.ForeignKey("adapters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_adapter_events_endpoint_id", "adapter_events", ["endpoint_id"])


def downgrade() -> None:
    op.drop_index("ix_adapter_events_endpoint_id", table_name="adapter_events")
    op.drop_table("adapter_events")
