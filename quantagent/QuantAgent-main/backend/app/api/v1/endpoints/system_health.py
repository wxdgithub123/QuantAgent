"""System health endpoint — L1-L6 pipeline status aggregation."""

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def get_system_health() -> Dict[str, Any]:
    """Aggregate L1-L6 pipeline health and return per-layer status."""
    t0 = time.time()
    layers: Dict[str, Dict[str, Any]] = {}

    # ── L1: Data Sources ──────────────────────────────────────────────
    l1_checks: Dict[str, Any] = {}
    openbb_available = False
    try:
        from app.services.openbb_data_service import openbb_data_service

        openbb_available = openbb_data_service.available
        l1_checks["openbb"] = {
            "status": "ok" if openbb_available else "unavailable",
            "provider": "yfinance",
            "detail": "OpenBB SDK available" if openbb_available else "OpenBB not installed",
        }
    except Exception as e:
        l1_checks["openbb"] = {"status": "error", "detail": str(e)}

    # Market data connectivity (local storage/OpenBB first)
    try:
        from app.services.market_data_gateway import market_data_gateway

        t_market = time.time()
        price = await market_data_gateway.get_price("BTCUSDT")
        latency = (time.time() - t_market) * 1000
        l1_checks["market_data"] = {
            "status": "ok" if price is not None else "error",
            "detail": f"BTC/USDT = {price}",
            "latency_ms": round(latency, 1),
        }
    except Exception as e:
        l1_checks["market_data"] = {"status": "error", "detail": str(e)[:100]}

    # CCXT exchange connector registry. This is a lightweight capability check;
    # live exchange pings remain explicit because they can be slow or region-limited.
    try:
        from app.services.exchange_service import exchange_service

        exchanges = exchange_service.get_supported_exchanges()
        l1_checks["ccxt"] = {
            "status": "ok" if exchanges else "unavailable",
            "provider": "ccxt",
            "exchanges": [item["id"] for item in exchanges],
            "detail": f"CCXT connector ready for {len(exchanges)} exchanges",
        }
    except Exception as e:
        l1_checks["ccxt"] = {"status": "error", "detail": str(e)[:100]}

    # FRED economic data
    try:
        from app.services.macro_analysis_service import MacroAnalysisService

        l1_checks["fred"] = {
            "status": "ok" if openbb_available else "unavailable",
            "indicators": ["FEDFUNDS", "DGS10", "T10YIE", "M2SL"],
            "detail": "FRED via OpenBB" if openbb_available else "needs OpenBB",
        }
    except Exception as e:
        l1_checks["fred"] = {"status": "error", "detail": str(e)[:100]}

    # Equity/stock data via OpenBB
    try:
        from app.services.openbb_data_service import openbb_data_service

        ticker = await openbb_data_service.get_equity_ticker("SPY")
        l1_checks["equity"] = {
            "status": "ok" if ticker is not None else "unavailable",
            "symbol": "SPY",
            "detail": f"SPY = {ticker.price}" if ticker else "OpenBB equity data unavailable",
        }
    except Exception as e:
        l1_checks["equity"] = {"status": "error", "detail": str(e)[:100]}

    layers["L1_data_source"] = l1_checks

    # ── L2: Unified Access ───────────────────────────────────────────
    l2_checks: Dict[str, Any] = {}
    try:
        from app.core.bus import BacktestDataAdapter

        adapter = BacktestDataAdapter()
        l2_checks["adapter"] = {"status": "ok", "detail": "BacktestDataAdapter initialized"}
    except Exception as e:
        l2_checks["adapter"] = {"status": "error", "detail": str(e)[:100]}

    layers["L2_unified_access"] = l2_checks

    # ── L3: Standardization ──────────────────────────────────────────
    l3_checks: Dict[str, Any] = {}
    try:
        from app.models.instrument import Instrument

        inst = Instrument.from_raw("BTCUSDT")
        l3_checks["instrument"] = {
            "status": "ok",
            "detail": f"BTCUSDT → base={inst.base_asset} quote={inst.quote_asset} ccxt={inst.ccxt_symbol}",
        }
    except Exception as e:
        l3_checks["instrument"] = {"status": "error", "detail": str(e)[:100]}

    try:
        from app.models.trading import BarData

        l3_checks["bar_data"] = {"status": "ok", "detail": "BarData model available"}
    except Exception as e:
        l3_checks["bar_data"] = {"status": "error", "detail": str(e)[:100]}

    layers["L3_standardization"] = l3_checks

    # ── L4: Storage ──────────────────────────────────────────────────
    l4_checks: Dict[str, Any] = {}
    try:
        from app.services.storage_factory import get_storage_service

        storage = get_storage_service()
        storage_name = type(storage).__name__
        storage_available = False
        try:
            storage_available = await storage.ping()
        except Exception:
            pass

        l4_checks["backend"] = {
            "status": "ok" if storage_available else "degraded",
            "name": storage_name,
            "detail": f"Active: {storage_name}",
        }

        # DuckDB file stats
        try:
            from app.services.duckdb_service import _data_dir, duckdb_service

            base = _data_dir()
            import os
            import glob as g

            parquet_files = g.glob(os.path.join(base, "**", "*.parquet"), recursive=True)
            total_size = sum(os.path.getsize(f) for f in parquet_files) if parquet_files else 0
            l4_checks["parquet"] = {
                "status": "ok" if duckdb_service.available else "unavailable",
                "files": len(parquet_files),
                "size_mb": round(total_size / (1024 * 1024), 2),
                "path": base,
            }
        except Exception:
            l4_checks["parquet"] = {"files": 0, "size_mb": 0, "detail": "DuckDB not active"}

        # ClickHouse counterpart
        try:
            from app.services.clickhouse_service import clickhouse_service

            ch_ok = await clickhouse_service.ping()
            l4_checks["clickhouse"] = {
                "status": "ok" if ch_ok else "unavailable",
                "detail": "ClickHouse connected" if ch_ok else "ClickHouse unavailable",
            }
            source_ranges = await clickhouse_service.get_market_bar_source_ranges()
            l4_checks["market_bars"] = {
                "status": "ok" if ch_ok else "unavailable",
                "source_groups": len(source_ranges),
                "sample": source_ranges[:5],
                "detail": "Source-aware market_bars table ready",
            }
        except Exception:
            l4_checks["clickhouse"] = {"status": "unavailable"}
    except Exception as e:
        l4_checks["backend"] = {"status": "error", "detail": str(e)[:100]}

    layers["L4_storage"] = l4_checks

    # ── L5: Factors & Signals ────────────────────────────────────────
    l5_checks: Dict[str, Any] = {}
    try:
        from app.models.signal import FactorSnapshot, SignalEvent

        l5_checks["models"] = {"status": "ok", "detail": "FactorSnapshot + SignalEvent models OK"}
    except Exception as e:
        l5_checks["models"] = {"status": "error", "detail": str(e)[:100]}

    try:
        from app.services.factor_signal_pipeline import DEFAULT_STRATEGIES, factor_signal_pipeline
        from app.services.analysis_context_builder import analysis_context_builder
        from app.services.news_enrichment_service import news_enrichment_service

        l5_checks["pipeline"] = {
            "status": "ok",
            "detail": "On-demand L1-L5 factor/signal generation, news enrichment, and AnalysisContext assembly available",
            "default_strategies": DEFAULT_STRATEGIES,
            "service": type(factor_signal_pipeline).__name__,
            "context_builder": type(analysis_context_builder).__name__,
            "news_enrichment": type(news_enrichment_service).__name__,
        }
    except Exception as e:
        l5_checks["pipeline"] = {"status": "error", "detail": str(e)[:100]}

    # Check table counts if DB is connected
    try:
        from app.services.database import get_db

        async with get_db() as session:
            try:
                from sqlalchemy import text

                r = await session.execute(text("SELECT COUNT(*) FROM factor_snapshots"))
                factor_count = r.scalar() or 0
                r = await session.execute(text("SELECT COUNT(*) FROM signal_events"))
                signal_count = r.scalar() or 0
                r = await session.execute(text("SELECT MAX(timestamp) FROM factor_snapshots"))
                latest_factor_ts = r.scalar()
                r = await session.execute(text("SELECT MAX(timestamp) FROM signal_events"))
                latest_signal_ts = r.scalar()
                l5_checks["counts"] = {
                    "factor_snapshots": factor_count,
                    "signal_events": signal_count,
                    "latest_factor_timestamp": latest_factor_ts.isoformat() if latest_factor_ts else None,
                    "latest_signal_timestamp": latest_signal_ts.isoformat() if latest_signal_ts else None,
                    "status": "ok",
                }
            except Exception as e:
                l5_checks["counts"] = {"status": "empty", "detail": str(e)[:100]}
    except Exception as e:
        l5_checks["counts"] = {"status": "unavailable", "detail": str(e)[:100]}

    layers["L5_factors_signals"] = l5_checks

    # ── L6: Decision ─────────────────────────────────────────────────
    l6_checks: Dict[str, Any] = {}
    try:
        from app.agents.tradingagents_adapter import tradingagents_adapter
        from app.core.config import settings

        service_health = await tradingagents_adapter.health()
        l6_checks["tradingagents_service"] = {
            "status": service_health.get("status", "unavailable"),
            "enabled": settings.USE_TRADINGAGENTS,
            "detail": service_health,
        }
    except Exception as e:
        l6_checks["tradingagents_service"] = {"status": "error", "detail": str(e)[:100]}

    try:
        from app.agents.coordinator_agent import CoordinatorAgent

        l6_checks["coordinator"] = {
            "status": "ok",
            "detail": "CoordinatorAgent (3-agent voting) available",
        }
    except Exception as e:
        l6_checks["coordinator"] = {"status": "error", "detail": str(e)[:100]}

    layers["L6_decision"] = l6_checks

    # ── Infrastructure ───────────────────────────────────────────────
    infra: Dict[str, Any] = {}

    # PostgreSQL
    try:
        from app.services.database import check_db_connection

        db_ok = await check_db_connection()
        infra["postgresql"] = "connected" if db_ok else "unavailable"
    except Exception:
        infra["postgresql"] = "unavailable"

    # Redis
    try:
        from app.services.database import get_redis

        r = get_redis()
        if r:
            await r.ping()
            infra["redis"] = "connected"
        else:
            infra["redis"] = "unavailable"
    except Exception:
        infra["redis"] = "unavailable"

    # NATS
    try:
        from app.services.ingestion_service import ingestion_service

        if ingestion_service.running and ingestion_service.nc and ingestion_service.nc.is_connected:
            infra["nats"] = "connected"
        else:
            infra["nats"] = "disconnected"
    except Exception:
        infra["nats"] = "unknown"

    total_ms = (time.time() - t0) * 1000

    return {
        "timestamp": int(time.time()),
        "duration_ms": round(total_ms, 1),
        "layers": layers,
        "infrastructure": infra,
    }


def _ok(value: Any) -> bool:
    return value in {"ok", "connected"}


def _layer_value(health: Dict[str, Any], *path: str) -> Any:
    current: Any = health
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


async def _prd_counts() -> Dict[str, int]:
    counts = {
        "factor_snapshots": 0,
        "signal_events": 0,
        "coordination_history": 0,
        "backtest_results": 0,
        "replay_sessions": 0,
    }
    try:
        from sqlalchemy import text
        from app.services.database import get_db

        async with get_db() as session:
            for table_name in counts:
                result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                counts[table_name] = int(result.scalar() or 0)
    except Exception as exc:
        logger.debug(f"PRD flow count collection failed: {exc}")
    return counts


async def _prd106_extra_counts() -> Dict[str, int]:
    """Collect fixed-table counts used by the frontend/API monitor."""
    queries = {
        "factor_definitions": "SELECT COUNT(*) FROM factor_definitions",
        "audit_logs": "SELECT COUNT(*) FROM audit_logs",
        "completed_replays": "SELECT COUNT(*) FROM replay_sessions WHERE status = 'completed'",
        "pit_backtests": "SELECT COUNT(*) FROM backtest_results WHERE metrics ? 'pit'",
        "pit_repro_backtests": (
            "SELECT COUNT(*) FROM backtest_results "
            "WHERE metrics->'pit'->>'schema_version' = 'pit-repro-v1'"
        ),
        "strict_comparison_ready": """
            SELECT COUNT(DISTINCT rs.id)
            FROM replay_sessions rs
            JOIN backtest_results bt ON bt.id = rs.backtest_id
            WHERE rs.status = 'completed'
        """,
    }
    counts = {key: 0 for key in queries}
    try:
        from sqlalchemy import text
        from app.services.database import get_db

        async with get_db() as session:
            for key, sql in queries.items():
                result = await session.execute(text(sql))
                counts[key] = int(result.scalar() or 0)
    except Exception as exc:
        logger.debug(f"PRD 10.6 extra count collection failed: {exc}")
    return counts


async def _market_coverage_summary() -> Dict[str, Any]:
    """Return compact ClickHouse market-bar coverage without exposing rows."""
    summary: Dict[str, Any] = {
        "source_groups": 0,
        "total_rows": 0,
        "providers": [],
        "exchanges": [],
    }
    try:
        from app.services.clickhouse_service import clickhouse_service

        ranges = await clickhouse_service.get_market_bar_source_ranges()
        providers = sorted({str(row.get("provider") or "unknown") for row in ranges})
        exchanges = sorted({str(row.get("exchange") or "unknown") for row in ranges})
        summary.update(
            {
                "source_groups": len(ranges),
                "total_rows": sum(int(row.get("row_count") or 0) for row in ranges),
                "providers": providers,
                "exchanges": exchanges,
            }
        )
    except Exception as exc:
        summary["error"] = str(exc)[:160]
    return summary


def _status_label(value: Any) -> str:
    if _ok(value):
        return "ready"
    if value in {"degraded", "partial"}:
        return "partial"
    return "check"


def _feature_status(*conditions: bool) -> str:
    return "ready" if all(conditions) else "check"


@router.get("/prd-flow")
async def get_prd_flow_status() -> Dict[str, Any]:
    """Return PRD v1 flow readiness for frontend and release checks."""
    health = await get_system_health()
    counts = await _prd_counts()

    l1_ok = all(
        _ok(_layer_value(health, "layers", "L1_data_source", key, "status"))
        for key in ["openbb", "ccxt", "fred", "market_data", "equity"]
    )
    l4_ok = (
        _ok(_layer_value(health, "layers", "L4_storage", "clickhouse", "status"))
        and _ok(_layer_value(health, "infrastructure", "postgresql"))
        and _ok(_layer_value(health, "infrastructure", "redis"))
    )
    l5_ok = (
        _ok(_layer_value(health, "layers", "L5_factors_signals", "pipeline", "status"))
        and _ok(_layer_value(health, "layers", "L5_factors_signals", "counts", "status"))
        and counts["factor_snapshots"] > 0
        and counts["signal_events"] > 0
    )
    l6_ok = (
        _ok(_layer_value(health, "layers", "L6_decision", "tradingagents_service", "status"))
        and _ok(_layer_value(health, "layers", "L6_decision", "coordinator", "status"))
        and counts["coordination_history"] > 0
    )
    replay_ok = counts["backtest_results"] > 0 and counts["replay_sessions"] > 0

    stages = [
        {
            "id": "data_ingestion",
            "label": "10.1 Data ingestion",
            "status": "ok" if l1_ok else "check",
            "detail": "OpenBB, CCXT, FRED, news/macro and market data are reachable.",
            "evidence": {
                "openbb": _layer_value(health, "layers", "L1_data_source", "openbb"),
                "ccxt": _layer_value(health, "layers", "L1_data_source", "ccxt"),
                "fred": _layer_value(health, "layers", "L1_data_source", "fred"),
                "market_data": _layer_value(health, "layers", "L1_data_source", "market_data"),
                "equity": _layer_value(health, "layers", "L1_data_source", "equity"),
            },
        },
        {
            "id": "standard_storage",
            "label": "10.2 Standardization and storage",
            "status": "ok" if l4_ok else "check",
            "detail": "Standard models, PostgreSQL, Redis and ClickHouse are ready; DuckDB/Parquet stats are reported separately.",
            "evidence": {
                "storage": _layer_value(health, "layers", "L4_storage"),
                "infrastructure": health.get("infrastructure"),
            },
        },
        {
            "id": "factors_signals",
            "label": "10.3 Factors and signals",
            "status": "ok" if l5_ok else "check",
            "detail": "L5 factor/signal pipeline and point-in-time AnalysisContext assembly are available.",
            "evidence": {
                "counts": {
                    "factor_snapshots": counts["factor_snapshots"],
                    "signal_events": counts["signal_events"],
                },
                "pipeline": _layer_value(health, "layers", "L5_factors_signals", "pipeline"),
            },
        },
        {
            "id": "tradingagents_decision",
            "label": "10.4 TradingAgents decisioning",
            "status": "ok" if l6_ok else "check",
            "detail": "Coordinator and isolated TradingAgents service are connected with persisted audit history.",
            "evidence": {
                "coordination_history": counts["coordination_history"],
                "decision": _layer_value(health, "layers", "L6_decision"),
            },
        },
        {
            "id": "backtest_replay_audit",
            "label": "10.5 Backtest, replay and audit",
            "status": "ok" if replay_ok else "check",
            "detail": "Backtest results and replay sessions exist and can be linked for review.",
            "evidence": {
                "backtest_results": counts["backtest_results"],
                "replay_sessions": counts["replay_sessions"],
            },
        },
        {
            "id": "frontend_api",
            "label": "10.6 Frontend and API",
            "status": "ok",
            "detail": "Dashboard, data source management, signals, decisions, replay and backtest pages are exposed through the Next.js frontend.",
            "evidence": {
                "pages": ["/dashboard", "/data-sources", "/signals", "/decisions", "/replay", "/backtest"],
            },
        },
    ]

    overall_status = "ok" if all(stage["status"] == "ok" for stage in stages) else "check"
    return {
        "timestamp": int(time.time()),
        "overall_status": overall_status,
        "counts": counts,
        "stages": stages,
    }


@router.get("/frontend-api-overview")
async def get_frontend_api_overview() -> Dict[str, Any]:
    """Return the PRD 10.6 frontend/API visibility map for the monitor page."""
    health = await get_system_health()
    counts = await _prd_counts()
    counts.update(await _prd106_extra_counts())
    coverage = await _market_coverage_summary()

    pipeline_stats: Dict[str, Any] = {}
    try:
        from app.pipeline.orchestrator import pipeline_orchestrator
        from app.pipeline.storage.duckdb_store import pipeline_store

        pipeline_stats = pipeline_orchestrator.stats()
        pipeline_stats["store_available"] = pipeline_store.available
    except Exception as exc:
        pipeline_stats = {"error": str(exc)[:160]}

    openbb_status = _layer_value(health, "layers", "L1_data_source", "openbb", "status")
    ccxt_status = _layer_value(health, "layers", "L1_data_source", "ccxt", "status")
    fred_status = _layer_value(health, "layers", "L1_data_source", "fred", "status")
    equity_status = _layer_value(health, "layers", "L1_data_source", "equity", "status")
    clickhouse_status = _layer_value(health, "layers", "L4_storage", "clickhouse", "status")
    factor_status = _layer_value(health, "layers", "L5_factors_signals", "counts", "status")
    tradingagents_status = _layer_value(health, "layers", "L6_decision", "tradingagents_service", "status")

    infrastructure = health.get("infrastructure", {})
    ccxt_exchanges = _layer_value(health, "layers", "L1_data_source", "ccxt", "exchanges") or []
    if not isinstance(ccxt_exchanges, list):
        ccxt_exchanges = []

    features = [
        {
            "key": "data_source_management",
            "title": "数据源管理",
            "status": _feature_status(
                bool(_ok(openbb_status) or _ok(ccxt_status)),
                bool(_ok(clickhouse_status) or coverage["total_rows"] > 0),
            ),
            "front_page": "/data-sources",
            "page_label": "数据源工作台",
            "description": "查看 OpenBB、CCXT、宏观/新闻管道和 ClickHouse 本地缓存状态；手动触发小范围补数或归档测试。",
            "apis": [
                {"method": "GET", "path": "/api/v1/system/health", "purpose": "数据源和基础设施健康"},
                {"method": "GET", "path": "/api/v1/market/data-ingestion-overview", "purpose": "10.1 数据接入总览"},
                {"method": "GET", "path": "/api/v1/market/source-coverage", "purpose": "K线缓存覆盖范围"},
                {"method": "GET", "path": "/api/v1/market/klines/{symbol}?provider=yfinance&fallback_exchange=okx", "purpose": "crypto provider 和备用源读取"},
                {"method": "GET", "path": "/api/v1/market/backfill/status", "purpose": "补数状态"},
                {"method": "POST", "path": "/api/v1/market/backfill", "purpose": "手动小范围补数测试"},
            ],
            "evidence": [
                {"label": "OpenBB", "value": str(openbb_status or "unknown")},
                {"label": "CCXT连接器", "value": f"{len(ccxt_exchanges)} 个已注册，实盘可用需逐个测试"},
                {"label": "ClickHouse缓存", "value": f"{coverage['source_groups']} 组 / {coverage['total_rows']} 行"},
                {"label": "宏观/新闻", "value": f"{pipeline_stats.get('macro_stored', 0)} 条宏观，{pipeline_stats.get('news_stored', 0)} 条新闻"},
            ],
        },
        {
            "key": "standardized_factors",
            "title": "标准化数据与因子查看",
            "status": _feature_status(counts["factor_snapshots"] > 0, counts["factor_definitions"] > 0),
            "front_page": "/signals",
            "page_label": "因子/信号",
            "description": "查看因子字典、因子快照、信号事件和因子时序；页面会区分计算来源与上游数据来源。",
            "apis": [
                {"method": "GET", "path": "/api/v1/signals/factor-definitions", "purpose": "因子类型字典"},
                {"method": "GET", "path": "/api/v1/signals/factors", "purpose": "因子快照明细"},
                {"method": "GET", "path": "/api/v1/signals/events", "purpose": "策略信号事件"},
                {"method": "GET", "path": "/api/v1/signals/context/{symbol}", "purpose": "AnalysisContext 输入材料"},
            ],
            "evidence": [
                {"label": "因子类型", "value": f"{counts['factor_definitions']} 个"},
                {"label": "因子快照", "value": f"{counts['factor_snapshots']} 条"},
                {"label": "信号事件", "value": f"{counts['signal_events']} 条"},
                {"label": "PIT能力", "value": str(factor_status or "unknown")},
            ],
        },
        {
            "key": "backtest_tasks",
            "title": "回测任务",
            "status": _feature_status(counts["backtest_results"] > 0),
            "front_page": "/backtest",
            "page_label": "回测",
            "description": "创建策略回测、查看历史结果、参数优化和组合对比；回测结果进入数据库并可被审计页引用。",
            "apis": [
                {"method": "POST", "path": "/api/v1/strategy/backtest/run", "purpose": "运行回测"},
                {"method": "GET", "path": "/api/v1/strategy/backtest/history", "purpose": "回测历史"},
                {"method": "POST", "path": "/api/v1/strategy/backtest/batch", "purpose": "批量回测"},
                {"method": "POST", "path": "/api/v1/strategy/optimize", "purpose": "参数优化"},
            ],
            "evidence": [
                {"label": "回测结果", "value": f"{counts['backtest_results']} 条"},
                {"label": "PIT回测", "value": f"{counts['pit_backtests']} 条"},
                {"label": "完整复现包", "value": f"{counts['pit_repro_backtests']} 条"},
            ],
        },
        {
            "key": "audit_view",
            "title": "审计查看",
            "status": _feature_status(
                counts["audit_logs"] > 0,
                counts["backtest_results"] > 0,
                counts["replay_sessions"] > 0,
            ),
            "front_page": "/audit",
            "page_label": "回测与审计",
            "description": "集中查看 point-in-time 回测、历史回放、审计日志、智能体决策和结果对比候选。",
            "apis": [
                {"method": "GET", "path": "/api/v1/audit/overview", "purpose": "审计工作台汇总"},
                {"method": "GET", "path": "/api/v1/replay/sessions", "purpose": "历史回放会话"},
                {"method": "GET", "path": "/api/v1/analytics/replay-backtest-comparison", "purpose": "回放与回测对比"},
                {"method": "GET", "path": "/api/v1/coordination/history", "purpose": "智能体决策历史"},
            ],
            "evidence": [
                {"label": "审计日志", "value": f"{counts['audit_logs']} 条"},
                {"label": "历史回放", "value": f"{counts['completed_replays']} / {counts['replay_sessions']} 已完成"},
                {"label": "严格可比样例", "value": f"{counts['strict_comparison_ready']} 条"},
                {"label": "决策历史", "value": f"{counts['coordination_history']} 条"},
            ],
        },
        {
            "key": "system_monitoring",
            "title": "系统状态监控",
            "status": _feature_status(
                _ok(infrastructure.get("postgresql")),
                _ok(infrastructure.get("redis")),
                bool(_ok(clickhouse_status) or coverage["total_rows"] > 0),
            ),
            "front_page": "/monitor",
            "page_label": "系统监控",
            "description": "把前端页面、后端接口、数据源、缓存、基础设施和 TradingAgents 状态放在一个页面里持续查看。",
            "apis": [
                {"method": "GET", "path": "/api/v1/system/frontend-api-overview", "purpose": "10.6 页面/API总览"},
                {"method": "GET", "path": "/api/v1/system/health", "purpose": "系统健康"},
                {"method": "GET", "path": "/api/v1/system/prd-flow", "purpose": "PRD全流程状态"},
                {"method": "GET", "path": "/api/v1/system/pipeline", "purpose": "新闻/宏观管道状态"},
            ],
            "evidence": [
                {"label": "PostgreSQL", "value": str(infrastructure.get("postgresql", "unknown"))},
                {"label": "Redis", "value": str(infrastructure.get("redis", "unknown"))},
                {"label": "ClickHouse", "value": str(clickhouse_status or "unknown")},
                {"label": "TradingAgents", "value": str(tradingagents_status or "unknown")},
            ],
        },
    ]

    pages = [
        {"path": "/dashboard", "label": "仪表盘", "role": "看加密行情、宏观、新闻和智能体概览"},
        {"path": "/data-sources", "label": "数据源工作台", "role": "管理 OpenBB/CCXT/缓存/补数状态"},
        {"path": "/signals", "label": "因子/信号", "role": "查看标准化数据加工后的因子和信号"},
        {"path": "/backtest", "label": "回测", "role": "创建和查看策略回测任务"},
        {"path": "/audit", "label": "回测与审计", "role": "查看 PIT、回放、审计、对比"},
        {"path": "/monitor", "label": "系统监控", "role": "查看 10.6 前端/API/服务状态"},
    ]

    source_notes = [
        {"name": "OpenBB", "role": "统一金融数据入口；当前主要通过 yfinance/FRED/OECD 等 provider 获取股票、宏观和部分行情能力。"},
        {"name": "CCXT", "role": "交易所连接器层；当前页面会标注已注册连接器，不把未实测交易所写成已连通。"},
        {"name": "ClickHouse", "role": "本地 K 线缓存和查询加速层；它不是上游数据源，真实来源会保存在 provider/exchange 字段。"},
        {"name": "TradingAgents", "role": "默认决策引擎；消费 AnalysisContext 后输出结构化建议，服务状态在监控页展示。"},
    ]

    return {
        "timestamp": int(time.time()),
        "overall_status": "ready" if all(item["status"] == "ready" for item in features) else "check",
        "features": features,
        "pages": pages,
        "counts": counts,
        "market_coverage": coverage,
        "pipeline": pipeline_stats,
        "source_notes": source_notes,
        "system": [
            {"label": "OpenBB", "status": _status_label(openbb_status), "detail": _layer_value(health, "layers", "L1_data_source", "openbb", "detail")},
            {"label": "CCXT", "status": _status_label(ccxt_status), "detail": f"{len(ccxt_exchanges)} 个连接器已注册"},
            {"label": "FRED/OECD", "status": _status_label(fred_status), "detail": "宏观指标入口"},
            {"label": "股票/yfinance", "status": _status_label(equity_status), "detail": _layer_value(health, "layers", "L1_data_source", "equity", "detail")},
            {"label": "PostgreSQL", "status": _status_label(infrastructure.get("postgresql")), "detail": "主数据、审计、回测和决策记录"},
            {"label": "Redis", "status": _status_label(infrastructure.get("redis")), "detail": "缓存和短生命周期状态"},
            {"label": "ClickHouse", "status": _status_label(clickhouse_status), "detail": f"{coverage['total_rows']} 行本地K线缓存"},
            {"label": "TradingAgents", "status": _status_label(tradingagents_status), "detail": "默认决策服务"},
        ],
    }


@router.get("/pipeline")
async def get_pipeline_stats():
    """Return pipeline orchestrator stats and storage counts."""
    from app.pipeline.orchestrator import pipeline_orchestrator
    from app.pipeline.storage.duckdb_store import pipeline_store

    stats = pipeline_orchestrator.stats()
    return {
        **stats,
        "store_available": pipeline_store.available,
    }


@router.post("/pipeline/macro/refresh", status_code=202)
async def trigger_macro_refresh():
    """Manually trigger a macro data refresh."""
    from app.pipeline.orchestrator import pipeline_orchestrator
    result = await pipeline_orchestrator.run_macro_now()
    return result


@router.post("/pipeline/news/refresh", status_code=202)
async def trigger_news_refresh():
    """Manually trigger a news data refresh."""
    from app.pipeline.orchestrator import pipeline_orchestrator
    result = await pipeline_orchestrator.run_news_now()
    return result
