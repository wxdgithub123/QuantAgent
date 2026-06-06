from datetime import datetime, timezone

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
    _risk_result_from_rows,
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
