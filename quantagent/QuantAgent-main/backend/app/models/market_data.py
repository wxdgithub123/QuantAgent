"""
Market Data Models
"""

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class TickerData(BaseModel):
    """Ticker/Price data model"""
    symbol: str
    price: float
    change_24h: float
    change_percent: float
    volume: float
    high_24h: float
    low_24h: float
    timestamp: datetime


class KlineData(BaseModel):
    """Raw K-line data from exchange APIs.

    DEPRECATED for internal use — prefer ``BarData`` from ``app.models.trading``
    which has three-time semantics.  Use ``to_bar_data()`` to convert.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: Optional[datetime] = None
    quote_volume: Optional[float] = None
    trades: Optional[int] = None

    def to_bar_data(
        self,
        symbol: str,
        interval: str,
        provider: str = "unknown",
        exchange: str = "unknown",
        source_version: Optional[str] = None,
        instrument_id: Optional[str] = None,
        available_time: Optional[datetime] = None,
    ) -> "BarData":
        """Convert raw exchange K-line data into the canonical BarData model."""
        from app.models.trading import BarData

        ingested_at = available_time or datetime.utcnow()
        return BarData(
            symbol=symbol,
            instrument_id=instrument_id or symbol,
            exchange=exchange,
            provider=provider,
            source_version=source_version,
            schema_version="bar.v1",
            datetime=self.timestamp,
            bar_start_time=self.timestamp,
            bar_end_time=self.close_time or self.timestamp,
            event_time=self.timestamp,
            available_time=ingested_at,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            volume_notional=self.quote_volume,
            transactions=self.trades,
            quote_volume=self.quote_volume,
            trades=self.trades,
            interval=interval,
            timeframe=interval,
        )


class KlineResponse(BaseModel):
    """Kline response model"""
    symbol: str
    interval: str
    data: List[KlineData]
    source: str


class SymbolInfo(BaseModel):
    """Trading symbol information"""
    symbol: str
    base: str
    quote: str
    exchange: str


class MarketOverview(BaseModel):
    """Market overview data from CoinGecko"""
    id: str
    symbol: str
    name: str
    current_price: float
    market_cap: Optional[float] = None
    market_cap_rank: Optional[int] = None
    price_change_24h: Optional[float] = None
    price_change_percentage_24h: Optional[float] = None
    total_volume: Optional[float] = None
    last_updated: Optional[datetime] = None


class PriceComparison(BaseModel):
    """Price comparison between exchanges"""
    symbol: str
    binance_price: Optional[float] = None
    coingecko_price: Optional[float] = None
    price_diff: Optional[float] = None
    price_diff_percent: Optional[float] = None
    timestamp: datetime
