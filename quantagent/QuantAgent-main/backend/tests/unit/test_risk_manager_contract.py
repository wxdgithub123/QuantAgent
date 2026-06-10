import pytest

from app.services.risk_manager import RiskManager


@pytest.mark.asyncio
async def test_check_order_blocks_below_min_order_notional(monkeypatch):
    manager = RiskManager()

    async def fake_config():
        return {
            "MIN_ORDER_NOTIONAL": 25.0,
            "RISK_FAILURE_ACTION": "reduce",
            "FORBIDDEN_SYMBOLS": [],
        }

    monkeypatch.setattr(manager, "get_config", fake_config)

    result = await manager.check_order(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        price=1000.0,
        current_balance=100000.0,
        current_positions={},
        total_portfolio_value=100000.0,
        market_price=1000.0,
    )

    assert result.allowed is False
    assert result.rule == "MIN_ORDER_NOTIONAL"
    assert result.action == "reduce"


@pytest.mark.asyncio
async def test_preview_order_rules_exposes_prd_failure_and_wait_contract(monkeypatch):
    manager = RiskManager()

    async def fake_config():
        return {
            "MAX_SINGLE_POSITION_PCT": 0.2,
            "MAX_TOTAL_EXPOSURE_PCT": 1.0,
            "MAX_TOTAL_DRAWDOWN_PCT": 0.15,
            "MAX_DAILY_LOSS_PCT": 0.05,
            "MIN_ORDER_NOTIONAL": 25.0,
            "RISK_FAILURE_ACTION": "warn",
            "WAIT_ORDER_INTENT_POLICY": "skip",
            "FORBIDDEN_SYMBOLS": [],
        }

    async def fake_peak(value):
        return value

    async def fake_daily_pnl():
        return 0.0

    async def fake_redis_get(key):
        return None

    monkeypatch.setattr(manager, "get_config", fake_config)
    monkeypatch.setattr(manager, "_get_peak_balance", fake_peak)
    monkeypatch.setattr(manager, "_get_today_realized_pnl", fake_daily_pnl)
    monkeypatch.setattr("app.services.risk_manager.redis_get", fake_redis_get)

    rows = await manager.preview_order_rules(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        price=1000.0,
        current_balance=100000.0,
        current_positions={},
        total_portfolio_value=100000.0,
    )

    by_rule = {row["ruleName"]: row for row in rows}
    assert by_rule["最小订单金额"]["passed"] is False
    assert by_rule["WAIT 处理策略"]["currentValue"] == "skip"
    assert by_rule["失败动作"]["currentValue"] == "warn"


@pytest.mark.asyncio
async def test_risk_status_exposes_prd_order_wait_and_failure_rules(monkeypatch):
    manager = RiskManager()

    async def fake_config():
        return {
            "MAX_SINGLE_POSITION_PCT": 0.2,
            "MAX_TOTAL_EXPOSURE_PCT": 1.0,
            "MAX_TOTAL_DRAWDOWN_PCT": 0.15,
            "MAX_DAILY_LOSS_PCT": 0.05,
            "MIN_ORDER_NOTIONAL": 25.0,
            "RISK_FAILURE_ACTION": "warn",
            "WAIT_ORDER_INTENT_POLICY": "skip",
            "FORBIDDEN_SYMBOLS": [],
        }

    async def fake_peak(value):
        return value

    async def fake_daily_pnl():
        return 0.0

    async def fake_redis_get(key):
        return None

    monkeypatch.setattr(manager, "get_config", fake_config)
    monkeypatch.setattr(manager, "_get_peak_balance", fake_peak)
    monkeypatch.setattr(manager, "_get_today_realized_pnl", fake_daily_pnl)
    monkeypatch.setattr("app.services.risk_manager.redis_get", fake_redis_get)

    status = await manager.get_risk_status(100000.0, positions=[])
    by_rule = {row["ruleName"]: row for row in status["checked_rules"]}

    assert by_rule["最小订单金额"]["limitValue"] == 25.0
    assert by_rule["WAIT 处理策略"]["currentValue"] == "skip"
    assert by_rule["失败动作"]["currentValue"] == "warn"
