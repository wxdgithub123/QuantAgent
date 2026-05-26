"""Factor snapshots & signal events endpoints."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from sqlalchemy import text, func

from app.services.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


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
            query_sql = f"""SELECT id, symbol, timestamp, factor_name, factor_value, parameters, source
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

            query_sql = f"""SELECT id, symbol, timestamp, signal_type, signal_value, confidence, source_strategy, strategy_id, factors
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
