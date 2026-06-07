"""Harden audit_logs with standard fields and append-only guard.

Revision ID: 015
Revises: 014
Create Date: 2026-06-07
"""

from typing import Sequence, Union

from alembic import op


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE audit_logs
        ADD COLUMN IF NOT EXISTS event_type VARCHAR(80),
        ADD COLUMN IF NOT EXISTS symbol VARCHAR(100),
        ADD COLUMN IF NOT EXISTS decision_id INTEGER,
        ADD COLUMN IF NOT EXISTS source_decision_id INTEGER,
        ADD COLUMN IF NOT EXISTS replay_decision_id INTEGER,
        ADD COLUMN IF NOT EXISTS order_intent_id VARCHAR(128),
        ADD COLUMN IF NOT EXISTS order_id VARCHAR(128),
        ADD COLUMN IF NOT EXISTS context_id VARCHAR(128),
        ADD COLUMN IF NOT EXISTS context_hash VARCHAR(128),
        ADD COLUMN IF NOT EXISTS risk_status VARCHAR(32),
        ADD COLUMN IF NOT EXISTS execution_status VARCHAR(32),
        ADD COLUMN IF NOT EXISTS backtest_id INTEGER,
        ADD COLUMN IF NOT EXISTS replay_session_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(50),
        ADD COLUMN IF NOT EXISTS payload_hash VARCHAR(128),
        ADD COLUMN IF NOT EXISTS prev_hash VARCHAR(128),
        ADD COLUMN IF NOT EXISTS immutable BOOLEAN NOT NULL DEFAULT TRUE;
        """
    )
    op.execute(
        """
        UPDATE audit_logs
        SET
          event_type = COALESCE(
            event_type,
            CASE COALESCE(details->>'eventType', details->>'event_type', action)
              WHEN 'ORDER_INTENT_NOOP' THEN 'HOLD_RECORDED'
              WHEN 'ORDER_INTENT_PREVIEW' THEN 'ORDER_INTENT_CREATED'
              WHEN 'ORDER_INTENT_RISK_CHECKED' THEN 'RISK_CHECK_PASSED'
              WHEN 'ORDER_INTENT_BLOCKED' THEN 'RISK_BLOCKED'
              WHEN 'ORDER_INTENT_EXECUTED' THEN 'PAPER_ORDER_FILLED'
              WHEN 'ORDER_CREATE' THEN 'PAPER_ORDER_FILLED'
              WHEN 'ORDER_FILL' THEN 'PAPER_ORDER_FILLED'
              WHEN 'ORDER_CANCEL' THEN 'PAPER_ORDER_REJECTED'
              ELSE COALESCE(details->>'eventType', details->>'event_type', action)
            END
          ),
          symbol = COALESCE(symbol, details->>'symbol', details->'intent'->>'symbol', resource),
          decision_id = COALESCE(
            decision_id,
            CASE WHEN details->>'decisionId' ~ '^[0-9]+$' THEN (details->>'decisionId')::integer END,
            CASE WHEN details->>'decision_id' ~ '^[0-9]+$' THEN (details->>'decision_id')::integer END,
            CASE WHEN details->'intent'->>'decision_id' ~ '^[0-9]+$' THEN (details->'intent'->>'decision_id')::integer END,
            CASE WHEN details->'decision'->>'id' ~ '^[0-9]+$' THEN (details->'decision'->>'id')::integer END
          ),
          source_decision_id = COALESCE(
            source_decision_id,
            CASE WHEN details->>'sourceDecisionId' ~ '^[0-9]+$' THEN (details->>'sourceDecisionId')::integer END,
            CASE WHEN details->>'source_decision_id' ~ '^[0-9]+$' THEN (details->>'source_decision_id')::integer END
          ),
          replay_decision_id = COALESCE(
            replay_decision_id,
            CASE WHEN details->>'replayDecisionId' ~ '^[0-9]+$' THEN (details->>'replayDecisionId')::integer END,
            CASE WHEN details->>'replay_decision_id' ~ '^[0-9]+$' THEN (details->>'replay_decision_id')::integer END
          ),
          order_intent_id = COALESCE(order_intent_id, details->>'orderIntentId', details->'intent'->>'id', details->'intent'->>'intent_id'),
          order_id = COALESCE(order_id, details->>'orderId', details->>'order_id', details->'execution'->>'order_id', details->'executionResult'->>'order_id'),
          context_id = COALESCE(context_id, details->>'contextId', details->'decision'->>'context_id'),
          context_hash = COALESCE(context_hash, details->>'contextHash', details->'decision'->>'context_hash'),
          backtest_id = COALESCE(
            backtest_id,
            CASE WHEN details->>'backtestId' ~ '^[0-9]+$' THEN (details->>'backtestId')::integer END,
            CASE WHEN details->>'backtest_id' ~ '^[0-9]+$' THEN (details->>'backtest_id')::integer END
          ),
          replay_session_id = COALESCE(replay_session_id, details->>'replaySessionId', details->>'replay_session_id'),
          execution_mode = COALESCE(execution_mode, details->>'executionMode', details->>'execution_mode'),
          immutable = TRUE
        WHERE TRUE;
        """
    )
    for index_name, column_name in (
        ("idx_audit_logs_event_type", "event_type"),
        ("idx_audit_logs_symbol_std", "symbol"),
        ("idx_audit_logs_decision_id", "decision_id"),
        ("idx_audit_logs_source_decision_id", "source_decision_id"),
        ("idx_audit_logs_replay_decision_id", "replay_decision_id"),
        ("idx_audit_logs_order_intent_id", "order_intent_id"),
        ("idx_audit_logs_order_id", "order_id"),
        ("idx_audit_logs_context_hash", "context_hash"),
        ("idx_audit_logs_backtest_id", "backtest_id"),
        ("idx_audit_logs_replay_session_id", "replay_session_id"),
        ("idx_audit_logs_payload_hash", "payload_hash"),
    ):
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON audit_logs ({column_name});
            """
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_logs_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_logs are append-only; write a new audit event instead';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_logs_mutation ON audit_logs;")
    op.execute(
        """
        CREATE TRIGGER trg_prevent_audit_logs_mutation
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_logs_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_logs_mutation ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_logs_mutation();")
    for index_name in (
        "idx_audit_logs_payload_hash",
        "idx_audit_logs_replay_session_id",
        "idx_audit_logs_backtest_id",
        "idx_audit_logs_context_hash",
        "idx_audit_logs_order_id",
        "idx_audit_logs_order_intent_id",
        "idx_audit_logs_replay_decision_id",
        "idx_audit_logs_source_decision_id",
        "idx_audit_logs_decision_id",
        "idx_audit_logs_symbol_std",
        "idx_audit_logs_event_type",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index_name};")
    op.execute(
        """
        ALTER TABLE audit_logs
        DROP COLUMN IF EXISTS immutable,
        DROP COLUMN IF EXISTS prev_hash,
        DROP COLUMN IF EXISTS payload_hash,
        DROP COLUMN IF EXISTS execution_mode,
        DROP COLUMN IF EXISTS replay_session_id,
        DROP COLUMN IF EXISTS backtest_id,
        DROP COLUMN IF EXISTS execution_status,
        DROP COLUMN IF EXISTS risk_status,
        DROP COLUMN IF EXISTS context_hash,
        DROP COLUMN IF EXISTS context_id,
        DROP COLUMN IF EXISTS order_id,
        DROP COLUMN IF EXISTS order_intent_id,
        DROP COLUMN IF EXISTS replay_decision_id,
        DROP COLUMN IF EXISTS source_decision_id,
        DROP COLUMN IF EXISTS decision_id,
        DROP COLUMN IF EXISTS symbol,
        DROP COLUMN IF EXISTS event_type;
        """
    )
