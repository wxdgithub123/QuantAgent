"""
Trading Endpoints - Paper Trading
All endpoints simulate real exchange behavior using virtual USDT balance.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime

from app.services.paper_trading_service import paper_trading_service
from app.services.exchange_service import exchange_service
from app.services.order_intent_service import order_intent_service

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    symbol: str                              # e.g. "BTCUSDT"
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET"] = "MARKET"
    quantity: float
    price: Optional[float] = None            # If None, fetch real-time price
    exchange_id: Literal[
        "binance", "okx", "bybit", "gateio", "bitget", "coinbase", "kraken"
    ] = "okx"                                # Target exchange for simulated trading


class OrderResponse(BaseModel):
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float
    fee: float
    pnl: Optional[float]
    status: str
    created_at: str


# ─────────────────────────────────────────────────────────────────────────────
# Orders
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/orders", response_model=OrderResponse)
async def create_order(order: OrderRequest):
    """
    Place a paper trading order.
    - If price is not provided, fetches real-time price from the selected exchange.
    - BUY deducts USDT; SELL closes position and calculates PnL.
    """
    # Normalize symbol to ccxt format: "BTCUSDT" -> "BTC/USDT"

    # Get real-time price if not provided — use selected exchange
    if order.price is None:
        try:
            ticker = await exchange_service.get_ticker(order.exchange_id, order.symbol)
            exec_price = ticker.price
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"数据暂不可用，无法获取 {order.symbol} 的模拟成交参考价，请稍后重试。")
    else:
        exec_price = order.price

    try:
        intent_result = await order_intent_service.execute_manual_order(
            symbol=order.symbol.upper(),
            side=order.side,
            quantity=order.quantity,
            price=exec_price,
            order_type=order.order_type,
            exchange_id=order.exchange_id,
        )
        if intent_result.get("status") == "BLOCKED":
            reason = intent_result.get("blockedReason") or intent_result.get("message") or "RiskGuard blocked order"
            raise ValueError(str(reason))
        result = intent_result.get("execution") or {}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="数据暂不可用，模拟下单暂时无法完成，请稍后重试。")

    return OrderResponse(**result)


@router.get("/orders")
async def get_orders(
    symbol: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get order / trade history, newest first."""
    try:
        data = await paper_trading_service.get_orders(symbol=symbol, limit=limit)
        data.setdefault("status", "ok")
        data.setdefault("metadata", {
            "data_source": "paper_trades",
            "last_updated": datetime.utcnow().isoformat(),
            "is_cached": False,
            "fallback_source": None,
            "degraded": False,
        })
        return data
    except Exception as exc:
        return {
            "status": "error",
            "orders": [],
            "total": 0,
            "metadata": {
                "data_source": "paper_trades",
                "last_updated": datetime.utcnow().isoformat(),
                "is_cached": False,
                "fallback_source": None,
                "degraded": True,
                "message": "数据暂不可用，暂无订单数据。",
                "error": str(exc)[:200],
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Positions
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/positions")
async def get_positions(
    exchange_id: Optional[str] = Query("okx", description="交易所 ID，用于获取实时价格计算持仓盈亏"),
):
    """
    Get current open positions with real-time PnL.
    Fetches latest prices from the selected exchange for each held symbol.
    """
    now = datetime.utcnow().isoformat()
    metadata: Dict[str, Any] = {
        "data_source": "paper_positions",
        "price_source": f"CCXT/{str(exchange_id).upper()} mark price",
        "last_updated": now,
        "is_cached": False,
        "fallback_source": None,
        "degraded": False,
        "message": "本地模拟盘持仓数据。",
    }
    try:
        # PaperTradingService already computes mark price once and falls back to
        # avgEntryPrice if the selected exchange is temporarily unavailable.
        positions = await paper_trading_service.get_positions(exchange_id=exchange_id)
    except Exception as exc:
        return {
            "status": "error",
            "positions": [],
            "metadata": {
                **metadata,
                "degraded": True,
                "message": "数据暂不可用，暂无持仓数据。",
                "error": str(exc)[:200],
            },
        }
    if not positions:
        return {"status": "ok", "positions": [], "metadata": metadata}

    latest_update = max((p.get("updatedAt") or p.get("updated_at") or "" for p in positions), default="")
    if latest_update:
        metadata["last_updated"] = latest_update
    return {"status": "ok", "positions": positions, "metadata": metadata}


@router.post("/positions/close-all")
async def close_all_positions(
    exchange_id: Optional[str] = Query("okx", description="交易所 ID"),
):
    """Close every open position at current market price."""
    positions_raw = await paper_trading_service.get_positions(exchange_id=exchange_id)
    if not positions_raw:
        return {"message": "No open positions", "results": []}

    current_prices: Dict[str, float] = {}
    for pos in positions_raw:
        symbol = pos["symbol"]
        try:
            ticker = await exchange_service.get_ticker(exchange_id, symbol)
            current_prices[symbol] = ticker.price
        except Exception:
            current_prices[symbol] = pos["avg_price"]

    results = await paper_trading_service.close_all_positions(current_prices, exchange_id=exchange_id)
    return {"message": "Positions closed", "results": results}


# ─────────────────────────────────────────────────────────────────────────────
# Balance
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/balance")
async def get_balance():
    """Get virtual USDT account balance."""
    return await paper_trading_service.get_balance()


@router.get("/risk-status")
async def get_risk_status(
    exchange_id: Optional[str] = Query("okx", description="交易所 ID"),
):
    """Get current account risk metrics and status."""
    from app.services.risk_manager import risk_manager

    try:
        # 1. Balance
        balance_data = await paper_trading_service.get_balance()
        available = balance_data.get("available_balance", 0.0)

        # 2. Positions Value (Mark-to-Market). The service performs one price
        # lookup per held symbol and falls back internally, so this endpoint
        # should not fetch prices a second time.
        positions = await paper_trading_service.get_positions(exchange_id=exchange_id)

        pos_value = 0.0
        for p in positions:
            price = p.get("mark_price", p.get("markPrice", p.get("avg_price", 0.0)))
            qty = abs(p.get("quantity", 0.0))
            pos_value += qty * price

        total_portfolio = available + pos_value

        data = await risk_manager.get_risk_status(total_portfolio, positions=positions)
        data["metadata"] = {
            "data_source": "risk_guard",
            "last_updated": datetime.utcnow().isoformat(),
            "is_cached": False,
            "fallback_source": None,
            "degraded": False,
        }
        return data
    except Exception as exc:
        return {
            "status": "error",
            "kill_switch_active": False,
            "drawdown_breached": False,
            "total_drawdown_pct": 0,
            "drawdown_limit_pct": 0,
            "daily_loss_breached": False,
            "daily_pnl": 0,
            "daily_loss_limit_pct": 0,
            "single_position_limit_pct": 0,
            "total_exposure_limit_pct": 0,
            "max_leverage": 1,
            "checked_rules": [],
            "metadata": {
                "data_source": "risk_guard",
                "last_updated": datetime.utcnow().isoformat(),
                "is_cached": False,
                "fallback_source": None,
                "degraded": True,
                "message": "数据暂不可用，暂无风控状态。",
                "error": str(exc)[:200],
            },
        }


@router.get("/workbench")
async def get_paper_trading_workbench(
    symbol: Optional[str] = Query(None, description="Optional symbol filter"),
    exchange_id: Optional[str] = Query("okx", description="Paper execution exchange"),
    limit: int = Query(25, ge=1, le=100),
):
    """Return the Phase 2 paper-trading workbench read model."""
    from app.services.paper_trading_workbench import build_paper_trading_workbench

    normalized_symbol = symbol.upper().replace("/", "") if symbol else None
    return await build_paper_trading_workbench(
        symbol=normalized_symbol,
        exchange_id=exchange_id or "okx",
        limit=limit,
    )


@router.get("/macro-status")
async def get_macro_status(symbol: str = "BTCUSDT"):
    """获取当前宏观经济与链上指标状态 (Smart Beta & Anti-Black Swan)"""
    from app.services.macro_analysis_service import macro_analysis_service
    return await macro_analysis_service.get_macro_score(symbol)
