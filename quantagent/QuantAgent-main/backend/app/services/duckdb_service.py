"""
DuckDB Service — Lightweight OLAP storage using Parquet files (L4)

Provides the same interface as ClickHouseService so the storage backend
can be switched via the ``STORAGE_BACKEND`` environment variable.

Data is stored as Parquet files partitioned by symbol/interval/date:
    data/market/{symbol}/{interval}/YYYY/MM/DD.parquet

DuckDB scans these files directly via ``read_parquet()`` — no ETL ingestion step.

Dependency: duckdb, pyarrow (pip install duckdb pyarrow)
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Client singleton ────────────────────────────────────────────────────────────

_duckdb_conn = None
_duckdb_lock = threading.Lock()


def _get_conn():
    """Lazily create or return the DuckDB in-memory connection."""
    global _duckdb_conn
    if _duckdb_conn is not None:
        return _duckdb_conn
    with _duckdb_lock:
        if _duckdb_conn is not None:
            return _duckdb_conn
        try:
            import duckdb

            _duckdb_conn = duckdb.connect(":memory:")
            logger.info("DuckDB in-memory connection created")
            return _duckdb_conn
        except ImportError:
            logger.warning("duckdb not installed. Run: pip install duckdb pyarrow")
            return None
        except Exception as e:
            logger.error(f"DuckDB connection failed: {e}")
            return None


def _data_dir() -> Path:
    """Resolve the Parquet data directory."""
    return Path(settings.DUCKDB_DATA_DIR or "data/market")


def _parquet_glob(symbol: str, interval: str) -> str:
    """Return a DuckDB-compatible glob pattern for Parquet files."""
    base = _data_dir()
    return str(base / symbol / interval / "*" / "*" / "*.parquet").replace("\\", "/")


def _parquet_path(symbol: str, interval: str, dt: datetime) -> Path:
    """Build the Parquet file path for a given timestamp."""
    return (
        _data_dir()
        / symbol
        / interval
        / f"{dt.year:04d}"
        / f"{dt.month:02d}"
        / f"{dt.day:02d}.parquet"
    )


# ── Service class ───────────────────────────────────────────────────────────────


class DuckDBService:
    """DuckDB-based time-series storage.

    Uses Parquet files for persistence and DuckDB for queries.
    Same interface as ClickHouseService for transparent backend switching.
    """

    _instance: Optional["DuckDBService"] = None

    @classmethod
    def get_instance(cls) -> "DuckDBService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._initialized = False

    @property
    def available(self) -> bool:
        return _get_conn() is not None

    # ── Initialization ──────────────────────────────────────────────────────

    def init_tables(self) -> bool:
        """Verify DuckDB can read/write to the Parquet data directory."""
        if not self.available:
            return False
        try:
            _data_dir().mkdir(parents=True, exist_ok=True)
            logger.info(f"DuckDB Parquet data dir: {_data_dir()}")
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"DuckDB init failed: {e}")
            return False

    async def async_init_tables(self) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.init_tables)

    # ── Insert ──────────────────────────────────────────────────────────────

    def insert_klines_sync(
        self,
        symbol: str,
        interval: str,
        rows: List[Dict[str, Any]],
    ) -> int:
        """Sync insert: write klines to Parquet files partitioned by day.

        Returns the number of rows written.
        """
        if not rows:
            return 0

        conn = _get_conn()
        if conn is None:
            return 0

        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            # Group rows by date and write each day's file
            by_date: Dict[str, List[Dict[str, Any]]] = {}
            for r in rows:
                ot = r.get("open_time")
                if isinstance(ot, str):
                    ot = datetime.fromisoformat(ot.replace("Z", "+00:00"))
                elif isinstance(ot, pd.Timestamp):
                    ot = ot.to_pydatetime()
                day_key = ot.strftime("%Y-%m-%d") if ot else "unknown"
                by_date.setdefault(day_key, []).append(r)

            written = 0
            for day_str, day_rows in by_date.items():
                dt = datetime.strptime(day_str, "%Y-%m-%d") if day_str != "unknown" else datetime.utcnow()
                file_path = _parquet_path(symbol, interval, dt)
                file_path.parent.mkdir(parents=True, exist_ok=True)

                df = pd.DataFrame(day_rows)
                table = pa.Table.from_pandas(df)
                pq.write_table(table, str(file_path))
                written += len(day_rows)

            logger.debug(f"DuckDB: wrote {written} rows for {symbol}/{interval}")
            return written

        except Exception as e:
            logger.error(f"DuckDB insert failed for {symbol}/{interval}: {e}")
            return 0

    async def insert_klines(
        self,
        symbol: str,
        interval: str,
        rows: List[Dict[str, Any]],
    ) -> int:
        """Async wrapper for kline insertion."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.insert_klines_sync, symbol, interval, rows
        )

    # ── Query ───────────────────────────────────────────────────────────────

    def query_klines_sync(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query klines by scanning Parquet files."""
        conn = _get_conn()
        if conn is None:
            return []

        glob_pat = _parquet_glob(symbol, interval)
        try:
            # Build SQL
            sql = f"""
                SELECT *
                FROM read_parquet('{glob_pat}', hive_partitioning=false)
                WHERE 1=1
            """
            if start:
                sql += f" AND open_time >= '{start.isoformat()}'"
            if end:
                sql += f" AND open_time <= '{end.isoformat()}'"
            sql += " ORDER BY open_time ASC"
            if limit:
                sql += f" LIMIT {limit}"
            if offset:
                sql += f" OFFSET {offset}"

            result = conn.sql(sql)
            df = result.df()
            if df.empty:
                return []
            return df.to_dict(orient="records")
        except Exception as e:
            logger.debug(f"DuckDB query failed for {symbol}/{interval}: {e}")
            return []

    async def query_klines(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Async wrapper for kline query."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.query_klines_sync,
            symbol, interval, start, end, limit, offset,
        )

    # ── DataFrame interface ─────────────────────────────────────────────────

    def get_klines_dataframe_sync(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100000,
    ) -> Optional[pd.DataFrame]:
        """Return a DataFrame with open_time as the index (for backtesting)."""
        rows = self.query_klines_sync(symbol, interval, start, end, limit)
        if not rows:
            return None

        df = pd.DataFrame(rows)
        if "open_time" in df.columns:
            df["open_time"] = pd.to_datetime(df["open_time"])
            df = df.set_index("open_time").sort_index()
        return df

    async def get_klines_dataframe(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100000,
    ) -> Optional[pd.DataFrame]:
        """Async wrapper for DataFrame getter."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.get_klines_dataframe_sync,
            symbol, interval, start, end, limit,
        )

    # ── Metadata ────────────────────────────────────────────────────────────

    def get_max_timestamp_sync(
        self, symbol: str, interval: str
    ) -> Optional[datetime]:
        """Get the latest open_time for a symbol/interval pair."""
        rows = self.query_klines_sync(
            symbol, interval, limit=1, offset=0
        )
        # Need to get the LAST row, so query without limit and sort DESC
        conn = _get_conn()
        if conn is None:
            return None

        glob_pat = _parquet_glob(symbol, interval)
        try:
            sql = f"""
                SELECT max(open_time) AS max_time
                FROM read_parquet('{glob_pat}', hive_partitioning=false)
            """
            result = conn.sql(sql).fetchone()
            if result and result[0] is not None:
                val = result[0]
                if isinstance(val, str):
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                if isinstance(val, pd.Timestamp):
                    return val.to_pydatetime()
                return val
        except Exception:
            pass
        return None

    async def get_max_timestamp(
        self, symbol: str, interval: str
    ) -> Optional[datetime]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.get_max_timestamp_sync, symbol, interval
        )

    def count_klines_sync(self, symbol: str, interval: str) -> int:
        """Total number of stored klines for a symbol/interval."""
        conn = _get_conn()
        if conn is None:
            return 0

        glob_pat = _parquet_glob(symbol, interval)
        try:
            result = conn.sql(
                f"SELECT count(*) FROM read_parquet('{glob_pat}', hive_partitioning=false)"
            ).fetchone()
            return int(result[0]) if result else 0
        except Exception:
            return 0

    async def count_klines(self, symbol: str, interval: str) -> int:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.count_klines_sync, symbol, interval
        )

    def ping(self) -> bool:
        return self.available


# ── Module-level singleton ─────────────────────────────────────────────────────

duckdb_service = DuckDBService.get_instance()
