"""Standard AnalysisContext consumed by L6 agents."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _json_safe(value: Any) -> Any:
    """Recursively convert numpy/pandas/DB values into JSON-safe primitives."""
    if value is None:
        return None
    try:
        if value != value:
            return None
    except Exception:
        pass
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    return str(value)


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
        return _json_safe(self.model_dump(mode="python"))
