"""
Signal & Factor Models (L5)

FactorSnapshot — persisted factor/indicator value at a point in time
SignalEvent   — persisted trading signal consumed by L6 decision layer
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class FactorSnapshot(BaseModel):
    """Persisted snapshot of a computed factor value at a point in time.

    Enables reproducibility of signal generation and factor backtesting.
    """

    symbol: str
    timestamp: datetime
    factor_name: str  # e.g. "sma_10", "rsi_14", "macd_dif"
    factor_value: float
    parameters: Dict[str, Any] = Field(default_factory=dict)  # e.g. {"period": 10}
    source: str = "indicators"  # "indicators", "macro", "custom"


class SignalEvent(BaseModel):
    """Persisted trading signal generated from factor analysis.

    Consumed by the L6 decision layer (CoordinatorAgent / TradingAgents).
    Previously signals were computed in-memory and immediately discarded.
    """

    symbol: str
    timestamp: datetime
    signal_type: str  # "BUY", "SELL", "WAIT", "LONG_REVERSAL", "SHORT_REVERSAL"
    signal_value: float = 0.0  # -1.0 to 1.0 (directional strength)
    confidence: float = 0.5  # 0.0 to 1.0
    source_strategy: str = ""  # e.g. "ma", "rsi", "boll", "trend_agent"
    strategy_id: str = ""  # database ID of the generating strategy
    factors: Dict[str, float] = Field(default_factory=dict)
    extra_data: Dict[str, Any] = Field(default_factory=dict)
