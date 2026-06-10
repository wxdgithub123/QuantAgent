from datetime import datetime, timezone

from app.api.v1.endpoints.linkage import build_replay_package, build_workbench_linkage


def test_workbench_linkage_builds_pit_cross_desk_links():
    payload = build_workbench_linkage(
        symbol="btc/usdt",
        interval="1h",
        as_of_time=datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
        decision_id="42",
        audit_id="7",
        backtest_id="9",
        replay_session_id="rp-1",
        order_intent_id="oi-1",
        order_id="po-1",
        context_hash="sha256:abc",
        source="backtest_trade",
    )

    assert payload["identity"]["symbol"] == "BTCUSDT"
    assert payload["identity"]["context_hash"] == "sha256:abc"
    assert payload["pit"]["rule"] == "available_time <= as_of_time"
    assert payload["pit"]["agent_input_policy"] == "local_storage_only"
    assert payload["pit"]["external_fallback_allowed"] is False
    assert payload["links"]["research"].startswith("/dashboard?symbol=BTCUSDT&interval=1h&as_of_time=")
    assert "/api/v1/bars/as-of?symbol=BTCUSDT" in payload["links"]["bars_as_of_api"]
    assert payload["links"]["audit"] == (
        "/audit?symbol=BTCUSDT&decision_id=42&audit_id=7&backtest_id=9&"
        "replay_session_id=rp-1&order_intent_id=oi-1&order_id=po-1"
    )
    assert payload["links"]["audit_export_api"] == "/api/v1/audit/records/7/export"
    assert payload["links"]["replay"].startswith("/replay?session_id=rp-1&as_of_time=")
    assert payload["replayability"]["requires_snapshot_ids"] is True


def test_workbench_linkage_defaults_without_database():
    payload = build_workbench_linkage()

    assert payload["identity"]["symbol"] == "BTCUSDT"
    assert payload["links"]["research"] == "/dashboard?symbol=BTCUSDT&interval=1h"
    assert payload["links"]["snapshot_api"] == "/api/v1/snapshot?symbol=BTCUSDT&interval=1h"


def test_replay_package_restores_strict_snapshot_and_execution_chain():
    audit_record = {
        "id": 7,
        "action": "AGENT_DECISION",
        "event_type": "AGENT_DECISION",
        "decision_id": 42,
        "symbol": "BTCUSDT",
        "context_hash": "sha256:ctx",
        "created_at": datetime(2026, 6, 1, 10, 1, tzinfo=timezone.utc),
        "payload_hash": "sha256:audit",
        "immutable": True,
        "details": {
            "decisionId": 42,
            "contextHash": "sha256:ctx",
            "normalizedSnapshot": {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "as_of_time": "2026-06-01T10:00:00+00:00",
                "context_hash": "sha256:ctx",
                "input_snapshot_ids": {"bar_ids": [1, 2], "news_event_ids": [9]},
                "data_versions": {"bars": "clickhouse.market_bars.v1"},
                "bars": [
                    {
                        "id": 1,
                        "timestamp": "2026-06-01T09:00:00+00:00",
                        "available_time": "2026-06-01T09:01:00+00:00",
                        "close": 100,
                    }
                ],
                "latest_factors": {
                    "rsi": {
                        "id": 11,
                        "available_time": "2026-06-01T09:59:00+00:00",
                        "value": 55,
                    }
                },
                "recent_signals": [{"id": 12, "available_time": "2026-06-01T09:58:00+00:00"}],
                "news_events": [{"id": 13, "available_time": "2026-06-01T09:30:00+00:00"}],
                "macro_events": [],
            },
            "agentOutputs": [{"role": "market_analyst", "summary": "BUY"}],
            "decision": {"id": 42, "final_signal": "BUY", "confidence": 0.72},
        },
    }
    risk_record = {
        "id": 8,
        "action": "RISK_CHECK_PASSED",
        "event_type": "RISK_CHECK_PASSED",
        "decision_id": 42,
        "details": {
            "intent": {"id": "oi-1", "side": "long", "positionRatio": 0.1},
            "riskCheckResult": {"passed": True, "checkedRules": ["MAX_POSITION"]},
        },
        "immutable": True,
    }
    package = build_replay_package(
        decision_row={
            "id": 42,
            "symbol": "BTCUSDT",
            "timestamp": datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
            "final_signal": "BUY",
            "confidence": 0.72,
            "context_hash": "sha256:ctx",
        },
        audit_record=audit_record,
        audit_events=[audit_record, risk_record],
    )

    assert package["identity"]["decision_id"] == 42
    assert package["pit"]["strict_snapshot_replay"] is True
    assert package["pit"]["agent_input_policy"] == "local_storage_only"
    assert package["pit"]["external_fallback_allowed"] is False
    assert package["agent_input_package"]["record_ids"] == {"bar_ids": [1, 2], "news_event_ids": [9]}
    assert package["agent_input_package"]["counts"] == {"bars": 1, "factors": 1, "signals": 1, "news": 1, "macro": 0}
    assert all(check["passed"] in (True, None) for check in package["pit"]["visible_data_checks"])
    assert package["execution_chain"]["risk_guard"]["passed"] is True
    assert package["links"]["replay_package_api"].startswith("/api/v1/linkage/replay-package?")


def test_replay_package_falls_back_to_local_pit_rebuild_contract():
    package = build_replay_package(
        symbol="eth/usdt",
        interval="4h",
        as_of_time=datetime(2026, 6, 1, 8, tzinfo=timezone.utc),
        context_hash="sha256:missing",
    )

    assert package["identity"]["symbol"] == "ETHUSDT"
    assert package["pit"]["strict_snapshot_replay"] is False
    assert package["pit"]["replay_method"] == "pit_rebuild_from_local_storage"
    assert package["replayability"]["can_replay_without_external_source"] is True
    assert package["replayability"]["missing_for_strict_replay"] == ["normalizedSnapshot", "input_snapshot_ids", "agent_role_outputs"]
    assert package["replay_plan"][0]["status"] == "pit_rebuild_required"
