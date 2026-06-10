from datetime import datetime, timezone

import pandas as pd
import pytest

from app.services import openbb_financial_adapter as adapter


def test_normalize_fundamental_records_preserves_pit_and_metrics():
    df = pd.DataFrame(
        [
            {
                "period_ending": "2026-03-31",
                "fiscal_year": 2026,
                "revenue": 123.45,
                "net_income": 12.3,
                "reported_currency": "USD",
            }
        ]
    )
    fetched_at = datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc)

    rows = adapter.normalize_fundamental_records(
        "AAPL",
        "income",
        df,
        provider="openbb:yfinance",
        fetched_at=fetched_at,
    )

    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["report_type"] == "income_statement"
    assert rows[0]["fiscal_year"] == 2026
    assert rows[0]["available_time"] == fetched_at
    assert rows[0]["metrics"]["revenue"] == 123.45
    assert rows[0]["lineage"]["adapter"] == adapter.OPENBB_FINANCIAL_ADAPTER_VERSION


def test_normalize_dividends_and_splits_build_corporate_actions_and_adjustments():
    fetched_at = datetime(2026, 4, 15, tzinfo=timezone.utc)
    dividend_df = pd.DataFrame([{"ex_dividend_date": "2026-02-01", "amount": 0.25, "currency": "USD"}])
    split_df = pd.DataFrame(
        [
            {"date": "2026-03-01", "split_ratio": "4:1"},
            {"date": "2026-04-01", "split_ratio": "1:10"},
        ]
    )

    dividends = adapter.normalize_dividend_actions("AAPL", dividend_df, provider="openbb:yfinance", fetched_at=fetched_at)
    splits = adapter.normalize_split_actions("AAPL", split_df, provider="openbb:yfinance", fetched_at=fetched_at)
    adjustments = adapter.normalize_adjustment_factors_from_splits("AAPL", split_df, provider="openbb:yfinance", fetched_at=fetched_at)

    assert dividends[0]["action_type"] == "dividend"
    assert dividends[0]["cash_amount"] == 0.25
    assert splits[0]["action_type"] == "split"
    assert splits[0]["factor"] == pytest.approx(0.25)
    assert adjustments[0]["factor_type"] == "split"
    assert adjustments[0]["factor"] == pytest.approx(0.25)
    assert adjustments[1]["factor"] == pytest.approx(10.0)
    assert adjustments[1]["cumulative_factor"] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_refresh_financial_data_uses_local_ingest_after_provider_fetch(monkeypatch):
    async def fake_fetch(symbol, *, tables=None, provider="yfinance", source_version="openbb-sdk", period="annual", limit=20):
        return (
            {
                "fundamental_report": [
                    {
                        "symbol": symbol,
                        "report_type": "income_statement",
                        "fiscal_period": "2026-FY",
                        "report_date": "2026-04-15",
                    }
                ]
            },
            {
                "adapter_version": adapter.OPENBB_FINANCIAL_ADAPTER_VERSION,
                "record_counts": {"fundamental_report": 1},
                "external_fetch_performed": True,
            },
            [],
        )

    calls = []

    async def fake_ingest(table_name, records, **kwargs):
        calls.append((table_name, records, kwargs))
        return records, {"status": "validated", "dry_run": kwargs.get("dry_run"), "table": table_name}, []

    monkeypatch.setattr(adapter, "fetch_openbb_financial_records", fake_fetch)
    monkeypatch.setattr(adapter, "ingest_records", fake_ingest)

    results, meta, errors = await adapter.refresh_openbb_financial_data(
        ["aapl"],
        tables=["fundamental_report"],
        dry_run=True,
    )

    assert errors == []
    assert meta["external_fetch_performed"] is True
    assert meta["local_ingest_performed"] is False
    assert meta["agent_input_policy"] == "local_storage_only"
    assert meta["pit_rule"] == "available_time <= as_of_time"
    assert calls[0][0] == "fundamental_report"
    assert calls[0][2]["dry_run"] is True
    assert results[0]["status"] == "validated"
