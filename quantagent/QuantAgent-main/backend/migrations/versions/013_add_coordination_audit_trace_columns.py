"""Add audit trace columns to coordination_history.

Revision ID: 013
Revises: 012
Create Date: 2026-06-06
"""

from typing import Sequence, Union

from alembic import op


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE coordination_history
        ADD COLUMN IF NOT EXISTS context_id VARCHAR(128),
        ADD COLUMN IF NOT EXISTS context_hash VARCHAR(128),
        ADD COLUMN IF NOT EXISTS available_time TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS model_version VARCHAR(128),
        ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(128);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_coord_context_hash
        ON coordination_history (context_hash);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_coord_context_hash;")
    op.execute(
        """
        ALTER TABLE coordination_history
        DROP COLUMN IF EXISTS prompt_version,
        DROP COLUMN IF EXISTS model_version,
        DROP COLUMN IF EXISTS available_time,
        DROP COLUMN IF EXISTS context_hash,
        DROP COLUMN IF EXISTS context_id;
        """
    )
