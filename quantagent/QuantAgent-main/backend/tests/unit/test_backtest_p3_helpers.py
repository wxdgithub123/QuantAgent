import asyncio
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.api.v1.endpoints import strategy as strategy_module
from app.api.v1.endpoints.strategy import (
    EXECUTION_MODE_AGENT_AUDITED,
    EXECUTION_MODE_RULE_ONLY,
    _agent_action_to_order_action,
    _build_order_intent_payload,
    _build_drawdown_curve,
    _build_pit_check,
    _clamp_max_agent_calls,
    _normalize_backtest_trade,
    _normalize_execution_mode,
    _task_public_view,
    _risk_result_from_rows,
    _build_backtest_risk_rows,
)


def test_pit_check_detects_available_time_after_as_of_time():
    pit = {
        "as_of_time": "2026-06-01T10:00:00+00:00",
        "actual_start_time": "2026-06-01T00:00:00+00:00",
        "actual_end_time": "2026-06-01T09:00:00+00:00",
    }
    records = [
        {
            "id": "future-factor-1",
            "dataType": "factor",
            "asOfTime": "2026-06-01T10:00:00+00:00",
            "availableTime": "2026-06-01T10:05:00+00:00",
        }
    ]

    result = _build_pit_check(pit, records)

    assert result["passed"] is False
    assert result["violationCount"] == 1
    assert result["violations"][0]["recordId"] == "future-factor-1"
    assert result["rule"] == "available_time <= as_of_time"


def test_pit_check_passes_when_records_are_point_in_time_safe():
    result = _build_pit_check(
        {"as_of_time": datetime(2026, 6, 1, 10, tzinfo=timezone.utc)},
        [
            {
                "id": "safe-news-1",
                "dataType": "news",
                "asOfTime": "2026-06-01T10:00:00+00:00",
                "availableTime": "2026-06-01T09:59:00+00:00",
            }
        ],
    )

    assert result["passed"] is True
    assert result["violationCount"] == 0
    assert result["violations"] == []


def test_drawdown_curve_uses_running_peak():
    curve = [
        {"t": "t1", "v": 100.0},
        {"t": "t2", "v": 120.0},
        {"t": "t3", "v": 90.0},
    ]

    drawdown = _build_drawdown_curve(curve)

    assert drawdown == [
        {"t": "t1", "v": 0.0},
        {"t": "t2", "v": 0.0},
        {"t": "t3", "v": -25.0},
    ]


def test_normalize_backtest_trade_adds_links_and_related_audits():
    trade = {
        "entry_time": "2026-06-01T01:00:00",
        "exit_time": "2026-06-01T02:00:00",
        "entry_price": 100.0,
        "exit_price": 110.0,
        "quantity": 2,
        "pnl": 20.0,
        "pnl_pct": 10.0,
    }

    normalized = _normalize_backtest_trade(
        trade,
        index=0,
        backtest_id=42,
        symbol="BTCUSDT",
        audit_ids=[7, 8],
        linked_replay_id="replay-1",
    )

    assert normalized["tradeId"] == "BT-42-1"
    assert normalized["symbol"] == "BTCUSDT"
    assert normalized["realizedPnl"] == 20.0
    assert normalized["relatedAuditIds"] == [7, 8]
    assert normalized["replayUrl"].startswith("/replay?session_id=replay-1")
    assert normalized["auditUrl"] == "/audit?backtest_id=42"


def test_execution_mode_normalization_keeps_rule_only_fast_mode_default():
    assert _normalize_execution_mode(None) == EXECUTION_MODE_RULE_ONLY
    assert _normalize_execution_mode("rule_only") == EXECUTION_MODE_RULE_ONLY
    assert _normalize_execution_mode("agent_audited") == EXECUTION_MODE_AGENT_AUDITED
    assert _normalize_execution_mode("audited") == EXECUTION_MODE_AGENT_AUDITED


def test_max_agent_calls_is_clamped_for_performance_guard():
    assert _clamp_max_agent_calls(-10) == 0
    assert _clamp_max_agent_calls("7") == 7
    assert _clamp_max_agent_calls(999) == 20


def test_agent_audited_payloads_have_intent_and_risk_shapes():
    intent = _build_order_intent_payload(
        intent_id="OI-BT-1-1-test",
        symbol="BTCUSDT",
        action="BUY",
        quantity=1.5,
        price=100.0,
        confidence=0.8,
        source_decision_id=99,
        as_of_time=datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
        initial_capital=10000.0,
    )
    risk_result = _risk_result_from_rows(
        [
            {"ruleName": "single position", "passed": True},
            {"ruleName": "forbidden symbol", "passed": True},
        ]
    )

    assert intent["sourceDecisionId"] == 99
    assert intent["status"] == "CREATED"
    assert intent["executionMode"] == EXECUTION_MODE_AGENT_AUDITED
    assert risk_result["passed"] is True
    assert risk_result["blockedReason"] is None


def test_agent_audited_order_action_uses_agent_final_signal():
    assert _agent_action_to_order_action("BUY") == "BUY"
    assert _agent_action_to_order_action("LONG_REVERSAL") == "BUY"
    assert _agent_action_to_order_action("SELL") == "SELL"
    assert _agent_action_to_order_action("SHORT_REVERSAL") == "SELL"
    assert _agent_action_to_order_action("WAIT") == "WAIT"
    assert _agent_action_to_order_action("HOLD") == "HOLD"
    assert _agent_action_to_order_action("UNKNOWN") == "WAIT"


def test_risk_result_records_blocked_rule_without_generating_order_assumption():
    result = _risk_result_from_rows(
        [
            {"ruleName": "single position", "passed": True},
            {"ruleName": "forbidden symbol", "passed": False, "message": "blocked"},
        ]
    )

    assert result["passed"] is False
    assert result["blockedReason"] == "blocked"
    assert len(result["checkedRules"]) == 2


def test_risk_result_marks_unavailable_as_not_passed():
    result = _risk_result_from_rows(
        [
            {
                "ruleName": "RiskGuard unavailable",
                "passed": False,
                "unavailable": True,
                "message": "RiskGuard preview was unavailable",
            }
        ]
    )

    assert result["passed"] is False
    assert result["riskUnavailable"] is True
    assert result["blockedReason"] == "RiskGuard preview was unavailable"


async def _fake_risk_config():
    return {
        "MAX_SINGLE_POSITION_PCT": 0.20,
        "MAX_TOTAL_EXPOSURE_PCT": 1.00,
        "MAX_TOTAL_DRAWDOWN_PCT": 0.15,
        "MAX_DAILY_LOSS_PCT": 0.05,
        "FORBIDDEN_SYMBOLS": [],
        "MIN_ORDER_NOTIONAL": 25.0,
        "WAIT_ORDER_INTENT_POLICY": "skip",
        "RISK_FAILURE_ACTION": "warn",
    }


def _row_by_name(rows):
    return {row["ruleName"]: row for row in rows}


def test_backtest_risk_rows_include_min_notional_wait_and_failure_action(monkeypatch):
    async def run():
        rows = await _build_backtest_risk_rows(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.001,
            price=1000.0,
            initial_capital=10000.0,
            portfolio_value=10000.0,
        )
        return _row_by_name(rows)

    monkeypatch.setattr("app.api.v1.endpoints.strategy.risk_manager.get_config", _fake_risk_config)

    by_rule = asyncio.run(run())

    assert by_rule["Minimum order notional"]["passed"] is False
    assert by_rule["WAIT order intent policy"]["currentValue"] == "skip"
    assert by_rule["Risk failure action"]["currentValue"] == "warn"


def test_backtest_task_public_view_hides_internal_retry_payloads():
    public = _task_public_view(
        {
            "task_id": "bt-1",
            "status": "queued",
            "request": object(),
            "param_combinations": [{"fast": 5}],
            "storage": "PostgreSQL backtest_results + DuckDB backtest_results archive",
            "result_storage": {"archive": "DuckDB data/backtest/backtest_results.duckdb"},
            "cancel_supported": True,
            "retry_supported": True,
        }
    )

    assert public["task_id"] == "bt-1"
    assert public["cancel_supported"] is True
    assert public["retry_supported"] is True
    assert public["result_storage"]["archive"].endswith("backtest_results.duckdb")
    assert "request" not in public
    assert "param_combinations" not in public


def test_backtest_detail_endpoint_has_audit_model_import():
    assert strategy_module.AuditLog.__tablename__ == "audit_logs"


@pytest.mark.asyncio
async def test_run_backtest_uses_local_only_market_gateway(monkeypatch):
    index = pd.date_range("2026-05-01", periods=320, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0 + i * 0.1 for i in range(len(index))],
            "high": [101.0 + i * 0.1 for i in range(len(index))],
            "low": [99.0 + i * 0.1 for i in range(len(index))],
            "close": [100.5 + i * 0.1 for i in range(len(index))],
            "volume": [1000.0 for _ in range(len(index))],
        },
        index=index,
    )
    gateway_calls = []

    async def fake_get_dataframe(*args, **kwargs):
        gateway_calls.append({"args": args, "kwargs": kwargs})
        return df

    class FakeBacktester:
        def __init__(self, df, signal_func, initial_capital):
            self.df = df
            self.initial_capital = initial_capital

        def run(self):
            return {
                "equity_curve": [self.initial_capital for _ in range(len(self.df))],
                "trades": [],
                "total_return": 0.0,
                "annual_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
                "total_commission": 0.0,
                "final_capital": self.initial_capital,
            }

    class FailingDbContext:
        async def __aenter__(self):
            raise RuntimeError("database intentionally unavailable for unit test")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(strategy_module.market_data_gateway, "get_dataframe", fake_get_dataframe)
    monkeypatch.setattr(strategy_module, "EventDrivenBacktester", FakeBacktester)
    monkeypatch.setattr(
        strategy_module,
        "_run_backtest_engine",
        lambda *args, **kwargs: {"equity_curve": [{"t": "2026-05-01T00:00:00", "v": 10000.0}]},
    )
    monkeypatch.setattr(strategy_module, "get_db", lambda: FailingDbContext())

    response = await strategy_module.run_backtest(
        strategy_module.BacktestRequest(
            strategy_type="ma",
            symbol="BTCUSDT",
            interval="1h",
            limit=320,
            initial_capital=10000.0,
            params={"fast_period": 5, "slow_period": 20},
            as_of_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
            executionMode=EXECUTION_MODE_RULE_ONLY,
            maxAgentCalls=0,
        )
    )

    assert gateway_calls
    call_kwargs = gateway_calls[0]["kwargs"]
    assert call_kwargs["allow_external_fallback"] is False
    assert call_kwargs["allow_ccxt_fallback"] is False
    assert call_kwargs["allow_binance_fallback"] is False
    assert response.pit["data_source"] == "market_data_gateway:local_storage"
    assert response.pitCheck["passed"] is True
    assert response.dataRange["barsCount"] == 320
