# Phase 2 Full-Scope Task Board

Last updated: 2026-06-10

This board persists the deep-analysis findings from the three source requirement files:

- `C:/Users/yhy05/Desktop/量化/功能模块V2.xlsx`
- `C:/Users/yhy05/Desktop/量化/金融数据平台子系统需求.docx`
- `C:/Users/yhy05/Desktop/量化/量化研究平台 · 第二阶段 PRD.docx`

The raw extraction is stored in `docs/phase2_source_requirements_extracted.md`. It includes Excel merged-cell inherited text, visible cell content, later remark columns, and Word table/comment XML evidence.

## Non-Negotiable Acceptance Rules

- Data -> decision -> execution -> visualization -> audit -> replay/backtest must form a closed loop.
- Agent, research review, replay, and backtest must use point-in-time data only: `available_time <= as_of_time` or an equivalent visibility rule.
- Agent inputs must come from local persisted storage before being forwarded to any Agent or LLM.
- Agent-facing data boundary is `local_storage_only`; live provider refresh is an explicit manual operation and cannot be used as an Agent/backtest hidden fallback.
- Every Agent input must record data record IDs or stable snapshot IDs, including bars, factors, signals, news, macro, context hash, and data versions.
- Audit records are append-only, immutable, traceable, exportable, and replayable.
- RiskGuard failures are blocking events. They must be written to audit and must not be bypassed.
- The system must support crypto, equities, futures/perpetuals, and future fixed-income/macro data expansion without crypto-only assumptions.

## Workstreams

### 1. Financial Data Platform

Status: in progress

Required scope:

- OpenBB + local storage gateway with provider registration, health, priority, fallback, rate-limit metadata, and custom provider skeleton.
- PostgreSQL/TimescaleDB contract for `instrument`, `bar_1m`, `bar_1h`, `bar_1d`, `quote_latest`, `fundamental_report`, `corporate_action`, `etl_job_log`, `news_event`, `macro_indicator`.
- Existing local implementation uses ClickHouse `market_bars` and DuckDB `macro_indicators`/`news_articles`; expose these through PRD-compatible top-level API routes while keeping the storage contract visible.
- ETL contract: idempotent upsert, dedupe, gap fill metadata, outlier flags, adjustment-factor independence, UTC timestamps, type/null/unit normalization, cleaning rule versions, multi-source comparison, lineage, and job logs.
- Scheduler contract: Prefect 3 compatible routes/status, with current implementation backed by the existing pipeline orchestrator until Prefect is installed.
- API routes must expose unified `{data, meta, errors}`:
  - `/api/v1/bars`
  - `/api/v1/bars/batch`
  - `/api/v1/quotes/latest`
  - `/api/v1/quotes/history`
  - `/api/v1/fundamentals/{symbol}`
  - `/api/v1/fundamentals/{symbol}/latest`
  - `/api/v1/instruments`
  - `/api/v1/instruments/{symbol}`
  - `/api/v1/instruments/search`
  - `/api/v1/corporate-actions/{symbol}`
  - `/api/v1/adjust-factors/{symbol}`
  - `/api/v1/macro/indicators`
  - `/api/v1/macro/indicators/{code}`
  - `/api/v1/news`
  - `/api/v1/news/{id}`
  - `/api/v1/meta/coverage`
  - `/api/v1/meta/providers`
  - `/api/v1/meta/jobs`
  - `/api/v1/meta/jobs/{batch_id}`
  - `/api/v1/bars/as-of`
  - `/api/v1/snapshot`

Current implementation target:

- Add a top-level data-platform adapter router that reuses `market_data_gateway`, ClickHouse `market_bars`, DuckDB pipeline storage, and `AnalysisContextBuilder`.
- Keep live/external source fetch opt-in. Agent/research/backtest paths remain local-only.
- Added PostgreSQL/TimescaleDB storage contract migration `017_data_platform_contract_tables.py` with `data_provider`, `instrument`, `bar_1m`, `bar_1h`, `bar_1d`, `quote_latest`, `fundamental_report`, `corporate_action`, `adjustment_factor`, `etl_job_log`, `news_event`, `macro_indicator`, `data_lineage`, `cleaned_data_item`, and `data_platform_storage_policy`.
- Added `/api/v1/meta/storage-contract` so the table, PIT, upsert, ETL, scheduler, lineage, compression, retention, and PITR contract is visible through the API.
- Added local PostgreSQL PIT query helper for `fundamental_report`, `corporate_action`, and `adjustment_factor`; API reads now use `available_time <= as_of_time`, `local_storage_only`, and return honest `not_ingested_yet`/`local_storage_unavailable` states instead of external fallback.
- Added local ingestion/upsert helper and manual ingest API for provider-normalized `fundamental_report`, `corporate_action`, and `adjustment_factor` records; writes are idempotent, transactional, and record `etl_job_log` plus `data_lineage`.
- Data governance overview/page now exposes the storage contract, manual ingest API, and preview tabs for fundamentals, corporate actions, and adjustment factors.

### 2. Research Desk, Factors, And Signals

Status: in progress

Required scope:

- Top control bar, market panel, market snapshot, news/macro panel, and AnalysisContext panel.
- Standard Bar display: candlestick, volume, VWAP, latest price, change, high/low, interval, provider, latest bar time, stale status.
- Financial news ingestion, sector/symbol extraction, live push path, manual symbol submission from news, factor calculation, signal alert generation.
- Factor/signal page: context header, factor overview, current `as_of_time` snapshot, signal overview, signal events table, timeline, research/config panels, new factor config, signal condition config.

Current implementation target:

- Preserve existing `/signals` and `/api/v1/signals/context/{symbol}` PIT logic.
- Wire PRD top-level data-platform snapshot routes into research/backtest/audit linkage.

### 3. TradingAgents Decision And Agent Configuration

Status: in progress

Required scope:

- Decision page supports BTCUSDT/ETHUSDT/SOLUSDT and extensible symbols, 1m/5m/15m/1h/4h/1d, quick/full LangGraph, real-time/historical `as_of_time`, background jobs, history, status refresh.
- Task chain: AnalysisContext -> market/news/macro -> bull/bear -> research manager -> trader -> risk analysts -> final decision -> audit.
- Input summary defaults collapsed and includes bar/factor/signal/news/macro counts, `as_of_time`, PIT check, `context_hash`, and data versions.
- Role panels for market, news, macro/fundamental, scenario summary, bull, bear, manager, trader, aggressive/conservative/neutral risk, final judge.
- Final decision card always shows BUY/SELL/WAIT, confidence, position advice, risk flags, core reasons, generation time, `decision_id`, and actions for OrderIntent, paper trading, audit, backtest, copy.
- Config center supports default mode, LLM provider, model, base URL, role switches, max run time, background run, prompt version, zh-CN output, full output save, audit write.
- Custom agents can have independent LLM, prompt, and skill configuration, falling back to default LLM when unset.

Current implementation target:

- Preserve existing `/api/v1/system/tradingagents-config` effective readiness.
- Add `/api/v1/config-center/tradingagents` and custom-agent local persistence.
- Added editable TradingAgents role configuration in config center:
  - `PATCH /api/v1/config-center/tradingagents/roles/{role_id}` persists role enablement, prompt version, prompt, skill, provider, model, and base URL.
  - Role configs now return `effective_llm` with default inheritance evidence.
  - `/config-center` supports inline role editing plus custom Agent create/edit/delete; custom Agents can use independent LLM settings or inherit defaults.

### 4. Execution Layer And Simulated Trading

Status: in progress

Required scope:

- OrderIntent standard object: `long|short|flat`, position ratio, validity, reason, linked decision/context/audit IDs.
- RiskGuard rules: single position, total exposure, per-symbol exposure, forbidden symbols, daily loss, max drawdown, leverage, min order notional, WAIT behavior, failure action `block|reduce|warn`.
- Risk failure writes `BLOCKED` audit and cannot be bypassed.
- Simulated trading desk shows account/mode, OrderIntent list, RiskGuard check, orders/fills, positions, PnL/equity curve, execution chain.
- Lifecycle trace: created -> risk checked -> filled/rejected -> PnL, written back to audit.

Current implementation target:

- Preserve existing `order_intent_service`, `risk_manager`, `/api/v1/execution`, `/api/v1/risk`, and paper-trading surfaces.
- Surface the configuration and execution linkage in config center and audit pages.
- Added a dedicated Phase 2 paper-trading workbench:
  - `GET /api/v1/trading/workbench` aggregates account/mode, OrderIntent audit events, RiskGuard status/config, paper orders, positions, PnL/equity curve, and execution-chain evidence.
  - `/paper-trading` displays the PRD desk: account/mode bar, OrderIntent list, RiskGuard check area, simulated order/fill records, positions, PnL/equity curve, and execution chain.
  - Navigation now points the simulated trading entry to `/paper-trading`; real exchange order submission remains disabled.
  - OrderIntent execution linkage now separates fill evidence from linkage evidence: the paper execution path writes the single `PAPER_ORDER_FILLED` event, and the wrapper writes `ORDER_INTENT_EXECUTION_LINKED`.
  - The workbench read model deduplicates historical duplicate fill evidence by `action + orderIntentId + orderId` while retaining immutable raw audit rows and exposing raw/deduped counts.
  - The workbench read model normalizes blocked RiskGuard events to `BLOCKED`, so a rejected lifecycle is not hidden behind the draft intent's `CREATED` status.
- Added PRD-complete RiskGuard execution contract:
  - Runtime config now includes `MIN_ORDER_NOTIONAL`, `WAIT_ORDER_INTENT_POLICY`, and `RISK_FAILURE_ACTION`.
  - `RiskManager.check_order` blocks orders below the minimum notional and records configured failure-action intent while keeping the effective execution action `block`.
  - `OrderIntentService` records WAIT/flat behavior as either `record_flat` or explicit `skip`, with audit details for generated/skipped intent evidence.
  - Backtest RiskGuard rows include minimum notional, WAIT policy, and failure-action evidence so backtests and simulated execution explain the same rules.
  - `/risk` exposes the new money and enum controls; `/api/v1/system/phase2-ops-monitor` reports the same values and `bypass_allowed = False`.

### 5. Audit Desk

Status: in progress

Required scope:

- Audit list ordered by time desc, filter by symbol/time/decision/execution.
- Detail page restores each Agent analysis and decision, not just logs.
- Detail includes decision identity, input snapshot ID fields, unified input snapshot, every Agent input summary/output report, expandable reasoning/decision chain, OrderIntent, RiskGuard, execution result, traceability/future-function check, JSON export, replay.
- Excel note resolution: decision identity is clearly `decision_id/context_hash/input_snapshot_id/audit_id/version/timestamps`; reasoning/decision chain is integrated with Agent input/output order to avoid duplication.
- Audit write interface is separated from business logic, append-only, not update/delete.

Current implementation target:

- Preserve append-only migration and `audit.py` detail/export logic.
- Ensure new data-platform and config operations report lineage and audit compatibility honestly.

### 6. Backtest Desk And Replay Desk

Status: in progress

Required scope:

- Backtests are async/background and do not block UI.
- Results stored in DuckDB contract; current implementation persists through existing DB structures and exposes agent-audited metrics.
- Backtest/optimization/batch market-data reads must use local persisted data only, with no hidden OpenBB/CCXT/Binance fallback.
- Config supports symbol, interval, start/end, capital, fee, slippage, strategy `ma|rsi|macd|boll|ichimoku|custom`, thresholds, risk config, `rule-only|agent-audited`, Agent mode, max parallel 5, queue operations.
- Queue supports details, cancel, retry, result jump, audit jump.
- Performance: total/annualized return, max drawdown, Sharpe, information ratio, win rate, profit factor, total trades, holding period, fees, slippage.
- Charts: equity, drawdown, benchmark, buy/sell, Agent decision points, RiskGuard intercept points.
- Trade detail jumps to research desk with matching `as_of_time`.
- Point-in-time check section is mandatory.
- Agent analysis section answers whether Agent improves risk/return.
- Supports multiple result comparison.
- Replay desk contains controls, historical market replay, current state snapshot, event timeline/detail, replay performance.

Current implementation target:

- Preserve existing `/backtest`, `/replay`, `/api/v1/strategy`, and `/api/v1/replay`.
- Make top-level `/api/v1/bars/as-of` and `/api/v1/snapshot` the shared PIT contract used by research and future backtest adapters.

### 7. Operations, Configuration Center, And Data Governance

Status: in progress

Required scope:

- Operations monitor: global health, service health, data freshness by data type, TradingAgents monitoring, background queues, LLM calls, audit health, execution/risk health, backtest/replay tasks, errors, resources/performance.
- Configuration center: data sources, instruments/markets, factors/signals, risk, simulated trading, backtest/replay, system/security, TradingAgents and custom agents.
- Data governance: data source configuration, data preview, cleaning/processing, cleaned changed items stored separately with versions, lineage, OpenBB reuse rather than duplicate logic.
- Traditional strategy desk remains as strategy-research/comparison entry and is marked as discussion-needed but compatible.
- Live trading desk is a skeleton only; no real-money order placement yet.

Current implementation target:

- Add `/config-center` and `/data-governance` frontend pages.
- Add `/api/v1/config-center/*` and `/api/v1/data-governance/*` backend routers.

## Current Implementation Slice

1. Persist this full-scope task board.
2. Add PRD-compatible top-level data-platform routes.
3. Add config-center backend routes and local custom-agent persistence.
4. Add data-governance backend routes for preview, lineage, cleaning-rule version metadata, and coverage.
5. Add `/config-center` and `/data-governance` pages and navigation entries.
6. Expand `backend/scripts/phase2_acceptance.py` so the local acceptance script checks the new full-scope markers.
7. Run focused tests and static validation.
8. Harden offline infrastructure behavior:
   - Redis cache/config/lock calls use bounded operation timeouts and short-circuit after failure.
   - ClickHouse keeps the existing unavailable retry window.
   - `/api/v1/bars/as-of` uses an AnalysisContext zero-limit fast path so PIT bar review does not touch factor/signal/news/macro stores.
   - AnalysisContext factor/signal SQL panels use bounded query timeouts and a short unavailable window.
   - `market_data_gateway.get_dataframe` has an explicit `allow_external_fallback` flag for research/backtest local-only paths.
   - NATS startup uses bounded reconnects; Binance WebSocket ingestion fallback is explicit opt-in via `ENABLE_INGESTION_BINANCE_FALLBACK`.
9. Add cross-workbench linkage and replay-package contract:
   - `/api/v1/linkage/context` returns PIT-safe links between research, backtest, replay, audit, decision, analytics, and data snapshot APIs.
   - `/api/v1/linkage/replay-package` returns one immutable/PIT replay package for a decision/audit/context: identity, strict snapshot replay availability, Agent input record IDs, data versions, visible-data checks, role outputs, OrderIntent, RiskGuard, execution result, audit chain, and local-only replay plan.
   - Research dashboard accepts `symbol`, `interval`, and `as_of_time` URL parameters and switches its K-line chart to `/api/v1/bars/as-of` when reviewing a historical point.
   - Backtest, replay, and audit pages show the shared workbench linkage bar.
   - Replay store/session typing now carries `backtest_id` and narrows JSON params before syncing them into page state.
10. Add concrete financial-data storage contract:
   - Alembic revision `017` declares required PostgreSQL/Timescale tables, PIT fields (`event_time`, `ingest_time`, `available_time`), upsert keys, `(symbol, ts)` indexes, data-quality fields, lineage tables, versioned cleaned-data store, and guarded Timescale hypertable/compression policies.
   - `GET /api/v1/meta/storage-contract` returns a structured contract for tables, ETL behavior, Prefect 3 scheduler target, local compatibility stores, lifecycle policies, and `local_storage_only` Agent visibility.
   - Acceptance script now checks both the migration and the storage-contract API markers.
11. Wire local PIT reads for storage-contract tables:
   - `backend/app/services/data_platform_storage.py` builds whitelisted local SQL for `fundamental_report`, `corporate_action`, and `adjustment_factor`.
   - `/api/v1/fundamentals/{symbol}`, `/api/v1/fundamentals/{symbol}/latest`, `/api/v1/corporate-actions/{symbol}`, and `/api/v1/adjust-factors/{symbol}` now read local PostgreSQL with `available_time <= as_of_time`.
   - No live provider fallback is used on these read paths; unavailable/unmigrated storage is surfaced as structured API errors.
12. Add provider-normalized local ingestion:
   - `backend/app/services/data_platform_ingestion.py` validates records, fills UTC PIT timestamps, stable `record_id`, raw payload hash, provider/source version, and lineage metadata.
   - `POST /api/v1/meta/ingest` supports dry-run validation and local transactional upsert for `fundamental_report`, `corporate_action`, and `adjustment_factor`.
   - Successful writes also insert lineage rows and ETL job log rows with batch ID, idempotency key, row counts, status, symbols, and parameters.
13. Surface storage/ingestion in data governance:
   - Data governance overview returns `storage_contract` and contract links for `/api/v1/meta/storage-contract` plus `/api/v1/meta/ingest`.
   - Data preview supports `fundamentals`, `corporate_actions`, and `adjustment_factors` in addition to bars/quotes/news/macro.
   - `/data-governance` page shows storage contract tables, PIT fields, indexes, lifecycle policies, manual ingest endpoint, and scheduler jobs.
14. Harden TradingAgents and custom Agent configuration editing:
   - Role configs normalize default fields and return `effective_llm` inheritance evidence.
   - `PATCH /api/v1/config-center/tradingagents/roles/{role_id}` saves role enablement, prompt version, prompt, skill, and per-role LLM overrides without mutating environment variables.
   - `/config-center` supports role editing and custom Agent create/edit/delete while preserving independent LLM or default-LLM fallback behavior.
15. Add the dedicated simulated-trading workbench:
   - `backend/app/services/paper_trading_workbench.py` builds `paper_trading_workbench.v1`.
   - `GET /api/v1/trading/workbench` exposes a read model over OrderIntent, RiskGuard, PaperOrder, positions, PnL, equity curve, and immutable audit evidence.
   - `/paper-trading` implements the PRD simulated trading desk and is wired into navigation.
16. Complete the RiskGuard PRD rule contract:
   - `MIN_ORDER_NOTIONAL`, `WAIT_ORDER_INTENT_POLICY`, and `RISK_FAILURE_ACTION` are defaulted, validated, editable, previewed, audited, and exposed in ops monitoring.
   - Execution remains non-bypassable: any failed RiskGuard check returns `BLOCKED`; `reduce`/`warn` are saved as review intent only.
   - Agent-draft WAIT/flat decisions can be recorded as flat intent or explicitly skipped, but both paths write immutable audit evidence.
17. Add repeatable live acceptance gate:
   - `backend/scripts/phase2_live_acceptance.py` checks running API routes for PIT bars/snapshot, storage contract, ops monitor, paper-trading workbench, RiskGuard PRD config, and OpenBB dry-run refresh.
   - DB checks verify Alembic head `017`, data-platform tables, PIT columns, bar indexes, Timescale/storage policies, and audit append-only trigger metadata.
   - `--run-migrations` runs `alembic upgrade head`; `--mutating-audit-check` inserts an immutable proof row and verifies UPDATE/DELETE are rejected.

## Verification Plan

- `python -m pytest backend/tests/unit/test_database_redis_fast_degrade.py backend/tests/unit/test_clickhouse_fast_degrade.py backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_config_center_contract.py backend/tests/unit/test_system_tradingagents_config.py backend/tests/unit/test_risk_config_api.py backend/tests/unit/test_analysis_context_builder_pit.py -q`
- `python backend/scripts/phase2_acceptance.py`
- `cd frontend; npx eslint app/config-center/page.tsx app/data-governance/page.tsx components/navigation/AppTopNav.tsx components/navigation/Breadcrumb.tsx`
- If frontend validation is stable, run `npx tsc --noEmit --pretty false --incremental false`.

## Known Residual Risks To Retest Later

- Prefect 3 is not currently installed in `backend/requirements.txt`; current scheduler compatibility is represented by the pipeline orchestrator and API contract.
- TimescaleDB hypertables/compression/retention/PITR are now declared in migration `017` with guarded DDL; live migration passed on local `pgvector/pg16` after widening the Timescale extension guard, and full backup restore still needs operational PITR execution on a Timescale-enabled stack.
- Fundamentals, corporate actions, and adjustment factors now have concrete storage tables, local PIT query adapters, provider-normalized upsert helpers, and OpenBB refresh adapter; live DB migration and OpenBB dry-run API checks passed against local services, while production provider credentials/rate limits still need operational validation.
- Full TradingAgentsGraph acceptance depends on runtime service availability, native graph import readiness, and LLM credentials.
- `/api/v1/linkage/replay-package` has unit coverage for pure package assembly and static acceptance checks; run a live DB-backed smoke once PostgreSQL/audit rows are available to verify SQL JSONB paths and realistic chain sizes.
- NATS was not running during the latest backend live gate; backend degraded gracefully, but full messaging workflows still need a NATS-enabled smoke.
- DuckDB backtest archive now has static/unit coverage plus a real live local-data backtest proof (`backtest_id=9`) showing PostgreSQL detail, audit link, DuckDB archive write/read, and cross-backend visibility from `127.0.0.1:8004` to frontend-rewrite backend `127.0.0.1:8002`.
- Frontend live-browser smoke against the API+DB backend passed for `/paper-trading`, `/monitor`, `/data-governance`, `/config-center`, and `/risk`; broader route coverage remains a follow-up.

## Latest Local Verification

2026-06-10:

- `python -m py_compile backend/app/core/config.py backend/app/services/ingestion_service.py backend/app/services/trading_worker.py backend/app/services/database.py backend/app/services/analysis_context_builder.py backend/app/services/market_data_gateway.py backend/main.py backend/scripts/phase2_acceptance.py` passed.
- `python -m pytest backend/tests/unit/test_database_redis_fast_degrade.py backend/tests/unit/test_clickhouse_fast_degrade.py backend/tests/unit/test_ingestion_fallback_policy.py backend/tests/unit/test_analysis_context_builder_pit.py backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_config_center_contract.py backend/tests/unit/test_risk_config_api.py -q` passed: 23 tests.
- `python backend/scripts/phase2_acceptance.py` passed: 27/27 static checks.
- `python backend/scripts/phase2_acceptance.py --api-base http://127.0.0.1:8004 --timeout 8` passed: 34/34 static + live checks.
- Current offline smoke on a clean temporary backend (`127.0.0.1:8004`) returned:
  - `/api/v1/snapshot?symbol=BTCUSDT&interval=1h&bar_limit=5`: 1.85s.
  - `/api/v1/bars/as-of?symbol=BTCUSDT&interval=1h&limit=5`: 0.91s.
  - `/api/v1/risk/config-metadata`: 0.53s.
  - `/api/v1/config-center/overview`: 1.45s.
  - `/api/v1/data-governance/overview`: 1.42s.
- `npx eslint app/config-center/page.tsx app/data-governance/page.tsx components/navigation/AppTopNav.tsx components/navigation/Breadcrumb.tsx` passed.
- `npx tsc --noEmit --pretty false --incremental false` passed.
- Temporary backend on port 8004 was stopped after verification.

2026-06-10 later slice:

- Added shared workbench linkage API and replay package API:
  - `GET /api/v1/linkage/context`
  - `GET /api/v1/linkage/replay-package`
- Added shared frontend linkage bar and wired it into research dashboard, backtest, replay, and audit.
- Shared linkage bar exposes a `重放包` JSON entry that opens `/api/v1/linkage/replay-package` for the current context.
- Research dashboard URL PIT review now uses `/api/v1/bars/as-of` through `TradingViewChart.asOfTime`.
- Replay package contract captures `strict_snapshot_replay`, `pit_rebuild_from_local_storage`, `local_storage_only`, `available_time <= as_of_time`, Agent input record IDs, data versions, role outputs, OrderIntent, RiskGuard, execution result, immutable audit chain, and replay plan.
- Frontend type/lint cleanup for touched files:
  - Dashboard URL params use derived defaults instead of synchronous effect state writes.
  - Audit linkage no longer references a non-existent `filters.auditId`.
  - Replay store carries `backtest_id` and uses `Record<string, unknown> | null` for session params.
  - Replay page narrows restored JSON params before syncing dynamic-selection state.
- Verification:
  - `python -m py_compile backend/app/api/v1/endpoints/linkage.py backend/app/api/v1/router.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_linkage_contract.py backend/tests/unit/test_database_redis_fast_degrade.py backend/tests/unit/test_analysis_context_builder_pit.py -q` passed: 10 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 31/31 static checks.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` passed.
  - `cd frontend; npx eslint app/dashboard/page.tsx components/linkage/WorkbenchLinkBar.tsx components/charts/TradingViewChart.tsx lib/replay-store.tsx` passed.
  - After adding the `重放包` link, focused frontend lint/typecheck and `backend/scripts/phase2_acceptance.py` still passed.

2026-06-10 data-platform storage contract slice:

- Added `backend/migrations/versions/017_data_platform_contract_tables.py`.
- Added `build_storage_contract()` and `GET /api/v1/meta/storage-contract`.
- Updated `/meta/coverage` to point to the structured storage contract.
- Added static/unit coverage for required tables, PIT fields, Timescale declarations, governance/lineage tables, and storage contract metadata.
- Verification:
  - `python -m py_compile backend/app/api/v1/endpoints/data_platform.py backend/migrations/versions/017_data_platform_contract_tables.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_data_platform_helpers.py -q` passed: 5 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 33/33 static checks.

2026-06-10 data-platform local PIT table-query slice:

- Added `backend/app/services/data_platform_storage.py`.
- Updated fundamentals, corporate-actions, and adjust-factors endpoints to query local PostgreSQL contract tables with `available_time <= as_of_time`.
- Added tests for whitelist SQL generation, UTC `as_of_time`, adjustment-factor ordering, and Decimal/date/JSON serialization.
- Verification:
  - `python -m py_compile backend/app/services/data_platform_storage.py backend/app/api/v1/endpoints/data_platform.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_storage.py -q` passed: 9 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 35/35 static checks.

2026-06-10 data-platform ingestion/upsert slice:

- Added `backend/app/services/data_platform_ingestion.py`.
- Added `POST /api/v1/meta/ingest` for manual dry-run or local upsert of provider-normalized records.
- Ingestion validates PIT (`available_time >= event_time`), normalizes symbols, preserves provider/source version, generates stable IDs/hashes, writes lineage, and records ETL job logs.
- Verification:
  - `python -m py_compile backend/app/services/data_platform_ingestion.py backend/app/services/data_platform_storage.py backend/app/api/v1/endpoints/data_platform.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_storage.py backend/tests/unit/test_data_platform_ingestion.py -q` passed: 15 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 37/37 static checks.

2026-06-10 data-governance storage visibility slice:

- Updated data governance overview/quality/lineage/preview endpoints to include storage contract and manual ingest metadata.
- Added preview routing for `fundamentals`, `corporate_actions`, and `adjustment_factors`.
- Updated `/data-governance` frontend with storage contract cards, lifecycle policy cards, manual ingest contract, and expanded preview tabs.
- Verification:
  - `python -m py_compile backend/app/api/v1/endpoints/data_governance.py backend/app/api/v1/endpoints/data_platform.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_data_governance_contract.py backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_storage.py backend/tests/unit/test_data_platform_ingestion.py -q` passed: 17 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 37/37 static checks.
  - `cd frontend; npx eslint app/data-governance/page.tsx` passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` passed.

2026-06-10 backtest DuckDB archive and queue-control slice:

- Added `backend/app/services/backtest_duckdb_store.py`.
- Single backtest runs now attempt a non-blocking DuckDB archive after PostgreSQL persistence; archive metadata is returned in `dataRange.duckdbArchive` and stored in metrics.
- DuckDB archive schema stores PRD metrics, PIT check evidence, equity curve, trades, params, execution mode, and Agent stats JSON in `data/backtest/backtest_results.duckdb`.
- Parameter-batch tasks now expose PostgreSQL + DuckDB archive storage metadata, write task events to DuckDB, support cancellation requests, and can retry completed/failed/cancelled tasks from the original request and parameter combinations.
- `/api/v1/strategy/backtest/duckdb-archive` lists the latest DuckDB archive rows for comparison/replay use.
- `/backtest` task card displays DuckDB archive path/schema and provides cancel/retry controls.
- Verification:
  - `python -m py_compile backend/app/services/backtest_duckdb_store.py backend/app/api/v1/endpoints/strategy.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_backtest_duckdb_store.py backend/tests/unit/test_backtest_p3_helpers.py -q` passed: 12 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 40/40 static checks.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` passed.
  - `cd frontend; npx eslint app/backtest/page.tsx` still fails on pre-existing broad lint debt in that file (`no-explicit-any`, hook purity, unused imports, conditional hook); this slice removed new `any` catches and did not attempt the full legacy cleanup.

2026-06-10 Phase2 operations monitor slice:

- Added `backend/app/services/phase2_ops_monitor.py`.
- Added `GET /api/v1/system/phase2-ops-monitor` for the PRD operations monitor:
  - data freshness across storage-contract tables (`bar_1m`, `bar_1h`, `bar_1d`, `quote_latest`, fundamentals, corporate actions, adjustment factors, news, macro, ETL jobs);
  - TradingAgents service/config/data-boundary status;
  - LLM provider/model/service call-monitoring contract;
  - immutable audit health (`append_only`, hash coverage, export API);
  - execution/RiskGuard health and simulated trading chain;
  - in-process backtest task queue status;
  - DuckDB backtest archive status/path/schema;
  - process resource snapshot.
- Updated `/monitor` to show the Phase2 operations control panel with PIT/local-only boundary, freshness table, audit health, RiskGuard execution chain, queue controls, and DuckDB archive visibility.
- Updated `backend/scripts/phase2_acceptance.py` with ops-monitor service/API/frontend checks.
- Verification:
  - `python -m py_compile backend/app/services/phase2_ops_monitor.py backend/app/api/v1/endpoints/system_health.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_phase2_ops_monitor.py backend/tests/unit/test_system_tradingagents_config.py -q` passed: 6 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 43/43 static checks.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` passed.
  - `cd frontend; npx eslint app/monitor/page.tsx` passed.

2026-06-10 OpenBB financial adapter local-ingestion slice:

- Added `backend/app/services/openbb_financial_adapter.py`.
- Added explicit provider refresh API `POST /api/v1/meta/refresh-financials`.
- Adapter normalizes OpenBB financial data into local storage-contract records:
  - `fundamental_report` from income/balance/cash statement endpoints.
  - `corporate_action` from dividends and historical splits.
  - `adjustment_factor` independently from split rows with cumulative factors.
- Refresh API defaults to `dry_run=true`; actual writes still go through `data_platform_ingestion.ingest_records`, preserving record IDs, PIT fields, raw payload hash, `etl_job_log`, and `data_lineage`.
- Agent/backtest/read paths remain `local_storage_only` via `/fundamentals`, `/corporate-actions`, `/adjust-factors`; provider refresh is explicit and not a hidden fallback.
- `/data-governance` now displays `/api/v1/meta/refresh-financials` next to `/api/v1/meta/ingest`.
- Verification:
  - `python -m py_compile backend/app/services/openbb_financial_adapter.py backend/app/api/v1/endpoints/data_platform.py backend/app/api/v1/endpoints/data_governance.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_openbb_financial_adapter.py backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_data_platform_ingestion.py -q` passed: 14 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 44/44 static checks.
  - `cd frontend; npx eslint app/data-governance/page.tsx` passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` passed.

2026-06-10 config-center editability and simulated-trading workbench slices:

- Added editable TradingAgents role configuration:
  - `RoleConfigPayload`, `_normalize_role_configs`, `_normalize_tradingagents_config`, and `PATCH /api/v1/config-center/tradingagents/roles/{role_id}`.
  - `/config-center` can edit role prompts/skills/LLM settings and create/edit/delete custom Agents.
- Added dedicated paper-trading workbench:
  - `backend/app/services/paper_trading_workbench.py`
  - `GET /api/v1/trading/workbench`
  - `/paper-trading` frontend page and navigation/breadcrumb entries.
- Verification:
  - `python -m py_compile backend/app/api/v1/endpoints/config_center.py backend/app/services/paper_trading_workbench.py backend/app/api/v1/endpoints/trading.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_config_center_contract.py backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_order_intent_service.py -q` passed: 16 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 47/47 static checks.
  - `cd frontend; npx eslint app/config-center/page.tsx app/paper-trading/page.tsx components/navigation/AppTopNav.tsx components/navigation/Breadcrumb.tsx` passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` passed.

2026-06-10 RiskGuard PRD execution-contract slice:

- Added runtime and configuration coverage for:
  - `MIN_ORDER_NOTIONAL`;
  - `WAIT_ORDER_INTENT_POLICY = record_flat|skip`;
  - `RISK_FAILURE_ACTION = block|reduce|warn`.
- RiskGuard execution still enforces non-bypassable blocking:
  - `RiskCheckResult.action` records the configured action intent;
  - `effective_failure_action` remains `block` in OrderIntent risk previews.
- Added matching evidence in:
  - `backend/app/core/config.py`;
  - `backend/app/services/risk_manager.py`;
  - `backend/app/api/v1/endpoints/risk.py`;
  - `backend/app/services/order_intent_service.py`;
  - `backend/app/api/v1/endpoints/strategy.py`;
  - `backend/app/services/phase2_ops_monitor.py`;
  - `frontend/app/risk/page.tsx`.
- Verification:
  - `python -m py_compile backend/app/core/config.py backend/app/services/risk_manager.py backend/app/api/v1/endpoints/risk.py backend/app/services/order_intent_service.py backend/app/api/v1/endpoints/strategy.py backend/app/services/phase2_ops_monitor.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_risk_config_api.py backend/tests/unit/test_risk_manager_contract.py backend/tests/unit/test_order_intent_service.py backend/tests/unit/test_backtest_p3_helpers.py -q` passed: 35 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 48/48 static checks.
  - `cd frontend; npx eslint app/risk/page.tsx` passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` passed.

2026-06-10 Phase2 live acceptance gate slice:

- Added `backend/scripts/phase2_live_acceptance.py`:
  - API checks: `/api/v1/bars/as-of`, `/api/v1/snapshot`, `/api/v1/meta/storage-contract`, `/api/v1/system/phase2-ops-monitor`, `/api/v1/trading/workbench`, `/api/v1/risk/config-metadata`, and `POST /api/v1/meta/refresh-financials` dry-run.
  - DB checks: Alembic head `017`, required data-platform tables, PIT columns, bar indexes, Timescale/storage policies, audit append-only metadata.
  - Optional mutation proof: `--mutating-audit-check` inserts an immutable audit proof row and verifies UPDATE/DELETE rejection.
  - Optional migration gate: `--run-migrations` runs `alembic upgrade head` before DB checks.
- Added `backend/tests/unit/test_phase2_live_acceptance.py`.
- Verification:
  - `python -m py_compile backend/scripts/phase2_live_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_phase2_live_acceptance.py -q` passed: 5 tests.
  - `python backend/scripts/phase2_live_acceptance.py --api-base= --database-url= --json` passed with empty result set.
  - `python backend/scripts/phase2_acceptance.py` passed: 49/49 static checks.

2026-06-10 live API/DB acceptance hardening slice:

- Started local Postgres/Redis/ClickHouse through Docker Compose and a local backend on `127.0.0.1:8004`.
- Fixed migration `017_data_platform_contract_tables.py` so the Timescale extension guard also handles `feature_not_supported`; plain `pgvector/pg16` now creates the contract tables and storage-policy metadata instead of failing.
- Verified Alembic reached head `017` on local Postgres at `localhost:5435`.
- Verified audit append-only enforcement with `--mutating-audit-check`; the live gate inserted immutable proof rows and confirmed UPDATE/DELETE rejection through the audit trigger.
- Hardened the live gate's paper-trading workbench predicate to accept the actual `execution_chain.chain` API shape.
- Exposed the new RiskGuard PRD rules (`MIN_ORDER_NOTIONAL`, `WAIT_ORDER_INTENT_POLICY`, `RISK_FAILURE_ACTION`) through `RiskManager.get_risk_status()` so operations/workbench/live gates report the same executable contract.
- Verification:
  - `python -m alembic upgrade head` with `DATABASE_URL=postgresql+asyncpg://quantagent:quantagent@localhost:5435/quantagent` passed; Alembic head is `017`.
  - `python scripts/phase2_live_acceptance.py --api-base= --database-url=$DATABASE_URL --mutating-audit-check --json` passed: 7/7 DB checks.
  - `python scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url=$DATABASE_URL --mutating-audit-check --json` passed: 14/14 API+DB checks.
  - `python scripts/phase2_acceptance.py --api-base http://127.0.0.1:8004 --timeout 12` passed: 57/57 static+live checks.
  - `python -m pytest backend/tests/unit/test_risk_manager_contract.py backend/tests/unit/test_phase2_live_acceptance.py -q` passed: 8 tests.
  - `python -m py_compile backend/app/services/risk_manager.py backend/scripts/phase2_live_acceptance.py` passed.

2026-06-10 frontend live-backend smoke slice:

- Reused the existing Next dev server on `http://127.0.0.1:3002`.
- Started a matching local backend on `127.0.0.1:8002` with the same local Postgres/Redis/ClickHouse settings because `frontend/next.config.ts` rewrites `/api/v1/*` to `http://localhost:8002` unless `NEXT_PUBLIC_API_URL` is set before the Next dev lock is acquired.
- Verified the Next rewrite path through `http://127.0.0.1:3002/api/v1/meta/storage-contract`.
- Browser smoke passed for:
  - `/paper-trading`: rendered OrderIntent, RiskGuard, PnL/equity, and execution-chain panels against live API data.
  - `/monitor`: rendered TradingAgents and Phase2 operations sections; after live endpoints returned, `10.6 功能项` reached `5/5`.
  - `/data-governance`: rendered preview tabs plus storage/ingestion contract text.
  - `/config-center`: rendered TradingAgents role/custom-Agent configuration sections.
  - `/risk`: rendered RiskGuard status, minimum order notional, WAIT policy, and failure-action controls.
- Fixed data-governance wording to use `存储契约` and `手动入库与生命周期` consistently with the requirement/acceptance language.
- Verification:
  - `python backend/scripts/phase2_acceptance.py` passed: 49/49 static checks.
  - `python -m pytest backend/tests/unit/test_data_platform_helpers.py backend/tests/unit/test_phase2_live_acceptance.py backend/tests/unit/test_risk_manager_contract.py -q` passed: 14 tests.
  - `python backend/scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url $DATABASE_URL --mutating-audit-check --json` passed: 14/14 API+DB checks.
  - `python backend/scripts/phase2_acceptance.py --api-base http://127.0.0.1:8004 --timeout 12` passed: 57/57 static+live checks.
  - `cd frontend; npx eslint app/data-governance/page.tsx` passed.
  - `cd frontend; npx tsc --noEmit --pretty false --incremental false` passed.
  - `python -m py_compile backend/scripts/phase2_acceptance.py` passed after updating the data-governance frontend marker from `存储合同` to `存储契约`/`手动入库`.
  - `python backend/scripts/phase2_acceptance.py` passed: 49/49 static checks.

2026-06-10 paper execution audit-link hardening slice:

- Fixed the OrderIntent -> RiskGuard -> paper execution -> audit chain so new successful paper executions produce exactly one fill audit event:
  - `backend/app/services/order_intent_service.py` no longer duplicates `PAPER_ORDER_FILLED` after `PaperTradingService.execute_order_intent()`.
  - The wrapper writes a distinct `ORDER_INTENT_EXECUTION_LINKED` event to preserve the OrderIntent-to-paper-order relationship without inflating fills.
  - `backend/app/services/audit_service.py` and `backend/app/services/paper_trading_workbench.py` recognize `ORDER_INTENT_EXECUTION_LINKED`.
- Hardened the paper-trading workbench read model:
  - Historical immutable duplicate fill rows are not mutated or deleted.
  - Read-side fill summaries dedupe by `action + orderIntentId + orderId`.
  - The workbench response exposes `raw_total`, `deduped_total`, and `dedupe_rule`, and execution-chain details include raw audit events, deduped audit events, and execution-link status.
- Live proof chain:
  - BUY `BTCUSDT`, quantity `0.0001`, price `100000` produced paper order `PT-13`; it retains earlier duplicate immutable fill rows from the pre-fix path.
  - SELL `BTCUSDT`, quantity `0.0001`, price `100000` produced paper order `PT-14` after the fix and closed the position.
  - Database/workbench inspection confirmed `PT-14` has one `PAPER_ORDER_FILLED`, one `ORDER_INTENT_EXECUTION_LINKED`, and no duplicate new fill evidence.
- Verification:
  - `python -m py_compile backend/app/services/audit_service.py backend/app/services/order_intent_service.py backend/app/services/paper_trading_workbench.py` passed.
  - `python -m pytest backend/tests/unit/test_order_intent_service.py backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_audit_service.py -q` passed: 20 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 49/49 static checks.
  - After backend restart, `python -m pytest backend/tests/unit/test_order_intent_service.py backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_audit_service.py backend/tests/unit/test_phase2_live_acceptance.py -q` passed: 25 tests.
  - `python backend/scripts/phase2_live_acceptance.py --api-base http://127.0.0.1:8004 --database-url $DATABASE_URL --mutating-audit-check --json` passed: 14/14 API+DB checks.

2026-06-10 live backtest DuckDB/local-only hardening slice:

- Closed a PIT/local-only gap in backtest-family data reads:
  - `run_backtest`, `optimize_strategy`, and `batch_backtest` now call `market_data_gateway.get_dataframe()` with `allow_external_fallback=False`, `allow_ccxt_fallback=False`, and `allow_binance_fallback=False`.
  - Backtest live responses now identify the source as `market_data_gateway:local_storage` when served from persisted local bars.
  - Error text now says local market data is missing rather than implying external fallback.
- Fixed live backtest detail:
  - `backend/app/api/v1/endpoints/strategy.py` imports `AuditLog`, so `GET /api/v1/strategy/backtest/history/{id}` can return audit-linked details instead of `AuditLog` name errors.
- Hardened DuckDB archive for multiple local backend processes:
  - `backend/app/services/backtest_duckdb_store.py` uses short-lived DuckDB connections and commits/closes per operation.
  - This prevents a stale per-process connection from hiding rows written by another backend, which matters because Next dev rewrites hit `127.0.0.1:8002` while live gates use `127.0.0.1:8004`.
- Added regression coverage:
  - `backend/tests/unit/test_backtest_p3_helpers.py` locks local-only gateway kwargs and the `AuditLog` import.
  - `backend/tests/unit/test_backtest_duckdb_store.py` locks cross-store DuckDB read-after-write visibility.
  - `backend/scripts/phase2_acceptance.py` now includes `backtest_local_only_data_boundary` and DuckDB short-connection markers; static acceptance is now 50/50.
- Live proof:
  - `POST /api/v1/strategy/backtest/run` on `127.0.0.1:8004` with `BTCUSDT`, `1h`, `limit=400`, `as_of_time=2026-06-09T21:00:00Z`, `ma`, `rule_only` produced `backtest_id=9`.
  - Result evidence: `data_source=market_data_gateway:local_storage`, `pit_passed=true`, `bars=400`, `trades=12`, `duckdb_status=archived`, `audit_count=1`.
  - `GET /api/v1/strategy/backtest/duckdb-archive?limit=5` returned IDs `[9, 8, 7]` from both `127.0.0.1:8004` and `127.0.0.1:8002`.
  - `GET /api/v1/strategy/backtest/history/9` returned `schema_version=backtest_detail.v1`, local data source, `bars=400`, and `auditCount=1`.
- Verification:
  - `python -m py_compile backend/app/services/backtest_duckdb_store.py backend/app/api/v1/endpoints/strategy.py backend/scripts/phase2_acceptance.py` passed.
  - `python -m pytest backend/tests/unit/test_backtest_duckdb_store.py backend/tests/unit/test_backtest_p3_helpers.py -q` passed: 16 tests.
  - `python backend/scripts/phase2_acceptance.py` passed: 50/50 static checks.

2026-06-10 live RiskGuard BLOCKED simulation proof slice:

- Ran a fresh low-notional manual paper order through the real API:
  - Request: `POST /api/v1/trading/orders`, `BTCUSDT`, BUY, quantity `0.00001`, price `100000`, exchange `okx`.
  - Expected notional was `1.00` USDT, below current `MIN_ORDER_NOTIONAL=5.0`.
  - API returned HTTP 400 with the RiskGuard reason, without creating a paper order.
- Audit/database evidence for `OI-MANUAL-1781040381074`:
  - `ORDER_INTENT_CREATED`: 1.
  - `RISK_BLOCKED`: 1.
  - `PAPER_ORDER_FILLED`: 0.
  - `PAPER_ORDER_REJECTED`: 0.
  - `ORDER_INTENT_EXECUTION_LINKED`: 0.
  - `paper_trades`: 0.
- Workbench evidence:
  - `GET /api/v1/trading/workbench?symbol=BTCUSDT&limit=12` on both `127.0.0.1:8004` and frontend-rewrite backend `127.0.0.1:8002` shows latest item `RISK_BLOCKED`, stage `blocked`, status `BLOCKED`, `risk.rule=MIN_ORDER_NOTIONAL`, `risk.passed=false`, `orderId=null`, and positions still `0`.
- Read-model hardening:
  - `backend/app/services/paper_trading_workbench.py` now prefers lifecycle event status over the stale draft intent status through `_status_for_event()`.
  - This prevents blocked events from showing `CREATED` in the simulated-trading desk.
- Verification:
  - `python -m py_compile backend/app/services/paper_trading_workbench.py backend/tests/unit/test_paper_trading_workbench.py` passed.
  - `python -m pytest backend/tests/unit/test_paper_trading_workbench.py backend/tests/unit/test_order_intent_service.py -q` passed: 15 tests.
