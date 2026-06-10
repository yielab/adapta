"""training_jobs.eval_metrics — full eval result JSON for an auditable gate (A4.6)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The full EvaluationResult.to_dict() as JSON (score, base_score, score_delta,
    # held_out, sample_predictions, metrics) so an operator can audit WHY a gate
    # passed or failed, not just see the scalar score.
    op.add_column("training_jobs", sa.Column("eval_metrics", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("training_jobs", "eval_metrics")
