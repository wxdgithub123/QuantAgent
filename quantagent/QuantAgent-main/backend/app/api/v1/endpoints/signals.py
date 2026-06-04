"""Factor snapshots & signal events endpoints."""

import logging
from typing import Any, Dict, List, Optional

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.services.database import get_db
from app.services.research_assets import (
    FACTOR_BLUEPRINTS,
    FACTOR_CATEGORY_ORDER,
    category_sort_key,
    factor_blueprint,
    infer_availability_status,
    infer_missing_rate,
    merge_unique,
    signal_related_factor_names,
    strategies_using_factor,
    strategy_asset_base,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_number(metrics: Any, *keys: str) -> Optional[float]:
    if not isinstance(metrics, dict):
        return None
    for key in keys:
        value = metrics.get(key)
        number = _safe_float(value)
        if number is not None:
            return number
    return None


def _extract_related_value(payload: Any, *keys: str) -> Optional[Any]:
    if isinstance(payload, dict):
        for key in keys:
            if payload.get(key) not in (None, ""):
                return payload.get(key)
        for value in payload.values():
            found = _extract_related_value(value, *keys)
            if found not in (None, ""):
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _extract_related_value(item, *keys)
            if found not in (None, ""):
                return found
    return None


async def _load_backtest_stats(session: Any) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    r = await session.execute(text("""
SELECT id, strategy_type, metrics, created_at
FROM backtest_results
ORDER BY created_at DESC
LIMIT 5000
"""))
    for row in r.fetchall():
        strategy_type = row[1] or "unknown"
        metrics = row[2] or {}
        item = stats.setdefault(strategy_type, {
            "count": 0,
            "agentAuditedCount": 0,
            "latestBacktestAt": None,
            "bestBacktestReturn": None,
            "maxDrawdown": None,
            "ids": [],
        })
        item["count"] += 1
        item["ids"].append(row[0])
        item["latestBacktestAt"] = item["latestBacktestAt"] or _iso(row[3])
        execution_mode = metrics.get("executionMode") or metrics.get("execution_mode")
        if execution_mode == "agent_audited":
            item["agentAuditedCount"] += 1
        total_return = _metric_number(metrics, "totalReturn", "total_return", "total_return_pct")
        if total_return is not None:
            current_best = item.get("bestBacktestReturn")
            item["bestBacktestReturn"] = total_return if current_best is None else max(current_best, total_return)
        max_drawdown = _metric_number(metrics, "maxDrawdown", "max_drawdown", "max_drawdown_pct")
        if max_drawdown is not None:
            current_dd = item.get("maxDrawdown")
            item["maxDrawdown"] = max_drawdown if current_dd is None else min(current_dd, max_drawdown)
    return stats


async def _load_strategy_signal_stats(session: Any) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    r = await session.execute(text("""
SELECT source_strategy, signal_type, COUNT(*) AS cnt, MAX(timestamp) AS latest_timestamp
FROM signal_events
GROUP BY source_strategy, signal_type
"""))
    for row in r.fetchall():
        strategy = row[0] or "unknown"
        item = stats.setdefault(strategy, {"count": 0, "signalTypes": {}, "latestSignalAt": None})
        item["count"] += int(row[2] or 0)
        item["signalTypes"][row[1] or "UNKNOWN"] = int(row[2] or 0)
        latest = _iso(row[3])
        if latest and not item["latestSignalAt"]:
            item["latestSignalAt"] = latest
    return stats


async def _build_factor_catalog(session: Any) -> List[Dict[str, Any]]:
    definitions: Dict[str, Dict[str, Any]] = {}
    r = await session.execute(text("""
SELECT factor_name, display_name, category, family, description, calculation,
       upstream_data, provider_hint, unit, default_interval
FROM factor_definitions
WHERE is_active IS TRUE
"""))
    for row in r.fetchall():
        name = str(row[0] or "").lower()
        definitions[name] = {
            "factor_name": name,
            "display_name": row[1],
            "category": row[2],
            "family": row[3],
            "description": row[4],
            "calculation": row[5],
            "upstream_data": row[6],
            "provider_hint": row[7],
            "unit": row[8],
            "default_interval": row[9],
        }

    observed: Dict[str, Dict[str, Any]] = {}
    r = await session.execute(text("""
SELECT factor_name, COUNT(*) AS snapshot_count, COUNT(DISTINCT symbol) AS symbol_count,
       MAX(timestamp) AS latest_timestamp, MAX(available_time) AS latest_available_time,
       STRING_AGG(DISTINCT COALESCE(provider, '未记录'), ', ') AS providers,
       STRING_AGG(DISTINCT COALESCE(data_source, '未记录'), ', ') AS data_sources
FROM factor_snapshots
GROUP BY factor_name
"""))
    for row in r.fetchall():
        name = str(row[0] or "").lower()
        observed[name] = {
            "snapshotCount": int(row[1] or 0),
            "symbolCount": int(row[2] or 0),
            "latestUpdateTime": _iso(row[3]),
            "latestAvailableTime": _iso(row[4]),
            "providers": [item.strip() for item in (row[5] or "").split(",") if item.strip()],
            "dataSources": [item.strip() for item in (row[6] or "").split(",") if item.strip()],
        }

    latest_values: Dict[str, Dict[str, Any]] = {}
    r = await session.execute(text("""
SELECT DISTINCT ON (factor_name)
       factor_name, factor_value, timestamp, available_time, provider, data_source, source_version
FROM factor_snapshots
ORDER BY factor_name, timestamp DESC
"""))
    for row in r.fetchall():
        name = str(row[0] or "").lower()
        latest_values[name] = {
            "latestValue": row[1],
            "latestUpdateTime": _iso(row[2]),
            "latestAvailableTime": _iso(row[3]),
            "provider": row[4],
            "dataSource": row[5],
            "sourceVersion": row[6],
        }

    signal_usage: Dict[str, Dict[str, Any]] = {}
    r = await session.execute(text("""
SELECT f.factor_name, COUNT(*) AS signal_count, MAX(se.timestamp) AS latest_signal_at,
       ARRAY_AGG(DISTINCT se.source_strategy) AS strategies
FROM signal_events se
CROSS JOIN LATERAL jsonb_object_keys(se.factors) AS f(factor_name)
GROUP BY f.factor_name
"""))
    for row in r.fetchall():
        name = str(row[0] or "").lower()
        signal_usage[name] = {
            "signalCount": int(row[1] or 0),
            "latestSignalAt": _iso(row[2]),
            "strategies": sorted(item for item in (row[3] or []) if item),
        }

    backtest_stats = await _load_backtest_stats(session)
    factor_names = set(FACTOR_BLUEPRINTS.keys()) | set(definitions.keys()) | set(observed.keys()) | set(signal_usage.keys())
    items: List[Dict[str, Any]] = []

    for name in factor_names:
        blueprint = factor_blueprint(name, definitions.get(name))
        obs = observed.get(name, {})
        latest = latest_values.get(name, {})
        usage = signal_usage.get(name, {})
        used_strategies = merge_unique(strategies_using_factor(name), usage.get("strategies", []))
        used_in_backtests = sum(int(backtest_stats.get(strategy, {}).get("count", 0)) for strategy in used_strategies)
        used_in_agent = sum(int(backtest_stats.get(strategy, {}).get("agentAuditedCount", 0)) for strategy in used_strategies)
        snapshot_count = int(obs.get("snapshotCount", 0))
        latest_value = latest.get("latestValue")
        status = infer_availability_status(snapshot_count, latest_value, bool(blueprint.get("supportsPIT")))
        providers = obs.get("providers") or ([latest.get("provider")] if latest.get("provider") else [])
        data_sources = obs.get("dataSources") or ([latest.get("dataSource")] if latest.get("dataSource") else [])
        item = {
            **blueprint,
            "availabilityStatus": status,
            "missingRate": infer_missing_rate(status),
            "latestValue": latest_value,
            "latestUpdateTime": latest.get("latestUpdateTime") or obs.get("latestUpdateTime"),
            "latestAvailableTime": latest.get("latestAvailableTime") or obs.get("latestAvailableTime"),
            "providers": providers,
            "observedDataSources": data_sources,
            "sourceVersion": latest.get("sourceVersion"),
            "snapshotCount": snapshot_count,
            "symbolCount": int(obs.get("symbolCount", 0)),
            "usedBySignals": usage.get("strategies", []),
            "signalCount": int(usage.get("signalCount", 0)),
            "latestSignalAt": usage.get("latestSignalAt"),
            "usedByStrategies": used_strategies,
            "usedInBacktests": used_in_backtests,
            "usedInAgentAudited": used_in_agent,
            "ic": None,
            "winRate": None,
            "contribution": None,
        }
        items.append(item)

    return sorted(items, key=lambda item: (category_sort_key(item["category"]), item["factorName"]))


def _build_strategy_asset(
    strategy_id: str,
    template: Optional[Dict[str, Any]],
    backtest_stats: Dict[str, Dict[str, Any]],
    signal_stats: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    base = strategy_asset_base(strategy_id, template)
    bt = backtest_stats.get(strategy_id, {})
    signals = signal_stats.get(strategy_id, {})
    return {
        **base,
        "triggerSignals": sorted((signals.get("signalTypes") or {}).keys()) or base["triggerSignals"],
        "signalCount": int(signals.get("count", 0)),
        "latestSignalAt": signals.get("latestSignalAt"),
        "recentBacktestCount": int(bt.get("count", 0)),
        "bestBacktestReturn": bt.get("bestBacktestReturn"),
        "maxDrawdown": bt.get("maxDrawdown"),
        "latestBacktestAt": bt.get("latestBacktestAt"),
        "backtestIds": bt.get("ids", [])[:20],
    }


class SignalPipelineRunRequest(BaseModel):
    """Request body for one on-demand L1-L5 pipeline run."""

    symbol: str = Field(default="BTCUSDT", description="Canonical symbol, e.g. BTCUSDT")
    asset_type: str = Field(default="crypto", description="crypto or equity")
    interval: str = Field(default="1h", description="K-line interval, e.g. 1m/15m/1h/1d")
    limit: int = Field(default=300, ge=60, le=5000)
    provider: str = Field(default="yfinance", description="OpenBB provider name")
    fallback_providers: Optional[List[str]] = Field(default=None, description="Provider fallback chain")
    strategies: Optional[List[str]] = Field(
        default=None,
        description="Strategy ids from strategy_templates.py. Defaults to core sync strategies.",
    )
    include_wait_signals: bool = True
    persist_fetched_bars: bool = True
    refresh_from_source: bool = False
    include_context: bool = True


@router.post("/run")
async def run_signal_pipeline(req: SignalPipelineRunRequest) -> Dict[str, Any]:
    """Run L1-L5 once: load/fetch bars, compute factors, persist signals."""
    try:
        from app.services.factor_signal_pipeline import factor_signal_pipeline

        return await factor_signal_pipeline.run(
            symbol=req.symbol,
            asset_type=req.asset_type,
            interval=req.interval,
            limit=req.limit,
            provider=req.provider,
            fallback_providers=req.fallback_providers,
            strategies=req.strategies,
            include_wait_signals=req.include_wait_signals,
            persist_fetched_bars=req.persist_fetched_bars,
            refresh_from_source=req.refresh_from_source,
            include_context=req.include_context,
        )
    except Exception as e:
        logger.error(f"Failed to run signal pipeline: {e}", exc_info=True)
        return {
            "status": "error",
            "symbol": req.symbol,
            "interval": req.interval,
            "error": str(e),
        }


@router.get("/context/{symbol}")
async def get_analysis_context(
    symbol: str,
    interval: str = Query("1h"),
    as_of_time: Optional[datetime] = Query(None),
    bar_limit: int = Query(120, ge=1, le=1000),
    factor_limit: int = Query(60, ge=1, le=500),
    signal_limit: int = Query(40, ge=1, le=500),
    news_limit: int = Query(20, ge=0, le=200),
    macro_limit: int = Query(30, ge=0, le=200),
) -> Dict[str, Any]:
    """Assemble PRD AnalysisContext with point-in-time filtering."""
    try:
        from app.services.analysis_context_builder import analysis_context_builder

        context = await analysis_context_builder.build(
            symbol=symbol,
            interval=interval,
            as_of_time=as_of_time,
            bar_limit=bar_limit,
            factor_limit=factor_limit,
            signal_limit=signal_limit,
            news_limit=news_limit,
            macro_limit=macro_limit,
        )
        return context.to_agent_payload()
    except Exception as e:
        logger.error(f"Failed to build AnalysisContext: {e}", exc_info=True)
        return {"status": "error", "symbol": symbol, "error": str(e)}


@router.get("/factors")
async def get_factors(
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g. BTCUSDT)"),
    factor_name: Optional[str] = Query(None, description="Filter by factor name (e.g. sma_10)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List factor snapshots with optional filters and pagination."""
    try:
        async with get_db() as session:
            conditions = []
            factor_conditions = []
            params: Dict[str, Any] = {}
            if symbol:
                conditions.append("symbol = :symbol")
                factor_conditions.append("fs.symbol = :symbol")
                params["symbol"] = symbol
            if factor_name:
                conditions.append("factor_name = :factor_name")
                factor_conditions.append("fs.factor_name = :factor_name")
                params["factor_name"] = factor_name

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            factor_where_clause = " AND ".join(factor_conditions) if factor_conditions else "1=1"

            # Count
            count_sql = f"SELECT COUNT(*) FROM factor_snapshots WHERE {where_clause}"
            r = await session.execute(text(count_sql), params)
            total = r.scalar() or 0

            # Query
            query_sql = f"""SELECT fs.id, fs.symbol, fs.timestamp, fs.factor_name, fs.factor_value, fs.parameters, fs.source,
fs.interval, fs.provider, fs.data_source, fs.source_version, fs.schema_version, fs.available_time, fs.as_of_time,
fd.display_name, fd.category, fd.family, fd.description, fd.calculation, fd.upstream_data, fd.provider_hint, fd.unit
FROM factor_snapshots fs
LEFT JOIN factor_definitions fd ON fd.factor_name = fs.factor_name
WHERE {factor_where_clause}
ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"""
            params["limit"] = limit
            params["offset"] = offset
            r = await session.execute(text(query_sql), params)
            rows = []
            for row in r.fetchall():
                rows.append({
                    "id": row[0],
                    "symbol": row[1],
                    "timestamp": row[2].isoformat() if row[2] else None,
                    "factor_name": row[3],
                    "factor_value": row[4],
                    "parameters": row[5] or {},
                    "source": row[6],
                    "interval": row[7],
                    "provider": row[8],
                    "data_source": row[9],
                    "source_version": row[10],
                    "schema_version": row[11],
                    "available_time": row[12].isoformat() if row[12] else None,
                    "as_of_time": row[13].isoformat() if row[13] else None,
                    "definition": {
                        "display_name": row[14] or row[3],
                        "category": row[15] or "未分类",
                        "family": row[16],
                        "description": row[17] or "",
                        "calculation": row[18] or "",
                        "upstream_data": row[19] or "未记录",
                        "provider_hint": row[20] or "",
                        "unit": row[21] or "",
                    },
                })

            return {"data": rows, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Failed to fetch factors: {e}")
        return {"data": [], "total": 0, "error": str(e)}


@router.get("/factor-definitions")
async def get_factor_definitions(
    category: Optional[str] = Query(None, description="Filter by factor category"),
    include_inactive: bool = Query(False),
) -> Dict[str, Any]:
    """List the factor catalog with observed snapshot counts."""
    try:
        async with get_db() as session:
            conditions = []
            params: Dict[str, Any] = {}
            if category:
                conditions.append("fd.category = :category")
                params["category"] = category
            if not include_inactive:
                conditions.append("fd.is_active IS TRUE")

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            sql = f"""
WITH observed AS (
    SELECT
        factor_name,
        COUNT(*) AS snapshot_count,
        COUNT(DISTINCT symbol) AS symbol_count,
        MAX(timestamp) AS latest_timestamp,
        STRING_AGG(DISTINCT COALESCE(provider, '未记录'), ', ' ORDER BY COALESCE(provider, '未记录')) AS providers,
        STRING_AGG(DISTINCT COALESCE(data_source, '未记录'), ', ' ORDER BY COALESCE(data_source, '未记录')) AS data_sources
    FROM factor_snapshots
    GROUP BY factor_name
)
SELECT
    fd.factor_name,
    fd.display_name,
    fd.category,
    fd.family,
    fd.description,
    fd.calculation,
    fd.upstream_data,
    fd.provider_hint,
    fd.unit,
    fd.default_interval,
    fd.sort_order,
    fd.is_active,
    COALESCE(o.snapshot_count, 0) AS snapshot_count,
    COALESCE(o.symbol_count, 0) AS symbol_count,
    o.latest_timestamp,
    COALESCE(o.providers, '') AS observed_providers,
    COALESCE(o.data_sources, '') AS observed_data_sources
FROM factor_definitions fd
LEFT JOIN observed o ON o.factor_name = fd.factor_name
{where_clause}
ORDER BY fd.sort_order, fd.factor_name
"""
            r = await session.execute(text(sql), params)
            rows = []
            for row in r.fetchall():
                rows.append({
                    "factor_name": row[0],
                    "display_name": row[1],
                    "category": row[2],
                    "family": row[3],
                    "description": row[4],
                    "calculation": row[5],
                    "upstream_data": row[6],
                    "provider_hint": row[7],
                    "unit": row[8],
                    "default_interval": row[9],
                    "sort_order": row[10],
                    "is_active": row[11],
                    "snapshot_count": row[12],
                    "symbol_count": row[13],
                    "latest_timestamp": row[14].isoformat() if row[14] else None,
                    "observed_providers": [item.strip() for item in (row[15] or "").split(",") if item.strip()],
                    "observed_data_sources": [item.strip() for item in (row[16] or "").split(",") if item.strip()],
                })

            r = await session.execute(text("SELECT COUNT(*) FROM factor_snapshots"))
            snapshot_total = r.scalar() or 0
            r = await session.execute(text("SELECT COUNT(DISTINCT factor_name) FROM factor_snapshots"))
            observed_factor_count = r.scalar() or 0
            by_category: Dict[str, int] = {}
            for row in rows:
                by_category[row["category"]] = by_category.get(row["category"], 0) + 1

            return {
                "data": rows,
                "total": len(rows),
                "snapshot_total": snapshot_total,
                "observed_factor_count": observed_factor_count,
                "by_category": by_category,
            }
    except Exception as e:
        logger.error(f"Failed to fetch factor definitions: {e}", exc_info=True)
        return {"data": [], "total": 0, "error": str(e)}


@router.get("/factor-catalog")
async def get_factor_catalog(
    category: Optional[str] = Query(None, description="因子分类"),
    availabilityStatus: Optional[str] = Query(None, description="available / partial / unavailable"),
    q: Optional[str] = Query(None, description="Search factorName/displayName"),
    usedInBacktests: bool = Query(False),
    usedInAgentAudited: bool = Query(False),
) -> Dict[str, Any]:
    """Research asset catalog for factors, including availability and reverse links."""
    try:
        async with get_db() as session:
            items = await _build_factor_catalog(session)
            if category and category != "all":
                items = [item for item in items if item.get("category") == category]
            if availabilityStatus and availabilityStatus != "all":
                items = [item for item in items if item.get("availabilityStatus") == availabilityStatus]
            if q:
                needle = q.strip().lower()
                items = [
                    item for item in items
                    if needle in str(item.get("factorName", "")).lower()
                    or needle in str(item.get("displayName", "")).lower()
                ]
            if usedInBacktests:
                items = [item for item in items if int(item.get("usedInBacktests") or 0) > 0]
            if usedInAgentAudited:
                items = [item for item in items if int(item.get("usedInAgentAudited") or 0) > 0]

            return {
                "data": items,
                "total": len(items),
                "categories": FACTOR_CATEGORY_ORDER,
                "availabilityStatuses": ["available", "partial", "unavailable"],
            }
    except Exception as e:
        logger.error(f"Failed to fetch factor catalog: {e}", exc_info=True)
        return {"data": [], "total": 0, "error": str(e)}


@router.get("/factors/{factor_name}/detail")
async def get_factor_detail(factor_name: str) -> Dict[str, Any]:
    """Factor detail with reverse links to strategies, signals, and backtests."""
    name = factor_name.strip().lower()
    try:
        async with get_db() as session:
            catalog = await _build_factor_catalog(session)
            item = next((factor for factor in catalog if factor.get("factorName") == name), None)
            if not item:
                item = factor_blueprint(name)

            snapshots_result = await session.execute(text("""
SELECT id, symbol, timestamp, factor_value, interval, provider, data_source, source_version, available_time, as_of_time
FROM factor_snapshots
WHERE LOWER(factor_name) = :factor_name
ORDER BY timestamp DESC
LIMIT 20
"""), {"factor_name": name})
            recent_snapshots = [
                {
                    "id": row[0],
                    "symbol": row[1],
                    "timestamp": _iso(row[2]),
                    "value": row[3],
                    "interval": row[4],
                    "provider": row[5],
                    "dataSource": row[6],
                    "sourceVersion": row[7],
                    "availableTime": _iso(row[8]),
                    "asOfTime": _iso(row[9]),
                }
                for row in snapshots_result.fetchall()
            ]

            signals_result = await session.execute(text("""
SELECT id, symbol, timestamp, signal_type, confidence, source_strategy, strategy_id
FROM signal_events
WHERE factors ? :factor_name
ORDER BY timestamp DESC
LIMIT 20
"""), {"factor_name": name})
            recent_signals = [
                {
                    "signalId": row[0],
                    "symbol": row[1],
                    "triggeredAt": _iso(row[2]),
                    "signalType": row[3],
                    "confidence": row[4],
                    "sourceStrategy": row[5],
                    "strategyId": row[6],
                }
                for row in signals_result.fetchall()
            ]

            return {
                **item,
                "recentSnapshots": recent_snapshots,
                "recentSignals": recent_signals,
                "lastBacktestAt": item.get("latestBacktestAt"),
                "lastSignalAt": item.get("latestSignalAt"),
                "participatesInAgentAudited": int(item.get("usedInAgentAudited") or 0) > 0,
            }
    except Exception as e:
        logger.error(f"Failed to fetch factor detail: {e}", exc_info=True)
        return {"factorName": name, "recentSnapshots": [], "recentSignals": [], "error": str(e)}


@router.get("/strategies")
async def get_strategy_assets() -> Dict[str, Any]:
    """List strategy research assets with factor usage and recent backtest stats."""
    try:
        from app.services.strategy_templates import get_all_templates_meta

        async with get_db() as session:
            backtest_stats = await _load_backtest_stats(session)
            signal_stats = await _load_strategy_signal_stats(session)
            templates = {item["id"]: item for item in get_all_templates_meta(include_all=True)}
            strategy_ids = sorted(set(templates.keys()) | set(backtest_stats.keys()) | set(signal_stats.keys()))
            rows = [
                _build_strategy_asset(strategy_id, templates.get(strategy_id), backtest_stats, signal_stats)
                for strategy_id in strategy_ids
            ]
            return {"data": rows, "total": len(rows)}
    except Exception as e:
        logger.error(f"Failed to fetch strategy assets: {e}", exc_info=True)
        return {"data": [], "total": 0, "error": str(e)}


@router.get("/strategies/{strategy_type}/detail")
async def get_strategy_detail(strategy_type: str) -> Dict[str, Any]:
    """Strategy detail with used factors and signal/backtest linkage."""
    strategy_id = strategy_type.strip()
    try:
        from app.services.strategy_templates import get_all_templates_meta

        async with get_db() as session:
            backtest_stats = await _load_backtest_stats(session)
            signal_stats = await _load_strategy_signal_stats(session)
            templates = {item["id"]: item for item in get_all_templates_meta(include_all=True)}
            asset = _build_strategy_asset(strategy_id, templates.get(strategy_id), backtest_stats, signal_stats)

            signals_result = await session.execute(text("""
SELECT id, symbol, timestamp, signal_type, confidence
FROM signal_events
WHERE source_strategy = :strategy_id
ORDER BY timestamp DESC
LIMIT 20
"""), {"strategy_id": strategy_id})
            asset["recentSignals"] = [
                {
                    "signalId": row[0],
                    "symbol": row[1],
                    "triggeredAt": _iso(row[2]),
                    "signalType": row[3],
                    "confidence": row[4],
                }
                for row in signals_result.fetchall()
            ]
            return asset
    except Exception as e:
        logger.error(f"Failed to fetch strategy detail: {e}", exc_info=True)
        return {"strategyId": strategy_id, "usedFactors": [], "recentSignals": [], "error": str(e)}


@router.get("/factors/{symbol}/{factor_name}/series")
async def get_factor_series(
    symbol: str,
    factor_name: str,
    limit: int = Query(500, ge=1, le=5000),
) -> Dict[str, Any]:
    """Return a time series of values for a specific factor."""
    try:
        async with get_db() as session:
            sql = """SELECT timestamp, factor_value, parameters
FROM factor_snapshots
WHERE symbol = :symbol AND factor_name = :factor_name
ORDER BY timestamp ASC LIMIT :limit"""
            r = await session.execute(text(sql), {
                "symbol": symbol, "factor_name": factor_name, "limit": limit,
            })
            rows = []
            for row in r.fetchall():
                rows.append({
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "value": row[1],
                    "parameters": row[2] or {},
                })
            return {"symbol": symbol, "factor_name": factor_name, "data": rows, "count": len(rows)}
    except Exception as e:
        logger.error(f"Failed to fetch factor series: {e}")
        return {"symbol": symbol, "factor_name": factor_name, "data": [], "error": str(e)}


@router.get("/events")
async def get_events(
    symbol: Optional[str] = Query(None),
    signal_type: Optional[str] = Query(None, description="BUY, SELL, WAIT, etc."),
    source_strategy: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List signal events with optional filters and pagination."""
    try:
        async with get_db() as session:
            conditions = []
            params: Dict[str, Any] = {}
            if symbol:
                conditions.append("symbol = :symbol")
                params["symbol"] = symbol
            if signal_type:
                conditions.append("signal_type = :signal_type")
                params["signal_type"] = signal_type
            if source_strategy:
                conditions.append("source_strategy = :source_strategy")
                params["source_strategy"] = source_strategy

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            count_sql = f"SELECT COUNT(*) FROM signal_events WHERE {where_clause}"
            r = await session.execute(text(count_sql), params)
            total = r.scalar() or 0

            query_sql = f"""SELECT id, symbol, timestamp, signal_type, signal_value, confidence, source_strategy, strategy_id, factors,
interval, provider, data_source, source_version, schema_version, available_time, as_of_time
FROM signal_events WHERE {where_clause}
ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"""
            params["limit"] = limit
            params["offset"] = offset
            r = await session.execute(text(query_sql), params)
            rows = []
            for row in r.fetchall():
                rows.append({
                    "id": row[0],
                    "symbol": row[1],
                    "timestamp": row[2].isoformat() if row[2] else None,
                    "signal_type": row[3],
                    "signal_value": row[4],
                    "confidence": round(row[5], 4) if row[5] else 0,
                    "source_strategy": row[6],
                    "strategy_id": row[7],
                    "factors": row[8] or {},
                    "interval": row[9],
                    "provider": row[10],
                    "data_source": row[11],
                    "source_version": row[12],
                    "schema_version": row[13],
                    "available_time": row[14].isoformat() if row[14] else None,
                    "as_of_time": row[15].isoformat() if row[15] else None,
                })

            return {"data": rows, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}")
        return {"data": [], "total": 0, "error": str(e)}


@router.get("/events/{signal_id}/detail")
async def get_signal_event_detail(signal_id: int) -> Dict[str, Any]:
    """SignalEvent detail with factor evidence and downstream linkage."""
    try:
        async with get_db() as session:
            result = await session.execute(text("""
SELECT id, symbol, timestamp, event_time, available_time, as_of_time,
       signal_type, signal_value, confidence, source_strategy, strategy_id,
       factors, extra_data, interval, provider, data_source, source_version, schema_version
FROM signal_events
WHERE id = :signal_id
"""), {"signal_id": signal_id})
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"SignalEvent {signal_id} not found")

            factors = row[11] or {}
            related_factors = signal_related_factor_names(factors)
            source_strategy = row[9] or ""

            decision_rows = await session.execute(text("""
SELECT id, final_signal, confidence, timestamp, created_at
FROM coordination_history
WHERE input_snapshot_ids::text LIKE :needle
ORDER BY created_at DESC
LIMIT 10
"""), {"needle": f"%{signal_id}%"})
            decisions = [
                {
                    "decisionId": drow[0],
                    "finalSignal": drow[1],
                    "confidence": drow[2],
                    "asOfTime": _iso(drow[3]),
                    "createdAt": _iso(drow[4]),
                }
                for drow in decision_rows.fetchall()
            ]

            audit_rows_result = await session.execute(text("""
SELECT id, action, resource, details, created_at
FROM audit_logs
WHERE details::text LIKE :needle
ORDER BY created_at DESC
LIMIT 30
"""), {"needle": f"%{signal_id}%"})
            audit_rows = audit_rows_result.fetchall()
            audits = [
                {
                    "auditId": arow[0],
                    "eventType": arow[1],
                    "symbol": arow[2],
                    "createdAt": _iso(arow[4]),
                }
                for arow in audit_rows
            ]

            backtest_rows = await session.execute(text("""
SELECT id, strategy_type, symbol, interval, created_at, metrics
FROM backtest_results
WHERE trades_summary::text LIKE :needle OR metrics::text LIKE :needle
ORDER BY created_at DESC
LIMIT 20
"""), {"needle": f"%{signal_id}%"})
            backtests = [
                {
                    "backtestId": brow[0],
                    "strategyType": brow[1],
                    "symbol": brow[2],
                    "interval": brow[3],
                    "createdAt": _iso(brow[4]),
                    "executionMode": (brow[5] or {}).get("executionMode") or (brow[5] or {}).get("execution_mode"),
                }
                for brow in backtest_rows.fetchall()
            ]

            related_order_intent_id = None
            related_order_id = None
            related_replay_session_id = None
            for arow in audit_rows:
                details = arow[3] or {}
                related_order_intent_id = related_order_intent_id or _extract_related_value(
                    details, "orderIntentId", "order_intent_id", "relatedOrderIntentId", "client_order_id"
                )
                related_order_id = related_order_id or _extract_related_value(
                    details, "orderId", "order_id", "relatedOrderId"
                )
                related_replay_session_id = related_replay_session_id or _extract_related_value(
                    details, "replaySessionId", "replay_session_id"
                )

            return {
                "signalId": row[0],
                "symbol": row[1],
                "signalType": row[6],
                "strength": row[7],
                "confidence": row[8],
                "triggeredAt": _iso(row[2]),
                "eventTime": _iso(row[3]),
                "availableTime": _iso(row[4]),
                "asOfTime": _iso(row[5]),
                "sourceStrategy": source_strategy,
                "strategyId": row[10],
                "relatedFactors": related_factors,
                "factorValues": factors,
                "triggerCondition": f"{source_strategy or 'strategy'} 根据 {', '.join(related_factors[:8]) or '暂无因子'} 触发 {row[6]} 信号",
                "explanation": f"该信号由 {source_strategy or '未知策略'} 生成，触发时已保存因子快照引用，后续可继续追踪到决策、交易意图、回测和审计。",
                "whetherTriggeredAgent": bool(decisions or any((bt.get("executionMode") == "agent_audited") for bt in backtests)),
                "relatedDecisionId": decisions[0]["decisionId"] if decisions else None,
                "relatedOrderIntentId": related_order_intent_id,
                "relatedOrderId": related_order_id,
                "relatedBacktestId": backtests[0]["backtestId"] if backtests else None,
                "relatedReplaySessionId": related_replay_session_id,
                "relatedAuditIds": [item["auditId"] for item in audits],
                "relatedDecisions": decisions,
                "relatedBacktests": backtests,
                "relatedAudits": audits,
                "extraData": row[12] or {},
                "interval": row[13],
                "provider": row[14],
                "dataSource": row[15],
                "sourceVersion": row[16],
                "schemaVersion": row[17],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch signal event detail: {e}", exc_info=True)
        return {"signalId": signal_id, "relatedFactors": [], "relatedAuditIds": [], "error": str(e)}


@router.get("/summary")
async def get_signals_summary() -> Dict[str, Any]:
    """Aggregated summary: signal type distribution, strategy breakdown, symbol counts."""
    try:
        async with get_db() as session:
            # Signal type distribution
            r = await session.execute(text(
                "SELECT signal_type, COUNT(*) as cnt FROM signal_events GROUP BY signal_type ORDER BY cnt DESC"
            ))
            by_type = {row[0]: row[1] for row in r.fetchall()}

            # Strategy distribution
            r = await session.execute(text(
                "SELECT source_strategy, COUNT(*) as cnt FROM signal_events GROUP BY source_strategy ORDER BY cnt DESC"
            ))
            by_strategy = {row[0]: row[1] for row in r.fetchall()}

            # Symbol distribution
            r = await session.execute(text(
                "SELECT symbol, COUNT(*) as cnt FROM signal_events GROUP BY symbol ORDER BY cnt DESC"
            ))
            by_symbol = {row[0]: row[1] for row in r.fetchall()}

            # Total counts
            r = await session.execute(text("SELECT COUNT(*) FROM signal_events"))
            event_total = r.scalar() or 0
            r = await session.execute(text("SELECT COUNT(*) FROM factor_snapshots"))
            factor_total = r.scalar() or 0
            r = await session.execute(text("SELECT COUNT(DISTINCT factor_name) FROM factor_snapshots"))
            distinct_factor_count = r.scalar() or 0

            r = await session.execute(text("""
SELECT COALESCE(fd.category, '未分类') AS category, COUNT(DISTINCT fs.factor_name) AS cnt
FROM factor_snapshots fs
LEFT JOIN factor_definitions fd ON fd.factor_name = fs.factor_name
GROUP BY COALESCE(fd.category, '未分类')
ORDER BY cnt DESC
"""))
            by_factor_category = {row[0]: row[1] for row in r.fetchall()}

            # Recent signals (last 7 days)
            r = await session.execute(text(
                "SELECT COUNT(*) FROM signal_events WHERE timestamp >= NOW() - INTERVAL '7 days'"
            ))
            recent_7d = r.scalar() or 0

            return {
                "factor_total": factor_total,
                "distinct_factor_count": distinct_factor_count,
                "event_total": event_total,
                "recent_7d": recent_7d,
                "by_signal_type": by_type,
                "by_strategy": by_strategy,
                "by_symbol": by_symbol,
                "by_factor_category": by_factor_category,
            }
    except Exception as e:
        logger.error(f"Failed to fetch signals summary: {e}")
        return {"error": str(e)}
