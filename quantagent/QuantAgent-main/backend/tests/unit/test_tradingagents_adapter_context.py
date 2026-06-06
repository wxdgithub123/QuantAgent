from app.agents.tradingagents_adapter import TradingAgentsAdapter


def _bar(i: int, padding: str = ""):
    return {
        "event_time": f"2026-06-01T{i:02d}:00:00",
        "available_time": f"2026-06-01T{i:02d}:59:59",
        "open": 100 + i,
        "high": 101 + i,
        "low": 99 + i,
        "close": 100.5 + i,
        "volume": 10 + i,
        "provider": "market_data_gateway",
        "padding": padding,
    }


def test_compact_analysis_context_preserves_decision_evidence():
    ctx = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "as_of_time": "2026-06-01T00:00:00",
        "schema_version": "analysis_context.v1",
        "bars": [_bar(i) for i in range(160)],
        "latest_factors": {"rsi_14": 42.0, "macd": 0.12},
        "recent_signals": [
            {"id": 1, "signal_type": "BUY", "confidence": 0.8, "source_strategy": "ma"},
            {"id": 2, "signal_type": "WAIT", "confidence": 0.6, "source_strategy": "rsi"},
        ],
        "news_events": [
            {"raw_payload_id": f"n{i}", "title": "market update", "summary": "x" * 1000}
            for i in range(40)
        ],
        "macro_events": [
            {"indicator": f"macro_{i}", "value": i, "event_time": "2026-06-01"}
            for i in range(35)
        ],
        "input_snapshot_ids": {
            "factor_snapshot_ids": [10, 11],
            "signal_event_ids": [20, 21],
            "bar_meta": [{"bars_count": 160, "ohlc_digest": "sha256:abc"}],
        },
        "data_versions": {"factors": {"rsi_14": {"schema_version": "factor.v1"}}},
        "context_hash": "sha256:builderhash",
        "metadata": {"context_hash": "sha256:builderhash"},
    }

    compact = TradingAgentsAdapter._compact_analysis_context(ctx, symbol="BTCUSDT", interval="1h")

    assert compact["context_hash"] == "sha256:builderhash"
    assert len(compact["bars"]) == 120
    assert compact["bars"][0]["event_time"] == "2026-06-01T40:00:00"
    assert compact["latest_factors"] == ctx["latest_factors"]
    assert compact["recent_signals"] == ctx["recent_signals"]
    assert compact["input_snapshot_ids"] == ctx["input_snapshot_ids"]
    assert compact["data_versions"] == ctx["data_versions"]
    assert len(compact["news_events"]) == 30
    assert len(compact["macro_events"]) == 30
    assert compact["backend_api_url"] == "http://backend:8000"


def test_compact_analysis_context_trims_only_high_cardinality_collections():
    ctx = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "as_of_time": "2026-06-01T00:00:00",
        "bars": [_bar(i, padding="x" * 600) for i in range(140)],
        "latest_factors": {"rsi_14": 42.0, "atr_14": 12.5},
        "recent_signals": [{"id": 1, "signal_type": "BUY", "confidence": 0.8}],
        "news_events": [{"raw_payload_id": f"n{i}", "summary": "y" * 900} for i in range(40)],
        "macro_events": [{"indicator": f"m{i}", "summary": "z" * 900} for i in range(40)],
        "input_snapshot_ids": {"factor_snapshot_ids": [1], "signal_event_ids": [2]},
        "data_versions": {"signals": {"2": {"schema_version": "signal.v1"}}},
    }

    compact = TradingAgentsAdapter._compact_analysis_context(
        ctx,
        symbol="BTCUSDT",
        interval="1h",
        max_payload_bytes=8_000,
    )

    assert len(compact["bars"]) <= 20
    assert len(compact["news_events"]) <= 5
    assert len(compact["macro_events"]) <= 5
    assert compact["latest_factors"] == ctx["latest_factors"]
    assert compact["recent_signals"] == ctx["recent_signals"]
    assert compact["input_snapshot_ids"] == ctx["input_snapshot_ids"]
    assert compact["data_versions"] == ctx["data_versions"]
    assert compact["context_hash"].startswith("sha256:")
