from app.api.v1.endpoints.market import _build_signal_panel


def _signal(**overrides):
    base = {
        "id": 1,
        "symbol": "BTCUSDT",
        "event_time": "2026-05-30T00:00:00+00:00",
        "available_time": "2026-05-30T00:00:00+00:00",
        "signal_type": "BUY",
        "signal_value": 1.0,
        "confidence": 0.68,
        "source_strategy": "backtest:ma",
        "strategy_id": "backtest-19",
        "provider": "QuantAgent",
        "data_source": "BACKTEST",
        "factors": {"entryPrice": 73394.47, "exitPrice": 73542.76},
        "extra_data": {"backtestId": 19},
    }
    base.update(overrides)
    return base


def test_duplicate_signals_are_merged_for_same_backtest_key():
    panel = _build_signal_panel(
        [
            _signal(id=101),
            _signal(id=102),
        ],
        symbol="BTCUSDT",
    )

    assert len(panel) == 1
    assert panel[0]["mergedCount"] == 2
    assert panel[0]["mergedSignalIds"] == [101, 102]
    assert panel[0]["relatedBacktestId"] == 19
    assert "backtest:ma" not in panel[0]["triggerReason"]
    assert "均线策略满足买入条件" in panel[0]["triggerReason"]


def test_different_time_strategy_symbol_or_backtest_are_not_merged():
    panel = _build_signal_panel(
        [
            _signal(id=1),
            _signal(id=2, event_time="2026-05-30T01:00:00+00:00"),
            _signal(id=3, source_strategy="backtest:rsi"),
            _signal(id=4, symbol="ETHUSDT"),
            _signal(id=5, strategy_id="backtest-20", extra_data={"backtestId": 20}),
        ],
        symbol="BTCUSDT",
    )

    assert len(panel) == 5
    assert all(item["mergedCount"] == 1 for item in panel)


def test_old_signals_without_backtest_id_can_still_be_merged():
    panel = _build_signal_panel(
        [
            _signal(id=201, strategy_id="", extra_data={}),
            _signal(id=202, strategy_id="", extra_data={}),
        ],
        symbol="BTCUSDT",
    )

    assert len(panel) == 1
    assert panel[0]["mergedCount"] == 2
    assert panel[0]["relatedBacktestId"] is None
