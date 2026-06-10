import json

from app.services import backtest_duckdb_store as store_module
from app.services.backtest_duckdb_store import (
    BACKTEST_DUCKDB_SCHEMA_VERSION,
    BacktestDuckDBStore,
    build_backtest_archive_record,
)


def test_build_backtest_archive_record_keeps_prd_metrics_and_pit_evidence():
    record = build_backtest_archive_record(
        backtest_id=42,
        task_id="bt-task",
        strategy_type="ma",
        symbol="btcusdt",
        interval="1h",
        params={"fast": 5, "slow": 20},
        params_hash="hash-1",
        metrics={
            "total_return": 12.5,
            "annualized_return": 18.0,
            "max_drawdown": 4.2,
            "sharpe_ratio": 1.4,
            "information_ratio": 0.8,
            "win_rate": 55.5,
            "profit_factor": 1.8,
            "total_trades": 3,
            "total_fee": 10.0,
            "total_slippage": 2.0,
            "agentCallCount": 2,
            "riskBlockedCount": 1,
            "waitCount": 1,
        },
        equity_curve=[{"t": "2026-01-01T00:00:00", "v": 10000}],
        trades=[{"tradeId": "BT-42-1"}],
        pit={"as_of_time": "2026-01-02T00:00:00Z", "actual_start_time": "2026-01-01T00:00:00Z"},
        pit_check={"passed": False, "violationCount": 1, "rule": "available_time <= as_of_time"},
        execution_mode="agent_audited",
    )

    assert record["schema_version"] == BACKTEST_DUCKDB_SCHEMA_VERSION
    assert record["backtest_id"] == 42
    assert record["symbol"] == "BTCUSDT"
    assert record["pit_passed"] is False
    assert record["pit_violation_count"] == 1
    assert record["total_return"] == 12.5
    assert record["information_ratio"] == 0.8
    assert json.loads(record["params_json"]) == {"fast": 5, "slow": 20}
    agent_stats = json.loads(record["agent_stats_json"])
    assert agent_stats["agentCallCount"] == 2
    assert agent_stats["riskBlockedCount"] == 1
    assert agent_stats["waitCount"] == 1


def test_duckdb_archive_uses_short_lived_connections_for_cross_store_visibility(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "BACKTEST_DUCKDB_PATH", tmp_path / "backtest_results.duckdb")
    record = build_backtest_archive_record(
        backtest_id=88,
        task_id=None,
        strategy_type="ma",
        symbol="BTCUSDT",
        interval="1h",
        params={"fast": 5, "slow": 20},
        params_hash="hash-88",
        metrics={"total_return": 1.23, "total_trades": 2},
        equity_curve=[{"t": "2026-06-01T00:00:00Z", "v": 10000.0}],
        trades=[{"tradeId": "BT-88-1"}],
        pit={"as_of_time": "2026-06-01T00:00:00Z"},
        pit_check={"passed": True, "violationCount": 0},
        execution_mode="rule_only",
    )

    writer = BacktestDuckDBStore()
    reader = BacktestDuckDBStore()

    assert writer.archive_result(record)["status"] == "archived"
    rows = reader.latest_results(limit=5)

    assert [row["backtest_id"] for row in rows] == [88]
    assert store_module.BACKTEST_DUCKDB_PATH.exists()
