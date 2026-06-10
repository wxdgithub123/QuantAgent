import pytest

from backend.scripts import phase2_live_acceptance as live


def test_to_sync_database_url_converts_asyncpg_driver():
    assert (
        live._to_sync_database_url("postgresql+asyncpg://user:pass@localhost:5432/db")
        == "postgresql://user:pass@localhost:5432/db"
    )
    assert live._to_sync_database_url("postgresql://user:pass@localhost/db") == "postgresql://user:pass@localhost/db"


def test_default_database_url_reads_env_without_importing_app_settings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://env/db")

    assert live._default_database_url() == "postgresql+asyncpg://env/db"


def test_live_api_checks_are_declared_for_remaining_phase2_risks(monkeypatch):
    calls = []

    def fake_api_check(base_url, timeout, name, path, params, predicate, detail):
        calls.append((name, path, params))
        return live.CheckResult(name, True, detail, "test")

    def fake_api_post_check(base_url, timeout, name, path, body, predicate, detail):
        calls.append((name, path, body))
        return live.CheckResult(name, True, detail, "test")

    monkeypatch.setattr(live, "_api_check", fake_api_check)
    monkeypatch.setattr(live, "_api_post_check", fake_api_post_check)

    results = live.build_live_api_checks("http://localhost:8002", 1)
    names = {result.name for result in results}
    paths = {path for _, path, _ in calls}

    assert "api_phase2_ops_monitor" in names
    assert "api_trading_workbench" in names
    assert "api_openbb_refresh_dry_run" in names
    assert "/api/v1/system/phase2-ops-monitor" in paths
    assert "/api/v1/trading/workbench" in paths
    assert "/api/v1/meta/refresh-financials" in paths


class FakeConn:
    def __init__(self):
        self.updated = False
        self.deleted = False

    async def fetchrow(self, sql, *args):
        if "alembic_version" in sql and "to_regclass" in sql:
            return (True,)
        if "version_num" in sql:
            return ("017",)
        if "pg_trigger" in sql:
            return (True,)
        if "information_schema.columns" in sql and "audit_logs" in sql:
            return (True,)
        return (None,)

    async def fetch(self, sql, *args):
        if "information_schema.tables" in sql:
            return [{"table_name": table} for table in live.REQUIRED_DATA_PLATFORM_TABLES]
        if "information_schema.columns" in sql:
            tables = args[0]
            return [
                {"table_name": table, "column_name": column}
                for table in tables
                for column in ["event_time", "ingest_time", "available_time"]
            ]
        if "pg_indexes" in sql:
            expected = args[0]
            return [{"indexname": name} for name in expected]
        if "data_platform_storage_policy" in sql:
            return [
                {"policy_id": policy_id, "status": "declared"}
                for policy_id in args[0]
            ]
        return []


@pytest.mark.asyncio
async def test_db_metadata_checks_accept_complete_contract():
    conn = FakeConn()

    assert await live._check_alembic_head(conn) == (True, "expected alembic head 017, got '017'")
    assert (await live._check_required_tables(conn))[0] is True
    assert (await live._check_pit_columns(conn))[0] is True
    assert (await live._check_bar_indexes(conn))[0] is True
    assert (await live._check_audit_append_only_metadata(conn))[0] is True


@pytest.mark.asyncio
async def test_required_tables_check_reports_missing_tables():
    class MissingConn(FakeConn):
        async def fetch(self, sql, *args):
            if "information_schema.tables" in sql:
                return [{"table_name": "instrument"}]
            return await super().fetch(sql, *args)

    ok, detail = await live._check_required_tables(MissingConn())

    assert ok is False
    assert "bar_1m" in detail
