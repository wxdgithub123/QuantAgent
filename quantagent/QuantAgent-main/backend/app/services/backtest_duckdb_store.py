"""DuckDB archive contract for backtest results and task queues."""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

_conn_lock = threading.Lock()


BACKTEST_DUCKDB_SCHEMA_VERSION = "backtest_duckdb_archive.v1"
BACKTEST_DUCKDB_PATH = Path("data/backtest/backtest_results.duckdb")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, default=str)


@contextmanager
def _duckdb_connection() -> Iterator[Any]:
    """Open a short-lived DuckDB connection so multi-backend readers see fresh rows."""
    try:
        import duckdb
    except ImportError:
        logger.warning("duckdb not installed; backtest DuckDB archive disabled")
        yield None
        return

    conn = None
    try:
        BACKTEST_DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(BACKTEST_DUCKDB_PATH))
    except Exception as exc:
        logger.warning("Backtest DuckDB archive unavailable: %s", exc)
        yield None
        return

    try:
        yield conn
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def build_backtest_archive_record(
    *,
    backtest_id: Optional[int],
    strategy_type: str,
    symbol: str,
    interval: str,
    params: Dict[str, Any],
    params_hash: Optional[str],
    metrics: Dict[str, Any],
    equity_curve: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    pit: Dict[str, Any],
    pit_check: Dict[str, Any],
    execution_mode: str,
    task_id: Optional[str] = None,
    status: str = "completed",
) -> Dict[str, Any]:
    """Build one stable row for DuckDB backtest result archival."""
    agent_stats = {
        "agentCallCount": metrics.get("agentCallCount", 0),
        "buyCount": metrics.get("buyCount", metrics.get("BUY", 0)),
        "sellCount": metrics.get("sellCount", metrics.get("SELL", 0)),
        "waitCount": metrics.get("waitCount", metrics.get("WAIT", 0)),
        "avgConfidence": metrics.get("avgConfidence", metrics.get("averageConfidence")),
        "riskBlockedCount": metrics.get("riskBlockedCount", 0),
        "riskPassedCount": metrics.get("riskPassedCount"),
        "agentDecisionReturn": metrics.get("agentDecisionReturn"),
        "ruleOnlyComparison": metrics.get("ruleOnlyComparison"),
    }
    record = {
        "schema_version": BACKTEST_DUCKDB_SCHEMA_VERSION,
        "backtest_id": backtest_id,
        "task_id": task_id,
        "status": status,
        "strategy_type": strategy_type,
        "symbol": symbol.upper(),
        "interval": interval,
        "params_hash": params_hash,
        "execution_mode": execution_mode,
        "created_at": datetime.now(timezone.utc),
        "start_time": pit.get("actual_start_time") or pit.get("requested_start_time"),
        "end_time": pit.get("actual_end_time") or pit.get("requested_end_time"),
        "as_of_time": pit.get("as_of_time") or pit.get("requested_as_of_time") or pit.get("actual_end_time"),
        "pit_rule": pit_check.get("rule") or pit.get("rule") or "available_time <= as_of_time",
        "pit_passed": bool(pit_check.get("passed", True)),
        "pit_violation_count": int(pit_check.get("violationCount", 0) or 0),
        "total_return": float(metrics.get("total_return", 0.0) or 0.0),
        "annualized_return": float(metrics.get("annualized_return", metrics.get("annual_return", 0.0)) or 0.0),
        "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
        "sharpe": float(metrics.get("sharpe_ratio", metrics.get("sharpe", 0.0)) or 0.0),
        "information_ratio": float(metrics.get("information_ratio", 0.0) or 0.0),
        "win_rate": float(metrics.get("win_rate", 0.0) or 0.0),
        "profit_factor": float(metrics.get("profit_factor", 0.0) or 0.0),
        "total_trades": int(metrics.get("total_trades", len(trades)) or 0),
        "total_fee": float(metrics.get("total_fee", metrics.get("total_commission", 0.0)) or 0.0),
        "total_slippage": float(metrics.get("total_slippage", 0.0) or 0.0),
        "params_json": _json(params),
        "metrics_json": _json(metrics),
        "equity_curve_json": _json(equity_curve),
        "trades_json": _json(trades),
        "pit_json": _json(pit),
        "pit_check_json": _json(pit_check),
        "agent_stats_json": _json(agent_stats),
    }
    return record


class BacktestDuckDBStore:
    """Persistent DuckDB archive for backtest comparison and replay evidence."""

    def __init__(self) -> None:
        self._tables_ready = False

    @property
    def available(self) -> bool:
        with _duckdb_connection() as conn:
            return conn is not None

    def ensure_tables(self, conn: Any) -> bool:
        if conn is None:
            return False
        with _conn_lock:
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS backtest_results (
                        schema_version VARCHAR,
                        backtest_id BIGINT,
                        task_id VARCHAR,
                        status VARCHAR,
                        strategy_type VARCHAR,
                        symbol VARCHAR,
                        interval VARCHAR,
                        params_hash VARCHAR,
                        execution_mode VARCHAR,
                        created_at TIMESTAMP,
                        start_time VARCHAR,
                        end_time VARCHAR,
                        as_of_time VARCHAR,
                        pit_rule VARCHAR,
                        pit_passed BOOLEAN,
                        pit_violation_count INTEGER,
                        total_return DOUBLE,
                        annualized_return DOUBLE,
                        max_drawdown DOUBLE,
                        sharpe DOUBLE,
                        information_ratio DOUBLE,
                        win_rate DOUBLE,
                        profit_factor DOUBLE,
                        total_trades INTEGER,
                        total_fee DOUBLE,
                        total_slippage DOUBLE,
                        params_json VARCHAR,
                        metrics_json VARCHAR,
                        equity_curve_json VARCHAR,
                        trades_json VARCHAR,
                        pit_json VARCHAR,
                        pit_check_json VARCHAR,
                        agent_stats_json VARCHAR
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS backtest_task_events (
                        task_id VARCHAR,
                        event_time TIMESTAMP,
                        status VARCHAR,
                        event_type VARCHAR,
                        payload_json VARCHAR
                    )
                    """
                )
                self._tables_ready = True
                return True
            except Exception as exc:
                logger.warning("Backtest DuckDB archive table init failed: %s", exc)
                return False

    def archive_result(self, record: Dict[str, Any]) -> Dict[str, Any]:
        with _duckdb_connection() as conn:
            if not self.ensure_tables(conn):
                return {
                    "enabled": True,
                    "status": "unavailable",
                    "path": str(BACKTEST_DUCKDB_PATH),
                    "schema_version": BACKTEST_DUCKDB_SCHEMA_VERSION,
                }
            try:
                with _conn_lock:
                    conn.execute(
                        """
                        DELETE FROM backtest_results
                        WHERE backtest_id IS NOT NULL AND backtest_id = ?
                        """,
                        [record.get("backtest_id")],
                    )
                    columns = list(record.keys())
                    placeholders = ", ".join(["?"] * len(columns))
                    conn.execute(
                        f"INSERT INTO backtest_results ({', '.join(columns)}) VALUES ({placeholders})",
                        [record[column] for column in columns],
                    )
                    conn.commit()
                return {
                    "enabled": True,
                    "status": "archived",
                    "path": str(BACKTEST_DUCKDB_PATH),
                    "schema_version": BACKTEST_DUCKDB_SCHEMA_VERSION,
                }
            except Exception as exc:
                logger.warning("Backtest DuckDB archive write failed: %s", exc)
                return {
                    "enabled": True,
                    "status": "failed",
                    "path": str(BACKTEST_DUCKDB_PATH),
                    "schema_version": BACKTEST_DUCKDB_SCHEMA_VERSION,
                    "error": str(exc)[:240],
                }

    def append_task_event(self, task_id: str, status: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with _duckdb_connection() as conn:
            if not self.ensure_tables(conn):
                return {"status": "unavailable", "path": str(BACKTEST_DUCKDB_PATH)}
            try:
                with _conn_lock:
                    conn.execute(
                        """
                        INSERT INTO backtest_task_events (task_id, event_time, status, event_type, payload_json)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        [task_id, datetime.now(timezone.utc), status, event_type, _json(payload)],
                    )
                    conn.commit()
                return {"status": "archived", "path": str(BACKTEST_DUCKDB_PATH)}
            except Exception as exc:
                logger.warning("Backtest DuckDB task event write failed: %s", exc)
                return {"status": "failed", "path": str(BACKTEST_DUCKDB_PATH), "error": str(exc)[:240]}

    def latest_results(self, limit: int = 20) -> List[Dict[str, Any]]:
        with _duckdb_connection() as conn:
            if not self.ensure_tables(conn):
                return []
            try:
                df = conn.sql(
                    f"""
                    SELECT backtest_id, task_id, status, strategy_type, symbol, interval,
                           params_hash, execution_mode, created_at, as_of_time, pit_passed,
                           pit_violation_count, total_return, annualized_return, max_drawdown,
                           sharpe, information_ratio, win_rate, profit_factor, total_trades
                    FROM backtest_results
                    ORDER BY created_at DESC
                    LIMIT {max(1, min(int(limit), 100))}
                    """
                ).df()
                return df.to_dict(orient="records")
            except Exception as exc:
                logger.warning("Backtest DuckDB latest query failed: %s", exc)
                return []


backtest_duckdb_store = BacktestDuckDBStore()
