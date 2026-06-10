# Phase 2 Gap Analysis

Last updated: 2026-06-10

This analysis compares the target repository with the two read-only references and identifies where P0 should reuse, harden, or add compatibility layers.

## Repository Boundaries

Target repository for changes:

- `QuantAgent-main`

Read-only references:

- `C:\Users\yhy05\Desktop\量化\回测结合版`
- `C:\Users\yhy05\Desktop\量化\数据底座\QuantAgent-yhy\quantagent\QuantAgent-main`

## Existing Target Capabilities

### Audit

Target files to inspect/use:

- `backend/app/models/db_models.py`
- `backend/app/services/audit_service.py`
- `backend/migrations/versions/015_harden_audit_logs.py`
- `backend/app/api/v1/endpoints/audit.py`
- `frontend/app/audit/page.tsx`

Observed capability:

- `AuditLog` already contains standard Phase 2 fields including hash, immutable, decision, order, backtest, and replay linkage fields.
- `audit_service.py` standardizes payload details and computes stable payload/chain hashes.
- Migration `015_harden_audit_logs.py` adds append-only columns/indexes and a PostgreSQL trigger that rejects update/delete.
- Audit API already exposes overview, list/detail, export, decision detail, and decision replay endpoints.

Current gap/risk:

- Need focused tests proving append-only enforcement, hash verification, export completeness, and link coverage.
- Need acceptance script coverage so this is verifiable outside manual inspection.

### AnalysisContext and Agent Decision

Target files to inspect/use:

- `backend/app/services/analysis_context_builder.py`
- `backend/app/models/analysis_context.py`
- `backend/app/agents/coordinator_agent.py`
- `backend/app/agents/tradingagents_adapter.py`
- `tradingagents-service/main.py`
- `frontend/app/decisions/page.tsx`

Observed capability:

- AnalysisContext already carries `input_snapshot_ids`, `data_versions`, PIT visibility checks, and `context_hash`.
- Builder applies `available_time <= as_of_time` constraints for local factor/signal/news/macro queries and aligns market bars to the cutoff.
- Coordinator persists decision result and writes `AGENT_DECISION` audit with `raise_on_failure=True`.
- TradingAgents adapter keeps compact context metadata and distinguishes fast/full graph behavior.

Current gap/risk:

- Need verify the market-data path does not use direct external live fallback for Agent PIT contexts.
- Need tests for stable context hashes, local/PIT evidence, and fast/full mode differentiation.
- Need ensure role outputs and model/runtime metadata are present in persisted/exported audit evidence.

### OrderIntent, RiskGuard, Paper Execution

Target files to inspect/use:

- `backend/app/services/order_intent_service.py`
- `backend/app/services/risk_manager.py`
- `backend/app/api/v1/endpoints/execution.py`
- `frontend/app/decisions/page.tsx`
- `frontend/app/audit/page.tsx`

Observed capability:

- `order_intent_service.py` can draft/preview/execute decisions and manual orders.
- OrderIntent fields include direction, position percent, validity, confidence, source decision ID, and reason-like context.
- RiskManager has rule checks for forbidden symbols, kill switch, single position, total exposure, daily loss, max drawdown, leverage, and order notional.
- Audit events exist for OrderIntent creation, hold recording, risk pass/block, paper fill, and paper rejection.
- Execution API exposes preview, execute, and latest OrderIntent endpoints.

Current gap/risk:

- Need deterministic tests for pass/block audit linkage. Tail-risk random behavior should be avoided or controlled in tests.
- Need verify PnL/fill evidence is enough for acceptance and JSON export.
- Need verify frontend exposes the chain clearly enough.

### Backtest and Replay

Target files to inspect/use:

- `backend/app/api/v1/endpoints/replay.py`
- `backend/app/api/v1/endpoints/analytics.py`
- `backend/app/services/backtester/event_driven.py`
- `backend/app/services/backtester/vectorized.py`
- `backend/app/services/backtester/reproducibility.py`
- `frontend/app/backtest/page.tsx`
- `frontend/app/replay/page.tsx`

Observed capability:

- Target has backtest and replay surfaces but exact P0 compliance still needs detailed inspection.
- Existing tests include P3 helper tests, but Phase 2 P0 requires stronger PIT/audit/evidence acceptance.

Current gap/risk:

- Need confirm backtest parameters, PIT checks, Agent invocation tracking, risk blocks, metrics, and audit links.
- Need add or update tests for no-future-data evidence and reproducibility.
- Need ensure replay reconstructs from immutable audit/context evidence without mutating originals.

### Data Platform Dependency

Target files to inspect/use:

- `backend/app/services/market_data_gateway.py`
- `backend/app/api/v1/endpoints/market.py`
- `backend/app/services/analysis_context_builder.py`

Observed capability:

- Market data gateway uses local ClickHouse first.
- Research snapshot endpoint wraps AnalysisContext and provides PIT-aligned context.
- Data model supports `available_time` semantics in local queries.

Current gap/risk:

- Data platform reference documents mention `/api/v1/bars/as-of` and `/api/v1/snapshot`; target may instead expose `market/research-snapshot/{symbol}`.
- Need either add compatibility endpoints or document/verify equivalent behavior used by Phase 2 acceptance.
- Need ensure Agent paths do not silently fall back to external live data.

## Reference-Only Reusable Ideas

### 回测结合版

Relevant reusable files/ideas:

- `frontend/app/backtest-v2/page.tsx`
- `frontend/components/backtest/StrategyAnalysisPanel.tsx`
- `frontend/components/backtest/ReflectionReport.tsx`
- `frontend/components/backtest/ParticipantAllocationTable.tsx`
- `frontend/components/backtest/LiveBacktestChart.tsx`
- `frontend/components/backtest/DataPanelSelector.tsx`
- `frontend/components/backtest/BacktestModeSelector.tsx`
- `backend/schemas/backtest_v2.py`
- `backend/app/services/backtester/streaming_agent_runner.py`
- `backend/app/services/backtester/multi_mode_runner.py`
- `backend/app/services/backtester/agent_signal_provider.py`

Reuse approach:

- Use as design/reference only unless a narrow component or schema can be migrated safely.
- Prefer target's existing backtester and frontend pages first.
- Avoid broad UI rewrite before P0 acceptance.

Risk:

- Reference implementation may rely on routes, schemas, or service assumptions missing from target.
- Migrating large chunks could create regressions outside owned scope.

### 数据底座版

Relevant reusable files/ideas:

- `docs/financial_data_platform_gap_and_plan.md`
- `docs/data_platform_acceptance_report.md`
- `backend/scripts/data_platform_acceptance.py`
- Data platform API concepts: `GET /api/v1/bars/as-of`, `GET /api/v1/snapshot`

Reuse approach:

- Use scripts/docs as a model for Phase 2 acceptance checks.
- Add compatibility checks only where needed for Agent/backtest P0.
- Keep target's ClickHouse/DuckDB/PostgreSQL implementation if it enforces equivalent PIT semantics.

Risk:

- Endpoint names may differ from target.
- Direct copying could conflict with target API layout and settings.

## P0 Gap Summary

| Area | Target status | Gap | P0 action |
| --- | --- | --- | --- |
| Audit schema | Mostly present | Need executable proof | Add tests/acceptance and update docs |
| Append-only audit | Migration present | Need verification path | Test trigger or script check |
| Audit export | API present | Need completeness check | Add acceptance assertions |
| AnalysisContext PIT | Mostly present | Market fallback/local-only risk | Inspect and harden Agent path if needed |
| TradingAgents trace | Present | Need role/mode evidence tests | Add focused tests |
| OrderIntent/RiskGuard | Present | Need pass/block audit tests | Add focused tests |
| Paper execution | Present | Need linked audit/PnL evidence check | Add acceptance assertions |
| Backtest PIT | Partly unknown | Need deeper inspection | Inspect service/API and add tests |
| Replay | Partly present | Need immutable reconstruction evidence | Inspect and add acceptance assertions |
| Frontend pages | Present | Need smoke/UI evidence | Inspect and run browser smoke after changes |
| Data platform APIs | Equivalent likely | As-of/snapshot endpoint mismatch possible | Add compatibility or document equivalent |

## Migration Risk Ranking

- Low risk: Add acceptance script, focused tests, docs, audit export assertions.
- Medium risk: Harden Agent market-data fallback and add API compatibility wrappers.
- Medium risk: Backtest evidence model/API augmentation.
- High risk: Wholesale importing backtest-v2 UI/services from reference.
- Excluded for P0: Live trading, large data-platform migrations, full configuration center.

## Post-Implementation Notes

- Agent bar loading now calls `MarketDataGateway.get_klines(..., allow_external_fallback=False, allow_ccxt_fallback=False, allow_binance_fallback=False)` from `AnalysisContextBuilder`.
- Bar metadata records `agent_input_policy=local_storage_only` and `external_fallback_allowed=false`.
- Target now exposes PRD-compatible data-platform routes:
  - `GET /api/v1/market/bars/as-of`
  - `GET /api/v1/market/snapshot/{symbol}`
- Existing target backtest code already supports `executionMode=agent_audited`, `maxAgentCalls`, Agent decision points, OrderIntent, RiskGuard, paper-order audit chain, replay session linkage, PIT checks, and audit IDs.
- Frontend P0 pages were reused rather than rewritten because the target already exposes the required audit, decision, backtest, and replay evidence panels.

## P1/P2 Gap Update

Implemented:

- TradingAgents effective configuration and readiness API:
  - `GET /api/v1/system/tradingagents-config`
  - redacted service/LLM URL display
  - provider/model/mode/full graph readiness/strong acceptance eligibility
  - repeated local/PIT Agent input boundary
- RiskGuard configuration center:
  - `GET /api/v1/risk/config-metadata`
  - `POST /api/v1/risk/config`
  - `POST /api/v1/risk/config/reset`
  - `/risk` frontend page
  - editable coverage for single-position, total exposure, drawdown, daily loss, price deviation, margin, volatility, and forbidden symbols
  - config update/reset audit events
- Phase 2 P1/P2 status map:
  - `GET /api/v1/system/phase2-p1p2-status`
- Monitor page TradingAgents configuration/readiness panel.
- Static acceptance coverage for P1 config APIs and frontend panels.
- Focused tests for URL redaction, full graph readiness, fast-mode/local-boundary readiness, and RiskGuard config validation.

Already covered by existing target implementation:

- Research desk linkage through `/signals`, `/market/research-snapshot/{symbol}`, historical `as_of_time`, and backtest-to-research context links.
- Advanced analytics through `/analytics`, `/api/v1/analytics/strategy-comparison`, `/api/v1/analytics/replay-backtest-comparison`, and attribution comparison APIs.
- Basic risk status and execution gating through `/api/v1/trading/risk/status`, OrderIntent, and RiskGuard execution paths.

Remaining P2 gaps:

- Custom Agent marketplace and role/workflow customization.
- Complex approval workflow.
- Multi-market expansion.
- Live broker execution, still excluded by Phase 2 P0/P1 safety boundary.
- Large infrastructure migration such as Prefect/TimescaleDB.
