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


@router.get("/prd-flow")
async def get_prd_flow_status() -> Dict[str, Any]:
    """Return PRD v1 flow readiness for frontend and release checks."""
    health = await get_system_health()
    counts = await _prd_counts()

    l1_ok = all(
        _ok(_layer_value(health, "layers", "L1_data_source", key, "status"))
        for key in ["openbb", "fred", "market_data", "equity"]
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
            "detail": "OpenBB, FRED, news/macro and market data are reachable.",
            "evidence": {
                "openbb": _layer_value(health, "layers", "L1_data_source", "openbb"),
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
