"""Coordination decision history endpoints."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.services.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/history")
async def get_coordination_history(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List past coordination decisions with pagination."""
    try:
        async with get_db() as session:
            conditions = []
            params: Dict[str, Any] = {}
            if symbol:
                conditions.append("symbol = :symbol")
                params["symbol"] = symbol
            where_clause = " AND ".join(conditions) if conditions else "1=1"

            count_sql = f"SELECT COUNT(*) FROM coordination_history WHERE {where_clause}"
            r = await session.execute(text(count_sql), params)
            total = r.scalar() or 0

            query_sql = f"""SELECT id, symbol, timestamp, final_signal, confidence, vote_breakdown, risk_veto, summary, agent_signals
FROM coordination_history WHERE {where_clause}
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
                    "final_signal": row[3],
                    "confidence": round(row[4], 3) if row[4] else 0,
                    "vote_breakdown": row[5] or {},
                    "risk_veto": row[6],
                    "summary": row[7] or "",
                    "agent_signals": row[8] or [],
                })
            return {"data": rows, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Failed to fetch coordination history: {e}")
        return {"data": [], "total": 0, "error": str(e)}


@router.get("/latest")
async def get_latest_coordination(
    symbol: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Return the most recent coordination decision."""
    try:
        async with get_db() as session:
            if symbol:
                sql = """SELECT id, symbol, timestamp, final_signal, confidence, vote_breakdown, risk_veto, summary, agent_signals
FROM coordination_history WHERE symbol = :symbol ORDER BY timestamp DESC LIMIT 1"""
                r = await session.execute(text(sql), {"symbol": symbol})
            else:
                sql = """SELECT id, symbol, timestamp, final_signal, confidence, vote_breakdown, risk_veto, summary, agent_signals
FROM coordination_history ORDER BY timestamp DESC LIMIT 1"""
                r = await session.execute(text(sql))

            row = r.fetchone()
            if not row:
                return {"data": None}
            return {"data": {
                "id": row[0],
                "symbol": row[1],
                "timestamp": row[2].isoformat() if row[2] else None,
                "final_signal": row[3],
                "confidence": round(row[4], 3) if row[4] else 0,
                "vote_breakdown": row[5] or {},
                "risk_veto": row[6],
                "summary": row[7] or "",
                "agent_signals": row[8] or [],
            }}
    except Exception as e:
        logger.error(f"Failed to fetch latest coordination: {e}")
        return {"data": None, "error": str(e)}


@router.get("/stats")
async def get_coordination_stats() -> Dict[str, Any]:
    """Aggregated statistics for coordination decisions."""
    try:
        async with get_db() as session:
            r = await session.execute(text("SELECT COUNT(*) FROM coordination_history"))
            total = r.scalar() or 0

            r = await session.execute(text(
                "SELECT final_signal, COUNT(*) as cnt FROM coordination_history GROUP BY final_signal ORDER BY cnt DESC"
            ))
            by_signal = {row[0]: row[1] for row in r.fetchall()}

            r = await session.execute(text("SELECT AVG(confidence) FROM coordination_history"))
            avg_conf = r.scalar() or 0

            r = await session.execute(text(
                "SELECT COUNT(*) FROM coordination_history WHERE risk_veto = true"
            ))
            veto_count = r.scalar() or 0

            r = await session.execute(text(
                "SELECT symbol, COUNT(*) as cnt FROM coordination_history GROUP BY symbol ORDER BY cnt DESC LIMIT 10"
            ))
            by_symbol = {row[0]: row[1] for row in r.fetchall()}

            r = await session.execute(text(
                "SELECT COUNT(*) FROM coordination_history WHERE timestamp >= NOW() - INTERVAL '7 days'"
            ))
            recent_7d = r.scalar() or 0

            return {
                "total": total,
                "recent_7d": recent_7d,
                "avg_confidence": round(avg_conf, 3),
                "veto_count": veto_count,
                "by_signal": by_signal,
                "by_symbol": by_symbol,
            }
    except Exception as e:
        logger.error(f"Failed to fetch coordination stats: {e}")
        return {"error": str(e)}


@router.get("/{decision_id}")
async def get_coordination_detail(decision_id: int) -> Dict[str, Any]:
    """Return full detail for a single coordination decision."""
    try:
        async with get_db() as session:
            r = await session.execute(text(
                "SELECT id, symbol, timestamp, final_signal, confidence, vote_breakdown, risk_veto, summary, agent_signals FROM coordination_history WHERE id = :id"
            ), {"id": decision_id})
            row = r.fetchone()
            if not row:
                return {"data": None, "error": "Not found"}
            return {"data": {
                "id": row[0],
                "symbol": row[1],
                "timestamp": row[2].isoformat() if row[2] else None,
                "final_signal": row[3],
                "confidence": round(row[4], 3) if row[4] else 0,
                "vote_breakdown": row[5] or {},
                "risk_veto": row[6],
                "summary": row[7] or "",
                "agent_signals": row[8] or [],
            }}
    except Exception as e:
        logger.error(f"Failed to fetch coordination detail: {e}")
        return {"data": None, "error": str(e)}
