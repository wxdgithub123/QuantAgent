from datetime import datetime, timezone

from app.agents.base_agent import SignalType
from app.agents.coordinator_agent import CoordinationResult
from app.api.v1.endpoints.audit import (
    _analysis_context_from_snapshot,
    _audit_record_payload,
    _decision_payload,
    _decision_diff_summary,
    _extract_interval_from_snapshot,
    _normalized_snapshot_from_details,
)


def test_decision_diff_summary_reports_replay_changes():
    source = {
        "final_signal": "BUY",
        "confidence": 0.7,
        "risk_veto": False,
        "summary": "original",
        "context_hash": "sha256:original",
    }
    replay = CoordinationResult(
        symbol="BTCUSDT",
        final_signal=SignalType.WAIT,
        confidence=0.55,
        summary="replayed",
        risk_veto=True,
        context_hash="sha256:replay",
        timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    diff = _decision_diff_summary(source, replay)

    assert diff["originalAction"] == "BUY"
    assert diff["replayAction"] == "WAIT"
    assert diff["actionChanged"] is True
    assert diff["confidenceDelta"] == -0.15
    assert diff["riskVetoChanged"] is True
    assert diff["contextHashChanged"] is True
    assert diff["summaryChanged"] is True


def test_extract_interval_from_snapshot_prefers_bar_meta():
    assert _extract_interval_from_snapshot({"bar_meta": [{"interval": "4h"}]}) == "4h"
    assert _extract_interval_from_snapshot({"timeframe": "1d"}) == "1d"
    assert _extract_interval_from_snapshot({}) == "1h"


def test_decision_payload_tolerates_missing_optional_display_columns():
    row = {
        "id": 1,
        "symbol": "BTCUSDT",
        "timestamp": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "final_signal": "WAIT",
        "confidence": 0.5,
        "vote_breakdown": {},
        "risk_veto": False,
        "summary": "hold",
        "input_snapshot_ids": {"bar_meta": [{"interval": "1h"}]},
        "role_opinions": [],
        "agent_signals": [],
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "context_id": "ctx-1",
        "context_hash": "sha256:ctx",
        "available_time": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "model_version": "test-model",
        "prompt_version": "v1",
    }

    payload = _decision_payload(row)

    assert payload["bull_view"] == ""
    assert payload["bear_view"] == ""
    assert payload["position_advice"] == {}
    assert payload["risk_notes"] == ""


def test_normalized_snapshot_from_details_supports_current_and_legacy_locations():
    snapshot = {
        "schema_version": "audit_analysis_context_snapshot.v1",
        "context_hash": "sha256:ctx",
    }

    assert _normalized_snapshot_from_details({"normalizedSnapshot": snapshot}) == snapshot
    assert _normalized_snapshot_from_details({"inputSummary": {"normalizedSnapshot": snapshot}}) == snapshot
    assert _normalized_snapshot_from_details({"inputSummary": {"normalized_snapshot": snapshot}}) == snapshot
    assert _normalized_snapshot_from_details({"inputSummary": {"snapshot_ids": {"factor_snapshot_ids": [1]}}}) == {}


def test_analysis_context_from_snapshot_preserves_agent_visible_inputs():
    snapshot = {
        "schema_version": "audit_analysis_context_snapshot.v1",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "as_of_time": "2026-06-01T10:00:00+00:00",
        "context_hash": "sha256:ctx",
        "input_snapshot_ids": {"factor_snapshot_ids": [1], "signal_event_ids": [2]},
        "data_versions": {"bars": {"source_version": "bars.v1"}},
        "bars": [{"timestamp": "2026-06-01T09:00:00+00:00", "close": 100.0}],
        "latest_factors": {"rsi_14": 42.0},
        "recent_signals": [{"signal_type": "BUY", "confidence": 0.8}],
        "news_events": [{"id": "n1"}],
        "macro_events": [{"indicator": "cpi"}],
        "metadata": {"source": "audit_logs"},
    }

    ctx = _analysis_context_from_snapshot(snapshot)

    assert ctx["symbol"] == "BTCUSDT"
    assert ctx["timeframe"] == "1h"
    assert ctx["as_of_time"] == "2026-06-01T10:00:00+00:00"
    assert ctx["context_hash"] == "sha256:ctx"
    assert ctx["input_snapshot_ids"] == {"factor_snapshot_ids": [1], "signal_event_ids": [2]}
    assert ctx["data_versions"] == {"bars": {"source_version": "bars.v1"}}
    assert ctx["bars"][0]["close"] == 100.0
    assert ctx["latest_factors"] == {"rsi_14": 42.0}
    assert ctx["recent_signals"][0]["signal_type"] == "BUY"
    assert ctx["news_events"] == [{"id": "n1"}]
    assert ctx["macro_events"] == [{"indicator": "cpi"}]
    assert ctx["metadata"]["strict_snapshot_replay"] is True
    assert ctx["metadata"]["snapshot_schema_version"] == "audit_analysis_context_snapshot.v1"


def test_audit_record_payload_normalizes_replay_and_risk_unavailable_fields():
    row = {
        "id": 7,
        "action": "RISK_CHECK_UNAVAILABLE",
        "user_id": "system",
        "resource": "BTCUSDT",
        "details": {
            "eventType": "RISK_CHECK_UNAVAILABLE",
            "decisionId": 222,
            "sourceDecisionId": 111,
            "replayDecisionId": 222,
            "contextHash": "sha256:replay",
            "riskUnavailable": True,
            "riskCheckResult": {
                "passed": False,
                "riskUnavailable": True,
                "checkedRules": [{"ruleName": "RiskGuard unavailable", "passed": False}],
            },
        },
        "ip_address": "internal",
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }

    payload = _audit_record_payload(row)

    assert payload["eventType"] == "RISK_CHECK_UNAVAILABLE"
    assert payload["decisionId"] == 222
    assert payload["sourceDecisionId"] == 111
    assert payload["replayDecisionId"] == 222
    assert payload["contextHash"] == "sha256:replay"
    assert payload["riskStatus"] == "unavailable"
    assert payload["riskUnavailable"] is True
    assert payload["auditSource"] == "audit_logs"
    assert payload["synthetic"] is False
