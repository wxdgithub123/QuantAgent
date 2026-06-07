"""Supplement missing columns (2026-06-06 work session).

Covers:
  - factor_snapshots: + interval, as_of_time, instrument_id, event_time
  - signal_events: + interval, as_of_time, instrument_id, event_time
  - paper_trades: + exchange_id (migration 006 had a broken down_revision chain)
  - paper_positions: + exchange_id

Revision ID: 016
Revises: 015
Create Date: 2026-06-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists in a table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns(table)}
    return column in existing


def upgrade() -> None:
    # ── 1. factor_snapshots: missing columns ──
    for col_name, col_type in [
        ("interval", sa.String(50)),
        ("as_of_time", sa.DateTime(timezone=True)),
        ("instrument_id", sa.String(64)),
        ("event_time", sa.DateTime(timezone=True)),
    ]:
        if not _column_exists("factor_snapshots", col_name):
            op.add_column("factor_snapshots", sa.Column(col_name, col_type))

    # ── 2. signal_events: missing columns ──
    for col_name, col_type in [
        ("interval", sa.String(50)),
        ("as_of_time", sa.DateTime(timezone=True)),
        ("instrument_id", sa.String(64)),
        ("event_time", sa.DateTime(timezone=True)),
    ]:
        if not _column_exists("signal_events", col_name):
            op.add_column("signal_events", sa.Column(col_name, col_type))

    # ── 3. paper_trades: exchange_id (fix broken 006 migration) ──
    if not _column_exists("paper_trades", "exchange_id"):
        op.add_column(
            "paper_trades",
            sa.Column("exchange_id", sa.String(20), nullable=False, server_default="binance"),
        )

    # ── 4. paper_positions: exchange_id ──
    if not _column_exists("paper_positions", "exchange_id"):
        op.add_column(
            "paper_positions",
            sa.Column("exchange_id", sa.String(20), nullable=False, server_default="binance"),
        )


def downgrade() -> None:
    # This migration is an idempotent compatibility supplement for schemas that
    # missed earlier revisions. Dropping these columns here would remove columns
    # owned by 006/009/014 on normally migrated databases, so downgrade is a no-op.
    pass
