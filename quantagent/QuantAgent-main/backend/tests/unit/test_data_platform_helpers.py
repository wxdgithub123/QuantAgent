from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import data_platform


def test_data_platform_response_envelope_shape():
    payload = data_platform._response([{"x": 1}], meta={"count": 1})

    assert payload["data"] == [{"x": 1}]
    assert payload["meta"]["schema_version"] == "data_platform_response.v1"
    assert payload["meta"]["count"] == 1
    assert payload["errors"] == []


def test_bar_to_record_keeps_three_time_visibility():
    ts = datetime(2026, 1, 1, 1, 0, 0)
    bar = SimpleNamespace(
        timestamp=ts,
        close_time=ts,
        open=1,
        high=2,
        low=0.5,
        close=1.5,
        volume=100,
        quote_volume=150,
        trades=12,
    )

    record = data_platform._bar_to_record(bar, "BTCUSDT", "1h", provider="local:test")

    assert record["symbol"] == "BTCUSDT"
    assert record["interval"] == "1h"
    assert record["event_time"].startswith("2026-01-01T01:00:00")
    assert record["available_time"].startswith("2026-01-01T01:00:00")
    assert record["provider"] == "local:test"
    assert record["schema_version"] == "bar.v1"
    assert record["id"].startswith("sha256:")


def test_instrument_record_normalizes_crypto_symbol():
    record = data_platform._instrument_record("BTC/USDT")

    assert record["symbol"] == "BTCUSDT"
    assert record["base_asset"] == "BTC"
    assert record["quote_asset"] == "USDT"
    assert record["ccxt_symbol"] == "BTC/USDT"
    assert record["openbb_symbol"] == "BTC-USD"


@pytest.mark.asyncio
async def test_local_ingest_endpoint_dry_run_uses_unified_envelope():
    req = data_platform.LocalIngestRequest(
        table="fundamental_report",
        provider="openbb:yfinance",
        dry_run=True,
        records=[
            {
                "symbol": "AAPL",
                "report_type": "income_statement",
                "fiscal_period": "2026Q1",
                "report_date": "2026-04-15",
            }
        ],
    )

    payload = await data_platform.ingest_local_records(req)

    assert payload["errors"] == []
    assert payload["meta"]["schema_version"] == "data_platform_response.v1"
    assert payload["meta"]["dry_run"] is True
    assert payload["meta"]["external_fetch_performed"] is False
    assert payload["meta"]["agent_input_policy"] == "local_storage_only"
    assert payload["data"][0]["record_id"].startswith("sha256:")


def test_storage_contract_covers_required_phase2_tables_and_pit_fields():
    contract = data_platform.build_storage_contract()
    tables = contract["tables"]

    for table in data_platform.REQUIRED_STORAGE_TABLES:
        assert table in tables

    for table in ["instrument", "bar_1m", "bar_1h", "bar_1d", "quote_latest", "news_event", "macro_indicator"]:
        assert tables[table]["pit_fields"] == ["event_time", "ingest_time", "available_time"]

    assert tables["bar_1m"]["upsert_key"] == ["symbol", "ts", "provider", "source_version"]
    assert tables["adjustment_factor"]["purpose"].startswith("Independent adjustment-factor")
    assert contract["visibility_rule"] == "available_time <= as_of_time"
    assert contract["agent_input_policy"] == "local_storage_only"
    assert contract["scheduler_contract"]["target"] == "Prefect 3"
    assert "backup_pitr" in contract["backup_and_lifecycle"]


def test_data_platform_storage_migration_declares_timescale_and_governance_contract():
    migration = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "017_data_platform_contract_tables.py"
    text = migration.read_text(encoding="utf-8")

    for marker in [
        "CREATE EXTENSION IF NOT EXISTS timescaledb",
        "undefined_file OR insufficient_privilege OR feature_not_supported",
        "create_hypertable",
        "add_compression_policy",
        "available_time TIMESTAMPTZ",
        "CHECK (available_time >= event_time)",
        "CREATE TABLE IF NOT EXISTS instrument",
        'BAR_TABLES = ("bar_1m", "bar_1h", "bar_1d")',
        "CREATE TABLE IF NOT EXISTS {table}",
        "CREATE TABLE IF NOT EXISTS quote_latest",
        "CREATE TABLE IF NOT EXISTS fundamental_report",
        "CREATE TABLE IF NOT EXISTS corporate_action",
        "CREATE TABLE IF NOT EXISTS adjustment_factor",
        "CREATE TABLE IF NOT EXISTS etl_job_log",
        "CREATE TABLE IF NOT EXISTS news_event",
        "CREATE TABLE IF NOT EXISTS macro_indicator",
        "CREATE TABLE IF NOT EXISTS data_lineage",
        "CREATE TABLE IF NOT EXISTS cleaned_data_item",
        "data_platform_storage_policy",
        "postgres_pitr",
        "idx_{table}_symbol_ts",
        "uq_{table}_symbol_ts_provider",
        "raw_payload_hash",
        "cleaning_rule_version",
    ]:
        assert marker in text
