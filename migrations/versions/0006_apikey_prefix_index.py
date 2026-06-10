"""api_keys (key_prefix, is_active) index — auth hot-path lookup (A4.4)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-10
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every /v1/chat/completions call resolves the scoped key via
    # `WHERE key_prefix = ? AND is_active = true`. Index it so the hottest query
    # in the product is an index scan, not a full table scan as keys accumulate.
    op.create_index("ix_apikey_prefix_active", "api_keys", ["key_prefix", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_apikey_prefix_active", table_name="api_keys")
