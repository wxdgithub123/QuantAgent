from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

from app.agents.base_agent import SignalType
from app.agents.coordinator_agent import CoordinationResult, CoordinatorAgent


def test_coordination_result_to_dict_includes_audit_identity_fields():
    result = CoordinationResult(
        symbol="BTCUSDT",
        final_signal=SignalType.BUY,
        confidence=0.82,
        summary="test decision",
        decision_id=123,
        context_id="ctx-test",
        context_hash="sha256:abc123",
        audit_url="/audit?decision_id=123",
        order_intent_status="READY",
        order_intent_id="OI-123-okx-0500",
        timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    payload = result.to_dict()

    assert payload["decision_id"] == 123
    assert payload["decisionId"] == 123
    assert payload["context_id"] == "ctx-test"
    assert payload["contextId"] == "ctx-test"
    assert payload["context_hash"] == "sha256:abc123"
    assert payload["contextHash"] == "sha256:abc123"
    assert payload["audit_url"] == "/audit?decision_id=123"
    assert payload["auditUrl"] == "/audit?decision_id=123"
    assert payload["order_intent_status"] == "READY"
    assert payload["orderIntentStatus"] == "READY"
    assert payload["order_intent_id"] == "OI-123-okx-0500"
    assert payload["orderIntentId"] == "OI-123-okx-0500"


@pytest.mark.asyncio
async def test_persist_result_returns_decision_id_and_populates_audit_fields(monkeypatch):
    result = CoordinationResult(
        symbol="BTCUSDT",
        final_signal=SignalType.BUY,
        confidence=0.82,
        summary="test decision",
        input_snapshot_ids={"factor_snapshot_ids": [1], "signal_event_ids": [2]},
        role_opinions=[{"role": "market", "reasoning": "bullish"}],
        position_advice={"position_pct": 0.05},
        timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    ctx = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "as_of_time": "2026-06-01T00:00:00+00:00",
        "context_hash": "sha256:ctxhash",
        "input_snapshot_ids": result.input_snapshot_ids,
        "data_versions": {"signals": {"2": {"schema_version": "signal.v1"}}},
        "latest_factors": {"rsi_14": 42.0},
        "recent_signals": [{"signal_type": "BUY", "source_strategy": "ma", "confidence": 0.8}],
        "bars": [{"close": 100.0}],
        "news_events": [{"id": "n1"}],
        "macro_events": [{"indicator": "cpi"}],
    }
    audit_calls = []
    draft_calls = []

    class FakeExecuteResult:
        def scalar(self):
            return 777

    class FakeSession:
        def __init__(self):
            self.params = None

        async def execute(self, statement, params):
            self.params = params
            return FakeExecuteResult()

    session = FakeSession()

    @asynccontextmanager
    async def fake_get_db():
        yield session

    class FakeAuditService:
        async def log_event(self, **kwargs):
            audit_calls.append(kwargs)

    class FakeOrderIntentService:
        async def draft_intent_from_decision(self, decision_id):
            draft_calls.append(decision_id)
            return {"status": "READY", "intent": {"intent_id": "OI-777-okx-0500"}}

    monkeypatch.setattr("app.agents.coordinator_agent.get_db", fake_get_db)
    monkeypatch.setattr("app.services.audit_service.audit_service", FakeAuditService())
    monkeypatch.setattr("app.services.order_intent_service.order_intent_service", FakeOrderIntentService())

    decision_id = await CoordinatorAgent._persist_result(result, ctx)

    assert decision_id == 777
    assert result.decision_id == 777
    assert result.audit_url == "/audit?decision_id=777"
    assert result.context_hash == "sha256:ctxhash"
    assert result.order_intent_status == "READY"
    assert result.order_intent_id == "OI-777-okx-0500"
    assert session.params["context_hash"] == "sha256:ctxhash"
    assert audit_calls[0]["details"]["decisionId"] == 777
    assert audit_calls[0]["details"]["contextHash"] == "sha256:ctxhash"
    assert audit_calls[0]["details"]["inputSummary"]["factor_snapshot"] == {"rsi_14": 42.0}
    assert draft_calls == [777]


@pytest.mark.asyncio
async def test_coordinate_at_uses_pit_context_and_can_skip_draft(monkeypatch):
    as_of_time = datetime(2026, 6, 1, 10, tzinfo=timezone.utc)
    loaded_calls = []
    adapter_calls = []
    persist_calls = []

    async def fake_load(self, symbol, interval="1h", as_of_time=None):
        loaded_calls.append({"symbol": symbol, "interval": interval, "as_of_time": as_of_time})
        return {
            "symbol": symbol,
            "timeframe": interval,
            "as_of_time": as_of_time.isoformat(),
            "context_hash": "sha256:pit",
            "input_snapshot_ids": {"factor_snapshot_ids": [1]},
            "metadata": {},
        }

    class FakeAdapter:
        async def run_analysis(self, **kwargs):
            adapter_calls.append(kwargs)
            return CoordinationResult(
                symbol=kwargs["symbol"],
                final_signal=SignalType.BUY,
                confidence=0.71,
                summary="pit decision",
                input_snapshot_ids={"adapter_snapshot": "kept"},
                timestamp=datetime(2026, 6, 6, tzinfo=timezone.utc),
            )

    async def fake_persist(result, ctx, *, draft_order_intent=True, audit_metadata=None):
        result.decision_id = 501
        result.audit_url = "/audit?decision_id=501"
        persist_calls.append(
            {
                "result": result,
                "ctx": ctx,
                "draft_order_intent": draft_order_intent,
                "audit_metadata": audit_metadata,
            }
        )
        return 501

    monkeypatch.setattr(CoordinatorAgent, "_load_analysis_context", fake_load)
    monkeypatch.setattr("app.agents.tradingagents_adapter.tradingagents_adapter", FakeAdapter())
    monkeypatch.setattr(CoordinatorAgent, "_persist_result", staticmethod(fake_persist))

    result = await CoordinatorAgent(use_tradingagents=True, fast_mode=True).coordinate_at(
        symbol="btcusdt",
        interval="1h",
        as_of_time=as_of_time,
        extra_input_snapshot_ids={"backtestId": 42},
        audit_metadata={"source": "backtest"},
        draft_order_intent=False,
    )

    assert loaded_calls == [{"symbol": "BTCUSDT", "interval": "1h", "as_of_time": as_of_time}]
    assert adapter_calls[0]["analysis_context"]["input_snapshot_ids"]["backtestId"] == 42
    assert result.timestamp == as_of_time
    assert result.input_snapshot_ids["factor_snapshot_ids"] == [1]
    assert result.input_snapshot_ids["adapter_snapshot"] == "kept"
    assert result.context_hash == "sha256:pit"
    assert result.decision_id == 501
    assert persist_calls[0]["draft_order_intent"] is False
    assert persist_calls[0]["audit_metadata"] == {"source": "backtest"}
