"""
Task Scheduler Service
Manages periodic background tasks using APScheduler.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from app.core.config import settings
from app.services.database import get_db
from app.services.binance_service import binance_service
from app.services.clickhouse_service import clickhouse_service
from app.models.db_models import AgentMemory
from sqlalchemy import select
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Standalone Task Functions (Picklable) ─────────────────────────────────────

async def health_log_task():
    logger.info("Scheduler is alive. System check passed.")

async def daily_report_task():
    """Generate daily TCA report."""
    try:
        from app.services.tca_service import tca_service
        report = await tca_service.generate_report()
        logger.info(f"Daily TCA Report: {report}")
        # In a real system, you might email this or save to a DailyReport table
    except Exception as e:
        logger.error(f"Failed to generate daily report: {e}")

async def match_orders_task():
    """Periodically match pending orders."""
    try:
        from app.services.paper_trading_service import paper_trading_service
        await paper_trading_service.match_orders()
    except Exception as e:
        logger.error(f"Error in order matching task: {e}")

async def equity_snapshot_task():
    """Record equity snapshot hourly."""
    try:
        from app.tasks.equity_tasks import record_equity_snapshot
        await record_equity_snapshot()
    except Exception as e:
        logger.error(f"Error in equity snapshot task: {e}")

async def auto_strategy_task():
    """Execute automated strategies."""
    try:
        from app.services.strategy_runner_service import strategy_runner_service
        await strategy_runner_service.run_all_strategies()
    except Exception as e:
        logger.error(f"Error in auto strategy task: {e}")

async def risk_monitor_task():
    """Run periodic risk checks."""
    try:
        from app.tasks.risk_tasks import short_squeeze_monitor_task
        await short_squeeze_monitor_task()
    except Exception as e:
        logger.error(f"Failed to run risk monitor task: {e}")

async def calculate_agent_pnl_task():
    """
    Backtrack Agent decisions and calculate PnL after N hours.
    Fills 'outcome_pnl' in AgentMemory.
    """
    logger.info("Starting Agent PnL Backtracking...")
    
    # Define PnL horizon (e.g., 24 hours after decision)
    HORIZON_HOURS = 24
    horizon_time = datetime.now(timezone.utc) - timedelta(hours=HORIZON_HOURS)
    
    try:
        async with get_db() as session:
            # Find memories older than horizon with null PnL
            stmt = (
                select(AgentMemory)
                .where(AgentMemory.outcome_pnl.is_(None))
                .where(AgentMemory.created_at <= horizon_time)
                .where(AgentMemory.entry_price.isnot(None))
                .where(AgentMemory.signal.in_(['BUY', 'SELL', 'LONG_REVERSAL', 'SHORT_REVERSAL']))
                .limit(100) # Process in batches
            )
            result = await session.execute(stmt)
            memories = result.scalars().all()
            
            if not memories:
                logger.info("No pending AgentMemory records for PnL calculation.")
                return

            logger.info(f"Processing {len(memories)} AgentMemory records for PnL...")
            
            for mem in memories:
                # Get current price (or price at horizon time ideally, but current is approx okay for now)
                # Ideally we should fetch historical kline at created_at + 24h
                # For simplicity, we use current price if it's roughly recent, 
                # but strictly we should use the price at T+24h.
                
                # Let's try to get the close price of the kline at created_at + 24h
                target_time = mem.created_at + timedelta(hours=HORIZON_HOURS)
                # Convert to timestamp ms
                ts = int(target_time.timestamp() * 1000)
                
                try:
                    # Fetch single kline at that time
                    klines = await binance_service.get_klines(
                        symbol=mem.symbol,
                        interval="1m",
                        limit=1,
                        start_time=ts,
                        end_time=ts + 60000
                    )
                    
                    if klines:
                        exit_price = klines[0].close
                        entry_price = float(mem.entry_price)
                        
                        pnl = 0.0
                        if mem.signal in ['BUY', 'LONG_REVERSAL']:
                            pnl = (exit_price - entry_price) / entry_price * 100
                        elif mem.signal in ['SELL', 'SHORT_REVERSAL']:
                            pnl = (entry_price - exit_price) / entry_price * 100
                            
                        mem.outcome_pnl = round(pnl, 2)
                        logger.info(f"Updated PnL for {mem.id} ({mem.symbol}): {pnl:.2f}%")
                        
                except Exception as e:
                    logger.warning(f"Failed to fetch price for memory {mem.id}: {e}")
                    continue
            
            await session.commit()
            
    except Exception as e:
        logger.error(f"Error in PnL backtracking: {e}")


# ── Multi-Interval Backfill Task (standalone helpers) ────────────────────────

INTERVALS_BACKFILL = {
    "1m":  {"days_back": 7,   "batch_limit": 1000, "ms_delta": 60_000},
    "5m":  {"days_back": 30,  "batch_limit": 1000, "ms_delta": 300_000},
    "15m": {"days_back": 60,  "batch_limit": 1000, "ms_delta": 900_000},
    "1h":  {"days_back": 365, "batch_limit": 1000, "ms_delta": 3_600_000},
    "4h":  {"days_back": 730, "batch_limit": 1000, "ms_delta": 14_400_000},
    "1d":  {"days_back": 1825, "batch_limit": 1000, "ms_delta": 86_400_000},
}


def symbol_to_binance(symbol: str) -> str:
    if '/' in symbol:
        return symbol
    if symbol.endswith('USDT'):
        return f"{symbol[:-4]}/USDT"
    return symbol


async def _backfill_interval_batch(
    symbol_clickhouse: str,
    interval: str,
    *,
    start_ms: int,
    end_ms: int,
) -> int:
    """Fetch and write one batch of klines. Returns number fetched."""
    symbol_binance = symbol_to_binance(symbol_clickhouse)
    config = INTERVALS_BACKFILL.get(interval, {})
    batch_limit = config.get("batch_limit", 1000)

    klines = await binance_service.get_klines(
        symbol=symbol_binance,
        timeframe=interval,
        limit=batch_limit,
        since=start_ms,
    )
    if not klines:
        return 0

    rows = [
        {
            "open_time":  k.timestamp,
            "open":       k.open,
            "high":       k.high,
            "low":        k.low,
            "close":      k.close,
            "volume":     k.volume,
            "close_time": k.close_time,
        }
        for k in klines
    ]
    await clickhouse_service.insert_klines(symbol_clickhouse, interval, rows)
    return len(klines)


async def _sync_symbol_interval(symbol: str, interval: str) -> int:
    """Incrementally sync one symbol/interval. Returns total rows written."""
    config = INTERVALS_BACKFILL.get(interval)
    if not config:
        return 0

    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)

    max_ts = await clickhouse_service.get_max_timestamp(symbol, interval)
    if max_ts is None:
        # No data — full backfill
        start_dt = now - timedelta(days=config["days_back"])
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)
    else:
        # Start slightly before max to ensure continuity
        ms_delta = config["ms_delta"]
        start_ms = int(max_ts.timestamp() * 1000) - ms_delta
        end_ms = int(now.timestamp() * 1000)

        diff_min = (now - max_ts).total_seconds() / 60
        if diff_min < 5:
            logger.debug(f"[{symbol}/{interval}] already up-to-date, skip")
            return 0

    total = 0
    current_ms = start_ms
    while current_ms < end_ms:
        fetched = await _backfill_interval_batch(
            symbol, interval, start_ms=current_ms, end_ms=end_ms
        )
        if fetched == 0:
            break
        total += fetched
        # Advance cursor
        last = None
        # Re-fetch last timestamp from the batch we just wrote
        rows = await clickhouse_service.query_klines(
            symbol, interval,
            start=datetime.fromtimestamp(current_ms / 1000, tz=timezone.utc),
            end=datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc),
            limit=1,
        )
        if rows:
            last = rows[-1]["open_time"]
        if last:
            current_ms = int(last.timestamp() * 1000) + config["ms_delta"]
        else:
            break
        await asyncio.sleep(0.3)

    return total


async def backfill_multi_interval_task():
    """
    增量同步所有币种/周期数据到最新。
    每5分钟运行一次，从各 symbol/interval 的最大时间戳开始拉取最新数据。
    """
    logger.info("Starting incremental backfill for all symbols/intervals...")

    for symbol in settings.SYMBOLS:
        for interval in INTERVALS_BACKFILL.keys():
            try:
                total = await _sync_symbol_interval(symbol, interval)
                if total > 0:
                    logger.info(f"Backfill [{symbol}/{interval}]: synced {total} bars")
                else:
                    logger.debug(f"Backfill [{symbol}/{interval}]: up-to-date")
            except Exception as e:
                logger.warning(f"Backfill [{symbol}/{interval}] failed: {e}")

    logger.info("Incremental backfill completed.")


# ── Scheduler Service ─────────────────────────────────────────────────────────

class SchedulerService:
    def __init__(self):
        # Configure JobStores
        # Parse Redis URL using urllib
        parsed = urlparse(settings.REDIS_URL)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 6379
        db = 0
        if parsed.path and parsed.path.startswith('/'):
            try:
                db = int(parsed.path[1:])
            except ValueError:
                pass
        password = parsed.password

        self.jobstores = {
            'default': RedisJobStore(
                jobs_key='apscheduler.jobs',
                run_times_key='apscheduler.run_times',
                host=host,
                port=port,
                db=db,
                password=password
            )
        }
        
        # self.executors = {
        #    'default': ThreadPoolExecutor(10)
        # }
        
        self.job_defaults = {
            'coalesce': False,
            'max_instances': 1
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=self.jobstores,
            # executors=self.executors,
            job_defaults=self.job_defaults,
            timezone="UTC"
        )

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started.")
            
            # Add default jobs here
            self.add_system_jobs()

    def stop(self):
        """Shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped.")

    def add_system_jobs(self):
        """Add system-level periodic tasks."""
        # Daily Report at 00:00 UTC
        self.scheduler.add_job(
            daily_report_task, 
            'cron', 
            hour=0, 
            minute=0, 
            id='daily_report', 
            replace_existing=True
        )
        
        # Example: Health Check Log every 5 mins
        self.scheduler.add_job(
            health_log_task,
            'interval',
            minutes=5,
            id='health_log',
            replace_existing=True
        )

        # Agent PnL Backtracking Task (Every 1 hour)
        self.scheduler.add_job(
            calculate_agent_pnl_task,
            'interval',
            hours=1,
            id='agent_pnl_backtrack',
            replace_existing=True
        )
        
        # Risk Monitor Task (Every 1 minute)
        self.scheduler.add_job(
            risk_monitor_task,
            'interval',
            minutes=1,
            id='risk_monitor',
            replace_existing=True
        )

        # Order Matching Task (Every 2 seconds)
        self.scheduler.add_job(
            match_orders_task,
            'interval',
            seconds=2,
            id='order_matching',
            replace_existing=True,
            max_instances=1
        )

        # Equity Snapshot Task (Every 1 hour)
        self.scheduler.add_job(
            equity_snapshot_task,
            'interval',
            hours=1,
            id='equity_snapshot',
            replace_existing=True,
            max_instances=1
        )

        # Auto Strategy Execution (Every 5 minutes)
        self.scheduler.add_job(
            auto_strategy_task,
            'interval',
            minutes=5,
            id='auto_strategy',
            replace_existing=True,
            max_instances=1
        )

        # Incremental Historical Data Backfill (Every 5 minutes)
        self.scheduler.add_job(
            backfill_multi_interval_task,
            'interval',
            minutes=5,
            id='multi_interval_backfill',
            replace_existing=True,
            max_instances=1
        )

        # ── Paper Bot Tasks ─────────────────────────────────────────────────────
        # Paper Bot Equity Snapshot Task (Every 30 minutes)
        self.scheduler.add_job(
            paper_bot_equity_snapshot_task,
            'interval',
            minutes=30,
            id='paper_bot_equity_snapshot',
            replace_existing=True,
            max_instances=1
        )

        # Paper Bot Status Reconciliation Task (Every 1 minute)
        self.scheduler.add_job(
            paper_bot_reconciliation_task,
            'interval',
            minutes=1,
            id='paper_bot_reconciliation',
            replace_existing=True,
            max_instances=1
        )


async def paper_bot_equity_snapshot_task():
    """
    每30分钟记录所有运行中 Paper Bot 的权益快照。
    """
    try:
        from app.services.hummingbot_paper_bot_service import get_paper_bot_records
        from app.services.paper_bot_equity_service import paper_bot_equity_service

        records = get_paper_bot_records()
        running_bots = [
            (bot_id, record)
            for bot_id, record in records.items()
            if record.get("remote_status") == "running"
        ]

        if not running_bots:
            logger.debug("No running Paper Bots for equity snapshot")
            return

        from app.services.hummingbot_paper_bot_service import (
            get_paper_bot_portfolio,
            get_paper_bot_positions,
        )

        async with get_db() as session:
            for paper_bot_id, record in running_bots:
                try:
                    portfolio = await get_paper_bot_portfolio(paper_bot_id)
                    positions = await get_paper_bot_positions(paper_bot_id)

                    portfolio_data = portfolio.get("data", {}).get("portfolio") if portfolio.get("data") else None
                    positions_data = positions.get("data", {}).get("positions", []) if positions.get("data") else []

                    await paper_bot_equity_service.record_snapshot(
                        session=session,
                        paper_bot_id=paper_bot_id,
                        portfolio_data=portfolio_data,
                        positions_data=positions_data,
                        trades_summary=None,
                    )
                except Exception as e:
                    logger.error(f"Paper Bot equity snapshot failed for {paper_bot_id}: {e}")

        logger.info(f"Paper Bot equity snapshots recorded for {len(running_bots)} bots")
    except Exception as e:
        logger.error(f"Paper Bot equity snapshot task failed: {e}")


async def paper_bot_reconciliation_task():
    """
    每分钟对账 Paper Bot 状态，更新远端检测结果。
    检测到 Bot 意外停止时记录警告。
    同时通过 WebSocket 推送状态更新。
    """
    try:
        from app.services.hummingbot_paper_bot_service import (
            get_paper_bot_records,
            _fetch_hummingbot_active_bots,
            update_paper_bot_fields,
            get_paper_bot_portfolio,
            get_paper_bot_orders,
            get_paper_bot_positions,
        )
        from app.websocket.paper_bot_ws import paper_bot_ws_manager
        from app.services.paper_bot_local_portfolio import paper_bot_local_portfolio

        records = get_paper_bot_records()
        remote_bots, _ = await _fetch_hummingbot_active_bots()

        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"

        for paper_bot_id, record in records.items():
            is_running = any(
                paper_bot_id.lower() in str(bot.get("instance_name", "")).lower()
                for bot in remote_bots
            )

            if is_running:
                update_paper_bot_fields(
                    paper_bot_id,
                    remote_status="running",
                    local_status="running",
                    matched_remote_bot=True,
                    last_remote_check_at=now,
                )

                # 并行获取所有数据，减少总等待时间
                portfolio, orders, positions, local_portfolio = await asyncio.gather(
                    get_paper_bot_portfolio(paper_bot_id),
                    get_paper_bot_orders(paper_bot_id),
                    get_paper_bot_positions(paper_bot_id),
                    paper_bot_local_portfolio.get_portfolio(paper_bot_id),
                    return_exceptions=True,
                )

                # 推送 Portfolio（Hummingbot 全局）
                if not isinstance(portfolio, Exception) and portfolio:
                    portfolio_data = portfolio.get("data", {}).get("portfolio") if portfolio.get("data") else None
                    if portfolio_data:
                        await paper_bot_ws_manager.broadcast_portfolio(paper_bot_id, portfolio_data)

                # 推送 Orders
                if not isinstance(orders, Exception) and orders:
                    orders_data = orders.get("data", {}).get("orders", []) if orders.get("data") else []
                    if orders_data:
                        await paper_bot_ws_manager.broadcast_orders(paper_bot_id, orders_data)

                # 推送 Positions
                if not isinstance(positions, Exception) and positions:
                    positions_data = positions.get("data", {}).get("positions", []) if positions.get("data") else []
                    if positions_data:
                        await paper_bot_ws_manager.broadcast_positions(paper_bot_id, positions_data)

                # 推送本地隔离资产
                if not isinstance(local_portfolio, Exception) and local_portfolio:
                    await paper_bot_ws_manager.broadcast_portfolio(paper_bot_id, {
                        "source": "local",
                        **local_portfolio,
                    })
            else:
                if record.get("remote_status") == "running":
                    update_paper_bot_fields(
                        paper_bot_id,
                        remote_status="stopped",
                        local_status="stopped",
                        matched_remote_bot=False,
                        last_error="Bot 意外停止（由定时任务检测）",
                        last_remote_check_at=now,
                    )
                    logger.warning(f"Paper Bot 停止检测: {paper_bot_id}")

                    # 推送停止状态
                    await paper_bot_ws_manager.broadcast_bot_status(paper_bot_id, {
                        "local_status": "stopped",
                        "remote_status": "stopped",
                        "event": "unexpected_stop",
                        "message": "Bot 意外停止，已被定时任务检测到",
                    })
    except Exception as e:
        logger.error(f"Paper Bot reconciliation task failed: {e}")

# Singleton
scheduler_service = SchedulerService()
