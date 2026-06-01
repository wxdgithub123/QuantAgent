"""Add hibernation columns to selection_history.

Revision ID: 012
Revises: 011
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE selection_history
        ADD COLUMN IF NOT EXISTS hibernating_strategy_ids JSONB DEFAULT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE selection_history
        ADD COLUMN IF NOT EXISTS revived_strategy_ids JSONB DEFAULT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE selection_history
        ADD COLUMN IF NOT EXISTS revival_reasons JSONB DEFAULT NULL;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE selection_history DROP COLUMN IF EXISTS revival_reasons;")
    op.execute("ALTER TABLE selection_history DROP COLUMN IF EXISTS revived_strategy_ids;")
    op.execute("ALTER TABLE selection_history DROP COLUMN IF EXISTS hibernating_strategy_ids;")
