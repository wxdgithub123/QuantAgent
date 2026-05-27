"""Add bull/bear debate and role opinion fields to coordination_history.

PRD 10.4 requires structured multi-role analysis output including:
  - bull_view / bear_view / final_decision (multi-round debate)
  - role_opinions (technical, news, macro, risk structured outputs)
  - position_advice / risk_notes
  - input_snapshot_ids (audit trail linking back to AnalysisContext)

Revision ID: 010_add_coordination_debate_fields
Revises: 009_add_factor_signal_time_semantics
Create Date: 2026-05-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "010_add_coordination_debate_fields"
down_revision: Union[str, None] = "009_add_factor_signal_time_semantics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "coordination_history",
        sa.Column("bull_view", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "coordination_history",
        sa.Column("bear_view", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "coordination_history",
        sa.Column(
            "input_snapshot_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "coordination_history",
        sa.Column(
            "role_opinions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "coordination_history",
        sa.Column(
            "position_advice",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "coordination_history",
        sa.Column("risk_notes", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("coordination_history", "risk_notes")
    op.drop_column("coordination_history", "position_advice")
    op.drop_column("coordination_history", "role_opinions")
    op.drop_column("coordination_history", "input_snapshot_ids")
    op.drop_column("coordination_history", "bear_view")
    op.drop_column("coordination_history", "bull_view")
