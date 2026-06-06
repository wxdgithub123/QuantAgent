from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.order_intent_service import OrderIntentService


def make_decision(**overrides):
    base = {
        "id": 101,
        "symbol": "BTCUSDT",
        "timestamp": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "final_signal": "WAIT",
        "confidence": 0.65,
        "risk_veto": False,
        "summary": "受控测试决策",
        "agent_signals": [],
        "input_snapshot_ids": {"factor_snapshot_ids": [1], "signal_event_ids": [2]},
        "role_opinions": [{"role": "technical", "opinion": "neutral"}],
        "position_advice": {},
        "risk_notes": "",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_wait_decision_generates_no_action(monkeypatch):
    service = OrderIntentService()

    async def fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_audit", fake_audit)

    result = await service._preview(
        make_decision(),
        service._build_intent(make_decision(), exchange_id="okx", position_pct=None),
        "okx",
    )

    assert result["status"] == "NO_ACTION"
    assert result["intent"]["side"] is None
    assert result["intent"]["position_pct"] == 0.0


def test_trade_intent_has_stable_id_and_capped_size():
    service = OrderIntentService()
    decision = make_decision(final_signal="BUY", confidence=0.9, position_advice={"suggested_position_pct": 25})

    first = service._build_intent(decision, exchange_id="okx", position_pct=None)
    second = service._build_intent(decision, exchange_id="okx", position_pct=None)

    assert first.side == "BUY"
    assert first.direction == "long"
    assert first.position_pct == 0.10
    assert first.intent_id == second.intent_id == "OI-101-okx-1000"


def test_low_confidence_trade_signal_is_no_action():
    service = OrderIntentService()
    decision = make_decision(final_signal="BUY", confidence=0.54)

    intent = service._build_intent(decision, exchange_id="okx", position_pct=None)

    assert intent.side is None
    assert intent.status == "NO_ACTION"
    assert intent.position_pct == 0.0


@pytest.mark.asyncio
async def test_buy_decision_executes_paper_order_once(monkeypatch):
    service = OrderIntentService()
    decision = make_decision(final_signal="BUY", confidence=0.8, position_advice={"position_pct": 0.05})
    calls = []

    async def fake_load_decision(decision_id):
        return decision

    monkeypatch.setattr(service, "_load_decision", fake_load_decision)

    async def fake_get_price(symbol, exchange_id):
        return 50000.0

    async def fake_calculate_quantity(intent, price):
        return {
            "total_equity": 100000.0,
            "target_notional": 5000.0,
            "quantity": 0.1,
            "position_pct": intent.position_pct,
        }

    async def fake_risk_preview(intent, price, quantity):
        return {
            "allowed": True,
            "rule": None,
            "reason": "",
            "checked_at": "2026-06-01T00:00:00+00:00",
        }

    async def fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_get_price", fake_get_price)
    monkeypatch.setattr(service, "_calculate_quantity", fake_calculate_quantity)
    monkeypatch.setattr(service, "_risk_preview", fake_risk_preview)
    monkeypatch.setattr(service, "_audit", fake_audit)

    async def fake_create_order(**kwargs):
        calls.append(kwargs)
        return {"order_id": "PT-999", "status": "FILLED", "duplicate": len(calls) > 1}

    paper = SimpleNamespace(create_order=fake_create_order)
    monkeypatch.setattr("app.services.order_intent_service.paper_trading_service", paper)

    first = await service.execute_from_decision(101, exchange_id="okx")
    second = await service.execute_from_decision(101, exchange_id="okx")

    assert first["status"] == "FILLED"
    assert first["order_id"] == "PT-999"
    assert second["message"] == "该 OrderIntent 已执行过，本次没有重复下单。"
    assert calls[0]["client_order_id"] == "OI-101-okx-0500"
    assert calls[1]["client_order_id"] == "OI-101-okx-0500"
    assert calls[0]["mode"] == "paper"
    assert calls[0]["exchange_id"] == "okx"
