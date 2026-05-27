"""Factor snapshots & signal events endpoints."""

import logging
from typing import Any, Dict, List, Optional

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.services.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


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
            params: Dict[str, Any] = {}
            if symbol:
                conditions.append("symbol = :symbol")
                params["symbol"] = symbol
            if factor_name:
                conditions.append("factor_name = :factor_name")
                params["factor_name"] = factor_name

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # Count
            count_sql = f"SELECT COUNT(*) FROM factor_snapshots WHERE {where_clause}"
            r = await session.execute(text(count_sql), params)
            total = r.scalar() or 0

            # Query
            query_sql = f"""SELECT id, symbol, timestamp, factor_name, factor_value, parameters, source,
interval, provider, data_source, source_version, schema_version, available_time, as_of_time
FROM factor_snapshots WHERE {where_clause}
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
                })

            return {"data": rows, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Failed to fetch factors: {e}")
        return {"data": [], "total": 0, "error": str(e)}


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

            # Recent signals (last 7 days)
            r = await session.execute(text(
                "SELECT COUNT(*) FROM signal_events WHERE timestamp >= NOW() - INTERVAL '7 days'"
            ))
            recent_7d = r.scalar() or 0

            return {
                "factor_total": factor_total,
                "event_total": event_total,
                "recent_7d": recent_7d,
                "by_signal_type": by_type,
                "by_strategy": by_strategy,
                "by_symbol": by_symbol,
            }
    except Exception as e:
        logger.error(f"Failed to fetch signals summary: {e}")
        return {"error": str(e)}
