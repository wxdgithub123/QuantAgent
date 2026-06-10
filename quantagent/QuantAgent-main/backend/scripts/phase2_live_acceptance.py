"""Phase 2 live acceptance checks.

This script turns the remaining Phase 2 live-infrastructure risks into a
repeatable gate. By default it is read-only: it checks API shapes and database
metadata without mutating application data. Use --mutating-audit-check to insert
a temporary audit row and prove the append-only trigger rejects UPDATE/DELETE.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

REQUIRED_DATA_PLATFORM_TABLES = [
    "data_provider",
    "instrument",
    "bar_1m",
    "bar_1h",
    "bar_1d",
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

BAR_TABLE_INDEXES = {
    "bar_1m": ["idx_bar_1m_symbol_ts", "idx_bar_1m_available_time"],
    "bar_1h": ["idx_bar_1h_symbol_ts", "idx_bar_1h_available_time"],
    "bar_1d": ["idx_bar_1d_symbol_ts", "idx_bar_1d_available_time"],
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    mode: str
    elapsed_ms: Optional[float] = None


def _to_sync_database_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://") :]
    return url


def _default_database_url() -> str:
    env_value = os.environ.get("DATABASE_URL")
    if env_value:
        return env_value
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "DATABASE_URL":
                return value.strip().strip('"').strip("'")
    return "postgresql+asyncpg://quantagent:quantagent@localhost:5432/quantagent"


def _http_json(base_url: str, path: str, params: dict[str, Any], timeout: float) -> tuple[Any, float]:
    query = f"?{urlencode(params)}" if params else ""
    request = Request(f"{base_url.rstrip('/')}{path}{query}", method="GET")
    start = time.perf_counter()
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload, (time.perf_counter() - start) * 1000


def _http_post_json(base_url: str, path: str, body: dict[str, Any], timeout: float) -> tuple[Any, float]:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload, (time.perf_counter() - start) * 1000


def _api_check(
    base_url: str,
    timeout: float,
    name: str,
    path: str,
    params: dict[str, Any],
    predicate: Callable[[Any], tuple[bool, str]],
    detail: str,
) -> CheckResult:
    try:
        payload, elapsed = _http_json(base_url, path, params, timeout)
        ok, fail_detail = predicate(payload)
        return CheckResult(name, ok, detail if ok else fail_detail, "live-api", round(elapsed, 2))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return CheckResult(name, False, f"live API unavailable or invalid: {exc}", "live-api")


def _api_post_check(
    base_url: str,
    timeout: float,
    name: str,
    path: str,
    body: dict[str, Any],
    predicate: Callable[[Any], tuple[bool, str]],
    detail: str,
) -> CheckResult:
    try:
        payload, elapsed = _http_post_json(base_url, path, body, timeout)
        ok, fail_detail = predicate(payload)
        return CheckResult(name, ok, detail if ok else fail_detail, "live-api", round(elapsed, 2))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return CheckResult(name, False, f"live API unavailable or invalid: {exc}", "live-api")


def build_live_api_checks(base_url: str, timeout: float) -> list[CheckResult]:
    checks = [
        _api_check(
            base_url,
            timeout,
            "api_bars_asof_pit",
            "/api/v1/bars/as-of",
            {"symbol": "BTCUSDT", "interval": "1h", "limit": 5},
            lambda data: (
                isinstance(data, dict)
                and isinstance(data.get("data"), list)
                and data.get("meta", {}).get("pit_rule") == "available_time <= as_of_time"
                and data.get("meta", {}).get("external_fallback_allowed") is False,
                f"unexpected bars/as-of payload: {data}",
            ),
            "bars/as-of returns PIT metadata and disables external fallback.",
        ),
        _api_check(
            base_url,
            timeout,
            "api_snapshot_context_hash",
            "/api/v1/snapshot",
            {"symbol": "BTCUSDT", "interval": "1h", "bar_limit": 5},
            lambda data: (
                isinstance(data, dict)
                and isinstance(data.get("data"), dict)
                and bool(data.get("meta", {}).get("context_hash"))
                and data.get("meta", {}).get("pit_rule") == "available_time <= as_of_time",
                f"unexpected snapshot payload: {data}",
            ),
            "snapshot returns context hash and PIT evidence.",
        ),
        _api_check(
            base_url,
            timeout,
            "api_storage_contract",
            "/api/v1/meta/storage-contract",
            {},
            lambda data: (
                isinstance(data, dict)
                and "bar_1m" in data.get("data", {}).get("tables", {})
                and "etl_job_log" in data.get("data", {}).get("tables", {})
                and data.get("data", {}).get("visibility_rule") == "available_time <= as_of_time"
                and data.get("data", {}).get("agent_input_policy") == "local_storage_only",
                f"unexpected storage-contract payload: {data}",
            ),
            "storage contract exposes required tables and local/PIT rules.",
        ),
        _api_check(
            base_url,
            timeout,
            "api_phase2_ops_monitor",
            "/api/v1/system/phase2-ops-monitor",
            {},
            lambda data: (
                isinstance(data, dict)
                and data.get("pit_rule") == "available_time <= as_of_time"
                and data.get("agent_input_policy") == "local_storage_only"
                and data.get("external_fallback_allowed") is False
                and isinstance(data.get("audit_health"), dict)
                and isinstance(data.get("execution_risk"), dict),
                f"unexpected phase2-ops-monitor payload: {data}",
            ),
            "ops monitor reports PIT/local-only boundary plus audit and execution/risk sections.",
        ),
        _api_check(
            base_url,
            timeout,
            "api_trading_workbench",
            "/api/v1/trading/workbench",
            {},
            lambda data: (
                isinstance(data, dict)
                and data.get("schema_version") == "paper_trading_workbench.v1"
                and (
                    data.get("safety", {}).get("live_broker_submission") is False
                    or data.get("mode", {}).get("live_broker_submission") is False
                )
                and (
                    isinstance(data.get("execution_chain"), list)
                    or isinstance(data.get("execution_chain", {}).get("chain"), list)
                )
                and data.get("risk_guard", {}).get("required_before_fill") is True,
                f"unexpected trading/workbench payload: {data}",
            ),
            "paper-trading workbench exposes execution chain and live-broker-disabled safety.",
        ),
        _api_check(
            base_url,
            timeout,
            "api_risk_config_prd_rules",
            "/api/v1/risk/config-metadata",
            {},
            lambda data: (
                isinstance(data, dict)
                and data.get("schema_version") == "risk_config.v1"
                and "MIN_ORDER_NOTIONAL" in data.get("config", {})
                and "WAIT_ORDER_INTENT_POLICY" in data.get("config", {})
                and "RISK_FAILURE_ACTION" in data.get("config", {}),
                f"unexpected risk config metadata payload: {data}",
            ),
            "RiskGuard metadata exposes min notional, WAIT policy, and failure action.",
        ),
        _api_post_check(
            base_url,
            timeout,
            "api_openbb_refresh_dry_run",
            "/api/v1/meta/refresh-financials",
            {"symbols": ["AAPL"], "tables": ["fundamental_report"], "dry_run": True},
            lambda data: (
                isinstance(data, dict)
                and data.get("meta", {}).get("dry_run") is True
                and data.get("meta", {}).get("external_fallback_allowed") is False
                and data.get("meta", {}).get("agent_input_policy") == "local_storage_only",
                f"unexpected refresh-financials dry-run payload: {data}",
            ),
            "OpenBB refresh dry-run is explicit and still reports local-only Agent boundary.",
        ),
    ]
    return checks


async def _scalar(conn: Any, sql: str, *args: Any) -> Any:
    row = await conn.fetchrow(sql, *args)
    if not row:
        return None
    return row[0]


async def _db_check(
    name: str,
    conn: Any,
    check: Callable[[Any], Awaitable[tuple[bool, str]]],
    detail: str,
) -> CheckResult:
    start = time.perf_counter()
    try:
        ok, fail_detail = await check(conn)
        return CheckResult(name, ok, detail if ok else fail_detail, "live-db", round((time.perf_counter() - start) * 1000, 2))
    except Exception as exc:
        return CheckResult(name, False, f"database check failed: {exc}", "live-db")


async def _check_alembic_head(conn: Any) -> tuple[bool, str]:
    exists = await _scalar(conn, "SELECT to_regclass('public.alembic_version') IS NOT NULL")
    if not exists:
        return False, "alembic_version table is missing"
    version = await _scalar(conn, "SELECT version_num FROM alembic_version LIMIT 1")
    return str(version) == "017", f"expected alembic head 017, got {version!r}"


async def _check_required_tables(conn: Any) -> tuple[bool, str]:
    rows = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = ANY($1::text[])
        """,
        REQUIRED_DATA_PLATFORM_TABLES,
    )
    present = {row["table_name"] for row in rows}
    missing = [table for table in REQUIRED_DATA_PLATFORM_TABLES if table not in present]
    return not missing, f"missing data-platform tables: {missing}"


async def _check_pit_columns(conn: Any) -> tuple[bool, str]:
    tables = [
        "instrument",
        "bar_1m",
        "bar_1h",
        "bar_1d",
        "quote_latest",
        "fundamental_report",
        "corporate_action",
        "adjustment_factor",
        "news_event",
        "macro_indicator",
    ]
    rows = await conn.fetch(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = ANY($1::text[])
          AND column_name = ANY($2::text[])
        """,
        tables,
        ["event_time", "ingest_time", "available_time"],
    )
    by_table: dict[str, set[str]] = {table: set() for table in tables}
    for row in rows:
        by_table[row["table_name"]].add(row["column_name"])
    missing = {table: sorted({"event_time", "ingest_time", "available_time"} - cols) for table, cols in by_table.items() if {"event_time", "ingest_time", "available_time"} - cols}
    return not missing, f"missing PIT columns: {missing}"


async def _check_bar_indexes(conn: Any) -> tuple[bool, str]:
    expected = [name for names in BAR_TABLE_INDEXES.values() for name in names]
    rows = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname = ANY($1::text[])", expected)
    present = {row["indexname"] for row in rows}
    missing = [name for name in expected if name not in present]
    return not missing, f"missing bar indexes: {missing}"


async def _check_timescale_contract(conn: Any) -> tuple[bool, str]:
    policy_rows = await conn.fetch(
        """
        SELECT policy_id, status
        FROM data_platform_storage_policy
        WHERE policy_id = ANY($1::text[])
        """,
        [
            "bar_1m_compression",
            "bar_1h_compression",
            "bar_1d_compression",
            "bar_1m_retention",
            "bar_1h_retention",
            "bar_1d_retention",
            "postgres_pitr",
        ],
    )
    present = {row["policy_id"] for row in policy_rows}
    missing = {"bar_1m_compression", "bar_1h_compression", "bar_1d_compression", "bar_1m_retention", "bar_1h_retention", "bar_1d_retention", "postgres_pitr"} - present
    if missing:
        return False, f"missing storage policies: {sorted(missing)}"

    timescale_installed = bool(
        await _scalar(conn, "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb')")
    )
    hypertable_count = 0
    if timescale_installed:
        hypertable_count = int(
            await _scalar(
                conn,
                """
                SELECT COUNT(*)
                FROM timescaledb_information.hypertables
                WHERE hypertable_name = ANY($1::text[])
                """,
                ["bar_1m", "bar_1h", "bar_1d"],
            )
            or 0
        )
    if timescale_installed and hypertable_count < 3:
        return False, f"TimescaleDB installed but expected 3 bar hypertables, got {hypertable_count}"
    return True, "storage policies declared and Timescale hypertables are valid when extension is installed"


async def _check_audit_append_only_metadata(conn: Any) -> tuple[bool, str]:
    trigger = await _scalar(
        conn,
        """
        SELECT EXISTS (
          SELECT 1 FROM pg_trigger
          WHERE tgname = 'trg_prevent_audit_logs_mutation'
        )
        """,
    )
    immutable_column = await _scalar(
        conn,
        """
        SELECT EXISTS (
          SELECT 1 FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name = 'audit_logs'
            AND column_name = 'immutable'
        )
        """,
    )
    return bool(trigger and immutable_column), f"append-only trigger={trigger}, immutable column={immutable_column}"


async def _check_audit_append_only_rejection(conn: Any) -> tuple[bool, str]:
    table_exists = await _scalar(conn, "SELECT to_regclass('public.audit_logs') IS NOT NULL")
    if not table_exists:
        return False, "audit_logs table is missing"
    test_action = f"PHASE2_LIVE_APPEND_ONLY_PROOF_{int(time.time() * 1000)}"
    row_id = await _scalar(
        conn,
        """
        INSERT INTO audit_logs (action, user_id, resource, details, ip_address, immutable)
        VALUES ($1, 'phase2_live_acceptance', 'audit_logs', '{"append_only_proof": true}'::jsonb, 'internal', TRUE)
        RETURNING id
        """,
        test_action,
    )
    update_rejected = False
    delete_rejected = False
    try:
        await conn.execute("UPDATE audit_logs SET resource = 'mutated' WHERE id = $1", row_id)
    except Exception as exc:
        update_rejected = "append-only" in str(exc).lower() or "audit_logs" in str(exc).lower()
    try:
        await conn.execute("DELETE FROM audit_logs WHERE id = $1", row_id)
    except Exception as exc:
        delete_rejected = "append-only" in str(exc).lower() or "audit_logs" in str(exc).lower()
    return update_rejected and delete_rejected, f"update_rejected={update_rejected}, delete_rejected={delete_rejected}, proof_row_id={row_id}"


async def build_live_db_checks(database_url: str, mutating_audit_check: bool) -> list[CheckResult]:
    import asyncpg

    conn = await asyncpg.connect(_to_sync_database_url(database_url))
    try:
        checks = [
            await _db_check("db_alembic_head", conn, _check_alembic_head, "alembic head is at revision 017."),
            await _db_check("db_data_platform_tables", conn, _check_required_tables, "all data-platform contract tables exist."),
            await _db_check("db_pit_columns", conn, _check_pit_columns, "PIT event/ingest/available columns exist on required tables."),
            await _db_check("db_bar_indexes", conn, _check_bar_indexes, "bar tables expose required symbol/ts and available_time indexes."),
            await _db_check("db_timescale_storage_policy", conn, _check_timescale_contract, "Timescale/compression/retention/PITR policies are declared and hypertables are valid when TimescaleDB is installed."),
            await _db_check("db_audit_append_only_metadata", conn, _check_audit_append_only_metadata, "audit append-only trigger and immutable column are present."),
        ]
        if mutating_audit_check:
            checks.append(
                await _db_check(
                    "db_audit_append_only_rejection",
                    conn,
                    _check_audit_append_only_rejection,
                    "audit append-only trigger rejects UPDATE and DELETE on an immutable proof row.",
                )
            )
        else:
            checks.append(
                CheckResult(
                    "db_audit_append_only_rejection",
                    True,
                    "skipped by default; rerun with --mutating-audit-check to insert an immutable proof row and prove UPDATE/DELETE rejection.",
                    "live-db-skip",
                )
            )
        return checks
    finally:
        await conn.close()


def run_alembic_upgrade(database_url: str) -> CheckResult:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    start = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(BACKEND_ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=120,
        )
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[-1200:]
            return CheckResult("alembic_upgrade_head", False, detail or "alembic failed without output", "migration", elapsed)
        return CheckResult("alembic_upgrade_head", True, "alembic upgrade head completed.", "migration", elapsed)
    except Exception as exc:
        return CheckResult("alembic_upgrade_head", False, f"alembic upgrade failed: {exc}", "migration")


async def async_main(args: argparse.Namespace) -> list[CheckResult]:
    results: list[CheckResult] = []
    if args.run_migrations:
        results.append(run_alembic_upgrade(args.database_url))
    if args.api_base:
        results.extend(build_live_api_checks(args.api_base, args.timeout))
    if args.database_url:
        try:
            results.extend(await build_live_db_checks(args.database_url, args.mutating_audit_check))
        except Exception as exc:
            results.append(CheckResult("db_connection", False, f"database unavailable: {exc}", "live-db"))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 live acceptance checks.")
    parser.add_argument("--api-base", default="http://localhost:8002", help="Backend API base URL. Use empty string to skip API checks.")
    parser.add_argument("--database-url", default=_default_database_url(), help="PostgreSQL database URL. Use empty string to skip DB checks.")
    parser.add_argument("--run-migrations", action="store_true", help="Run alembic upgrade head before DB checks.")
    parser.add_argument("--mutating-audit-check", action="store_true", help="Insert a temporary audit row and prove UPDATE/DELETE are rejected.")
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    results = asyncio.run(async_main(args))
    failed = [result for result in results if not result.ok]
    if args.json:
        print(json.dumps({"ok": not failed, "results": [asdict(result) for result in results]}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            elapsed = f", {result.elapsed_ms:.2f}ms" if result.elapsed_ms is not None else ""
            print(f"[{status}] {result.name} ({result.mode}{elapsed}) - {result.detail}")
        print(f"\nSummary: {len(results) - len(failed)}/{len(results)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
