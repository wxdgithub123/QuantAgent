"""Phase 2 operations monitor contract.

This module keeps the PRD operations view separate from the older L1-L6 health
endpoint. It is intentionally local-storage focused: the monitor may inspect
local databases and task queues, but it never fetches live market data.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


PHASE2_OPS_MONITOR_SCHEMA_VERSION = "phase2_ops_monitor.v1"
PIT_RULE = "available_time <= as_of_time"
AGENT_INPUT_POLICY = "local_storage_only"

DATA_FRESHNESS_TABLES: Dict[str, Dict[str, str]] = {
    "bar_1m": {"label": "1m bars", "time_column": "available_time"},
    "bar_1h": {"label": "1h bars", "time_column": "available_time"},
    "bar_1d": {"label": "1d bars", "time_column": "available_time"},
    "quote_latest": {"label": "Latest quotes", "time_column": "available_time"},
    "fundamental_report": {"label": "Fundamentals", "time_column": "available_time"},
    "corporate_action": {"label": "Corporate actions", "time_column": "available_time"},
    "adjustment_factor": {"label": "Adjustment factors", "time_column": "available_time"},
    "news_event": {"label": "News events", "time_column": "available_time"},
    "macro_indicator": {"label": "Macro indicators", "time_column": "available_time"},
    "etl_job_log": {"label": "ETL jobs", "time_column": "started_at"},
}

CORE_DB_TABLES: Dict[str, Dict[str, str]] = {
    "factor_snapshots": {"label": "Factor snapshots", "time_column": "available_time"},
    "signal_events": {"label": "Signal events", "time_column": "available_time"},
    "coordination_history": {"label": "Agent decisions", "time_column": "available_time"},
    "backtest_results": {"label": "Backtest results", "time_column": "created_at"},
    "replay_sessions": {"label": "Replay sessions", "time_column": "updated_at"},
    "audit_logs": {"label": "Audit records", "time_column": "created_at"},
    "paper_trades": {"label": "Paper orders/fills", "time_column": "created_at"},
    "paper_positions": {"label": "Paper positions", "time_column": "updated_at"},
}

STATUS_WEIGHT = {"ready": 3, "partial": 2, "declared": 1, "check": 0, "degraded": 0}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def age_seconds(value: Any, now: Optional[datetime] = None) -> Optional[float]:
    if value is None:
        return None
    now = now or datetime.now(timezone.utc)
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds())


def status_from_count(count: int, *, declared_when_empty: bool = False) -> str:
    if count > 0:
        return "ready"
    return "declared" if declared_when_empty else "check"


def overall_status(statuses: Iterable[str]) -> str:
    values = list(statuses)
    if not values:
        return "check"
    if all(value == "ready" for value in values):
        return "ready"
    if any(value in {"ready", "partial", "declared"} for value in values):
        return "partial"
    return "check"


async def scalar(session: Any, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
    from sqlalchemy import text

    result = await session.execute(text(sql), params or {})
    return result.scalar()


async def table_exists(session: Any, table_name: str) -> bool:
    result = await scalar(
        session,
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = 'public' AND table_name = :table_name
        )
        """,
        {"table_name": table_name},
    )
    return bool(result)


async def table_summary(session: Any, table_name: str, spec: Dict[str, str]) -> Dict[str, Any]:
    """Return count/latest stats for one fixed table contract."""
    exists = await table_exists(session, table_name)
    if not exists:
        return {
            "table": table_name,
            "label": spec["label"],
            "status": "declared",
            "row_count": 0,
            "latest_available_time": None,
            "age_seconds": None,
            "detail": "contract declared; table not found in the connected database",
        }
    time_column = spec["time_column"]
    count = safe_int(await scalar(session, f"SELECT COUNT(*) FROM {table_name}"))
    latest = await scalar(session, f"SELECT MAX({time_column}) FROM {table_name}")
    return {
        "table": table_name,
        "label": spec["label"],
        "status": status_from_count(count, declared_when_empty=True),
        "row_count": count,
        "latest_available_time": to_iso(latest),
        "age_seconds": age_seconds(latest),
        "pit_rule": PIT_RULE if time_column == "available_time" else None,
    }


async def collect_postgres_summaries(tables: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    summaries: Dict[str, Dict[str, Any]] = {}
    try:
        from app.services.database import get_db

        async with get_db() as session:
            for table_name, spec in tables.items():
                try:
                    summaries[table_name] = await table_summary(session, table_name, spec)
                except Exception as exc:
                    summaries[table_name] = {
                        "table": table_name,
                        "label": spec["label"],
                        "status": "degraded",
                        "row_count": 0,
                        "latest_available_time": None,
                        "age_seconds": None,
                        "error": str(exc)[:180],
                    }
    except Exception as exc:
        for table_name, spec in tables.items():
            summaries[table_name] = {
                "table": table_name,
                "label": spec["label"],
                "status": "degraded",
                "row_count": 0,
                "latest_available_time": None,
                "age_seconds": None,
                "error": str(exc)[:180],
            }
    return summaries


def collect_pipeline_storage() -> Dict[str, Any]:
    try:
        from app.pipeline.orchestrator import pipeline_orchestrator
        from app.pipeline.storage.duckdb_store import pipeline_store

        stats = pipeline_orchestrator.stats()
        latest_macro = pipeline_store.latest_macro()
        latest_news = pipeline_store.query_news(limit=1)
        latest_news_time = latest_news[0].get("available_time") or latest_news[0].get("published_at") if latest_news else None
        latest_macro_time = None
        for item in latest_macro.values():
            candidate = item.get("available_time") or item.get("date")
            if candidate and (latest_macro_time is None or str(candidate) > str(latest_macro_time)):
                latest_macro_time = candidate
        return {
            "status": "ready" if pipeline_store.available else "degraded",
            "store_available": pipeline_store.available,
            "running": bool(stats.get("running")),
            "macro_stored": safe_int(stats.get("macro_stored")),
            "news_stored": safe_int(stats.get("news_stored")),
            "latest_macro_available_time": to_iso(latest_macro_time),
            "latest_news_available_time": to_iso(latest_news_time),
            "last_check": stats.get("last_check"),
            "pit_rule": "COALESCE(available_time, event_time) <= as_of_time",
        }
    except Exception as exc:
        return {"status": "degraded", "store_available": False, "error": str(exc)[:180]}


def collect_backtest_queue() -> Dict[str, Any]:
    try:
        from app.api.v1.endpoints.strategy import BACKTEST_TASKS

        tasks = list(BACKTEST_TASKS.values())
        by_status: Dict[str, int] = {}
        for task in tasks:
            status = str(task.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        active_count = sum(by_status.get(key, 0) for key in ["queued", "running", "cancelling"])
        return {
            "status": "ready",
            "queue_scope": "in_process_memory",
            "total_tasks": len(tasks),
            "active_tasks": active_count,
            "queued": by_status.get("queued", 0),
            "running": by_status.get("running", 0),
            "cancelling": by_status.get("cancelling", 0),
            "completed": by_status.get("completed", 0),
            "completed_with_errors": by_status.get("completed_with_errors", 0),
            "failed": by_status.get("failed", 0),
            "cancelled": by_status.get("cancelled", 0),
            "max_parallel": 5,
            "cancel_supported": True,
            "retry_supported": True,
        }
    except Exception as exc:
        return {"status": "degraded", "queue_scope": "in_process_memory", "error": str(exc)[:180]}


def collect_duckdb_archive(limit: int = 5) -> Dict[str, Any]:
    try:
        from app.services.backtest_duckdb_store import BACKTEST_DUCKDB_PATH, BACKTEST_DUCKDB_SCHEMA_VERSION, backtest_duckdb_store

        rows = backtest_duckdb_store.latest_results(limit=limit)
        path = Path(BACKTEST_DUCKDB_PATH)
        return {
            "status": "ready" if backtest_duckdb_store.available else "degraded",
            "available": backtest_duckdb_store.available,
            "path": str(path),
            "schema_version": BACKTEST_DUCKDB_SCHEMA_VERSION,
            "file_exists": path.exists(),
            "file_size_bytes": path.stat().st_size if path.exists() else 0,
            "latest_result_count": len(rows),
            "latest_results": rows,
            "pit_rule": PIT_RULE,
        }
    except Exception as exc:
        return {"status": "degraded", "available": False, "error": str(exc)[:180]}


async def collect_audit_health() -> Dict[str, Any]:
    try:
        from app.services.database import get_db

        async with get_db() as session:
            exists = await table_exists(session, "audit_logs")
            if not exists:
                return {
                    "status": "declared",
                    "append_only": True,
                    "row_count": 0,
                    "hash_coverage": "0/0",
                    "detail": "audit_logs table not found in connected database",
                }
            count = safe_int(await scalar(session, "SELECT COUNT(*) FROM audit_logs"))
            payload_hash_count = safe_int(await scalar(session, "SELECT COUNT(*) FROM audit_logs WHERE payload_hash IS NOT NULL"))
            immutable_false = safe_int(await scalar(session, "SELECT COUNT(*) FROM audit_logs WHERE immutable IS DISTINCT FROM TRUE"))
            latest = await scalar(session, "SELECT MAX(created_at) FROM audit_logs")
            trigger_exists = bool(
                await scalar(
                    session,
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM pg_trigger
                      WHERE tgname = 'trg_prevent_audit_logs_mutation'
                    )
                    """,
                )
            )
            status = "ready" if trigger_exists and immutable_false == 0 else "partial"
            return {
                "status": status,
                "append_only": trigger_exists,
                "immutable_rows": count - immutable_false,
                "mutable_rows": immutable_false,
                "row_count": count,
                "payload_hash_count": payload_hash_count,
                "hash_coverage": f"{payload_hash_count}/{count}",
                "latest_created_at": to_iso(latest),
                "age_seconds": age_seconds(latest),
                "export_api": "/api/v1/audit/records/{audit_id}/export",
                "replayable": True,
            }
    except Exception as exc:
        return {"status": "degraded", "append_only": True, "row_count": 0, "error": str(exc)[:180]}


async def collect_execution_risk_health() -> Dict[str, Any]:
    try:
        from app.services.database import get_db
        from app.services.risk_manager import risk_manager

        async with get_db() as session:
            paper_trade_count = safe_int(await scalar(session, "SELECT COUNT(*) FROM paper_trades")) if await table_exists(session, "paper_trades") else 0
            open_position_count = safe_int(await scalar(session, "SELECT COUNT(*) FROM paper_positions WHERE quantity != 0")) if await table_exists(session, "paper_positions") else 0
            risk_event_count = safe_int(await scalar(session, "SELECT COUNT(*) FROM risk_events")) if await table_exists(session, "risk_events") else 0
            risk_blocked_count = safe_int(
                await scalar(
                    session,
                    """
                    SELECT COUNT(*) FROM audit_logs
                    WHERE action = 'RISK_BLOCKED'
                       OR event_type = 'RISK_BLOCKED'
                       OR risk_status = 'BLOCKED'
                    """,
                )
            ) if await table_exists(session, "audit_logs") else 0
        config = await risk_manager.get_config()
        return {
            "status": "ready",
            "riskguard": {
                "status": "ready",
                "fail_action_default": "block",
                "rules": [
                    "MAX_SINGLE_POSITION_PCT",
                    "MAX_TOTAL_EXPOSURE_PCT",
                    "MAX_DAILY_LOSS_PCT",
                    "MAX_TOTAL_DRAWDOWN_PCT",
                    "MAX_LEVERAGE",
                    "MIN_ORDER_NOTIONAL",
                    "FORBIDDEN_SYMBOLS",
                    "WAIT_ORDER_INTENT_POLICY",
                ],
                "forbidden_symbols": config.get("FORBIDDEN_SYMBOLS", []),
                "max_single_position_pct": config.get("MAX_SINGLE_POSITION_PCT"),
                "max_total_exposure_pct": config.get("MAX_TOTAL_EXPOSURE_PCT"),
                "min_order_notional": config.get("MIN_ORDER_NOTIONAL"),
                "wait_order_intent_policy": config.get("WAIT_ORDER_INTENT_POLICY"),
                "configured_failure_action": config.get("RISK_FAILURE_ACTION"),
                "effective_failure_action": "block",
                "bypass_allowed": False,
            },
            "simulation": {
                "paper_trade_count": paper_trade_count,
                "open_position_count": open_position_count,
                "risk_event_count": risk_event_count,
                "risk_blocked_count": risk_blocked_count,
                "real_ordering_enabled": False,
            },
            "chain": ["OrderIntent", "RiskGuard", "PaperOrder", "PnL", "AuditRecord"],
        }
    except Exception as exc:
        return {"status": "degraded", "error": str(exc)[:180], "chain": ["OrderIntent", "RiskGuard", "PaperOrder", "PnL", "AuditRecord"]}


def collect_llm_monitor(tradingagents_config: Dict[str, Any]) -> Dict[str, Any]:
    llm = tradingagents_config.get("llm", {}) if isinstance(tradingagents_config, dict) else {}
    service = tradingagents_config.get("service", {}) if isinstance(tradingagents_config, dict) else {}
    mode = tradingagents_config.get("mode", {}) if isinstance(tradingagents_config, dict) else {}
    return {
        "status": tradingagents_config.get("overall_status", "check") if isinstance(tradingagents_config, dict) else "check",
        "provider": llm.get("provider", "unknown"),
        "model": llm.get("model", "unknown"),
        "quick_model": llm.get("quickModel"),
        "deep_model": llm.get("deepModel"),
        "base_url": llm.get("baseUrl", ""),
        "service_status": service.get("status", "unknown"),
        "timeout_seconds": service.get("timeout_seconds"),
        "mode": mode.get("configured", "unknown"),
        "full_graph_ready": bool(mode.get("fullGraphReady")),
        "call_monitoring": "contract_declared",
    }


def collect_resources() -> Dict[str, Any]:
    try:
        import psutil

        process = psutil.Process(os.getpid())
        memory = process.memory_info()
        return {
            "status": "ready",
            "process_pid": os.getpid(),
            "process_rss_mb": round(memory.rss / (1024 * 1024), 2),
            "cpu_percent": process.cpu_percent(interval=None),
            "open_files": len(process.open_files()),
        }
    except Exception as exc:
        return {
            "status": "declared",
            "process_pid": os.getpid(),
            "error": str(exc)[:180],
            "detail": "psutil unavailable; runtime resource contract is still declared",
        }


async def build_phase2_ops_monitor(tradingagents_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the Phase 2 operations monitor payload."""
    tradingagents_config = tradingagents_config or {}
    data_freshness = await collect_postgres_summaries(DATA_FRESHNESS_TABLES)
    core_tables = await collect_postgres_summaries(CORE_DB_TABLES)
    pipeline_storage = collect_pipeline_storage()
    backtest_queue = collect_backtest_queue()
    duckdb_archive = collect_duckdb_archive()
    audit_health = await collect_audit_health()
    execution_risk = await collect_execution_risk_health()
    llm_monitor = collect_llm_monitor(tradingagents_config)
    resources = collect_resources()

    sections = [
        {
            "key": "data_freshness",
            "label": "Data freshness",
            "status": overall_status(item["status"] for item in data_freshness.values()),
            "api": "/api/v1/meta/coverage",
        },
        {
            "key": "tradingagents",
            "label": "TradingAgents",
            "status": tradingagents_config.get("overall_status", "check"),
            "api": "/api/v1/system/tradingagents-config",
        },
        {
            "key": "audit",
            "label": "Audit health",
            "status": audit_health.get("status", "check"),
            "api": "/api/v1/audit/overview",
        },
        {
            "key": "execution_risk",
            "label": "Execution and RiskGuard",
            "status": execution_risk.get("status", "check"),
            "api": "/api/v1/risk/config-metadata",
        },
        {
            "key": "backtest_replay",
            "label": "Backtest and replay",
            "status": overall_status([backtest_queue.get("status", "check"), duckdb_archive.get("status", "check")]),
            "api": "/api/v1/strategy/backtest/tasks",
        },
        {
            "key": "resources",
            "label": "Resources",
            "status": resources.get("status", "check"),
            "api": "/api/v1/system/health",
        },
    ]
    return {
        "schema_version": PHASE2_OPS_MONITOR_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "overall_status": overall_status(section["status"] for section in sections),
        "pit_rule": PIT_RULE,
        "agent_input_policy": AGENT_INPUT_POLICY,
        "external_fallback_allowed": False,
        "sections": sections,
        "data_freshness": data_freshness,
        "core_tables": core_tables,
        "pipeline_storage": pipeline_storage,
        "tradingagents": {
            "status": tradingagents_config.get("overall_status", "check"),
            "enabled": tradingagents_config.get("enabled"),
            "mode": tradingagents_config.get("mode", {}),
            "service": tradingagents_config.get("service", {}),
            "data_boundary": tradingagents_config.get("data_boundary", {}),
            "readiness": tradingagents_config.get("readiness", []),
        },
        "llm_monitor": llm_monitor,
        "audit_health": audit_health,
        "execution_risk": execution_risk,
        "backtest_replay": {
            "queue": backtest_queue,
            "duckdb_archive": duckdb_archive,
            "replay_table": core_tables.get("replay_sessions", {}),
            "result_table": core_tables.get("backtest_results", {}),
        },
        "errors": [
            item
            for item in [
                data_freshness.get("bar_1m", {}).get("error"),
                audit_health.get("error"),
                execution_risk.get("error"),
                pipeline_storage.get("error"),
                duckdb_archive.get("error"),
            ]
            if item
        ],
        "resources": resources,
    }
