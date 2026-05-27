"""Add source/version/time semantics to factor and signal tables.

Revision ID: 009_add_factor_signal_time_semantics
Revises: 008_add_coordination_history
Create Date: 2026-05-27
"""

from typing import List, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_add_factor_signal_time_semantics"
down_revision: Union[str, None] = "008_add_coordination_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns(table_name)}
    if column_name in existing:
        op.drop_column(table_name, column_name)


def _create_index_if_missing(index_name: str, table_name: str, columns: List[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)


def _alter_varchar_if_present(table_name: str, column_name: str, length: int) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns(table_name)}
    if column_name in existing:
        op.alter_column(
            table_name,
            column_name,
            type_=sa.String(length),
            existing_type=sa.String(),
        )


def upgrade() -> None:
    for table_name, schema_version in [
        ("factor_snapshots", "factor_snapshot.v1"),
        ("signal_events", "signal_event.v1"),
    ]:
        _add_column_if_missing(table_name, sa.Column("instrument_id", sa.String(64), nullable=True))
        _add_column_if_missing(table_name, sa.Column("event_time", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing(table_name, sa.Column("available_time", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing(table_name, sa.Column("as_of_time", sa.DateTime(timezone=True), nullable=True))
        _add_column_if_missing(table_name, sa.Column("interval", sa.String(50), nullable=True))
        _add_column_if_missing(table_name, sa.Column("provider", sa.String(100), nullable=True))
        _add_column_if_missing(table_name, sa.Column("data_source", sa.String(100), nullable=True))
        _add_column_if_missing(table_name, sa.Column("source_version", sa.String(100), nullable=True))
        _add_column_if_missing(
            table_name,
            sa.Column(
                "schema_version",
                sa.String(100),
                nullable=False,
                server_default=schema_version,
            ),
        )

    _alter_varchar_if_present("factor_snapshots", "factor_name", 100)
    _alter_varchar_if_present("factor_snapshots", "interval", 50)
    _alter_varchar_if_present("factor_snapshots", "provider", 100)
    _alter_varchar_if_present("factor_snapshots", "data_source", 100)
    _alter_varchar_if_present("factor_snapshots", "source_version", 100)
    _alter_varchar_if_present("factor_snapshots", "schema_version", 100)
    _alter_varchar_if_present("signal_events", "source_strategy", 100)
    _alter_varchar_if_present("signal_events", "strategy_id", 120)
    _alter_varchar_if_present("signal_events", "interval", 50)
    _alter_varchar_if_present("signal_events", "provider", 100)
    _alter_varchar_if_present("signal_events", "data_source", 100)
    _alter_varchar_if_present("signal_events", "source_version", 100)
    _alter_varchar_if_present("signal_events", "schema_version", 100)

    _create_index_if_missing(
        "idx_factor_available_time",
        "factor_snapshots",
        ["symbol", "available_time"],
    )
    _create_index_if_missing(
        "idx_signal_available_time",
        "signal_events",
        ["symbol", "available_time"],
    )


def downgrade() -> None:
    _drop_index_if_exists("idx_signal_available_time", "signal_events")
    _drop_index_if_exists("idx_factor_available_time", "factor_snapshots")

    for table_name in ["signal_events", "factor_snapshots"]:
        for column_name in [
            "schema_version",
            "source_version",
            "data_source",
            "provider",
            "interval",
            "as_of_time",
            "available_time",
            "event_time",
            "instrument_id",
        ]:
            _drop_column_if_exists(table_name, column_name)
