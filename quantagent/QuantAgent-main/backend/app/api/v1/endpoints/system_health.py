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

    # Binance connectivity
    try:
        from app.services.binance_service import binance_service

        t_binance = time.time()
        price = await binance_service.get_price("BTCUSDT")
        latency = (time.time() - t_binance) * 1000
        l1_checks["binance"] = {
            "status": "ok",
            "detail": f"BTC/USDT = {price}",
            "latency_ms": round(latency, 1),
        }
    except Exception as e:
        l1_checks["binance"] = {"status": "error", "detail": str(e)[:100]}

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
            from app.services.duckdb_service import duckdb_service

            base = duckdb_service._data_dir()
            import os
            import glob as g

            parquet_files = g.glob(os.path.join(base, "**", "*.parquet"), recursive=True)
            total_size = sum(os.path.getsize(f) for f in parquet_files) if parquet_files else 0
            l4_checks["parquet"] = {
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
                l5_checks["counts"] = {
                    "factor_snapshots": factor_count,
                    "signal_events": signal_count,
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
        from app.agents.tradingagents_adapter import TradingAgentsAdapter

        l6_checks["tradingagents"] = {
            "status": "ok" if TradingAgentsAdapter.available else "unavailable",
            "detail": "TradingAgents (13+ agents, 5 stages)" if TradingAgentsAdapter.available else "TradingAgents not installed — fallback active",
        }
    except Exception as e:
        l6_checks["tradingagents"] = {"status": "error", "detail": str(e)[:100]}

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
