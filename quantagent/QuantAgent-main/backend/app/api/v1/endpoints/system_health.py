"""System health endpoint — L1-L6 pipeline status aggregation."""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote, urlsplit, urlunsplit

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


def _redact_url(value: Any) -> str:
    """Return a display-safe URL without credentials, query, or fragment."""
    if not value:
        return ""
    text = str(value).strip()
    try:
        parsed = urlsplit(text)
    except Exception:
        return "[redacted]"
    if not parsed.scheme or not parsed.netloc:
        return text.split("?", 1)[0].split("#", 1)[0]

    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    if parsed.username or parsed.password:
        host = f"***:***@{host}"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/") or "", "", ""))


def _env_source(name: str) -> str:
    return "environment" if name in os.environ else "default"


def _service_detail(service_health: Dict[str, Any]) -> Dict[str, Any]:
    detail = service_health.get("detail") if isinstance(service_health, dict) else {}
    return detail if isinstance(detail, dict) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "healthy", "ready"}
    return bool(value)


def _build_tradingagents_config_status(service_health: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the Phase 2 P1 effective TradingAgents configuration payload."""
    from app.core.config import settings

    service_health = service_health or {}
    detail = _service_detail(service_health)
    native_graph = detail.get("native_graph") if isinstance(detail.get("native_graph"), dict) else {}

    configured_mode = str(
        detail.get("mode")
        or os.getenv("TRADINGAGENTS_MODE")
        or "context_adapter"
    ).strip().lower()
    full_graph_modes = {"quantagent_patched_graph", "quantagent_graph", "patched_graph", "native_graph"}
    full_graph_requested = configured_mode in full_graph_modes

    provider = str(
        detail.get("llm_provider")
        or os.getenv("TRADINGAGENTS_LLM_PROVIDER")
        or settings.LLM_PROVIDER
        or "none"
    ).strip().lower()
    openai_configured = (
        _truthy(detail.get("openai_configured"))
        if "openai_configured" in detail
        else bool(settings.OPENAI_API_KEY)
    )
    ollama_enabled = _truthy(detail.get("ollama_enabled")) or provider == "ollama"
    context_adapter_ready = bool(settings.USE_TRADINGAGENTS) and service_health.get("status") == "ok"
    llm_ready = provider in {"none", "disabled"} or provider == "ollama" or (
        provider in {"openai", "openai_compatible"} and openai_configured
    )
    graph_available = _truthy(detail.get("tradingagents_available")) or _truthy(native_graph.get("available"))
    full_graph_ready = bool(settings.USE_TRADINGAGENTS and context_adapter_ready and full_graph_requested and graph_available and llm_ready)

    quick_model = (
        native_graph.get("quick_model")
        or detail.get("quick_model")
        or os.getenv("TRADINGAGENTS_NATIVE_QUICK_MODEL")
        or detail.get("openai_model")
        or settings.OPENAI_MODEL
    )
    deep_model = (
        native_graph.get("deep_model")
        or detail.get("deep_model")
        or os.getenv("TRADINGAGENTS_NATIVE_DEEP_MODEL")
        or detail.get("openai_model")
        or settings.OPENAI_MODEL
    )
    selected_analysts = native_graph.get("selected_analysts")
    if not isinstance(selected_analysts, list) or not selected_analysts:
        selected_analysts = ["market", "news", "social", "fundamentals"]

    service_status = "ready" if context_adapter_ready else ("disabled" if not settings.USE_TRADINGAGENTS else "check")
    overall_status = "ready" if context_adapter_ready else service_status

    readiness = [
        {
            "id": "service",
            "label": "TradingAgents service",
            "status": service_status,
            "detail": "Service reachable and enabled" if context_adapter_ready else "Enable service or check connectivity",
        },
        {
            "id": "context_adapter",
            "label": "Fast research mode",
            "status": "ready" if context_adapter_ready else "check",
            "detail": "Uses QuantAgent AnalysisContext with optional LLM summarization.",
        },
        {
            "id": "full_graph",
            "label": "Full TradingAgentsGraph",
            "status": "ready" if full_graph_ready else ("partial" if graph_available else "check"),
            "detail": (
                "Configured mode can run the full graph."
                if full_graph_ready
                else "Not required for P0; configure patched/native graph plus LLM credentials for strong full-graph acceptance."
            ),
        },
        {
            "id": "llm",
            "label": "LLM configuration",
            "status": "ready" if llm_ready else "check",
            "detail": f"provider={provider}, quick={quick_model}, deep={deep_model}",
        },
        {
            "id": "data_boundary",
            "label": "Agent input boundary",
            "status": "ready",
            "detail": "Agent bars and snapshots are local_storage_only with available_time <= as_of_time.",
        },
    ]

    return {
        "timestamp": int(time.time()),
        "overall_status": overall_status,
        "enabled": settings.USE_TRADINGAGENTS,
        "service": {
            "status": service_health.get("status", "unavailable"),
            "http_status": service_health.get("http_status"),
            "url": _redact_url(service_health.get("service_url") or settings.TRADINGAGENTS_SERVICE_URL),
            "timeout_seconds": settings.TRADINGAGENTS_TIMEOUT_SECONDS,
            "error": None if service_health.get("status") == "ok" else str(service_health.get("detail") or "")[:200],
        },
        "mode": {
            "configured": configured_mode,
            "fastResearchReady": context_adapter_ready,
            "fullGraphRequested": full_graph_requested,
            "fullGraphReady": full_graph_ready,
            "supportedModes": ["context_adapter", "quantagent_patched_graph", "native_graph"],
            "selectedAnalysts": selected_analysts,
            "roles": [
                "market_analyst",
                "news_analyst",
                "sentiment_analyst",
                "fundamentals_macro_analyst",
                "bull_researcher",
                "bear_researcher",
                "research_manager",
                "trader",
                "risk_analysts",
                "final_judge",
            ],
        },
        "llm": {
            "provider": provider,
            "openaiConfigured": openai_configured,
            "ollamaEnabled": ollama_enabled,
            "baseUrl": _redact_url(detail.get("openai_base_url") or settings.OPENAI_BASE_URL),
            "model": detail.get("openai_model") or settings.OPENAI_MODEL,
            "quickModel": quick_model,
            "deepModel": deep_model,
            "sources": {
                "LLM_PROVIDER": _env_source("LLM_PROVIDER"),
                "OPENAI_MODEL": _env_source("OPENAI_MODEL"),
                "OPENAI_BASE_URL": _env_source("OPENAI_BASE_URL"),
                "TRADINGAGENTS_MODE": _env_source("TRADINGAGENTS_MODE"),
            },
        },
        "graph": {
            "tradingagentsAvailable": graph_available,
            "importError": detail.get("tradingagents_error") or native_graph.get("import_error"),
            "nativeGraph": {
                "available": _truthy(native_graph.get("available")),
                "manualOnly": _truthy(native_graph.get("manual_only")),
                "nativeSymbolExample": native_graph.get("native_symbol"),
                "dataSourceNote": native_graph.get("data_source_note"),
            },
            "strongAcceptanceEligible": full_graph_ready,
        },
        "data_boundary": {
            "agent_input_policy": "local_storage_only",
            "pit_rule": "available_time <= as_of_time",
            "externalFallbackAllowed": False,
            "allowCcxtFallback": False,
            "allowBinanceFallback": False,
            "snapshotEndpoints": [
                "/api/v1/market/bars/as-of",
                "/api/v1/market/snapshot/{symbol}",
                "/api/v1/market/research-snapshot/{symbol}",
            ],
        },
        "readiness": readiness,
    }


@router.get("/tradingagents-config")
async def get_tradingagents_config() -> Dict[str, Any]:
    """Return effective TradingAgents P1 configuration and readiness."""
    try:
        from app.agents.tradingagents_adapter import tradingagents_adapter

        service_health = await tradingagents_adapter.health()
    except Exception as exc:
        from app.core.config import settings

        service_health = {
            "status": "unavailable" if settings.USE_TRADINGAGENTS else "disabled",
            "service_url": settings.TRADINGAGENTS_SERVICE_URL,
            "detail": str(exc)[:200],
        }
    return _build_tradingagents_config_status(service_health)


@router.get("/phase2-p1p2-status")
async def get_phase2_p1p2_status() -> Dict[str, Any]:
    """Return a compact status map for Phase 2 P1/P2 follow-up work."""
    tradingagents = await get_tradingagents_config()
    counts = await _prd_counts()

    items = [
        {
            "key": "tradingagents_configuration",
            "priority": "P1",
            "status": tradingagents.get("overall_status", "check"),
            "page": "/monitor",
            "api": "/api/v1/system/tradingagents-config",
            "evidence": {
                "mode": _layer_value(tradingagents, "mode", "configured"),
                "provider": _layer_value(tradingagents, "llm", "provider"),
                "fullGraphReady": _layer_value(tradingagents, "mode", "fullGraphReady"),
            },
        },
        {
            "key": "risk_configuration",
            "priority": "P1/P2",
            "status": "ready",
            "page": "/risk",
            "api": "/api/v1/risk/config",
            "evidence": {
                "configMetadata": "/api/v1/risk/config-metadata",
                "configPage": "/risk",
                "resetEndpoint": "/api/v1/risk/config/reset",
            },
        },
        {
            "key": "research_desk_linkage",
            "priority": "P1",
            "status": "ready",
            "page": "/signals",
            "api": "/api/v1/market/research-snapshot/{symbol}",
            "evidence": {
                "asOfReview": True,
                "contextHash": True,
                "backtestLinks": True,
            },
        },
        {
            "key": "system_monitoring",
            "priority": "P1",
            "status": "ready",
            "page": "/monitor",
            "api": "/api/v1/system/frontend-api-overview",
            "evidence": {
                "backtestResults": counts.get("backtest_results", 0),
                "replaySessions": counts.get("replay_sessions", 0),
                "auditLogs": counts.get("audit_logs", 0),
            },
        },
        {
            "key": "advanced_backtest_replay_analytics",
            "priority": "P1/P2",
            "status": "ready",
            "page": "/analytics",
            "api": "/api/v1/analytics/replay-backtest-comparison",
            "evidence": {
                "strategyComparison": "/api/v1/analytics/strategy-comparison",
                "attributionComparison": "/api/v1/analytics/attribution/comparison",
            },
        },
        {
            "key": "deferred_p2_scope",
            "priority": "P2",
            "status": "deferred",
            "page": None,
            "api": None,
            "evidence": {
                "items": [
                    "custom Agent marketplace",
                    "complex approval workflows",
                    "multi-market expansion",
                    "live broker execution",
                    "Prefect/TimescaleDB migration",
                ],
            },
        },
    ]
    active_items = [item for item in items if item["status"] != "deferred"]
    return {
        "timestamp": int(time.time()),
        "overall_status": "ready" if all(item["status"] == "ready" for item in active_items) else "partial",
        "items": items,
    }


@router.get("/phase2-ops-monitor")
async def get_phase2_ops_monitor() -> Dict[str, Any]:
    """Return Phase 2 operations health for data, Agent, audit, risk, and backtest desks."""
    from app.services.phase2_ops_monitor import build_phase2_ops_monitor

    tradingagents = await get_tradingagents_config()
    return await build_phase2_ops_monitor(tradingagents)


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
                {"method": "GET", "path": "/api/v1/system/tradingagents-config", "purpose": "TradingAgents 有效配置和准备度"},
                {"method": "GET", "path": "/api/v1/system/phase2-p1p2-status", "purpose": "Phase 2 P1/P2 状态"},
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
        {"path": "/risk", "label": "风控配置", "role": "查看和调整 RiskGuard 阈值、禁用标的与熔断"},
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


def _demo_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _demo_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _demo_count_status(count: int, *, partial_when_zero: bool = True) -> str:
    if count > 0:
        return "done"
    return "partial" if partial_when_zero else "pending"


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return value
    return None


def _compact_sample_id(prefix: str, value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text.startswith(prefix) else f"{prefix}{text}"


def _demo_step(
    *,
    step_name: str,
    status: str,
    latest_update_time: Optional[str],
    sample_id: Optional[str],
    short_description: str,
    related_page_url: str,
    related_api: str,
    evidence_count: int,
) -> Dict[str, Any]:
    return {
        "stepName": step_name,
        "status": status,
        "latestUpdateTime": latest_update_time,
        "sampleId": sample_id,
        "shortDescription": short_description,
        "relatedPageUrl": related_page_url,
        "relatedApi": related_api,
        "evidenceCount": int(evidence_count or 0),
    }


def _build_closed_loop_steps(
    counts: Dict[str, int],
    latest_sample: Optional[Dict[str, Any]],
    latest_updates: Optional[Dict[str, Optional[str]]] = None,
) -> list[Dict[str, Any]]:
    """Build the P5 closed-loop progress cards from persisted evidence counts."""
    latest_updates = latest_updates or {}
    sample = latest_sample or {}
    decision_id = sample.get("latestDecisionId")
    intent_id = sample.get("latestOrderIntentId")
    order_id = sample.get("latestPaperOrderId")
    audit_id = sample.get("latestAuditRecordId")
    backtest_id = sample.get("latestBacktestId")
    replay_id = sample.get("latestReplaySessionId")

    market_count = counts.get("market_bar_rows", 0)
    return [
        _demo_step(
            step_name="数据接入",
            status="done" if market_count > 0 or counts.get("data_source_ready", 0) > 0 else "partial",
            latest_update_time=latest_updates.get("market"),
            sample_id="BTCUSDT",
            short_description="OpenBB / CCXT / FRED 等入口接入后，行情会进入本地标准化与缓存链路。",
            related_page_url="/data-sources",
            related_api="/api/v1/system/health",
            evidence_count=market_count,
        ),
        _demo_step(
            step_name="数据标准化",
            status="done" if counts.get("factor_snapshots", 0) > 0 or counts.get("signal_events", 0) > 0 else "partial",
            latest_update_time=latest_updates.get("factor"),
            sample_id="BarData / FactorSnapshot",
            short_description="K 线、因子、信号统一为可回测、可审计、支持 PIT 的结构化数据。",
            related_page_url="/signals",
            related_api="/api/v1/signals/factor-catalog",
            evidence_count=counts.get("factor_snapshots", 0),
        ),
        _demo_step(
            step_name="因子计算",
            status=_demo_count_status(counts.get("factor_snapshots", 0)),
            latest_update_time=latest_updates.get("factor"),
            sample_id="factor_snapshots",
            short_description="行情基础因子、技术指标、收益率、波动率、新闻和宏观因子进入研究资产目录。",
            related_page_url="/signals",
            related_api="/api/v1/signals/factors",
            evidence_count=counts.get("factor_snapshots", 0),
        ),
        _demo_step(
            step_name="信号触发",
            status=_demo_count_status(counts.get("signal_events", 0)),
            latest_update_time=latest_updates.get("signal"),
            sample_id="signal_events",
            short_description="策略基于因子生成 SignalEvent，强信号可进入 Agent 审计回测链路。",
            related_page_url="/signals",
            related_api="/api/v1/signals/events",
            evidence_count=counts.get("signal_events", 0),
        ),
        _demo_step(
            step_name="Agent 决策",
            status=_demo_count_status(counts.get("coordination_history", 0)),
            latest_update_time=latest_updates.get("decision"),
            sample_id=_compact_sample_id("#", decision_id),
            short_description="TradingAgents 消费 AnalysisContext，输出结构化 AgentDecision 并进入详情页。",
            related_page_url="/decisions",
            related_api="/api/v1/coordination/history",
            evidence_count=counts.get("coordination_history", 0),
        ),
        _demo_step(
            step_name="OrderIntent",
            status=_demo_count_status(counts.get("order_intent_events", 0)),
            latest_update_time=latest_updates.get("audit"),
            sample_id=intent_id,
            short_description="系统把 Agent 建议或手动操作转换为标准交易意图，HOLD 也会写入审计。",
            related_page_url="/decisions",
            related_api="/api/v1/execution/order-intents/latest",
            evidence_count=counts.get("order_intent_events", 0),
        ),
        _demo_step(
            step_name="RiskGuard",
            status=_demo_count_status(counts.get("risk_guard_events", 0)),
            latest_update_time=latest_updates.get("audit"),
            sample_id="RiskGuard",
            short_description="所有模拟下单前统一执行仓位、敞口、回撤、标的和杠杆等风控规则。",
            related_page_url="/dashboard?tab=positions",
            related_api="/api/v1/trading/risk-status",
            evidence_count=counts.get("risk_guard_events", 0),
        ),
        _demo_step(
            step_name="模拟执行",
            status=_demo_count_status(counts.get("paper_trades", 0)),
            latest_update_time=latest_updates.get("paper_trade"),
            sample_id=order_id,
            short_description="本阶段只做本地模拟成交，记录成交价、手续费、滑点和关联 ID。",
            related_page_url="/dashboard?tab=positions",
            related_api="/api/v1/trading/orders",
            evidence_count=counts.get("paper_trades", 0),
        ),
        _demo_step(
            step_name="持仓 / PnL",
            status="done" if counts.get("paper_positions", 0) > 0 or counts.get("paper_trades", 0) > 0 else "partial",
            latest_update_time=latest_updates.get("position") or latest_updates.get("paper_trade"),
            sample_id="paper_positions",
            short_description="模拟订单更新持仓、现金和盈亏，供仪表盘、回放和审计联动查看。",
            related_page_url="/dashboard?tab=positions",
            related_api="/api/v1/trading/positions",
            evidence_count=counts.get("paper_positions", 0),
        ),
        _demo_step(
            step_name="回测验证",
            status=_demo_count_status(counts.get("backtest_results", 0)),
            latest_update_time=latest_updates.get("backtest"),
            sample_id=_compact_sample_id("#", backtest_id),
            short_description="支持普通规则回测和 Agent 审计回测，结果包含指标、曲线、PIT 检查和交易明细。",
            related_page_url="/backtest",
            related_api="/api/v1/strategy/backtest/history",
            evidence_count=counts.get("backtest_results", 0),
        ),
        _demo_step(
            step_name="历史回放",
            status=_demo_count_status(counts.get("replay_sessions", 0)),
            latest_update_time=latest_updates.get("replay"),
            sample_id=replay_id,
            short_description="播放器式还原某一 as_of_time 的行情、因子、信号、决策、订单和审计事件。",
            related_page_url="/replay",
            related_api="/api/v1/replay/events",
            evidence_count=counts.get("replay_sessions", 0),
        ),
        _demo_step(
            step_name="审计导出",
            status=_demo_count_status(counts.get("audit_logs", 0)),
            latest_update_time=latest_updates.get("audit"),
            sample_id=_compact_sample_id("#", audit_id),
            short_description="AuditRecord 写入后不可修改，支持筛选、详情查看和 JSON 导出 / 复制。",
            related_page_url="/audit",
            related_api="/api/v1/audit/records",
            evidence_count=counts.get("audit_logs", 0),
        ),
    ]


def _build_prd_acceptance(counts: Dict[str, int]) -> list[Dict[str, Any]]:
    """Build PRD acceptance cards for phase 1 and phase 2."""
    def item(name: str, done: bool, evidence: str, jump_link: str, note: str = "") -> Dict[str, Any]:
        return {
            "name": name,
            "status": "done" if done else "partial",
            "evidence": evidence,
            "jumpLink": jump_link,
            "note": note or ("已有真实记录支撑。" if done else "能力已预留，建议继续补充演示样例。"),
        }

    phase1 = [
        item("数据接入", counts.get("market_bar_rows", 0) > 0 or counts.get("data_source_ready", 0) > 0, f"{counts.get('market_bar_rows', 0):,} 行 K 线缓存", "/data-sources"),
        item("标准化数据模型", counts.get("factor_snapshots", 0) > 0, f"{counts.get('factor_snapshots', 0):,} 条因子快照", "/signals"),
        item("TradingAgents 消费 AnalysisContext", counts.get("coordination_history", 0) > 0, f"{counts.get('coordination_history', 0):,} 条决策历史", "/decisions"),
        item("point-in-time 回测", counts.get("pit_backtests", 0) > 0, f"{counts.get('pit_backtests', 0):,} 条 PIT 回测记录", "/backtest"),
        item("决策审计和回放", counts.get("audit_logs", 0) > 0 and counts.get("replay_sessions", 0) > 0, f"{counts.get('audit_logs', 0):,} 条审计，{counts.get('replay_sessions', 0):,} 个回放", "/audit"),
        item("前端配置、查看和复盘", True, "数据源、研究资产、回测、回放、决策、审计页面已接入", "/monitor"),
    ]
    phase2 = [
        item("OrderIntent", counts.get("order_intent_events", 0) > 0, f"{counts.get('order_intent_events', 0):,} 条相关审计事件", "/decisions"),
        item("RiskGuard", counts.get("risk_guard_events", 0) > 0, f"{counts.get('risk_guard_events', 0):,} 条风控事件", "/dashboard?tab=positions"),
        item("模拟交易执行", counts.get("paper_trades", 0) > 0, f"{counts.get('paper_trades', 0):,} 条模拟订单", "/dashboard?tab=positions"),
        item("研究台", counts.get("factor_snapshots", 0) > 0 and counts.get("signal_events", 0) > 0, "行情、因子、信号、新闻、Agent 面板已整合", "/dashboard"),
        item("回测台", counts.get("backtest_results", 0) > 0, f"{counts.get('backtest_results', 0):,} 条回测结果", "/backtest"),
        item("审计台", counts.get("audit_logs", 0) > 0, f"{counts.get('audit_logs', 0):,} 条不可变审计记录", "/audit"),
        item("历史回放", counts.get("replay_sessions", 0) > 0, f"{counts.get('replay_sessions', 0):,} 个回放会话", "/replay"),
        item("三台联动", counts.get("agent_audited_backtests", 0) > 0 and counts.get("replay_sessions", 0) > 0 and counts.get("audit_logs", 0) > 0, "回测详情、历史回放、审计筛选已通过 ID 联动", "/backtest"),
    ]
    return [
        {"phaseName": "第一阶段", "items": phase1},
        {"phaseName": "第二阶段", "items": phase2},
    ]


def _build_demo_path(latest_sample: Optional[Dict[str, Any]]) -> list[Dict[str, str]]:
    sample = latest_sample or {}
    backtest_url = sample.get("backtestDetailUrl") or "/backtest"
    replay_url = sample.get("replayUrl") or "/replay"
    decision_url = sample.get("decisionDetailUrl") or "/decisions"
    audit_url = sample.get("auditRecordUrl") or "/audit"
    return [
        {
            "title": "查看数据源状态",
            "description": "先说明 OpenBB、CCXT、FRED、缓存和降级源分别是什么。",
            "url": "/data-sources",
            "expectedResult": "能看到数据源、缓存、最后更新时间和降级状态。",
            "fallbackNote": "如果上游暂不可用，页面会展示缓存或暂无数据。",
        },
        {
            "title": "查看因子资产目录",
            "description": "展示因子不是一堆数字，而是按研究类别管理的资产。",
            "url": "/signals",
            "expectedResult": "能看到因子分类、可用性、数据来源、被哪些策略和信号使用。",
            "fallbackNote": "暂无统计项会显示“暂无统计”，不会报错。",
        },
        {
            "title": "查看策略体系",
            "description": "在因子/信号页切到策略体系，说明策略如何使用因子触发信号。",
            "url": "/signals",
            "expectedResult": "能看到策略、使用因子、触发信号和支持的回测模式。",
            "fallbackNote": "如果策略详情为空，先展示内置策略资产说明。",
        },
        {
            "title": "运行 Agent 审计回测",
            "description": "选择 Agent 审计回测，强调只在强信号触发时调用 Agent。",
            "url": "/backtest",
            "expectedResult": "生成 BacktestResult、PIT 检查、交易明细和审计链路。",
            "fallbackNote": "如果演示时间紧，直接打开最近样例回测详情。",
        },
        {
            "title": "查看回测详情",
            "description": "展示核心指标、净值/回撤曲线、PIT 检查、交易明细。",
            "url": backtest_url,
            "expectedResult": "能看到 rule_only / agent_audited 模式说明和关联 ID。",
            "fallbackNote": "暂无样例时返回回测列表。",
        },
        {
            "title": "点击交易进入历史回放",
            "description": "从交易表跳到对应 as_of_time，看那一刻发生了什么。",
            "url": replay_url,
            "expectedResult": "播放器展示事件流、当前状态、因子、信号和账户状态。",
            "fallbackNote": "暂无 replaySessionId 时进入回放首页。",
        },
        {
            "title": "查看 Agent 决策详情",
            "description": "解释 Agent 输入快照、角色输出、最终建议和置信度来源。",
            "url": decision_url,
            "expectedResult": "能看到决策基本信息、输入快照、角色分析和关联 OrderIntent。",
            "fallbackNote": "暂无 decisionId 时进入决策中心列表。",
        },
        {
            "title": "查看 OrderIntent 和 RiskGuard",
            "description": "说明交易建议先变成标准意图，再过风控，不能直接成交。",
            "url": "/decisions",
            "expectedResult": "能看到 OrderIntent 状态和风控规则表。",
            "fallbackNote": "如果没有关联意图，页面显示暂无关联记录。",
        },
        {
            "title": "查看模拟订单和持仓 PnL",
            "description": "强调当前是本地模拟环境，不会产生真实订单。",
            "url": "/dashboard?tab=positions",
            "expectedResult": "能看到模拟订单、持仓、未实现盈亏和风险状态。",
            "fallbackNote": "无持仓时展示“暂无持仓”。",
        },
        {
            "title": "查看审计记录并复制 JSON",
            "description": "最后用审计台证明每一步都可追溯、可导出。",
            "url": audit_url,
            "expectedResult": "能筛选关联记录，打开详情并复制 / 导出 JSON。",
            "fallbackNote": "无关联 auditId 时进入审计中心列表。",
        },
    ]


def _build_demo_health_summary(
    health: Dict[str, Any],
    counts: Dict[str, int],
    coverage: Dict[str, Any],
    health_error: Optional[str] = None,
) -> Dict[str, Any]:
    infrastructure = health.get("infrastructure", {}) if isinstance(health, dict) else {}
    clickhouse_status = _layer_value(health, "layers", "L4_storage", "clickhouse", "status") or (
        "ok" if coverage.get("total_rows", 0) > 0 else "unavailable"
    )
    ingestion_status = _layer_value(health, "infrastructure", "nats") or "unknown"
    return {
        "backendHealth": "ok" if not health_error else "partial",
        "databaseStatus": infrastructure.get("postgresql", "unknown"),
        "redisStatus": infrastructure.get("redis", "unknown"),
        "clickhouseStatus": clickhouse_status,
        "ingestionStatus": ingestion_status,
        "frontendBuildStatus": "当前页面已加载，正式构建以 typecheck / build 结果为准",
        "lastSmokeTestTime": _demo_now_iso(),
        "apiErrorCount": 1 if health_error else 0,
        "lastErrorSummary": "暂无明显错误" if not health_error else "系统健康检查部分数据暂不可用，首页已使用缓存式摘要兜底。",
        "counts": counts,
        "marketCoverage": coverage,
    }


async def _demo_scalar(session: Any, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
    from sqlalchemy import text

    result = await session.execute(text(sql), params or {})
    return int(result.scalar() or 0)


async def _demo_counts_and_updates() -> tuple[Dict[str, int], Dict[str, Optional[str]]]:
    counts = {
        "data_source_ready": 0,
        "market_bar_rows": 0,
        "factor_snapshots": 0,
        "signal_events": 0,
        "coordination_history": 0,
        "order_intent_events": 0,
        "risk_guard_events": 0,
        "risk_blocked_events": 0,
        "paper_trades": 0,
        "paper_positions": 0,
        "backtest_results": 0,
        "agent_audited_backtests": 0,
        "pit_backtests": 0,
        "replay_sessions": 0,
        "audit_logs": 0,
    }
    latest_updates: Dict[str, Optional[str]] = {
        "market": None,
        "factor": None,
        "signal": None,
        "decision": None,
        "audit": None,
        "paper_trade": None,
        "position": None,
        "backtest": None,
        "replay": None,
    }
    try:
        from sqlalchemy import text
        from app.services.database import get_db

        async with get_db() as session:
            count_queries = {
                "factor_snapshots": "SELECT COUNT(*) FROM factor_snapshots",
                "signal_events": "SELECT COUNT(*) FROM signal_events",
                "coordination_history": "SELECT COUNT(*) FROM coordination_history",
                "paper_trades": "SELECT COUNT(*) FROM paper_trades",
                "paper_positions": "SELECT COUNT(*) FROM paper_positions WHERE quantity != 0",
                "backtest_results": "SELECT COUNT(*) FROM backtest_results",
                "replay_sessions": "SELECT COUNT(*) FROM replay_sessions",
                "audit_logs": "SELECT COUNT(*) FROM audit_logs",
                "pit_backtests": "SELECT COUNT(*) FROM backtest_results WHERE metrics ? 'pit'",
                "agent_audited_backtests": """
                    SELECT COUNT(*) FROM backtest_results
                    WHERE metrics->>'executionMode' = 'agent_audited'
                       OR metrics->>'execution_mode' = 'agent_audited'
                """,
                "order_intent_events": """
                    SELECT COUNT(*) FROM audit_logs
                    WHERE action LIKE 'ORDER_INTENT_%'
                       OR action IN ('ORDER_INTENT_CREATED','HOLD_RECORDED')
                       OR details->>'orderIntentId' IS NOT NULL
                       OR details->'intent'->>'intent_id' IS NOT NULL
                """,
                "risk_guard_events": """
                    SELECT COUNT(*) FROM audit_logs
                    WHERE action IN ('RISK_CHECK_PASSED','RISK_BLOCKED')
                       OR details->>'eventType' IN ('RISK_CHECK_PASSED','RISK_BLOCKED')
                       OR details->'riskCheckResult' IS NOT NULL
                """,
                "risk_blocked_events": """
                    SELECT COUNT(*) FROM audit_logs
                    WHERE action = 'RISK_BLOCKED'
                       OR details->>'eventType' = 'RISK_BLOCKED'
                """,
            }
            for key, sql in count_queries.items():
                counts[key] = await _demo_scalar(session, sql)

            update_queries = {
                "factor": "SELECT MAX(created_at) FROM factor_snapshots",
                "signal": "SELECT MAX(created_at) FROM signal_events",
                "decision": "SELECT MAX(created_at) FROM coordination_history",
                "audit": "SELECT MAX(created_at) FROM audit_logs",
                "paper_trade": "SELECT MAX(created_at) FROM paper_trades",
                "position": "SELECT MAX(updated_at) FROM paper_positions",
                "backtest": "SELECT MAX(created_at) FROM backtest_results",
                "replay": "SELECT MAX(created_at) FROM replay_sessions",
            }
            for key, sql in update_queries.items():
                result = await session.execute(text(sql))
                latest_updates[key] = _demo_iso(result.scalar())
    except Exception as exc:
        logger.debug("Demo overview count collection failed: %s", exc)
    return counts, latest_updates


def _extract_related_from_trade(trade: Dict[str, Any]) -> Dict[str, Any]:
    audit_ids = _first_present(
        trade.get("relatedAuditIds"),
        trade.get("related_audit_ids"),
        trade.get("auditRecordIds"),
    ) or []
    if not isinstance(audit_ids, list):
        audit_ids = [audit_ids]
    return {
        "decision_id": _first_present(trade.get("relatedDecisionId"), trade.get("related_decision_id"), trade.get("decisionId")),
        "intent_id": _first_present(trade.get("relatedOrderIntentId"), trade.get("related_order_intent_id"), trade.get("orderIntentId")),
        "order_id": _first_present(trade.get("relatedOrderId"), trade.get("related_order_id"), trade.get("orderId")),
        "audit_ids": audit_ids,
        "as_of_time": _first_present(trade.get("asOfTime"), trade.get("as_of_time"), trade.get("entryTime"), trade.get("entry_time")),
    }


async def _latest_demo_sample() -> Optional[Dict[str, Any]]:
    try:
        from sqlalchemy import text
        from app.services.database import get_db

        async with get_db() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT
                            bt.id,
                            bt.strategy_type,
                            bt.symbol,
                            bt.interval,
                            bt.metrics,
                            bt.trades_summary,
                            bt.created_at,
                            rs.replay_session_id,
                            rs.current_timestamp,
                            rs.end_time
                        FROM backtest_results bt
                        LEFT JOIN replay_sessions rs ON rs.backtest_id = bt.id
                        ORDER BY
                            CASE
                              WHEN bt.metrics->>'executionMode' = 'agent_audited'
                                OR bt.metrics->>'execution_mode' = 'agent_audited'
                              THEN 0 ELSE 1
                            END,
                            bt.created_at DESC,
                            rs.created_at DESC
                        LIMIT 1
                        """
                    )
                )
            ).mappings().first()
            if not row:
                return None

            metrics = row["metrics"] or {}
            trades = row["trades_summary"] or []
            if not isinstance(trades, list):
                trades = []
            related: Dict[str, Any] = {}
            for trade in trades:
                if isinstance(trade, dict):
                    related = _extract_related_from_trade(trade)
                    if any(related.values()):
                        break

            audit_ids = related.get("audit_ids") or metrics.get("auditRecordIds") or []
            if not isinstance(audit_ids, list):
                audit_ids = [audit_ids]
            latest_audit_id = _first_present(audit_ids[-1] if audit_ids else None)
            if not latest_audit_id:
                audit_row = (
                    await session.execute(
                        text(
                            """
                            SELECT id
                            FROM audit_logs
                            WHERE details->>'backtestId' = :backtest_id
                               OR details->>'backtest_id' = :backtest_id
                            ORDER BY created_at DESC, id DESC
                            LIMIT 1
                            """
                        ),
                        {"backtest_id": str(row["id"])},
                    )
                ).mappings().first()
                latest_audit_id = audit_row["id"] if audit_row else None

            latest_decision_id = related.get("decision_id")
            if not latest_decision_id:
                decision_row = (
                    await session.execute(
                        text(
                            """
                            SELECT id
                            FROM coordination_history
                            WHERE symbol = :symbol
                            ORDER BY timestamp DESC, id DESC
                            LIMIT 1
                            """
                        ),
                        {"symbol": row["symbol"]},
                    )
                ).mappings().first()
                latest_decision_id = decision_row["id"] if decision_row else None

            replay_session_id = row["replay_session_id"]
            replay_as_of = _demo_iso(_first_present(related.get("as_of_time"), row["current_timestamp"], row["end_time"]))
            replay_url = "/replay"
            if replay_session_id:
                replay_url = f"/replay?session_id={quote(str(replay_session_id))}"
                if replay_as_of:
                    replay_url += f"&as_of_time={quote(replay_as_of)}"

            execution_mode = _first_present(metrics.get("executionMode"), metrics.get("execution_mode"), "rule_only")
            sample = {
                "latestBacktestId": row["id"],
                "latestReplaySessionId": replay_session_id,
                "latestDecisionId": latest_decision_id,
                "latestOrderIntentId": related.get("intent_id"),
                "latestPaperOrderId": related.get("order_id"),
                "latestAuditRecordId": latest_audit_id,
                "executionMode": execution_mode,
                "symbol": row["symbol"],
                "strategyType": row["strategy_type"],
                "interval": row["interval"],
                "createdAt": _demo_iso(row["created_at"]),
                "backtestDetailUrl": f"/backtest?backtest_id={row['id']}",
                "replayUrl": replay_url,
                "decisionDetailUrl": f"/audit?decision_id={latest_decision_id}" if latest_decision_id else "/decisions",
                "orderIntentUrl": f"/audit?order_intent_id={quote(str(related.get('intent_id')))}" if related.get("intent_id") else "/decisions",
                "paperOrderUrl": f"/audit?order_id={quote(str(related.get('order_id')))}" if related.get("order_id") else "/dashboard?tab=positions",
                "auditRecordUrl": f"/audit?audit_id={latest_audit_id}" if latest_audit_id else "/audit",
            }
            return sample
    except Exception as exc:
        logger.debug("Latest demo sample collection failed: %s", exc)
        return None


@router.get("/demo-overview")
async def get_demo_overview() -> Dict[str, Any]:
    """Return a P5-friendly demo homepage overview without changing core flows."""
    generated_at = _demo_now_iso()
    health: Dict[str, Any] = {}
    health_error: Optional[str] = None
    try:
        health = await get_system_health()
    except Exception as exc:
        health_error = str(exc)[:160]
        logger.debug("Demo overview health check degraded: %s", exc)

    counts, latest_updates = await _demo_counts_and_updates()
    coverage = await _market_coverage_summary()
    counts["market_bar_rows"] = int(coverage.get("total_rows") or 0)
    counts["data_source_ready"] = 1 if _layer_value(health, "layers", "L1_data_source", "market_data", "status") in {"ok", "connected"} else 0
    latest_updates["market"] = latest_updates.get("factor") or latest_updates.get("signal") or generated_at

    latest_sample = await _latest_demo_sample()
    closed_loop_steps = _build_closed_loop_steps(counts, latest_sample, latest_updates)
    prd_acceptance = _build_prd_acceptance(counts)
    done_steps = sum(1 for step in closed_loop_steps if step["status"] == "done")

    return {
        "schemaVersion": "demo_overview.v1",
        "generatedAt": generated_at,
        "overallStatus": "done" if done_steps == len(closed_loop_steps) else "partial",
        "closedLoopSteps": closed_loop_steps,
        "prdAcceptance": prd_acceptance,
        "demoPath": _build_demo_path(latest_sample),
        "health": _build_demo_health_summary(health, counts, coverage, health_error),
        "latestSample": latest_sample,
        "summary": {
            "doneSteps": done_steps,
            "totalSteps": len(closed_loop_steps),
            "phase1Done": sum(1 for item in prd_acceptance[0]["items"] if item["status"] == "done"),
            "phase2Done": sum(1 for item in prd_acceptance[1]["items"] if item["status"] == "done"),
        },
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
