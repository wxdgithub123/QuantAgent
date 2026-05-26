"""
Instrument Model — Unified symbol representation (L3)

A single canonical representation for trading instruments,
replacing ad-hoc string parsing scattered across services.
"""

from __future__ import annotations

from enum import Enum
from typing import ClassVar, Optional, Set

from pydantic import BaseModel


class InstrumentType(str, Enum):
    SPOT = "spot"
    PERPETUAL = "perpetual"
    FUTURE = "future"


class Instrument(BaseModel):
    """Canonical instrument/symbol model for all services and layers."""

    # ── Common stablecoins that map to USD ──────────────────────────────────
    USD_STABLECOINS: ClassVar[Set[str]] = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "USD"}

    symbol: str = ""  # Canonical raw form: "BTCUSDT"
    base_asset: str = ""  # "BTC"
    quote_asset: str = ""  # "USDT"
    exchange: str = "binance"
    instrument_type: InstrumentType = InstrumentType.SPOT
    tick_size: Optional[float] = None  # Minimum price increment
    lot_size: Optional[float] = None  # Minimum quantity increment
    min_notional: Optional[float] = None  # Minimum order notional value

    @classmethod
    def from_ccxt(cls, ccxt_symbol: str, exchange: str = "binance") -> "Instrument":
        """Parse CCXT format (BTC/USDT) to Instrument."""
        if "/" in ccxt_symbol:
            base, quote = ccxt_symbol.split("/", 1)
        else:
            base, quote = ccxt_symbol, "USDT"
        return cls(
            symbol=f"{base}{quote}",
            base_asset=base.upper(),
            quote_asset=quote.upper(),
            exchange=exchange,
        )

    @classmethod
    def from_raw(cls, raw: str, exchange: str = "binance") -> "Instrument":
        """Parse raw symbol (BTCUSDT or BTC/USDT) to Instrument.

        Handles edge cases like BTC-USD, BTCUSD, BTC/USD, etc.
        """
        raw = raw.strip().upper()
        if "/" in raw:
            return cls.from_ccxt(raw, exchange)
        if "-" in raw:
            base, quote = raw.split("-", 1)
            if quote == "USD":
                quote = "USDT"
            return cls(
                symbol=f"{base}{quote}",
                base_asset=base,
                quote_asset=quote,
                exchange=exchange,
            )

        # Heuristic: find quote asset by checking known suffixes
        known_quotes = ["USDT", "USDC", "BUSD", "BTC", "ETH", "DAI", "TUSD", "USD"]
        for q in sorted(known_quotes, key=len, reverse=True):
            if raw.endswith(q) and len(raw) > len(q):
                base = raw[: -len(q)]
                return cls(
                    symbol=raw,
                    base_asset=base,
                    quote_asset=q,
                    exchange=exchange,
                )

        # Fallback: assume USDT quote
        return cls(symbol=raw, base_asset=raw, quote_asset="USDT", exchange=exchange)

    @property
    def ccxt_symbol(self) -> str:
        """Return CCXT format: BTC/USDT"""
        return f"{self.base_asset}/{self.quote_asset}"

    @property
    def hyphen_symbol(self) -> str:
        """Return hyphen format for OpenBB: BTC-USD"""
        quote = "USD" if self.quote_asset.upper() in self.USD_STABLECOINS else self.quote_asset
        return f"{self.base_asset.upper()}-{quote.upper()}"
