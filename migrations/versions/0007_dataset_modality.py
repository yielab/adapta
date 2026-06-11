"""datasets.modality + num_images — image-understanding fine-tunes (§V1.3)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # "text" | "vision". Every pre-existing dataset is text (server_default
    # backfills); vision datasets arrive with the §V2 bundle upload.
    op.add_column(
        "datasets",
        sa.Column("modality", sa.String(16), nullable=False, server_default="text"),
    )
    # Image count for vision bundles; NULL for text datasets.
    op.add_column("datasets", sa.Column("num_images", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "num_images")
    op.drop_column("datasets", "modality")
