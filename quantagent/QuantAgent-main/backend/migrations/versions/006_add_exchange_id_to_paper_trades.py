"""Add exchange_id column to paper_trades table.

Reason: The ORM model (PaperTrade in db_models.py) defines exchange_id,
but the initial migration (001) did not include it, causing
"column paper_trades.exchange_id does not exist" errors in the
order-matching scheduler.

Revision ID: 006
Revises: 2026_04_12_1039-d4293f8c131f
Create Date: 2026-05-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "d4293f8c131f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("paper_trades")}
    if "exchange_id" in existing_columns:
        return

    op.add_column(
        "paper_trades",
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
    existing_columns = {column["name"] for column in inspector.get_columns("paper_trades")}
    if "exchange_id" not in existing_columns:
        return

    op.drop_column("paper_trades", "exchange_id")
