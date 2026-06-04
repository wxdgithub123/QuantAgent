from app.api.v1.endpoints.system_health import (
    _build_closed_loop_steps,
    _build_demo_path,
    _build_prd_acceptance,
)


def _counts(**overrides):
    base = {
        "data_source_ready": 1,
        "market_bar_rows": 120,
        "factor_snapshots": 30,
        "signal_events": 12,
        "coordination_history": 4,
        "order_intent_events": 3,
        "risk_guard_events": 3,
        "paper_trades": 2,
        "paper_positions": 1,
        "backtest_results": 2,
        "agent_audited_backtests": 1,
        "pit_backtests": 1,
        "replay_sessions": 1,
        "audit_logs": 8,
    }
    base.update(overrides)
    return base


def test_demo_closed_loop_steps_cover_full_prd_chain():
    sample = {
        "latestBacktestId": 19,
        "latestReplaySessionId": "BTAG-19-demo",
        "latestDecisionId": 61,
        "latestOrderIntentId": "OI-demo",
        "latestPaperOrderId": "PT-44",
        "latestAuditRecordId": 84,
    }

    steps = _build_closed_loop_steps(_counts(), sample)

    assert len(steps) == 12
    assert all(step["status"] == "done" for step in steps)
    assert steps[0]["relatedApi"] == "/api/v1/system/health"
    assert steps[-1]["relatedPageUrl"] == "/audit"


def test_demo_closed_loop_steps_have_safe_partial_states_without_evidence():
    steps = _build_closed_loop_steps(_counts(market_bar_rows=0, factor_snapshots=0, signal_events=0, audit_logs=0), None)

    assert len(steps) == 12
    assert any(step["status"] == "partial" for step in steps)
    assert all("failed to fetch" not in step["shortDescription"].lower() for step in steps)


def test_prd_acceptance_returns_two_phases_with_jump_links():
    phases = _build_prd_acceptance(_counts())

    assert [phase["phaseName"] for phase in phases]
    assert len(phases) == 2
    assert all(item["jumpLink"].startswith("/") for phase in phases for item in phase["items"])
    assert all(item["status"] == "done" for phase in phases for item in phase["items"])


def test_demo_path_uses_latest_sample_links_when_available():
    path = _build_demo_path(
        {
            "backtestDetailUrl": "/backtest?backtest_id=19",
            "replayUrl": "/replay?session_id=BTAG-19-demo",
            "decisionDetailUrl": "/audit?decision_id=61",
            "auditRecordUrl": "/audit?audit_id=84",
        }
    )

    assert len(path) >= 10
    assert any(item["url"] == "/backtest?backtest_id=19" for item in path)
    assert any(item["url"] == "/replay?session_id=BTAG-19-demo" for item in path)
