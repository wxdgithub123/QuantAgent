"""
Paper Bot Equity Service

权益追踪与分析服务：
1. 记录 Paper Bot 权益快照
2. 获取权益曲线数据
3. 计算统计指标
4. 定时快照记录
"""

import logging
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    PaperBotEquitySnapshot,
    PaperBotTradeRecord,
    PaperBotPositionSnapshot,
)

logger = logging.getLogger(__name__)


class PaperBotEquityService:
    """Paper Bot 权益追踪与分析服务"""

    def __init__(self):
        # 峰值权益缓存：paper_bot_id -> peak_equity
        self._peak_equity_cache: Dict[str, Decimal] = {}

    async def record_snapshot(
        self,
        session: AsyncSession,
        paper_bot_id: str,
        portfolio_data: Optional[Dict[str, Any]] = None,
        positions_data: Optional[List[Dict[str, Any]]] = None,
        trades_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[PaperBotEquitySnapshot]:
        """
        记录权益快照。

        Args:
            session: 数据库会话
            paper_bot_id: Paper Bot ID
            portfolio_data: Portfolio 数据（从 Hummingbot API 获取）
            positions_data: 持仓数据
            trades_summary: 交易汇总数据

        Returns:
            创建的快照对象，如果没有数据则返回 None
        """
        try:
            # 1. 解析 Portfolio 数据
            balances = []
            if portfolio_data:
                if isinstance(portfolio_data, dict):
                    balances = portfolio_data.get("balances", [])
                    total_usd = portfolio_data.get("total_usd_value", 0)
                else:
                    total_usd = 0
            else:
                total_usd = 0

            total_equity = Decimal(str(total_usd)) if total_usd else Decimal("0")

            # 计算现金余额
            cash_balance = Decimal("0")
            for bal in balances:
                asset = str(bal.get("asset", "")).upper()
                if asset in ("USDT", "USD", "BUSD", "USDC"):
                    available = Decimal(str(bal.get("available", 0)))
                    locked = Decimal(str(bal.get("locked", 0)))
                    cash_balance += available + locked

            if total_equity == 0:
                total_equity = cash_balance

            # 2. 计算持仓价值
            position_value = Decimal("0")
            positions_detail: List[Dict[str, Any]] = []
            for pos in (positions_data or []):
                qty = Decimal(str(pos.get("amount", 0) or pos.get("quantity", 0)))
                price = Decimal(str(pos.get("current_price", 0)))
                value = qty * price
                position_value += value
                positions_detail.append({
                    "symbol": pos.get("symbol", "UNKNOWN"),
                    "side": pos.get("side", "UNKNOWN"),
                    "quantity": float(qty),
                    "avg_price": float(pos.get("avg_price", 0)),
                    "current_price": float(price),
                    "value": float(value),
                    "unrealized_pnl": float(pos.get("unrealized_pnl", 0)),
                })

            # 3. 获取初始资金
            initial_capital = await self._get_initial_capital(session, paper_bot_id)

            # 4. 计算 P&L
            pnl = total_equity - initial_capital
            pnl_pct = (pnl / initial_capital * 100) if initial_capital > 0 else Decimal("0")

            # 5. 更新峰值权益和回撤
            if paper_bot_id not in self._peak_equity_cache:
                self._peak_equity_cache[paper_bot_id] = initial_capital

            peak = self._peak_equity_cache[paper_bot_id]
            if total_equity > peak:
                self._peak_equity_cache[paper_bot_id] = total_equity
                peak = total_equity

            drawdown = ((peak - total_equity) / peak * 100) if peak > 0 else Decimal("0")

            # 6. 获取交易统计
            total_trades = (trades_summary or {}).get("total_trades", 0)
            winning_trades = (trades_summary or {}).get("winning_trades", 0)
            losing_trades = (trades_summary or {}).get("losing_trades", 0)
            total_fees = Decimal(str((trades_summary or {}).get("total_fees", 0)))

            # 7. 计算日收益率
            prev_snapshot = await self._get_latest_snapshot(session, paper_bot_id)
            if prev_snapshot:
                prev_equity = Decimal(str(prev_snapshot.total_equity))
                if prev_equity > 0:
                    daily_return = ((total_equity - prev_equity) / prev_equity * 100)
                else:
                    daily_return = pnl_pct
            else:
                daily_return = pnl_pct

            # 8. 创建快照
            now = datetime.utcnow()
            snapshot_id = f"EQ-{paper_bot_id}-{int(time.time())}"

            snapshot = PaperBotEquitySnapshot(
                id=snapshot_id,
                paper_bot_id=paper_bot_id,
                timestamp=now,
                total_equity=total_equity,
                cash_balance=cash_balance,
                position_value=position_value,
                positions_detail=positions_detail if positions_detail else None,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                total_fees=total_fees,
                initial_capital=initial_capital,
                pnl=pnl,
                pnl_pct=pnl_pct,
                drawdown=drawdown,
                peak_equity=peak,
                daily_return=daily_return,
            )

            session.add(snapshot)
            await session.commit()
            await session.refresh(snapshot)

            logger.info(f"权益快照记录成功: {paper_bot_id}, equity={total_equity}")
            return snapshot

        except Exception as e:
            logger.error(f"记录权益快照失败: {paper_bot_id}, {e}")
            await session.rollback()
            return None

    async def get_equity_curve(
        self,
        session: AsyncSession,
        paper_bot_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        interval: str = "1h",
    ) -> Dict[str, Any]:
        """
        获取权益曲线数据。

        Args:
            session: 数据库会话
            paper_bot_id: Paper Bot ID
            start_time: 开始时间（可选）
            end_time: 结束时间（可选）
            interval: 聚合间隔 (1h, 4h, 1d)

        Returns:
            权益曲线数据
        """
        if end_time is None:
            end_time = datetime.utcnow()
        if start_time is None:
            start_time = end_time - timedelta(days=30)

        # 查询快照数据
        stmt = select(PaperBotEquitySnapshot).where(
            and_(
                PaperBotEquitySnapshot.paper_bot_id == paper_bot_id,
                PaperBotEquitySnapshot.timestamp >= start_time,
                PaperBotEquitySnapshot.timestamp <= end_time,
            )
        ).order_by(PaperBotEquitySnapshot.timestamp)

        result = await session.execute(stmt)
        snapshots = list(result.scalars().all())

        # 按间隔聚合
        aggregated_data = self._aggregate_by_interval(snapshots, interval)

        # 计算统计数据
        statistics = self._calculate_statistics(snapshots)

        return {
            "paper_bot_id": paper_bot_id,
            "interval": interval,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "data": aggregated_data,
            "statistics": statistics,
        }

    def _aggregate_by_interval(
        self,
        snapshots: List[PaperBotEquitySnapshot],
        interval: str,
    ) -> List[Dict[str, Any]]:
        """按间隔聚合数据"""
        if not snapshots:
            return []

        interval_delta_map = {
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }
        interval_delta = interval_delta_map.get(interval, timedelta(hours=1))

        # 分组
        groups: Dict[str, List[PaperBotEquitySnapshot]] = {}
        for snapshot in snapshots:
            key = self._get_interval_key(snapshot.timestamp, interval)
            if key not in groups:
                groups[key] = []
            groups[key].append(snapshot)

        # 聚合每个组（取最后一个快照的值）
        aggregated = []
        for key, group_snapshots in sorted(groups.items()):
            last = group_snapshots[-1]
            total_trades = last.total_trades or 0
            aggregated.append({
                "timestamp": key,
                "total_equity": float(last.total_equity),
                "cash_balance": float(last.cash_balance),
                "position_value": float(last.position_value),
                "pnl": float(last.pnl) if last.pnl else 0.0,
                "pnl_pct": float(last.pnl_pct) if last.pnl_pct else 0.0,
                "drawdown": float(last.drawdown) if last.drawdown else 0.0,
                "total_trades": total_trades,
                "win_rate": (
                    float(last.winning_trades / total_trades * 100)
                    if total_trades > 0 else 0.0
                ),
            })

        return aggregated

    def _get_interval_key(self, timestamp: datetime, interval: str) -> str:
        """获取间隔分组键"""
        if interval == "1h":
            return timestamp.strftime("%Y-%m-%d %H:00:00")
        elif interval == "4h":
            hour = (timestamp.hour // 4) * 4
            return timestamp.replace(hour=hour, minute=0, second=0).strftime("%Y-%m-%d %H:00:00")
        elif interval == "1d":
            return timestamp.strftime("%Y-%m-%d 00:00:00")
        return timestamp.isoformat()

    def _calculate_statistics(
        self,
        snapshots: List[PaperBotEquitySnapshot],
    ) -> Dict[str, Any]:
        """计算统计指标"""
        if not snapshots:
            return {}

        first = snapshots[0]
        last = snapshots[-1]

        initial_capital = float(first.initial_capital or 0)
        current_equity = float(last.total_equity or 0)

        # 总收益率
        total_return_pct = ((current_equity - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0.0

        # 最大回撤
        max_drawdown = max(float(s.drawdown or 0) for s in snapshots)

        # 收益率序列
        returns: List[float] = []
        for i in range(1, len(snapshots)):
            prev_equity = float(snapshots[i - 1].total_equity or 0)
            curr_equity = float(snapshots[i].total_equity or 0)
            if prev_equity > 0:
                daily_ret = (curr_equity - prev_equity) / prev_equity
                returns.append(daily_ret)

        # 夏普比率
        sharpe_ratio = 0.0
        if returns:
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_return = variance ** 0.5
            if std_return > 0:
                # 年化收益 / 年化波动率（假设252交易日）
                annualized_return = avg_return * 252
                annualized_vol = std_return * (252 ** 0.5)
                risk_free_rate = 0.02  # 2% 年化无风险利率
                sharpe_ratio = (annualized_return - risk_free_rate) / annualized_vol

        # 胜率
        total_trades = last.total_trades or 0
        winning_trades = last.winning_trades or 0
        win_rate_pct = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # 盈亏比
        total_fees = float(last.total_fees or 0)

        return {
            "initial_capital": initial_capital,
            "current_equity": current_equity,
            "total_return_pct": round(total_return_pct, 4),
            "max_drawdown_pct": round(max_drawdown, 4),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "win_rate_pct": round(win_rate_pct, 2),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": last.losing_trades or 0,
            "total_fees": total_fees,
        }

    async def _get_initial_capital(
        self,
        session: AsyncSession,
        paper_bot_id: str,
    ) -> Decimal:
        """获取 Bot 初始资金"""
        # 从第一个快照获取
        stmt = (
            select(PaperBotEquitySnapshot.initial_capital)
            .where(PaperBotEquitySnapshot.paper_bot_id == paper_bot_id)
            .order_by(PaperBotEquitySnapshot.timestamp)
            .limit(1)
        )
        result = await session.execute(stmt)
        capital = result.scalar_one_or_none()

        if capital:
            return Decimal(str(capital))

        # 尝试从 Bot 配置获取
        from app.services.hummingbot_paper_bot_service import get_paper_bot_record
        record = get_paper_bot_record(paper_bot_id)
        if record:
            config = record.get("config", {})
            strategy_params = config.get("strategy_params", {})
            return Decimal(str(strategy_params.get("paper_initial_balance", 10000)))

        return Decimal("10000")

    async def _get_latest_snapshot(
        self,
        session: AsyncSession,
        paper_bot_id: str,
    ) -> Optional[PaperBotEquitySnapshot]:
        """获取最新的快照"""
        stmt = (
            select(PaperBotEquitySnapshot)
            .where(PaperBotEquitySnapshot.paper_bot_id == paper_bot_id)
            .order_by(PaperBotEquitySnapshot.timestamp.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


# 全局单例
paper_bot_equity_service = PaperBotEquityService()
