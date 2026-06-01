"""Market data gateway with OpenBB/local-first routing.

PRD 10.4 treats OpenBB as the unified data entry. Exchange-specific REST access
is only kept as an explicit opt-in fallback for edge cases.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from app.models.market_data import KlineData, SymbolInfo, TickerData
from app.models.trading import BarData

logger = logging.getLogger(__name__)


INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
}


def _clean_symbol(symbol: str) -> str:
    value = symbol.upper().replace("/", "")
    return value


def _to_ccxt_symbol(symbol: str) -> str:
    value = symbol.upper()
    if "/" in value:
        return value
    for quote in ("USDT", "USDC", "BUSD", "USD", "BTC", "ETH", "BNB"):
        if value.endswith(quote) and len(value) > len(quote):
            return f"{value[:-len(quote)]}/{quote}"
    return value


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bar_to_kline(bar: BarData) -> KlineData:
    return KlineData(
        timestamp=bar.datetime,
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=float(bar.volume),
        close_time=bar.bar_end_time or bar.datetime,
        quote_volume=bar.volume_notional,
        trades=bar.transactions,
    )


def _is_fresh(klines: List[KlineData], interval: str, end_time: Optional[datetime]) -> bool:
    if not klines:
        return False
    if end_time is not None:
        return True
    latest = _as_utc(klines[-1].timestamp)
    now = datetime.now(timezone.utc)
    interval_seconds = INTERVAL_SECONDS.get(interval, 3600)
    max_age = timedelta(seconds=max(interval_seconds * 2, 3600))
    return now - latest <= max_age


def _row_to_kline(row: Dict[str, Any]) -> KlineData:
    return KlineData(
        timestamp=row["open_time"],
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        close_time=row.get("close_time") or row["open_time"],
    )


def _serialize_time(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class MarketDataGateway:
    """Local storage + OpenBB-first market data access."""

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        openbb_provider: str = "yfinance",
        openbb_fallback_providers: Optional[List[str]] = None,
        allow_ccxt_fallback: bool = True,
        fallback_exchange: str = "okx",
        allow_binance_fallback: bool = False,
    ) -> List[KlineData]:
        clean_symbol = _clean_symbol(symbol)

        rows = await self._get_local_klines(clean_symbol, interval, limit, start_time, end_time)
        if rows and _is_fresh(rows, interval, end_time):
            return rows

        openbb_start = start_time
        openbb_limit = limit
        if rows and start_time is None and end_time is None:
            latest = _as_utc(rows[-1].timestamp)
            openbb_start = latest + timedelta(seconds=INTERVAL_SECONDS.get(interval, 3600))
            expected_missing = int(
                max((datetime.now(timezone.utc) - openbb_start).total_seconds(), 0)
                / INTERVAL_SECONDS.get(interval, 3600)
            ) + 2
            openbb_limit = max(limit, min(expected_missing, 5000))

        bars = await self.get_openbb_bars(
            clean_symbol,
            interval=interval,
            limit=openbb_limit,
            start_time=openbb_start,
            end_time=end_time,
            provider=openbb_provider,
            fallback_providers=openbb_fallback_providers,
            persist=True,
        )
        if bars:
            merged = [*rows, *[_bar_to_kline(bar) for bar in bars]]
            by_time = {k.timestamp: k for k in merged}
            return [by_time[ts] for ts in sorted(by_time.keys())][-limit:]

        if rows:
            return rows

        if allow_ccxt_fallback and fallback_exchange:
            try:
                from app.services.exchange_service import exchange_service

                since = int(start_time.timestamp() * 1000) if start_time else None
                return await exchange_service.get_klines(
                    exchange_id=fallback_exchange,
                    symbol=_to_ccxt_symbol(clean_symbol),
                    timeframe=interval,
                    limit=limit,
                    since=since,
                )
            except Exception as exc:
                logger.warning(
                    "CCXT fallback failed for %s/%s via %s: %s",
                    clean_symbol,
                    interval,
                    fallback_exchange,
                    exc,
                )

        if allow_binance_fallback:
            try:
                from app.services.binance_service import binance_service

                since = int(start_time.timestamp() * 1000) if start_time else None
                return await binance_service.get_klines(
                    symbol=_to_ccxt_symbol(clean_symbol),
                    timeframe=interval,
                    limit=limit,
                    since=since,
                )
            except Exception as exc:
                logger.warning("Binance kline fallback failed for %s/%s: %s", clean_symbol, interval, exc)
        return []

    async def get_openbb_bars(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        provider: str = "yfinance",
        fallback_providers: Optional[List[str]] = None,
        persist: bool = False,
    ) -> List[BarData]:
        from app.services.openbb_data_service import openbb_data_service

        bars = await openbb_data_service.get_crypto_historical(
            symbol=_clean_symbol(symbol),
            interval=interval,
            start=start_time,
            end=end_time,
            limit=limit,
            provider=provider,
            fallback_providers=fallback_providers or [],
        )
        if bars and persist:
            await self.persist_bars(_clean_symbol(symbol), interval, bars)
        return bars

    async def get_ticker(
        self,
        symbol: str,
        openbb_provider: str = "yfinance",
        openbb_fallback_providers: Optional[List[str]] = None,
        allow_ccxt_fallback: bool = True,
        fallback_exchange: str = "okx",
        allow_binance_fallback: bool = False,
    ) -> Optional[TickerData]:
        clean_symbol = _clean_symbol(symbol)
        ticker = await self._get_local_ticker(clean_symbol)
        if ticker:
            return ticker

        from app.services.openbb_data_service import openbb_data_service

        ticker = await openbb_data_service.get_crypto_ticker(
            clean_symbol,
            provider=openbb_provider,
            fallback_providers=openbb_fallback_providers,
        )
        if ticker:
            return ticker

        if allow_ccxt_fallback and fallback_exchange:
            try:
                from app.services.exchange_service import exchange_service

                return await exchange_service.get_ticker(
                    fallback_exchange,
                    _to_ccxt_symbol(clean_symbol),
                )
            except Exception as exc:
                logger.warning("CCXT ticker fallback failed for %s via %s: %s", clean_symbol, fallback_exchange, exc)

        if allow_binance_fallback:
            try:
                from app.services.binance_service import binance_service

                return await binance_service.get_ticker(_to_ccxt_symbol(clean_symbol))
            except Exception as exc:
                logger.warning("Binance ticker fallback failed for %s: %s", clean_symbol, exc)
        return None

    async def get_price(
        self,
        symbol: str,
        openbb_provider: str = "yfinance",
        openbb_fallback_providers: Optional[List[str]] = None,
        allow_ccxt_fallback: bool = True,
        fallback_exchange: str = "okx",
        allow_binance_fallback: bool = False,
    ) -> Optional[float]:
        ticker = await self.get_ticker(
            symbol,
            openbb_provider=openbb_provider,
            openbb_fallback_providers=openbb_fallback_providers,
            allow_ccxt_fallback=allow_ccxt_fallback,
            fallback_exchange=fallback_exchange,
            allow_binance_fallback=allow_binance_fallback,
        )
        return ticker.price if ticker else None

    async def get_kline_metadata(
        self,
        symbol: str,
        interval: str = "1h",
    ) -> Dict[str, Any]:
        """Describe the source currently backing dashboard K-lines."""
        clean_symbol = _clean_symbol(symbol)
        metadata: Dict[str, Any] = {
            "active_source": "market_data_gateway",
            "cache": "clickhouse:klines",
            "symbol": clean_symbol,
            "interval": interval,
            "provider": "unknown",
            "exchange": "unknown",
            "updated_at": None,
            "source_groups": [],
        }
        try:
            from app.services.clickhouse_service import clickhouse_service

            ranges = await clickhouse_service.get_market_bar_source_ranges()
            groups = [
                {
                    **item,
                    "min_time": _serialize_time(item.get("min_time")),
                    "max_time": _serialize_time(item.get("max_time")),
                }
                for item in ranges
                if item.get("symbol") == clean_symbol and item.get("interval") == interval
            ]
            metadata["source_groups"] = groups

            if groups:
                latest = max(groups, key=lambda item: item.get("max_time") or "")
                metadata["provider"] = latest.get("provider") or "unknown"
                metadata["exchange"] = latest.get("exchange") or "unknown"
                metadata["updated_at"] = latest.get("max_time")
                metadata["active_source"] = f"{metadata['provider']}:{metadata['exchange']}"
            else:
                max_time = await clickhouse_service.get_max_timestamp(clean_symbol, interval)
                metadata["updated_at"] = _serialize_time(max_time)
                if max_time:
                    metadata["provider"] = "legacy"
                    metadata["exchange"] = "clickhouse"
                    metadata["active_source"] = "clickhouse:legacy_klines"
        except Exception as exc:
            logger.debug("Kline metadata unavailable for %s/%s: %s", clean_symbol, interval, exc)
        return metadata

    async def get_symbols(self) -> List[SymbolInfo]:
        from app.core.config import settings

        return [
            SymbolInfo(
                symbol=_clean_symbol(symbol),
                base=_clean_symbol(symbol).removesuffix("USDT"),
                quote="USDT",
                exchange="configured",
            )
            for symbol in settings.SYMBOLS
        ]

    async def get_dataframe(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        openbb_provider: str = "yfinance",
        openbb_fallback_providers: Optional[List[str]] = None,
        allow_ccxt_fallback: bool = True,
        fallback_exchange: str = "okx",
        allow_binance_fallback: bool = False,
    ) -> pd.DataFrame:
        klines = await self.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start,
            end_time=end,
            openbb_provider=openbb_provider,
            openbb_fallback_providers=openbb_fallback_providers,
            allow_ccxt_fallback=allow_ccxt_fallback,
            fallback_exchange=fallback_exchange,
            allow_binance_fallback=allow_binance_fallback,
        )
        if not klines:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(
            [
                {
                    "timestamp": k.timestamp,
                    "open": k.open,
                    "high": k.high,
                    "low": k.low,
                    "close": k.close,
                    "volume": k.volume,
                }
                for k in klines
            ]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        return df.sort_index()

    async def persist_bars(self, symbol: str, interval: str, bars: List[BarData]) -> int:
        if not bars:
            return 0
        from app.services.clickhouse_service import clickhouse_service

        rows = [
            {
                "open_time": bar.datetime,
                "instrument_id": bar.instrument_id or _clean_symbol(symbol),
                "exchange": bar.exchange,
                "provider": bar.provider,
                "source_version": bar.source_version or "openbb-sdk",
                "schema_version": bar.schema_version,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "close_time": bar.bar_end_time or bar.datetime,
                "available_time": bar.available_time,
                "vwap": bar.vwap,
                "volume_notional": bar.volume_notional,
                "transactions": bar.transactions,
            }
            for bar in bars
        ]
        legacy_written = await clickhouse_service.insert_klines(_clean_symbol(symbol), interval, rows)
        source_written = await clickhouse_service.insert_market_bars(
            _clean_symbol(symbol),
            interval,
            rows,
            provider=rows[0].get("provider") or "openbb",
            exchange=rows[0].get("exchange") or "openbb",
            source_version=rows[0].get("source_version") or "openbb-sdk",
        )
        return legacy_written or source_written

    async def _get_local_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> List[KlineData]:
        try:
            from app.services.clickhouse_service import clickhouse_service

            if start_time is None:
                total_rows = await clickhouse_service.get_bar_count(
                    symbol,
                    interval,
                    start_time=None,
                    end_time=end_time,
                )
                query_offset = max(total_rows - limit, 0)
            else:
                query_offset = 0

            rows = await clickhouse_service.query_klines(
                symbol=symbol,
                interval=interval,
                start=start_time,
                end=end_time,
                limit=limit,
                offset=query_offset,
            )
            klines = [_row_to_kline(row) for row in rows]
            by_time = {_as_utc(kline.timestamp): kline for kline in klines}
            return [by_time[ts] for ts in sorted(by_time.keys())][-limit:]
        except Exception as exc:
            logger.debug("Local kline query failed for %s/%s: %s", symbol, interval, exc)
            return []

    async def _get_local_ticker(self, symbol: str) -> Optional[TickerData]:
        klines = await self._get_local_klines(
            symbol=symbol,
            interval="1h",
            limit=25,
            start_time=None,
            end_time=None,
        )
        if not klines:
            return None
        latest = klines[-1]
        prev = klines[0] if len(klines) > 1 else latest
        change = latest.close - prev.close
        pct = (change / prev.close * 100) if prev.close else 0.0
        high = max(k.high for k in klines)
        low = min(k.low for k in klines)
        volume = sum(k.volume for k in klines)
        return TickerData(
            symbol=symbol,
            price=latest.close,
            change_24h=change,
            change_percent=pct,
            volume=volume,
            high_24h=high,
            low_24h=low,
            timestamp=latest.timestamp,
        )

    async def backfill_range(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: Optional[datetime] = None,
        limit: int = 1000,
        provider: str = "yfinance",
        fallback_providers: Optional[List[str]] = None,
    ) -> int:
        end = end or datetime.now(timezone.utc)
        bars = await self.get_openbb_bars(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=_as_utc(start),
            end_time=_as_utc(end),
            provider=provider,
            fallback_providers=fallback_providers,
            persist=True,
        )
        return len(bars)


market_data_gateway = MarketDataGateway()
