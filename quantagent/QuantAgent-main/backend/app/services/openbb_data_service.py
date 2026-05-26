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
BinanceService is retained for WebSocket streaming only.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from app.models.market_data import TickerData, SymbolInfo
from app.models.trading import BarData

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
            "Falling back to BinanceService + CoinGeckoService for data access."
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


# ── Service class ──────────────────────────────────────────────────────────────


class OpenBBDataService:
    """Unified data service wrapping the OpenBB SDK.

    Provides crypto historical, ticker, price, and FRED economic data
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

    # ── Crypto historical (replaces binance_service.get_klines) ─────────────

    async def get_crypto_historical(
        self,
        symbol: str,
        interval: str = "1h",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
        provider: str = "yfinance",
    ) -> List[BarData]:
        """Fetch OHLCV bars via OpenBB crypto price historical.

        Returns ``List[BarData]`` — the same type the strategy bus expects.
        If OpenBB is unavailable, returns an empty list (caller should fall back).
        """
        if not await self.ensure_initialized():
            return []

        obb_symbol = _to_openbb_symbol(symbol)
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
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
        for idx, row in df.iterrows():
            ts = idx if isinstance(idx, datetime) else pd.Timestamp(idx).to_pydatetime()
            bars.append(
                BarData(
                    symbol=symbol,
                    datetime=ts,
                    event_time=ts,
                    available_time=datetime.utcnow(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                    interval=interval,
                )
            )
        return bars[-limit:] if len(bars) > limit else bars

    # ── Crypto ticker / price (replaces binance_service.get_ticker/get_price) ──

    async def get_crypto_ticker(
        self, symbol: str, provider: str = "yfinance"
    ) -> Optional[TickerData]:
        """Fetch current ticker via OpenBB."""
        if not await self.ensure_initialized():
            return None

        obb_symbol = _to_openbb_symbol(symbol)
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _obb.crypto.price.historical(
                    obb_symbol, interval="1d", limit=1, provider=provider
                ),
            )
        except Exception as e:
            logger.error(f"OpenBB ticker({symbol}) failed: {e}")
            return None

        if result is None:
            return None

        df = result.to_dataframe() if hasattr(result, "to_dataframe") else result
        if df is None or df.empty:
            return None

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

    async def get_crypto_price(
        self, symbol: str, provider: str = "yfinance"
    ) -> Optional[float]:
        """Fetch current price. Returns None on failure so callers can fall back."""
        ticker = await self.get_crypto_ticker(symbol, provider)
        return ticker.price if ticker else None

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


# ── Module-level singleton ─────────────────────────────────────────────────────

openbb_data_service = OpenBBDataService.get_instance()
