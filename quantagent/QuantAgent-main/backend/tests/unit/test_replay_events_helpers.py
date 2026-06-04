from datetime import datetime, timezone

from app.api.v1.endpoints.replay import (
    _build_replay_event_stats,
    _dedupe_replay_events,
    _event_payload,
    _sort_replay_events,
)


def test_event_payload_keeps_replay_lineage_links():
    event = _event_payload(
        event_id="evt-1",
        event_type="PAPER_ORDER_FILLED",
        event_time=datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        summary="filled",
        payload={"price": 100.0},
        related_decision_id=101,
        related_order_intent_id="OI-101-okx-0500",
        related_order_id="PT-999",
        related_audit_id=77,
    )

    assert event["eventType"] == "PAPER_ORDER_FILLED"
    assert event["asOfTime"] == "2026-06-01T09:00:00+00:00"
    assert event["relatedDecisionId"] == 101
    assert event["links"]["audit"] == "/audit?audit_id=77"
    assert event["links"]["orderIntent"] == "/audit?order_intent_id=OI-101-okx-0500"


def test_sort_replay_events_orders_by_as_of_time_then_event_time():
    events = [
        {"id": "later", "eventTime": "2026-06-01T11:00:00+00:00"},
        {"id": "earlier", "asOfTime": "2026-06-01T09:00:00"},
        {"id": "middle", "asOfTime": "2026-06-01T10:00:00+00:00"},
    ]

    sorted_events = _sort_replay_events(events)

    assert [item["id"] for item in sorted_events] == ["earlier", "middle", "later"]


def test_event_payload_supports_agent_audited_signal_and_skip_links():
    event = _event_payload(
        event_id="skip-1",
        event_type="SKIPPED_AGENT_CALL",
        event_time=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        summary="maxAgentCalls reached",
        payload={
            "backtestId": 15,
            "replaySessionId": "BTAG-15-test",
            "signalEventId": 123,
        },
        related_audit_id=88,
    )

    assert event["eventType"] == "SKIPPED_AGENT_CALL"
    assert event["payload"]["replaySessionId"] == "BTAG-15-test"
    assert event["links"]["audit"] == "/audit?audit_id=88"


def test_duplicate_paper_order_events_are_merged_without_losing_payloads():
    as_of = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    trade_event = _event_payload(
        event_id="trade-1",
        event_type="PAPER_ORDER_FILLED",
        event_time=as_of,
        symbol="BTCUSDT",
        summary="trade fill",
        payload={"price": 100.0, "source": "paper_trades"},
        related_order_intent_id="OI-1",
        related_order_id="PT-1",
    )
    audit_event = _event_payload(
        event_id="audit-1",
        event_type="PAPER_ORDER_FILLED",
        event_time=as_of,
        symbol="BTCUSDT",
        summary="audit fill",
        payload={"price": 100.0, "fee": 1.0, "source": "audit_logs"},
        related_order_intent_id="OI-1",
        related_order_id="PT-1",
        related_audit_id=10,
    )

    deduped = _dedupe_replay_events([trade_event, audit_event])

    assert len(deduped) == 1
    assert deduped[0]["relatedAuditId"] == 10
    assert deduped[0]["mergedFromCount"] == 2
    assert len(deduped[0]["sourceEvents"]) == 2
    assert len(deduped[0]["rawPayloads"]) == 2


def test_duplicate_pnl_events_are_merged_without_losing_payloads():
    as_of = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    events = [
        _event_payload(
            event_id="pnl-1",
            event_type="PNL_UPDATED",
            event_time=as_of,
            symbol="BTCUSDT",
            summary="pnl",
            payload={"realizedPnl": 10.0},
            related_order_id="PT-1",
        ),
        _event_payload(
            event_id="audit-pnl-1",
            event_type="PNL_UPDATED",
            event_time=as_of,
            symbol="BTCUSDT",
            summary="audit pnl",
            payload={"realizedPnl": 10.0, "executionMode": "agent_audited"},
            related_order_id="PT-1",
            related_order_intent_id="OI-1",
            related_audit_id=11,
        ),
    ]

    deduped = _dedupe_replay_events(events)

    assert len(deduped) == 1
    assert deduped[0]["relatedAuditId"] == 11
    assert deduped[0]["payload"]["mergedFromCount"] == 2


def test_sort_replay_events_uses_business_order_for_same_as_of_time():
    as_of = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    events = [
        _event_payload(event_id="pnl", event_type="PNL_UPDATED", event_time=as_of, symbol="BTCUSDT", summary="", payload={}),
        _event_payload(event_id="bar", event_type="BAR_UPDATED", event_time=as_of, symbol="BTCUSDT", summary="", payload={}),
        _event_payload(event_id="decision", event_type="AGENT_DECISION", event_time=as_of, symbol="BTCUSDT", summary="", payload={}),
        _event_payload(event_id="signal", event_type="SIGNAL_TRIGGERED", event_time=as_of, symbol="BTCUSDT", summary="", payload={}),
    ]

    sorted_events = _sort_replay_events(events)

    assert [item["eventType"] for item in sorted_events] == [
        "BAR_UPDATED",
        "SIGNAL_TRIGGERED",
        "AGENT_DECISION",
        "PNL_UPDATED",
    ]


def test_replay_event_stats_counts_agent_audited_events():
    events = [
        {"eventType": "SIGNAL_TRIGGERED", "relatedAuditId": 1, "payload": {"executionMode": "agent_audited"}},
        {"eventType": "AGENT_DECISION", "relatedAuditId": 2, "payload": {"executionMode": "agent_audited"}},
        {"eventType": "SKIPPED_AGENT_CALL", "relatedAuditId": 3, "payload": {}},
        {"eventType": "RISK_CHECK_PASSED", "relatedAuditId": 4, "payload": {}},
        {"eventType": "PAPER_ORDER_FILLED", "relatedAuditId": 5, "payload": {}},
    ]

    stats = _build_replay_event_stats(events)

    assert stats["signalTriggeredCount"] == 1
    assert stats["agentDecisionCount"] == 1
    assert stats["skippedAgentCallCount"] == 1
    assert stats["riskPassedCount"] == 1
    assert stats["paperOrderFilledCount"] == 1
    assert stats["auditRecordCount"] == 5
    assert stats["executionMode"] == "agent_audited"
