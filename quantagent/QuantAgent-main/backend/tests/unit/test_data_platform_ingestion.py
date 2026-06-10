from datetime import datetime, timezone

import pytest

from app.services import data_platform_ingestion as ingestion


def test_prepare_fundamental_record_adds_identity_pit_hash_and_lineage():
    record = ingestion.prepare_ingest_record(
        "fundamental_report",
        {
            "symbol": "btc/usdt",
            "report_type": "income_statement",
            "fiscal_period": "2026Q1",
            "report_date": "2026-04-15",
            "metrics": {"revenue": 123.45},
        },
        provider="openbb:yfinance",
        source_version="v1",
        batch_id="batch-1",
    )

    assert record["symbol"] == "BTCUSDT"
    assert record["provider"] == "openbb:yfinance"
    assert record["schema_version"] == "fundamental_report.v1"
    assert record["event_time"].isoformat() == "2026-04-15T00:00:00+00:00"
    assert record["available_time"] == record["event_time"]
    assert record["record_id"].startswith("sha256:")
    assert record["raw_payload_hash"].startswith("sha256:")
    assert record["lineage"]["batch_id"] == "batch-1"
    assert record["lineage"]["raw_payload_hash"] == record["raw_payload_hash"]


def test_prepare_record_rejects_future_visibility_violation():
    with pytest.raises(ValueError, match="available_time"):
        ingestion.prepare_ingest_record(
            "corporate_action",
            {
                "symbol": "AAPL",
                "action_type": "split",
                "event_time": "2026-01-02T00:00:00+00:00",
                "available_time": "2026-01-01T00:00:00+00:00",
            },
            provider="openbb:yfinance",
        )


def test_build_upsert_statement_casts_jsonb_and_is_idempotent():
    record = ingestion.prepare_ingest_record(
        "corporate_action",
        {
            "symbol": "AAPL",
            "action_type": "dividend",
            "ex_date": "2026-02-03",
            "details": {"amount": 0.25},
        },
        provider="openbb:yfinance",
    )
    sql, params = ingestion.build_upsert_statement("corporate_action", record)

    assert "INSERT INTO corporate_action" in sql
    assert "ON CONFLICT (record_id) DO UPDATE" in sql
    assert "CAST(:details AS JSONB)" in sql
    assert "updated_at = now()" in sql
    assert params["symbol"] == "AAPL"
    assert params["details"].startswith("{")


def test_build_lineage_and_etl_job_log_statements_include_record_ids():
    record = ingestion.prepare_ingest_record(
        "adjustment_factor",
        {
            "symbol": "AAPL",
            "factor_type": "split",
            "effective_time": datetime(2026, 2, 3, tzinfo=timezone.utc),
            "factor": 0.5,
        },
        provider="openbb:yfinance",
        batch_id="batch-adjust",
    )

    lineage_sql, lineage_params = ingestion.build_lineage_statement(
        "adjustment_factor",
        record,
        batch_id="batch-adjust",
    )
    job_sql, job_params = ingestion.build_etl_job_log_statement(
        table_name="adjustment_factor",
        provider="openbb:yfinance",
        batch_id="batch-adjust",
        status="success",
        records=[record],
    )

    assert "INSERT INTO data_lineage" in lineage_sql
    assert "ON CONFLICT (record_id) DO NOTHING" in lineage_sql
    assert lineage_params["entity_record_id"] == record["record_id"]
    assert "INSERT INTO etl_job_log" in job_sql
    assert "ON CONFLICT (batch_id) DO UPDATE" in job_sql
    assert job_params["rows_read"] == 1
    assert record["record_id"] in job_params["lineage"]


@pytest.mark.asyncio
async def test_ingest_records_dry_run_validates_without_database():
    rows, meta, errors = await ingestion.ingest_records(
        "fundamental_report",
        [
            {
                "symbol": "MSFT",
                "report_type": "balance_sheet",
                "fiscal_period": "2026Q1",
                "report_date": "2026-04-15",
            }
        ],
        provider="openbb:yfinance",
        dry_run=True,
    )

    assert errors == []
    assert meta["status"] == "validated"
    assert meta["write_mode"] == "transactional bulk upsert"
    assert meta["pit_rule"] == "available_time <= as_of_time"
    assert rows[0]["symbol"] == "MSFT"
