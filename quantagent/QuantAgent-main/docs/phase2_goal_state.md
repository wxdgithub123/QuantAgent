# Phase 2 Goal State

Last updated: 2026-06-10

## Current Goal

Complete the Phase 2 closed loop for the QuantAgent platform within the target repository only:

`local data platform -> AnalysisContext -> TradingAgents -> AgentDecision -> OrderIntent -> RiskGuard -> paper execution -> AuditRecord -> backtest/replay/frontend audit`

Owned scope:

- Audit system and immutable audit evidence.
- Agent decision traceability.
- Backtest and replay linkage.
- OrderIntent, RiskGuard, paper execution, and audit write-back.
- Frontend pages directly connected to audit, decisions, replay, and backtest.

Out of scope for this pass:

- Live trading connectivity.
- Large strategy marketplace expansion.
- Full Prefect or TimescaleDB migration.
- Custom Agent marketplace, complex approval workflow, and large configuration-center redesign beyond the P1 TradingAgents/RiskGuard configuration slices.

## Current Phase

Phase 2 P0/P1 implementation verified in focused/offline mode and through a local live API/DB acceptance gate.

The required documentation is persisted, the main P0 backend gap has been hardened, the existing frontend P0 pages have been inspected and smoke-tested, and the acceptance scripts are runnable. P1/P2 configuration coverage now includes TradingAgents effective configuration/readiness, a RiskGuard configuration center, a paper-trading workbench, and live DB/API contract checks against local services.

## Completed Items

- Goal Mode was created for this thread.
- Target and reference boundaries were confirmed.
- Requirement sources were extracted from:
  - `量化研究平台 · 第二阶段 PRD.docx`
  - `金融数据平台子系统需求.docx`
  - `功能模块V2.xlsx`
- Existing target capabilities were mapped at a high level:
  - `backend/app/models/db_models.py`
  - `backend/app/services/audit_service.py`
  - `backend/migrations/versions/015_harden_audit_logs.py`
  - `backend/app/services/analysis_context_builder.py`
  - `backend/app/agents/coordinator_agent.py`
  - `backend/app/agents/tradingagents_adapter.py`
  - `backend/app/services/order_intent_service.py`
  - `backend/app/services/risk_manager.py`
  - `backend/app/api/v1/endpoints/audit.py`
  - `backend/app/api/v1/endpoints/execution.py`
  - `frontend/app/audit/page.tsx`
  - `frontend/app/decisions/page.tsx`
  - `frontend/app/backtest/page.tsx`
  - `frontend/app/replay/page.tsx`
- Added explicit local-only Agent bar loading:
  - `backend/app/services/market_data_gateway.py`
  - `backend/app/services/analysis_context_builder.py`
- Added data-platform compatibility endpoints:
  - `GET /api/v1/market/bars/as-of`
  - `GET /api/v1/market/snapshot/{symbol}`
- Added focused PIT/local-only tests:
  - `backend/tests/unit/test_analysis_context_builder_pit.py`
- Added machine-runnable Phase 2 acceptance script:
  - `backend/scripts/phase2_acceptance.py`
- Added Phase 2 P1/P2 configuration and monitoring slice:
  - `GET /api/v1/system/tradingagents-config`
  - `GET /api/v1/system/phase2-p1p2-status`
  - TradingAgents configuration/readiness panel on `/monitor`
  - URL redaction for service and LLM base URLs
  - Readiness evidence for fast research mode, full graph eligibility, LLM settings, and local/PIT Agent input boundary
- Added focused P1 tests:
  - `backend/tests/unit/test_system_tradingagents_config.py`
- Added P1/P2 RiskGuard configuration center:
  - `GET /api/v1/risk/config-metadata`
  - `POST /api/v1/risk/config`
  - `POST /api/v1/risk/config/reset`
  - `/risk` frontend page for thresholds, forbidden symbols, and kill-switch controls
  - Navigation and breadcrumb entry for `/risk`
- Added focused RiskGuard config tests:
  - `backend/tests/unit/test_risk_config_api.py`
- Added editable TradingAgents/custom Agent configuration:
  - `PATCH /api/v1/config-center/tradingagents/roles/{role_id}`
  - Role config normalization with `effective_llm` default inheritance evidence.
  - `/config-center` can edit role prompts/skills/per-role LLM settings and create/edit/delete custom Agents.
- Added dedicated simulated trading workbench:
  - `backend/app/services/paper_trading_workbench.py`
  - `GET /api/v1/trading/workbench`
  - `/paper-trading` page for account/mode, OrderIntent, RiskGuard, orders/fills, positions, PnL/equity curve, and execution-chain details.
  - Navigation and breadcrumb entries now point to `/paper-trading`.
  - New paper executions now write a single fill audit event and a separate OrderIntent execution-link event, so lifecycle evidence is traceable without double-counting fills.
  - Workbench blocked events now display lifecycle status `BLOCKED`, not stale draft status `CREATED`.
- Verification completed:
  - Baseline focused backend tests before implementation: 26 passed.
  - Expanded focused backend tests after implementation: 29 passed.
  - Phase 2 offline acceptance script: 10/10 passed.
  - Frontend browser smoke: `/audit`, `/decisions`, `/backtest`, `/replay` mounted without Next error overlays.
  - P1 focused backend tests: 9 passed for TradingAgents config, adapter context, and Agent PIT boundary.
  - Phase 2 offline acceptance script after P1 slice: 12/12 passed.
  - Frontend checks for `/monitor`: `npx eslint app/monitor/page.tsx` passed, `npx tsc --noEmit --pretty false --incremental false` passed, browser smoke confirmed the TradingAgents panel mounted without a Next error overlay.
  - P1/P2 config focused backend tests: 17 passed for RiskGuard config, TradingAgents config, adapter context, and Agent PIT boundary.
  - Phase 2 offline acceptance script after RiskGuard config slice: 14/14 passed.
  - Frontend checks for `/risk`, `/monitor`, and navigation files: page-scoped lint passed, frontend typecheck passed, browser smoke confirmed `/risk` mounted without a Next error overlay.
- Added cross-workbench linkage and replay package slice:
  - `GET /api/v1/linkage/context`
  - `GET /api/v1/linkage/replay-package`
  - Shared `WorkbenchLinkBar` for research/backtest/replay/audit.
  - Research dashboard URL PIT review and K-line chart as-of data path.
  - Replay package includes Agent input record IDs, data versions, role outputs, PIT visible-data checks, OrderIntent, RiskGuard, execution result, immutable audit chain, and strict-snapshot vs local-PIT-rebuild replay method.
- Latest verification for linkage/replay package:
  - `python -m pytest backend/tests/unit/test_linkage_contract.py backend/tests/unit/test_database_redis_fast_degrade.py backend/tests/unit/test_analysis_context_builder_pit.py -q` -> 10 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 31/31 passed.
  - `npx tsc --noEmit --pretty false --incremental false` -> passed.
  - `npx eslint app/dashboard/page.tsx components/linkage/WorkbenchLinkBar.tsx components/charts/TradingViewChart.tsx lib/replay-store.tsx` -> passed.
- Added financial data platform storage contract slice:
  - Alembic revision `017_data_platform_contract_tables.py` declares provider registry, instrument, 1m/1h/1d bar, quote, fundamental, corporate action, independent adjustment factor, ETL job log, news, macro, lineage, cleaned-data, and storage-policy tables.
  - Tables include PIT fields (`event_time`, `ingest_time`, `available_time`), upsert keys, `(symbol, ts)`/available-time indexes, quality flags, cleaning-rule versions, source versions, raw payload hashes, and lineage JSON.
  - Timescale extension, hypertable, and compression setup is guarded; compression/retention/PITR policies are declared in `data_platform_storage_policy`.
  - `GET /api/v1/meta/storage-contract` exposes structured storage, ETL, scheduler, lifecycle, `available_time <= as_of_time`, and `local_storage_only` contract metadata.
- Latest verification for data-platform storage contract:
  - `python -m py_compile backend/app/api/v1/endpoints/data_platform.py backend/migrations/versions/017_data_platform_contract_tables.py backend/scripts/phase2_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_data_platform_helpers.py -q` -> 5 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 33/33 passed.
- Added financial data local PIT table-query slice:
  - `backend/app/services/data_platform_storage.py` provides whitelisted local PostgreSQL queries for `fundamental_report`, `corporate_action`, and `adjustment_factor`.
  - Fundamentals, corporate action, and adjust-factor endpoints now query local storage with `available_time <= as_of_time`, `local_storage_only`, no external fallback, and structured empty/unavailable states.
- Latest verification for local PIT table-query slice:
  - `python -m py_compile backend/app/services/data_platform_storage.py backend/app/api/v1/endpoints/data_platform.py backend/scripts/phase2_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_storage.py -q` -> 9 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 35/35 passed.
- Added financial data local ingestion/upsert slice:
  - `backend/app/services/data_platform_ingestion.py` validates provider-normalized records, fills PIT timestamps, generates stable record IDs/raw payload hashes, and writes idempotent upserts.
  - `POST /api/v1/meta/ingest` exposes manual dry-run/upsert for `fundamental_report`, `corporate_action`, and `adjustment_factor`; it does not fetch external providers.
  - Successful upserts record `etl_job_log` and `data_lineage` evidence.
- Latest verification for local ingestion/upsert slice:
  - `python -m py_compile backend/app/services/data_platform_ingestion.py backend/app/services/data_platform_storage.py backend/app/api/v1/endpoints/data_platform.py backend/scripts/phase2_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_storage.py backend/tests/unit/test_data_platform_ingestion.py -q` -> 15 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 37/37 passed.
- Added data governance storage visibility slice:
  - Data governance overview/quality/lineage/preview endpoints now expose the storage contract, manual ingest contract, lifecycle policy, and additional preview types.
  - `/data-governance` page displays storage contract tables, PIT fields, index counts, lifecycle policies, manual ingest endpoint, scheduler jobs, and preview tabs for fundamentals/corporate actions/adjustment factors.
- Latest verification for data governance storage visibility:
  - `python -m py_compile backend/app/api/v1/endpoints/data_governance.py backend/app/api/v1/endpoints/data_platform.py backend/scripts/phase2_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_data_governance_contract.py backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_storage.py backend/tests/unit/test_data_platform_ingestion.py -q` -> 17 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 37/37 passed.
  - `npx eslint app/data-governance/page.tsx` -> passed.
  - `npx tsc --noEmit --pretty false --incremental false` -> passed.
- Added backtest DuckDB archive and queue-control slice:
  - `backend/app/services/backtest_duckdb_store.py` archives backtest results to `data/backtest/backtest_results.duckdb` with PRD metrics, PIT check, equity curve, trades, params, execution mode, and Agent stats.
  - Single backtest persistence now attempts non-blocking DuckDB archive after PostgreSQL save; batch task events are also archived.
  - Backtest parameter-batch queue now exposes cancel/retry endpoints and storage metadata for PostgreSQL + DuckDB archive.
  - `/api/v1/strategy/backtest/duckdb-archive` lists latest archive rows for comparison/replay workflows.
  - `/backtest` page shows archive path/schema and task cancel/retry controls.
  - Backtest, optimization, and batch backtest data loads now explicitly disable OpenBB/CCXT/Binance fallback and use local persisted market data only.
  - DuckDB archive uses short-lived committed connections so multiple local backend processes see newly archived rows.
  - Backtest detail imports `AuditLog` and returns audit-linked detail payloads.
- Latest verification for backtest DuckDB archive and queue-control:
  - `python -m py_compile backend/app/services/backtest_duckdb_store.py backend/app/api/v1/endpoints/strategy.py backend/scripts/phase2_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_backtest_duckdb_store.py backend/tests/unit/test_backtest_p3_helpers.py -q` -> 12 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 40/40 passed.
  - `npx tsc --noEmit --pretty false --incremental false` -> passed.
  - `npx eslint app/backtest/page.tsx` still fails on pre-existing broad lint debt in that large page; this was recorded as residual risk, not a regression gate for this slice.
  - Later hardening: `python -m py_compile backend/app/services/backtest_duckdb_store.py backend/app/api/v1/endpoints/strategy.py backend/scripts/phase2_acceptance.py` -> passed.
  - Later hardening: `python -m pytest backend/tests/unit/test_backtest_duckdb_store.py backend/tests/unit/test_backtest_p3_helpers.py -q` -> 16 passed.
  - Later hardening: `python backend/scripts/phase2_acceptance.py` -> 50/50 passed.
  - Live proof: `POST /api/v1/strategy/backtest/run` on `127.0.0.1:8004` produced `backtest_id=9` with `data_source=market_data_gateway:local_storage`, `pit_passed=true`, `bars=400`, `trades=12`, `duckdb_status=archived`, and `audit_count=1`.
  - Cross-backend proof: both `127.0.0.1:8004` and frontend-rewrite backend `127.0.0.1:8002` returned DuckDB archive IDs `[9, 8, 7]`.
  - Detail proof: `GET /api/v1/strategy/backtest/history/9` returned `schema_version=backtest_detail.v1`, local data source, `bars=400`, and `auditCount=1`.
- Added Phase2 operations monitor slice:
  - `backend/app/services/phase2_ops_monitor.py` builds `phase2_ops_monitor.v1`.
  - `GET /api/v1/system/phase2-ops-monitor` exposes data freshness, TradingAgents, LLM monitor contract, audit health, execution/RiskGuard health, in-process backtest task queue, DuckDB archive, replay/backtest table status, and local resource snapshot.
  - The payload repeats the hard boundary: `available_time <= as_of_time`, `local_storage_only`, and `external_fallback_allowed = False`.
  - `/monitor` now shows a Phase2 operations control panel with freshness rows, audit append-only/hash coverage, RiskGuard execution chain, queue status, and DuckDB archive path/schema.
- Latest verification for Phase2 operations monitor:
  - `python -m py_compile backend/app/services/phase2_ops_monitor.py backend/app/api/v1/endpoints/system_health.py backend/scripts/phase2_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_phase2_ops_monitor.py backend/tests/unit/test_system_tradingagents_config.py -q` -> 6 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 43/43 passed.
  - `cd frontend; npx eslint app/monitor/page.tsx` -> passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` -> passed.
- Added OpenBB financial adapter local-ingestion slice:
  - `backend/app/services/openbb_financial_adapter.py` normalizes OpenBB fundamentals, dividends, splits, and split-derived adjustment factors.
  - `POST /api/v1/meta/refresh-financials` explicitly fetches provider data, then validates or writes only through `data_platform_ingestion.ingest_records`.
  - Refresh defaults to `dry_run=true` and repeats `local_storage_only`, `available_time <= as_of_time`, and `external_fallback_allowed = False`.
  - `/data-governance` now displays `/api/v1/meta/refresh-financials` beside `/api/v1/meta/ingest`.
- Latest verification for OpenBB financial adapter:
  - `python -m py_compile backend/app/services/openbb_financial_adapter.py backend/app/api/v1/endpoints/data_platform.py backend/app/api/v1/endpoints/data_governance.py backend/scripts/phase2_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_openbb_financial_adapter.py backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_ingestion.py -q` -> 14 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 44/44 passed.
  - `cd frontend; npx eslint app/data-governance/page.tsx` -> passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` -> passed.
- Added config-center editability and simulated-trading workbench slices:
  - `backend/app/api/v1/endpoints/config_center.py` now normalizes role configs, returns `effective_llm`, and exposes `PATCH /api/v1/config-center/tradingagents/roles/{role_id}`.
  - `/config-center` now supports role prompt/skill/LLM editing and custom Agent create/edit/delete.
  - `backend/app/services/paper_trading_workbench.py` builds `paper_trading_workbench.v1` from existing OrderIntent/RiskGuard/PaperTrading/Audit evidence.
  - `GET /api/v1/trading/workbench` and `/paper-trading` expose the dedicated simulated trading desk.
- Latest verification for config center and paper-trading workbench:
  - `python -m py_compile backend/app/api/v1/endpoints/config_center.py backend/app/services/paper_trading_workbench.py backend/app/api/v1/endpoints/trading.py backend/scripts/phase2_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_config_center_contract.py backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_order_intent_service.py -q` -> 16 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 47/47 passed.
  - `cd frontend; npx eslint app/config-center/page.tsx app/paper-trading/page.tsx components/navigation/AppTopNav.tsx components/navigation/Breadcrumb.tsx` -> passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` -> passed.
- Added RiskGuard PRD execution-contract slice:
  - Runtime/default config now includes `MIN_ORDER_NOTIONAL`, `WAIT_ORDER_INTENT_POLICY`, and `RISK_FAILURE_ACTION`.
  - `/api/v1/risk/config-metadata` and `/risk` expose minimum notional plus WAIT/failure-action controls.
  - `RiskManager.check_order` blocks orders below minimum notional; failed checks still cannot bypass simulated execution.
  - `OrderIntentService` records WAIT/flat policy (`record_flat` or `skip`) and stores configured/effective failure actions in risk preview/audit evidence.
  - Agent-audited backtest RiskGuard rows now include minimum notional, WAIT policy, and failure-action evidence.
  - Phase2 ops monitor reports these config values and `bypass_allowed = False`.
- Latest verification for RiskGuard PRD execution-contract:
  - `python -m py_compile backend/app/core/config.py backend/app/services/risk_manager.py backend/app/api/v1/endpoints/risk.py backend/app/services/order_intent_service.py backend/app/api/v1/endpoints/strategy.py backend/app/services/phase2_ops_monitor.py backend/scripts/phase2_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_risk_config_api.py backend/tests/unit/test_risk_manager_contract.py backend/tests/unit/test_order_intent_service.py backend/tests/unit/test_backtest_p3_helpers.py -q` -> 35 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 48/48 passed.
  - `cd frontend; npx eslint app/risk/page.tsx` -> passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` -> passed.
- Added Phase2 live acceptance gate:
  - `backend/scripts/phase2_live_acceptance.py` checks running API routes for PIT bars/snapshot, storage contract, ops monitor, paper-trading workbench, RiskGuard PRD config, and OpenBB dry-run refresh.
  - DB checks verify Alembic head `017`, data-platform tables, PIT columns, bar indexes, Timescale/storage policies, and audit append-only trigger metadata.
  - Optional flags: `--run-migrations` runs `alembic upgrade head`; `--mutating-audit-check` inserts an immutable proof row and verifies UPDATE/DELETE rejection.
- Latest verification for Phase2 live acceptance gate:
  - `python -m py_compile backend/scripts/phase2_live_acceptance.py` -> passed.
  - `python -m pytest backend/tests/unit/test_phase2_live_acceptance.py -q` -> 5 passed.
  - `python backend/scripts/phase2_live_acceptance.py --api-base= --database-url= --json` -> passed with empty result set.
  - `python backend/scripts/phase2_acceptance.py` -> 49/49 passed.
- Hardened and executed the live API/DB gate against local services:
  - Docker services: local Postgres on `localhost:5435`, Redis on `localhost:6382`, ClickHouse on `localhost:8124`.
  - Backend: local Uvicorn on `127.0.0.1:8004`, with NATS unavailable and graceful fallback warnings in logs.
  - Migration `017_data_platform_contract_tables.py` now catches `feature_not_supported` for Timescale extension creation on plain `pgvector/pg16`.
  - RiskGuard status now reports minimum order notional, WAIT policy, and configured failure action.
  - Live audit immutability was proven with inserted proof rows and rejected UPDATE/DELETE attempts.
- Latest live verification:
  - `python -m alembic upgrade head` with `DATABASE_URL=postgresql+asyncpg://quantagent:quantagent@localhost:5435/quantagent` -> passed; Alembic head `017`.
  - `python scripts/phase2_live_acceptance.py --api-base= --database-url=$DATABASE_URL --mutating-audit-check --json` -> 7/7 DB checks passed.
  - `python scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url=$DATABASE_URL --mutating-audit-check --json` -> 14/14 API+DB checks passed.
  - `python scripts/phase2_acceptance.py --api-base http://127.0.0.1:8004 --timeout 12` -> 57/57 static+live checks passed.
  - `python -m pytest backend/tests/unit/test_risk_manager_contract.py backend/tests/unit/test_phase2_live_acceptance.py -q` -> 8 passed.
  - `python -m py_compile backend/app/services/risk_manager.py backend/scripts/phase2_live_acceptance.py` -> passed.
- Completed frontend live-backend smoke:
  - Existing Next dev server on `http://127.0.0.1:3002` was verified against live APIs by starting a matching backend on `127.0.0.1:8002`, which matches `frontend/next.config.ts` default rewrites.
  - `/paper-trading`, `/monitor`, `/data-governance`, `/config-center`, and `/risk` rendered without visible runtime errors or console errors.
  - `/paper-trading` showed OrderIntent/RiskGuard/PnL/执行链; `/monitor` reached `10.6 功能项 5/5` after live endpoints returned; `/data-governance` showed `存储契约`, `手动入库`, and `数据预览`.
  - Data-governance wording was aligned to `存储契约` and `手动入库与生命周期`.
- Latest repeat verification:
  - `python backend/scripts/phase2_acceptance.py` -> 49/49 passed.
  - `python -m pytest backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_phase2_live_acceptance.py backend/tests/unit/test_risk_manager_contract.py -q` -> 14 passed.
  - `python backend/scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url $DATABASE_URL --mutating-audit-check --json` -> 14/14 passed.
  - `python backend/scripts/phase2_acceptance.py --api-base http://127.0.0.1:8004 --timeout 12` -> 57/57 passed.
  - `cd frontend; npx eslint app/data-governance/page.tsx` -> passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` -> passed.
  - `python -m py_compile backend/scripts/phase2_acceptance.py` -> passed after synchronizing the data-governance marker to `存储契约`/`手动入库`.
  - `python backend/scripts/phase2_acceptance.py` -> 49/49 passed.
- Added paper execution audit-link hardening:
  - `backend/app/services/order_intent_service.py` now lets `PaperTradingService.execute_order_intent()` own the `PAPER_ORDER_FILLED` audit row and writes a distinct `ORDER_INTENT_EXECUTION_LINKED` row for the linkage.
  - `backend/app/services/audit_service.py` and `backend/app/services/paper_trading_workbench.py` recognize `ORDER_INTENT_EXECUTION_LINKED`.
  - `backend/app/services/paper_trading_workbench.py` deduplicates historical duplicate fill rows by `action + orderIntentId + orderId` while exposing raw vs deduped totals.
  - Live proof: BUY `PT-13` then SELL `PT-14` for `BTCUSDT`; `PT-14` closed the position and produced exactly one `PAPER_ORDER_FILLED` plus one `ORDER_INTENT_EXECUTION_LINKED`.
- Latest verification for paper execution audit-link hardening:
  - `python -m py_compile backend/app/services/audit_service.py backend/app/services/order_intent_service.py backend/app/services/paper_trading_workbench.py` -> passed.
  - `python -m pytest backend/tests/unit/test_order_intent_service.py backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_audit_service.py -q` -> 20 passed.
  - `python backend/scripts/phase2_acceptance.py` -> 49/49 passed.
  - `python -m pytest backend/tests/unit/test_order_intent_service.py backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_audit_service.py backend/tests/unit/test_phase2_live_acceptance.py -q` -> 25 passed after backend restart.
  - `python backend/scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url $DATABASE_URL --mutating-audit-check --json` -> 14/14 passed.
- Added live RiskGuard BLOCKED simulation proof:
  - Manual BUY `BTCUSDT`, quantity `0.00001`, price `100000`, exchange `okx` returned HTTP 400 because notional `$1.00` is below `MIN_ORDER_NOTIONAL=$5.00`.
  - Intent `OI-MANUAL-1781040381074` has one `ORDER_INTENT_CREATED`, one `RISK_BLOCKED`, zero fills, zero execution-link events, and zero `paper_trades`.
  - Both `127.0.0.1:8004` and frontend-rewrite backend `127.0.0.1:8002` show latest workbench item as `RISK_BLOCKED`, `status=BLOCKED`, `risk.rule=MIN_ORDER_NOTIONAL`, `orderId=null`, and positions still `0`.
- Latest verification for BLOCKED read-model hardening:
  - `python -m py_compile backend/app/services/paper_trading_workbench.py backend/tests/unit/test_paper_trading_workbench.py` -> passed.
  - `python -m pytest backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_order_intent_service.py -q` -> 15 passed.

## Active Blockers

- None blocking P0/P1 offline or local live API/DB acceptance.

Known environmental risks:

- Some backend tests may require PostgreSQL, ClickHouse, DuckDB files, Redis, or service environment variables.
- Local live API/DB acceptance now passes against backend/PostgreSQL/Redis/ClickHouse; NATS was not running, so full messaging workflows still need a NATS-enabled smoke.
- Replay-package live DB smoke still needs to run against richer real audit rows; API/DB live gate covers adjacent shape and audit immutability evidence.
- Data-platform migration `017` passed on local plain Postgres/pgvector with guarded Timescale DDL; full Timescale hypertable behavior, compression jobs, retention jobs, backup/PITR restore still need operational validation on a Timescale-enabled stack.
- Fundamentals, corporate actions, and adjustment factors now have concrete storage tables, PIT query adapters, provider-normalized upsert helpers, and an OpenBB financial refresh adapter; live migration and OpenBB dry-run checks passed locally, while real provider credentials/rate limits/data coverage still need production validation.
- DuckDB backtest archive has static/unit coverage and a live local-data proof (`backtest_id=9`) for write/read/detail/audit linkage across `127.0.0.1:8004` and `127.0.0.1:8002`; remaining risk is broader strategy/agent-audited backtest scenario coverage, not basic archive visibility.
- Phase2 operations monitor has unit/static/frontend coverage and live API shape coverage; richer data freshness/resource assertions still need long-running services and populated datasets.
- Paper-trading workbench has unit/static/frontend coverage, live API shape coverage, live-browser rendering coverage, a fresh BUY/SELL simulated execution proof (`PT-13`/`PT-14`), and a fresh RiskGuard BLOCKED proof (`OI-MANUAL-1781040381074`) showing no paper order/fill/link rows; remaining paper-trading risk is richer PnL/session scenario coverage rather than basic lifecycle proof.
- Frontend `npm run lint` has pre-existing unrelated failures across tests/shared pages/components, mostly `no-explicit-any`, React compiler purity rules, and CommonJS `require()` rules.
- Reference repositories are read-only and must not be modified.

## Next Actions

1. Run an `agent_audited` backtest with a very small `maxAgentCalls` to verify Agent participation stats, decision/audit links, and rule-only comparison on live local data.
2. Start NATS and rerun a messaging-enabled backend smoke for TradingAgents/task workflows.
3. Add richer paper-trading PnL/session scenario coverage after the basic fill/block lifecycle proofs are stable.
4. Repeat `python backend/scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url=$DATABASE_URL --mutating-audit-check --json` after any backend/storage change.
5. Run operational PITR restore validation outside the application test harness.
6. Decide whether to clean the broader frontend lint backlog in a separate slice.
