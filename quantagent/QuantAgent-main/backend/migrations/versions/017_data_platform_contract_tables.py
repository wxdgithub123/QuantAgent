"""Add Phase 2 financial data platform storage contract tables.

Revision ID: 017
Revises: 016
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import op


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BAR_TABLES = ("bar_1m", "bar_1h", "bar_1d")


def _create_bar_table(table: str) -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id BIGSERIAL,
            record_id VARCHAR(128) NOT NULL,
            instrument_id VARCHAR(128),
            symbol VARCHAR(100) NOT NULL,
            exchange VARCHAR(80),
            asset_type VARCHAR(40) NOT NULL DEFAULT 'crypto',
            ts TIMESTAMPTZ NOT NULL,
            event_time TIMESTAMPTZ NOT NULL,
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ NOT NULL,
            open NUMERIC(30, 12) NOT NULL,
            high NUMERIC(30, 12) NOT NULL,
            low NUMERIC(30, 12) NOT NULL,
            close NUMERIC(30, 12) NOT NULL,
            volume NUMERIC(38, 12),
            quote_volume NUMERIC(38, 12),
            vwap NUMERIC(30, 12),
            trade_count INTEGER,
            provider VARCHAR(120) NOT NULL,
            source VARCHAR(160),
            source_priority INTEGER NOT NULL DEFAULT 100,
            source_version VARCHAR(120) NOT NULL DEFAULT 'default',
            schema_version VARCHAR(80) NOT NULL DEFAULT 'bar.v1',
            cleaning_rule_version VARCHAR(120),
            unit_standard VARCHAR(80) NOT NULL DEFAULT 'canonical',
            null_policy VARCHAR(80) NOT NULL DEFAULT 'standardized',
            data_quality_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
            outlier_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
            gap_status VARCHAR(40) NOT NULL DEFAULT 'none',
            fill_method VARCHAR(80),
            is_backfilled BOOLEAN NOT NULL DEFAULT false,
            is_adjusted BOOLEAN NOT NULL DEFAULT false,
            adjustment_factor_id BIGINT,
            raw_payload_hash VARCHAR(128),
            lineage JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            units JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_{table}_id_ts PRIMARY KEY (id, ts),
            CONSTRAINT uq_{table}_record_id_ts UNIQUE (record_id, ts),
            CONSTRAINT uq_{table}_symbol_ts_provider UNIQUE (symbol, ts, provider, source_version),
            CONSTRAINT ck_{table}_pit_visibility CHECK (available_time >= event_time),
            CONSTRAINT ck_{table}_ohlc_nonnegative CHECK (high >= low AND high >= open AND high >= close AND low <= open AND low <= close)
        );
        """
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_symbol_ts ON {table} (symbol, ts DESC);")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_available_time ON {table} (available_time DESC);")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_provider_ts ON {table} (provider, ts DESC);")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_quality_gin ON {table} USING GIN (data_quality_flags);")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_lineage_gin ON {table} USING GIN (lineage);")
    op.execute(
        f"""
        COMMENT ON TABLE {table} IS
        'Phase 2 canonical PIT bar table. Upsert key: (symbol, ts, provider, source_version). Visibility: available_time <= as_of_time.';
        """
    )


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          CREATE EXTENSION IF NOT EXISTS timescaledb;
        EXCEPTION
          WHEN undefined_file OR insufficient_privilege OR feature_not_supported THEN
            RAISE NOTICE 'TimescaleDB extension is unavailable; storage contract tables will remain plain PostgreSQL tables.';
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_provider (
            provider_id VARCHAR(120) PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            provider_type VARCHAR(60) NOT NULL,
            priority INTEGER NOT NULL DEFAULT 100,
            status VARCHAR(40) NOT NULL DEFAULT 'registered',
            health_check_url TEXT,
            rate_limit_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
            supports JSONB NOT NULL DEFAULT '[]'::jsonb,
            fallback_provider_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            custom_provider BOOLEAN NOT NULL DEFAULT false,
            last_health_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_data_provider_priority ON data_provider (priority, provider_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_data_provider_supports_gin ON data_provider USING GIN (supports);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS instrument (
            instrument_id VARCHAR(128) PRIMARY KEY,
            symbol VARCHAR(100) NOT NULL UNIQUE,
            raw_symbol VARCHAR(160),
            asset_type VARCHAR(40) NOT NULL,
            instrument_type VARCHAR(60) NOT NULL,
            exchange VARCHAR(80),
            base_asset VARCHAR(80),
            quote_asset VARCHAR(80),
            currency VARCHAR(40),
            country VARCHAR(80),
            timezone VARCHAR(80) NOT NULL DEFAULT 'UTC',
            status VARCHAR(40) NOT NULL DEFAULT 'active',
            provider VARCHAR(120),
            source_version VARCHAR(120) NOT NULL DEFAULT 'default',
            schema_version VARCHAR(80) NOT NULL DEFAULT 'instrument.v1',
            event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_instrument_pit_visibility CHECK (available_time >= event_time)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_instrument_symbol ON instrument (symbol);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_instrument_asset_type ON instrument (asset_type, instrument_type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_instrument_available_time ON instrument (available_time DESC);")

    for table in BAR_TABLES:
        _create_bar_table(table)

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS quote_latest (
            id BIGSERIAL PRIMARY KEY,
            record_id VARCHAR(128) NOT NULL UNIQUE,
            instrument_id VARCHAR(128),
            symbol VARCHAR(100) NOT NULL,
            exchange VARCHAR(80),
            asset_type VARCHAR(40) NOT NULL DEFAULT 'crypto',
            ts TIMESTAMPTZ NOT NULL,
            event_time TIMESTAMPTZ NOT NULL,
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ NOT NULL,
            bid NUMERIC(30, 12),
            ask NUMERIC(30, 12),
            last NUMERIC(30, 12),
            price NUMERIC(30, 12),
            mid NUMERIC(30, 12),
            volume NUMERIC(38, 12),
            quote_volume NUMERIC(38, 12),
            change_24h NUMERIC(30, 12),
            change_percent NUMERIC(20, 8),
            high_24h NUMERIC(30, 12),
            low_24h NUMERIC(30, 12),
            provider VARCHAR(120) NOT NULL,
            source_version VARCHAR(120) NOT NULL DEFAULT 'default',
            schema_version VARCHAR(80) NOT NULL DEFAULT 'quote_latest.v1',
            data_quality_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
            raw_payload_hash VARCHAR(128),
            lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_quote_latest_symbol_provider UNIQUE (symbol, provider),
            CONSTRAINT ck_quote_latest_pit_visibility CHECK (available_time >= event_time)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_quote_latest_symbol_ts ON quote_latest (symbol, ts DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_quote_latest_available_time ON quote_latest (available_time DESC);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fundamental_report (
            id BIGSERIAL PRIMARY KEY,
            record_id VARCHAR(128) NOT NULL UNIQUE,
            instrument_id VARCHAR(128),
            symbol VARCHAR(100) NOT NULL,
            report_type VARCHAR(80) NOT NULL,
            fiscal_period VARCHAR(40),
            fiscal_year INTEGER,
            period_start DATE,
            period_end DATE,
            report_date DATE,
            event_time TIMESTAMPTZ NOT NULL,
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ NOT NULL,
            currency VARCHAR(40),
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            units JSONB NOT NULL DEFAULT '{}'::jsonb,
            provider VARCHAR(120) NOT NULL,
            source_version VARCHAR(120) NOT NULL DEFAULT 'default',
            schema_version VARCHAR(80) NOT NULL DEFAULT 'fundamental_report.v1',
            cleaning_rule_version VARCHAR(120),
            raw_payload_hash VARCHAR(128),
            lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_fundamental_report_period UNIQUE (symbol, report_type, fiscal_period, provider, source_version),
            CONSTRAINT ck_fundamental_report_pit_visibility CHECK (available_time >= event_time)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_fundamental_report_symbol_event ON fundamental_report (symbol, event_time DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fundamental_report_available_time ON fundamental_report (available_time DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fundamental_report_metrics_gin ON fundamental_report USING GIN (metrics);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS corporate_action (
            id BIGSERIAL PRIMARY KEY,
            record_id VARCHAR(128) NOT NULL UNIQUE,
            instrument_id VARCHAR(128),
            symbol VARCHAR(100) NOT NULL,
            action_type VARCHAR(80) NOT NULL,
            ex_date DATE,
            record_date DATE,
            payable_date DATE,
            event_time TIMESTAMPTZ NOT NULL,
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ NOT NULL,
            factor NUMERIC(30, 12),
            cash_amount NUMERIC(30, 12),
            currency VARCHAR(40),
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            provider VARCHAR(120) NOT NULL,
            source_version VARCHAR(120) NOT NULL DEFAULT 'default',
            schema_version VARCHAR(80) NOT NULL DEFAULT 'corporate_action.v1',
            raw_payload_hash VARCHAR(128),
            lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_corporate_action_event UNIQUE (symbol, action_type, event_time, provider, source_version),
            CONSTRAINT ck_corporate_action_pit_visibility CHECK (available_time >= event_time)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_corporate_action_symbol_event ON corporate_action (symbol, event_time DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_corporate_action_available_time ON corporate_action (available_time DESC);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS adjustment_factor (
            id BIGSERIAL PRIMARY KEY,
            record_id VARCHAR(128) NOT NULL UNIQUE,
            instrument_id VARCHAR(128),
            symbol VARCHAR(100) NOT NULL,
            corporate_action_id BIGINT,
            factor_type VARCHAR(80) NOT NULL,
            effective_time TIMESTAMPTZ NOT NULL,
            event_time TIMESTAMPTZ NOT NULL,
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ NOT NULL,
            factor NUMERIC(30, 12) NOT NULL,
            cumulative_factor NUMERIC(30, 12),
            provider VARCHAR(120) NOT NULL,
            source_version VARCHAR(120) NOT NULL DEFAULT 'default',
            schema_version VARCHAR(80) NOT NULL DEFAULT 'adjustment_factor.v1',
            lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_adjustment_factor_effective UNIQUE (symbol, factor_type, effective_time, provider, source_version),
            CONSTRAINT ck_adjustment_factor_pit_visibility CHECK (available_time >= event_time)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_adjustment_factor_symbol_effective ON adjustment_factor (symbol, effective_time DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_adjustment_factor_available_time ON adjustment_factor (available_time DESC);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_event (
            id BIGSERIAL PRIMARY KEY,
            record_id VARCHAR(128) NOT NULL UNIQUE,
            title TEXT NOT NULL,
            url TEXT,
            source VARCHAR(160),
            provider VARCHAR(120) NOT NULL,
            author VARCHAR(200),
            published_at TIMESTAMPTZ,
            event_time TIMESTAMPTZ NOT NULL,
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ NOT NULL,
            language VARCHAR(40),
            symbols JSONB NOT NULL DEFAULT '[]'::jsonb,
            sectors JSONB NOT NULL DEFAULT '[]'::jsonb,
            topics JSONB NOT NULL DEFAULT '[]'::jsonb,
            sentiment JSONB NOT NULL DEFAULT '{}'::jsonb,
            summary TEXT,
            body_hash VARCHAR(128),
            raw_payload_hash VARCHAR(128),
            source_version VARCHAR(120) NOT NULL DEFAULT 'default',
            schema_version VARCHAR(80) NOT NULL DEFAULT 'news_event.v1',
            cleaning_rule_version VARCHAR(120),
            lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_news_event_provider_hash UNIQUE (provider, raw_payload_hash),
            CONSTRAINT ck_news_event_pit_visibility CHECK (available_time >= event_time)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_event_available_time ON news_event (available_time DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_event_published_at ON news_event (published_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_event_symbols_gin ON news_event USING GIN (symbols);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_event_topics_gin ON news_event USING GIN (topics);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_indicator (
            id BIGSERIAL PRIMARY KEY,
            record_id VARCHAR(128) NOT NULL UNIQUE,
            code VARCHAR(120) NOT NULL,
            name VARCHAR(240),
            country VARCHAR(80),
            category VARCHAR(120),
            frequency VARCHAR(40),
            observation_time TIMESTAMPTZ NOT NULL,
            event_time TIMESTAMPTZ NOT NULL,
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ NOT NULL,
            value NUMERIC(38, 12),
            unit VARCHAR(80),
            provider VARCHAR(120) NOT NULL,
            source_version VARCHAR(120) NOT NULL DEFAULT 'default',
            schema_version VARCHAR(80) NOT NULL DEFAULT 'macro_indicator.v1',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw_payload_hash VARCHAR(128),
            lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_macro_indicator_observation UNIQUE (code, observation_time, provider, source_version),
            CONSTRAINT ck_macro_indicator_pit_visibility CHECK (available_time >= event_time)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_macro_indicator_code_observation ON macro_indicator (code, observation_time DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_macro_indicator_available_time ON macro_indicator (available_time DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_macro_indicator_metadata_gin ON macro_indicator USING GIN (metadata);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS etl_job_log (
            id BIGSERIAL PRIMARY KEY,
            batch_id VARCHAR(128) NOT NULL,
            job_type VARCHAR(100) NOT NULL,
            status VARCHAR(40) NOT NULL,
            provider VARCHAR(120),
            data_type VARCHAR(80) NOT NULL,
            symbols JSONB NOT NULL DEFAULT '[]'::jsonb,
            intervals JSONB NOT NULL DEFAULT '[]'::jsonb,
            parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
            idempotency_key VARCHAR(160),
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            event_time TIMESTAMPTZ,
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ,
            rows_read INTEGER NOT NULL DEFAULT 0,
            rows_written INTEGER NOT NULL DEFAULT 0,
            rows_duplicate INTEGER NOT NULL DEFAULT 0,
            gaps_detected INTEGER NOT NULL DEFAULT 0,
            gaps_filled INTEGER NOT NULL DEFAULT 0,
            outliers_flagged INTEGER NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0,
            timeout_seconds INTEGER,
            error TEXT,
            lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_etl_job_log_batch UNIQUE (batch_id),
            CONSTRAINT uq_etl_job_log_idempotency UNIQUE (idempotency_key)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_etl_job_log_status ON etl_job_log (status, started_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_etl_job_log_data_type ON etl_job_log (data_type, started_at DESC);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_lineage (
            id BIGSERIAL PRIMARY KEY,
            record_id VARCHAR(128) NOT NULL UNIQUE,
            entity_table VARCHAR(120) NOT NULL,
            entity_record_id VARCHAR(128) NOT NULL,
            provider VARCHAR(120),
            etl_batch_id VARCHAR(128),
            upstream_record_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            transformation VARCHAR(160),
            cleaning_rule_version VARCHAR(120),
            source_version VARCHAR(120),
            lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_data_lineage_entity ON data_lineage (entity_table, entity_record_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_data_lineage_batch ON data_lineage (etl_batch_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_data_lineage_upstream_gin ON data_lineage USING GIN (upstream_record_ids);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cleaned_data_item (
            id BIGSERIAL PRIMARY KEY,
            record_id VARCHAR(128) NOT NULL UNIQUE,
            entity_table VARCHAR(120) NOT NULL,
            original_record_id VARCHAR(128) NOT NULL,
            cleaned_record_id VARCHAR(128) NOT NULL,
            rule_id VARCHAR(160) NOT NULL,
            rule_version INTEGER NOT NULL,
            changed_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
            before_value JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_value JSONB NOT NULL DEFAULT '{}'::jsonb,
            reason TEXT,
            event_time TIMESTAMPTZ NOT NULL,
            ingest_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            available_time TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_cleaned_data_item_pit_visibility CHECK (available_time >= event_time)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cleaned_data_item_original ON cleaned_data_item (entity_table, original_record_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cleaned_data_item_rule ON cleaned_data_item (rule_id, rule_version);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_platform_storage_policy (
            policy_id VARCHAR(120) PRIMARY KEY,
            table_name VARCHAR(120) NOT NULL,
            policy_type VARCHAR(80) NOT NULL,
            policy_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(40) NOT NULL DEFAULT 'declared',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        INSERT INTO data_platform_storage_policy (policy_id, table_name, policy_type, policy_config, status)
        VALUES
          ('bar_1m_compression', 'bar_1m', 'timescale_compression', '{"after": "7 days", "segmentby": "symbol", "orderby": "ts DESC"}'::jsonb, 'guarded'),
          ('bar_1h_compression', 'bar_1h', 'timescale_compression', '{"after": "30 days", "segmentby": "symbol", "orderby": "ts DESC"}'::jsonb, 'guarded'),
          ('bar_1d_compression', 'bar_1d', 'timescale_compression', '{"after": "90 days", "segmentby": "symbol", "orderby": "ts DESC"}'::jsonb, 'guarded'),
          ('bar_1m_retention', 'bar_1m', 'retention', '{"after": "730 days", "cold_tier_after": "90 days"}'::jsonb, 'declared'),
          ('bar_1h_retention', 'bar_1h', 'retention', '{"after": "1825 days", "cold_tier_after": "365 days"}'::jsonb, 'declared'),
          ('bar_1d_retention', 'bar_1d', 'retention', '{"after": "unlimited", "cold_tier_after": "1825 days"}'::jsonb, 'declared'),
          ('postgres_pitr', 'all', 'backup_pitr', '{"wal_archiving": true, "base_backup": "required", "restore_test": "required"}'::jsonb, 'declared')
        ON CONFLICT (policy_id) DO UPDATE
        SET policy_config = EXCLUDED.policy_config,
            status = EXCLUDED.status,
            updated_at = now();
        """
    )

    op.execute(
        """
        DO $$
        DECLARE
          tbl text;
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'create_hypertable') THEN
            FOREACH tbl IN ARRAY ARRAY['bar_1m', 'bar_1h', 'bar_1d']
            LOOP
              EXECUTE format('SELECT create_hypertable(%L, %L, if_not_exists => TRUE, migrate_data => TRUE)', tbl, 'ts');
            END LOOP;
          ELSE
            RAISE NOTICE 'TimescaleDB create_hypertable() is unavailable; hypertable policy remains declared.';
          END IF;
        EXCEPTION
          WHEN undefined_function OR insufficient_privilege OR feature_not_supported THEN
            RAISE NOTICE 'TimescaleDB hypertable setup skipped for Phase 2 storage contract.';
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
          tbl text;
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'add_compression_policy') THEN
            FOREACH tbl IN ARRAY ARRAY['bar_1m', 'bar_1h', 'bar_1d']
            LOOP
              EXECUTE format('ALTER TABLE %I SET (timescaledb.compress, timescaledb.compress_segmentby = %L, timescaledb.compress_orderby = %L)', tbl, 'symbol', 'ts DESC');
            END LOOP;
            PERFORM add_compression_policy('bar_1m', INTERVAL '7 days', if_not_exists => TRUE);
            PERFORM add_compression_policy('bar_1h', INTERVAL '30 days', if_not_exists => TRUE);
            PERFORM add_compression_policy('bar_1d', INTERVAL '90 days', if_not_exists => TRUE);
          ELSE
            RAISE NOTICE 'TimescaleDB add_compression_policy() is unavailable; compression policy remains declared.';
          END IF;
        EXCEPTION
          WHEN undefined_function OR insufficient_privilege OR feature_not_supported THEN
            RAISE NOTICE 'TimescaleDB compression setup skipped for Phase 2 storage contract.';
        END $$;
        """
    )


def downgrade() -> None:
    for table in (
        "data_platform_storage_policy",
        "cleaned_data_item",
        "data_lineage",
        "etl_job_log",
        "macro_indicator",
        "news_event",
        "adjustment_factor",
        "corporate_action",
        "fundamental_report",
        "quote_latest",
        "bar_1d",
        "bar_1h",
        "bar_1m",
        "instrument",
        "data_provider",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
