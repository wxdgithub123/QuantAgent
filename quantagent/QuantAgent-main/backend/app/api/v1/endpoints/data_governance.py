"""Phase 2 data governance endpoints.

These endpoints make data-source configuration, preview, cleaning-rule
versions, lineage, and data-quality evidence visible without duplicating the
OpenBB/local-storage pipeline.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
GOVERNANCE_FILE = CONFIG_DIR / "phase2_data_governance.json"

DEFAULT_GOVERNANCE: Dict[str, Any] = {
    "schema_version": "data_governance.v1",
    "cleaning_rules": [
        {
            "rule_id": "bar_null_standardization.v1",
            "data_type": "bar",
            "enabled": True,
            "version": 1,
            "description": "Standardize empty numeric fields to null before canonical bar validation.",
            "changed_data_store": "data/governance/changed_items",
        },
        {
            "rule_id": "bar_outlier_flag.v1",
            "data_type": "bar",
            "enabled": True,
            "version": 1,
            "description": "Flag high/low/close outliers for review instead of silently deleting them.",
            "changed_data_store": "data/governance/changed_items",
        },
        {
            "rule_id": "news_symbol_enrichment.v1",
            "data_type": "news",
            "enabled": True,
            "version": 1,
            "description": "Persist extracted symbols/topics/tags as versioned enrichment metadata.",
            "changed_data_store": "DuckDB news_articles metadata/raw_payload_id",
        },
        {
            "rule_id": "macro_available_time.v1",
            "data_type": "macro",
            "enabled": True,
            "version": 1,
            "description": "Use available_time for PIT visibility and never observation timestamp alone.",
            "changed_data_store": "DuckDB macro_indicators available_time",
        },
    ],
    "quality_thresholds": {
        "max_missing_rate": 0.01,
        "max_staleness_multiplier": 2,
        "require_utc": True,
        "require_provider_lineage": True,
    },
    "lineage_contract": {
        "bars": ["symbol", "interval", "open_time", "available_time", "provider", "exchange", "source_version", "schema_version"],
        "news": ["raw_payload_id", "url", "published_at", "available_time", "provider", "schema_version"],
        "macro": ["indicator", "timestamp", "available_time", "provider", "source_version", "schema_version"],
        "agent_context": ["context_hash", "input_snapshot_ids", "data_versions", "as_of_time"],
    },
}


class CleaningRulePayload(BaseModel):
    rule_id: str = Field(..., min_length=3, max_length=120)
    data_type: str = Field(..., min_length=2, max_length=40)
    enabled: bool = True
    version: int = Field(default=1, ge=1)
    description: str = ""
    changed_data_store: str = "data/governance/changed_items"
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_governance() -> Dict[str, Any]:
    if not GOVERNANCE_FILE.exists():
        return deepcopy(DEFAULT_GOVERNANCE)
    try:
        raw = json.loads(GOVERNANCE_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return deepcopy(DEFAULT_GOVERNANCE)
        merged = deepcopy(DEFAULT_GOVERNANCE)
        merged.update(raw)
        return merged
    except Exception:
        return deepcopy(DEFAULT_GOVERNANCE)


def _save_governance(payload: Dict[str, Any]) -> Dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(payload)
    payload["schema_version"] = DEFAULT_GOVERNANCE["schema_version"]
    payload["updated_at"] = _now_iso()
    GOVERNANCE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _response(data: Any, *, meta: Optional[Dict[str, Any]] = None, errors: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "schema_version": "data_governance_response.v1",
            "generated_at": _now_iso(),
            "config_file": str(GOVERNANCE_FILE),
            **(meta or {}),
        },
        "errors": errors or [],
    }


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if value is None:
        return None
    return str(value)


async def _coverage() -> Dict[str, Any]:
    try:
        from app.api.v1.endpoints.data_platform import get_meta_coverage

        return await get_meta_coverage()
    except Exception as exc:
        return {"data": {}, "errors": [{"message": str(exc)[:240]}]}


@router.get("/overview")
async def get_data_governance_overview() -> Dict[str, Any]:
    governance = _load_governance()
    coverage = await _coverage()
    try:
        from app.pipeline.storage.duckdb_store import pipeline_store

        latest_macro = pipeline_store.latest_macro()
        latest_news = pipeline_store.query_news(limit=5)
        pipeline_store_available = pipeline_store.available
    except Exception:
        latest_macro = {}
        latest_news = []
        pipeline_store_available = False
    data = {
        "governance": governance,
        "coverage": coverage.get("data", {}),
        "storage_contract": {},
        "quality": {
            "market_source_groups": len((coverage.get("data", {}).get("market_bars") or [])) if isinstance(coverage.get("data"), dict) else 0,
            "macro_indicator_count": len(latest_macro),
            "news_sample_count": len(latest_news),
            "pipeline_store_available": pipeline_store_available,
            "pit_rule": "available_time <= as_of_time",
        },
        "contracts": {
            "source_config": "/api/v1/data-governance/sources",
            "preview": "/api/v1/data-governance/preview",
            "cleaning_rules": "/api/v1/data-governance/cleaning-rules",
            "lineage": "/api/v1/data-governance/lineage",
            "storage_contract": "/api/v1/meta/storage-contract",
            "manual_ingest": "/api/v1/meta/ingest",
            "financial_refresh": "/api/v1/meta/refresh-financials",
        },
    }
    try:
        from app.api.v1.endpoints.data_platform import get_meta_storage_contract

        storage_payload = await get_meta_storage_contract()
        data["storage_contract"] = storage_payload.get("data", {})
        data["quality"]["storage_contract_table_count"] = storage_payload.get("meta", {}).get("table_count", 0)
        data["quality"]["manual_ingest_ready"] = True
    except Exception:
        data["quality"]["manual_ingest_ready"] = False
    return _response(data)


@router.get("/sources")
async def get_governance_sources() -> Dict[str, Any]:
    try:
        from app.api.v1.endpoints.data_platform import get_meta_providers

        providers = await get_meta_providers()
    except Exception as exc:
        providers = {"data": [], "errors": [{"message": str(exc)[:240]}]}
    return _response(
        {
            "providers": providers.get("data", []),
            "source_policy": {
                "openbb_reuse": True,
                "local_storage_before_agent": True,
                "manual_refresh_can_fetch_external": True,
                "agent_external_bypass_allowed": False,
            },
        },
        errors=providers.get("errors", []),
    )


@router.get("/preview")
async def preview_governed_data(
    data_type: str = Query("bars", pattern="^(bars|news|macro|quotes|fundamentals|corporate_actions|adjustment_factors)$"),
    symbol: Optional[str] = Query("BTCUSDT"),
    interval: str = Query("1h"),
    limit: int = Query(20, ge=1, le=200),
    as_of_time: Optional[datetime] = Query(None),
) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    if data_type == "bars":
        from app.api.v1.endpoints.data_platform import get_bars_as_of

        payload = await get_bars_as_of(symbol=symbol or "BTCUSDT", interval=interval, as_of_time=as_of_time, limit=limit)
        return _response(payload.get("data", []), meta={"source_endpoint": "/api/v1/bars/as-of", **payload.get("meta", {})})
    if data_type == "quotes":
        from app.api.v1.endpoints.data_platform import get_quote_history

        payload = await get_quote_history(
            symbol=symbol or "BTCUSDT",
            interval=interval,
            limit=limit,
            start_time=None,
            end_time=as_of_time,
        )
        return _response(payload.get("data", []), meta={"source_endpoint": "/api/v1/quotes/history", **payload.get("meta", {})})
    if data_type == "news":
        from app.api.v1.endpoints.data_platform import list_news

        payload = await list_news(symbol=symbol, limit=limit, offset=0, as_of_time=as_of_time)
        return _response(payload.get("data", []), meta={"source_endpoint": "/api/v1/news", **payload.get("meta", {})})
    if data_type == "macro":
        from app.api.v1.endpoints.data_platform import list_macro_indicators

        payload = await list_macro_indicators(indicator=None, start=None, end=as_of_time, limit=limit)
        return _response(payload.get("data", []), meta={"source_endpoint": "/api/v1/macro/indicators", **payload.get("meta", {})})
    if data_type == "fundamentals":
        from app.api.v1.endpoints.data_platform import get_fundamentals

        payload = await get_fundamentals(symbol=symbol or "BTCUSDT", limit=limit, as_of_time=as_of_time)
        return _response(payload.get("data", []), meta={"source_endpoint": "/api/v1/fundamentals/{symbol}", **payload.get("meta", {})}, errors=payload.get("errors", []))
    if data_type == "corporate_actions":
        from app.api.v1.endpoints.data_platform import get_corporate_actions

        payload = await get_corporate_actions(symbol=symbol or "BTCUSDT", limit=limit, as_of_time=as_of_time)
        return _response(payload.get("data", []), meta={"source_endpoint": "/api/v1/corporate-actions/{symbol}", **payload.get("meta", {})}, errors=payload.get("errors", []))
    if data_type == "adjustment_factors":
        from app.api.v1.endpoints.data_platform import get_adjust_factors

        payload = await get_adjust_factors(symbol=symbol or "BTCUSDT", limit=limit, as_of_time=as_of_time)
        return _response(payload.get("data", []), meta={"source_endpoint": "/api/v1/adjust-factors/{symbol}", **payload.get("meta", {})}, errors=payload.get("errors", []))
    errors.append({"code": "unsupported_data_type", "message": f"Unsupported data_type: {data_type}"})
    return _response([], errors=errors)


@router.get("/cleaning-rules")
async def list_cleaning_rules() -> Dict[str, Any]:
    governance = _load_governance()
    return _response(
        governance.get("cleaning_rules", []),
        meta={
            "count": len(governance.get("cleaning_rules", [])),
            "versioning_policy": "Cleaned or changed items must be stored separately with rule_id/version and original record identity.",
        },
    )


@router.post("/cleaning-rules")
async def upsert_cleaning_rule(payload: CleaningRulePayload) -> Dict[str, Any]:
    governance = _load_governance()
    rules = [item for item in governance.get("cleaning_rules", []) if item.get("rule_id") != payload.rule_id]
    rule = payload.model_dump()
    rule["updated_at"] = _now_iso()
    rule["schema_version"] = "cleaning_rule.v1"
    rules.append(rule)
    governance["cleaning_rules"] = sorted(rules, key=lambda item: item.get("rule_id", ""))
    saved = _save_governance(governance)
    return _response(rule, meta={"updated": True, "rule_count": len(saved.get("cleaning_rules", []))})


@router.get("/lineage")
async def get_data_lineage(
    symbol: Optional[str] = Query(None),
    interval: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    coverage = await _coverage()
    market_bars = []
    if isinstance(coverage.get("data"), dict):
        market_bars = coverage["data"].get("market_bars") or []
    filtered = []
    for row in market_bars:
        if symbol and str(row.get("symbol", "")).upper() != symbol.upper().replace("/", ""):
            continue
        if interval and row.get("interval") != interval:
            continue
        filtered.append(
            {
                "data_type": "bar",
                "symbol": row.get("symbol"),
                "interval": row.get("interval"),
                "provider": row.get("provider"),
                "exchange": row.get("exchange"),
                "min_time": _iso(row.get("min_time")),
                "max_time": _iso(row.get("max_time")),
                "row_count": row.get("row_count"),
                "storage": "clickhouse.market_bars",
                "pit_field": "available_time",
            }
        )
    governance = _load_governance()
    storage_contract = {}
    try:
        from app.api.v1.endpoints.data_platform import build_storage_contract

        storage_contract = build_storage_contract()
    except Exception:
        storage_contract = {}
    return _response(
        filtered[:limit],
        meta={
            "count": len(filtered[:limit]),
            "total": len(filtered),
            "lineage_contract": governance.get("lineage_contract", {}),
            "agent_context_lineage": "context_hash + input_snapshot_ids + data_versions",
            "storage_contract_tables": list((storage_contract.get("tables") or {}).keys()),
            "manual_ingest_api": "/api/v1/meta/ingest",
        },
        errors=coverage.get("errors", []),
    )


@router.get("/quality")
async def get_data_quality() -> Dict[str, Any]:
    governance = _load_governance()
    coverage = await _coverage()
    rows = []
    if isinstance(coverage.get("data"), dict):
        rows = coverage["data"].get("market_bars") or []
    total_rows = sum(int(row.get("row_count") or 0) for row in rows)
    providers = sorted({str(row.get("provider") or "unknown") for row in rows})
    try:
        from app.api.v1.endpoints.data_platform import build_storage_contract

        storage_tables = build_storage_contract().get("tables", {})
    except Exception:
        storage_tables = {}
    return _response(
        {
            "thresholds": governance.get("quality_thresholds", {}),
            "checks": [
                {"id": "provider_lineage", "status": "ready" if providers else "check", "detail": f"{len(providers)} providers observed"},
                {"id": "market_bar_coverage", "status": "ready" if total_rows > 0 else "check", "detail": f"{total_rows} market bar rows"},
                {"id": "pit_visibility", "status": "ready", "detail": "AnalysisContext and as-of endpoints enforce available_time <= as_of_time"},
                {"id": "cleaning_versions", "status": "ready", "detail": f"{len(governance.get('cleaning_rules', []))} rule versions configured"},
                {"id": "storage_contract_tables", "status": "ready" if storage_tables else "check", "detail": f"{len(storage_tables)} PostgreSQL/Timescale contract tables declared"},
                {"id": "manual_ingest_contract", "status": "ready", "detail": "POST /api/v1/meta/ingest dry-run/upsert writes ETL job log and lineage evidence"},
            ],
        },
        meta={"provider_count": len(providers), "market_rows": total_rows},
        errors=coverage.get("errors", []),
    )
