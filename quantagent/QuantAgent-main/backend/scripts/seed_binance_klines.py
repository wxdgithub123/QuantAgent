"""
Fetch BTCUSDT klines from Binance REST and store in ClickHouse (via kline ingestion).
"""
import sys, os, json, urllib.request, time, asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

BASE_URL = "https://api.binance.com/api/v3/klines"
SYMBOL = "BTCUSDT"
INTERVALS = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}


def fetch_binance(symbol: str, interval: str, limit: int = 500) -> list:
    url = f"{BASE_URL}?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "QuantAgent/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


async def main():
    from app.services.clickhouse_service import clickhouse_service
    from app.services.duckdb_service import DuckDBService

    ch_ok = await clickhouse_service.async_init_tables()
    print(f"ClickHouse init: {ch_ok}")

    duck = DuckDBService()
    duck_ok = await duck.async_init_tables()
    print(f"DuckDB init: {duck_ok}")

    for interval, bin_interval in INTERVALS.items():
        print(f"\n[{SYMBOL} {interval}] Fetching from Binance...")
        try:
            raw = fetch_binance(SYMBOL, bin_interval, limit=500)
        except Exception as e:
            print(f"  Fetch error: {e}")
            continue

        print(f"  Got {len(raw)} bars")

        # Convert to ClickHouse row format
        ch_rows = []
        duck_rows = []
        for k in raw:
            open_ms = k[0]
            close_ms = k[6]
            open_dt = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc)
            close_dt = datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc)

            # ClickHouse format
            ch_rows.append({
                "open_time": open_dt,
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": close_dt,
                "event_time": close_dt,
                "available_time": close_dt,
                "provider": "ccxt",
                "source_version": "ccxt",
                "schema_version": "bar.v1",
                "quote_volume": float(k[7]),
                "trades": int(k[8]),
            })

            # DuckDB format
            duck_rows.append({
                "open_time": open_dt,
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": close_dt,
                "event_time": close_dt,
                "available_time": close_dt,
                "provider": "binance",
                "source_version": "binance-rest-v3",
                "schema_version": "klines.v1",
            })

        # Write to ClickHouse
        try:
            n = await clickhouse_service.insert_market_bars(
                SYMBOL, interval, ch_rows,
                provider="ccxt", exchange="binance", source_version="ccxt",
            )
            print(f"  ClickHouse: wrote {n} rows")
        except Exception as e:
            print(f"  ClickHouse error: {e}")

        # Also write to DuckDB (as fallback)
        try:
            n = await duck.insert_klines(SYMBOL, interval, duck_rows)
            print(f"  DuckDB: wrote {n} rows")
        except Exception as e:
            print(f"  DuckDB error: {e}")

        time.sleep(0.5)

    # Show results
    print("\n=== Data counts ===")
    for interval in INTERVALS:
        try:
            ch_cnt = await clickhouse_service.get_bar_count(SYMBOL, interval)
        except Exception:
            ch_cnt = 0
        try:
            dk_cnt = await duck.count_klines(SYMBOL, interval)
        except Exception:
            dk_cnt = 0
        print(f"  {SYMBOL} {interval}: CH={ch_cnt}, DK={dk_cnt}")


if __name__ == "__main__":
    asyncio.run(main())
