"""
Fetch BTCUSDT klines from Binance REST API and store in DuckDB.
One-shot script for local data seeding.
"""
import sys, os, json, urllib.request, time, asyncio
from datetime import datetime, timezone

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

INTERVALS = {
    "1m":   {"limit": 500, "binance_interval": "1m"},
    "5m":   {"limit": 500, "binance_interval": "5m"},
    "15m":  {"limit": 500, "binance_interval": "15m"},
    "1h":   {"limit": 500, "binance_interval": "1h"},
    "4h":   {"limit": 500, "binance_interval": "4h"},
    "1d":   {"limit": 500, "binance_interval": "1d"},
}

BASE_URL = "https://api.binance.com/api/v3/klines"


def fetch_klines(symbol: str, interval: str, limit: int) -> list:
    """Fetch klines from Binance REST API."""
    url = f"{BASE_URL}?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "QuantAgent/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data


def binance_to_rows(raw_klines: list, symbol: str, interval: str) -> list:
    """Convert Binance kline format to DuckDB row dicts."""
    rows = []
    for k in raw_klines:
        open_time_ms = k[0]
        close_time_ms = k[6]
        open_time = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
        close_time = datetime.fromtimestamp(close_time_ms / 1000, tz=timezone.utc)
        rows.append({
            "open_time": open_time,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": close_time,
            "event_time": close_time,
            "available_time": close_time,
            "symbol": symbol,
            "interval": interval,
            "provider": "binance",
            "source_version": "binance-rest-v3",
            "schema_version": "klines.v1",
        })
    return rows


async def main():
    from app.services.duckdb_service import DuckDBService

    storage = DuckDBService()
    await storage.async_init_tables()

    symbol = "BTCUSDT"

    for interval, config in INTERVALS.items():
        binance_interval = config["binance_interval"]
        limit = config["limit"]

        # Check existing count
        existing = await storage.count_klines(symbol, interval)
        print(f"[{symbol} {interval}] existing: {existing} klines")

        # Fetch from Binance
        print(f"  Fetching {limit} bars from Binance...")
        try:
            raw = fetch_klines(symbol, binance_interval, limit)
        except Exception as e:
            print(f"  ERROR fetching: {e}")
            continue

        if not raw:
            print(f"  No data returned")
            continue

        rows = binance_to_rows(raw, symbol, interval)
        print(f"  Got {len(rows)} bars")

        # Insert into DuckDB
        try:
            inserted = await storage.insert_klines(symbol, interval, rows)
            print(f"  Inserted: {inserted} (new: {inserted - existing})")
        except Exception as e:
            print(f"  ERROR inserting: {e}")

        # Be nice to Binance API
        time.sleep(0.5)

    # Print summary
    print("\n=== Final counts ===")
    for interval in INTERVALS:
        cnt = await storage.count_klines(symbol, interval)
        print(f"  {symbol} {interval}: {cnt} klines")


if __name__ == "__main__":
    asyncio.run(main())
