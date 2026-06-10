from datetime import datetime, timezone

from app.services import paper_trading_workbench as workbench


def test_summarize_order_intent_event_extracts_chain_identity():
    event = {
        "id": 77,
        "action": "RISK_BLOCKED",
        "resource": "BTCUSDT",
        "details": {
            "intent": {
                "id": "OI-101-okx-0500",
                "symbol": "BTCUSDT",
                "side": "long",
                "positionRatio": 0.05,
                "sourceDecisionId": 101,
            },
            "risk_preview": {
                "passed": False,
                "rule": "MAX_SINGLE_POSITION",
                "reason": "单笔仓位超过上限",
                "checkedRules": [{"ruleName": "MAX_SINGLE_POSITION", "passed": False}],
            },
        },
        "created_at": datetime(2026, 6, 10, tzinfo=timezone.utc),
    }

    row = workbench.summarize_order_intent_event(event)

    assert row["audit_id"] == 77
    assert row["stage"] == "blocked"
    assert row["status"] == "BLOCKED"
    assert row["orderIntentId"] == "OI-101-okx-0500"
    assert row["decisionId"] == 101
    assert row["risk"]["passed"] is False
    assert row["risk"]["rule"] == "MAX_SINGLE_POSITION"
    assert row["links"]["audit"] == "/audit?audit_id=77"
    assert row["links"]["order_intent"] == "/audit?order_intent_id=OI-101-okx-0500"


def test_summarize_blocked_event_prefers_event_status_over_stale_intent_status():
    row = workbench.summarize_order_intent_event(
        {
            "id": 78,
            "action": "RISK_BLOCKED",
            "resource": "BTCUSDT",
            "details": {
                "status": "BLOCKED",
                "intent": {
                    "id": "OI-MANUAL-1",
                    "symbol": "BTCUSDT",
                    "status": "CREATED",
                },
                "risk_preview": {
                    "passed": False,
                    "rule": "MIN_ORDER_NOTIONAL",
                    "reason": "订单名义金额低于最小订单金额",
                },
            },
        }
    )

    assert row["status"] == "BLOCKED"
    assert row["risk"]["rule"] == "MIN_ORDER_NOTIONAL"
    assert row["execution"]["orderId"] is None


def test_build_execution_chain_counts_prd_lifecycle():
    events = [
        {"action": "ORDER_INTENT_CREATED", "stage": "created"},
        {"action": "RISK_CHECK_PASSED", "stage": "risk_checked"},
        {"action": "PAPER_ORDER_FILLED", "stage": "filled"},
        {"action": "RISK_BLOCKED", "stage": "blocked"},
    ]

    chain = workbench.build_execution_chain(events)

    assert chain["schema_version"] == "paper_execution_chain.v1"
    assert chain["chain"] == ["OrderIntent", "RiskGuard", "PaperOrder", "PnL", "AuditRecord"]
    assert chain["counts"]["created"] == 1
    assert chain["counts"]["risk_checked"] == 1
    assert chain["counts"]["filled"] == 1
    assert chain["counts"]["blocked"] == 1
    assert chain["closed_loop_ready"] is True


def test_build_execution_chain_dedupes_duplicate_fill_audit_rows():
    events = [
        {
            "action": "PAPER_ORDER_FILLED",
            "stage": "filled",
            "orderIntentId": "OI-MANUAL-1",
            "orderId": "PT-13",
        },
        {
            "action": "PAPER_ORDER_FILLED",
            "stage": "filled",
            "orderIntentId": "OI-MANUAL-1",
            "orderId": "PT-13",
        },
        {
            "action": "ORDER_INTENT_EXECUTION_LINKED",
            "stage": "execution_linked",
            "orderIntentId": "OI-MANUAL-1",
            "orderId": "PT-13",
        },
    ]

    chain = workbench.build_execution_chain(events)

    assert chain["counts"]["filled"] == 1
    assert chain["counts"]["execution_linked"] == 1
    assert chain["counts"]["raw_audit_events"] == 3
    assert chain["counts"]["deduped_audit_events"] == 1
    assert chain["dedupe_rule"] == "action + orderIntentId + orderId"


def test_account_and_order_summaries_are_frontend_ready():
    balance = {"total_balance": 100000, "available_balance": 95000}
    positions = [
        {"symbol": "BTCUSDT", "quantity": 0.1, "mark_price": 50000, "pnl": 120},
        {"symbol": "ETHUSDT", "quantity": -1, "markPrice": 2500, "unrealizedPnl": -40},
    ]
    orders = [
        {"pnl": 100, "fee": 2.5, "slippage": 0.0001},
        {"realizedPnl": -30, "fee": 1.5, "slippage": -0.0002},
    ]

    account = workbench.build_account_summary(balance, positions)
    order_summary = workbench._orders_summary(orders)

    assert account["available_balance"] == 95000
    assert account["position_value"] == 7500
    assert account["total_equity"] == 102500
    assert account["open_positions"] == 2
    assert account["unrealized_pnl"] == 80
    assert order_summary["order_count"] == 2
    assert order_summary["realized_pnl"] == 70
    assert order_summary["total_fee"] == 4
    assert order_summary["total_abs_slippage"] == 0.0003
