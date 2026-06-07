from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

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
    snapshot = audit_calls[0]["details"]["normalizedSnapshot"]
    assert snapshot["schema_version"] == "audit_analysis_context_snapshot.v1"
    assert snapshot["context_hash"] == "sha256:ctxhash"
    assert snapshot["input_snapshot_ids"] == {"factor_snapshot_ids": [1], "signal_event_ids": [2]}
    assert snapshot["bars_summary"]["count"] == 1
    assert snapshot["latest_factors"] == {"rsi_14": 42.0}
    assert snapshot["recent_signals"][0]["source_strategy"] == "ma"
    assert snapshot["news_events"] == [{"id": "n1"}]
    assert snapshot["macro_events"] == [{"indicator": "cpi"}]
    assert audit_calls[0]["details"]["inputSummary"]["factor_snapshot"] == {"rsi_14": 42.0}
    assert audit_calls[0]["details"]["inputSummary"]["normalized_snapshot_schema"] == "audit_analysis_context_snapshot.v1"
    assert audit_calls[0]["details"]["inputSummary"]["bars_count"] == 1
    assert audit_calls[0]["raise_on_failure"] is True
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


@pytest.mark.asyncio
async def test_coordinate_at_strict_snapshot_override_skips_context_loader(monkeypatch):
    as_of_time = datetime(2026, 6, 1, 10, tzinfo=timezone.utc)
    adapter_calls = []
    persist_calls = []

    async def fail_load(self, symbol, interval="1h", as_of_time=None):
        raise AssertionError("strict snapshot replay must not rebuild AnalysisContext")

    class FakeAdapter:
        async def run_analysis(self, **kwargs):
            adapter_calls.append(kwargs)
            return CoordinationResult(
                symbol=kwargs["symbol"],
                final_signal=SignalType.WAIT,
                confidence=0.61,
                summary="strict replay",
                input_snapshot_ids={},
                timestamp=datetime(2026, 6, 6, tzinfo=timezone.utc),
            )

    async def fake_persist(result, ctx, *, draft_order_intent=True, audit_metadata=None):
        result.decision_id = 901
        persist_calls.append({"ctx": ctx, "audit_metadata": audit_metadata})
        return 901

    snapshot_context = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "as_of_time": "2026-06-01T10:00:00+00:00",
        "context_hash": "sha256:snapshot",
        "input_snapshot_ids": {"factor_snapshot_ids": [11]},
        "latest_factors": {"rsi_14": 51.0},
        "recent_signals": [{"signal_type": "WAIT", "confidence": 0.6}],
        "bars": [{"close": 100.0}],
        "metadata": {"strict_snapshot_replay": True},
    }

    monkeypatch.setattr(CoordinatorAgent, "_load_analysis_context", fail_load)
    monkeypatch.setattr("app.agents.tradingagents_adapter.tradingagents_adapter", FakeAdapter())
    monkeypatch.setattr(CoordinatorAgent, "_persist_result", staticmethod(fake_persist))

    result = await CoordinatorAgent(use_tradingagents=True).coordinate_at(
        symbol="btcusdt",
        interval="1h",
        as_of_time=as_of_time,
        audit_metadata={"sourceDecisionId": 777, "strictSnapshotReplay": True},
        analysis_context_override=snapshot_context,
    )

    assert result.decision_id == 901
    assert adapter_calls[0]["analysis_context"]["context_hash"] == "sha256:snapshot"
    assert adapter_calls[0]["analysis_context"]["input_snapshot_ids"] == {"factor_snapshot_ids": [11]}
    assert adapter_calls[0]["analysis_context"]["metadata"]["strictSnapshotReplay"] is True
    assert persist_calls[0]["ctx"]["latest_factors"] == {"rsi_14": 51.0}
    assert persist_calls[0]["audit_metadata"]["strictSnapshotReplay"] is True


@pytest.mark.asyncio
async def test_coordinate_at_uses_local_prd104_when_tradingagents_disabled(monkeypatch):
    local_calls = []
    persist_calls = []

    async def fake_load(self, symbol, interval="1h", as_of_time=None):
        return {
            "symbol": symbol,
            "timeframe": interval,
            "context_hash": "sha256:local",
            "input_snapshot_ids": {"factor_snapshot_ids": [9]},
        }

    async def fake_local(self, symbol, interval, ctx):
        local_calls.append({"symbol": symbol, "interval": interval, "ctx": ctx})
        return CoordinationResult(
            symbol=symbol,
            final_signal=SignalType.WAIT,
            confidence=0.55,
            summary="local path",
            data_source="analysis_context",
            input_snapshot_ids=ctx["input_snapshot_ids"],
            timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )

    async def fake_persist(result, ctx, *, draft_order_intent=True, audit_metadata=None):
        result.decision_id = 602
        result.audit_url = "/audit?decision_id=602"
        persist_calls.append({"result": result, "ctx": ctx})
        return 602

    monkeypatch.setattr(CoordinatorAgent, "_load_analysis_context", fake_load)
    monkeypatch.setattr(CoordinatorAgent, "_coordinate_prd104_from_context", fake_local)
    monkeypatch.setattr(CoordinatorAgent, "_persist_result", staticmethod(fake_persist))

    result = await CoordinatorAgent(use_tradingagents=False).coordinate_at("btcusdt", "1h")

    assert local_calls[0]["symbol"] == "BTCUSDT"
    assert local_calls[0]["ctx"]["context_hash"] == "sha256:local"
    assert result.data_source == "analysis_context"
    assert result.decision_id == 602
    assert persist_calls[0]["result"] is result


@pytest.mark.asyncio
async def test_coordinate_at_returns_error_when_persistence_fails(monkeypatch):
    async def fake_load(self, symbol, interval="1h", as_of_time=None):
        return {
            "symbol": symbol,
            "timeframe": interval,
            "context_hash": "sha256:persist-fails",
            "input_snapshot_ids": {"signal_event_ids": [3]},
        }

    class FakeAdapter:
        async def run_analysis(self, **kwargs):
            return CoordinationResult(
                symbol=kwargs["symbol"],
                final_signal=SignalType.BUY,
                confidence=0.8,
                summary="adapter ok",
                input_snapshot_ids={},
                timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

    async def fake_persist(result, ctx, *, draft_order_intent=True, audit_metadata=None):
        return None

    monkeypatch.setattr(CoordinatorAgent, "_load_analysis_context", fake_load)
    monkeypatch.setattr("app.agents.tradingagents_adapter.tradingagents_adapter", FakeAdapter())
    monkeypatch.setattr(CoordinatorAgent, "_persist_result", staticmethod(fake_persist))

    result = await CoordinatorAgent(use_tradingagents=True).coordinate_at("BTCUSDT", "1h")

    assert result.data_source == "error"
    assert result.decision_id is None
    assert "持久化" in result.summary


@pytest.mark.asyncio
async def test_coordinate_endpoint_rejects_error_result(monkeypatch):
    from app.api.v1.endpoints import market as market_endpoint

    class FakeCoordinator:
        def __init__(self, **kwargs):
            pass

        async def coordinate(self, symbol, interval):
            return CoordinationResult(
                symbol=symbol,
                final_signal=SignalType.WAIT,
                confidence=0.0,
                summary="TradingAgents 服务不可用",
                data_source="error",
                timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

    monkeypatch.setattr("app.agents.coordinator_agent.CoordinatorAgent", FakeCoordinator)

    with pytest.raises(HTTPException) as exc_info:
        await market_endpoint.coordinate_agents("BTCUSDT")

    assert exc_info.value.status_code == 503
    assert "服务不可用" in exc_info.value.detail
