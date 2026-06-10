"""Idempotent local ingestion helpers for Phase 2 financial data tables."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.services.data_platform_storage import serialize_storage_value
from app.services.database import get_db


DATA_PLATFORM_INGEST_TIMEOUT_SECONDS = 10.0


JSON_COLUMNS = {
    "metrics",
    "units",
    "details",
    "lineage",
}


INGESTION_TABLE_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "fundamental_report": {
        "schema_version": "fundamental_report.v1",
        "data_type": "fundamental",
        "identity_fields": ["symbol", "report_type", "fiscal_period", "fiscal_year", "period_end"],
        "event_time_fallbacks": ["event_time", "report_date", "period_end"],
        "columns": [
            "record_id",
            "instrument_id",
            "symbol",
            "report_type",
            "fiscal_period",
            "fiscal_year",
            "period_start",
            "period_end",
            "report_date",
            "event_time",
            "ingest_time",
            "available_time",
            "currency",
            "metrics",
            "units",
            "provider",
            "source_version",
            "schema_version",
            "cleaning_rule_version",
            "raw_payload_hash",
            "lineage",
        ],
        "json_columns": {"metrics", "units", "lineage"},
        "required_fields": ["symbol", "report_type"],
    },
    "corporate_action": {
        "schema_version": "corporate_action.v1",
        "data_type": "corporate_action",
        "identity_fields": ["symbol", "action_type", "event_time", "ex_date", "record_date"],
        "event_time_fallbacks": ["event_time", "ex_date", "record_date"],
        "columns": [
            "record_id",
            "instrument_id",
            "symbol",
            "action_type",
            "ex_date",
            "record_date",
            "payable_date",
            "event_time",
            "ingest_time",
            "available_time",
            "factor",
            "cash_amount",
            "currency",
            "details",
            "provider",
            "source_version",
            "schema_version",
            "raw_payload_hash",
            "lineage",
        ],
        "json_columns": {"details", "lineage"},
        "required_fields": ["symbol", "action_type"],
    },
    "adjustment_factor": {
        "schema_version": "adjustment_factor.v1",
        "data_type": "adjustment_factor",
        "identity_fields": ["symbol", "factor_type", "effective_time"],
        "event_time_fallbacks": ["event_time", "effective_time"],
        "columns": [
            "record_id",
            "instrument_id",
            "symbol",
            "corporate_action_id",
            "factor_type",
            "effective_time",
            "event_time",
            "ingest_time",
            "available_time",
            "factor",
            "cumulative_factor",
            "provider",
            "source_version",
            "schema_version",
            "lineage",
        ],
        "json_columns": {"lineage"},
        "required_fields": ["symbol", "factor_type", "factor"],
    },
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return serialize_storage_value(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _hash_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        text_value = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text_value)
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _event_time_from_record(record: Dict[str, Any], fallback_fields: List[str]) -> datetime:
    for field in fallback_fields:
        parsed = _parse_datetime(record.get(field))
        if parsed is not None:
            return parsed
    return _utc_now()


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("-", "")


def prepare_ingest_record(
    table_name: str,
    record: Dict[str, Any],
    *,
    provider: str,
    source_version: str = "default",
    batch_id: Optional[str] = None,
    ingest_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Normalize and enrich one provider record before PostgreSQL upsert."""
    if table_name not in INGESTION_TABLE_CONTRACTS:
        raise ValueError(f"Unsupported data platform ingestion table: {table_name}")
    if not isinstance(record, dict):
        raise ValueError("Ingestion record must be an object")

    contract = INGESTION_TABLE_CONTRACTS[table_name]
    missing = [field for field in contract["required_fields"] if record.get(field) in (None, "")]
    if missing:
        raise ValueError(f"{table_name} record missing required fields: {missing}")

    now = ingest_time or _utc_now()
    prepared: Dict[str, Any] = {key: record.get(key) for key in contract["columns"] if key in record}
    prepared["symbol"] = _normalize_symbol(prepared.get("symbol") or record.get("symbol"))
    prepared["provider"] = str(prepared.get("provider") or provider)
    prepared["source_version"] = str(prepared.get("source_version") or source_version or "default")
    prepared["schema_version"] = str(prepared.get("schema_version") or contract["schema_version"])
    prepared["event_time"] = _parse_datetime(prepared.get("event_time")) or _event_time_from_record(
        record,
        contract["event_time_fallbacks"],
    )
    prepared["ingest_time"] = _parse_datetime(prepared.get("ingest_time")) or now
    prepared["available_time"] = _parse_datetime(prepared.get("available_time")) or prepared["event_time"]
    if prepared["available_time"] < prepared["event_time"]:
        raise ValueError("available_time must be greater than or equal to event_time")

    raw_payload_hash = prepared.get("raw_payload_hash")
    if not raw_payload_hash:
        raw_payload_hash = _hash_id("raw", table_name, _canonical_json(record))
    prepared["raw_payload_hash"] = raw_payload_hash

    identity = [prepared.get(field) or record.get(field) for field in contract["identity_fields"]]
    prepared["record_id"] = prepared.get("record_id") or _hash_id(
        table_name,
        *identity,
        prepared["provider"],
        prepared["source_version"],
    )
    lineage = prepared.get("lineage")
    lineage_dict = lineage if isinstance(lineage, dict) else {}
    prepared["lineage"] = {
        "provider": prepared["provider"],
        "source_version": prepared["source_version"],
        "batch_id": batch_id,
        "raw_payload_hash": raw_payload_hash,
        **lineage_dict,
    }

    for column in contract["json_columns"]:
        if column not in prepared or prepared[column] is None:
            prepared[column] = {} if column != "symbols" else []

    return {column: prepared.get(column) for column in contract["columns"] if column in prepared}


def build_upsert_statement(table_name: str, record: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Build a whitelisted PostgreSQL upsert statement for one normalized record."""
    if table_name not in INGESTION_TABLE_CONTRACTS:
        raise ValueError(f"Unsupported data platform ingestion table: {table_name}")
    contract = INGESTION_TABLE_CONTRACTS[table_name]
    json_columns = contract["json_columns"]
    columns = [column for column in contract["columns"] if column in record]
    if "record_id" not in columns:
        raise ValueError("record_id is required for idempotent upsert")

    values_sql = []
    params: Dict[str, Any] = {}
    for column in columns:
        if column in json_columns:
            values_sql.append(f"CAST(:{column} AS JSONB)")
            params[column] = _canonical_json(record.get(column) if record.get(column) is not None else {})
        else:
            values_sql.append(f":{column}")
            params[column] = record.get(column)

    update_columns = [column for column in columns if column not in {"record_id", "created_at"}]
    set_sql = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
    if "updated_at" not in update_columns:
        set_sql = f"{set_sql}, updated_at = now()" if set_sql else "updated_at = now()"

    sql = f"""
        INSERT INTO {table_name} ({", ".join(columns)})
        VALUES ({", ".join(values_sql)})
        ON CONFLICT (record_id) DO UPDATE
        SET {set_sql}
        RETURNING record_id
    """
    return sql, params


def build_lineage_statement(table_name: str, record: Dict[str, Any], *, batch_id: str) -> Tuple[str, Dict[str, Any]]:
    lineage_id = _hash_id("lineage", table_name, record["record_id"], batch_id)
    lineage_payload = {
        "record_id": lineage_id,
        "entity_table": table_name,
        "entity_record_id": record["record_id"],
        "provider": record.get("provider"),
        "etl_batch_id": batch_id,
        "upstream_record_ids": record.get("lineage", {}).get("upstream_record_ids", []),
        "transformation": "data_platform_ingestion.upsert",
        "cleaning_rule_version": record.get("cleaning_rule_version"),
        "source_version": record.get("source_version"),
        "lineage": record.get("lineage", {}),
    }
    sql = """
        INSERT INTO data_lineage (
            record_id, entity_table, entity_record_id, provider, etl_batch_id,
            upstream_record_ids, transformation, cleaning_rule_version,
            source_version, lineage
        )
        VALUES (
            :record_id, :entity_table, :entity_record_id, :provider, :etl_batch_id,
            CAST(:upstream_record_ids AS JSONB), :transformation, :cleaning_rule_version,
            :source_version, CAST(:lineage AS JSONB)
        )
        ON CONFLICT (record_id) DO NOTHING
    """
    params = {
        **lineage_payload,
        "upstream_record_ids": _canonical_json(lineage_payload["upstream_record_ids"]),
        "lineage": _canonical_json(lineage_payload["lineage"]),
    }
    return sql, params


def build_etl_job_log_statement(
    *,
    table_name: str,
    provider: str,
    batch_id: str,
    status: str,
    records: List[Dict[str, Any]],
    parameters: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    contract = INGESTION_TABLE_CONTRACTS[table_name]
    symbols = sorted({record.get("symbol") for record in records if record.get("symbol")})
    now = _utc_now()
    sql = """
        INSERT INTO etl_job_log (
            batch_id, job_type, status, provider, data_type, symbols, parameters,
            idempotency_key, started_at, finished_at, ingest_time, available_time,
            rows_read, rows_written, rows_duplicate, error, lineage
        )
        VALUES (
            :batch_id, :job_type, :status, :provider, :data_type, CAST(:symbols AS JSONB),
            CAST(:parameters AS JSONB), :idempotency_key, :started_at, :finished_at,
            :ingest_time, :available_time, :rows_read, :rows_written, :rows_duplicate,
            :error, CAST(:lineage AS JSONB)
        )
        ON CONFLICT (batch_id) DO UPDATE
        SET status = EXCLUDED.status,
            finished_at = EXCLUDED.finished_at,
            rows_read = EXCLUDED.rows_read,
            rows_written = EXCLUDED.rows_written,
            rows_duplicate = EXCLUDED.rows_duplicate,
            error = EXCLUDED.error,
            lineage = EXCLUDED.lineage
    """
    params = {
        "batch_id": batch_id,
        "job_type": f"{contract['data_type']}_upsert",
        "status": status,
        "provider": provider,
        "data_type": contract["data_type"],
        "symbols": _canonical_json(symbols),
        "parameters": _canonical_json(parameters or {}),
        "idempotency_key": f"{table_name}:{batch_id}",
        "started_at": now,
        "finished_at": now,
        "ingest_time": now,
        "available_time": now,
        "rows_read": len(records),
        "rows_written": len(records) if status == "success" else 0,
        "rows_duplicate": 0,
        "error": error,
        "lineage": _canonical_json({"table": table_name, "record_ids": [record.get("record_id") for record in records]}),
    }
    return sql, params


async def ingest_records(
    table_name: str,
    records: List[Dict[str, Any]],
    *,
    provider: str,
    source_version: str = "default",
    batch_id: Optional[str] = None,
    dry_run: bool = False,
    parameters: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """Upsert normalized records, lineage, and an ETL job log into local storage."""
    if table_name not in INGESTION_TABLE_CONTRACTS:
        raise ValueError(f"Unsupported data platform ingestion table: {table_name}")
    if not isinstance(records, list):
        raise ValueError("records must be a list")

    batch = batch_id or _hash_id("batch", table_name, provider, source_version, _canonical_json(records))
    prepared_records = [
        prepare_ingest_record(
            table_name,
            record,
            provider=provider,
            source_version=source_version,
            batch_id=batch,
        )
        for record in records
    ]
    meta = {
        "batch_id": batch,
        "table": table_name,
        "provider": provider,
        "source_version": source_version,
        "count": len(prepared_records),
        "write_mode": "transactional bulk upsert",
        "idempotency": "record_id",
        "pit_rule": "available_time <= as_of_time",
        "agent_input_policy": "local_storage_only",
        "external_fallback_allowed": False,
        "dry_run": dry_run,
    }
    if dry_run:
        return prepared_records, {**meta, "status": "validated"}, []

    try:
        async with get_db() as session:
            async def _write() -> None:
                for record in prepared_records:
                    sql, params = build_upsert_statement(table_name, record)
                    await session.execute(text(sql), params)
                    lineage_sql, lineage_params = build_lineage_statement(table_name, record, batch_id=batch)
                    await session.execute(text(lineage_sql), lineage_params)
                job_sql, job_params = build_etl_job_log_statement(
                    table_name=table_name,
                    provider=provider,
                    batch_id=batch,
                    status="success",
                    records=prepared_records,
                    parameters=parameters,
                )
                await session.execute(text(job_sql), job_params)

            await asyncio.wait_for(_write(), timeout=DATA_PLATFORM_INGEST_TIMEOUT_SECONDS)
        return prepared_records, {**meta, "status": "success"}, []
    except Exception as exc:
        return (
            [],
            {**meta, "status": "local_storage_unavailable"},
            [{"code": "local_storage_unavailable", "message": str(exc)[:240], "table": table_name}],
        )
