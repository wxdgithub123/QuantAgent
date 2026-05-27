"""
Pipeline DuckDB Store — Parquet-backed storage for macro indicators and news.
Extends the existing DuckDB service pattern with new tables.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_conn_lock = threading.Lock()
_conn = None


def _get_conn():
    global _conn
    if _conn is not None:
        return _conn
    with _conn_lock:
        if _conn is not None:
            return _conn
        try:
            import duckdb
            db_path = str(Path("data/pipeline/pipeline.db").resolve())
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            _conn = duckdb.connect(db_path)
            _conn.execute("PRAGMA threads=2")
            logger.info(f"Pipeline DuckDB connected: {db_path}")
            return _conn
        except ImportError:
            logger.warning("duckdb not installed")
            return None
        except Exception as e:
            logger.error(f"Pipeline DuckDB init failed: {e}")
            return None


class PipelineStore:
    """Persistent storage for macro indicators and news articles."""

    _instance: Optional["PipelineStore"] = None

    @classmethod
    def get_instance(cls) -> "PipelineStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._tables_created = False

    @property
    def available(self) -> bool:
        return _get_conn() is not None

    def _ensure_tables(self):
        if self._tables_created:
            return
        conn = _get_conn()
        if conn is None:
            return
        conn.execute("""
            CREATE TABLE IF NOT EXISTS macro_indicators (
                indicator   VARCHAR NOT NULL,
                value       DOUBLE  NOT NULL,
                source      VARCHAR NOT NULL,
                timestamp   TIMESTAMP NOT NULL,
                event_time  TIMESTAMP,
                available_time TIMESTAMP,
                as_of_time  TIMESTAMP,
                provider    VARCHAR,
                source_version VARCHAR,
                schema_version VARCHAR,
                metadata    VARCHAR,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (indicator, timestamp)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id           BIGINT PRIMARY KEY DEFAULT (ABS(CAST(XXHASH64(url) AS BIGINT))),
                title        VARCHAR NOT NULL,
                source       VARCHAR NOT NULL,
                url          VARCHAR NOT NULL,
                summary      VARCHAR,
                body         VARCHAR,
                excerpt      VARCHAR,
                language     VARCHAR,
                published_at TIMESTAMP NOT NULL,
                event_time   TIMESTAMP,
                available_time TIMESTAMP,
                as_of_time   TIMESTAMP,
                symbols      VARCHAR[],
                topics       VARCHAR[],
                event_tags   VARCHAR[],
                sentiment_score DOUBLE,
                provider     VARCHAR,
                source_version VARCHAR,
                schema_version VARCHAR,
                raw_payload_id VARCHAR,
                metadata     VARCHAR,
                ingested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._ensure_column("macro_indicators", "event_time", "TIMESTAMP")
        self._ensure_column("macro_indicators", "available_time", "TIMESTAMP")
        self._ensure_column("macro_indicators", "as_of_time", "TIMESTAMP")
        self._ensure_column("macro_indicators", "provider", "VARCHAR")
        self._ensure_column("macro_indicators", "source_version", "VARCHAR")
        self._ensure_column("macro_indicators", "schema_version", "VARCHAR")
        self._ensure_column("macro_indicators", "metadata", "VARCHAR")
        for name, typ in [
            ("body", "VARCHAR"),
            ("excerpt", "VARCHAR"),
            ("language", "VARCHAR"),
            ("event_time", "TIMESTAMP"),
            ("available_time", "TIMESTAMP"),
            ("as_of_time", "TIMESTAMP"),
            ("topics", "VARCHAR[]"),
            ("event_tags", "VARCHAR[]"),
            ("sentiment_score", "DOUBLE"),
            ("provider", "VARCHAR"),
            ("source_version", "VARCHAR"),
            ("schema_version", "VARCHAR"),
            ("raw_payload_id", "VARCHAR"),
            ("metadata", "VARCHAR"),
        ]:
            self._ensure_column("news_articles", name, typ)
        self._tables_created = True
        logger.info("Pipeline DuckDB tables ready")

    def _ensure_column(self, table_name: str, column_name: str, column_type: str) -> None:
        conn = _get_conn()
        if conn is None:
            return
        try:
            existing = conn.sql(f"DESCRIBE {table_name}").df()
            if column_name not in set(existing["column_name"]):
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        except Exception as e:
            logger.debug(f"DuckDB column check skipped for {table_name}.{column_name}: {e}")

    # ── Macro ─────────────────────────────────────────────────────────

    def upsert_macro(self, snapshots: List[Any]) -> int:
        """Insert or skip macro snapshots. Returns count written."""
        if not snapshots:
            return 0
        self._ensure_tables()
        conn = _get_conn()
        if conn is None:
            return 0

        rows = [{
            "indicator": s.indicator,
            "value": s.value,
            "source": s.source,
            "timestamp": s.timestamp,
            "event_time": getattr(s, "event_time", None) or s.timestamp,
            "available_time": getattr(s, "available_time", None) or datetime.utcnow(),
            "as_of_time": getattr(s, "as_of_time", None),
            "provider": getattr(s, "provider", None) or s.source,
            "source_version": getattr(s, "source_version", None),
            "schema_version": getattr(s, "schema_version", None) or "macro_event.v1",
            "metadata": json.dumps(getattr(s, "metadata", {}) or {}, ensure_ascii=True),
            "ingested_at": datetime.utcnow(),
        } for s in snapshots]

        df = pd.DataFrame(rows)
        written = 0
        try:
            # INSERT OR IGNORE via left-anti join
            existing = conn.sql("SELECT indicator, timestamp FROM macro_indicators").df()
            if not existing.empty:
                merged = df.merge(existing, on=["indicator", "timestamp"], how="left", indicator=True)
                new_rows = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])
            else:
                new_rows = df

            if not new_rows.empty:
                conn.sql("""
                    INSERT INTO macro_indicators (
                        indicator, value, source, timestamp, event_time, available_time,
                        as_of_time, provider, source_version, schema_version, metadata, ingested_at
                    )
                    SELECT indicator, value, source, timestamp, event_time, available_time,
                           as_of_time, provider, source_version, schema_version, metadata, ingested_at
                    FROM new_rows
                """)
                written = len(new_rows)
            return written
        except Exception as e:
            logger.error(f"Macro upsert failed: {e}")
            return 0

    def query_macro(
        self,
        indicator: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Query macro indicators, optionally filtered."""
        self._ensure_tables()
        conn = _get_conn()
        if conn is None:
            return []

        try:
            conditions = ["1=1"]
            if indicator:
                conditions.append(f"indicator = '{indicator}'")
            if start:
                conditions.append(f"timestamp >= '{start.isoformat()}'")
            if end:
                conditions.append(f"timestamp <= '{end.isoformat()}'")
            where = " AND ".join(conditions)
            result = conn.sql(f"""
                SELECT indicator, value, source, timestamp, event_time, available_time,
                       as_of_time, provider, source_version, schema_version, metadata
                FROM macro_indicators
                WHERE {where}
                ORDER BY timestamp DESC LIMIT {limit}
            """)
            return result.df().to_dict(orient="records")
        except Exception as e:
            logger.error(f"Macro query failed: {e}")
            return []

    def latest_macro(self) -> Dict[str, Any]:
        """Return the latest value for each indicator."""
        self._ensure_tables()
        conn = _get_conn()
        if conn is None:
            return {}
        try:
            result = conn.sql("""
                SELECT indicator, value, timestamp, source, available_time, provider, schema_version
                FROM macro_indicators m1
                WHERE timestamp = (SELECT MAX(timestamp) FROM macro_indicators m2 WHERE m2.indicator = m1.indicator)
                ORDER BY indicator
            """)
            df = result.df()
            out: Dict[str, Any] = {}
            for _, row in df.iterrows():
                out[row["indicator"]] = {
                    "value": float(row["value"]),
                    "date": str(row["timestamp"]),
                    "source": row["source"],
                    "available_time": str(row["available_time"]) if pd.notna(row.get("available_time")) else None,
                    "provider": row.get("provider"),
                    "schema_version": row.get("schema_version"),
                }
            return out
        except Exception as e:
            logger.error(f"Latest macro failed: {e}")
            return {}

    def macro_time_series(self, indicator: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Return time series for one indicator (for charts)."""
        return self.query_macro(indicator=indicator, limit=limit)

    # ── News ──────────────────────────────────────────────────────────

    def upsert_news(self, articles: List[Any]) -> int:
        """Insert new articles, skip duplicates by URL hash. Returns count written."""
        if not articles:
            return 0
        self._ensure_tables()
        conn = _get_conn()
        if conn is None:
            return 0

        rows = []
        for a in articles:
            rows.append({
                "title": a.title,
                "source": a.source,
                "url": a.url,
                "summary": (a.summary or "")[:2000],
                "body": (a.body or a.summary or "")[:4000],
                "excerpt": (a.excerpt or a.summary or a.title or "")[:300],
                "language": a.language or "unknown",
                "published_at": a.published_at,
                "event_time": getattr(a, "event_time", None) or a.published_at,
                "available_time": getattr(a, "available_time", None) or a.ingested_at or datetime.utcnow(),
                "as_of_time": getattr(a, "as_of_time", None),
                "symbols": a.symbols or [],
                "topics": getattr(a, "topics", []) or [],
                "event_tags": getattr(a, "event_tags", []) or [],
                "sentiment_score": getattr(a, "sentiment_score", None),
                "provider": getattr(a, "provider", None) or "openbb",
                "source_version": getattr(a, "source_version", None),
                "schema_version": getattr(a, "schema_version", None) or "news_event.v1",
                "raw_payload_id": getattr(a, "raw_payload_id", None),
                "metadata": json.dumps(getattr(a, "metadata", {}) or {}, ensure_ascii=True),
                "ingested_at": a.ingested_at or datetime.utcnow(),
            })

        df = pd.DataFrame(rows)
        written = 0
        try:
            # Deduplicate by URL
            existing_urls = conn.sql("SELECT url FROM news_articles").df()
            if not existing_urls.empty:
                new_rows = df[~df["url"].isin(existing_urls["url"])]
            else:
                new_rows = df

            if not new_rows.empty:
                conn.sql("""
                    INSERT INTO news_articles (
                        title, source, url, summary, body, excerpt, language,
                        published_at, event_time, available_time, as_of_time,
                        symbols, topics, event_tags, sentiment_score, provider,
                        source_version, schema_version, raw_payload_id, metadata, ingested_at
                    )
                    SELECT title, source, url, summary, body, excerpt, language,
                           published_at, event_time, available_time, as_of_time,
                           symbols, topics, event_tags, sentiment_score, provider,
                           source_version, schema_version, raw_payload_id, metadata, ingested_at
                    FROM new_rows
                """)
                written = len(new_rows)
            return written
        except Exception as e:
            logger.error(f"News upsert failed: {e}")
            return 0

    def query_news(
        self,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query recent news, optionally filtered by symbol."""
        self._ensure_tables()
        conn = _get_conn()
        if conn is None:
            return []

        try:
            base = """
                SELECT title, source, url, summary, body, excerpt, language,
                       published_at, event_time, available_time, as_of_time,
                       symbols, topics, event_tags, sentiment_score, provider,
                       source_version, schema_version, raw_payload_id, metadata
                FROM news_articles
            """
            if symbol:
                candidates = self._symbol_candidates(symbol)
                checks = " OR ".join(f"list_contains(symbols, '{candidate}')" for candidate in candidates)
                base += f" WHERE ({checks})"
            base += f" ORDER BY published_at DESC LIMIT {limit} OFFSET {offset}"
            result = conn.sql(base)
            return result.df().to_dict(orient="records")
        except Exception as e:
            logger.error(f"News query failed: {e}")
            return []

    def _symbol_candidates(self, symbol: str) -> List[str]:
        raw = symbol.upper().replace("/", "").replace("-", "")
        candidates = {raw}
        for suffix in ("USDT", "USD"):
            if raw.endswith(suffix) and len(raw) > len(suffix):
                candidates.add(raw[: -len(suffix)])
        return sorted(candidates)


pipeline_store = PipelineStore.get_instance()
