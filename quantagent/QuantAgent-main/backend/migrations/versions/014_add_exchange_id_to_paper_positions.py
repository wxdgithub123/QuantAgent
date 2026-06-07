"""Add exchange_id column to paper_positions table.

Reason: The ORM model (PaperPosition in db_models.py) defines exchange_id,
but earlier migrations only added it to paper_trades. Scheduler risk checks
read PaperPosition.exchange_id and fail when the column is missing.

Revision ID: 014
Revises: 013
Create Date: 2026-06-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("paper_positions")
    }
    if "exchange_id" in existing_columns:
        return

    op.add_column(
        "paper_positions",
        sa.Column(
            "exchange_id",
            sa.String(20),
            nullable=False,
            server_default="binance",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("paper_positions")
    }
    if "exchange_id" not in existing_columns:
        return

    op.drop_column("paper_positions", "exchange_id")
