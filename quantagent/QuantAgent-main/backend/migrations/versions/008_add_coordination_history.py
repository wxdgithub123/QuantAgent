"""Add coordination_history table for audit/visualization of L6 decisions.

Revision ID: 008
Revises: 007_add_factor_signal_tables
Create Date: 2026-05-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008_add_coordination_history"
down_revision: Union[str, None] = "007_add_factor_signal_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coordination_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("final_signal", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("vote_breakdown", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("risk_veto", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("agent_signals", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_coord_symbol_time", "coordination_history", ["symbol", "timestamp"])
    op.create_index("idx_coord_signal", "coordination_history", ["final_signal"])


def downgrade() -> None:
    op.drop_index("idx_coord_signal", table_name="coordination_history")
    op.drop_index("idx_coord_symbol_time", table_name="coordination_history")
    op.drop_table("coordination_history")
