import pytest

from app.services import phase2_ops_monitor


def test_ops_monitor_overall_status_handles_declared_and_partial_states():
    assert phase2_ops_monitor.overall_status(["ready", "ready"]) == "ready"
    assert phase2_ops_monitor.overall_status(["ready", "declared"]) == "partial"
    assert phase2_ops_monitor.overall_status(["degraded", "check"]) == "check"
    assert phase2_ops_monitor.status_from_count(0, declared_when_empty=True) == "declared"


def test_backtest_queue_contract_reads_in_process_tasks(monkeypatch):
    from app.api.v1.endpoints import strategy

    monkeypatch.setattr(
        strategy,
        "BACKTEST_TASKS",
        {
            "bt-a": {"status": "queued"},
            "bt-b": {"status": "running"},
            "bt-c": {"status": "completed"},
            "bt-d": {"status": "cancelled"},
        },
    )

    payload = phase2_ops_monitor.collect_backtest_queue()

    assert payload["status"] == "ready"
    assert payload["queue_scope"] == "in_process_memory"
    assert payload["active_tasks"] == 2
    assert payload["max_parallel"] == 5
    assert payload["cancel_supported"] is True
    assert payload["retry_supported"] is True


@pytest.mark.asyncio
async def test_build_phase2_ops_monitor_keeps_local_pit_boundary(monkeypatch):
    async def fake_collect_postgres_summaries(tables):
        return {
            table: {
                "table": table,
                "label": spec["label"],
                "status": "declared",
                "row_count": 0,
                "latest_available_time": None,
                "age_seconds": None,
                "pit_rule": phase2_ops_monitor.PIT_RULE if spec["time_column"] == "available_time" else None,
            }
            for table, spec in tables.items()
        }

    monkeypatch.setattr(phase2_ops_monitor, "collect_postgres_summaries", fake_collect_postgres_summaries)
    monkeypatch.setattr(
        phase2_ops_monitor,
        "collect_pipeline_storage",
        lambda: {"status": "declared", "store_available": False, "macro_stored": 0, "news_stored": 0},
    )
    monkeypatch.setattr(
        phase2_ops_monitor,
        "collect_backtest_queue",
        lambda: {"status": "ready", "queue_scope": "in_process_memory", "active_tasks": 0, "max_parallel": 5},
    )
    monkeypatch.setattr(
        phase2_ops_monitor,
        "collect_duckdb_archive",
        lambda: {
            "status": "ready",
            "available": True,
            "path": "data/backtest/backtest_results.duckdb",
            "schema_version": "backtest_duckdb_archive.v1",
            "latest_result_count": 0,
        },
    )

    async def fake_audit_health():
        return {"status": "ready", "append_only": True, "hash_coverage": "0/0", "export_api": "/api/v1/audit/records/{audit_id}/export"}

    async def fake_execution_risk():
        return {"status": "ready", "chain": ["OrderIntent", "RiskGuard", "PaperOrder", "PnL", "AuditRecord"]}

    monkeypatch.setattr(phase2_ops_monitor, "collect_audit_health", fake_audit_health)
    monkeypatch.setattr(phase2_ops_monitor, "collect_execution_risk_health", fake_execution_risk)
    monkeypatch.setattr(phase2_ops_monitor, "collect_resources", lambda: {"status": "ready", "process_pid": 1})

    payload = await phase2_ops_monitor.build_phase2_ops_monitor(
        {
            "overall_status": "ready",
            "enabled": True,
            "mode": {"configured": "context_adapter", "fullGraphReady": False},
            "service": {"status": "ok"},
            "llm": {"provider": "openai", "model": "gpt-test", "baseUrl": "https://api.example/v1"},
            "data_boundary": {
                "agent_input_policy": "local_storage_only",
                "pit_rule": "available_time <= as_of_time",
                "externalFallbackAllowed": False,
            },
            "readiness": [],
        }
    )

    assert payload["schema_version"] == phase2_ops_monitor.PHASE2_OPS_MONITOR_SCHEMA_VERSION
    assert payload["pit_rule"] == "available_time <= as_of_time"
    assert payload["agent_input_policy"] == "local_storage_only"
    assert payload["external_fallback_allowed"] is False
    assert payload["audit_health"]["append_only"] is True
    assert payload["backtest_replay"]["duckdb_archive"]["schema_version"] == "backtest_duckdb_archive.v1"
    assert payload["execution_risk"]["chain"] == ["OrderIntent", "RiskGuard", "PaperOrder", "PnL", "AuditRecord"]
