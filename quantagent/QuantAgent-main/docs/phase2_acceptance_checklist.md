# Phase 2 Acceptance Checklist

Last updated: 2026-06-10

Status markers:

- `[x]` inspected or already present in target repository.
- `[ ]` pending implementation or verification.
- `[~]` partially present, needs focused verification or hardening.

## Documentation

- [x] Goal state persisted in `docs/phase2_goal_state.md`.
- [x] Requirements context persisted in `docs/phase2_requirements_context.md`.
- [x] Gap analysis persisted in `docs/phase2_gap_analysis.md`.
- [x] Implementation plan persisted in `docs/phase2_implementation_plan.md`.
- [x] Acceptance checklist persisted in this file.

## Backend Audit

- [x] Audit model contains `payload_hash`, `prev_hash`, `context_hash`, `immutable`, `decision_id`, `backtest_id`, `replay_session_id`, `order_intent_id`, and `order_id`.
- [x] Audit service computes stable payload hash and previous hash chain.
- [x] Append-only database trigger exists in migration and live PostgreSQL update/delete rejection was verified with an immutable proof row.
- [x] Audit detail API returns immutable/hash/link evidence.
- [x] Audit JSON export includes input snapshot/decision details, RiskGuard/execution details, PIT context, hash chain, and immutable status.
- [x] Focused audit tests executed and results recorded.

## Agent Decision Traceability

- [x] AnalysisContext carries `input_snapshot_ids`, `data_versions`, `as_of_time`, `available_time` checks, and `context_hash`.
- [x] Agent decision audit records context snapshot and normalized decision.
- [x] TradingAgents fast mode and full graph/patched graph mode are distinguishable.
- [x] Agent bar path verified and hardened to avoid direct external live fallback.
- [x] Focused Agent traceability tests executed and results recorded.

## Financial Data Platform Storage

- [x] PostgreSQL/TimescaleDB migration declares `instrument`, `bar_1m`, `bar_1h`, `bar_1d`, `quote_latest`, `fundamental_report`, `corporate_action`, `adjustment_factor`, `etl_job_log`, `news_event`, and `macro_indicator`.
- [x] Migration declares `data_provider`, `data_lineage`, `cleaned_data_item`, and `data_platform_storage_policy` for provider registry, lineage, changed-data versioning, compression/retention/PITR policy evidence.
- [x] Bar tables include PIT fields, `(symbol, ts)` indexes, upsert-friendly uniqueness, quality flags, outlier/gap fields, cleaning rule versions, unit/null policy, and lineage JSON.
- [x] Timescale extension, hypertable, and compression setup are guarded so plain PostgreSQL environments do not fail silently.
- [x] `GET /api/v1/meta/storage-contract` exposes the structured storage, ETL, scheduler, PIT, local-only, and lifecycle contract.
- [x] Fundamentals, corporate actions, and adjustment factors endpoints read from local PostgreSQL storage-contract tables with `available_time <= as_of_time`.
- [x] Local table reads use a whitelist query helper and return structured `not_ingested_yet` or `local_storage_unavailable` states without external fallback.
- [x] Provider-normalized local ingestion supports dry-run and transactional idempotent upsert for fundamentals, corporate actions, and adjustment factors.
- [x] Local ingestion writes stable record IDs, raw payload hashes, ETL job log rows, and data lineage rows.
- [x] Explicit OpenBB financial refresh API exists at `POST /api/v1/meta/refresh-financials`.
- [x] OpenBB financial adapter normalizes fundamentals, corporate actions, and adjustment factors before local ingestion.
- [x] Provider refresh defaults to dry-run and never becomes a hidden Agent/backtest external fallback.
- [x] Data governance overview/page exposes storage contract, manual ingest contract, lifecycle policy, and preview tabs for fundamentals/corporate actions/adjustment factors.
- [x] Live PostgreSQL migration application was verified through Alembic head `017` on the local `pgvector/pg16` container.
- [x] Live data-platform table, PIT column, bar index, storage-policy, and audit append-only metadata checks passed.
- [~] TimescaleDB hypertable/compression behavior and backup/PITR restore still require a Timescale-enabled/operational environment.

## OrderIntent, RiskGuard, Paper Execution

- [x] OrderIntent includes normalized direction, position percent/ratio, validity, confidence, reason/context, and source decision ID.
- [x] RiskGuard covers single-position max, total exposure max, forbidden symbols, daily-loss circuit breaker, max drawdown, leverage, minimum order notional, WAIT behavior, and failure-action intent.
- [x] RiskGuard config/API/UI support `MIN_ORDER_NOTIONAL`, `WAIT_ORDER_INTENT_POLICY`, and `RISK_FAILURE_ACTION`.
- [x] RiskGuard records configured `block|reduce|warn` action intent but effective simulated execution remains non-bypassable `BLOCKED` on any failed check.
- [x] Risk pass writes audit.
- [x] Risk block writes BLOCKED/REJECTED audit and prevents fill.
- [x] Paper fill/reject writes linked audit evidence.
- [x] OrderIntent paper-execution wrapper writes one `PAPER_ORDER_FILLED` audit event per new paper order and a separate `ORDER_INTENT_EXECUTION_LINKED` linkage event, preventing duplicate fill evidence.
- [x] Dedicated paper-trading workbench API exists at `GET /api/v1/trading/workbench`.
- [x] Paper-trading workbench aggregates account/mode, OrderIntent events, RiskGuard checks, paper orders/fills, positions, PnL/equity curve, execution chain, and immutable audit links.
- [x] Paper-trading workbench shows blocked RiskGuard events as `BLOCKED` even when the underlying draft intent status remains `CREATED`.
- [x] Paper-trading workbench deduplicates historical duplicate fill rows by `action + orderIntentId + orderId` while exposing `raw_total`, `deduped_total`, and the dedupe rule for audit transparency.
- [x] Focused OrderIntent/RiskGuard tests executed and results recorded.

## Backtest and Replay

- [x] Backtest service/API inspected for symbol, interval, start/end time, initial capital, fees, slippage, risk config, and Agent mode.
- [x] Backtest PIT evidence verified in helper tests and static acceptance: checks expose `available_time <= as_of_time` violations.
- [x] Backtest, optimization, and batch backtest market-data loads explicitly disable OpenBB/CCXT/Binance fallback and use local persisted market data only.
- [x] Backtest persists metrics, equity/drawdown, trades, decision points, risk blocks, and Agent participation stats.
- [x] Backtest result archive writes a DuckDB contract row with PRD metrics, PIT evidence, trades, equity curve, params, execution mode, and Agent stats.
- [x] DuckDB archive uses short-lived connections with commit/close so multiple local backend processes can read newly archived rows consistently.
- [x] Backtest result links to audit or replay.
- [x] Backtest detail API imports `AuditLog` correctly and returns audit-linked detail instead of failing on live records.
- [x] Backtest task queue exposes async status, max parallel 5, cancel, retry, and PostgreSQL + DuckDB archive storage metadata.
- [x] Replay reconstructs from immutable audit/context evidence without mutating originals in inspected audit replay path.
- [x] Cross-workbench replay package API exists and returns strict snapshot replay evidence or an explicit local PIT rebuild contract.
- [x] Replay package includes Agent input record IDs, data versions, visible-data checks, role outputs, OrderIntent, RiskGuard, execution result, and immutable audit chain fields.
- [x] Focused backtest/replay tests executed and results recorded.

## Frontend

- [x] Audit page inspected for records, filters, detail, input snapshot, Agent output, risk/execution chain, PIT checks, hash/immutable evidence, and JSON export.
- [x] Decision page inspected for controls, status, input summary, role outputs, final decision, and history.
- [x] Backtest page inspected for config, status/results, metrics, trade table, PIT checks, Agent stats, and links.
- [x] Backtest page exposes DuckDB archive path/schema plus cancel/retry task controls.
- [x] Replay page inspected for replay state and evidence.
- [x] Data governance page surfaces storage contract tables, manual ingest endpoint, lifecycle policies, and additional financial-data preview tabs.
- [x] Data governance page uses consistent "存储契约" and "手动入库" language for the storage/ingestion contract.
- [x] Data governance page surfaces the explicit OpenBB financial refresh endpoint.
- [x] `/paper-trading` implements the simulated trading desk with account/mode, OrderIntent, RiskGuard, simulated orders, positions, PnL/equity curve, and execution-chain panels.
- [x] Local browser smoke completed on `http://localhost:3002`.

## P1/P2 Configuration and Monitoring

- [x] TradingAgents effective configuration API exists at `GET /api/v1/system/tradingagents-config`.
- [x] TradingAgents API redacts service/LLM URLs and does not expose API keys.
- [x] TradingAgents API reports provider, model, configured mode, fast research readiness, full graph readiness, and strong acceptance eligibility.
- [x] TradingAgents API repeats the Agent input boundary: `local_storage_only`, no external/CCXT/Binance fallback, and `available_time <= as_of_time`.
- [x] P1/P2 status API exists at `GET /api/v1/system/phase2-p1p2-status`.
- [x] Monitor page displays TradingAgents configuration and readiness.
- [x] Phase2 operations monitor API exists at `GET /api/v1/system/phase2-ops-monitor`.
- [x] Phase2 operations monitor covers data freshness, TradingAgents, LLM monitor contract, audit health, execution/RiskGuard, backtest/replay queue, DuckDB archive, and resources.
- [x] Monitor page displays Phase2 operations health, PIT/local-only boundary, audit immutability/hash coverage, RiskGuard execution chain, and backtest DuckDB archive visibility.
- [x] RiskGuard config metadata API exists at `GET /api/v1/risk/config-metadata`.
- [x] RiskGuard config update API covers total exposure, forbidden symbols, margin thresholds, volatility thresholds, minimum order notional, WAIT policy, failure action, and audit logging.
- [x] RiskGuard config reset API exists at `POST /api/v1/risk/config/reset`.
- [x] Dedicated RiskGuard configuration page exists at `/risk`.
- [x] Config center role editor supports TradingAgents role enablement, prompt version, prompt, skill, per-role LLM provider/model/base URL, and default LLM inheritance evidence.
- [x] Config center custom Agent controls support create/edit/delete and independent or default-inherited LLM settings.
- [x] Research snapshot/as-of review and backtest-to-research links are already present in `/signals`, `/backtest`, and `/market/research-snapshot/{symbol}`.
- [x] Advanced replay/backtest comparison APIs and analytics page are already present.
- [ ] Custom Agent marketplace, complex approval workflow, live broker execution, multi-market expansion, and large platform migration are deferred P2 items from the documents, not invented scope.

## Acceptance Script

- [x] `backend/scripts/phase2_acceptance.py` exists.
- [x] Script checks data-platform as-of/snapshot availability or target equivalent.
- [x] Script checks Agent decision audit evidence.
- [x] Script checks local snapshot/context hash evidence.
- [x] Script checks OrderIntent generation.
- [x] Script checks RiskGuard pass and block audit paths.
- [x] Script checks paper execution audit linkage.
- [x] Script checks backtest metrics and no-future-data evidence.
- [x] Script checks audit JSON export.
- [x] Script checks append-only audit enforcement or reports required DB precondition.
- [x] Script executed and result recorded.
- [x] Script includes P1 TradingAgents config API and monitor panel checks.
- [x] Script includes P1/P2 RiskGuard config API and frontend page checks.
- [x] Script includes RiskGuard runtime checks for minimum order notional, WAIT policy, and failure-action evidence.
- [x] Script includes workbench linkage and replay-package contract markers.
- [x] Script includes data-platform storage migration and `/meta/storage-contract` checks.
- [x] Script includes local PIT table-query checks for fundamentals, corporate actions, and adjustment factors.
- [x] Script includes local ingestion/upsert, lineage, ETL job log, and manual ingest API checks.
- [x] Script includes OpenBB financial adapter and explicit refresh API checks.
- [x] Script includes backtest DuckDB archive and queue cancel/retry checks.
- [x] Script includes Phase2 operations monitor service/API/frontend checks.
- [x] Script includes editable config-center roles/custom Agents and paper-trading workbench service/API/frontend checks.
- [x] Live acceptance gate exists at `backend/scripts/phase2_live_acceptance.py` for API shape, DB migration/table/index, Timescale policy, OpenBB dry-run, ops monitor, paper-trading workbench, and append-only audit proof.
- [x] Live acceptance gate executed against local backend/PostgreSQL with API + DB + `--mutating-audit-check`.

## Verification Log

- Baseline backend: `python -m pytest tests/unit/test_audit_service.py tests/unit/test_tradingagents_adapter_context.py tests/unit/test_order_intent_service.py tests/unit/test_backtest_p3_helpers.py -q` -> 26 passed.
- Expanded backend: `python -m pytest tests/unit/test_audit_service.py tests/unit/test_tradingagents_adapter_context.py tests/unit/test_order_intent_service.py tests/unit/test_backtest_p3_helpers.py tests/unit/test_analysis_context_builder_pit.py -q` -> 29 passed.
- Acceptance: `python backend/scripts/phase2_acceptance.py` -> 10/10 passed.
- P1 focused backend: `python -m pytest tests/unit/test_system_tradingagents_config.py tests/unit/test_tradingagents_adapter_context.py tests/unit/test_analysis_context_builder_pit.py -q` -> 9 passed.
- P1/P2 acceptance: `python backend/scripts/phase2_acceptance.py` -> 12/12 passed.
- Monitor page lint: `npx eslint app/monitor/page.tsx` -> passed.
- Frontend typecheck: `npx tsc --noEmit --pretty false --incremental false` -> passed.
- P1/P2 config backend: `python -m pytest tests/unit/test_risk_config_api.py tests/unit/test_system_tradingagents_config.py tests/unit/test_tradingagents_adapter_context.py tests/unit/test_analysis_context_builder_pit.py -q` -> 17 passed.
- P1/P2 config acceptance: `python backend/scripts/phase2_acceptance.py` -> 14/14 passed.
- Risk/config page lint: `npx eslint app/risk/page.tsx components/navigation/AppTopNav.tsx components/navigation/Breadcrumb.tsx app/monitor/page.tsx` -> passed.
- Frontend typecheck after RiskGuard config page: `npx tsc --noEmit --pretty false --incremental false` -> passed.
- Full frontend lint: prior `npm run lint` failed on pre-existing unrelated lint backlog; this pass used page-scoped lint for the edited monitor page and it passed.
- Browser smoke: `/audit`, `/decisions`, `/backtest`, `/replay` mounted without Next error overlays on `http://localhost:3002`; `/decisions` showed backend HTTP 500 because the backend API stack was not running.
- Browser smoke: `/monitor` mounted on `http://localhost:3002`, TradingAgents configuration/readiness panel rendered, and no Next error overlay appeared. With backend unavailable, monitor shows a friendly load error instead of a raw JSON parse error.
- Browser smoke: `/risk` mounted on `http://localhost:3002`, RiskGuard configuration page rendered, breadcrumb label is Chinese, backend-unavailable state shows a friendly load error, and no Next error overlay appeared.
- Workbench linkage/replay package backend: `python -m pytest backend/tests/unit/test_linkage_contract.py backend/tests/unit/test_database_redis_fast_degrade.py backend/tests/unit/test_analysis_context_builder_pit.py -q` -> 10 passed.
- Workbench linkage/replay package acceptance: `python backend/scripts/phase2_acceptance.py` -> 31/31 passed.
- Workbench linkage/replay package frontend: `npx tsc --noEmit --pretty false --incremental false` -> passed.
- Workbench linkage/replay package lint: `npx eslint app/dashboard/page.tsx components/linkage/WorkbenchLinkBar.tsx components/charts/TradingViewChart.tsx lib/replay-store.tsx` -> passed.
- Data-platform storage contract compile: `python -m py_compile backend/app/api/v1/endpoints/data_platform.py backend/migrations/versions/017_data_platform_contract_tables.py backend/scripts/phase2_acceptance.py` -> passed.
- Data-platform storage contract tests: `python -m pytest backend/tests/unit/test_data_platform_helpers.py -q` -> 5 passed.
- Data-platform storage contract acceptance: `python backend/scripts/phase2_acceptance.py` -> 33/33 passed.
- Data-platform local PIT table-query compile: `python -m py_compile backend/app/services/data_platform_storage.py backend/app/api/v1/endpoints/data_platform.py backend/scripts/phase2_acceptance.py` -> passed.
- Data-platform local PIT table-query tests: `python -m pytest backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_storage.py -q` -> 9 passed.
- Data-platform local PIT table-query acceptance: `python backend/scripts/phase2_acceptance.py` -> 35/35 passed.
- Data-platform ingestion/upsert compile: `python -m py_compile backend/app/services/data_platform_ingestion.py backend/app/services/data_platform_storage.py backend/app/api/v1/endpoints/data_platform.py backend/scripts/phase2_acceptance.py` -> passed.
- Data-platform ingestion/upsert tests: `python -m pytest backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_storage.py backend/tests/unit/test_data_platform_ingestion.py -q` -> 15 passed.
- Data-platform ingestion/upsert acceptance: `python backend/scripts/phase2_acceptance.py` -> 37/37 passed.
- Data-governance storage visibility compile: `python -m py_compile backend/app/api/v1/endpoints/data_governance.py backend/app/api/v1/endpoints/data_platform.py backend/scripts/phase2_acceptance.py` -> passed.
- Data-governance storage visibility backend tests: `python -m pytest backend/tests/unit/test_data_governance_contract.py backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_storage.py backend/tests/unit/test_data_platform_ingestion.py -q` -> 17 passed.
- Data-governance storage visibility acceptance: `python backend/scripts/phase2_acceptance.py` -> 37/37 passed.
- Data-governance page lint/typecheck: `npx eslint app/data-governance/page.tsx` -> passed; `npx tsc --noEmit --pretty false --incremental false` -> passed.
- Backtest DuckDB archive/queue compile: `python -m py_compile backend/app/services/backtest_duckdb_store.py backend/app/api/v1/endpoints/strategy.py backend/scripts/phase2_acceptance.py` -> passed.
- Backtest DuckDB archive/queue tests: `python -m pytest backend/tests/unit/test_backtest_duckdb_store.py backend/tests/unit/test_backtest_p3_helpers.py -q` -> 12 passed.
- Backtest DuckDB archive/queue acceptance: `python backend/scripts/phase2_acceptance.py` -> 40/40 passed.
- Backtest local-only + DuckDB multi-backend hardening compile: `python -m py_compile backend/app/services/backtest_duckdb_store.py backend/app/api/v1/endpoints/strategy.py backend/scripts/phase2_acceptance.py` -> passed.
- Backtest local-only + DuckDB multi-backend hardening tests: `python -m pytest backend/tests/unit/test_backtest_duckdb_store.py backend/tests/unit/test_backtest_p3_helpers.py -q` -> 16 passed.
- Backtest local-only + DuckDB static acceptance: `python backend/scripts/phase2_acceptance.py` -> 50/50 passed.
- Live backtest archive proof: `POST /api/v1/strategy/backtest/run` on `127.0.0.1:8004` with `BTCUSDT`, `1h`, `limit=400`, `as_of_time=2026-06-09T21:00:00Z`, `ma`, `rule_only` produced `backtest_id=9`, `data_source=market_data_gateway:local_storage`, `pit_passed=true`, `bars=400`, `trades=12`, `duckdb_status=archived`, and `audit_count=1`.
- Live DuckDB cross-backend proof: both `127.0.0.1:8004` and frontend-rewrite backend `127.0.0.1:8002` returned DuckDB archive IDs `[9, 8, 7]`, proving newly written archive rows are visible across local backend processes.
- Live backtest detail proof: `GET /api/v1/strategy/backtest/history/9` returned `schema_version=backtest_detail.v1`, `dataSource=market_data_gateway:local_storage`, `bars=400`, and `auditCount=1`.
- Frontend typecheck after backtest queue controls: `npx tsc --noEmit --pretty false --incremental false` -> passed.
- Backtest page full lint remains blocked by pre-existing `frontend/app/backtest/page.tsx` lint debt unrelated to this slice; page-scoped lint was not used as a passing gate.
- Phase2 ops monitor compile: `python -m py_compile backend/app/services/phase2_ops_monitor.py backend/app/api/v1/endpoints/system_health.py backend/scripts/phase2_acceptance.py` -> passed.
- Phase2 ops monitor backend tests: `python -m pytest backend/tests/unit/test_phase2_ops_monitor.py backend/tests/unit/test_system_tradingagents_config.py -q` -> 6 passed.
- Phase2 ops monitor acceptance: `python backend/scripts/phase2_acceptance.py` -> 43/43 passed.
- Phase2 ops monitor frontend lint/typecheck: `npx eslint app/monitor/page.tsx` -> passed; `npx tsc --noEmit --pretty false --incremental false` -> passed.
- OpenBB financial adapter compile: `python -m py_compile backend/app/services/openbb_financial_adapter.py backend/app/api/v1/endpoints/data_platform.py backend/app/api/v1/endpoints/data_governance.py backend/scripts/phase2_acceptance.py` -> passed.
- OpenBB financial adapter backend tests: `python -m pytest backend/tests/unit/test_openbb_financial_adapter.py backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_ingestion.py -q` -> 14 passed.
- OpenBB financial adapter acceptance: `python backend/scripts/phase2_acceptance.py` -> 44/44 passed.
- Data-governance frontend after OpenBB refresh entry: `npx eslint app/data-governance/page.tsx` -> passed; `npx tsc --noEmit --pretty false --incremental false` -> passed.
- Config center editability compile: `python -m py_compile backend/app/api/v1/endpoints/config_center.py backend/scripts/phase2_acceptance.py` -> passed.
- Config center editability backend tests: `python -m pytest backend/tests/unit/test_config_center_contract.py -q` -> 5 passed.
- Config center editability acceptance/frontend: `python backend/scripts/phase2_acceptance.py` -> 44/44 passed; `npx eslint app/config-center/page.tsx` -> passed; `npx tsc --noEmit --pretty false --incremental false` -> passed.
- Paper-trading workbench compile: `python -m py_compile backend/app/services/paper_trading_workbench.py backend/app/api/v1/endpoints/trading.py backend/scripts/phase2_acceptance.py` -> passed.
- Paper-trading workbench backend tests: `python -m pytest backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_order_intent_service.py -q` -> 11 passed.
- Paper-trading workbench acceptance: `python backend/scripts/phase2_acceptance.py` -> 47/47 passed.
- Paper-trading workbench frontend lint/typecheck: `npx eslint app/paper-trading/page.tsx components/navigation/AppTopNav.tsx components/navigation/Breadcrumb.tsx` -> passed; `npx tsc --noEmit --pretty false --incremental false` -> passed.
- RiskGuard PRD execution-contract compile: `python -m py_compile backend/app/core/config.py backend/app/services/risk_manager.py backend/app/api/v1/endpoints/risk.py backend/app/services/order_intent_service.py backend/app/api/v1/endpoints/strategy.py backend/app/services/phase2_ops_monitor.py backend/scripts/phase2_acceptance.py` -> passed.
- RiskGuard PRD execution-contract backend tests: `python -m pytest backend/tests/unit/test_risk_config_api.py backend/tests/unit/test_risk_manager_contract.py backend/tests/unit/test_order_intent_service.py backend/tests/unit/test_backtest_p3_helpers.py -q` -> 35 passed.
- RiskGuard PRD execution-contract acceptance: `python backend/scripts/phase2_acceptance.py` -> 48/48 passed.
- RiskGuard PRD execution-contract frontend lint/typecheck: `npx eslint app/risk/page.tsx` -> passed; `npx tsc --noEmit --pretty false --incremental false` -> passed.
- Phase2 live acceptance gate compile: `python -m py_compile backend/scripts/phase2_live_acceptance.py` -> passed.
- Phase2 live acceptance gate unit tests: `python -m pytest backend/tests/unit/test_phase2_live_acceptance.py -q` -> 5 passed.
- Phase2 live acceptance gate empty-run JSON smoke: `python backend/scripts/phase2_live_acceptance.py --api-base= --database-url= --json` -> passed with empty result set.
- Phase2 static acceptance after live-gate registration: `python backend/scripts/phase2_acceptance.py` -> 49/49 passed.
- Phase2 live DB migration: `DATABASE_URL=postgresql+asyncpg://quantagent:quantagent@localhost:5435/quantagent python -m alembic upgrade head` -> passed after widening the Timescale extension guard.
- Phase2 live DB gate: `python scripts/phase2_live_acceptance.py --api-base= --database-url=$DATABASE_URL --mutating-audit-check --json` -> 7/7 passed.
- Phase2 live API+DB gate: `python scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url=$DATABASE_URL --mutating-audit-check --json` -> 14/14 passed.
- Phase2 static+live acceptance: `python scripts/phase2_acceptance.py --api-base http://127.0.0.1:8004 --timeout 12` -> 57/57 passed.
- RiskManager live-gate fix tests: `python -m pytest backend/tests/unit/test_risk_manager_contract.py backend/tests/unit/test_phase2_live_acceptance.py -q` -> 8 passed.
- Phase2 repeat live API+DB gate: `python backend/scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url $DATABASE_URL --mutating-audit-check --json` -> 14/14 passed.
- Phase2 repeat static+live acceptance: `python backend/scripts/phase2_acceptance.py --api-base http://127.0.0.1:8004 --timeout 12` -> 57/57 passed.
- Focused backend docs/live-gate tests: `python -m pytest backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_phase2_live_acceptance.py backend/tests/unit/test_risk_manager_contract.py -q` -> 14 passed.
- Frontend live-backend smoke: started a second backend on `127.0.0.1:8002` using the same local Postgres/Redis/ClickHouse settings so existing Next rewrites on `http://127.0.0.1:3002` hit live APIs; `/paper-trading`, `/monitor`, `/data-governance`, `/config-center`, and `/risk` rendered without visible runtime errors or console errors.
- Frontend live smoke detail: `/monitor` reached `10.6 功能项 5/5` after the slower live operations endpoints returned; `/data-governance` showed `存储契约`, `手动入库`, and `数据预览`; `/paper-trading` showed OrderIntent/RiskGuard/PnL/执行链.
- Data-governance wording lint/typecheck: `cd frontend; npx eslint app/data-governance/page.tsx` -> passed; `cd frontend; npx tsc --noEmit --pretty false --incremental false` -> passed.
- Acceptance marker sync: `backend/scripts/phase2_acceptance.py` now checks `存储契约` and `手动入库`; `python -m py_compile backend/scripts/phase2_acceptance.py` -> passed; `python backend/scripts/phase2_acceptance.py` -> 49/49 passed.
- Paper execution audit-link hardening: `backend/app/services/order_intent_service.py` now delegates fill audit to the paper-trading execution path and writes `ORDER_INTENT_EXECUTION_LINKED` for the OrderIntent-to-order relationship; `backend/app/services/audit_service.py` and `backend/app/services/paper_trading_workbench.py` recognize the new event type.
- Live simulated execution proof: created BUY `PT-13` then SELL `PT-14` for `BTCUSDT` quantity `0.0001` at price `100000`; `PT-14` closed the position and produced exactly one `PAPER_ORDER_FILLED` plus one `ORDER_INTENT_EXECUTION_LINKED` audit row.
- Workbench duplicate-read proof: historical duplicate immutable rows from `PT-13` remain untouched, while the workbench read model reports deduped fills using `action + orderIntentId + orderId` and exposes raw vs deduped totals.
- Paper execution audit-link verification: `python -m py_compile backend/app/services/audit_service.py backend/app/services/order_intent_service.py backend/app/services/paper_trading_workbench.py` -> passed.
- Paper execution audit-link tests: `python -m pytest backend/tests/unit/test_order_intent_service.py backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_audit_service.py -q` -> 20 passed.
- Paper execution audit-link repeat tests after backend restart: `python -m pytest backend/tests/unit/test_order_intent_service.py backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_audit_service.py backend/tests/unit/test_phase2_live_acceptance.py -q` -> 25 passed.
- Static acceptance after paper execution audit-link hardening: `python backend/scripts/phase2_acceptance.py` -> 49/49 passed.
- Live gate after paper execution audit-link hardening: `python backend/scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url $DATABASE_URL --mutating-audit-check --json` -> 14/14 passed.
- Live RiskGuard BLOCKED proof: manual BUY `BTCUSDT`, quantity `0.00001`, price `100000`, exchange `okx` returned HTTP 400 with `订单名义金额 $1.00 低于最小订单金额 $5.00`; intent `OI-MANUAL-1781040381074` has one `ORDER_INTENT_CREATED`, one `RISK_BLOCKED`, zero `PAPER_ORDER_FILLED`, zero `ORDER_INTENT_EXECUTION_LINKED`, and zero `paper_trades`.
- Workbench blocked-read proof: both `127.0.0.1:8004` and frontend-rewrite backend `127.0.0.1:8002` show the latest `BTCUSDT` item as `RISK_BLOCKED`, `status=BLOCKED`, `risk.rule=MIN_ORDER_NOTIONAL`, `risk.passed=false`, `orderId=null`, and `positionsTotal=0`.
- Workbench blocked-status hardening compile/tests: `python -m py_compile backend/app/services/paper_trading_workbench.py backend/tests/unit/test_paper_trading_workbench.py` -> passed; `python -m pytest backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_order_intent_service.py -q` -> 15 passed.
