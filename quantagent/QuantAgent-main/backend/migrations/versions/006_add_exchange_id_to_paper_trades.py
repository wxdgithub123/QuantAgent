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


revision: str = "006_add_exchange_id_to_paper_trades"
down_revision: Union[str, None] = "d4293f8c131f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.drop_column("paper_trades", "exchange_id")
