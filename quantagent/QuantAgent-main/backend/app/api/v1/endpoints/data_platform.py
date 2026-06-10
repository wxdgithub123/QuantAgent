"""PRD-compatible financial data platform endpoints.

This router exposes the top-level Phase 2 data-platform contract while reusing
the existing local-first QuantAgent services:

- ClickHouse/market gateway for bars and quotes
- DuckDB pipeline store for news and macro
- AnalysisContextBuilder for point-in-time snapshots
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.models.instrument import Instrument
from app.services.market_data_gateway import market_data_gateway

router = APIRouter()


class BarsBatchRequest(BaseModel):
    symbols: List[str] = Field(default_factory=list)
    interval: str = "1h"
    limit: int = Field(default=120, ge=1, le=1000)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    asset_type: str = "crypto"
    provider: str = "yfinance"
    fallback_providers: List[str] = Field(default_factory=list)
    refresh_from_source: bool = False


class SnapshotRequest(BaseModel):
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    as_of_time: Optional[datetime] = None
    bar_limit: int = Field(default=120, ge=1, le=1000)
    factor_limit: int = Field(default=60, ge=0, le=500)
    signal_limit: int = Field(default=40, ge=0, le=500)
    news_limit: int = Field(default=20, ge=0, le=200)
    macro_limit: int = Field(default=30, ge=0, le=200)


class LocalIngestRequest(BaseModel):
    table: str = Field(..., description="fundamental_report | corporate_action | adjustment_factor")
    provider: str = Field(..., min_length=2, max_length=120)
    source_version: str = Field(default="default", max_length=120)
    batch_id: Optional[str] = Field(default=None, max_length=128)
    dry_run: bool = Field(default=True, description="Validate and normalize only. Set false to write local PostgreSQL storage.")
    records: List[Dict[str, Any]] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class FinancialRefreshRequest(BaseModel):
    symbols: List[str] = Field(default_factory=list, description="Equity symbols to refresh, e.g. AAPL/MSFT.")
    tables: List[str] = Field(
        default_factory=lambda: ["fundamental_report", "corporate_action", "adjustment_factor"],
        description="financial storage tables to normalize and ingest",
    )
    provider: str = Field(default="yfinance", max_length=80)
    source_version: str = Field(default="openbb-sdk", max_length=120)
    period: str = Field(default="annual", max_length=40)
    limit: int = Field(default=20, ge=1, le=200)
    dry_run: bool = Field(default=True, description="Validate normalized records only unless explicitly disabled.")


STORAGE_CONTRACT_VERSION = "data_platform_storage_contract.v1"
PIT_FIELDS = ["event_time", "ingest_time", "available_time"]
BAR_STORAGE_TABLES = ["bar_1m", "bar_1h", "bar_1d"]
REQUIRED_STORAGE_TABLES = [
    "data_provider",
    "instrument",
    *BAR_STORAGE_TABLES,
    "quote_latest",
    "fundamental_report",
    "corporate_action",
    "adjustment_factor",
    "etl_job_log",
    "news_event",
    "macro_indicator",
    "data_lineage",
    "cleaned_data_item",
    "data_platform_storage_policy",
]


def build_storage_contract() -> Dict[str, Any]:
    """Return the database contract required by the Phase 2 data-platform PRD."""
    bar_tables = {
        table: {
            "grain": table.replace("bar_", ""),
            "pit_fields": PIT_FIELDS,
            "upsert_key": ["symbol", "ts", "provider", "source_version"],
            "record_identity": ["record_id", "ts"],
            "indexes": [
                f"idx_{table}_symbol_ts",
                f"idx_{table}_available_time",
                f"idx_{table}_provider_ts",
                f"idx_{table}_quality_gin",
                f"idx_{table}_lineage_gin",
            ],
            "quality_fields": [
                "data_quality_flags",
                "outlier_flags",
                "gap_status",
                "fill_method",
                "cleaning_rule_version",
                "unit_standard",
                "null_policy",
            ],
            "timescale": {
                "hypertable": {"time_column": "ts", "guarded": True},
                "compression_policy": "declared_and_guarded",
                "hot_cold_retention_policy": "declared",
            },
        }
        for table in BAR_STORAGE_TABLES
    }
    return {
        "schema_version": STORAGE_CONTRACT_VERSION,
        "migration_revision": "017",
        "migration_file": "backend/migrations/versions/017_data_platform_contract_tables.py",
        "visibility_rule": "available_time <= as_of_time",
        "agent_input_policy": "local_storage_only",
        "timezone": "UTC",
        "storage_engine": {
            "target": "PostgreSQL + TimescaleDB",
            "current_compatibility_layers": ["ClickHouse market_bars", "DuckDB news_articles/macro_indicators"],
            "timescale_installation": "guarded_migration; remains plain PostgreSQL if extension is unavailable",
        },
        "tables": {
            "data_provider": {
                "purpose": "Provider registry with health, priority, fallback, rate-limit, and custom-provider metadata.",
                "primary_key": ["provider_id"],
                "supports_custom_provider": True,
            },
            "instrument": {
                "purpose": "Canonical multi-asset instrument registry for crypto, equities, futures/perpetuals, macro expansion.",
                "primary_key": ["instrument_id"],
                "unique": [["symbol"]],
                "pit_fields": PIT_FIELDS,
            },
            **bar_tables,
            "quote_latest": {
                "purpose": "Latest local quote snapshot for fast read paths.",
                "pit_fields": PIT_FIELDS,
                "upsert_key": ["symbol", "provider"],
                "indexes": ["idx_quote_latest_symbol_ts", "idx_quote_latest_available_time"],
            },
            "fundamental_report": {
                "purpose": "Equity/fundamental reports with raw metrics and unit normalization.",
                "pit_fields": PIT_FIELDS,
                "upsert_key": ["symbol", "report_type", "fiscal_period", "provider", "source_version"],
                "indexes": ["idx_fundamental_report_symbol_event", "idx_fundamental_report_available_time"],
            },
            "corporate_action": {
                "purpose": "Dividends, splits, symbol changes, and other company actions.",
                "pit_fields": PIT_FIELDS,
                "upsert_key": ["symbol", "action_type", "event_time", "provider", "source_version"],
                "indexes": ["idx_corporate_action_symbol_event", "idx_corporate_action_available_time"],
            },
            "adjustment_factor": {
                "purpose": "Independent adjustment-factor store for split/dividend-adjusted research and backtests.",
                "pit_fields": PIT_FIELDS,
                "upsert_key": ["symbol", "factor_type", "effective_time", "provider", "source_version"],
                "indexes": ["idx_adjustment_factor_symbol_effective", "idx_adjustment_factor_available_time"],
            },
            "news_event": {
                "purpose": "Financial news with extracted symbols, sectors, topics, sentiment, and stable payload hashes.",
                "pit_fields": PIT_FIELDS,
                "upsert_key": ["provider", "raw_payload_hash"],
                "indexes": ["idx_news_event_available_time", "idx_news_event_symbols_gin", "idx_news_event_topics_gin"],
            },
            "macro_indicator": {
                "purpose": "Macro/fixed-income indicators with observation and release/available-time separation.",
                "pit_fields": PIT_FIELDS,
                "upsert_key": ["code", "observation_time", "provider", "source_version"],
                "indexes": ["idx_macro_indicator_code_observation", "idx_macro_indicator_available_time"],
            },
            "etl_job_log": {
                "purpose": "Idempotent ETL, retry, row-count, gap, outlier, error, and lineage job evidence.",
                "unique": [["batch_id"], ["idempotency_key"]],
                "indexes": ["idx_etl_job_log_status", "idx_etl_job_log_data_type"],
            },
            "data_lineage": {
                "purpose": "Per-record upstream IDs, ETL batch, cleaning rule, source version, and transformation trace.",
                "indexes": ["idx_data_lineage_entity", "idx_data_lineage_batch", "idx_data_lineage_upstream_gin"],
            },
            "cleaned_data_item": {
                "purpose": "Versioned store for changed/cleaned items with before/after values and rule identity.",
                "pit_fields": PIT_FIELDS,
                "indexes": ["idx_cleaned_data_item_original", "idx_cleaned_data_item_rule"],
            },
            "data_platform_storage_policy": {
                "purpose": "Declared compression, retention, cold-tier, backup, and PITR policies.",
                "policies": [
                    "bar_1m_compression",
                    "bar_1h_compression",
                    "bar_1d_compression",
                    "bar_1m_retention",
                    "bar_1h_retention",
                    "bar_1d_retention",
                    "postgres_pitr",
                ],
            },
        },
        "etl_contract": {
            "write_mode": "transactional bulk upsert",
            "idempotency": ["record_id", "provider", "source_version", "idempotency_key"],
            "quality": [
                "dedupe",
                "gap_detection",
                "gap_fill_or_resample",
                "outlier_flag_or_recollect",
                "null_standardization",
                "unit_standardization",
                "type_validation",
                "multi_source_comparison",
                "cleaning_rule_versioning",
            ],
            "lineage": ["raw_payload_hash", "etl_batch_id", "upstream_record_ids", "data_lineage"],
        },
        "scheduler_contract": {
            "target": "Prefect 3",
            "current_adapter": "pipeline_orchestrator",
            "jobs": [
                "historical_backfill",
                "daily_incremental",
                "minute_bars",
                "quote_snapshot",
                "fundamentals",
                "macro",
                "news",
                "corporate_actions",
                "data_quality_patrol",
            ],
            "features": ["retry", "idempotent", "parallel", "dynamic", "timeout", "logging", "manual_trigger", "parameterized"],
        },
        "backup_and_lifecycle": {
            "timescale_compression": "guarded_policy",
            "hot_cold_tiering": "declared_policy",
            "retention": "declared_policy",
            "backup_pitr": "declared_policy_requires_infra_validation",
        },
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if isinstance(value, pd.Timestamp):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return str(value)
    except Exception:
        return str(value)


def _split_csv(value: Optional[str]) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _clean_symbol(symbol: str) -> str:
    return Instrument.from_raw(symbol).symbol


def _record_id(*parts: Any) -> str:
    stable = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"


def _get_field(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _safe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _response(
    data: Any,
    *,
    meta: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "schema_version": "data_platform_response.v1",
            "generated_at": _now_iso(),
            **(meta or {}),
        },
        "errors": errors or [],
    }


def _bar_to_record(bar: Any, symbol: str, interval: str, provider: Optional[str] = None) -> Dict[str, Any]:
    timestamp = _get_field(bar, "timestamp") or _get_field(bar, "datetime") or _get_field(bar, "open_time")
    close_time = _get_field(bar, "close_time") or _get_field(bar, "bar_end_time")
    available_time = _get_field(bar, "available_time") or close_time or timestamp
    quote_volume = _get_field(bar, "quote_volume") or _get_field(bar, "volume_notional")
    trades = _get_field(bar, "trades") or _get_field(bar, "transactions")
    return {
        "id": _record_id("bar", symbol, interval, timestamp, provider),
        "symbol": symbol,
        "interval": interval,
        "ts": _iso(timestamp),
        "event_time": _iso(timestamp),
        "available_time": _iso(available_time),
        "open": float(_get_field(bar, "open")),
        "high": float(_get_field(bar, "high")),
        "low": float(_get_field(bar, "low")),
        "close": float(_get_field(bar, "close")),
        "volume": float(_get_field(bar, "volume", 0.0) or 0.0),
        "quote_volume": float(quote_volume) if quote_volume is not None else None,
        "trades": int(trades) if trades is not None else None,
        "provider": provider or _get_field(bar, "provider") or "market_data_gateway:local_storage",
        "schema_version": "bar.v1",
    }


def _ticker_to_record(ticker: Any, symbol: str) -> Dict[str, Any]:
    return {
        "id": _record_id("quote_latest", symbol, getattr(ticker, "timestamp", None)),
        "symbol": symbol,
        "price": float(ticker.price),
        "change_24h": float(ticker.change_24h or 0.0),
        "change_percent": float(ticker.change_percent or 0.0),
        "volume": float(ticker.volume or 0.0),
        "high_24h": float(ticker.high_24h or 0.0),
        "low_24h": float(ticker.low_24h or 0.0),
        "ts": _iso(ticker.timestamp),
        "event_time": _iso(ticker.timestamp),
        "available_time": _iso(ticker.timestamp),
        "provider": "market_data_gateway:local_storage",
        "schema_version": "quote_latest.v1",
    }


def _news_id(row: Dict[str, Any]) -> str:
    raw = row.get("raw_payload_id") or row.get("url") or row.get("title") or ""
    return _record_id("news", raw)


def _normalize_pipeline_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, float) and pd.isna(value):
            out[key] = None
        elif isinstance(value, pd.Timestamp):
            out[key] = _iso(value)
        elif isinstance(value, datetime):
            out[key] = _iso(value)
        elif key == "metadata":
            out[key] = _safe_json(value)
        else:
            out[key] = value
    return out


def _instrument_record(symbol: str, *, source: str = "configured") -> Dict[str, Any]:
    inst = Instrument.from_raw(symbol)
    return {
        "symbol": inst.symbol,
        "instrument_id": inst.symbol,
        "base_asset": inst.base_asset,
        "quote_asset": inst.quote_asset,
        "exchange": inst.exchange,
        "asset_type": "crypto" if inst.quote_asset in {"USDT", "USDC", "USD", "BUSD"} else "unknown",
        "instrument_type": inst.instrument_type.value,
        "ccxt_symbol": inst.ccxt_symbol,
        "openbb_symbol": inst.hyphen_symbol,
        "source": source,
        "status": "active",
    }


async def _load_bars(
    *,
    symbol: str,
    interval: str,
    limit: int,
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    asset_type: str,
    provider: str,
    fallback_providers: List[str],
    refresh_from_source: bool,
    persist_fetched: bool = True,
) -> tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    canonical = _clean_symbol(symbol)
    errors: List[Dict[str, Any]] = []

    if asset_type.lower() in {"equity", "stock"} and refresh_from_source:
        try:
            from app.services.openbb_data_service import openbb_data_service

            bars = await openbb_data_service.get_equity_historical(
                symbol=symbol.upper(),
                interval=interval,
                start=start_time,
                end=end_time,
                limit=limit,
                provider=provider,
                fallback_providers=fallback_providers,
            )
            if persist_fetched and bars:
                await market_data_gateway.persist_bars(symbol.upper(), interval, bars)
            data = [_bar_to_record(bar, symbol.upper(), interval, provider=getattr(bar, "provider", None)) for bar in bars]
            return data, {"source": f"openbb:{provider}", "asset_type": "equity"}, errors
        except Exception as exc:
            errors.append({"code": "equity_fetch_failed", "message": str(exc)[:240]})

    bars = await market_data_gateway.get_klines(
        symbol=canonical,
        interval=interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        openbb_provider=provider,
        openbb_fallback_providers=fallback_providers,
        allow_external_fallback=refresh_from_source,
        allow_ccxt_fallback=refresh_from_source,
        allow_binance_fallback=False,
    )
    metadata = await market_data_gateway.get_kline_metadata(canonical, interval)
    active_provider = metadata.get("provider") or "market_data_gateway:local_storage"
    data = [_bar_to_record(bar, canonical, interval, provider=active_provider) for bar in bars]
    metadata.update(
        {
            "source": "market_data_gateway",
            "asset_type": asset_type,
            "refresh_from_source": refresh_from_source,
            "requested_provider": provider,
            "fallback_providers": fallback_providers,
            "external_fallback_allowed": refresh_from_source,
        }
    )
    return data, metadata, errors


@router.get("/bars")
async def get_bars(
    symbol: str = Query(...),
    interval: str = Query("1h"),
    limit: int = Query(120, ge=1, le=1000),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    asset_type: str = Query("crypto"),
    provider: str = Query("yfinance"),
    fallback_providers: Optional[str] = Query(None),
    refresh_from_source: bool = Query(False, description="Explicitly allow live provider fetch when local storage is empty/stale."),
) -> Dict[str, Any]:
    """Unified bars endpoint. Defaults to local storage only."""
    data, meta, errors = await _load_bars(
        symbol=symbol,
        interval=interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        asset_type=asset_type,
        provider=provider,
        fallback_providers=_split_csv(fallback_providers),
        refresh_from_source=refresh_from_source,
    )
    return _response(data, meta={"symbol": _clean_symbol(symbol), "interval": interval, "count": len(data), **meta}, errors=errors)


@router.get("/bars/batch")
async def get_bars_batch_query(
    symbols: str = Query(..., description="Comma-separated symbols."),
    interval: str = Query("1h"),
    limit: int = Query(120, ge=1, le=1000),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    asset_type: str = Query("crypto"),
    provider: str = Query("yfinance"),
    fallback_providers: Optional[str] = Query(None),
    refresh_from_source: bool = Query(False),
) -> Dict[str, Any]:
    req = BarsBatchRequest(
        symbols=_split_csv(symbols),
        interval=interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        asset_type=asset_type,
        provider=provider,
        fallback_providers=_split_csv(fallback_providers),
        refresh_from_source=refresh_from_source,
    )
    return await post_bars_batch(req)


@router.post("/bars/batch")
async def post_bars_batch(req: BarsBatchRequest) -> Dict[str, Any]:
    """Batch bars endpoint with a unified response envelope."""
    results: Dict[str, Any] = {}
    errors: List[Dict[str, Any]] = []
    for symbol in req.symbols:
        try:
            data, meta, item_errors = await _load_bars(
                symbol=symbol,
                interval=req.interval,
                limit=req.limit,
                start_time=req.start_time,
                end_time=req.end_time,
                asset_type=req.asset_type,
                provider=req.provider,
                fallback_providers=req.fallback_providers,
                refresh_from_source=req.refresh_from_source,
            )
            results[_clean_symbol(symbol)] = {"data": data, "meta": {"count": len(data), **meta}}
            errors.extend({"symbol": symbol, **item} for item in item_errors)
        except Exception as exc:
            errors.append({"symbol": symbol, "code": "bars_unavailable", "message": str(exc)[:240]})
    return _response(
        results,
        meta={
            "symbols": [_clean_symbol(item) for item in req.symbols],
            "interval": req.interval,
            "refresh_from_source": req.refresh_from_source,
            "external_fallback_allowed": req.refresh_from_source,
        },
        errors=errors,
    )


@router.get("/quotes/latest")
async def get_latest_quotes(
    symbols: str = Query("BTCUSDT"),
    provider: str = Query("yfinance"),
    fallback_providers: Optional[str] = Query(None),
    refresh_from_source: bool = Query(False),
) -> Dict[str, Any]:
    """Latest quotes. Defaults to local cache and derived latest local bar."""
    data: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for raw_symbol in _split_csv(symbols):
        symbol = _clean_symbol(raw_symbol)
        try:
            ticker = await market_data_gateway.get_ticker(
                symbol,
                openbb_provider=provider,
                openbb_fallback_providers=_split_csv(fallback_providers),
                allow_external_fallback=refresh_from_source,
                allow_ccxt_fallback=refresh_from_source,
                allow_binance_fallback=False,
            )
            if ticker:
                data.append(_ticker_to_record(ticker, symbol))
            else:
                errors.append({"symbol": symbol, "code": "quote_unavailable", "message": "No local quote/latest bar available."})
        except Exception as exc:
            errors.append({"symbol": symbol, "code": "quote_failed", "message": str(exc)[:240]})
    return _response(
        data,
        meta={
            "symbols": [_clean_symbol(item) for item in _split_csv(symbols)],
            "count": len(data),
            "refresh_from_source": refresh_from_source,
            "external_fallback_allowed": refresh_from_source,
        },
        errors=errors,
    )


@router.get("/quotes/history")
async def get_quote_history(
    symbol: str = Query(...),
    interval: str = Query("1h"),
    limit: int = Query(120, ge=1, le=1000),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
) -> Dict[str, Any]:
    bars, meta, errors = await _load_bars(
        symbol=symbol,
        interval=interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        asset_type="crypto",
        provider="yfinance",
        fallback_providers=[],
        refresh_from_source=False,
    )
    quotes = [
        {
            "id": _record_id("quote_history", row["symbol"], row["interval"], row["ts"]),
            "symbol": row["symbol"],
            "price": row["close"],
            "volume": row["volume"],
            "ts": row["ts"],
            "event_time": row["event_time"],
            "available_time": row["available_time"],
            "provider": row["provider"],
            "bar_id": row["id"],
        }
        for row in bars
    ]
    return _response(quotes, meta={"symbol": _clean_symbol(symbol), "interval": interval, "count": len(quotes), **meta}, errors=errors)


@router.get("/instruments/search")
async def search_instruments(q: str = Query(...), limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    from app.core.config import settings

    query = q.upper().replace("/", "").replace("-", "")
    configured = [_instrument_record(symbol) for symbol in settings.SYMBOLS]
    discovered: List[Dict[str, Any]] = []
    try:
        from app.services.clickhouse_service import clickhouse_service

        ranges = await clickhouse_service.get_market_bar_source_ranges()
        discovered = [_instrument_record(row["symbol"], source="market_bars") for row in ranges if row.get("symbol")]
    except Exception:
        discovered = []
    by_symbol = {item["symbol"]: item for item in [*configured, *discovered]}
    matched = [item for item in by_symbol.values() if query in item["symbol"] or query in item["base_asset"]]
    return _response(matched[:limit], meta={"query": q, "count": min(len(matched), limit), "total_matches": len(matched)})


@router.get("/instruments")
async def list_instruments(limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0)) -> Dict[str, Any]:
    from app.core.config import settings

    items = [_instrument_record(symbol) for symbol in settings.SYMBOLS]
    try:
        from app.services.clickhouse_service import clickhouse_service

        ranges = await clickhouse_service.get_market_bar_source_ranges()
        for row in ranges:
            symbol = row.get("symbol")
            if symbol:
                items.append(_instrument_record(symbol, source="market_bars"))
    except Exception:
        pass
    deduped = {item["symbol"]: item for item in items}
    ordered = sorted(deduped.values(), key=lambda item: item["symbol"])
    return _response(ordered[offset: offset + limit], meta={"count": len(ordered[offset: offset + limit]), "total": len(ordered), "limit": limit, "offset": offset})


@router.get("/instruments/{symbol}")
async def get_instrument(symbol: str) -> Dict[str, Any]:
    item = _instrument_record(symbol, source="normalized_symbol")
    try:
        item["market_data_metadata"] = await market_data_gateway.get_kline_metadata(item["symbol"], "1h")
    except Exception:
        item["market_data_metadata"] = {}
    return _response(item, meta={"symbol": item["symbol"]})


@router.get("/fundamentals/{symbol}/latest")
async def get_latest_fundamentals(symbol: str, as_of_time: Optional[datetime] = Query(None)) -> Dict[str, Any]:
    from app.services.data_platform_storage import query_pit_records

    rows, meta, errors = await query_pit_records(
        "fundamental_report",
        symbol=symbol,
        limit=1,
        as_of_time=as_of_time,
    )
    return _response(rows[0] if rows else None, meta=meta, errors=errors)


@router.get("/fundamentals/{symbol}")
async def get_fundamentals(
    symbol: str,
    limit: int = Query(20, ge=1, le=200),
    as_of_time: Optional[datetime] = Query(None),
) -> Dict[str, Any]:
    from app.services.data_platform_storage import query_pit_records

    rows, meta, errors = await query_pit_records(
        "fundamental_report",
        symbol=symbol,
        limit=limit,
        as_of_time=as_of_time,
    )
    return _response(rows, meta=meta, errors=errors)


@router.get("/corporate-actions/{symbol}")
async def get_corporate_actions(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000),
    as_of_time: Optional[datetime] = Query(None),
) -> Dict[str, Any]:
    from app.services.data_platform_storage import query_pit_records

    rows, meta, errors = await query_pit_records(
        "corporate_action",
        symbol=symbol,
        limit=limit,
        as_of_time=as_of_time,
    )
    return _response(rows, meta=meta, errors=errors)


@router.get("/adjust-factors/{symbol}")
async def get_adjust_factors(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000),
    as_of_time: Optional[datetime] = Query(None),
) -> Dict[str, Any]:
    from app.services.data_platform_storage import query_pit_records

    rows, meta, errors = await query_pit_records(
        "adjustment_factor",
        symbol=symbol,
        limit=limit,
        as_of_time=as_of_time,
    )
    return _response(rows, meta={**meta, "independent_store": True}, errors=errors)


@router.get("/macro/indicators")
async def list_macro_indicators(
    indicator: Optional[str] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
) -> Dict[str, Any]:
    from app.pipeline.storage.duckdb_store import pipeline_store

    rows = pipeline_store.query_macro(indicator=indicator, start=start, end=end, limit=limit)
    data = [_normalize_pipeline_row(row) for row in rows]
    latest = pipeline_store.latest_macro()
    return _response(
        data,
        meta={
            "count": len(data),
            "latest_indicator_count": len(latest),
            "pit_rule": "COALESCE(available_time, timestamp) <= end/as_of_time when provided",
            "store_available": pipeline_store.available,
        },
    )


@router.get("/macro/indicators/{code}")
async def get_macro_indicator(code: str, limit: int = Query(200, ge=1, le=2000)) -> Dict[str, Any]:
    from app.pipeline.storage.duckdb_store import pipeline_store

    rows = pipeline_store.query_macro(indicator=code, limit=limit)
    data = [_normalize_pipeline_row(row) for row in rows]
    return _response(data, meta={"indicator": code, "count": len(data), "store_available": pipeline_store.available})


@router.get("/news")
async def list_news(
    symbol: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    as_of_time: Optional[datetime] = Query(None),
) -> Dict[str, Any]:
    from app.pipeline.storage.duckdb_store import pipeline_store

    rows = pipeline_store.query_news(symbol=symbol, limit=limit, offset=offset, end=as_of_time)
    data = []
    for row in rows:
        normalized = _normalize_pipeline_row(row)
        normalized["id"] = _news_id(normalized)
        data.append(normalized)
    return _response(
        data,
        meta={
            "symbol": symbol,
            "count": len(data),
            "limit": limit,
            "offset": offset,
            "pit_rule": "COALESCE(available_time, published_at) <= as_of_time when provided",
            "store_available": pipeline_store.available,
        },
    )


@router.get("/news/{news_id}")
async def get_news_item(news_id: str) -> Dict[str, Any]:
    from app.pipeline.storage.duckdb_store import pipeline_store

    rows = pipeline_store.query_news(limit=10_000)
    for row in rows:
        normalized = _normalize_pipeline_row(row)
        normalized["id"] = _news_id(normalized)
        if normalized["id"] == news_id or str(normalized.get("raw_payload_id")) == news_id:
            return _response(normalized, meta={"id": news_id, "store_available": pipeline_store.available})
    return _response(
        None,
        meta={"id": news_id, "status": "not_found", "store_available": pipeline_store.available},
        errors=[{"code": "news_not_found", "message": "No local news record matched the requested ID."}],
    )


@router.get("/meta/coverage")
async def get_meta_coverage() -> Dict[str, Any]:
    sources: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    try:
        from app.services.clickhouse_service import clickhouse_service

        ranges = await clickhouse_service.get_market_bar_source_ranges()
        sources = [
            {
                **row,
                "min_time": _iso(row.get("min_time")),
                "max_time": _iso(row.get("max_time")),
            }
            for row in ranges
        ]
    except Exception as exc:
        errors.append({"code": "coverage_unavailable", "message": str(exc)[:240]})
    try:
        from app.pipeline.orchestrator import pipeline_orchestrator
        from app.pipeline.storage.duckdb_store import pipeline_store

        pipeline = {**pipeline_orchestrator.stats(), "store_available": pipeline_store.available}
    except Exception as exc:
        pipeline = {"error": str(exc)[:240]}
    return _response(
        {"market_bars": sources, "pipeline": pipeline},
        meta={
            "market_source_groups": len(sources),
            "contracts": REQUIRED_STORAGE_TABLES,
            "storage_contract_api": "/api/v1/meta/storage-contract",
            "storage_contract_version": STORAGE_CONTRACT_VERSION,
        },
        errors=errors,
    )


@router.get("/meta/storage-contract")
async def get_meta_storage_contract() -> Dict[str, Any]:
    """Expose the concrete Phase 2 PostgreSQL/Timescale storage contract."""
    contract = build_storage_contract()
    return _response(
        contract,
        meta={
            "table_count": len(contract["tables"]),
            "bar_tables": BAR_STORAGE_TABLES,
            "pit_fields": PIT_FIELDS,
            "migration_revision": contract["migration_revision"],
            "timescale_contract_declared": True,
            "backup_pitr_contract_declared": True,
        },
    )


@router.get("/meta/providers")
async def get_meta_providers() -> Dict[str, Any]:
    from app.services.openbb_data_service import openbb_data_service

    providers = [
        {
            "id": "openbb:yfinance",
            "name": "OpenBB yfinance",
            "priority": 10,
            "status": "available" if openbb_data_service.available else "unavailable",
            "supports": ["crypto_bars", "crypto_quotes", "equity_bars", "equity_quotes", "news"],
            "rate_limit_policy": "provider_default",
        },
        {
            "id": "openbb:fred",
            "name": "OpenBB FRED",
            "priority": 20,
            "status": "available" if openbb_data_service.available else "unavailable",
            "supports": ["macro_indicator"],
            "rate_limit_policy": "provider_default",
        },
        {
            "id": "ccxt:okx",
            "name": "CCXT OKX fallback",
            "priority": 80,
            "status": "registered",
            "supports": ["crypto_bars", "crypto_quotes"],
            "rate_limit_policy": "explicit_fallback_only",
        },
        {
            "id": "clickhouse:market_bars",
            "name": "Local ClickHouse market_bars",
            "priority": 1,
            "status": "local_cache",
            "supports": ["bars", "quotes_history"],
            "rate_limit_policy": "local",
        },
        {
            "id": "duckdb:pipeline",
            "name": "Local DuckDB news/macro pipeline",
            "priority": 1,
            "status": "local_cache",
            "supports": ["news_event", "macro_indicator"],
            "rate_limit_policy": "local",
        },
    ]
    return _response(
        providers,
        meta={
            "provider_registry_version": "provider_registry.v1",
            "custom_provider_contract": {
                "required_fields": ["id", "name", "priority", "health_check", "supports", "rate_limit_policy"],
                "ingestion_contract": "Normalize to canonical storage before Agent/backtest consumption.",
            },
        },
    )


@router.get("/meta/jobs")
async def get_meta_jobs() -> Dict[str, Any]:
    try:
        from app.pipeline.orchestrator import pipeline_orchestrator
        from app.pipeline.storage.duckdb_store import pipeline_store

        stats = {**pipeline_orchestrator.stats(), "store_available": pipeline_store.available}
    except Exception as exc:
        stats = {"error": str(exc)[:240]}
    jobs = [
        {
            "batch_id": "pipeline:macro",
            "job_type": "macro_incremental",
            "status": "scheduled" if stats.get("running") else "idle",
            "scheduler": "pipeline_orchestrator",
            "prefect3_contract": True,
            "stored_records": stats.get("macro_stored", 0),
        },
        {
            "batch_id": "pipeline:news",
            "job_type": "news_incremental",
            "status": "scheduled" if stats.get("running") else "idle",
            "scheduler": "pipeline_orchestrator",
            "prefect3_contract": True,
            "stored_records": stats.get("news_stored", 0),
        },
    ]
    return _response(jobs, meta={"count": len(jobs), "etl_job_log_status": "contract_declared", "pipeline": stats})


@router.get("/meta/jobs/{batch_id}")
async def get_meta_job(batch_id: str) -> Dict[str, Any]:
    jobs_payload = await get_meta_jobs()
    for job in jobs_payload["data"]:
        if job.get("batch_id") == batch_id:
            return _response(job, meta={"batch_id": batch_id})
    return _response(
        None,
        meta={"batch_id": batch_id, "status": "not_found"},
        errors=[{"code": "job_not_found", "message": "No local ETL job matched the requested batch_id."}],
    )


@router.post("/meta/ingest")
async def ingest_local_records(req: LocalIngestRequest) -> Dict[str, Any]:
    """Validate or upsert provider-normalized records into local storage-contract tables."""
    from app.services.data_platform_ingestion import ingest_records

    rows, meta, errors = await ingest_records(
        req.table,
        req.records,
        provider=req.provider,
        source_version=req.source_version,
        batch_id=req.batch_id,
        dry_run=req.dry_run,
        parameters=req.parameters,
    )
    return _response(
        rows,
        meta={
            **meta,
            "manual_trigger": True,
            "external_fetch_performed": False,
            "ingestion_contract": "records must already be provider-normalized and locally persisted before Agent/backtest use",
        },
        errors=errors,
    )


@router.post("/meta/refresh-financials")
async def refresh_financial_records(req: FinancialRefreshRequest) -> Dict[str, Any]:
    """Explicitly fetch OpenBB financial records, normalize them, then local-ingest."""
    from app.services.openbb_financial_adapter import refresh_openbb_financial_data

    results, meta, errors = await refresh_openbb_financial_data(
        req.symbols,
        tables=req.tables,
        provider=req.provider,
        source_version=req.source_version,
        period=req.period,
        limit=req.limit,
        dry_run=req.dry_run,
    )
    return _response(
        results,
        meta={
            **meta,
            "manual_trigger": True,
            "default_dry_run": True,
            "provider_refresh_contract": "OpenBB fetch is explicit; normalized records are written only through local data_platform_ingestion.",
            "agent_backtest_reads": "local_storage_only via /fundamentals, /corporate-actions, /adjust-factors",
        },
        errors=errors,
    )


@router.get("/bars/as-of")
async def get_bars_as_of(
    symbol: str = Query(...),
    interval: str = Query("1h"),
    as_of_time: Optional[datetime] = Query(None),
    limit: int = Query(120, ge=1, le=1000),
) -> Dict[str, Any]:
    from app.services.analysis_context_builder import analysis_context_builder

    context = await analysis_context_builder.build(
        symbol=symbol,
        interval=interval,
        as_of_time=as_of_time,
        bar_limit=limit,
        factor_limit=0,
        signal_limit=0,
        news_limit=0,
        macro_limit=0,
    )
    payload = context.to_agent_payload()
    bars = payload.get("bars") or []
    return _response(
        bars,
        meta={
            "symbol": payload.get("symbol"),
            "interval": interval,
            "as_of_time": payload.get("as_of_time"),
            "count": len(bars),
            "context_hash": payload.get("context_hash"),
            "input_snapshot_ids": payload.get("input_snapshot_ids"),
            "data_versions": payload.get("data_versions"),
            "pit_rule": "available_time <= as_of_time",
            "agent_input_policy": "local_storage_only",
            "external_fallback_allowed": False,
        },
    )


@router.get("/snapshot")
async def get_snapshot_query(
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("1h"),
    as_of_time: Optional[datetime] = Query(None),
    bar_limit: int = Query(120, ge=1, le=1000),
    factor_limit: int = Query(60, ge=0, le=500),
    signal_limit: int = Query(40, ge=0, le=500),
    news_limit: int = Query(20, ge=0, le=200),
    macro_limit: int = Query(30, ge=0, le=200),
) -> Dict[str, Any]:
    return await post_snapshot(
        SnapshotRequest(
            symbol=symbol,
            interval=interval,
            as_of_time=as_of_time,
            bar_limit=bar_limit,
            factor_limit=factor_limit,
            signal_limit=signal_limit,
            news_limit=news_limit,
            macro_limit=macro_limit,
        )
    )


@router.post("/snapshot")
async def post_snapshot(req: SnapshotRequest) -> Dict[str, Any]:
    from app.services.analysis_context_builder import analysis_context_builder

    context = await analysis_context_builder.build(
        symbol=req.symbol,
        interval=req.interval,
        as_of_time=req.as_of_time,
        bar_limit=req.bar_limit,
        factor_limit=req.factor_limit,
        signal_limit=req.signal_limit,
        news_limit=req.news_limit,
        macro_limit=req.macro_limit,
    )
    payload = context.to_agent_payload()
    return _response(
        payload,
        meta={
            "symbol": payload.get("symbol"),
            "interval": req.interval,
            "as_of_time": payload.get("as_of_time"),
            "context_hash": payload.get("context_hash"),
            "input_snapshot_ids": payload.get("input_snapshot_ids"),
            "data_versions": payload.get("data_versions"),
            "pit_rule": "available_time <= as_of_time",
            "agent_input_policy": "local_storage_only",
            "external_fallback_allowed": False,
            "snapshot_schema_version": "analysis_context_snapshot.v1",
        },
    )
