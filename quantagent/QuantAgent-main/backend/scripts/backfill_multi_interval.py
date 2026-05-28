"""
多周期历史数据补数脚本
通过 market_data_gateway / OpenBB 获取各周期历史数据并写入 ClickHouse

支持的周期: 1m, 5m, 15m, 1h, 4h, 1d
币种: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT (来自 config.SYMBOLS)

用法:
  python backfill_multi_interval.py --check              # 查看当前数据范围
  python backfill_multi_interval.py --full               # 全量回填所有币种/周期
  python backfill_multi_interval.py --sync               # 增量同步（从最大时间戳开始）
  python backfill_multi_interval.py --full -i 1h -s BTCUSDT  # 指定周期和币种
"""
import asyncio
import logging
import sys
import os
import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.core.config import settings
from app.services.clickhouse_service import clickhouse_service
from app.services.market_data_gateway import market_data_gateway

# ── Custom formatter with timestamp ──────────────────────────────────────────
class TimestampedFormatter(logging.Formatter):
    """Each log line starts with [HH:MM:SS]"""
    def format(self, record):
        record.timestamp = time.strftime("%H:%M:%S")
        return f"[{record.timestamp}] {record.getMessage()}"


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(TimestampedFormatter())
root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)

logger = logging.getLogger("backfill")

# ── Interval configuration ────────────────────────────────────────────────────
INTERVALS: Dict[str, Dict[str, Any]] = {
    "1m":  {"days_back": 7,    "batch_limit": 1000, "ms_delta": 60_000,    "label": "1分钟"},
    "5m":  {"days_back": 30,   "batch_limit": 1000, "ms_delta": 300_000,   "label": "5分钟"},
    "15m": {"days_back": 60,   "batch_limit": 1000, "ms_delta": 900_000,   "label": "15分钟"},
    "1h":  {"days_back": 365,  "batch_limit": 1000, "ms_delta": 3_600_000, "label": "1小时"},
    "4h":  {"days_back": 730,  "batch_limit": 1000, "ms_delta": 14_400_000,"label": "4小时"},
    "1d":  {"days_back": 1825, "batch_limit": 1000, "ms_delta": 86_400_000, "label": "1天"},
}

# ── Connection health check ────────────────────────────────────────────────────

INTERVALS["1m"].update({"batch_limit": 5000, "window_days": 3})
INTERVALS["5m"].update({"window_days": 3})
INTERVALS["15m"].update({"window_days": 10})
INTERVALS["1h"].update({"days_back": 30, "window_days": 30})
INTERVALS["4h"].update({"days_back": 30, "window_days": 30})
INTERVALS["1d"].update({"window_days": 900})


async def check_connections() -> bool:
    """Check OpenBB gateway and ClickHouse connectivity before starting."""
    ok = True

    # Market gateway/OpenBB (with 20s timeout)
    try:
        price = await asyncio.wait_for(
            market_data_gateway.get_price("BTCUSDT"), timeout=20
        )
        logger.info(f"[OK] market gateway/OpenBB: BTCUSDT = {price}")
    except asyncio.TimeoutError:
        logger.warning("[WARN] market gateway/OpenBB: timeout after 20s, skipping connection check")
    except Exception as e:
        logger.warning(f"[WARN] market gateway/OpenBB: {e}, skipping connection check")

    # ClickHouse
    try:
        ping_ok = await clickhouse_service.ping()
        if ping_ok:
            ranges = await clickhouse_service.get_all_data_ranges()
            total_rows = sum(r.get("row_count", 0) for r in ranges)
            logger.info(f"[OK] ClickHouse: {len(ranges)} pairs, {total_rows} rows")
        else:
            logger.error("[FAIL] ClickHouse ping failed")
            ok = False
    except Exception as e:
        logger.error(f"[FAIL] ClickHouse: {e}")
        ok = False

    return ok


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bar_datetime(bar: Any) -> datetime:
    ts = getattr(bar, "datetime", None) or getattr(bar, "timestamp", None)
    if ts is None:
        raise ValueError("bar has no datetime/timestamp field")
    return _as_utc(ts)


def _to_rows(bars: List[Any], interval: str) -> List[Dict[str, Any]]:
    """Convert OpenBB/market-gateway BarData objects to ClickHouse rows."""
    # Interval duration in milliseconds
    ms_delta = INTERVALS.get(interval, {}).get("ms_delta", 60_000)
    rows = []
    for bar in bars:
        open_time = _bar_datetime(bar)
        close_time = (
            getattr(bar, "bar_end_time", None)
            or getattr(bar, "event_time", None)
            or (open_time + timedelta(milliseconds=ms_delta))
        )
        rows.append({
            "open_time":  open_time,
            "open":       bar.open,
            "high":       bar.high,
            "low":        bar.low,
            "close":      bar.close,
            "volume":     bar.volume,
            "close_time": _as_utc(close_time),
        })
    return rows


# ── Heartbeat ──────────────────────────────────────────────────────────────────

class Heartbeat:
    """Prints a heartbeat line every N seconds to show the script is alive."""
    def __init__(self, interval: int = 30):
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._start_time = time.time()
        self._last_heartbeat = 0

    def start(self):
        self._start_time = time.time()
        self._last_heartbeat = 0
        self._task = asyncio.create_task(self._beat())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None

    def pulse(self, msg: str):
        """Log a progress message that will appear in the next heartbeat line."""
        elapsed = int(time.time() - self._start_time)
        self._last_heartbeat = elapsed
        logger.info(f"  [心跳 {elapsed}s] {msg}")

    async def _beat(self):
        try:
            while True:
                await asyncio.sleep(self.interval)
                elapsed = int(time.time() - heartbeat._start_time)
                if elapsed - self._last_heartbeat >= self.interval:
                    logger.info(f"  [ALIVE {elapsed}s] script still running...")
        except asyncio.CancelledError:
            pass


# ── Core backfill logic ────────────────────────────────────────────────────────

async def backfill_interval(
    symbol_clickhouse: str,
    interval: str,
    *,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    days_back: Optional[int] = None,
    task_info: Dict[str, Any],
    heartbeat: Heartbeat,
) -> int:
    """
    Backfill a single symbol/interval with detailed progress feedback.

    task_info: dict with 'idx', 'total', 'symbol', 'interval' for progress display
    """
    config = INTERVALS.get(interval)
    if not config:
        logger.warning(f"  [!] Unknown interval: {interval}")
        return 0

    now = datetime.now(timezone.utc)

    if end_ms:
        end_dt = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
    else:
        end_dt = now
        end_ms = int(end_dt.timestamp() * 1000)

    if start_ms:
        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    elif days_back:
        start_dt = end_dt - timedelta(days=days_back)
        start_ms = int(start_dt.timestamp() * 1000)
    else:
        start_dt = end_dt - timedelta(days=config["days_back"])
        start_ms = int(start_dt.timestamp() * 1000)

    batch_limit = config["batch_limit"]
    ms_delta = config["ms_delta"]
    window_ms = int(config.get("window_days", 1) * 24 * 60 * 60 * 1000)

    # Estimate total batches
    total_range_ms = end_ms - start_ms
    estimated_batches = max(1, total_range_ms // window_ms + 1)

    # Progress header
    idx = task_info["idx"]
    total = task_info["total"]
    logger.info(
        f"[{idx}/{total}] "
        f"{symbol_clickhouse}/{interval} ({config['label']}) "
        f"range: {start_dt.strftime('%Y-%m-%d %H:%M')} -> {end_dt.strftime('%Y-%m-%d %H:%M')} "
        f"| est ~{estimated_batches} batches"
    )

    total_fetched = 0
    batch = 0
    current_ms = start_ms
    last_log_time = 0
    consecutive_empty = 0
    max_batches = max(3, estimated_batches * 3)

    while current_ms <= end_ms and batch < max_batches:
        batch += 1
        elapsed = int(time.time() - heartbeat._start_time)
        window_end_ms = min(current_ms + window_ms - 1, end_ms)

        try:
            klines = await asyncio.wait_for(
                market_data_gateway.get_openbb_bars(
                    symbol=symbol_clickhouse,
                    interval=interval,
                    limit=batch_limit,
                    start_time=datetime.fromtimestamp(current_ms / 1000, tz=timezone.utc),
                    end_time=datetime.fromtimestamp(window_end_ms / 1000, tz=timezone.utc),
                    persist=False,
                ),
                timeout=60,
            )

            if not klines:
                logger.info(f"  [{interval}] batch {batch}: no data, skipping window")
                current_ms = window_end_ms + ms_delta
                await asyncio.sleep(1)
                continue
            consecutive_empty = 0

            # Write to ClickHouse
            rows = _to_rows(klines, interval)
            inserted = await clickhouse_service.insert_klines(symbol_clickhouse, interval, rows)

            if inserted > 0:
                # Progress line every 5 batches or last batch
                if batch % 5 == 1 or len(klines) < batch_limit:
                    pct = min(100, batch * 100 // estimated_batches) if estimated_batches > 0 else 0
                    logger.info(
                        f"  [{interval}] batch {batch}/{estimated_batches} [{pct:3d}%] "
                        f"+{len(klines)} rows | total +{total_fetched + len(klines)} | "
                        f"cursor: {datetime.fromtimestamp(current_ms / 1000, tz=timezone.utc).strftime('%m-%d %H:%M')}"
                    )
            else:
                logger.warning(f"  [{interval}] batch {batch}: ClickHouse write failed (fetched {len(klines)})")

            total_fetched += len(klines)

            # Advance cursor
            last_ts = _bar_datetime(klines[-1]).timestamp() * 1000
            current_ms = max(int(last_ts + ms_delta), window_end_ms + ms_delta)

            # Check if we've reached end
            last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
            if last_dt >= end_dt:
                logger.info(f"  [{interval}] DONE! {total_fetched} rows, {batch} batches")
                break

        except asyncio.TimeoutError:
            logger.warning(f"  [{interval}] batch {batch}: timeout after 30s, retrying...")
            await asyncio.sleep(2)
            continue
        except Exception as e:
            logger.warning(f"  [{interval}] batch {batch} error: {e} | retrying...")
            await asyncio.sleep(2)
            continue

        # Brief pause between batches (rate limit)
        await asyncio.sleep(0.3)

    if batch >= max_batches:
        logger.warning(f"  [{interval}] reached max_batches={max_batches}, stopping to avoid endless loop")

    return total_fetched


async def sync_interval(
    symbol: str,
    interval: str,
    task_info: Dict[str, Any],
    heartbeat: Heartbeat,
) -> int:
    """Incrementally sync a symbol/interval from its max timestamp to now."""
    max_ts = await clickhouse_service.get_max_timestamp(symbol, interval)
    now = datetime.now(timezone.utc)
    config = INTERVALS.get(interval, {})

    if max_ts is None:
        logger.info(f"  [{symbol}/{interval}] no data, full backfill")
        return await backfill_interval(
            symbol, interval,
            days_back=config.get("days_back", 7),
            task_info=task_info,
            heartbeat=heartbeat,
        )

    # Normalize max_ts to UTC-aware
    if max_ts.tzinfo is None:
        max_ts = max_ts.replace(tzinfo=timezone.utc)

    ms_delta = config.get("ms_delta", 60_000)
    start_ms = int(max_ts.timestamp() * 1000) - ms_delta
    end_ms = int(now.timestamp() * 1000)

    diff_minutes = (now - max_ts).total_seconds() / 60
    if diff_minutes < 5:
        logger.info(f"  [{symbol}/{interval}] up-to-date (max={max_ts}), skip")
        return 0

    logger.info(f"  [{symbol}/{interval}] incremental: {max_ts} -> {now}")
    return await backfill_interval(
        symbol, interval,
        start_ms=start_ms,
        end_ms=end_ms,
        task_info=task_info,
        heartbeat=heartbeat,
    )


# ── Check data ranges ─────────────────────────────────────────────────────────

async def check_current_data():
    logger.info("=== 当前 ClickHouse 数据范围 ===")
    ranges = await clickhouse_service.get_all_data_ranges()
    if not ranges:
        logger.info("  (无数据)")
        return
    now = datetime.now(timezone.utc)
    stale_threshold = timedelta(hours=1)
    for r in ranges:
        max_t = r.get("max_time")
        stale = ""
        if max_t is not None:
            # Handle both naive and aware datetimes from ClickHouse
            if isinstance(max_t, datetime):
                if max_t.tzinfo is None:
                    max_t = max_t.replace(tzinfo=timezone.utc)
                diff = now - max_t
                if diff > stale_threshold:
                    stale = " [STALE]"
        logger.info(
            f"  {r['symbol']}/{r['interval']}: "
            f"min={r['min_time']}  max={r['max_time']}  count={r['row_count']}{stale}"
        )


# ── CLI entry ─────────────────────────────────────────────────────────────────

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="多周期历史数据补数")
    parser.add_argument("--full", "-f", action="store_true",
                        help="全量回填 (按 INTERVALS.days_back)")
    parser.add_argument("--sync", "-y", action="store_true",
                        help="增量同步 (从最大时间戳开始)")
    parser.add_argument("--check", "-c", action="store_true",
                        help="仅检查当前数据范围")
    parser.add_argument("--interval", "-i", type=str, default=None,
                        help=f"指定周期: {list(INTERVALS.keys())}")
    parser.add_argument("--symbol", "-s", type=str, default=None,
                        help=f"指定币种 (如 BTCUSDT)，默认全部: {settings.SYMBOLS}")
    args = parser.parse_args()

    overall_start = time.time()

    # Initialize ClickHouse tables
    logger.info("初始化 ClickHouse...")
    clickhouse_service.init_tables()

    if args.check:
        await check_current_data()
        return

    # ── Connection health check ─────────────────────────────────────────────────
    logger.info("检测连接状态...")
    if not await check_connections():
        logger.error("连接检查失败，请确认 market gateway / OpenBB 和 ClickHouse 可用后重试")
        return
    logger.info("连接状态正常，开始补数")

    # Determine symbols and intervals
    symbols = [args.symbol] if args.symbol else list(settings.SYMBOLS)
    intervals = [args.interval] if args.interval else list(INTERVALS.keys())

    symbols = [s for s in symbols if s in settings.SYMBOLS]
    intervals = [i for i in intervals if i in INTERVALS]

    if not symbols:
        logger.error(f"无可用币种: {args.symbol}")
        return
    if not intervals:
        logger.error(f"无可用周期: {args.interval}")
        return

    mode = "全量" if args.full else "增量"
    total_tasks = len(symbols) * len(intervals)

    logger.info(f"=" * 60)
    logger.info(f"  补数任务: {mode} | 币种: {symbols} | 周期: {intervals}")
    logger.info(f"  总任务数: {total_tasks} 个 (每个 symbol/interval 组合)")
    logger.info(f"  预计最大批次: ~{total_tasks * 400} 批 (每个周期约400批@1h)")
    logger.info(f"=" * 60)

    # Start heartbeat
    heartbeat = Heartbeat(interval=30)
    heartbeat.start()

    grand_total = 0
    task_idx = 0

    try:
        for symbol in symbols:
            for interval in intervals:
                task_idx += 1
                config = INTERVALS[interval]

                task_info = {
                    "idx": task_idx,
                    "total": total_tasks,
                    "symbol": symbol,
                    "interval": interval,
                }

                heartbeat.pulse(f"开始 [{task_idx}/{total_tasks}] {symbol}/{interval}")

                try:
                    if args.full:
                        total = await backfill_interval(
                            symbol, interval,
                            days_back=config["days_back"],
                            task_info=task_info,
                            heartbeat=heartbeat,
                        )
                    else:
                        total = await sync_interval(
                            symbol, interval,
                            task_info=task_info,
                            heartbeat=heartbeat,
                        )
                    grand_total += total
                except Exception as e:
                    logger.info(f"  [!] [{symbol}/{interval}] task error: {e}")
                    traceback.print_exc()

                await asyncio.sleep(0.5)

    finally:
        heartbeat.stop()

    elapsed = int(time.time() - overall_start)
    elapsed_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"

    logger.info(f"=" * 60)
    logger.info(f"  [DONE] Completed!")
    logger.info(f"  Time: {elapsed_str}")
    logger.info(f"  Total rows written: {grand_total}")
    logger.info(f"=" * 60)

    await check_current_data()


if __name__ == "__main__":
    asyncio.run(main())
