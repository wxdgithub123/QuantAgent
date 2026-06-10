"""OpenBB financial-data adapter for local Phase 2 ingestion.

The adapter is used only by explicit refresh jobs. Agent, research, and
backtest reads continue to consume local storage through PIT query helpers.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import reduce
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from app.services.data_platform_ingestion import ingest_records


OPENBB_FINANCIAL_ADAPTER_VERSION = "openbb_financial_adapter.v1"
SOURCE_VERSION = "openbb-sdk"
PIT_RULE = "available_time <= as_of_time"
AGENT_INPUT_POLICY = "local_storage_only"

SUPPORTED_TABLES = {"fundamental_report", "corporate_action", "adjustment_factor"}
STATEMENT_TO_REPORT_TYPE = {
    "income": "income_statement",
    "balance": "balance_sheet",
    "cash": "cash_flow",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper().replace("/", "").replace("-", "")


def _as_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _as_date(value: Any) -> Optional[date]:
    dt = _as_datetime(value)
    return dt.date() if dt else None


def _json_safe(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _first(row: Dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _result_to_dataframe(result: Any) -> pd.DataFrame:
    if result is None:
        return pd.DataFrame()
    if isinstance(result, pd.DataFrame):
        return result.copy()
    if hasattr(result, "to_dataframe"):
        df = result.to_dataframe()
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame(df)
    records = getattr(result, "results", None)
    if records is not None:
        return pd.DataFrame([item.model_dump() if hasattr(item, "model_dump") else getattr(item, "__dict__", item) for item in records])
    if isinstance(result, list):
        return pd.DataFrame(result)
    return pd.DataFrame()


def _iter_rows(data: Any) -> Iterable[Tuple[Any, Dict[str, Any]]]:
    df = _result_to_dataframe(data)
    if df.empty:
        return []
    rows: List[Tuple[Any, Dict[str, Any]]] = []
    index_name = df.index.name or "index"
    for idx, series in df.iterrows():
        row = {str(key): _json_safe(value) for key, value in series.to_dict().items()}
        if index_name not in row:
            row[index_name] = _json_safe(idx)
        rows.append((idx, row))
    return rows


def normalize_fundamental_records(
    symbol: str,
    statement_type: str,
    result: Any,
    *,
    provider: str,
    source_version: str = SOURCE_VERSION,
    period: str = "annual",
    fetched_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Normalize OpenBB financial statement rows into fundamental_report records."""
    fetched_at = fetched_at or _utc_now()
    report_type = STATEMENT_TO_REPORT_TYPE.get(statement_type, statement_type)
    records: List[Dict[str, Any]] = []
    for idx, row in _iter_rows(result):
        period_end = _as_date(_first(row, "period_ending", "period_end", "report_period", "date", "index", "asOfDate")) or _as_date(idx)
        report_date = _as_date(_first(row, "report_date", "filing_date", "date", "period_ending", "index")) or period_end
        fiscal_year_raw = _first(row, "fiscal_year", "year", "calendar_year")
        fiscal_year = int(fiscal_year_raw) if str(fiscal_year_raw or "").isdigit() else (period_end.year if period_end else None)
        fiscal_label = str(_first(row, "fiscal_period", "period", "quarter") or ("FY" if period == "annual" else "Q")).upper()
        fiscal_period = f"{fiscal_year}-{fiscal_label}" if fiscal_year else fiscal_label
        metrics = {
            key: value
            for key, value in row.items()
            if value is not None and key not in {"symbol", "provider"}
        }
        event_time = _as_datetime(report_date or period_end) or fetched_at
        records.append(
            {
                "symbol": _normalize_symbol(symbol),
                "report_type": report_type,
                "fiscal_period": fiscal_period,
                "fiscal_year": fiscal_year,
                "period_end": period_end,
                "report_date": report_date,
                "event_time": event_time,
                "available_time": fetched_at,
                "currency": _first(row, "currency", "reported_currency"),
                "metrics": metrics,
                "units": {"default": "provider_reported"},
                "provider": provider,
                "source_version": source_version,
                "schema_version": "fundamental_report.v1",
                "lineage": {
                    "adapter": OPENBB_FINANCIAL_ADAPTER_VERSION,
                    "openbb_endpoint": f"equity.fundamental.{statement_type}",
                    "period": period,
                },
            }
        )
    return records


def normalize_dividend_actions(
    symbol: str,
    result: Any,
    *,
    provider: str,
    source_version: str = SOURCE_VERSION,
    fetched_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Normalize OpenBB dividend rows into corporate_action records."""
    fetched_at = fetched_at or _utc_now()
    records: List[Dict[str, Any]] = []
    for _, row in _iter_rows(result):
        ex_date = _as_date(_first(row, "ex_dividend_date", "ex_date", "date", "index"))
        if not ex_date:
            continue
        amount = _first(row, "amount", "cash_amount", "dividend", "adjusted_amount")
        event_time = _as_datetime(ex_date) or fetched_at
        records.append(
            {
                "symbol": _normalize_symbol(symbol),
                "action_type": "dividend",
                "ex_date": ex_date,
                "record_date": _as_date(_first(row, "record_date")),
                "payable_date": _as_date(_first(row, "payment_date", "payable_date")),
                "event_time": event_time,
                "available_time": fetched_at,
                "cash_amount": amount,
                "currency": _first(row, "currency"),
                "details": row,
                "provider": provider,
                "source_version": source_version,
                "schema_version": "corporate_action.v1",
                "lineage": {
                    "adapter": OPENBB_FINANCIAL_ADAPTER_VERSION,
                    "openbb_endpoint": "equity.fundamental.dividends",
                },
            }
        )
    return records


def parse_split_adjustment_factor(row: Dict[str, Any]) -> Optional[float]:
    """Return the backward price adjustment factor for a split row.

    For a 4:1 split, pre-split prices are multiplied by 0.25.
    For a 1:10 reverse split, pre-split prices are multiplied by 10.
    """
    numerator = _first(row, "numerator", "to_factor", "new_shares")
    denominator = _first(row, "denominator", "from_factor", "old_shares")
    try:
        num = float(numerator)
        den = float(denominator)
        if num > 0 and den > 0:
            return den / num
    except (TypeError, ValueError):
        pass
    ratio = str(_first(row, "split_ratio", "ratio", "split") or "")
    numbers = re.findall(r"\d+(?:\.\d+)?", ratio)
    if len(numbers) >= 2:
        num = float(numbers[0])
        den = float(numbers[1])
        if num > 0 and den > 0:
            return den / num
    return None


def normalize_split_actions(
    symbol: str,
    result: Any,
    *,
    provider: str,
    source_version: str = SOURCE_VERSION,
    fetched_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Normalize OpenBB split rows into corporate_action records."""
    fetched_at = fetched_at or _utc_now()
    records: List[Dict[str, Any]] = []
    for _, row in _iter_rows(result):
        ex_date = _as_date(_first(row, "date", "ex_date", "execution_date", "index"))
        if not ex_date:
            continue
        factor = parse_split_adjustment_factor(row)
        event_time = _as_datetime(ex_date) or fetched_at
        records.append(
            {
                "symbol": _normalize_symbol(symbol),
                "action_type": "split",
                "ex_date": ex_date,
                "event_time": event_time,
                "available_time": fetched_at,
                "factor": factor,
                "details": row,
                "provider": provider,
                "source_version": source_version,
                "schema_version": "corporate_action.v1",
                "lineage": {
                    "adapter": OPENBB_FINANCIAL_ADAPTER_VERSION,
                    "openbb_endpoint": "equity.fundamental.historical_splits",
                },
            }
        )
    return records


def normalize_adjustment_factors_from_splits(
    symbol: str,
    split_result: Any,
    *,
    provider: str,
    source_version: str = SOURCE_VERSION,
    fetched_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Normalize split rows into independent adjustment_factor records."""
    fetched_at = fetched_at or _utc_now()
    rows: List[Tuple[date, Dict[str, Any], float]] = []
    for _, row in _iter_rows(split_result):
        effective_date = _as_date(_first(row, "date", "ex_date", "execution_date", "index"))
        factor = parse_split_adjustment_factor(row)
        if not effective_date or factor is None:
            continue
        rows.append((effective_date, row, factor))
    cumulative = 1.0
    records: List[Dict[str, Any]] = []
    for effective_date, row, factor in sorted(rows, key=lambda item: item[0]):
        cumulative *= factor
        effective_time = _as_datetime(effective_date) or fetched_at
        records.append(
            {
                "symbol": _normalize_symbol(symbol),
                "factor_type": "split",
                "effective_time": effective_time,
                "event_time": effective_time,
                "available_time": fetched_at,
                "factor": factor,
                "cumulative_factor": cumulative,
                "provider": provider,
                "source_version": source_version,
                "schema_version": "adjustment_factor.v1",
                "lineage": {
                    "adapter": OPENBB_FINANCIAL_ADAPTER_VERSION,
                    "openbb_endpoint": "equity.fundamental.historical_splits",
                    "raw_split": row,
                },
            }
        )
    return records


def _get_openbb_function(root: Any, dotted_path: str) -> Any:
    return reduce(getattr, dotted_path.split("."), root)


async def _call_openbb(dotted_path: str, **kwargs: Any) -> Tuple[Any, Optional[str]]:
    from app.services import openbb_data_service as openbb_module
    from app.services.openbb_data_service import openbb_data_service

    if not await openbb_data_service.ensure_initialized():
        return None, "OpenBB SDK is unavailable"
    try:
        func = _get_openbb_function(openbb_module._obb, dotted_path)
    except Exception as exc:
        return None, f"OpenBB function {dotted_path} is unavailable: {exc}"
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, lambda: func(**kwargs))
        return result, None
    except Exception as exc:
        return None, str(exc)[:240]


async def fetch_openbb_financial_records(
    symbol: str,
    *,
    tables: Optional[List[str]] = None,
    provider: str = "yfinance",
    source_version: str = SOURCE_VERSION,
    period: str = "annual",
    limit: int = 20,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any], List[Dict[str, Any]]]:
    """Fetch provider data and normalize it into local ingestion records."""
    requested_tables = [table for table in (tables or sorted(SUPPORTED_TABLES)) if table in SUPPORTED_TABLES]
    fetched_at = _utc_now()
    provider_id = f"openbb:{provider}"
    records_by_table: Dict[str, List[Dict[str, Any]]] = {table: [] for table in requested_tables}
    errors: List[Dict[str, Any]] = []
    attempted_functions: List[str] = []

    if "fundamental_report" in requested_tables:
        for statement_type in ("income", "balance", "cash"):
            path = "equity.fundamental.reported_financials"
            attempted_functions.append(path)
            result, error = await _call_openbb(
                path,
                symbol=symbol.upper(),
                period=period,
                statement_type=statement_type,
                limit=limit,
            )
            if error or _result_to_dataframe(result).empty:
                fallback_path = f"equity.fundamental.{statement_type}"
                attempted_functions.append(fallback_path)
                result, fallback_error = await _call_openbb(
                    fallback_path,
                    symbol=symbol.upper(),
                    period=period,
                    limit=limit,
                    provider=provider,
                )
                if fallback_error:
                    errors.append({"code": "openbb_fetch_failed", "symbol": symbol, "table": "fundamental_report", "endpoint": fallback_path, "message": fallback_error})
                    continue
            records_by_table["fundamental_report"].extend(
                normalize_fundamental_records(
                    symbol,
                    statement_type,
                    result,
                    provider=provider_id,
                    source_version=source_version,
                    period=period,
                    fetched_at=fetched_at,
                )
            )

    split_result: Any = None
    if "corporate_action" in requested_tables or "adjustment_factor" in requested_tables:
        if "corporate_action" in requested_tables:
            div_path = "equity.fundamental.dividends"
            attempted_functions.append(div_path)
            dividend_result, dividend_error = await _call_openbb(div_path, symbol=symbol.upper(), limit=limit, provider=provider)
            if dividend_error:
                errors.append({"code": "openbb_fetch_failed", "symbol": symbol, "table": "corporate_action", "endpoint": div_path, "message": dividend_error})
            else:
                records_by_table["corporate_action"].extend(
                    normalize_dividend_actions(symbol, dividend_result, provider=provider_id, source_version=source_version, fetched_at=fetched_at)
                )

        split_path = "equity.fundamental.historical_splits"
        attempted_functions.append(split_path)
        split_result, split_error = await _call_openbb(split_path, symbol=symbol.upper())
        if split_error:
            target = "corporate_action" if "corporate_action" in requested_tables else "adjustment_factor"
            errors.append({"code": "openbb_fetch_failed", "symbol": symbol, "table": target, "endpoint": split_path, "message": split_error})
        else:
            if "corporate_action" in requested_tables:
                records_by_table["corporate_action"].extend(
                    normalize_split_actions(symbol, split_result, provider=provider_id, source_version=source_version, fetched_at=fetched_at)
                )
            if "adjustment_factor" in requested_tables:
                records_by_table["adjustment_factor"].extend(
                    normalize_adjustment_factors_from_splits(
                        symbol,
                        split_result,
                        provider=provider_id,
                        source_version=source_version,
                        fetched_at=fetched_at,
                    )
                )

    meta = {
        "adapter_version": OPENBB_FINANCIAL_ADAPTER_VERSION,
        "symbol": _normalize_symbol(symbol),
        "provider": provider_id,
        "source_version": source_version,
        "period": period,
        "limit": limit,
        "tables": requested_tables,
        "attempted_functions": attempted_functions,
        "record_counts": {table: len(rows) for table, rows in records_by_table.items()},
        "external_fetch_performed": True,
        "pit_rule": PIT_RULE,
        "agent_input_policy": AGENT_INPUT_POLICY,
        "external_fallback_allowed": False,
    }
    return records_by_table, meta, errors


async def refresh_openbb_financial_data(
    symbols: List[str],
    *,
    tables: Optional[List[str]] = None,
    provider: str = "yfinance",
    source_version: str = SOURCE_VERSION,
    period: str = "annual",
    limit: int = 20,
    dry_run: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """Fetch OpenBB records and write or validate them through local ingestion."""
    normalized_symbols = [_normalize_symbol(symbol) for symbol in symbols if str(symbol or "").strip()]
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    total_fetched = 0
    total_prepared = 0
    for symbol in normalized_symbols:
        records_by_table, fetch_meta, fetch_errors = await fetch_openbb_financial_records(
            symbol,
            tables=tables,
            provider=provider,
            source_version=source_version,
            period=period,
            limit=limit,
        )
        errors.extend(fetch_errors)
        for table_name, records in records_by_table.items():
            total_fetched += len(records)
            if not records:
                results.append({"symbol": symbol, "table": table_name, "status": "no_records", "rows": [], "fetch_meta": fetch_meta})
                continue
            rows, ingest_meta, ingest_errors = await ingest_records(
                table_name,
                records,
                provider=f"openbb:{provider}",
                source_version=source_version,
                dry_run=dry_run,
                parameters={"provider_refresh": True, "symbol": symbol, "period": period, "limit": limit},
            )
            total_prepared += len(rows)
            errors.extend(ingest_errors)
            results.append(
                {
                    "symbol": symbol,
                    "table": table_name,
                    "status": ingest_meta.get("status"),
                    "rows": rows,
                    "fetch_meta": fetch_meta,
                    "ingest_meta": ingest_meta,
                }
            )
    meta = {
        "adapter_version": OPENBB_FINANCIAL_ADAPTER_VERSION,
        "symbols": normalized_symbols,
        "tables": [table for table in (tables or sorted(SUPPORTED_TABLES)) if table in SUPPORTED_TABLES],
        "provider": f"openbb:{provider}",
        "source_version": source_version,
        "period": period,
        "limit": limit,
        "dry_run": dry_run,
        "total_fetched_records": total_fetched,
        "total_prepared_records": total_prepared,
        "external_fetch_performed": True,
        "local_ingest_performed": not dry_run,
        "pit_rule": PIT_RULE,
        "agent_input_policy": AGENT_INPUT_POLICY,
        "external_fallback_allowed": False,
    }
    return results, meta, errors
