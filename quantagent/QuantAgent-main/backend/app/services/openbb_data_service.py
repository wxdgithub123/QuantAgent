"""
OpenBB Unified Data Service (L1-L2)

Wraps the OpenBB SDK to provide a single unified interface for:
  - Crypto historical OHLCV   (replaces binance_service REST queries)
  - Crypto ticker / price      (replaces binance_service.get_ticker/get_price)
  - Crypto symbol search       (replaces coingecko_service search)
  - FRED economic indicators   (replaces macro_analysis_service random data)

The OpenBB SDK is lazily loaded. If it's not installed, the service reports
`available = False` and callers should fall back to the existing services.

CoinGeckoService is fully superseded by this module and can be deprecated.
BinanceService remains only for exchange-specific surfaces such as websocket
streaming and order book access.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from app.models.market_data import TickerData, SymbolInfo
from app.pipeline.models import MacroSnapshot, NewsArticle
from app.models.trading import BarData
from app.services.news_enrichment_service import news_enrichment_service

logger = logging.getLogger(__name__)

# ── Lazy import of OpenBB ──────────────────────────────────────────────────────

_obb = None
_OPENBB_AVAILABLE = False


def _try_import_openbb() -> bool:
    """Attempt to import the OpenBB SDK. Returns True on success."""
    global _obb, _OPENBB_AVAILABLE
    if _obb is not None:
        return _OPENBB_AVAILABLE
    try:
        from openbb import obb as _obb_module

        _obb = _obb_module
        _OPENBB_AVAILABLE = True
        logger.info("OpenBB SDK loaded successfully")
        return True
    except ImportError:
        _OPENBB_AVAILABLE = False
        logger.warning(
            "OpenBB SDK not installed. Install with: pip install openbb[crypto,economy]\n"
            "Falling back to existing market data services."
        )
        return False


# ── Symbol normalization helpers ────────────────────────────────────────────────

# CCXT format:  "BTC/USDT"   →  OpenBB format: "BTC-USD"  (for yfinance/fmp/tiingo)
# Our internal: "BTCUSDT"    →  OpenBB format: "BTC-USD"

_USD_STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD"}


def _to_openbb_symbol(symbol: str) -> str:
    """Convert internal symbol (BTCUSDT) or CCXT symbol (BTC/USDT) to OpenBB format (BTC-USD)."""
    if "/" in symbol:
        base, quote = symbol.split("/", 1)
    else:
        # Heuristic: find where quote asset starts (usually after 3-4 chars)
        known_quotes = ["USDT", "USDC", "BUSD", "BTC", "ETH", "DAI", "TUSD", "USD"]
        base, quote = symbol, "USDT"
        for q in sorted(known_quotes, key=len, reverse=True):
            if symbol.endswith(q) and len(symbol) > len(q):
                base = symbol[: -len(q)]
                quote = q
                break

    if quote.upper() in _USD_STABLECOINS:
        quote = "USD"
    return f"{base.upper()}-{quote.upper()}"


def _from_openbb_symbol(obb_symbol: str) -> str:
    """Convert OpenBB symbol (BTC-USD) back to internal format (BTCUSDT)."""
    if "-" in obb_symbol:
        base, quote = obb_symbol.split("-", 1)
        if quote.upper() == "USD":
            quote = "USDT"
        return f"{base.upper()}{quote.upper()}"
    return obb_symbol


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _aggregate_hourly_bars(
    bars: List[BarData],
    target_interval: str,
    hours: int,
    limit: int,
) -> List[BarData]:
    """Aggregate provider-supported 1h bars into larger fixed-hour bars."""
    if not bars:
        return []

    buckets: Dict[datetime, List[BarData]] = {}
    for bar in sorted(bars, key=lambda b: _as_utc(b.datetime)):
        ts = _as_utc(bar.datetime)
        bucket_start = ts.replace(hour=(ts.hour // hours) * hours, minute=0, second=0, microsecond=0)
        buckets.setdefault(bucket_start, []).append(bar)

    aggregated: List[BarData] = []
    for bucket_start, group in sorted(buckets.items()):
        if not group:
            continue
        open_bar = group[0]
        close_bar = group[-1]
        volume = sum(float(b.volume or 0.0) for b in group)
        volume_notional = None
        if any(b.volume_notional is not None for b in group):
            volume_notional = sum(float(b.volume_notional or 0.0) for b in group)
        transactions = None
        if any(b.transactions is not None for b in group):
            transactions = sum(int(b.transactions or 0) for b in group)
        aggregated.append(
            BarData(
                symbol=open_bar.symbol,
                instrument_id=open_bar.instrument_id,
                exchange=open_bar.exchange,
                provider=f"{open_bar.provider}:aggregated-{target_interval}",
                source_version=open_bar.source_version,
                schema_version=open_bar.schema_version,
                datetime=bucket_start,
                bar_start_time=bucket_start,
                bar_end_time=bucket_start + timedelta(hours=hours),
                event_time=bucket_start,
                available_time=datetime.now(timezone.utc),
                open=float(open_bar.open),
                high=max(float(b.high) for b in group),
                low=min(float(b.low) for b in group),
                close=float(close_bar.close),
                volume=volume,
                volume_notional=volume_notional,
                transactions=transactions,
                interval=target_interval,
                timeframe=target_interval,
            )
        )

    return aggregated[-limit:] if len(aggregated) > limit else aggregated


# ── Service class ──────────────────────────────────────────────────────────────


class OpenBBDataService:
    """Unified data service wrapping the OpenBB SDK.

    Provides crypto/equity historical, ticker, price, news, and FRED economic data
    through a single interface.  Singleton — use ``get_instance()``.
    """

    _instance: Optional["OpenBBDataService"] = None

    @classmethod
    def get_instance(cls) -> "OpenBBDataService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._initialized = False
        self._fred_api_key: Optional[str] = None

    @property
    def available(self) -> bool:
        return _try_import_openbb()

    async def ensure_initialized(self) -> bool:
        """Lazy-load OpenBB and configure credentials. Returns True if ready."""
        if self._initialized:
            return _OPENBB_AVAILABLE
        ok = _try_import_openbb()
        if ok:
            try:
                from app.core.config import settings

                # yfinance is the default free provider (no API key needed)
                # For fmp or tiingo, set OPENBB_FMP_API_KEY / OPENBB_TIINGO_API_KEY

                # FRED key for economic data
                fred_key = os.environ.get("OPENBB_FRED_API_KEY", "")
                if fred_key:
                    _obb.user.credentials.fred_api_key = fred_key

            except Exception as e:
                logger.warning(f"OpenBB credential setup failed: {e}")
        self._initialized = True
        return _OPENBB_AVAILABLE

    # ── Provider helpers ───────────────────────────────────────────────────

    def _provider_chain(self, provider: str, fallbacks: Optional[List[str]] = None) -> List[str]:
        chain = [p.strip() for p in [provider, *(fallbacks or [])] if p and p.strip()]
        deduped: List[str] = []
        for p in chain:
            if p not in deduped:
                deduped.append(p)
        return deduped or ["yfinance"]

    # ── Crypto historical (replaces direct exchange REST kline queries) ───────

    async def get_crypto_historical(
        self,
        symbol: str,
        interval: str = "1h",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
        provider: str = "yfinance",
        fallback_providers: Optional[List[str]] = None,
    ) -> List[BarData]:
        """Fetch OHLCV bars via OpenBB crypto price historical.

        Returns ``List[BarData]`` — the same type the strategy bus expects.
        If OpenBB is unavailable, returns an empty list (caller should fall back).
        """
        if not await self.ensure_initialized():
            return []

        for candidate in self._provider_chain(provider, fallback_providers):
            bars = await self._get_crypto_historical_once(
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
                limit=limit,
                provider=candidate,
            )
            if bars:
                return bars
        return []

    async def _get_crypto_historical_once(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime],
        end: Optional[datetime],
        limit: int,
        provider: str,
    ) -> List[BarData]:
        if interval == "4h":
            hourly_limit = max(limit * 4 + 8, limit)
            hourly_bars = await self._get_crypto_historical_once(
                symbol=symbol,
                interval="1h",
                start=start,
                end=end,
                limit=hourly_limit,
                provider=provider,
            )
            return _aggregate_hourly_bars(hourly_bars, target_interval="4h", hours=4, limit=limit)

        obb_symbol = _to_openbb_symbol(symbol)
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "1d": "1d", "1w": "1w",
        }
        obb_interval = interval_map.get(interval, "1h")

        kwargs: Dict[str, Any] = {
            "symbol": obb_symbol,
            "interval": obb_interval,
            "provider": provider,
        }
        if start:
            kwargs["start_date"] = start.strftime("%Y-%m-%d")
        if end:
            kwargs["end_date"] = end.strftime("%Y-%m-%d")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _obb.crypto.price.historical(**kwargs),
            )
        except Exception as e:
            logger.error(f"OpenBB crypto.historical({symbol}) failed: {e}")
            return []

        if result is None:
            return []

        df = result.to_dataframe() if hasattr(result, "to_dataframe") else result
        if df is None or df.empty:
            return []

        bars = []
        ingested_at = datetime.utcnow()
        for idx, row in df.iterrows():
            ts = idx if isinstance(idx, datetime) else pd.Timestamp(idx).to_pydatetime()
            bars.append(
                BarData(
                    symbol=symbol,
                    instrument_id=symbol,
                    exchange=provider,
                    provider=f"openbb:{provider}",
                    source_version="openbb-sdk",
                    schema_version="bar.v1",
                    datetime=ts,
                    bar_start_time=ts,
                    bar_end_time=ts,
                    event_time=ts,
                    available_time=ingested_at,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                    vwap=float(row["vwap"]) if "vwap" in row and pd.notna(row["vwap"]) else None,
                    volume_notional=float(row["volume_notional"]) if "volume_notional" in row and pd.notna(row["volume_notional"]) else None,
                    transactions=int(row["transactions"]) if "transactions" in row and pd.notna(row["transactions"]) else None,
                    interval=interval,
                    timeframe=interval,
                )
            )
        return bars[-limit:] if len(bars) > limit else bars

    # ── Equity historical / ticker ─────────────────────────────────────────

    async def get_equity_historical(
        self,
        symbol: str,
        interval: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
        provider: str = "yfinance",
        fallback_providers: Optional[List[str]] = None,
    ) -> List[BarData]:
        """Fetch stock/equity OHLCV bars via OpenBB with provider fallback."""
        if not await self.ensure_initialized():
            return []

        for candidate in self._provider_chain(provider, fallback_providers):
            try:
                kwargs: Dict[str, Any] = {"symbol": symbol.upper(), "provider": candidate}
                if start:
                    kwargs["start_date"] = start.strftime("%Y-%m-%d")
                if end:
                    kwargs["end_date"] = end.strftime("%Y-%m-%d")
                if interval:
                    kwargs["interval"] = interval

                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: _obb.equity.price.historical(**kwargs),
                )
                df = result.to_dataframe() if hasattr(result, "to_dataframe") else result
                if df is None or df.empty:
                    continue

                ingested_at = datetime.utcnow()
                bars: List[BarData] = []
                for idx, row in df.iterrows():
                    ts = idx if isinstance(idx, datetime) else pd.Timestamp(idx).to_pydatetime()
                    bars.append(
                        BarData(
                            symbol=symbol.upper(),
                            instrument_id=symbol.upper(),
                            exchange=candidate,
                            provider=f"openbb:{candidate}",
                            source_version="openbb-sdk",
                            schema_version="bar.v1",
                            datetime=ts,
                            bar_start_time=ts,
                            bar_end_time=ts,
                            event_time=ts,
                            available_time=ingested_at,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row.get("volume", 0.0)),
                            vwap=float(row["vwap"]) if "vwap" in row and pd.notna(row["vwap"]) else None,
                            volume_notional=float(row["volume_notional"]) if "volume_notional" in row and pd.notna(row["volume_notional"]) else None,
                            transactions=int(row["transactions"]) if "transactions" in row and pd.notna(row["transactions"]) else None,
                            interval=interval,
                            timeframe=interval,
                        )
                    )
                if bars:
                    return bars[-limit:] if len(bars) > limit else bars
            except Exception as e:
                logger.debug(f"OpenBB equity.historical({symbol}, provider={candidate}) failed: {e}")
        return []

    async def get_equity_ticker(
        self, symbol: str, provider: str = "yfinance", fallback_providers: Optional[List[str]] = None
    ) -> Optional[TickerData]:
        """Fetch stock/equity latest price via OpenBB with provider fallback."""
        bars = await self.get_equity_historical(
            symbol=symbol,
            interval="1d",
            limit=2,
            provider=provider,
            fallback_providers=fallback_providers,
        )
        if not bars:
            return None
        latest = bars[-1]
        prev = bars[-2] if len(bars) > 1 else None
        change = latest.close - prev.close if prev else 0.0
        pct = (change / prev.close * 100) if prev and prev.close else 0.0
        return TickerData(
            symbol=symbol.upper(),
            price=latest.close,
            change_24h=change,
            change_percent=pct,
            volume=latest.volume,
            high_24h=latest.high,
            low_24h=latest.low,
            timestamp=latest.available_time or datetime.utcnow(),
        )

    # ── Crypto ticker / price (replaces direct exchange REST ticker queries) ──

    async def get_crypto_ticker(
        self, symbol: str, provider: str = "yfinance", fallback_providers: Optional[List[str]] = None
    ) -> Optional[TickerData]:
        """Fetch current ticker via OpenBB."""
        if not await self.ensure_initialized():
            return None

        obb_symbol = _to_openbb_symbol(symbol)
        for candidate in self._provider_chain(provider, fallback_providers):
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda p=candidate: _obb.crypto.price.historical(
                        symbol=obb_symbol, interval="1d", provider=p
                    ),
                )
                df = result.to_dataframe() if hasattr(result, "to_dataframe") else result
                if df is None or df.empty:
                    continue
                row = df.iloc[-1]
                return TickerData(
                    symbol=symbol,
                    price=float(row["close"]),
                    change_24h=0.0,
                    change_percent=0.0,
                    volume=float(row.get("volume", 0.0)),
                    high_24h=float(row.get("high", row["close"])),
                    low_24h=float(row.get("low", row["close"])),
                    timestamp=datetime.utcnow(),
                )
            except Exception as e:
                logger.debug(f"OpenBB ticker({symbol}, provider={candidate}) failed: {e}")
        return None

    async def get_crypto_price(
        self, symbol: str, provider: str = "yfinance", fallback_providers: Optional[List[str]] = None
    ) -> Optional[float]:
        """Fetch current price. Returns None on failure so callers can fall back."""
        ticker = await self.get_crypto_ticker(symbol, provider, fallback_providers)
        return ticker.price if ticker else None

    # ── News ───────────────────────────────────────────────────────────────

    async def get_news(
        self,
        symbol: str,
        limit: int = 20,
        provider: str = "yfinance",
        fallback_providers: Optional[List[str]] = None,
    ) -> List[NewsArticle]:
        """Fetch and normalize news via OpenBB provider chain."""
        if not await self.ensure_initialized():
            return []

        for candidate in self._provider_chain(provider, fallback_providers):
            try:
                ticker = _to_openbb_symbol(symbol) if symbol.upper().endswith(("USDT", "USD")) else symbol.upper()
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda p=candidate: _obb.news.company(symbol=ticker, limit=limit, provider=p),
                )
                if result is None or not getattr(result, "results", None):
                    continue
                now = datetime.utcnow()
                articles: List[NewsArticle] = []
                for item in result.results:
                    url = getattr(item, "url", "") or ""
                    title = getattr(item, "title", "") or ""
                    summary = getattr(item, "summary", "") or ""
                    pub_date = getattr(item, "date", None)
                    payload_id = hashlib.sha256(f"{url}|{title}".encode("utf-8")).hexdigest()
                    articles.append(
                        NewsArticle(
                            title=title,
                            source=getattr(item, "source", "") or candidate,
                            url=url,
                            summary=summary,
                            body=summary,
                            excerpt=summary[:300] or title[:300],
                            language="en",
                            published_at=pub_date if isinstance(pub_date, datetime) else now,
                            symbols=[symbol.upper()],
                            ingested_at=now,
                            provider=f"openbb:{candidate}",
                            source_version="openbb-sdk",
                            raw_payload_id=payload_id,
                        )
                    )
                if articles:
                    return news_enrichment_service.enrich_many(articles, requested_symbols=[symbol.upper()])
            except Exception as e:
                logger.debug(f"OpenBB news({symbol}, provider={candidate}) failed: {e}")
        return []

    # ── Symbol search ────────────────────────────────────────────────────────

    async def get_crypto_search(
        self, query: str, provider: str = "yfinance"
    ) -> List[SymbolInfo]:
        """Search for tradeable symbols."""
        if not await self.ensure_initialized():
            return []

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _obb.crypto.search(query, provider=provider),
            )
        except Exception as e:
            logger.error(f"OpenBB crypto.search({query}) failed: {e}")
            return []

        if result is None:
            return []

        df = result.to_dataframe() if hasattr(result, "to_dataframe") else result
        if df is None or df.empty:
            return []

        results = []
        for _, row in df.iterrows():
            raw_sym = _from_openbb_symbol(row.get("symbol", ""))
            if not raw_sym:
                continue
            results.append(
                SymbolInfo(
                    symbol=raw_sym,
                    base=raw_sym[:-4] if raw_sym.endswith("USDT") else raw_sym,
                    quote="USDT" if raw_sym.endswith("USDT") else "USD",
                    exchange=row.get("exchange", "unknown"),
                )
            )
        return results

    # ── FRED economic data (replaces random macro data) ──────────────────────

    async def get_economic_indicator(
        self,
        series_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        provider: str = "fred",
    ) -> Optional[pd.DataFrame]:
        """Fetch a FRED economic series via OpenBB economy module.

        Common series IDs:
          - FEDFUNDS  — Federal Funds Rate
          - DGS10     — 10-Year Treasury Yield
          - T10YIE    — 10-Year Breakeven Inflation Rate
          - M2SL      — M2 Money Supply (monthly)
          - DFF       — Federal Funds Rate (daily)
        """
        if not await self.ensure_initialized():
            return None

        kwargs: Dict[str, Any] = {"symbol": series_id}
        if provider:
            kwargs["provider"] = provider
        if start:
            kwargs["start_date"] = start.strftime("%Y-%m-%d")
        if end:
            kwargs["end_date"] = end.strftime("%Y-%m-%d")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _obb.economy.fred_series(**kwargs),
            )
        except Exception as e:
            logger.debug(f"OpenBB FRED series({series_id}) failed: {e}")
            return None

        if result is None:
            return None

        df = result.to_dataframe() if hasattr(result, "to_dataframe") else result
        return df if df is not None and not df.empty else None

    async def get_macro_events(
        self,
        series_map: Optional[Dict[str, str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        provider: str = "fred",
        fallback_providers: Optional[List[str]] = None,
    ) -> List[MacroSnapshot]:
        """Fetch macro series and normalize them into MacroEvent objects."""
        default_series = {
            "fed_funds_rate": "FEDFUNDS",
            "treasury_10y": "DGS10",
            "inflation_expect": "T10YIE",
            "m2_money_supply": "M2SL",
            "cpi": "CPIAUCSL",
            "core_cpi": "CPILFESL",
            "gdp": "GDP",
            "unemployment": "UNRATE",
            "retail_sales": "RSAFS",
            "industrial_production": "INDPRO",
            "consumer_sentiment": "UMCSENT",
        }
        series_map = series_map or default_series
        if not await self.ensure_initialized():
            return []

        events: List[MacroSnapshot] = []
        ingested_at = datetime.utcnow()
        for indicator, series_id in series_map.items():
            for candidate in self._provider_chain(provider, fallback_providers):
                if candidate != "fred":
                    continue
                df = await self.get_economic_indicator(
                    series_id=series_id,
                    start=start,
                    end=end,
                    provider=candidate,
                )
                if df is None or df.empty:
                    continue
                value_col = series_id if series_id in df.columns else None
                if value_col is None:
                    numeric_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
                    value_col = numeric_cols[0] if numeric_cols else df.columns[-1]
                for idx, row in df.iterrows():
                    value = row.get(value_col)
                    if pd.isna(value):
                        continue
                    ts = idx if isinstance(idx, datetime) else pd.Timestamp(idx).to_pydatetime()
                    events.append(
                        MacroSnapshot(
                            indicator=indicator,
                            value=float(value),
                            source=candidate,
                            timestamp=ts,
                            event_time=ts,
                            available_time=ingested_at,
                            provider=f"openbb:{candidate}",
                            source_version="openbb-sdk",
                            metadata={"series_id": series_id},
                        )
                    )
                if events:
                    break
        return events


# ── Module-level singleton ─────────────────────────────────────────────────────

openbb_data_service = OpenBBDataService.get_instance()
