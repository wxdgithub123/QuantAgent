"""L5 factor and signal generation pipeline.

This service bridges the currently separate pieces:
  L2/L3 standardized bars -> L4 storage -> L5 factor snapshots -> signal events.

It is intentionally callable on demand from the API so teammates can verify the
L1-L5 flow without waiting for a scheduler.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from app.models.db_models import FactorSnapshotDB, SignalEventDB
from app.models.instrument import Instrument
from app.models.trading import BarData
from app.services.database import get_db
from app.services.indicators import add_all_indicators
from app.services.market_data_gateway import market_data_gateway
from app.services.strategy_templates import build_signal_func
from sqlalchemy import delete

logger = logging.getLogger(__name__)

DEFAULT_STRATEGIES = ["ma", "rsi", "boll", "macd", "ema_triple", "atr_trend", "turtle", "ichimoku"]

FACTOR_COLUMNS: Dict[str, Dict[str, Any]] = {
    "sma_5": {"family": "sma", "period": 5},
    "sma_10": {"family": "sma", "period": 10},
    "sma_20": {"family": "sma", "period": 20},
    "sma_60": {"family": "sma", "period": 60},
    "ema_12": {"family": "ema", "period": 12},
    "ema_26": {"family": "ema", "period": 26},
    "boll_mid": {"family": "bollinger", "period": 20, "std_dev": 2.0},
    "boll_upper": {"family": "bollinger", "period": 20, "std_dev": 2.0},
    "boll_lower": {"family": "bollinger", "period": 20, "std_dev": 2.0},
    "boll_pct_b": {"family": "bollinger", "period": 20, "std_dev": 2.0},
    "boll_width": {"family": "bollinger", "period": 20, "std_dev": 2.0},
    "rsi_14": {"family": "rsi", "period": 14},
    "macd_dif": {"family": "macd", "fast": 12, "slow": 26, "signal": 9},
    "macd_dea": {"family": "macd", "fast": 12, "slow": 26, "signal": 9},
    "macd_hist": {"family": "macd", "fast": 12, "slow": 26, "signal": 9},
    "atr_14": {"family": "atr", "period": 14},
}


@dataclass
class LoadedBars:
    df: pd.DataFrame
    source: str
    provider: str
    stored_rows: int = 0


class FactorSignalPipeline:
    """Generate and persist factor snapshots plus strategy signal events."""

    _instance: Optional["FactorSignalPipeline"] = None

    @classmethod
    def get_instance(cls) -> "FactorSignalPipeline":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def run(
        self,
        symbol: str = "BTCUSDT",
        asset_type: str = "crypto",
        interval: str = "1h",
        limit: int = 300,
        strategies: Optional[List[str]] = None,
        include_wait_signals: bool = True,
        persist_fetched_bars: bool = True,
        refresh_from_source: bool = False,
        provider: Optional[str] = None,
        fallback_providers: Optional[List[str]] = None,
        include_context: bool = True,
    ) -> Dict[str, Any]:
        """Run the L5 pipeline and return a compact execution summary."""

        instrument = Instrument.from_raw(symbol)
        canonical_symbol = instrument.symbol
        normalized_asset_type = self._normalize_asset_type(asset_type)
        provider = provider or "yfinance"
        selected_strategies = self._normalize_strategies(strategies)
        limit = max(60, min(int(limit), 5000))

        loaded = await self._load_bars(
            instrument=instrument,
            asset_type=normalized_asset_type,
            interval=interval,
            limit=limit,
            persist_fetched_bars=persist_fetched_bars,
            refresh_from_source=refresh_from_source,
            provider=provider,
            fallback_providers=fallback_providers,
        )
        if loaded.df.empty:
            return {
                "status": "no_data",
                "symbol": canonical_symbol,
                "asset_type": normalized_asset_type,
                "interval": interval,
                "bars": 0,
                "factor_rows_written": 0,
                "signal_rows_written": 0,
                "strategies": selected_strategies,
                "detail": "No bars available from storage, OpenBB, or exchange fallback.",
            }

        bars_df = self._normalize_ohlcv_dataframe(loaded.df).tail(limit)
        if bars_df.empty:
            return {
                "status": "invalid_data",
                "symbol": canonical_symbol,
                "asset_type": normalized_asset_type,
                "interval": interval,
                "bars": 0,
                "factor_rows_written": 0,
                "signal_rows_written": 0,
                "strategies": selected_strategies,
                "detail": "Loaded bars did not contain usable OHLCV columns.",
            }

        factor_df = add_all_indicators(bars_df)
        factor_rows = self._build_factor_rows(
            factor_df,
            symbol=canonical_symbol,
            interval=interval,
            provider=loaded.provider,
            source=loaded.source,
        )
        signal_rows = await self._build_signal_rows(
            bars_df,
            factor_df,
            symbol=canonical_symbol,
            interval=interval,
            strategies=selected_strategies,
            include_wait_signals=include_wait_signals,
            provider=loaded.provider,
            source=loaded.source,
        )

        min_ts = self._to_python_datetime(bars_df.index.min())
        max_ts = self._to_python_datetime(bars_df.index.max())
        news_events = await self._load_news_events(
            instrument=instrument,
            provider=provider,
            fallback_providers=fallback_providers,
            refresh_from_source=refresh_from_source,
        )
        macro_events = await self._load_macro_events(
            provider=provider,
            fallback_providers=fallback_providers,
            refresh_from_source=refresh_from_source,
        )
        context_factor_rows = self._build_context_factor_rows(
            symbol=canonical_symbol,
            interval=interval,
            provider=loaded.provider,
            source=loaded.source,
            timestamp=max_ts,
            news_events=news_events,
            macro_events=macro_events,
        )
        context_signal_rows = self._build_context_signal_rows(
            symbol=canonical_symbol,
            interval=interval,
            provider=loaded.provider,
            source=loaded.source,
            timestamp=max_ts,
            news_events=news_events,
            include_wait_signals=include_wait_signals,
        )
        factor_rows.extend(context_factor_rows)
        signal_rows.extend(context_signal_rows)

        factor_written, signal_written = await self._replace_window(
            symbol=canonical_symbol,
            interval=interval,
            start=min_ts,
            end=max_ts,
            strategies=selected_strategies,
            factor_rows=factor_rows,
            signal_rows=signal_rows,
        )

        latest_factors = self._latest_factor_values(factor_df)
        latest_factors.update(self._latest_context_factor_values(context_factor_rows))
        latest_signal_counts = self._signal_counts(signal_rows)
        analysis_context: Optional[Dict[str, Any]] = None
        if include_context:
            try:
                from app.services.analysis_context_builder import analysis_context_builder

                context = await analysis_context_builder.build(
                    symbol=canonical_symbol,
                    interval=interval,
                    as_of_time=datetime.utcnow(),
                )
                analysis_context = context.to_agent_payload()
            except Exception as e:
                logger.debug(f"L5 AnalysisContext assembly skipped for {canonical_symbol}: {e}")

        return {
            "status": "ok",
            "symbol": canonical_symbol,
            "asset_type": normalized_asset_type,
            "interval": interval,
            "bars": int(len(bars_df)),
            "data_source": loaded.source,
            "provider": loaded.provider,
            "stored_rows_from_fetch": loaded.stored_rows,
            "factor_rows_written": factor_written,
            "signal_rows_written": signal_written,
            "strategies": selected_strategies,
            "include_wait_signals": include_wait_signals,
            "window": {
                "start": min_ts.isoformat(),
                "end": max_ts.isoformat(),
            },
            "latest_timestamp": max_ts.isoformat(),
            "latest_close": float(bars_df["close"].iloc[-1]),
            "latest_factors": latest_factors,
            "signal_counts": latest_signal_counts,
            "news_events_used": len(news_events),
            "macro_events_used": len(macro_events),
            "analysis_context": analysis_context,
        }

    async def _load_bars(
        self,
        instrument: Instrument,
        asset_type: str,
        interval: str,
        limit: int,
        persist_fetched_bars: bool,
        refresh_from_source: bool,
        provider: str,
        fallback_providers: Optional[List[str]],
    ) -> LoadedBars:
        if not refresh_from_source:
            stored = await self._load_from_storage(instrument.symbol, interval, limit)
            if stored is not None and not stored.empty:
                return LoadedBars(df=stored, source="storage", provider="active-storage")

        source_bars = await self._fetch_from_openbb(
            instrument=instrument,
            asset_type=asset_type,
            interval=interval,
            limit=limit,
            provider=provider,
            fallback_providers=fallback_providers,
        )
        provider = "openbb"
        if asset_type == "crypto" and not source_bars:
            source_bars = await self._fetch_from_exchange_fallback(instrument, interval, limit)
            provider = "exchange-fallback"

        if not source_bars:
            return LoadedBars(df=pd.DataFrame(), source="none", provider="none")

        df = self._bars_to_dataframe(source_bars)
        provider_name = source_bars[-1].provider or provider
        stored_rows = 0
        if persist_fetched_bars:
            stored_rows = await self._persist_bars(instrument.symbol, interval, source_bars)
        return LoadedBars(df=df, source="live-fetch", provider=provider_name, stored_rows=stored_rows)

    async def _load_from_storage(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        try:
            from app.services.storage_factory import get_storage_service

            storage = get_storage_service()
            offset = 0
            if hasattr(storage, "count_klines"):
                count = await storage.count_klines(symbol, interval)
                offset = max(int(count) - int(limit), 0)

            if hasattr(storage, "query_klines"):
                rows = await storage.query_klines(symbol, interval, limit=limit, offset=offset)
                if rows:
                    return self._rows_to_dataframe(rows)

            df = await storage.get_klines_dataframe(symbol, interval, limit=limit)
            return df
        except Exception as e:
            logger.debug(f"L5 storage load skipped for {symbol}/{interval}: {e}")
            return None

    async def _fetch_from_openbb(
        self,
        instrument: Instrument,
        asset_type: str,
        interval: str,
        limit: int,
        provider: str,
        fallback_providers: Optional[List[str]],
    ) -> List[BarData]:
        try:
            from app.services.openbb_data_service import openbb_data_service

            if not openbb_data_service.available:
                return []
            if asset_type == "equity":
                return await openbb_data_service.get_equity_historical(
                    instrument.symbol,
                    interval=interval,
                    limit=limit,
                    provider=provider,
                    fallback_providers=fallback_providers,
                )
            return await openbb_data_service.get_crypto_historical(
                instrument.symbol,
                interval=interval,
                limit=limit,
                provider=provider,
                fallback_providers=fallback_providers,
            )
        except Exception as e:
            logger.debug(f"L5 OpenBB fetch skipped for {instrument.symbol}/{interval}: {e}")
            return []

    async def _fetch_from_exchange_fallback(self, instrument: Instrument, interval: str, limit: int) -> List[BarData]:
        try:
            df = await market_data_gateway.get_dataframe(
                instrument.ccxt_symbol,
                interval=interval,
                limit=limit,
            )
            df = self._normalize_ohlcv_dataframe(df)
            if df.empty:
                return []
            ingested_at = datetime.now(timezone.utc)
            return [
                BarData(
                    symbol=instrument.symbol,
                    instrument_id=instrument.symbol,
                    exchange="exchange-fallback",
                    provider="exchange-fallback",
                    source_version="ccxt",
                    schema_version="bar.v1",
                    datetime=self._to_python_datetime(ts),
                    event_time=self._to_python_datetime(ts),
                    available_time=ingested_at,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    interval=interval,
                    timeframe=interval,
                )
                for ts, row in df.iterrows()
            ]
        except Exception as e:
            logger.debug(f"L5 exchange fallback fetch skipped for {instrument.symbol}/{interval}: {e}")
            return []

    async def _persist_bars(self, symbol: str, interval: str, bars: List[BarData]) -> int:
        try:
            from app.services.storage_factory import get_storage_service

            rows = []
            for bar in bars:
                close_time = bar.event_time or bar.datetime
                rows.append({
                    "open_time": bar.datetime,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "close_time": close_time,
                    "event_time": bar.event_time or bar.datetime,
                    "available_time": bar.available_time or close_time,
                    "provider": bar.provider,
                    "source_version": bar.source_version,
                    "schema_version": bar.schema_version,
                })
            storage = get_storage_service()
            if hasattr(storage, "insert_klines"):
                return await storage.insert_klines(symbol, interval, rows)
        except Exception as e:
            logger.debug(f"L5 bar persistence skipped for {symbol}/{interval}: {e}")
        return 0

    def _rows_to_dataframe(self, rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
        df = pd.DataFrame(list(rows))
        if df.empty:
            return df
        if "open_time" in df.columns:
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            df = df.set_index("open_time")
        elif "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.set_index("timestamp")
        return self._normalize_ohlcv_dataframe(df)

    def _bars_to_dataframe(self, bars: List[BarData]) -> pd.DataFrame:
        rows = [{
            "timestamp": b.datetime,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        } for b in bars]
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return self._normalize_ohlcv_dataframe(df.set_index("timestamp"))

    def _normalize_ohlcv_dataframe(self, df: Optional[pd.DataFrame]) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        result = df.copy()
        if not isinstance(result.index, pd.DatetimeIndex):
            if "open_time" in result.columns:
                result["open_time"] = pd.to_datetime(result["open_time"], utc=True)
                result = result.set_index("open_time")
            elif "timestamp" in result.columns:
                result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
                result = result.set_index("timestamp")
            else:
                return pd.DataFrame()

        result.index = pd.to_datetime(result.index, utc=True)
        result = result.sort_index()
        result = result[~result.index.duplicated(keep="last")]

        required = ["open", "high", "low", "close", "volume"]
        missing = [col for col in required if col not in result.columns]
        if missing:
            logger.warning(f"L5 bars missing columns: {missing}")
            return pd.DataFrame()
        for col in required:
            result[col] = pd.to_numeric(result[col], errors="coerce")
        result = result.replace([np.inf, -np.inf], np.nan).dropna(subset=required)
        return result[required]

    def _build_factor_rows(
        self,
        factor_df: pd.DataFrame,
        symbol: str,
        interval: str,
        provider: str,
        source: str,
    ) -> List[FactorSnapshotDB]:
        rows: List[FactorSnapshotDB] = []
        for ts, row in factor_df.iterrows():
            timestamp = self._to_python_datetime(ts)
            for factor_name, meta in FACTOR_COLUMNS.items():
                if factor_name not in row:
                    continue
                value = row[factor_name]
                if not self._is_finite(value):
                    continue
                rows.append(
                    FactorSnapshotDB(
                        symbol=symbol,
                        instrument_id=symbol,
                        timestamp=timestamp,
                        event_time=timestamp,
                        available_time=timestamp,
                        as_of_time=timestamp,
                        factor_name=factor_name,
                        factor_value=float(value),
                        interval=interval,
                        provider=provider,
                        data_source=source,
                        source_version="l5_pipeline",
                        schema_version="factor_snapshot.v1",
                        parameters={
                            **meta,
                            "interval": interval,
                            "provider": provider,
                            "data_source": source,
                            "schema_version": "factor_snapshot.v1",
                        },
                        source="l5_pipeline",
                    )
                )
        return rows

    async def _build_signal_rows(
        self,
        bars_df: pd.DataFrame,
        factor_df: pd.DataFrame,
        symbol: str,
        interval: str,
        strategies: List[str],
        include_wait_signals: bool,
        provider: str,
        source: str,
    ) -> List[SignalEventDB]:
        rows: List[SignalEventDB] = []
        for strategy in strategies:
            try:
                signal_func = build_signal_func(strategy, {})
                series = signal_func(bars_df)
                if inspect.isawaitable(series):
                    series = await series
                if series is None or len(series) == 0:
                    continue
                series = series.reindex(bars_df.index, fill_value=0).replace([np.inf, -np.inf], 0).fillna(0)
            except Exception as e:
                logger.warning(f"L5 signal generation failed for strategy={strategy}: {e}")
                continue

            for ts, raw_signal in series.items():
                signal_value = self._normalize_signal_value(raw_signal)
                if signal_value == 0 and not include_wait_signals:
                    continue
                timestamp = self._to_python_datetime(ts)
                factors = self._factor_values_at(factor_df, ts)
                rows.append(
                    SignalEventDB(
                        symbol=symbol,
                        instrument_id=symbol,
                        timestamp=timestamp,
                        event_time=timestamp,
                        available_time=timestamp,
                        as_of_time=timestamp,
                        signal_type=self._signal_type(signal_value),
                        signal_value=float(signal_value),
                        confidence=self._confidence(signal_value, factors),
                        source_strategy=strategy,
                        strategy_id=f"l5_{strategy}_{interval}",
                        interval=interval,
                        provider=provider,
                        data_source=source,
                        source_version="l5_pipeline",
                        schema_version="signal_event.v1",
                        factors=factors,
                        extra_data={
                            "interval": interval,
                            "provider": provider,
                            "data_source": source,
                            "schema_version": "signal_event.v1",
                            "generated_by": "factor_signal_pipeline",
                        },
                    )
                )
        return rows

    async def _replace_window(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        strategies: List[str],
        factor_rows: List[FactorSnapshotDB],
        signal_rows: List[SignalEventDB],
    ) -> tuple[int, int]:
        async with get_db() as session:
            await session.execute(
                delete(FactorSnapshotDB).where(
                    FactorSnapshotDB.symbol == symbol,
                    FactorSnapshotDB.timestamp >= start,
                    FactorSnapshotDB.timestamp <= end,
                    FactorSnapshotDB.source == "l5_pipeline",
                    FactorSnapshotDB.interval == interval,
                )
            )
            strategy_ids = sorted({row.strategy_id for row in signal_rows if row.strategy_id})
            if strategy_ids:
                await session.execute(
                    delete(SignalEventDB).where(
                        SignalEventDB.symbol == symbol,
                        SignalEventDB.timestamp >= start,
                        SignalEventDB.timestamp <= end,
                        SignalEventDB.strategy_id.in_(strategy_ids),
                    )
                )
            if factor_rows:
                session.add_all(factor_rows)
            if signal_rows:
                session.add_all(signal_rows)
        return len(factor_rows), len(signal_rows)

    async def _load_news_events(
        self,
        instrument: Instrument,
        provider: str,
        fallback_providers: Optional[List[str]],
        refresh_from_source: bool,
    ) -> List[Dict[str, Any]]:
        from app.pipeline.storage.duckdb_store import pipeline_store

        aliases = [instrument.symbol, instrument.base_asset]
        articles: List[Any] = []
        if refresh_from_source or not any(pipeline_store.query_news(symbol=alias, limit=1) for alias in aliases):
            try:
                from app.services.openbb_data_service import openbb_data_service

                articles = await openbb_data_service.get_news(
                    instrument.symbol,
                    limit=20,
                    provider=provider,
                    fallback_providers=fallback_providers,
                )
                if articles:
                    pipeline_store.upsert_news(articles)
            except Exception as e:
                logger.debug(f"L5 news fetch skipped for {instrument.symbol}: {e}")

        rows: Dict[str, Dict[str, Any]] = {}
        for alias in aliases:
            for row in pipeline_store.query_news(symbol=alias, limit=20):
                key = row.get("raw_payload_id") or row.get("url") or row.get("title")
                rows[str(key)] = row
        return list(rows.values())

    async def _load_macro_events(
        self,
        provider: str,
        fallback_providers: Optional[List[str]],
        refresh_from_source: bool,
    ) -> List[Dict[str, Any]]:
        from app.pipeline.storage.duckdb_store import pipeline_store

        rows = pipeline_store.query_macro(limit=30)
        if refresh_from_source or not rows:
            try:
                from app.services.openbb_data_service import openbb_data_service

                snapshots = await openbb_data_service.get_macro_events(
                    provider="fred",
                    fallback_providers=fallback_providers,
                )
                if not snapshots:
                    from app.pipeline.adapters.macro_adapter import macro_adapter

                    snapshots = await macro_adapter.fetch_all()
                if snapshots:
                    pipeline_store.upsert_macro(snapshots)
                    rows = pipeline_store.query_macro(limit=30)
            except Exception as e:
                logger.debug(f"L5 macro fetch skipped: {e}")
        return rows

    def _build_context_factor_rows(
        self,
        symbol: str,
        interval: str,
        provider: str,
        source: str,
        timestamp: datetime,
        news_events: List[Dict[str, Any]],
        macro_events: List[Dict[str, Any]],
    ) -> List[FactorSnapshotDB]:
        rows: List[FactorSnapshotDB] = []
        available_time = timestamp
        news_scores = [
            float(row["sentiment_score"])
            for row in news_events
            if self._is_finite(row.get("sentiment_score"))
        ]
        if news_scores:
            rows.append(self._context_factor_row(
                symbol=symbol,
                timestamp=timestamp,
                interval=interval,
                provider=provider,
                source=source,
                name="news_sentiment_mean",
                value=mean(news_scores),
                parameters={
                    "window": "recent_news",
                    "article_count": len(news_scores),
                    "schema_version": "factor_snapshot.v1",
                },
                available_time=available_time,
            ))
        event_tag_rows = [
            set(self._normalize_event_tags(row.get("event_tags")))
            for row in news_events
        ]
        for tag in sorted({tag for tags in event_tag_rows for tag in tags}):
            count = sum(1 for tags in event_tag_rows if tag in tags)
            rows.append(self._context_factor_row(
                symbol=symbol,
                timestamp=timestamp,
                interval=interval,
                provider=provider,
                source=source,
                name=f"news_event_{tag}",
                value=float(count),
                parameters={
                    "event_tag": tag,
                    "article_count": len(news_events),
                    "schema_version": "factor_snapshot.v1",
                },
                available_time=available_time,
            ))
        for row in macro_events:
            indicator = str(row.get("indicator") or "").strip()
            value = row.get("value")
            if indicator and self._is_finite(value):
                rows.append(self._context_factor_row(
                    symbol=symbol,
                    timestamp=timestamp,
                    interval=interval,
                    provider=row.get("provider") or provider,
                    source="macro",
                    name=f"macro_{indicator}",
                    value=float(value),
                    parameters={
                        "macro_timestamp": str(row.get("timestamp")),
                        "source": row.get("source"),
                        "schema_version": "factor_snapshot.v1",
                    },
                    available_time=available_time,
                ))
        return rows

    def _context_factor_row(
        self,
        symbol: str,
        timestamp: datetime,
        interval: str,
        provider: str,
        source: str,
        name: str,
        value: float,
        parameters: Dict[str, Any],
        available_time: datetime,
    ) -> FactorSnapshotDB:
        return FactorSnapshotDB(
            symbol=symbol,
            instrument_id=symbol,
            timestamp=timestamp,
            event_time=timestamp,
            available_time=available_time,
            as_of_time=timestamp,
            factor_name=name,
            factor_value=float(value),
            interval=interval,
            provider=provider,
            data_source=source,
            source_version="l5_pipeline",
            schema_version="factor_snapshot.v1",
            parameters={
                **parameters,
                "interval": interval,
                "provider": provider,
                "data_source": source,
            },
            source="l5_pipeline",
        )

    def _build_context_signal_rows(
        self,
        symbol: str,
        interval: str,
        provider: str,
        source: str,
        timestamp: datetime,
        news_events: List[Dict[str, Any]],
        include_wait_signals: bool,
    ) -> List[SignalEventDB]:
        scores = [
            float(row["sentiment_score"])
            for row in news_events
            if self._is_finite(row.get("sentiment_score"))
        ]
        if not scores:
            return [] if not include_wait_signals else [self._context_signal_row(
                symbol=symbol,
                interval=interval,
                provider=provider,
                source=source,
                timestamp=timestamp,
                signal_value=0,
                confidence=0.5,
                sentiment=0.0,
                article_count=0,
            )]
        sentiment = mean(scores)
        if sentiment > 0.2:
            signal_value = 1
        elif sentiment < -0.2:
            signal_value = -1
        else:
            signal_value = 0
        if signal_value == 0 and not include_wait_signals:
            return []
        confidence = round(min(0.55 + abs(sentiment) * 0.35, 0.9), 4)
        return [self._context_signal_row(
            symbol=symbol,
            interval=interval,
            provider=provider,
            source=source,
            timestamp=timestamp,
            signal_value=signal_value,
            confidence=confidence,
            sentiment=sentiment,
            article_count=len(scores),
        )]

    def _context_signal_row(
        self,
        symbol: str,
        interval: str,
        provider: str,
        source: str,
        timestamp: datetime,
        signal_value: int,
        confidence: float,
        sentiment: float,
        article_count: int,
    ) -> SignalEventDB:
        available_time = timestamp
        factors = {"news_sentiment_mean": round(float(sentiment), 6)}
        return SignalEventDB(
            symbol=symbol,
            instrument_id=symbol,
            timestamp=timestamp,
            event_time=timestamp,
            available_time=available_time,
            as_of_time=timestamp,
            signal_type=self._signal_type(signal_value),
            signal_value=float(signal_value),
            confidence=confidence,
            source_strategy="news_sentiment",
            strategy_id=f"l5_news_sentiment_{interval}",
            interval=interval,
            provider=provider,
            data_source=source,
            source_version="l5_pipeline",
            schema_version="signal_event.v1",
            factors=factors,
            extra_data={
                "interval": interval,
                "provider": provider,
                "data_source": source,
                "schema_version": "signal_event.v1",
                "generated_by": "factor_signal_pipeline",
                "article_count": article_count,
            },
        )

    def _factor_values_at(self, factor_df: pd.DataFrame, ts: Any) -> Dict[str, float]:
        if ts not in factor_df.index:
            return {}
        row = factor_df.loc[ts]
        values: Dict[str, float] = {}
        for name in FACTOR_COLUMNS:
            if name not in row:
                continue
            value = row[name]
            if self._is_finite(value):
                values[name] = float(value)
        return values

    def _latest_factor_values(self, factor_df: pd.DataFrame) -> Dict[str, float]:
        if factor_df.empty:
            return {}
        latest = factor_df.iloc[-1]
        out: Dict[str, float] = {}
        for name in FACTOR_COLUMNS:
            if name in latest and self._is_finite(latest[name]):
                out[name] = round(float(latest[name]), 8)
        return out

    def _latest_context_factor_values(self, factor_rows: List[FactorSnapshotDB]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for row in factor_rows:
            if self._is_finite(row.factor_value):
                out[row.factor_name] = round(float(row.factor_value), 8)
        return out

    def _signal_counts(self, signal_rows: List[SignalEventDB]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in signal_rows:
            counts[row.signal_type] = counts.get(row.signal_type, 0) + 1
        return counts

    def _normalize_strategies(self, strategies: Optional[List[str]]) -> List[str]:
        if not strategies:
            return DEFAULT_STRATEGIES.copy()
        cleaned = []
        for item in strategies:
            name = str(item).strip()
            if name and name not in cleaned:
                cleaned.append(name)
        return cleaned or DEFAULT_STRATEGIES.copy()

    def _normalize_asset_type(self, asset_type: str) -> str:
        value = (asset_type or "crypto").strip().lower()
        if value in {"stock", "stocks", "equity", "equities"}:
            return "equity"
        return "crypto"

    def _normalize_signal_value(self, value: Any) -> int:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0
        if numeric > 0:
            return 1
        if numeric < 0:
            return -1
        return 0

    def _signal_type(self, signal_value: int) -> str:
        return {1: "BUY", -1: "SELL", 0: "WAIT"}.get(signal_value, "WAIT")

    def _confidence(self, signal_value: int, factors: Dict[str, float]) -> float:
        if signal_value == 0:
            return 0.5
        rsi = factors.get("rsi_14")
        macd_hist = abs(factors.get("macd_hist", 0.0))
        atr = abs(factors.get("atr_14", 0.0))
        score = 0.65
        if rsi is not None and (rsi < 35 or rsi > 65):
            score += 0.05
        if macd_hist > 0:
            score += 0.03
        if atr > 0:
            score += 0.02
        return round(min(score, 0.85), 4)

    def _is_finite(self, value: Any) -> bool:
        try:
            return bool(np.isfinite(float(value)))
        except (TypeError, ValueError):
            return False

    def _normalize_event_tags(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, np.ndarray):
            raw_tags = value.tolist()
        elif isinstance(value, pd.Series):
            raw_tags = value.tolist()
        elif isinstance(value, (list, tuple, set)):
            raw_tags = list(value)
        else:
            raw_tags = [value]

        tags: List[str] = []
        for item in raw_tags:
            try:
                if bool(pd.isna(item)):
                    continue
            except (TypeError, ValueError):
                pass
            tag = str(item).strip()
            if tag:
                tags.append(tag)
        return tags

    def _to_python_datetime(self, value: Any) -> datetime:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize(timezone.utc)
        else:
            ts = ts.tz_convert(timezone.utc)
        ts = ts.tz_localize(None)
        return ts.to_pydatetime()


factor_signal_pipeline = FactorSignalPipeline.get_instance()
