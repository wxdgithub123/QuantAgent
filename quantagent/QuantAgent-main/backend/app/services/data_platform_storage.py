"""Local PostgreSQL storage helpers for the Phase 2 data platform contract."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.services.database import get_db


DATA_PLATFORM_QUERY_TIMEOUT_SECONDS = 1.5
PIT_RULE = "available_time <= as_of_time"


TABLE_QUERY_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "fundamental_report": {
        "schema_version": "fundamental_report.v1",
        "storage_contract": "fundamental_report",
        "order_by": "available_time DESC, event_time DESC, id DESC",
        "pit_columns": ["event_time", "ingest_time", "available_time"],
    },
    "corporate_action": {
        "schema_version": "corporate_action.v1",
        "storage_contract": "corporate_action",
        "order_by": "available_time DESC, event_time DESC, id DESC",
        "pit_columns": ["event_time", "ingest_time", "available_time"],
    },
    "adjustment_factor": {
        "schema_version": "adjustment_factor.v1",
        "storage_contract": "adjustment_factor",
        "order_by": "effective_time DESC, available_time DESC, id DESC",
        "pit_columns": ["effective_time", "event_time", "ingest_time", "available_time"],
    },
}


def normalize_as_of_time(value: Optional[datetime]) -> datetime:
    """Normalize caller supplied as_of_time to timezone-aware UTC."""
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def serialize_storage_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: serialize_storage_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_storage_value(item) for item in value]
    return value


def serialize_storage_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {key: serialize_storage_value(value) for key, value in record.items()}


def build_pit_query(
    table_name: str,
    *,
    symbol: str,
    limit: int,
    as_of_time: Optional[datetime] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Build a whitelisted PIT query for a local storage-contract table."""
    if table_name not in TABLE_QUERY_CONTRACTS:
        raise ValueError(f"Unsupported data platform table: {table_name}")
    contract = TABLE_QUERY_CONTRACTS[table_name]
    normalized_symbol = symbol.upper()
    safe_limit = max(1, min(int(limit), 1000))
    as_of = normalize_as_of_time(as_of_time)
    sql = f"""
        SELECT *
        FROM {table_name}
        WHERE symbol = :symbol
          AND available_time <= :as_of_time
        ORDER BY {contract["order_by"]}
        LIMIT :limit
    """
    return sql, {"symbol": normalized_symbol, "as_of_time": as_of, "limit": safe_limit}


async def query_pit_records(
    table_name: str,
    *,
    symbol: str,
    limit: int = 20,
    as_of_time: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """Query local PostgreSQL records with a strict PIT boundary."""
    contract = TABLE_QUERY_CONTRACTS[table_name]
    sql, params = build_pit_query(
        table_name,
        symbol=symbol,
        limit=limit,
        as_of_time=as_of_time,
    )
    meta = {
        "symbol": params["symbol"],
        "limit": params["limit"],
        "as_of_time": serialize_storage_value(params["as_of_time"]),
        "pit_rule": PIT_RULE,
        "agent_input_policy": "local_storage_only",
        "external_fallback_allowed": False,
        "storage_contract": contract["storage_contract"],
        "schema_version": contract["schema_version"],
    }
    try:
        async with get_db() as session:
            result = await asyncio.wait_for(
                session.execute(text(sql), params),
                timeout=DATA_PLATFORM_QUERY_TIMEOUT_SECONDS,
            )
            rows = [serialize_storage_record(dict(row)) for row in result.mappings().all()]
        status = "ok" if rows else "not_ingested_yet"
        return rows, {**meta, "count": len(rows), "status": status}, []
    except Exception as exc:
        return (
            [],
            {**meta, "count": 0, "status": "local_storage_unavailable"},
            [
                {
                    "code": "local_storage_unavailable",
                    "message": str(exc)[:240],
                    "storage_contract": contract["storage_contract"],
                }
            ],
        )
