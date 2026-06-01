"""Execution-layer endpoints for PRD stage 2."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.order_intent_service import order_intent_service

router = APIRouter()
logger = logging.getLogger(__name__)


class DecisionExecutionRequest(BaseModel):
    decision_id: int = Field(..., description="coordination_history.id")
    exchange_id: str = Field("okx", description="Paper execution pricing exchange")
    position_pct: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="Optional target position ratio, e.g. 0.05 means 5% of paper equity",
    )


@router.post("/order-intents/preview")
async def preview_order_intent(req: DecisionExecutionRequest) -> Dict[str, Any]:
    """Convert a TradingAgents decision into a standard OrderIntent without placing an order."""
    try:
        return await order_intent_service.preview_from_decision(
            req.decision_id,
            exchange_id=req.exchange_id,
            position_pct=req.position_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("OrderIntent preview failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"OrderIntent preview failed: {exc}")


@router.post("/order-intents/execute")
async def execute_order_intent(req: DecisionExecutionRequest) -> Dict[str, Any]:
    """Manually execute a standard OrderIntent through RiskGuard and the paper account."""
    try:
        return await order_intent_service.execute_from_decision(
            req.decision_id,
            exchange_id=req.exchange_id,
            position_pct=req.position_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("OrderIntent execution failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"OrderIntent execution failed: {exc}")


@router.get("/order-intents/latest")
async def latest_order_intent_audit(
    symbol: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Return recent OrderIntent audit events from the existing immutable audit log stream."""
    from sqlalchemy import text
    from app.services.database import get_db

    where = "action LIKE 'ORDER_INTENT_%'"
    params: Dict[str, Any] = {"limit": limit}
    if symbol:
        where += " AND resource = :symbol"
        params["symbol"] = symbol.upper()
    async with get_db() as session:
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT id, action, resource, details, created_at
                    FROM audit_logs
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).fetchall()
    return {
        "data": [
            {
                "id": row[0],
                "action": row[1],
                "symbol": row[2],
                "details": row[3] or {},
                "created_at": row[4].isoformat() if row[4] else None,
            }
            for row in rows
        ]
    }
