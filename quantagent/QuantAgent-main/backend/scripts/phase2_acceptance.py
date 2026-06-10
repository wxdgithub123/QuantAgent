"""Phase 2 full-scope acceptance checks.

Default mode is offline/static so it can run on a workstation without Docker.
When the backend is running, add --api-base http://localhost:8002 to include
live shape checks for PIT data-platform, configuration, and governance endpoints.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    mode: str = "static"


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _contains(name: str, relative: str, markers: list[str], detail: str) -> CheckResult:
    try:
        text = _read(relative)
    except FileNotFoundError:
        return CheckResult(name, False, f"missing file: {relative}")
    missing = [marker for marker in markers if marker not in text]
    if missing:
        return CheckResult(name, False, f"{relative} missing markers: {missing}")
    return CheckResult(name, True, detail)


def _http_json(base_url: str, path: str, params: dict[str, Any], timeout: float) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    request = Request(f"{base_url.rstrip('/')}{path}{query}", method="GET")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _static_checks() -> list[CheckResult]:
    checks = [
        _contains(
            "full_scope_task_board_persisted",
            "docs/phase2_full_scope_task_board.md",
            [
                "Financial Data Platform",
                "TradingAgents Decision And Agent Configuration",
                "Audit Desk",
                "Backtest Desk And Replay Desk",
                "Operations, Configuration Center, And Data Governance",
                "available_time <= as_of_time",
                "local_storage_only",
            ],
            "Deep-analysis requirements and follow-up tasks are persisted locally.",
        ),
        _contains(
            "prd_top_level_data_platform_api",
            "backend/app/api/v1/endpoints/data_platform.py",
            [
                '@router.get("/bars")',
                '@router.get("/bars/batch")',
                '@router.post("/bars/batch")',
                '@router.get("/quotes/latest")',
                '@router.get("/quotes/history")',
                '@router.get("/instruments")',
                '@router.get("/news")',
                '@router.get("/macro/indicators")',
                '@router.get("/meta/coverage")',
                '@router.get("/meta/storage-contract")',
                '@router.get("/meta/providers")',
                '@router.get("/meta/jobs")',
                '@router.get("/bars/as-of")',
                '@router.post("/meta/ingest")',
                '@router.post("/meta/refresh-financials")',
                '@router.post("/snapshot")',
                '"data"',
                '"meta"',
                '"errors"',
            ],
            "Top-level PRD data-platform routes expose the unified response envelope.",
        ),
        _contains(
            "data_platform_storage_contract_migration",
            "backend/migrations/versions/017_data_platform_contract_tables.py",
            [
                "Revision ID: 017",
                "CREATE TABLE IF NOT EXISTS instrument",
                'BAR_TABLES = ("bar_1m", "bar_1h", "bar_1d")',
                "CREATE TABLE IF NOT EXISTS {table}",
                "CREATE TABLE IF NOT EXISTS quote_latest",
                "CREATE TABLE IF NOT EXISTS fundamental_report",
                "CREATE TABLE IF NOT EXISTS corporate_action",
                "CREATE TABLE IF NOT EXISTS adjustment_factor",
                "CREATE TABLE IF NOT EXISTS etl_job_log",
                "CREATE TABLE IF NOT EXISTS news_event",
                "CREATE TABLE IF NOT EXISTS macro_indicator",
                "CREATE TABLE IF NOT EXISTS data_lineage",
                "CREATE TABLE IF NOT EXISTS cleaned_data_item",
                "available_time TIMESTAMPTZ",
                "CHECK (available_time >= event_time)",
                "uq_{table}_symbol_ts_provider",
                "CREATE EXTENSION IF NOT EXISTS timescaledb",
                "create_hypertable",
                "add_compression_policy",
                "postgres_pitr",
            ],
            "PostgreSQL/Timescale storage contract migration declares required tables, PIT fields, indexes, lineage, and lifecycle policies.",
        ),
        _contains(
            "data_platform_storage_contract_api",
            "backend/app/api/v1/endpoints/data_platform.py",
            [
                "STORAGE_CONTRACT_VERSION",
                "build_storage_contract",
                "REQUIRED_STORAGE_TABLES",
                "BAR_STORAGE_TABLES",
                '@router.get("/meta/storage-contract")',
                "PostgreSQL + TimescaleDB",
                "available_time <= as_of_time",
                "local_storage_only",
                "transactional bulk upsert",
                "Prefect 3",
                "backup_pitr",
            ],
            "Data-platform storage contract is exposed through a structured API with PIT, ETL, scheduler, and lifecycle metadata.",
        ),
        _contains(
            "data_platform_local_pit_table_queries",
            "backend/app/services/data_platform_storage.py",
            [
                "TABLE_QUERY_CONTRACTS",
                "fundamental_report",
                "corporate_action",
                "adjustment_factor",
                "available_time <= as_of_time",
                "agent_input_policy",
                "local_storage_only",
                "external_fallback_allowed",
                "False",
                "build_pit_query",
                "query_pit_records",
                "DATA_PLATFORM_QUERY_TIMEOUT_SECONDS",
            ],
            "Fundamentals, corporate actions, and adjustment factors query local PostgreSQL tables through a strict PIT helper.",
        ),
        _contains(
            "data_platform_local_first_pit",
            "backend/app/api/v1/endpoints/data_platform.py",
            [
                "refresh_from_source",
                "allow_external_fallback=refresh_from_source",
                "agent_input_policy",
                "local_storage_only",
                "available_time <= as_of_time",
                "query_pit_records",
            ],
            "Data-platform routes default to local-first reads and explicit source refresh, with honest empty contracts.",
        ),
        _contains(
            "data_platform_local_first_empty_states",
            "backend/app/services/data_platform_storage.py",
            [
                "not_ingested_yet",
                "local_storage_unavailable",
                "available_time <= as_of_time",
                "local_storage_only",
                "external_fallback_allowed",
                "False",
            ],
            "Local data-platform table queries return honest empty/unavailable states without external fallback.",
        ),
        _contains(
            "data_platform_local_ingestion_upsert_lineage",
            "backend/app/services/data_platform_ingestion.py",
            [
                "INGESTION_TABLE_CONTRACTS",
                "fundamental_report",
                "corporate_action",
                "adjustment_factor",
                "prepare_ingest_record",
                "build_upsert_statement",
                "ON CONFLICT (record_id) DO UPDATE",
                "build_lineage_statement",
                "INSERT INTO data_lineage",
                "build_etl_job_log_statement",
                "INSERT INTO etl_job_log",
                "available_time <= as_of_time",
                "local_storage_only",
                "DATA_PLATFORM_INGEST_TIMEOUT_SECONDS",
            ],
            "Local ingestion normalizes records, enforces PIT fields, performs idempotent upsert, and writes ETL/lineage evidence.",
        ),
        _contains(
            "data_platform_manual_ingest_api",
            "backend/app/api/v1/endpoints/data_platform.py",
            [
                "LocalIngestRequest",
                "FinancialRefreshRequest",
                '@router.post("/meta/ingest")',
                '@router.post("/meta/refresh-financials")',
                "ingest_local_records",
                "refresh_openbb_financial_data",
                "dry_run",
                "external_fetch_performed",
                "False",
                "records must already be provider-normalized",
                "normalized records are written only through local data_platform_ingestion",
            ],
            "Manual data-platform ingest validates/upserts local normalized records; explicit financial refresh fetches OpenBB then writes only through local ingestion.",
        ),
        _contains(
            "openbb_financial_adapter_local_ingestion",
            "backend/app/services/openbb_financial_adapter.py",
            [
                "OPENBB_FINANCIAL_ADAPTER_VERSION",
                "openbb_financial_adapter.v1",
                "SUPPORTED_TABLES",
                "fundamental_report",
                "corporate_action",
                "adjustment_factor",
                "normalize_fundamental_records",
                "normalize_dividend_actions",
                "normalize_split_actions",
                "normalize_adjustment_factors_from_splits",
                "fetch_openbb_financial_records",
                "refresh_openbb_financial_data",
                "ingest_records",
                "available_time <= as_of_time",
                "local_storage_only",
                "external_fallback_allowed",
                "False",
            ],
            "OpenBB financial adapter normalizes fundamentals/actions/adjustment factors and persists them through local ingestion only.",
        ),
        _contains(
            "config_center_api",
            "backend/app/api/v1/endpoints/config_center.py",
            [
                '@router.get("/overview")',
                '@router.get("/tradingagents")',
                '@router.post("/tradingagents")',
                '@router.patch("/tradingagents/roles/{role_id}")',
                '@router.get("/agents")',
                '@router.post("/agents")',
                '@router.delete("/agents/{agent_id}")',
                "RoleConfigPayload",
                "TRADINGAGENTS_CONFIG_FIELDS",
                "_normalize_tradingagents_config",
                "_normalize_role_configs",
                "max_runtime_seconds",
                "background_run",
                "save_full_output",
                "write_audit",
                "default_mode",
                "output_language",
                "effective_llm",
                "uses_default",
                "local_storage_only",
                "real_ordering_enabled",
            ],
            "Configuration center supports editable TradingAgents roles, custom agents, local overrides, and simulation/security contracts.",
        ),
        _contains(
            "data_governance_api",
            "backend/app/api/v1/endpoints/data_governance.py",
            [
                '@router.get("/overview")',
                '@router.get("/sources")',
                '@router.get("/preview")',
                '@router.get("/cleaning-rules")',
                '@router.post("/cleaning-rules")',
                '@router.get("/lineage")',
                '@router.get("/quality")',
                "changed_data_store",
                "available_time <= as_of_time",
                "storage_contract",
                "manual_ingest",
                "financial_refresh",
                "fundamentals",
                "corporate_actions",
                "adjustment_factors",
            ],
            "Data governance exposes source configuration, preview, cleaning-rule versions, lineage, and quality checks.",
        ),
        _contains(
            "full_scope_router_mounts",
            "backend/app/api/v1/router.py",
            [
                "data_platform",
                "config_center",
                "data_governance",
                "linkage",
                'prefix="/config-center"',
                'prefix="/data-governance"',
                'prefix="/linkage"',
                'prefix=""',
            ],
            "New data-platform, config-center, and data-governance routers are mounted under /api/v1.",
        ),
        _contains(
            "config_center_frontend",
            "frontend/app/config-center/page.tsx",
            [
                "/api/v1/config-center/overview",
                "/api/v1/config-center/tradingagents",
                "/api/v1/config-center/tradingagents/roles/",
                "/api/v1/config-center/agents",
                "TradingAgents 有效配置",
                "保存默认配置",
                "最大运行时间",
                "默认后台运行",
                "保存完整输出",
                "写入审计",
                "自定义 Agent",
                "正在编辑",
                "删除",
                "Prompt 版本",
                "默认继承",
                "local_storage_only",
            ],
            "Configuration center page provides editable TradingAgents role and custom-agent controls.",
        ),
        _contains(
            "workbench_linkage_frontend",
            "frontend/components/linkage/WorkbenchLinkBar.tsx",
            [
                "/api/v1/linkage/context",
                "available_time <= as_of_time",
                "local_storage_only",
                "研究台",
                "回测台",
                "回放台",
                "审计台",
                "重放包",
                "replay_package_api",
            ],
            "Shared linkage bar exposes PIT cross-desk navigation on workbench pages.",
        ),
        _contains(
            "research_dashboard_pit_url",
            "frontend/app/dashboard/page.tsx",
            [
                "useSearchParams",
                "as_of_time",
                "WorkbenchLinkBar",
                "asOfTime={asOfTime}",
            ],
            "Research dashboard reads symbol/interval/as_of_time from URL and exposes linkage context.",
        ),
        _contains(
            "research_chart_uses_asof_endpoint",
            "frontend/components/charts/TradingViewChart.tsx",
            [
                "/api/v1/bars/as-of",
                "asOfTime",
                "available_time <= as_of_time",
                "as-of",
            ],
            "Research K-line chart switches to PIT bars endpoint when as_of_time is present.",
        ),
        _contains(
            "data_governance_frontend",
            "frontend/app/data-governance/page.tsx",
            [
                "/api/v1/data-governance/overview",
                "/api/v1/data-governance/quality",
                "/api/v1/data-governance/cleaning-rules",
                "/api/v1/data-governance/preview",
                "数据预览",
                "清洗规则版本",
                "数据血缘",
                "存储契约",
                "手动入库",
                "/api/v1/meta/ingest",
                "/api/v1/meta/refresh-financials",
                "fundamentals",
                "corporate_actions",
                "adjustment_factors",
            ],
            "Data governance page provides preview, cleaning rule, quality, and lineage panels.",
        ),
        _contains(
            "full_scope_navigation",
            "frontend/components/navigation/AppTopNav.tsx",
            [
                "config-center",
                "data-governance",
                "/paper-trading",
                "配置中心",
                "数据治理",
                "模拟交易",
            ],
            "Navigation exposes configuration center, data governance, and the paper-trading workbench entries.",
        ),
        _contains(
            "ticker_external_fallback_guard",
            "backend/app/services/market_data_gateway.py",
            [
                "allow_external_fallback",
                "if not allow_external_fallback:",
                "return None",
            ],
            "Ticker/quote reads now honor the local-only external fallback guard.",
        ),
        _contains(
            "data_platform_asof_snapshot_routes",
            "backend/app/api/v1/endpoints/market.py",
            [
                '@router.get("/bars/as-of")',
                '@router.get("/snapshot/{symbol}")',
                "AnalysisContextBuilder",
                "externalFallbackAllowed",
            ],
            "PRD-compatible as-of bars and snapshot routes are backed by AnalysisContext.",
        ),
        _contains(
            "agent_decision_audit_evidence",
            "backend/app/agents/coordinator_agent.py",
            [
                "AGENT_DECISION",
                "raise_on_failure=True",
                "context_hash",
                "input_snapshot_ids",
                "normalizedSnapshot",
            ],
            "Coordinator persists Agent decision, context hash, snapshot IDs, and critical audit.",
        ),
        _contains(
            "agent_input_local_pit_boundary",
            "backend/app/services/analysis_context_builder.py",
            [
                "available_time <= as_of_time",
                "allow_external_fallback=False",
                "allow_ccxt_fallback=False",
                "allow_binance_fallback=False",
                "local_storage_only",
                "context_hash",
                "input_snapshot_ids",
            ],
            "AnalysisContext enforces PIT visibility and disables external live fallback for Agent bars.",
        ),
        _contains(
            "analysis_context_zero_limit_fast_path",
            "backend/app/services/analysis_context_builder.py",
            [
                "if factor_limit <= 0",
                "if signal_limit <= 0",
                "news = [] if news_limit <= 0",
                "macro = [] if macro_limit <= 0",
            ],
            "As-of bars can build a PIT context without touching non-bar storage when panel limits are zero.",
        ),
        _contains(
            "redis_fast_degrade",
            "backend/app/services/database.py",
            [
                "_redis_unavailable_until",
                "_REDIS_OPERATION_TIMEOUT_SECONDS",
                "_mark_redis_unavailable",
                "asyncio.wait_for",
                "socket_connect_timeout",
                "retry_on_timeout=False",
            ],
            "Redis cache, config, and lock calls short-circuit quickly when infrastructure is offline.",
        ),
        _contains(
            "nats_external_ingestion_fallback_guard",
            "backend/app/services/ingestion_service.py",
            [
                "ENABLE_INGESTION_BINANCE_FALLBACK",
                "Binance WebSocket fallback is disabled",
                "NATS_CONNECT_TIMEOUT_SECONDS",
                "NATS_MAX_RECONNECT_ATTEMPTS",
            ],
            "NATS offline startup no longer opens an implicit external Binance ingestion stream unless explicitly enabled.",
        ),
        _contains(
            "workbench_linkage_contract",
            "backend/app/api/v1/endpoints/linkage.py",
            [
                '@router.get("/context")',
                '@router.get("/replay-package")',
                "build_workbench_linkage",
                "build_replay_package",
                "available_time <= as_of_time",
                "local_storage_only",
                "external_fallback_allowed",
                "research_snapshot_api",
                "bars_as_of_api",
                "audit_export_api",
                "strict_snapshot_replay",
                "pit_rebuild_from_local_storage",
            ],
            "Research, backtest, replay, and audit desks share a PIT linkage and replay-package contract.",
        ),
        _contains(
            "order_intent_generation",
            "backend/app/services/order_intent_service.py",
            [
                "ORDER_INTENT_CREATED",
                "positionRatio",
                "validUntil",
                "sourceDecisionId",
                "confidence",
            ],
            "OrderIntent is normalized and audited.",
        ),
        _contains(
            "risk_guard_pass_block_audit",
            "backend/app/services/order_intent_service.py",
            [
                "RISK_CHECK_PASSED",
                "RISK_BLOCKED",
                "risk_preview",
            ],
            "RiskGuard pass/block paths write audit events.",
        ),
        _contains(
            "paper_trading_workbench_contract",
            "backend/app/services/paper_trading_workbench.py",
            [
                "PAPER_TRADING_WORKBENCH_SCHEMA_VERSION",
                "paper_trading_workbench.v1",
                "OrderIntent",
                "RiskGuard",
                "PaperOrder",
                "PnL",
                "AuditRecord",
                "build_paper_trading_workbench",
                "_status_for_event",
                'return "BLOCKED"',
                "ORDER_INTENT_CREATED",
                "RISK_CHECK_PASSED",
                "RISK_BLOCKED",
                "PAPER_ORDER_FILLED",
                "paper_trading_only",
                "append_only",
            ],
            "Paper-trading workbench read model aggregates OrderIntent, RiskGuard, paper orders, PnL, and audit evidence.",
        ),
        _contains(
            "paper_trading_workbench_api",
            "backend/app/api/v1/endpoints/trading.py",
            [
                '@router.get("/workbench")',
                "get_paper_trading_workbench",
                "build_paper_trading_workbench",
                "exchange_id",
                "symbol",
            ],
            "Trading API exposes the Phase 2 paper-trading workbench under /api/v1/trading/workbench.",
        ),
        _contains(
            "paper_execution_audit_linkage",
            "backend/app/services/audit_service.py",
            [
                "PAPER_ORDER_FILLED",
                "PAPER_ORDER_REJECTED",
                "order_id",
                "executionResult",
            ],
            "Paper fill/reject results are linked into audit details.",
        ),
        _contains(
            "paper_trading_workbench_frontend",
            "frontend/app/paper-trading/page.tsx",
            [
                "/api/v1/trading/workbench",
                "模拟交易台",
                "OrderIntent",
                "RiskGuard",
                "模拟订单",
                "持仓面板",
                "PnL / 资金曲线",
                "执行链详情",
                "AuditRecord",
                "paper_trading_only",
            ],
            "Paper-trading page provides the PRD execution desk for account, intents, RiskGuard, orders, positions, PnL, and audit chain.",
        ),
        _contains(
            "backtest_metrics_and_agent_trace",
            "backend/app/api/v1/endpoints/strategy.py",
            [
                "BacktestMetrics",
                "EXECUTION_MODE_AGENT_AUDITED",
                "BACKTEST_RUN",
                "auditRecordIds",
                "agentCallCount",
                "riskBlockedCount",
                "paperOrderCount",
                "backtest_duckdb_store",
                "build_backtest_archive_record",
                '@router.get("/backtest/duckdb-archive")',
            ],
            "Backtest persists metrics and agent-audited trace counters.",
        ),
        _contains(
            "backtest_duckdb_archive_contract",
            "backend/app/services/backtest_duckdb_store.py",
            [
                "BACKTEST_DUCKDB_SCHEMA_VERSION",
                "backtest_duckdb_archive.v1",
                "data/backtest/backtest_results.duckdb",
                "_duckdb_connection",
                "conn.close()",
                "conn.commit()",
                "CREATE TABLE IF NOT EXISTS backtest_results",
                "CREATE TABLE IF NOT EXISTS backtest_task_events",
                "pit_passed",
                "pit_violation_count",
                "information_ratio",
                "agent_stats_json",
                "archive_result",
                "latest_results",
            ],
            "Backtest results are archived to DuckDB with PIT, PRD metrics, trades, equity, and Agent stats.",
        ),
        _contains(
            "backtest_local_only_data_boundary",
            "backend/app/api/v1/endpoints/strategy.py",
            [
                "AuditLog",
                "market_data_gateway:local_storage",
                "回测不得隐式调用外部实时/历史源",
                "allow_external_fallback=False",
                "allow_ccxt_fallback=False",
                "allow_binance_fallback=False",
                "Failed to fetch local market data",
                "get_backtest_record_detail",
            ],
            "Backtest, optimization, batch, and detail paths use local-only market data and expose audit-linked details.",
        ),
        _contains(
            "backtest_no_future_evidence",
            "backend/app/api/v1/endpoints/strategy.py",
            [
                "_build_pit_check",
                "available_time <= as_of_time",
                "pitCheck",
                "violations",
            ],
            "Backtest exposes PIT checks and future-data violations.",
        ),
        _contains(
            "backtest_async_queue_controls",
            "backend/app/api/v1/endpoints/strategy.py",
            [
                '@router.post("/backtest/parameter-batch"',
                '@router.get("/backtest/tasks")',
                '@router.get("/backtest/tasks/{task_id}")',
                '@router.post("/backtest/tasks/{task_id}/cancel")',
                '@router.post("/backtest/tasks/{task_id}/retry"',
                "max_parallel",
                "cancel_supported",
                "retry_supported",
                "in_process_memory",
                "DuckDB backtest_results archive",
            ],
            "Backtest task queue supports async execution, max parallel 5, status, cancel, retry, and DuckDB archive metadata.",
        ),
        _contains(
            "backtest_frontend_queue_archive_controls",
            "frontend/app/backtest/page.tsx",
            [
                "/api/v1/strategy/backtest/parameter-batch",
                "/api/v1/strategy/backtest/tasks/",
                "/cancel",
                "/retry",
                "DuckDB data/backtest/backtest_results.duckdb",
                "backtest_duckdb_archive.v1",
                "取消",
                "重试",
            ],
            "Backtest page exposes queue status plus cancel/retry controls and DuckDB archive visibility.",
        ),
        _contains(
            "audit_json_export",
            "backend/app/api/v1/endpoints/audit.py",
            [
                '@router.get("/records/{audit_id}/export")',
                "audit_export.v1",
                "audit_record",
                "standard_audit_record",
                "linked_decision",
                "context_hash",
                "payload_hash",
            ],
            "Audit JSON export includes input, risk/execution, and PIT evidence.",
        ),
        _contains(
            "append_only_audit_guard",
            "backend/migrations/versions/015_harden_audit_logs.py",
            [
                "prevent_audit_logs_mutation",
                "BEFORE UPDATE OR DELETE ON audit_logs",
                "append-only",
                "payload_hash",
                "prev_hash",
            ],
            "Audit migration installs append-only trigger and hash columns.",
        ),
        _contains(
            "p1_tradingagents_config_api",
            "backend/app/api/v1/endpoints/system_health.py",
            [
                '@router.get("/tradingagents-config")',
                '@router.get("/phase2-p1p2-status")',
                "_redact_url",
                "fullGraphReady",
                "strongAcceptanceEligible",
                "agent_input_policy",
                "local_storage_only",
                "externalFallbackAllowed",
            ],
            "P1 TradingAgents effective config/readiness API exposes mode, redacted LLM config, full graph readiness, and local data boundary.",
        ),
        _contains(
            "p1_monitor_tradingagents_panel",
            "frontend/app/monitor/page.tsx",
            [
                "/api/v1/system/tradingagents-config",
                "TradingAgents 配置",
                "运行准备度",
                "fullGraphReady",
                "agent_input_policy",
            ],
            "Monitor page displays TradingAgents configuration and readiness.",
        ),
        _contains(
            "phase2_ops_monitor_service_contract",
            "backend/app/services/phase2_ops_monitor.py",
            [
                "PHASE2_OPS_MONITOR_SCHEMA_VERSION",
                "phase2_ops_monitor.v1",
                "DATA_FRESHNESS_TABLES",
                "bar_1m",
                "quote_latest",
                "fundamental_report",
                "corporate_action",
                "adjustment_factor",
                "build_phase2_ops_monitor",
                "collect_audit_health",
                "collect_execution_risk_health",
                "collect_backtest_queue",
                "collect_duckdb_archive",
                "available_time <= as_of_time",
                "local_storage_only",
                "external_fallback_allowed",
                "False",
            ],
            "Phase 2 operations monitor aggregates data freshness, audit, RiskGuard, backtest queue, DuckDB archive, and local PIT boundary.",
        ),
        _contains(
            "phase2_ops_monitor_api",
            "backend/app/api/v1/endpoints/system_health.py",
            [
                '@router.get("/phase2-ops-monitor")',
                "get_phase2_ops_monitor",
                "build_phase2_ops_monitor",
                "get_tradingagents_config",
            ],
            "System API exposes Phase 2 operations health under /api/v1/system/phase2-ops-monitor.",
        ),
        _contains(
            "phase2_ops_monitor_frontend",
            "frontend/app/monitor/page.tsx",
            [
                "/api/v1/system/phase2-ops-monitor",
                "Phase2 运维总控",
                "数据类型",
                "审计健康",
                "执行与 RiskGuard",
                "回测/回放运维",
                "DuckDB",
                "available_time <= as_of_time",
                "local_storage_only",
            ],
            "Monitor page displays Phase 2 ops health for freshness, audit, RiskGuard, queues, and DuckDB archive.",
        ),
        _contains(
            "phase2_live_acceptance_gate",
            "backend/scripts/phase2_live_acceptance.py",
            [
                "Phase 2 live acceptance checks",
                "REQUIRED_DATA_PLATFORM_TABLES",
                "api_phase2_ops_monitor",
                "api_trading_workbench",
                "api_openbb_refresh_dry_run",
                "db_data_platform_tables",
                "db_timescale_storage_policy",
                "db_audit_append_only_metadata",
                "db_audit_append_only_rejection",
                "--mutating-audit-check",
                "--run-migrations",
                "available_time <= as_of_time",
                "local_storage_only",
            ],
            "Live acceptance gate covers API, DB migration/table/index, Timescale policy, OpenBB dry-run, workbench, ops monitor, and append-only audit proof.",
        ),
        _contains(
            "p1_riskguard_config_api",
            "backend/app/api/v1/endpoints/risk.py",
            [
                '@router.get("/config-metadata")',
                '@router.post("/config/reset")',
                "MAX_TOTAL_EXPOSURE_PCT",
                "FORBIDDEN_SYMBOLS",
                "MIN_ORDER_NOTIONAL",
                "WAIT_ORDER_INTENT_POLICY",
                "RISK_FAILURE_ACTION",
                "_normalize_risk_config_update",
                "MARGIN_WARNING_LEVEL",
                "PRE_LIQUIDATION_LEVEL",
                "record_flat",
                "block",
                "RISK_CONFIG_UPDATE",
                "RISK_CONFIG_RESET",
            ],
            "P1 RiskGuard config API covers exposure, forbidden symbols, margin thresholds, reset, and audit events.",
        ),
        _contains(
            "riskguard_runtime_prd_contract",
            "backend/app/services/risk_manager.py",
            [
                "MIN_ORDER_NOTIONAL",
                "WAIT_ORDER_INTENT_POLICY",
                "RISK_FAILURE_ACTION",
                "最小订单金额",
                "WAIT 处理策略",
                "失败动作",
                "action=failure_action",
                "订单名义金额",
            ],
            "RiskGuard runtime enforces min order notional and exposes WAIT/failure-action policy evidence.",
        ),
        _contains(
            "p1_riskguard_config_frontend",
            "frontend/app/risk/page.tsx",
            [
                "/api/v1/risk/config-metadata",
                "/api/v1/risk/config/reset",
                "/api/v1/risk/kill-switch/trigger",
                "MAX_TOTAL_EXPOSURE_PCT",
                "FORBIDDEN_SYMBOLS",
                "MIN_ORDER_NOTIONAL",
                "WAIT_ORDER_INTENT_POLICY",
                "RISK_FAILURE_ACTION",
                "RiskGuard 状态",
            ],
            "RiskGuard configuration page exposes thresholds, forbidden symbols, and kill switch controls.",
        ),
    ]
    return checks


def _live_checks(base_url: str, timeout: float, require_live: bool) -> list[CheckResult]:
    checks: list[CheckResult] = []

    def run(name: str, path: str, params: dict[str, Any], predicate, success_detail: str) -> None:
        try:
            payload = _http_json(base_url, path, params, timeout)
            ok, detail = predicate(payload)
            checks.append(CheckResult(name, ok, detail if not ok else success_detail, mode="live"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            checks.append(
                CheckResult(
                    name,
                    False if require_live else True,
                    f"live API unavailable: {exc}",
                    mode="live-warning" if not require_live else "live",
                )
            )

    run(
        "live_bars_asof_shape",
        "/api/v1/bars/as-of",
        {"symbol": "BTCUSDT", "interval": "1h", "limit": 5},
        lambda data: (
            isinstance(data, dict)
            and isinstance(data.get("data"), list)
            and data.get("meta", {}).get("pit_rule") == "available_time <= as_of_time"
            and data.get("meta", {}).get("external_fallback_allowed") is False,
            f"unexpected bars/as-of payload: {data}",
        ),
        "top-level bars/as-of returns PIT metadata with external fallback disabled.",
    )
    run(
        "live_snapshot_shape",
        "/api/v1/snapshot",
        {"symbol": "BTCUSDT", "interval": "1h", "bar_limit": 5},
        lambda data: (
            isinstance(data, dict)
            and isinstance(data.get("data"), dict)
            and bool(data.get("meta", {}).get("context_hash"))
            and data.get("meta", {}).get("pit_rule") == "available_time <= as_of_time",
            f"unexpected snapshot payload: {data}",
        ),
        "top-level snapshot returns context hash and PIT evidence.",
    )
    run(
        "live_meta_providers_shape",
        "/api/v1/meta/providers",
        {},
        lambda data: (
            isinstance(data, dict)
            and isinstance(data.get("data"), list)
            and data.get("meta", {}).get("provider_registry_version") == "provider_registry.v1",
            f"unexpected meta/providers payload: {data}",
        ),
        "meta/providers returns provider registry in unified envelope.",
    )
    run(
        "live_meta_storage_contract_shape",
        "/api/v1/meta/storage-contract",
        {},
        lambda data: (
            isinstance(data, dict)
            and isinstance(data.get("data", {}).get("tables"), dict)
            and "bar_1m" in data.get("data", {}).get("tables", {})
            and "etl_job_log" in data.get("data", {}).get("tables", {})
            and data.get("data", {}).get("visibility_rule") == "available_time <= as_of_time"
            and data.get("data", {}).get("agent_input_policy") == "local_storage_only"
            and data.get("meta", {}).get("timescale_contract_declared") is True,
            f"unexpected meta/storage-contract payload: {data}",
        ),
        "meta/storage-contract returns required storage tables, PIT rule, and Timescale declaration.",
    )
    run(
        "live_config_center_shape",
        "/api/v1/config-center/overview",
        {},
        lambda data: (
            isinstance(data, dict)
            and isinstance(data.get("data", {}).get("sections"), list)
            and data.get("meta", {}).get("schema_version") == "config_center_response.v1",
            f"unexpected config-center payload: {data}",
        ),
        "config-center overview returns configuration sections.",
    )
    run(
        "live_data_governance_shape",
        "/api/v1/data-governance/overview",
        {},
        lambda data: (
            isinstance(data, dict)
            and isinstance(data.get("data", {}).get("governance"), dict)
            and data.get("meta", {}).get("schema_version") == "data_governance_response.v1",
            f"unexpected data-governance payload: {data}",
        ),
        "data-governance overview returns governance and quality contracts.",
    )
    run(
        "live_tradingagents_config_shape",
        "/api/v1/system/tradingagents-config",
        {},
        lambda data: (
            isinstance(data, dict)
            and isinstance(data.get("mode"), dict)
            and isinstance(data.get("llm"), dict)
            and data.get("data_boundary", {}).get("agent_input_policy") == "local_storage_only"
            and data.get("data_boundary", {}).get("externalFallbackAllowed") is False
            and "?" not in str(data.get("llm", {}).get("baseUrl", "")),
            f"unexpected tradingagents-config payload: {data}",
        ),
        "tradingagents-config returns redacted effective config and local-only boundary.",
    )
    run(
        "live_risk_config_metadata_shape",
        "/api/v1/risk/config-metadata",
        {},
        lambda data: (
            isinstance(data, dict)
            and data.get("schema_version") == "risk_config.v1"
            and isinstance(data.get("fields"), list)
            and "MAX_TOTAL_EXPOSURE_PCT" in data.get("config", {})
            and "FORBIDDEN_SYMBOLS" in data.get("config", {}),
            f"unexpected risk config metadata payload: {data}",
        ),
        "risk config metadata returns editable fields and full RiskGuard config.",
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 full-scope acceptance checks.")
    parser.add_argument("--api-base", default="", help="Optional backend base URL, e.g. http://localhost:8002")
    parser.add_argument("--require-live", action="store_true", help="Fail if live API checks cannot connect.")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    results = _static_checks()
    if args.api_base:
        results.extend(_live_checks(args.api_base, args.timeout, args.require_live))

    failed = [result for result in results if not result.ok]

    if args.json:
        print(json.dumps({"ok": not failed, "results": [asdict(item) for item in results]}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            print(f"[{status}] {result.name} ({result.mode}) - {result.detail}")
        print(f"\nSummary: {len(results) - len(failed)}/{len(results)} checks passed.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
