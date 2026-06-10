from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.market import _pit_bar_check
from app.services.analysis_context_builder import AnalysisContextBuilder


@pytest.mark.asyncio
async def test_load_bars_uses_local_only_gateway_and_filters_future_available_time(monkeypatch):
    captured = {}
    cutoff = datetime(2026, 6, 1, 10, tzinfo=timezone.utc)

    async def fake_get_klines(symbol, **kwargs):
        captured["symbol"] = symbol
        captured.update(kwargs)
        return [
            SimpleNamespace(
                timestamp=datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
                close_time=datetime(2026, 6, 1, 9, 59, tzinfo=timezone.utc),
                open=100,
                high=101,
                low=99,
                close=100.5,
                volume=10,
            ),
            SimpleNamespace(
                timestamp=datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
                close_time=datetime(2026, 6, 1, 10, 1, tzinfo=timezone.utc),
                open=101,
                high=102,
                low=100,
                close=101.5,
                volume=11,
            ),
        ]

    monkeypatch.setattr(
        "app.services.analysis_context_builder.market_data_gateway.get_klines",
        fake_get_klines,
    )

    rows = await AnalysisContextBuilder()._load_bars("BTCUSDT", "1h", cutoff, 10)

    assert captured["symbol"] == "BTCUSDT"
    assert captured["end_time"] == cutoff
    assert captured["allow_external_fallback"] is False
    assert captured["allow_ccxt_fallback"] is False
    assert captured["allow_binance_fallback"] is False
    assert len(rows) == 1
    assert rows[0]["available_time"].startswith("2026-06-01T09:59:00")
    assert rows[0]["provider"] == "market_data_gateway:local_storage"


def test_bar_meta_records_agent_local_only_policy():
    builder = AnalysisContextBuilder()

    meta = builder._build_bar_meta(
        [
            {
                "event_time": "2026-06-01T09:00:00",
                "available_time": "2026-06-01T09:59:00",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
                "volume": 10,
                "provider": "market_data_gateway:local_storage",
            }
        ],
        "1h",
    )

    assert meta["agent_input_policy"] == "local_storage_only"
    assert meta["external_fallback_allowed"] is False
    assert meta["ohlc_digest"].startswith("sha256:")


@pytest.mark.asyncio
async def test_build_with_zero_limits_skips_non_bar_storage(monkeypatch):
    builder = AnalysisContextBuilder()
    called = {"bars": 0, "factors": 0, "signals": 0, "news": 0, "macro": 0}

    async def fake_load_bars(*args, **kwargs):
        called["bars"] += 1
        return []

    async def fail_load_factors(*args, **kwargs):
        called["factors"] += 1
        raise AssertionError("factor storage should be skipped")

    async def fail_load_signals(*args, **kwargs):
        called["signals"] += 1
        raise AssertionError("signal storage should be skipped")

    def fail_load_news(*args, **kwargs):
        called["news"] += 1
        raise AssertionError("news storage should be skipped")

    def fail_load_macro(*args, **kwargs):
        called["macro"] += 1
        raise AssertionError("macro storage should be skipped")

    monkeypatch.setattr(builder, "_load_bars", fake_load_bars)
    monkeypatch.setattr(builder, "_load_factors", fail_load_factors)
    monkeypatch.setattr(builder, "_load_signals", fail_load_signals)
    monkeypatch.setattr(builder, "_load_news", fail_load_news)
    monkeypatch.setattr(builder, "_load_macro", fail_load_macro)

    context = await builder.build(
        "BTCUSDT",
        "1h",
        datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
        factor_limit=0,
        signal_limit=0,
        news_limit=0,
        macro_limit=0,
    )

    assert context.bars == []
    assert called == {"bars": 1, "factors": 0, "signals": 0, "news": 0, "macro": 0}


def test_pit_bar_check_reports_future_bar_violation():
    result = _pit_bar_check(
        [
            {
                "event_time": "2026-06-01T10:00:00+00:00",
                "available_time": "2026-06-01T10:01:00+00:00",
            }
        ],
        "2026-06-01T10:00:00+00:00",
    )

    assert result["passed"] is False
    assert result["violationCount"] == 1
    assert result["violations"][0]["dataType"] == "bar"
    assert result["externalFallbackAllowed"] is False
