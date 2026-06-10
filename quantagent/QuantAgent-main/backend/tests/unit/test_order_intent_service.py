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
    audit_events = []

    async def fake_audit(action, *args, **kwargs):
        audit_events.append(action)
        return None

    monkeypatch.setattr(service, "_audit", fake_audit)

    result = await service._preview(
        make_decision(),
        service._build_intent(make_decision(), exchange_id="okx", position_pct=None),
        "okx",
    )

    assert result["status"] == "NO_ACTION"
    assert result["intent"]["action"] == "HOLD"
    assert result["intent"]["side"] == "flat"
    assert result["intent"]["positionRatio"] == 0.0
    assert result["intent"]["position_pct"] == 0.0
    assert audit_events == ["HOLD_RECORDED"]


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
async def test_draft_intent_from_decision_skips_realtime_dependencies(monkeypatch):
    service = OrderIntentService()
    decision = make_decision(final_signal="BUY", confidence=0.8, position_advice={"position_pct": 0.05})
    audit_events = []

    async def fake_load_decision(decision_id):
        return decision

    async def fail_realtime_dependency(*args, **kwargs):
        raise AssertionError("draft intent must not call realtime execution dependencies")

    async def fake_audit_once(action, intent, details):
        audit_events.append((action, intent.intent_id, details.get("stage")))

    monkeypatch.setattr(service, "_load_decision", fake_load_decision)
    monkeypatch.setattr(service, "_get_price", fail_realtime_dependency)
    monkeypatch.setattr(service, "_calculate_quantity", fail_realtime_dependency)
    monkeypatch.setattr(service, "_risk_preview", fail_realtime_dependency)
    monkeypatch.setattr(service, "_audit_once", fake_audit_once)

    result = await service.draft_intent_from_decision(101, exchange_id="okx")

    assert result["status"] == "READY"
    assert result["draft_only"] is True
    assert result["price"] is None
    assert result["sizing"] is None
    assert result["risk_preview"] is None
    assert result["intent"]["intent_id"] == "OI-101-okx-0500"
    assert audit_events == [("ORDER_INTENT_CREATED", "OI-101-okx-0500", "decision_evidence")]


@pytest.mark.asyncio
async def test_wait_draft_intent_writes_hold_recorded(monkeypatch):
    service = OrderIntentService()
    audit_events = []

    async def fake_load_decision(decision_id):
        return make_decision(final_signal="WAIT", confidence=0.65)

    async def fail_realtime_dependency(*args, **kwargs):
        raise AssertionError("WAIT draft must not call realtime execution dependencies")

    async def fake_audit_once(action, intent, details):
        audit_events.append((action, intent.side, details.get("stage")))

    monkeypatch.setattr(service, "_load_decision", fake_load_decision)
    monkeypatch.setattr(service, "_get_price", fail_realtime_dependency)
    monkeypatch.setattr(service, "_calculate_quantity", fail_realtime_dependency)
    monkeypatch.setattr(service, "_risk_preview", fail_realtime_dependency)
    monkeypatch.setattr(service, "_audit_once", fake_audit_once)

    result = await service.draft_intent_from_decision(101, exchange_id="okx")

    assert result["status"] == "NO_ACTION"
    assert result["intent"]["action"] == "HOLD"
    assert result["intent"]["position_pct"] == 0.0
    assert result["risk_preview"] is None
    assert audit_events == [("HOLD_RECORDED", None, "decision_evidence")]


@pytest.mark.asyncio
async def test_wait_draft_can_skip_order_intent_by_policy(monkeypatch):
    service = OrderIntentService()
    audit_events = []

    async def fake_load_decision(decision_id):
        return make_decision(final_signal="WAIT", confidence=0.65)

    async def fake_policy():
        return "skip"

    async def fake_audit_once(action, intent, details):
        audit_events.append((action, details.get("wait_order_intent_policy"), details.get("generated_order_intent")))

    monkeypatch.setattr(service, "_load_decision", fake_load_decision)
    monkeypatch.setattr(service, "_wait_order_intent_policy", fake_policy)
    monkeypatch.setattr(service, "_audit_once", fake_audit_once)

    result = await service.draft_intent_from_decision(101, exchange_id="okx")

    assert result["status"] == "SKIPPED"
    assert result["intent"]["action"] == "HOLD"
    assert result["wait_order_intent_policy"] == "skip"
    assert result["generated_order_intent"] is False
    assert audit_events == [("HOLD_RECORDED", "skip", False)]


@pytest.mark.asyncio
async def test_buy_decision_executes_paper_order_once(monkeypatch):
    service = OrderIntentService()
    decision = make_decision(final_signal="BUY", confidence=0.8, position_advice={"position_pct": 0.05})
    calls = []
    audit_events = []

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
            "passed": True,
            "rule": None,
            "reason": "",
            "blockedReason": None,
            "checkedRules": [],
            "checked_at": "2026-06-01T00:00:00+00:00",
        }

    async def fake_audit(action, *args, **kwargs):
        audit_events.append(action)
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
    assert audit_events[:3] == ["ORDER_INTENT_CREATED", "RISK_CHECK_PASSED", "ORDER_INTENT_EXECUTION_LINKED"]


@pytest.mark.asyncio
async def test_risk_blocked_decision_writes_risk_blocked(monkeypatch):
    service = OrderIntentService()
    decision = make_decision(final_signal="BUY", confidence=0.8, position_advice={"position_pct": 0.05})
    audit_events = []

    async def fake_load_decision(decision_id):
        return decision

    async def fake_get_price(symbol, exchange_id):
        return 50000.0

    async def fake_calculate_quantity(intent, price):
        return {"total_equity": 100000.0, "target_notional": 5000.0, "quantity": 0.1, "position_pct": intent.position_pct}

    async def fake_risk_preview(intent, price, quantity):
        return {
            "allowed": False,
            "passed": False,
            "rule": "MAX_SINGLE_POSITION",
            "reason": "单笔仓位超过上限",
            "blockedReason": "单笔仓位超过上限",
            "checkedRules": [],
            "checked_at": "2026-06-01T00:00:00+00:00",
        }

    async def fake_audit(action, *args, **kwargs):
        audit_events.append(action)

    async def fake_create_order(**kwargs):
        raise AssertionError("风控拦截后不应进入模拟成交")

    monkeypatch.setattr(service, "_load_decision", fake_load_decision)
    monkeypatch.setattr(service, "_get_price", fake_get_price)
    monkeypatch.setattr(service, "_calculate_quantity", fake_calculate_quantity)
    monkeypatch.setattr(service, "_risk_preview", fake_risk_preview)
    monkeypatch.setattr(service, "_audit", fake_audit)
    monkeypatch.setattr("app.services.order_intent_service.paper_trading_service", SimpleNamespace(create_order=fake_create_order))

    result = await service.execute_from_decision(101, exchange_id="okx")

    assert result["status"] == "BLOCKED"
    assert audit_events == ["ORDER_INTENT_CREATED", "RISK_BLOCKED"]


@pytest.mark.asyncio
async def test_risk_preview_records_failure_action_but_blocks(monkeypatch):
    service = OrderIntentService()
    intent = service._build_intent(make_decision(final_signal="BUY", confidence=0.8), exchange_id="okx", position_pct=0.05)

    async def fake_balance():
        return {"available_balance": 100000.0, "total_balance": 100000.0}

    async def fake_positions(exchange_id="okx"):
        return []

    class FakeRiskResult:
        allowed = False
        rule = "MIN_ORDER_NOTIONAL"
        reason = "too small"
        action = "warn"

    async def fake_preview_order_rules(**kwargs):
        return [{"ruleName": "最小订单金额", "passed": False, "message": "too small"}]

    async def fake_check_order(**kwargs):
        return FakeRiskResult()

    monkeypatch.setattr(
        "app.services.order_intent_service.paper_trading_service",
        SimpleNamespace(get_balance=fake_balance, get_positions=fake_positions),
    )
    monkeypatch.setattr(
        "app.services.risk_manager.risk_manager",
        SimpleNamespace(preview_order_rules=fake_preview_order_rules, check_order=fake_check_order),
    )

    preview = await service._risk_preview(intent, price=100.0, quantity=0.01)

    assert preview["allowed"] is False
    assert preview["failure_action"] == "warn"
    assert preview["effective_failure_action"] == "block"
    assert preview["blockedReason"] == "too small"


@pytest.mark.asyncio
async def test_manual_order_generates_manual_intent_and_audit(monkeypatch):
    service = OrderIntentService()
    audit_events = []
    calls = []

    async def fake_risk_preview(intent, price, quantity):
        return {
            "allowed": True,
            "passed": True,
            "rule": None,
            "reason": "",
            "blockedReason": None,
            "checkedRules": [],
            "checked_at": "2026-06-01T00:00:00+00:00",
        }

    async def fake_audit(action, intent, details):
        audit_events.append((action, intent.source, intent.intent_id, details.get("intent", {}).get("sourceDecisionId")))

    async def fake_create_order(**kwargs):
        calls.append(kwargs)
        return {"order_id": "PT-MANUAL", "status": "FILLED", "source": "manual"}

    monkeypatch.setattr(service, "_risk_preview", fake_risk_preview)
    monkeypatch.setattr(service, "_audit", fake_audit)
    monkeypatch.setattr("app.services.order_intent_service.paper_trading_service", SimpleNamespace(create_order=fake_create_order))

    result = await service.execute_manual_order(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.01,
        price=50000.0,
        exchange_id="okx",
    )

    assert result["status"] == "FILLED"
    assert calls[0]["strategy_id"] == "manual"
    assert calls[0]["client_order_id"].startswith("OI-MANUAL-")
    assert [event[0] for event in audit_events] == ["ORDER_INTENT_CREATED", "RISK_CHECK_PASSED", "ORDER_INTENT_EXECUTION_LINKED"]
    assert all(event[1] == "manual" for event in audit_events)
