"""
Paper Bot 本地资产隔离追踪服务

在 Hummingbot 不支持按 Bot 隔离 Portfolio 的情况下，
通过本地记录每次订单成交来独立追踪各 Bot 的资产。

Phase 3 P2-2: 资产隔离追踪
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BotPosition:
    """单个持仓"""

    def __init__(
        self,
        symbol: str,
        quantity: Decimal = Decimal("0"),
        avg_price: Decimal = Decimal("0"),
        side: str = "LONG",  # LONG / SHORT
    ):
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price
        self.side = side

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": float(self.quantity),
            "avg_price": float(self.avg_price),
            "side": self.side,
        }


class BotPortfolio:
    """单个 Bot 的资产快照"""

    def __init__(
        self,
        paper_bot_id: str,
        initial_balance: Decimal,
        quote_asset: str = "USDT",
    ):
        self.paper_bot_id = paper_bot_id
        self.initial_balance = initial_balance
        self.quote_asset = quote_asset
        self.cash_balance: Decimal = initial_balance
        self.positions: Dict[str, BotPosition] = {}  # symbol -> BotPosition
        self.trade_history: list = []
        self.created_at: datetime = datetime.utcnow()
        self.updated_at: datetime = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_bot_id": self.paper_bot_id,
            "initial_balance": float(self.initial_balance),
            "cash_balance": float(self.cash_balance),
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "trade_history_count": len(self.trade_history),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PaperBotLocalPortfolioService:
    """
    本地资产隔离追踪服务

    由于 Hummingbot API 的 /portfolio/state 接口返回的是全局 Portfolio，
    不区分单个 Bot，本服务通过本地记录每次成交事件来独立追踪各 Bot 的资产。
    """

    def __init__(self):
        # paper_bot_id -> BotPortfolio
        self._portfolios: Dict[str, BotPortfolio] = {}
        self._lock = asyncio.Lock()

    # ── 初始化 ──────────────────────────────────────────────────────────────

    async def init_portfolio(
        self,
        paper_bot_id: str,
        initial_balance: float,
        quote_asset: str = "USDT",
    ) -> BotPortfolio:
        """初始化某个 Bot 的资产记录"""
        async with self._lock:
            if paper_bot_id in self._portfolios:
                return self._portfolios[paper_bot_id]

            portfolio = BotPortfolio(
                paper_bot_id=paper_bot_id,
                initial_balance=Decimal(str(initial_balance)),
                quote_asset=quote_asset,
            )
            self._portfolios[paper_bot_id] = portfolio
            logger.info(f"[Portfolio] Initialized {paper_bot_id}: initial={initial_balance} {quote_asset}")
            return portfolio

    async def destroy_portfolio(self, paper_bot_id: str) -> None:
        """删除某个 Bot 的资产记录（Bot 停止时调用）"""
        async with self._lock:
            if paper_bot_id in self._portfolios:
                del self._portfolios[paper_bot_id]
                logger.info(f"[Portfolio] Destroyed {paper_bot_id}")

    # ── 成交记录更新 ────────────────────────────────────────────────────────

    async def record_trade(
        self,
        paper_bot_id: str,
        trade_result: Dict[str, Any],
    ) -> Optional[BotPortfolio]:
        """
        记录一笔成交，更新本地资产状态。

        trade_result 格式（Hummingbot API 返回的成交记录）：
        {
            "symbol": "BTC-USDT",
            "side": "BUY" / "SELL",
            "price": 50000.0,
            "quantity": 0.1,
            "order_value": 5000.0,   # quantity * price
            "fee": 0.5,
            "timestamp": "2026-05-15T10:00:00Z",
        }
        """
        async with self._lock:
            portfolio = self._portfolios.get(paper_bot_id)
            if not portfolio:
                logger.warning(f"[Portfolio] record_trade: unknown bot {paper_bot_id}")
                return None

            symbol = trade_result.get("symbol", "")
            side = trade_result.get("side", "").upper()
            price = Decimal(str(trade_result.get("price", 0)))
            quantity = Decimal(str(trade_result.get("quantity", 0)))
            order_value = Decimal(str(trade_result.get("order_value", 0)))
            fee = Decimal(str(trade_result.get("fee", 0)))
            timestamp = trade_result.get("timestamp", datetime.utcnow().isoformat())

            if not all([symbol, side, price > 0, quantity > 0]):
                logger.warning(f"[Portfolio] Invalid trade data: {trade_result}")
                return portfolio

            quote = portfolio.quote_asset.upper().replace("PERPETUAL", "")
            # 构建标准 symbol（去掉 - 改为 / 以匹配现货格式）
            std_symbol = symbol.replace("-", "/")

            if side == "BUY":
                # 扣除现金，增加持仓
                portfolio.cash_balance -= order_value
                base_asset = std_symbol.split("/")[0] if "/" in std_symbol else symbol

                if base_asset not in portfolio.positions:
                    portfolio.positions[base_asset] = BotPosition(
                        symbol=base_asset,
                        quantity=quantity,
                        avg_price=price,
                        side="LONG",
                    )
                else:
                    pos = portfolio.positions[base_asset]
                    total_cost = pos.avg_price * pos.quantity + price * quantity
                    pos.quantity += quantity
                    pos.avg_price = total_cost / pos.quantity if pos.quantity > 0 else Decimal("0")

            elif side == "SELL":
                # 增加现金，减少持仓
                portfolio.cash_balance += order_value
                base_asset = std_symbol.split("/")[0] if "/" in std_symbol else symbol

                if base_asset in portfolio.positions:
                    pos = portfolio.positions[base_asset]
                    pos.quantity -= quantity
                    if pos.quantity <= 0:
                        del portfolio.positions[base_asset]

            portfolio.trade_history.append({
                "symbol": symbol,
                "side": side,
                "price": float(price),
                "quantity": float(quantity),
                "order_value": float(order_value),
                "fee": float(fee),
                "timestamp": timestamp,
                "cash_balance_after": float(portfolio.cash_balance),
            })
            portfolio.updated_at = datetime.utcnow()

            logger.debug(
                f"[Portfolio] Trade recorded for {paper_bot_id}: "
                f"{side} {quantity} {symbol} @ {price} => "
                f"cash={portfolio.cash_balance}"
            )
            return portfolio

    async def record_filled_order(
        self,
        paper_bot_id: str,
        order_data: Dict[str, Any],
    ) -> Optional[BotPortfolio]:
        """
        便捷方法：从订单数据（Hummingbot 订单记录）直接提取成交信息并更新资产。

        order_data 格式：
        {
            "symbol": "BTC-USDT",
            "side": "BUY" / "SELL",
            "status": "FILLED",
            "executed_amount": 0.1,
            "executed_price": 50000.0,
            "quote_balance_after": 9500.0,
        }
        """
        quantity = float(order_data.get("executed_amount", 0))
        price = float(order_data.get("executed_price", 0))
        if quantity <= 0 or price <= 0:
            return None

        trade_result = {
            "symbol": order_data.get("symbol", ""),
            "side": order_data.get("side", ""),
            "price": price,
            "quantity": quantity,
            "order_value": quantity * price,
            "fee": 0,
            "timestamp": order_data.get("updated_at", datetime.utcnow().isoformat()),
        }
        return await self.record_trade(paper_bot_id, trade_result)

    # ── 查询 ────────────────────────────────────────────────────────────────

    async def get_portfolio(self, paper_bot_id: str) -> Optional[Dict[str, Any]]:
        """获取某个 Bot 的当前资产快照"""
        async with self._lock:
            portfolio = self._portfolios.get(paper_bot_id)
            if not portfolio:
                return None

            # 计算当前持仓价值（使用最新价格）
            position_value = Decimal("0")
            positions_detail = []
            for sym, pos in portfolio.positions.items():
                # 尝试获取最新价格（如果有价格服务）
                current_price = await self._get_current_price(sym, portfolio.quote_asset)
                pos_value = pos.quantity * current_price
                position_value += pos_value
                positions_detail.append({
                    **pos.to_dict(),
                    "current_price": float(current_price),
                    "position_value": float(pos_value),
                    "unrealized_pnl": float(pos_value - pos.avg_price * pos.quantity),
                })

            total_equity = portfolio.cash_balance + position_value
            pnl = total_equity - portfolio.initial_balance
            pnl_pct = (pnl / portfolio.initial_balance * 100) if portfolio.initial_balance > 0 else Decimal("0")

            return {
                "paper_bot_id": paper_bot_id,
                "initial_balance": float(portfolio.initial_balance),
                "cash_balance": float(portfolio.cash_balance),
                "position_value": float(position_value),
                "total_equity": float(total_equity),
                "pnl": float(pnl),
                "pnl_pct": float(pnl_pct),
                "positions": positions_detail,
                "trade_count": len(portfolio.trade_history),
                "created_at": portfolio.created_at.isoformat(),
                "updated_at": portfolio.updated_at.isoformat(),
            }

    async def get_all_portfolios(self) -> Dict[str, Dict[str, Any]]:
        """获取所有 Bot 的资产快照"""
        async with self._lock:
            result = {}
            for paper_bot_id in list(self._portfolios.keys()):
                portfolio_data = await self.get_portfolio(paper_bot_id)
                if portfolio_data:
                    result[paper_bot_id] = portfolio_data
            return result

    async def get_trade_history(
        self,
        paper_bot_id: str,
        limit: int = 50,
    ) -> list:
        """获取某个 Bot 的成交历史"""
        async with self._lock:
            portfolio = self._portfolios.get(paper_bot_id)
            if not portfolio:
                return []
            return portfolio.trade_history[-limit:]

    # ── 辅助 ────────────────────────────────────────────────────────────────

    async def _get_current_price(self, base_asset: str, quote_asset: str) -> Decimal:
        """从价格服务获取当前价格"""
        try:
            from app.services.binance_service import binance_service
            symbol = f"{base_asset}/{quote_asset}"
            price = await binance_service.get_price(symbol)
            return Decimal(str(price))
        except Exception:
            # 如果无法获取价格，返回 0（会导致持仓价值为 0）
            return Decimal("0")

    def get_tracked_bots(self) -> list:
        """获取当前追踪的所有 Bot ID"""
        return list(self._portfolios.keys())


# 全局单例
paper_bot_local_portfolio = PaperBotLocalPortfolioService()
