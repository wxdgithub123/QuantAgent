from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.services.audit_service import AuditService


def test_audit_service_standardizes_lookup_ids():
    service = AuditService()

    details = service._standardize_details(
        action="PAPER_ORDER_FILLED",
        resource="BTCUSDT",
        details={
            "intent": {
                "id": "OI-101-okx-0500",
                "decision_id": 101,
                "symbol": "BTCUSDT",
                "action": "BUY",
            },
            "execution": {
                "order_id": "PT-999",
                "status": "FILLED",
            },
            "risk_preview": {
                "passed": True,
                "checkedRules": [],
            },
        },
    )

    assert details["eventType"] == "PAPER_ORDER_FILLED"
    assert details["symbol"] == "BTCUSDT"
    assert details["decisionId"] == 101
    assert details["orderIntentId"] == "OI-101-okx-0500"
    assert details["orderId"] == "PT-999"
    assert details["riskCheckResult"]["passed"] is True
    assert details["executionResult"]["status"] == "FILLED"
    assert details["immutable"] is True


def test_audit_service_standard_columns_include_hash_and_status():
    service = AuditService()
    details = service._standardize_details(
        action="ORDER_CREATE",
        resource="BTCUSDT",
        details={
            "intent": {
                "id": "OI-101-okx-0500",
                "decision_id": 101,
                "symbol": "BTCUSDT",
                "action": "BUY",
            },
            "executionResult": {
                "orderId": "PT-999",
                "status": "FILLED",
                "executionMode": "paper",
            },
            "riskCheckResult": {"passed": True, "checkedRules": []},
            "contextHash": "ctx-hash",
        },
    )

    columns = service._standard_columns(
        action="ORDER_CREATE",
        resource="BTCUSDT",
        details=details,
    )
    same_columns = service._standard_columns(
        action="ORDER_CREATE",
        resource="BTCUSDT",
        details=details,
    )

    assert columns["event_type"] == "PAPER_ORDER_FILLED"
    assert columns["symbol"] == "BTCUSDT"
    assert columns["decision_id"] == 101
    assert columns["order_intent_id"] == "OI-101-okx-0500"
    assert columns["order_id"] == "PT-999"
    assert columns["context_hash"] == "ctx-hash"
    assert columns["risk_status"] == "passed"
    assert columns["execution_status"] == "FILLED"
    assert columns["execution_mode"] == "paper"
    assert columns["payload_hash"].startswith("sha256:")
    assert columns["payload_hash"] == same_columns["payload_hash"]
    assert columns["immutable"] is True


def test_order_intent_execution_link_is_not_a_fill_event():
    service = AuditService()
    details = service._standardize_details(
        action="ORDER_INTENT_EXECUTION_LINKED",
        resource="BTCUSDT",
        details={
            "intent": {"id": "OI-MANUAL-1", "symbol": "BTCUSDT", "action": "BUY"},
            "executionResult": {"orderId": "PT-13", "status": "FILLED"},
        },
    )
    columns = service._standard_columns(
        action="ORDER_INTENT_EXECUTION_LINKED",
        resource="BTCUSDT",
        details=details,
    )

    assert details["eventType"] == "ORDER_INTENT_EXECUTION_LINKED"
    assert columns["event_type"] == "ORDER_INTENT_EXECUTION_LINKED"
    assert columns["order_intent_id"] == "OI-MANUAL-1"
    assert columns["order_id"] == "PT-13"
    assert columns["execution_status"] == "FILLED"


@pytest.mark.asyncio
async def test_add_event_populates_standard_columns_and_prev_hash():
    service = AuditService()

    class FakeResult:
        def first(self):
            return ("sha256:previous",)

    class FakeSession:
        def __init__(self):
            self.added = []
            self.flushed = False
            self.params = None

        async def execute(self, _stmt, params=None):
            self.params = params
            return FakeResult()

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            self.flushed = True

    session = FakeSession()
    entry = await service.add_event(
        session,
        action="PAPER_ORDER_FILLED",
        resource="BTCUSDT",
        details={
            "decisionId": 101,
            "orderIntentId": "OI-101-okx-0500",
            "orderId": "PT-999",
            "executionResult": {"status": "FILLED"},
        },
        flush=True,
    )

    assert session.added == [entry]
    assert session.flushed is True
    assert session.params == {"chain_id": 101}
    assert entry.event_type == "PAPER_ORDER_FILLED"
    assert entry.decision_id == 101
    assert entry.order_intent_id == "OI-101-okx-0500"
    assert entry.order_id == "PT-999"
    assert entry.execution_status == "FILLED"
    assert entry.payload_hash.startswith("sha256:")
    assert entry.prev_hash == "sha256:previous"
    assert entry.immutable is True


def test_audit_migration_contains_append_only_trigger():
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "015_harden_audit_logs.py"
    )
    text = migration.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS payload_hash" in text
    assert "ADD COLUMN IF NOT EXISTS prev_hash" in text
    assert "prevent_audit_logs_mutation" in text
    assert "BEFORE UPDATE OR DELETE ON audit_logs" in text


@pytest.mark.asyncio
async def test_log_event_can_raise_on_failure(monkeypatch):
    service = AuditService()

    @asynccontextmanager
    async def failing_get_db():
        raise RuntimeError("audit table missing")
        yield

    monkeypatch.setattr("app.services.audit_service.get_db", failing_get_db)

    assert await service.log_event(action="AGENT_DECISION", resource="BTCUSDT") is False
    with pytest.raises(RuntimeError, match="audit table missing"):
        await service.log_event(
            action="AGENT_DECISION",
            resource="BTCUSDT",
            raise_on_failure=True,
        )
