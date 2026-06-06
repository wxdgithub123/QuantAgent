"""Helpers for point-in-time replay/backtest reproducibility metadata."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


PIT_SCHEMA_VERSION = "pit-repro-v1"
BACKTEST_ENGINE_VERSION = "event-driven-backtester-v1"
STRATEGY_TEMPLATE_VERSION = "strategy-templates-v1"


def stable_json(value: Any) -> str:
    return json.dumps(value or {}, sort_keys=True, default=str)


def stable_params_hash(params: Optional[Dict[str, Any]]) -> str:
    return hashlib.sha256(stable_json(params or {}).encode()).hexdigest()


def short_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode()).hexdigest()


def source_layer(data_source: str) -> str:
    if data_source.startswith("clickhouse"):
        return "local_cache"
    if data_source.startswith("market_data_gateway"):
        return "data_gateway"
    return "unknown"


def enrich_pit_metadata(
    pit: Dict[str, Any],
    *,
    symbol: str,
    interval: str,
    strategy_type: str,
    params: Optional[Dict[str, Any]],
    params_hash: Optional[str],
    data_source: str,
    replay_session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach stable IDs needed to reproduce a PIT backtest later."""
    normalized_params_hash = params_hash or stable_params_hash(params)
    snapshot_payload = {
        "symbol": symbol.upper(),
        "interval": interval,
        "data_source": data_source,
        "actual_start_time": pit.get("actual_start_time"),
        "actual_end_time": pit.get("actual_end_time"),
        "row_count": pit.get("row_count"),
    }
    source_snapshot_id = short_hash(snapshot_payload)
    enriched = dict(pit)
    enriched.update(
        {
            "schema_version": PIT_SCHEMA_VERSION,
            "source_snapshot_id": source_snapshot_id,
            "data_snapshot_id": source_snapshot_id,
            "source_layer": source_layer(data_source),
            "params_hash": normalized_params_hash,
            "strategy_version": f"{strategy_type}:{STRATEGY_TEMPLATE_VERSION}",
            "engine_version": BACKTEST_ENGINE_VERSION,
            "reproducibility_level": "windowed_ohlcv_with_replay"
            if replay_session_id
            else "windowed_ohlcv",
            "replay_session_id": replay_session_id or pit.get("replay_session_id"),
            "upstream_note": "This records the local read layer and deterministic data window. It does not prove the original upstream exchange/provider unless that upstream is separately captured.",
        }
    )
    return enriched
