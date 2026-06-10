"""Build point-in-time AnalysisContext from standardized storage."""

from __future__ import annotations

import hashlib
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from app.models.analysis_context import AnalysisContext
from app.models.instrument import Instrument
from app.services.database import get_db
from app.services.market_data_gateway import market_data_gateway

logger = logging.getLogger(__name__)


class AnalysisContextBuilder:
    """Assemble Agent input while enforcing available_time <= as_of_time."""

    _instance: Optional["AnalysisContextBuilder"] = None
    _SQL_UNAVAILABLE_RETRY_SECONDS = 30.0
    _SQL_QUERY_TIMEOUT_SECONDS = 0.75

    def __init__(self) -> None:
        self._sql_unavailable_until = 0.0

    @classmethod
    def get_instance(cls) -> "AnalysisContextBuilder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def build(
        self,
        symbol: str,
        interval: str = "1h",
        as_of_time: Optional[datetime] = None,
        bar_limit: int = 120,
        factor_limit: int = 60,
        signal_limit: int = 40,
        news_limit: int = 20,
        macro_limit: int = 30,
    ) -> AnalysisContext:
        instrument = Instrument.from_raw(symbol)
        cutoff = self._normalize_cutoff(as_of_time)
        bars = await self._load_bars(instrument.symbol, interval, cutoff, bar_limit)
        factors, factor_ids, factor_versions = (
            ({}, [], {})
            if factor_limit <= 0
            else await self._load_factors(instrument.symbol, interval, cutoff, factor_limit)
        )
        signals, signal_ids, signal_versions = (
            ([], [], {})
            if signal_limit <= 0
            else await self._load_signals(instrument.symbol, interval, cutoff, signal_limit)
        )
        news = [] if news_limit <= 0 else self._load_news(instrument, cutoff, news_limit)
        macro = [] if macro_limit <= 0 else self._load_macro(cutoff, macro_limit)

        bar_meta = self._build_bar_meta(bars, interval)
        data_versions = {
            "bars": self._version_set(bars),
            "factors": factor_versions,
            "signals": signal_versions,
            "news": self._version_set(news),
            "macro": self._version_set(macro),
        }
        input_snapshot_ids = {
            "factor_snapshot_ids": factor_ids,
            "signal_event_ids": signal_ids,
            "news_payload_ids": [row.get("raw_payload_id") for row in news if row.get("raw_payload_id")],
            "macro_keys": [f"{row.get('indicator')}:{row.get('timestamp')}" for row in macro],
            # ── K-line metadata (bars don't have IDs, record as single-element list for Pydantic) ──
            "bar_meta": [bar_meta],
        }
        context_hash = self._context_hash(
            symbol=instrument.symbol,
            interval=interval,
            as_of_time=cutoff,
            input_snapshot_ids=input_snapshot_ids,
            data_versions=data_versions,
        )

        return AnalysisContext(
            instrument_id=instrument.symbol,
            symbol=instrument.symbol,
            timeframe=interval,
            as_of_time=cutoff,
            bars=bars,
            latest_factors=factors,
            recent_signals=signals,
            macro_events=macro,
            news_events=news,
            data_versions=data_versions,
            input_snapshot_ids=input_snapshot_ids,
            context_hash=context_hash,
            metadata={
                "point_in_time_rule": "available_time <= as_of_time",
                "builder_version": "analysis_context_builder.v1",
                "context_hash": context_hash,
            },
        )

    async def _load_bars(
        self,
        symbol: str,
        interval: str,
        cutoff: datetime,
        limit: int,
    ) -> List[Dict[str, Any]]:
        try:
            klines = await market_data_gateway.get_klines(
                symbol,
                interval=interval,
                limit=limit,
                end_time=cutoff,
                allow_external_fallback=False,
                allow_ccxt_fallback=False,
                allow_binance_fallback=False,
            )
            out: List[Dict[str, Any]] = []
            for kline in klines or []:
                event_time = kline.timestamp
                available_time = kline.close_time or event_time
                if not self._visible(available_time, cutoff):
                    continue
                out.append({
                    "symbol": symbol,
                    "instrument_id": symbol,
                    "timeframe": interval,
                    "event_time": self._iso(event_time),
                    "available_time": self._iso(available_time),
                    "open": float(kline.open),
                    "high": float(kline.high),
                    "low": float(kline.low),
                    "close": float(kline.close),
                    "volume": float(kline.volume),
                    "provider": "market_data_gateway:local_storage",
                    "schema_version": "bar.v1",
                })
            return out[-limit:]
        except Exception as e:
            logger.debug(f"AnalysisContext bar load skipped for {symbol}/{interval}: {e}")
            return []

    def _build_bar_meta(self, bars: List[Dict[str, Any]], interval: str) -> Dict[str, Any]:
        providers = sorted({str(b.get("provider") or "unknown") for b in bars})
        digest_rows = [
            {
                "t": bar.get("event_time"),
                "o": bar.get("open"),
                "h": bar.get("high"),
                "l": bar.get("low"),
                "c": bar.get("close"),
                "v": bar.get("volume"),
            }
            for bar in bars
        ]
        digest = hashlib.sha256(
            json.dumps(digest_rows, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        first = bars[0] if bars else {}
        last = bars[-1] if bars else {}
        return {
            "count": len(bars),
            "bars_count": len(bars),
            "interval": interval,
            "first_event_time": first.get("event_time"),
            "last_event_time": last.get("event_time"),
            "last_available_time": last.get("available_time"),
            "last_close": last.get("close"),
            "ohlc_digest": f"sha256:{digest}",
            "provider": providers[0] if len(providers) == 1 else ("multiple" if providers else "unknown"),
            "providers": providers,
            "agent_input_policy": "local_storage_only",
            "external_fallback_allowed": False,
            "schema_version": "bar_meta.v1",
        }

    @staticmethod
    def _context_hash(
        *,
        symbol: str,
        interval: str,
        as_of_time: Any,
        input_snapshot_ids: Dict[str, Any],
        data_versions: Dict[str, Any],
    ) -> str:
        stable = {
            "symbol": symbol,
            "timeframe": interval,
            "as_of_time": as_of_time,
            "input_snapshot_ids": input_snapshot_ids,
            "data_versions": data_versions,
        }
        digest = hashlib.sha256(
            json.dumps(stable, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        return f"sha256:{digest}"

    async def _load_factors(
        self,
        symbol: str,
        interval: str,
        cutoff: datetime,
        limit: int,
    ) -> tuple[Dict[str, float], List[Any], Dict[str, Any]]:
        if limit <= 0:
            return {}, [], {}
        if self._sql_short_circuited():
            return {}, [], {}
        try:
            async with get_db() as session:
                result = await asyncio.wait_for(session.execute(text("""
                    SELECT DISTINCT ON (factor_name)
                           id, factor_name, factor_value, timestamp, available_time,
                           provider, data_source, source_version, schema_version
                    FROM factor_snapshots
                    WHERE symbol = :symbol
                      AND (:interval = '' OR interval = :interval OR parameters->>'interval' = :interval)
                      AND COALESCE(available_time, timestamp) <= :cutoff
                    ORDER BY factor_name, timestamp DESC
                    LIMIT :limit
                """), {
                    "symbol": symbol,
                    "interval": interval,
                    "cutoff": cutoff,
                    "limit": limit,
                }), timeout=self._SQL_QUERY_TIMEOUT_SECONDS)
                values: Dict[str, float] = {}
                ids: List[Any] = []
                versions: Dict[str, Any] = {}
                for row in result.fetchall():
                    ids.append(row[0])
                    values[row[1]] = float(row[2])
                    versions[row[1]] = {
                        "provider": row[5],
                        "data_source": row[6],
                        "source_version": row[7],
                        "schema_version": row[8],
                    }
                return values, ids, versions
        except Exception as e:
            self._mark_sql_unavailable(e)
            logger.debug(f"AnalysisContext factor load skipped for {symbol}: {e}")
            return {}, [], {}

    async def _load_signals(
        self,
        symbol: str,
        interval: str,
        cutoff: datetime,
        limit: int,
    ) -> tuple[List[Dict[str, Any]], List[Any], Dict[str, Any]]:
        if limit <= 0:
            return [], [], {}
        if self._sql_short_circuited():
            return [], [], {}
        try:
            async with get_db() as session:
                result = await asyncio.wait_for(session.execute(text("""
                    SELECT id, timestamp, available_time, signal_type, signal_value,
                           confidence, source_strategy, strategy_id, factors,
                           provider, data_source, source_version, schema_version,
                           extra_data
                    FROM signal_events
                    WHERE symbol = :symbol
                      AND (:interval = '' OR interval = :interval OR extra_data->>'interval' = :interval)
                      AND COALESCE(available_time, timestamp) <= :cutoff
                    ORDER BY timestamp DESC
                    LIMIT :limit
                """), {
                    "symbol": symbol,
                    "interval": interval,
                    "cutoff": cutoff,
                    "limit": limit,
                }), timeout=self._SQL_QUERY_TIMEOUT_SECONDS)
                rows: List[Dict[str, Any]] = []
                ids: List[Any] = []
                versions: Dict[str, Any] = {}
                for row in result.fetchall():
                    ids.append(row[0])
                    rows.append({
                        "id": row[0],
                        "event_time": self._iso(row[1]),
                        "available_time": self._iso(row[2] or row[1]),
                        "signal_type": row[3],
                        "signal_value": float(row[4]),
                        "confidence": float(row[5]),
                        "source_strategy": row[6],
                        "strategy_id": row[7],
                        "factors": row[8] or {},
                        "provider": row[9],
                        "data_source": row[10],
                        "source_version": row[11],
                        "schema_version": row[12],
                        "extra_data": row[13] or {},
                    })
                    versions[str(row[0])] = {
                        "provider": row[9],
                        "data_source": row[10],
                        "source_version": row[11],
                        "schema_version": row[12],
                    }
                return rows, ids, versions
        except Exception as e:
            self._mark_sql_unavailable(e)
            logger.debug(f"AnalysisContext signal load skipped for {symbol}: {e}")
            return [], [], {}

    def _sql_short_circuited(self) -> bool:
        return time.monotonic() < self._sql_unavailable_until

    def _mark_sql_unavailable(self, reason: Exception) -> None:
        self._sql_unavailable_until = time.monotonic() + self._SQL_UNAVAILABLE_RETRY_SECONDS
        logger.debug(
            "AnalysisContext SQL panels unavailable for %.0fs: %s",
            self._SQL_UNAVAILABLE_RETRY_SECONDS,
            reason,
        )

    def _load_news(self, instrument: Instrument, cutoff: datetime, limit: int) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        try:
            from app.pipeline.storage.duckdb_store import pipeline_store

            aliases = {instrument.symbol, instrument.base_asset}
            rows: List[Dict[str, Any]] = []
            for alias in aliases:
                rows.extend(pipeline_store.query_news(symbol=alias, limit=limit, end=cutoff))
            deduped: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                available_time = row.get("available_time") or row.get("published_at")
                if not self._visible(available_time, cutoff):
                    continue
                key = row.get("raw_payload_id") or row.get("url") or row.get("title")
                deduped[str(key)] = self._normalize_payload_row(row)
            return sorted(
                deduped.values(),
                key=lambda item: item.get("event_time") or "",
                reverse=True,
            )[:limit]
        except Exception as e:
            logger.debug(f"AnalysisContext news load skipped for {instrument.symbol}: {e}")
            return []

    def _load_macro(self, cutoff: datetime, limit: int) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        try:
            from app.pipeline.storage.duckdb_store import pipeline_store

            rows = pipeline_store.query_macro(end=cutoff, limit=limit)
            visible = []
            for row in rows:
                available_time = row.get("available_time") or row.get("timestamp")
                if self._visible(available_time, cutoff):
                    visible.append(self._normalize_payload_row(row))
            return visible[:limit]
        except Exception as e:
            logger.debug(f"AnalysisContext macro load skipped: {e}")
            return []

    def _normalize_payload_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in row.items():
            try:
                if pd.isna(value):
                    out[key] = None
                    continue
            except Exception:
                pass
            if isinstance(value, pd.Timestamp):
                out[key] = value.isoformat()
            elif isinstance(value, datetime):
                out[key] = value.isoformat()
            elif key == "metadata" and isinstance(value, str):
                try:
                    out[key] = json.loads(value)
                except Exception:
                    out[key] = value
            else:
                out[key] = value
        return out

    def _normalize_cutoff(self, value: Optional[datetime]) -> datetime:
        cutoff = value or datetime.now(timezone.utc)
        ts = pd.Timestamp(cutoff)
        if ts.tzinfo is None:
            ts = ts.tz_localize(timezone.utc)
        else:
            ts = ts.tz_convert(timezone.utc)
        return ts.tz_localize(None).to_pydatetime()

    def _visible(self, value: Any, cutoff: datetime) -> bool:
        if value is None:
            return True
        try:
            ts = pd.Timestamp(value)
            cutoff_ts = pd.Timestamp(cutoff)
            if ts.tzinfo is not None:
                ts = ts.tz_convert(timezone.utc).tz_localize(None)
            if cutoff_ts.tzinfo is not None:
                cutoff_ts = cutoff_ts.tz_convert(timezone.utc).tz_localize(None)
            return ts.to_pydatetime() <= cutoff_ts.to_pydatetime()
        except Exception:
            return True

    def _iso(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        try:
            return pd.Timestamp(value).isoformat()
        except Exception:
            return str(value)

    def _version_set(self, rows: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
        versions: Dict[str, set[Any]] = {
            "provider": set(),
            "source_version": set(),
            "schema_version": set(),
        }
        for row in rows:
            for key in versions:
                if row.get(key):
                    versions[key].add(row[key])
        return {key: sorted(value) for key, value in versions.items()}


analysis_context_builder = AnalysisContextBuilder.get_instance()
