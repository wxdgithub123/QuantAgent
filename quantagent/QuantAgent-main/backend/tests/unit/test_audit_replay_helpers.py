from datetime import datetime, timezone

from app.agents.base_agent import SignalType
from app.agents.coordinator_agent import CoordinationResult
from app.api.v1.endpoints.audit import _decision_diff_summary, _extract_interval_from_snapshot


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
