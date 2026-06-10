from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services import data_platform_storage as storage


def test_build_pit_query_is_whitelisted_and_enforces_available_time():
    sql, params = storage.build_pit_query(
        "fundamental_report",
        symbol="btcusdt",
        limit=5000,
        as_of_time=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert "FROM fundamental_report" in sql
    assert "available_time <= :as_of_time" in sql
    assert "ORDER BY available_time DESC, event_time DESC, id DESC" in sql
    assert params["symbol"] == "BTCUSDT"
    assert params["limit"] == 1000
    assert params["as_of_time"].tzinfo == timezone.utc


def test_build_pit_query_rejects_unknown_tables():
    with pytest.raises(ValueError):
        storage.build_pit_query("audit_logs; DROP TABLE audit_logs", symbol="BTCUSDT", limit=1)


def test_adjustment_factor_query_orders_by_effective_time():
    sql, params = storage.build_pit_query(
        "adjustment_factor",
        symbol="AAPL",
        limit=50,
        as_of_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert "FROM adjustment_factor" in sql
    assert "ORDER BY effective_time DESC, available_time DESC, id DESC" in sql
    assert params["symbol"] == "AAPL"
    assert params["limit"] == 50


def test_serialize_storage_record_handles_decimal_dates_and_nested_json():
    record = storage.serialize_storage_record(
        {
            "value": Decimal("12.34"),
            "event_time": datetime(2026, 1, 1, 0, 0, 0),
            "report_date": date(2026, 1, 2),
            "metrics": {"eps": Decimal("1.23"), "dates": [date(2026, 1, 3)]},
        }
    )

    assert record["value"] == 12.34
    assert record["event_time"] == "2026-01-01T00:00:00+00:00"
    assert record["report_date"] == "2026-01-02"
    assert record["metrics"]["eps"] == 1.23
    assert record["metrics"]["dates"] == ["2026-01-03"]
