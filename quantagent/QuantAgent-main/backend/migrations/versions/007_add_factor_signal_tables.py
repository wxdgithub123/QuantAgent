"""Add factor_snapshots and signal_events tables (L3/L5 persistence).

Previously factors and signals were computed in-memory and discarded.
These tables enable:
  - Reproducibility of signal generation
  - L6 decision layer consuming persisted signal events
  - Audit trail of factor computation over time

Revision ID: 007
Revises: 006_add_exchange_id_to_paper_trades
Create Date: 2026-05-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── factor_snapshots ───────────────────────────────────────────────────
    op.create_table(
        "factor_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("factor_name", sa.String(50), nullable=False),
        sa.Column("factor_value", sa.Float(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'indicators'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_factor_symbol_time", "factor_snapshots", ["symbol", "timestamp"])
    op.create_index("idx_factor_name", "factor_snapshots", ["factor_name"])

    # ── signal_events ──────────────────────────────────────────────────────
    op.create_table(
        "signal_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_type", sa.String(20), nullable=False),
        sa.Column("signal_value", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("source_strategy", sa.String(30), nullable=False, server_default=sa.text("''")),
        sa.Column("strategy_id", sa.String(30), nullable=False, server_default=sa.text("''")),
        sa.Column("factors", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("extra_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_signal_symbol_time", "signal_events", ["symbol", "timestamp"])
    op.create_index("idx_signal_type", "signal_events", ["signal_type"])
    op.create_index("idx_signal_source", "signal_events", ["source_strategy"])


def downgrade() -> None:
    op.drop_index("idx_signal_source", table_name="signal_events")
    op.drop_index("idx_signal_type", table_name="signal_events")
    op.drop_index("idx_signal_symbol_time", table_name="signal_events")
    op.drop_table("signal_events")

    op.drop_index("idx_factor_name", table_name="factor_snapshots")
    op.drop_index("idx_factor_symbol_time", table_name="factor_snapshots")
    op.drop_table("factor_snapshots")
