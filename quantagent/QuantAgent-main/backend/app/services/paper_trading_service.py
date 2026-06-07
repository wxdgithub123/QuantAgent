"""
Paper Trading Service
Handles virtual account management, order execution, and position tracking.
All state is persisted to PostgreSQL; hot data cached in Redis.
Risk pre-checks are delegated to RiskManager before any BUY order is executed.
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any

from sqlalchemy import select, delete, func as sqlfunc
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.services.database import get_db, redis_get, redis_set, redis_delete
from app.models.db_models import (
    PaperAccount,
    PaperAccountReplay,
    PaperPosition,
    PaperTrade,
    EquitySnapshot,
)
from app.services.audit_service import audit_service
from app.services.risk_manager import risk_manager
from app.services.exchange_service import exchange_service

logger = logging.getLogger(__name__)

# Fee rate: 0.1% per trade (generic spot taker-like simulation)
FEE_RATE = Decimal("0.001")
SLIPPAGE_PCT = Decimal("0.0005")  # 0.05% slippage for market orders
INITIAL_BALANCE = Decimal("100000.0")

# Redis cache keys
REDIS_BALANCE_KEY = "paper:balance"
REDIS_POSITIONS_KEY = "paper:positions"
REDIS_REPLAY_BALANCE_PREFIX = "replay:balance:"  # + session_id


class PaperTradingService:
    """
    Simulated trading engine.
    - Fetches real-time price from the selected CCXT exchange at order time
    - Persists all trades/positions to PostgreSQL
    - Caches balance + positions in Redis (TTL 10s)
    """

    def __init__(self):
        self.simulated_time: Optional[datetime] = None

    def set_simulated_time(self, timestamp: datetime):
        """Set simulated time for historical replay mode"""
        self.simulated_time = timestamp
        logger.debug(f"PaperTradingService simulated time set to: {timestamp}")

    def _get_current_time(self) -> datetime:
        """Get current time (real or simulated)"""
        return self.simulated_time or datetime.now(timezone.utc)

    @staticmethod
    def _source_from_trade(trade: Optional[PaperTrade], mode: str = "paper") -> str:
        if mode in {"backtest", "historical_replay"}:
            return "backtest"
        if not trade:
            return "manual"
        strategy = (trade.strategy_id or "").lower()
        client_order_id = trade.client_order_id or ""
        if strategy in {"tradingagents", "agent"}:
            return "agent"
        if strategy == "manual":
            return "manual"
        if client_order_id.startswith("OI-") and not client_order_id.startswith("OI-MANUAL-"):
            return "agent"
        return "manual"

    @staticmethod
    def _decision_id_from_order_intent(order_intent_id: Optional[str]) -> Optional[int]:
        if not order_intent_id or not order_intent_id.startswith("OI-"):
            return None
        parts = order_intent_id.split("-")
        if len(parts) < 2 or parts[1].upper() == "MANUAL":
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None

    def _execution_audit_payload(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        fee: Optional[Decimal],
        status: str,
        order_id: Optional[str] = None,
        order_intent_id: Optional[str] = None,
        benchmark_price: Optional[float] = None,
        pnl: Optional[Decimal] = None,
        new_position_qty: Optional[Decimal] = None,
        source: str = "paper",
        mode: str = "paper",
        session_id: Optional[str] = None,
        order_type: str = "MARKET",
        slippage: Optional[float] = None,
        filled_at: Optional[datetime] = None,
        risk_result: Optional[Any] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        decision_id = self._decision_id_from_order_intent(order_intent_id)
        risk_payload: Dict[str, Any] = {"passed": True, "allowed": True}
        if risk_result is not None:
            risk_payload = {
                "passed": bool(getattr(risk_result, "allowed", False)),
                "allowed": bool(getattr(risk_result, "allowed", False)),
                "rule": getattr(risk_result, "rule", None),
                "reason": getattr(risk_result, "reason", None),
                "blockedReason": getattr(risk_result, "reason", None),
            }
        execution_result = {
            "orderId": order_id,
            "order_id": order_id,
            "status": status,
            "source": source,
            "executionMode": mode,
            "side": side,
            "quantity": float(quantity),
            "fillPrice": float(price),
            "price": float(price),
            "benchmarkPrice": benchmark_price,
            "fee": float(fee) if fee is not None else None,
            "realizedPnl": float(pnl) if pnl is not None else None,
            "pnl": float(pnl) if pnl is not None else None,
            "slippage": slippage,
            "filledAt": filled_at.isoformat() if filled_at else None,
            "positionAfterTrade": (
                {"symbol": symbol, "quantity": float(new_position_qty)}
                if new_position_qty is not None
                else None
            ),
        }
        payload = {
            "symbol": symbol,
            "decisionId": decision_id,
            "sourceDecisionId": decision_id,
            "orderIntentId": order_intent_id,
            "orderId": order_id,
            "order_id": order_id,
            "replaySessionId": session_id,
            "replay_session_id": session_id,
            "executionMode": mode,
            "asOfTime": filled_at.isoformat() if filled_at else None,
            "action": side,
            "source": source,
            "intent": {
                "id": order_intent_id,
                "intent_id": order_intent_id,
                "symbol": symbol,
                "action": side,
                "side": side,
                "quantity": float(quantity),
                "order_type": order_type,
                "sourceDecisionId": decision_id,
                "decision_id": decision_id,
                "executionMode": mode,
                "status": status,
            },
            "riskCheckResult": risk_payload,
            "executionResult": execution_result,
        }
        if extra:
            payload.update(extra)
        return payload

    async def _audit_risk_blocked(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        reason: str,
        rule: str,
        client_order_id: Optional[str],
        mode: str,
        session_id: Optional[str],
        order_type: str,
        leverage: int,
    ) -> None:
        decision_id = self._decision_id_from_order_intent(client_order_id)
        await audit_service.log_event(
            action="RISK_BLOCKED",
            user_id="system",
            resource=symbol,
            details={
                "symbol": symbol,
                "decisionId": decision_id,
                "sourceDecisionId": decision_id,
                "orderIntentId": client_order_id,
                "replaySessionId": session_id,
                "replay_session_id": session_id,
                "executionMode": mode,
                "action": side,
                "intent": {
                    "id": client_order_id,
                    "intent_id": client_order_id,
                    "symbol": symbol,
                    "action": side,
                    "side": side,
                    "quantity": quantity,
                    "order_type": order_type,
                    "sourceDecisionId": decision_id,
                    "decision_id": decision_id,
                    "executionMode": mode,
                    "status": "BLOCKED",
                },
                "riskCheckResult": {
                    "passed": False,
                    "allowed": False,
                    "rule": rule,
                    "reason": reason,
                    "blockedReason": reason,
                    "blocked_reason": reason,
                    "checkedRules": [
                        {
                            "ruleName": rule,
                            "passed": False,
                            "message": reason,
                        }
                    ],
                },
                "requestedOrder": {
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "price": price,
                    "leverage": leverage,
                    "order_type": order_type,
                },
            },
            ip_address="internal",
            raise_on_failure=True,
        )

    # ─────────────────────────────────────────────────────────────
    # Account Balance
    # ─────────────────────────────────────────────────────────────
    async def get_balance(
        self,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return current USDT balance.

        - With session_id: reads from the session-isolated PaperAccountReplay table.
        - Without session_id: reads from the global PaperAccount(id=1).
        """
        if session_id:
            # Session-isolated balance (replay mode)
            cache_key = f"{REDIS_REPLAY_BALANCE_PREFIX}{session_id}"
            cached = await redis_get(cache_key)
            if cached is not None:
                return cached

            async with get_db() as session:
                result = await session.execute(
                    select(PaperAccountReplay).where(
                        PaperAccountReplay.session_id == session_id
                    )
                )
                account = result.scalar_one_or_none()
                if account is None:
                    return {
                        "total_balance": 0.0,
                        "available_balance": 0.0,
                        "assets": [],
                        "session_id": session_id,
                        "initial_capital": 0.0,
                    }
                balance = float(account.total_usdt)
                data = {
                    "total_balance": balance,
                    "available_balance": balance,
                    "assets": [{"asset": "USDT", "free": balance, "locked": 0.0}],
                    "session_id": session_id,
                    "initial_capital": float(account.initial_capital),
                }
            await redis_set(cache_key, data, ttl=10)
            return data
        else:
            # Global paper trading balance (original logic)
            cached = await redis_get(REDIS_BALANCE_KEY)
            if cached is not None:
                return cached

            async with get_db() as session:
                result = await session.execute(
                    select(PaperAccount).where(PaperAccount.id == 1)
                )
                account = result.scalar_one_or_none()
                if account is None:
                    account = PaperAccount(id=1, total_usdt=INITIAL_BALANCE)
                    session.add(account)
                    await session.commit()
                    await session.refresh(account)

                balance = float(account.total_usdt)

            data = {
                "total_balance": balance,
                "available_balance": balance,
                "assets": [{"asset": "USDT", "free": balance, "locked": 0.0}],
            }
            await redis_set(REDIS_BALANCE_KEY, data, ttl=10)
            return data

    async def _get_usdt_balance(self, session) -> Decimal:
        result = await session.execute(select(PaperAccount).where(PaperAccount.id == 1))
        account = result.scalar_one_or_none()
        if account is None:
            account = PaperAccount(id=1, total_usdt=INITIAL_BALANCE)
            session.add(account)
            await session.flush()
        return Decimal(str(account.total_usdt))

    async def _update_usdt_balance(self, session, new_balance: Decimal):
        result = await session.execute(select(PaperAccount).where(PaperAccount.id == 1))
        account = result.scalar_one_or_none()
        now = self._get_current_time()
        if account is None:
            account = PaperAccount(id=1, total_usdt=new_balance, updated_at=now)
            session.add(account)
        else:
            account.total_usdt = new_balance
            account.updated_at = now
        await redis_delete(REDIS_BALANCE_KEY)

    # ── Session-isolated balance helpers (replay mode) ─────────────────────────
    async def _get_replay_usdt_balance(
        self, session_id: str, session
    ) -> Decimal:
        """Get USDT balance from the session-isolated replay account."""
        result = await session.execute(
            select(PaperAccountReplay).where(
                PaperAccountReplay.session_id == session_id
            )
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise ValueError(f"Replay account not found for session {session_id}")
        return Decimal(str(account.total_usdt))

    async def _update_replay_usdt_balance(
        self, session_id: str, session, new_balance: Decimal
    ):
        """Update balance for the session-isolated replay account."""
        result = await session.execute(
            select(PaperAccountReplay).where(
                PaperAccountReplay.session_id == session_id
            )
        )
        account = result.scalar_one_or_none()
        now = self._get_current_time()
        if account is None:
            raise ValueError(f"Replay account not found for session {session_id}")
        account.total_usdt = new_balance
        account.updated_at = now
        await redis_delete(f"{REDIS_REPLAY_BALANCE_PREFIX}{session_id}")

    # ─────────────────────────────────────────────────────────────
    # Positions
    # ─────────────────────────────────────────────────────────────
    async def get_positions(
        self,
        current_prices: Optional[Dict[str, float]] = None,
        session_id: Optional[str] = None,
        exchange_id: str = "okx",
    ) -> List[Dict[str, Any]]:
        """
        Return open positions with real-time PnL.
        current_prices: {symbol: price} dict for PnL calculation.
        If not provided, will try to fetch from ExchangeService.
        """
        # If no session_id, fallback to "paper" mode (global positions)
        async with get_db() as session:
            stmt = select(PaperPosition).where(
                PaperPosition.quantity != 0,
                PaperPosition.exchange_id == exchange_id,
            )
            if session_id:
                stmt = stmt.where(PaperPosition.session_id == session_id)
            else:
                stmt = stmt.where(PaperPosition.session_id.is_(None))

            result = await session.execute(stmt)
            rows = result.scalars().all()

        # Collect all symbols from positions
        symbols = [row.symbol for row in rows]

        latest_trade_by_symbol: Dict[str, PaperTrade] = {}
        if symbols:
            async with get_db() as session:
                trade_stmt = (
                    select(PaperTrade)
                    .where(PaperTrade.symbol.in_(symbols))
                    .where(PaperTrade.exchange_id == exchange_id)
                    .order_by(PaperTrade.created_at.desc())
                )
                if session_id:
                    trade_stmt = trade_stmt.where(PaperTrade.session_id == session_id)
                else:
                    trade_stmt = trade_stmt.where(PaperTrade.session_id.is_(None))
                trade_result = await session.execute(trade_stmt)
                for trade in trade_result.scalars().all():
                    if trade.symbol not in latest_trade_by_symbol:
                        latest_trade_by_symbol[trade.symbol] = trade

        # If no current_prices provided, try to get real-time prices
        prices_to_use = current_prices or {}
        if not current_prices and symbols:
            # Fetch real-time prices from ExchangeService
            for sym in set(symbols):
                try:
                    price = await exchange_service.get_price(exchange_id, sym)
                    prices_to_use[sym] = price
                except Exception as e:
                    logger.warning(f"Failed to fetch price for {sym} from {exchange_id}: {e}")
                    # Fallback to avg_price if we can't get real price
                    for row in rows:
                        if row.symbol == sym:
                            prices_to_use[sym] = float(row.avg_price)
                            break

        positions = []
        for row in rows:
            qty = float(row.quantity)
            avg = float(row.avg_price)
            symbol = row.symbol
            mark_price = prices_to_use.get(symbol, avg)

            # PnL Logic:
            # Long (Qty > 0): (Mark - Avg) * Qty
            # Short (Qty < 0): (Avg - Mark) * abs(Qty) = (Avg - Mark) * (-Qty) = (Mark - Avg) * Qty
            # Formula works for both.
            pnl = (mark_price - avg) * qty
            pnl_pct = (
                ((mark_price / avg) - 1) * 100 * (1 if qty > 0 else -1)
                if avg > 0
                else 0.0
            )
            latest_trade = latest_trade_by_symbol.get(symbol)
            related_intent_id = latest_trade.client_order_id if latest_trade else None
            related_decision_id = self._decision_id_from_order_intent(related_intent_id)
            source = self._source_from_trade(latest_trade, mode=latest_trade.mode if latest_trade else "paper")
            risk_status = "warning" if row.liquidation_price else "normal"

            positions.append(
                {
                    "symbol": symbol,
                    "side": "long" if qty > 0 else "short",
                    "quantity": qty,
                    "avg_price": avg,
                    "avgEntryPrice": avg,
                    "leverage": row.leverage,
                    "liquidation_price": float(row.liquidation_price)
                    if row.liquidation_price
                    else None,
                    "mark_price": mark_price,
                    "markPrice": mark_price,
                    "pnl": round(pnl, 4),
                    "unrealizedPnl": round(pnl, 4),
                    "pnl_pct": round(pnl_pct, 4),
                    "unrealizedPnlPct": round(pnl_pct, 4),
                    "source": source,
                    "relatedDecisionId": related_decision_id,
                    "relatedOrderIntentId": related_intent_id,
                    "riskStatus": risk_status,
                    "updated_at": row.updated_at.isoformat()
                    if row.updated_at
                    else None,
                    "updatedAt": row.updated_at.isoformat()
                    if row.updated_at
                    else None,
                }
            )

        # Always update cache (even with fetched prices) for consistency
        await redis_set(REDIS_POSITIONS_KEY, positions, ttl=10)
        return positions

    async def reset_session(self, initial_capital: float, session_id: str) -> None:
        """Reset a replay session to a clean state with its own isolated account."""
        async with get_db() as session:
            # 1. Clear session-scoped trades/positions/snapshots
            await session.execute(
                delete(PaperPosition).where(PaperPosition.session_id == session_id)
            )
            await session.execute(
                delete(PaperTrade).where(PaperTrade.session_id == session_id)
            )
            await session.execute(
                delete(EquitySnapshot).where(EquitySnapshot.session_id == session_id)
            )

            # 2. Create or reset the session's dedicated replay account
            result = await session.execute(
                select(PaperAccountReplay).where(
                    PaperAccountReplay.session_id == session_id
                )
            )
            existing = result.scalar_one_or_none()
            now = self._get_current_time()

            if existing:
                existing.total_usdt = Decimal(str(initial_capital))
                existing.initial_capital = Decimal(str(initial_capital))
                existing.updated_at = now
            else:
                new_account = PaperAccountReplay(
                    session_id=session_id,
                    total_usdt=Decimal(str(initial_capital)),
                    initial_capital=Decimal(str(initial_capital)),
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_account)

            await session.commit()

        # 3. Invalidate caches
        await redis_delete(f"{REDIS_REPLAY_BALANCE_PREFIX}{session_id}")
        await redis_delete(REDIS_POSITIONS_KEY)

    async def _get_position(
        self, session, symbol: str, session_id: Optional[str] = None, exchange_id: str = "okx"
    ) -> Optional[PaperPosition]:
        stmt = select(PaperPosition).where(PaperPosition.symbol == symbol).where(PaperPosition.exchange_id == exchange_id)
        if session_id:
            stmt = stmt.where(PaperPosition.session_id == session_id)
        else:
            stmt = stmt.where(PaperPosition.session_id.is_(None))

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    # ─────────────────────────────────────────────────────────────
    # Order Execution
    # ─────────────────────────────────────────────────────────────
    async def create_order(
        self,
        symbol: str,
        side: str,  # "BUY" | "SELL"
        quantity: float,
        price: float,  # real-time price from ExchangeService
        order_type: str = "MARKET",
        benchmark_price: Optional[float] = None,  # For TCA (Implementation Shortfall)
        client_order_id: Optional[str] = None,  # For idempotency
        leverage: int = 1,  # Leverage for margin simulation / liquidation price
        strategy_id: Optional[str] = None,  # Added for attribution
        mode: str = "paper",  # paper | backtest | historical_replay
        session_id: Optional[str] = None,  # For historical_replay session_id
        exchange_id: str = "okx",  # Target exchange for simulated trading
    ) -> Dict[str, Any]:
        """
        Execute a simulated market order or place a limit order.
        Performs risk pre-check before executing.
        Returns the created trade record dict.
        """
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side}")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if price <= 0:
            raise ValueError("Price must be positive")
        if leverage is None or int(leverage) <= 0:
            raise ValueError("Leverage must be a positive integer")
        leverage = int(leverage)

        # Get current time for all records
        now = self._get_current_time()

        # Idempotency check: if client_order_id provided, check for existing trade
        if client_order_id:
            async with get_db() as session:
                from sqlalchemy import select

                existing = await session.execute(
                    select(PaperTrade).where(
                        PaperTrade.client_order_id == client_order_id
                    )
                )
                existing_trade = existing.scalar_one_or_none()
                if existing_trade:
                    logger.info(
                        f"Duplicate order detected, returning existing trade {existing_trade.id} for client_order_id={client_order_id}"
                    )
                    return {
                        "order_id": f"PT-{existing_trade.id}",
                        "symbol": existing_trade.symbol,
                        "side": existing_trade.side,
                        "order_type": existing_trade.order_type,
                        "quantity": float(existing_trade.quantity),
                        "price": float(existing_trade.price),
                        "benchmark_price": float(existing_trade.benchmark_price)
                        if existing_trade.benchmark_price
                        else None,
                        "fee": float(existing_trade.fee),
                        "pnl": float(existing_trade.pnl)
                        if existing_trade.pnl
                        else None,
                        "status": existing_trade.status,
                        "created_at": existing_trade.created_at.isoformat()
                        if existing_trade.created_at
                        else now.isoformat(),
                        "duplicate": True,
                    }

        # Default benchmark to current price if not provided
        if benchmark_price is None:
            benchmark_price = price

        # ── 风控前置检查 ────────────────────────────────────────────────────
        balance_data = await self.get_balance(session_id=session_id)
        available_balance = balance_data.get("available_balance", 0.0)
        positions_data = await self.get_positions(session_id=session_id, exchange_id=exchange_id)
        current_positions = {p["symbol"]: p["quantity"] for p in positions_data}
        total_portfolio = available_balance + sum(
            p["quantity"] * p["mark_price"] for p in positions_data
        )

        # ── 核心兜底风控：名义价值绝对上限 ──────────────────────────────────────
        qty_dec = Decimal(str(quantity))
        price_dec = Decimal(str(price))
        
        # 名义价值 = 数量 * 价格
        notional_value = qty_dec * price_dec
        
        # 1. 绝对上限拦截：单笔订单名义价值不能超过总资产的 100%（容忍一点点滑点误差）
        # 这里我们使用 total_portfolio 的 1.05 倍作为硬性物理拦截线
        max_notional_allowed = Decimal(str(total_portfolio)) * Decimal("1.05")
        
        if notional_value > max_notional_allowed:
            block_reason = (
                f"[核心风控拦截] 订单名义价值过大！"
                f"请求名义价值: ${notional_value:.2f}, "
                f"当前总资产: ${Decimal(str(total_portfolio)):.2f}。"
                f"可能存在数量单位错误（如把 USDT 当成币种数量传入）。"
            )
            await self._audit_risk_blocked(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                reason=block_reason,
                rule="MAX_NOTIONAL_ABSOLUTE",
                client_order_id=client_order_id,
                mode=mode,
                session_id=session_id,
                order_type=order_type,
                leverage=leverage,
            )
            raise ValueError(block_reason)

        # All local simulated execution paths must pass RiskGuard before fill.
        # This includes manual paper trading, Agent-driven intents, backtests,
        # and historical replay. Real exchange order placement is not used here.
        if mode in {"paper", "backtest", "historical_replay"}:
            risk_result = await risk_manager.check_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                current_balance=available_balance,
                current_positions=current_positions,
                total_portfolio_value=total_portfolio,
                market_price=price,
                leverage=leverage,
            )
            if not risk_result.allowed:
                block_reason = f"[风控拦截] {risk_result.reason}"
                await self._audit_risk_blocked(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    reason=block_reason,
                    rule=getattr(risk_result, "rule", None) or "RISK_GUARD",
                    client_order_id=client_order_id,
                    mode=mode,
                    session_id=session_id,
                    order_type=order_type,
                    leverage=leverage,
                )
                raise ValueError(block_reason)
        else:
            # 仅做最基本的可用资金检查
            qty_dec = Decimal(str(quantity))
            price_dec = Decimal(str(price))
            
            # 判断是否为开仓/加仓操作
            current_qty = Decimal(str(current_positions.get(symbol, 0)))
            open_qty = Decimal("0")
            
            if side == "BUY":
                if current_qty >= 0:
                    open_qty = qty_dec
                elif qty_dec > abs(current_qty):
                    open_qty = qty_dec - abs(current_qty)
            elif side == "SELL":
                if current_qty <= 0:
                    open_qty = qty_dec
                elif qty_dec > current_qty:
                    open_qty = qty_dec - current_qty
                    
            if open_qty > 0:
                margin_required = open_qty * price_dec / Decimal(str(leverage))
                fee_est = qty_dec * price_dec * FEE_RATE
                total_cost = margin_required + fee_est
                avail_dec = Decimal(str(available_balance))
                if avail_dec < total_cost:
                    # 容忍 0.01 的浮点数舍入误差
                    if total_cost - avail_dec > Decimal("0.01"):
                        block_reason = f"[资金不足] {side} 需 ${total_cost:.2f}，可用 ${avail_dec:.2f}"
                        await self._audit_risk_blocked(
                            symbol=symbol,
                            side=side,
                            quantity=quantity,
                            price=price,
                            reason=block_reason,
                            rule="INSUFFICIENT_FUNDS",
                            client_order_id=client_order_id,
                            mode=mode,
                            session_id=session_id,
                            order_type=order_type,
                            leverage=leverage,
                        )
                        raise ValueError(block_reason)
        # ──────────────────────────────────────────────────────────────────

        qty_dec = Decimal(str(quantity))
        price_dec = Decimal(str(price))
        fee = qty_dec * price_dec * FEE_RATE

        # Handle LIMIT orders (PENDING -> NEW)
        if order_type == "LIMIT":
            async with get_db() as session:
                trade = PaperTrade(
                    client_order_id=client_order_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    exchange_id=exchange_id,
                    side=side,
                    order_type="LIMIT",
                    quantity=qty_dec,
                    price=price_dec,
                    leverage=leverage,
                    benchmark_price=Decimal(str(benchmark_price)),
                    fee=fee,
                    pnl=None,
                    status="NEW",
                    mode=mode,
                    session_id=session_id,
                    created_at=now,
                )
                session.add(trade)
                await session.commit()
                await session.refresh(trade)

                return {
                    "order_id": f"PT-{trade.id}",
                    "symbol": symbol,
                    "side": side,
                    "order_type": "LIMIT",
                    "quantity": float(qty_dec),
                    "price": float(price_dec),
                    "benchmark_price": float(benchmark_price),
                    "fee": float(fee),
                    "pnl": None,
                    "status": "NEW",
                    "created_at": now.isoformat(),
                }

        # MARKET execution (immediate fill)
        async with get_db() as session:
            # Apply Slippage for Market Orders
            # Buy: Execute higher
            # Sell: Execute lower
            slippage_mult = Decimal("1.0")
            if side == "BUY":
                slippage_mult = Decimal("1.0") + SLIPPAGE_PCT
            else:
                slippage_mult = Decimal("1.0") - SLIPPAGE_PCT

            # Adjust execution price
            price_dec = price_dec * slippage_mult

            realized_pnl, new_qty, new_avg = await self._apply_fill_to_account(
                session,
                symbol,
                side,
                qty_dec,
                price_dec,
                fee,
                leverage,
                strategy_id,
                session_id,
                exchange_id,
            )

            pnl_record = realized_pnl if realized_pnl != 0 else None

            trade = PaperTrade(
                client_order_id=client_order_id,
                strategy_id=strategy_id,
                symbol=symbol,
                exchange_id=exchange_id,
                side=side,
                order_type=order_type,
                quantity=qty_dec,
                price=price_dec,
                leverage=leverage,
                benchmark_price=Decimal(str(benchmark_price)),
                fee=fee,
                pnl=pnl_record,
                status="FILLED",
                mode=mode,
                session_id=session_id,
                created_at=now,
            )
            session.add(trade)
            await session.flush()
            trade_id = trade.id
            created_at = trade.created_at
            order_id = f"PT-{trade_id}"
            slippage = float(price_dec - Decimal(str(benchmark_price)))
            await audit_service.add_event(
                session,
                action="PAPER_ORDER_FILLED",
                user_id="system",
                resource=symbol,
                details=self._execution_audit_payload(
                    symbol=symbol,
                    side=side,
                    quantity=qty_dec,
                    price=price_dec,
                    fee=fee,
                    status="FILLED",
                    order_id=order_id,
                    order_intent_id=client_order_id,
                    benchmark_price=float(benchmark_price),
                    pnl=pnl_record,
                    new_position_qty=new_qty,
                    source=self._source_from_trade(trade, mode=mode),
                    mode=mode,
                    session_id=session_id,
                    order_type=order_type,
                    slippage=slippage,
                    filled_at=created_at or now,
                    risk_result=risk_result if mode in {"paper", "backtest", "historical_replay"} else None,
                ),
                ip_address="internal",
            )

        # Invalidate caches
        await redis_delete(REDIS_BALANCE_KEY)
        await redis_delete(REDIS_POSITIONS_KEY)

        # Trigger trade pair matching
        try:
            from app.services.trade_pair_service import trade_pair_service

            await trade_pair_service.on_trade_filled(
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                quantity=qty_dec,
                price=price_dec,
                fee=fee,
                created_at=created_at or now,
                strategy_id=strategy_id,
            )
        except Exception as e:
            logger.error(f"Trade pairing failed: {e}")

        # Update Risk Peak Balance
        try:
            new_balance_data = await self.get_balance()
            new_positions_data = await self.get_positions(session_id=session_id, exchange_id=exchange_id)
            total_value = new_balance_data.get("total_balance", 0.0) + sum(
                p["quantity"] * p["mark_price"] for p in new_positions_data
            )
            await risk_manager.update_peak_balance(total_value)
        except Exception as e:
            logger.warning(f"Failed to update peak balance: {e}")

        return {
            "order_id": f"PT-{trade_id}",
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": float(qty_dec),
            "price": float(price_dec),
            "fee": float(fee),
            "pnl": float(pnl_record) if pnl_record is not None else None,
            "status": "FILLED",
            "created_at": created_at.isoformat() if created_at else now.isoformat(),
        }

    async def cancel_order(self, order_id_str: str) -> Dict[str, Any]:
        """Cancel a PENDING order."""
        # order_id_str format: "PT-123"
        try:
            order_id = int(order_id_str.split("-")[1])
        except (IndexError, ValueError):
            raise ValueError(f"Invalid order ID format: {order_id_str}")

        async with get_db() as session:
            result = await session.execute(
                select(PaperTrade).where(PaperTrade.id == order_id)
            )
            order = result.scalar_one_or_none()

            if not order:
                raise ValueError(f"Order {order_id_str} not found")

            if order.status not in ("PENDING", "NEW", "PARTIALLY_FILLED"):
                raise ValueError(
                    f"Order {order_id_str} cannot be canceled (current status: {order.status})"
                )

            order.status = "CANCELED"
            await audit_service.add_event(
                session,
                action="PAPER_ORDER_REJECTED",
                user_id="system",
                resource=order.symbol,
                details={
                    "symbol": order.symbol,
                    "decisionId": self._decision_id_from_order_intent(order.client_order_id),
                    "sourceDecisionId": self._decision_id_from_order_intent(order.client_order_id),
                    "orderIntentId": order.client_order_id,
                    "orderId": order_id_str,
                    "order_id": order_id_str,
                    "replaySessionId": order.session_id,
                    "replay_session_id": order.session_id,
                    "executionMode": order.mode,
                    "action": order.side,
                    "intent": {
                        "id": order.client_order_id,
                        "intent_id": order.client_order_id,
                        "symbol": order.symbol,
                        "action": order.side,
                        "side": order.side,
                        "quantity": float(order.quantity),
                        "order_type": order.order_type,
                        "sourceDecisionId": self._decision_id_from_order_intent(order.client_order_id),
                        "decision_id": self._decision_id_from_order_intent(order.client_order_id),
                        "executionMode": order.mode,
                        "status": "CANCELLED",
                    },
                    "executionResult": {
                        "orderId": order_id_str,
                        "order_id": order_id_str,
                        "status": "CANCELED",
                        "source": self._source_from_trade(order, mode=order.mode),
                        "executionMode": order.mode,
                    },
                },
                ip_address="internal",
            )
            await session.commit()

        return {"message": f"Order {order_id_str} canceled", "status": "CANCELED"}

    async def _apply_fill_to_account(
        self,
        session,
        symbol: str,
        side: str,
        qty_dec: Decimal,
        price_dec: Decimal,
        fee: Decimal,
        leverage: Optional[int] = None,
        strategy_id: Optional[str] = None,
        session_id: Optional[str] = None,
        exchange_id: str = "okx",
    ):
        """Internal method to update position and balance on trade fill.

        When session_id is provided, uses the session-isolated PaperAccountReplay
        instead of the global PaperAccount(id=1).
        """
        # Choose the correct balance source based on whether this is a replay session
        if session_id:
            usdt_balance = await self._get_replay_usdt_balance(session_id, session)
        else:
            usdt_balance = await self._get_usdt_balance(session)
        position = await self._get_position(session, symbol, session_id, exchange_id)

        # Current Position State
        curr_qty = position.quantity if position else Decimal(0)
        curr_avg = position.avg_price if position else Decimal(0)
        curr_lev = int(position.leverage) if position and position.leverage else 1
        eff_lev = int(leverage) if leverage is not None else curr_lev

        # Determine Delta
        delta_qty = qty_dec if side == "BUY" else -qty_dec

        new_qty = curr_qty + delta_qty
        realized_pnl = Decimal(0)

        # Position Update Logic
        if curr_qty * new_qty >= 0:
            if abs(new_qty) > abs(curr_qty):
                # Opening / Adding
                total_val = (curr_qty * curr_avg) + (delta_qty * price_dec)
                new_avg = total_val / new_qty
                new_lev = eff_lev
            else:
                # Closing / Reducing
                new_avg = curr_avg
                new_lev = curr_lev
                realized_pnl = (price_dec - curr_avg) * (-delta_qty)
        else:
            # Flip Position
            realized_pnl = (price_dec - curr_avg) * curr_qty
            new_avg = price_dec
            new_lev = eff_lev

        # Calculate new liquidation price
        liq_price = None
        if new_qty != 0:
            liq_price_val = risk_manager.calculate_liquidation_price(
                side="BUY" if new_qty > 0 else "SELL",
                entry_price=float(new_avg),
                leverage=new_lev,
            )
            liq_price = Decimal(str(liq_price_val))

        # Update Database (Position)
        now = self._get_current_time()
        if new_qty == 0:
            if position:
                await session.delete(position)
        else:
            if position is None:
                position = PaperPosition(
                    symbol=symbol,
                    exchange_id=exchange_id,
                    session_id=session_id,
                    strategy_id=strategy_id,
                    quantity=new_qty,
                    avg_price=new_avg,
                    leverage=new_lev,
                    liquidation_price=liq_price,
                    updated_at=now,
                )
                session.add(position)
            else:
                position.quantity = new_qty
                position.avg_price = new_avg
                position.leverage = new_lev
                position.liquidation_price = liq_price
                position.updated_at = now
                position.exchange_id = exchange_id
                if strategy_id:
                    position.strategy_id = strategy_id
                if session_id:
                    position.session_id = session_id

        # Update Balance
        # Margin is handled implicitly in paper trading by checking balance in check_order
        # Here we just update the cash balance
        cash_change = -(delta_qty * price_dec) - fee
        new_balance = usdt_balance + cash_change
        if session_id:
            await self._update_replay_usdt_balance(session_id, session, new_balance)
        else:
            await self._update_usdt_balance(session, new_balance)

        return realized_pnl, new_qty, new_avg

    async def match_orders(self):
        """
        Check pending LIMIT orders (NEW/PARTIALLY_FILLED/PENDING) and execute.
        Should be called periodically by scheduler.
        """
        now = self._get_current_time()
        async with get_db() as session:
            # Support multiple active states
            stmt = select(PaperTrade).where(
                PaperTrade.status.in_(["NEW", "PARTIALLY_FILLED", "PENDING"])
            )
            result = await session.execute(stmt)
            pending_orders = result.scalars().all()

            if not pending_orders:
                return

            matched_any = False
            for order in pending_orders:
                try:
                    # Optimized: Check Redis price first via ExchangeService
                    current_price = await exchange_service.get_price(order.exchange_id or "okx", order.symbol)
                except Exception:
                    continue

                matched = False
                limit_price = float(order.price)

                if order.side == "BUY" and current_price <= limit_price:
                    matched = True
                elif order.side == "SELL" and current_price >= limit_price:
                    matched = True

                if matched:
                    # Execute Fill (Full fill for now, Partial logic requires schema update)
                    price_dec = order.price  # Execute at limit price
                    qty_dec = order.quantity
                    fee = order.fee

                    realized_pnl, new_qty, new_avg = await self._apply_fill_to_account(
                        session,
                        order.symbol,
                        order.side,
                        qty_dec,
                        price_dec,
                        fee,
                        leverage=order.leverage,
                        strategy_id=order.strategy_id,
                        exchange_id=order.exchange_id or "okx",
                    )

                    pnl_record = realized_pnl if realized_pnl != 0 else None

                    order.status = "FILLED"
                    order.pnl = pnl_record

                    await audit_service.add_event(
                        session,
                        action="PAPER_ORDER_FILLED",
                        user_id="system",
                        resource=order.symbol,
                        details=self._execution_audit_payload(
                            symbol=order.symbol,
                            side=order.side,
                            quantity=qty_dec,
                            price=price_dec,
                            fee=fee,
                            status="FILLED",
                            order_id=f"PT-{order.id}",
                            order_intent_id=order.client_order_id,
                            benchmark_price=float(order.benchmark_price) if order.benchmark_price else None,
                            pnl=pnl_record,
                            new_position_qty=new_qty,
                            source=self._source_from_trade(order, mode=order.mode),
                            mode=order.mode,
                            session_id=order.session_id,
                            order_type=order.order_type,
                            filled_at=now,
                            extra={"fillSource": "limit_price_match"},
                        ),
                    )
                    matched_any = True

                    # Trigger trade pair matching for limit order fill
                    try:
                        from app.services.trade_pair_service import trade_pair_service

                        await trade_pair_service.on_trade_filled(
                            trade_id=order.id,
                            symbol=order.symbol,
                            side=order.side,
                            quantity=qty_dec,
                            price=price_dec,
                            fee=fee,
                            created_at=order.created_at or now,
                            strategy_id=order.strategy_id,
                        )
                    except Exception as e:
                        logger.error(
                            f"Trade pairing failed for limit order {order.id}: {e}"
                        )

            if matched_any:
                await session.commit()
                # Invalidate caches
                await redis_delete(REDIS_BALANCE_KEY)
                await redis_delete(REDIS_POSITIONS_KEY)

    # ─────────────────────────────────────────────────────────────
    # Trade History
    # ─────────────────────────────────────────────────────────────
    async def get_orders(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return trade history, optionally filtered by symbol."""
        async with get_db() as session:
            stmt = (
                select(PaperTrade).order_by(PaperTrade.created_at.desc()).limit(limit)
            )
            if symbol:
                stmt = stmt.where(PaperTrade.symbol == symbol)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        orders = []
        for row in rows:
            order_id = f"PT-{row.id}"
            related_intent_id = row.client_order_id
            related_decision_id = self._decision_id_from_order_intent(related_intent_id)
            benchmark = float(row.benchmark_price) if row.benchmark_price else None
            fill_price = float(row.price)
            slippage = (
                round((fill_price - benchmark) / benchmark, 8)
                if benchmark and benchmark > 0
                else 0.0
            )
            filled_at = row.created_at.isoformat() if row.created_at and row.status == "FILLED" else None
            created_at = row.created_at.isoformat() if row.created_at else None
            source = self._source_from_trade(row, mode=row.mode)
            orders.append(
                {
                    "order_id": order_id,
                    "orderId": order_id,
                    "source": source,
                    "symbol": row.symbol,
                    "side": row.side,
                    "order_type": row.order_type,
                    "quantity": float(row.quantity),
                    "price": float(row.price),
                    "fillPrice": fill_price,
                    "fee": float(row.fee),
                    "pnl": float(row.pnl) if row.pnl is not None else None,
                    "realizedPnl": float(row.pnl) if row.pnl is not None else None,
                    "slippage": slippage,
                    "status": row.status,
                    "created_at": created_at,
                    "createdAt": created_at,
                    "filledAt": filled_at,
                    "relatedDecisionId": related_decision_id,
                    "relatedOrderIntentId": related_intent_id,
                }
            )

        return {"orders": orders, "total": len(orders)}

    # ─────────────────────────────────────────────────────────────
    # Limit Order Matching with Historical Bar Prices
    # ─────────────────────────────────────────────────────────────
    async def match_orders_with_bar_price(
        self,
        bar_prices: Dict[str, Dict[str, float]],
        session_id: Optional[str] = None,
    ):
        """
        Match pending LIMIT orders using the current replay bar's OHLC prices.

        This is the core fix for the "limit order uses real-time price" bug.
        When replaying history, limit orders should only fill if their limit price
        was reachable within the bar's [low, high] range — not at the current
        real-time market price.

        Args:
            bar_prices: {symbol: {"high": float, "low": float, "open": float, "close": float}}
            session_id: If provided, limits matching to this replay session's orders
        """
        now = self._get_current_time()
        # If no session_id (e.g. test/backtest without DB), skip order matching
        if not session_id:
            return
        async with get_db() as session:
            # Only match orders for symbols present in the current bar
            symbols = list(bar_prices.keys())
            if not symbols:
                return

            stmt = select(PaperTrade).where(
                PaperTrade.status.in_(["NEW", "PARTIALLY_FILLED", "PENDING"])
            ).where(PaperTrade.symbol.in_(symbols))

            if session_id:
                stmt = stmt.where(PaperTrade.session_id == session_id)

            result = await session.execute(stmt)
            pending_orders = result.scalars().all()

            if not pending_orders:
                return

            matched_any = False
            for order in pending_orders:
                symbol = order.symbol
                if symbol not in bar_prices:
                    continue

                price_data = bar_prices[symbol]
                bar_high = price_data["high"]
                bar_low = price_data["low"]
                limit_price = float(order.price)

                # Check if limit price is reachable within the bar's range
                # BUY order: fills if bar_low <= limit_price (price dropped to/below limit)
                # SELL order: fills if bar_high >= limit_price (price rose to/above limit)
                matched = False
                exec_price: Optional[Decimal] = None

                if order.side == "BUY" and bar_low <= limit_price:
                    matched = True
                    # Fill at limit price (best case for buyer who set a ceiling)
                    exec_price = Decimal(str(min(limit_price, bar_high)))
                elif order.side == "SELL" and bar_high >= limit_price:
                    matched = True
                    # Fill at limit price (best case for seller who set a floor)
                    exec_price = Decimal(str(max(limit_price, bar_low)))

                if matched and exec_price is not None:
                    qty_dec = order.quantity
                    fee = order.fee or (qty_dec * exec_price * FEE_RATE)

                    realized_pnl, new_qty, new_avg = await self._apply_fill_to_account(
                        session,
                        symbol=order.symbol,
                        side=order.side,
                        qty_dec=qty_dec,
                        price_dec=exec_price,
                        fee=fee,
                        leverage=order.leverage,
                        strategy_id=order.strategy_id,
                        session_id=session_id,
                    )

                    pnl_record = realized_pnl if realized_pnl != 0 else None
                    order.status = "FILLED"
                    order.pnl = pnl_record

                    await audit_service.add_event(
                        session,
                        action="PAPER_ORDER_FILLED",
                        user_id="system",
                        resource=symbol,
                        details=self._execution_audit_payload(
                            symbol=symbol,
                            side=order.side,
                            quantity=qty_dec,
                            price=exec_price,
                            fee=fee,
                            status="FILLED",
                            order_id=f"PT-{order.id}",
                            order_intent_id=order.client_order_id,
                            benchmark_price=float(order.benchmark_price) if order.benchmark_price else None,
                            pnl=pnl_record,
                            new_position_qty=new_qty,
                            source="bar_price_match",
                            mode=order.mode,
                            session_id=order.session_id,
                            order_type=order.order_type,
                            filled_at=now,
                            extra={"fillSource": "bar_price_match"},
                        ),
                    )
                    matched_any = True

                    logger.debug(
                        f"Limit order filled via bar price match: {symbol} "
                        f"{order.side} @ {float(exec_price):.2f} "
                        f"(bar [{bar_low:.2f}, {bar_high:.2f}], limit {limit_price:.2f})"
                    )

            if matched_any:
                await session.commit()
                await redis_delete(f"{REDIS_REPLAY_BALANCE_PREFIX}{session_id}" if session_id else REDIS_BALANCE_KEY)
                await redis_delete(REDIS_POSITIONS_KEY)

    # ─────────────────────────────────────────────────────────────
    # Close All Positions
    # ─────────────────────────────────────────────────────────────
    async def close_all_positions(
        self,
        current_prices: Dict[str, float],
        session_id: Optional[str] = None,
        exchange_id: str = "okx",
    ) -> List[Dict[str, Any]]:
        """Close every open position at current market price.

        Args:
            current_prices: {symbol: price} dict
            session_id: If provided, only close positions for this replay session
            exchange_id: Exchange to close positions for
        """
        positions = await self.get_positions(
            current_prices=current_prices,
            session_id=session_id,
            exchange_id=exchange_id,
        )
        results = []
        for pos in positions:
            symbol = pos["symbol"]
            qty = pos["quantity"]
            price = current_prices.get(symbol)
            if not price:
                continue

            # Determine side to close
            # If Long (qty>0) -> SELL
            # If Short (qty<0) -> BUY
            side = "SELL" if qty > 0 else "BUY"
            abs_qty = abs(qty)

            try:
                result = await self.create_order(
                    symbol=symbol,
                    side=side,
                    quantity=abs_qty,
                    price=price,
                    session_id=session_id,
                    exchange_id=exchange_id,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to close position {symbol}: {e}")
                results.append({"symbol": symbol, "error": str(e)})
        return results

    async def check_liquidations(self) -> List[Dict[str, Any]]:
        """
        后台清算检查任务：检查所有持仓是否触及清算价。
        由定时任务调用。
        """
        async with get_db() as session:
            result = await session.execute(
                select(PaperPosition).where(PaperPosition.quantity != 0)
            )
            positions = result.scalars().all()

            if not positions:
                return []

            liquidation_results = []
            for pos in positions:
                symbol = pos.symbol
                qty = float(pos.quantity)
                liq_price = (
                    float(pos.liquidation_price) if pos.liquidation_price else None
                )

                if not liq_price:
                    continue

                try:
                    current_price = await exchange_service.get_price(pos.exchange_id or "okx", symbol)
                except Exception:
                    continue

                triggered = False
                if qty > 0 and current_price <= liq_price:  # 多头清算
                    triggered = True
                elif qty < 0 and current_price >= liq_price:  # 空头清算
                    triggered = True

                if triggered:
                    logger.warning(
                        f"LIQUIDATION TRIGGERED: {symbol} at {current_price} (Liq: {liq_price})"
                    )
                    # 执行清算平仓
                    side = "SELL" if qty > 0 else "BUY"
                    try:
                        order_res = await self.create_order(
                            symbol=symbol,
                            side=side,
                            quantity=abs(qty),
                            price=current_price,
                            order_type="MARKET",
                            exchange_id=pos.exchange_id or "okx",
                        )
                        # 记录清算事件
                        await risk_manager._log_risk_event(
                            symbol,
                            "FORCE_LIQUIDATION",
                            True,
                            {
                                "price": current_price,
                                "liq_price": liq_price,
                                "qty": qty,
                            },
                        )
                        liquidation_results.append(order_res)
                    except Exception as e:
                        logger.error(f"Liquidation execution failed for {symbol}: {e}")

            return liquidation_results

    async def record_replay_equity_snapshot(
        self,
        session_id: str,
        timestamp: datetime,
        current_prices: Optional[Dict[str, float]] = None,
    ) -> bool:
        """
        Record an equity snapshot for historical replay with simulated timestamp.
        Uses the session-isolated PaperAccountReplay for cash_balance.

        Args:
            session_id: The replay session ID
            timestamp: The simulated timestamp to record
            current_prices: Dict of {symbol: price} from replay bars

        Returns:
            True if snapshot was recorded, False otherwise
        """
        try:
            async with get_db() as session:
                existing = await session.execute(
                    select(EquitySnapshot)
                    .where(EquitySnapshot.session_id == session_id)
                    .where(
                        EquitySnapshot.timestamp
                        >= timestamp.replace(minute=0, second=0, microsecond=0)
                    )
                    .where(
                        EquitySnapshot.timestamp
                        < timestamp.replace(minute=0, second=0, microsecond=0)
                        + timedelta(hours=1)
                    )
                )
                if existing.scalars().first():
                    return False

                # Read cash balance from session-isolated account (NOT PaperAccount.id=1)
                acc_result = await session.execute(
                    select(PaperAccountReplay).where(
                        PaperAccountReplay.session_id == session_id
                    )
                )
                account = acc_result.scalar_one_or_none()
                if not account:
                    logger.warning(f"Replay account not found for {session_id}")
                    return False

                cash_balance = Decimal(str(account.total_usdt))
                snapshot_initial = Decimal(str(account.initial_capital))

                pos_result = await session.execute(
                    select(PaperPosition).where(
                        PaperPosition.session_id == session_id,
                        PaperPosition.quantity != 0,
                    )
                )
                positions = pos_result.scalars().all()

                position_value = Decimal("0")
                for pos in positions:
                    qty = Decimal(str(pos.quantity))
                    avg = Decimal(str(pos.avg_price))
                    symbol = pos.symbol

                    if current_prices and symbol in current_prices:
                        price = Decimal(str(current_prices[symbol]))
                    else:
                        price = avg

                    position_value += qty * price

                total_equity = cash_balance + position_value

                prev_result = await session.execute(
                    select(EquitySnapshot)
                    .where(EquitySnapshot.session_id == session_id)
                    .order_by(EquitySnapshot.timestamp.desc())
                    .limit(1)
                )
                prev_snapshot = prev_result.scalar_one_or_none()

                if prev_snapshot:
                    prev_equity = Decimal(str(prev_snapshot.total_equity))
                    daily_pnl = total_equity - prev_equity
                    daily_return = (
                        ((daily_pnl / prev_equity) * 100)
                        if prev_equity > 0
                        else Decimal("0")
                    )
                else:
                    daily_pnl = Decimal("0")
                    daily_return = Decimal("0")

                peak_result = await session.execute(
                    select(sqlfunc.max(EquitySnapshot.total_equity)).where(
                        EquitySnapshot.session_id == session_id
                    )
                )
                peak = peak_result.scalar()
                if peak is None:
                    peak = total_equity

                peak_val = Decimal(str(peak))
                if peak_val > total_equity:
                    drawdown = ((peak_val - total_equity) / peak_val) * 100
                else:
                    drawdown = Decimal("0")

                snapshot = EquitySnapshot(
                    timestamp=timestamp,
                    session_id=session_id,
                    total_equity=total_equity,
                    cash_balance=cash_balance,
                    position_value=position_value,
                    daily_pnl=daily_pnl,
                    daily_return=daily_return,
                    drawdown=drawdown,
                    initial_capital=snapshot_initial,
                    data_source='REPLAY',
                )
                session.add(snapshot)
                await session.commit()

                logger.debug(
                    f"Replay equity snapshot recorded: session={session_id}, "
                    f"time={timestamp}, equity={float(total_equity):.2f}"
                )
                return True

        except Exception as e:
            logger.error(f"Failed to record replay equity snapshot: {e}")
            return False


# Singleton instance
paper_trading_service = PaperTradingService()
