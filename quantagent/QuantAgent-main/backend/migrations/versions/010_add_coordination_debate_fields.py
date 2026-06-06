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


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {existing["name"] for existing in inspector.get_columns(table_name)}
    if column.name not in existing_columns:
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {existing["name"] for existing in inspector.get_columns(table_name)}
    if column_name in existing_columns:
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    _add_column_if_missing(
        "coordination_history",
        sa.Column("bull_view", sa.Text(), nullable=False, server_default=""),
    )
    _add_column_if_missing(
        "coordination_history",
        sa.Column("bear_view", sa.Text(), nullable=False, server_default=""),
    )
    _add_column_if_missing(
        "coordination_history",
        sa.Column(
            "input_snapshot_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    _add_column_if_missing(
        "coordination_history",
        sa.Column(
            "role_opinions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    _add_column_if_missing(
        "coordination_history",
        sa.Column(
            "position_advice",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    _add_column_if_missing(
        "coordination_history",
        sa.Column("risk_notes", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    _drop_column_if_exists("coordination_history", "risk_notes")
    _drop_column_if_exists("coordination_history", "position_advice")
    _drop_column_if_exists("coordination_history", "role_opinions")
    _drop_column_if_exists("coordination_history", "input_snapshot_ids")
    _drop_column_if_exists("coordination_history", "bear_view")
    _drop_column_if_exists("coordination_history", "bull_view")
