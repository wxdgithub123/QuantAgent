"""Standard AnalysisContext consumed by L6 agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnalysisContext(BaseModel):
    """Point-in-time context assembled from standardized platform objects."""

    instrument_id: str
    symbol: str
    timeframe: str
    as_of_time: datetime
    schema_version: str = "analysis_context.v1"
    bars: List[Dict[str, Any]] = Field(default_factory=list)
    latest_factors: Dict[str, float] = Field(default_factory=dict)
    recent_signals: List[Dict[str, Any]] = Field(default_factory=list)
    macro_events: List[Dict[str, Any]] = Field(default_factory=list)
    news_events: List[Dict[str, Any]] = Field(default_factory=list)
    data_versions: Dict[str, Any] = Field(default_factory=dict)
    input_snapshot_ids: Dict[str, List[Any]] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_agent_payload(self) -> Dict[str, Any]:
        """Return a plain dict suitable for TradingAgents/CoordinatorAgent."""
        return self.model_dump(mode="json")
