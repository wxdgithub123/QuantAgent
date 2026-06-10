# Phase 2 Requirements Context

Last updated: 2026-06-10

This document persists the Phase 2 requirements relevant to the owned scope: audit, Agent decisions, backtest/replay, OrderIntent/RiskGuard/paper execution, and directly related frontend surfaces.

## Source Map

- Phase 2 PRD: `量化研究平台 · 第二阶段 PRD.docx`
  - Core closed-loop objective: data, decision, execution, visualization, audit.
  - Execution layer: TradingAgents recommendation to standardized OrderIntent, RiskGuard checks, paper execution only.
  - Backtest: strict point-in-time data use, selective Agent invocation on strong signals, metrics and decision/risk evidence persisted.
  - Audit: full context snapshot, role input/output, reasoning chain, OrderIntent, RiskGuard, execution, replay/export.
- Data platform PRD: `金融数据平台子系统需求.docx`
  - Local-first data platform, FastAPI API access, point-in-time storage semantics.
  - Time fields: `event_time`, `ingest_time`, `available_time`.
  - Downstream systems consume local storage/API rather than bypassing the data platform.
- Function module table: `功能模块V2.xlsx`
  - Rows 32-37: TradingAgents page controls, status, input summary, role outputs, final decision, local-only Agent data, input data IDs.
  - Rows 46-47: OrderIntent list and RiskGuard checks.
  - Row 59: Agent input/output by role.
  - Rows 71, 73, 74: backtest chart, PIT checks, Agent participation statistics.
  - Row 95: TradingAgents configuration, treated as P1/P2 unless already present.

## Hard Rules

- Agent input must come from local stored data or data-platform APIs. Agent paths must not bypass local data into external live sources.
- Every Agent decision must record input record IDs, snapshot/context hash, `as_of_time`, `available_time` checks, Agent outputs, final decision, OrderIntent, RiskGuard result, and execution result.
- Backtest must be strict point-in-time: only data with `available_time <= as_of_time` may be used.
- Audit records must be append-only. Update/delete must be rejected by database-level or equivalent enforcement.
- Risk failure must write BLOCKED or REJECTED audit evidence. Silent failure is not acceptable.
- P0 closes the loop for simulation/backtest/audit. Live trading is excluded.

## Module Requirements

### Audit

Priority: P0

- Standardize AuditRecord/AuditLog fields while reusing existing schema where possible.
- Required evidence fields include `payload_hash`, `prev_hash`, `context_hash`, `immutable`, `decision_id`, `backtest_id`, `replay_session_id`, `order_intent_id`, and `order_id`.
- Maintain an append-only hash chain for audit evidence.
- Provide audit list, detail, decision detail, replay, and JSON export APIs.
- Audit export must include input snapshot, Agent output, risk/execution chain, PIT evidence, hash values, and immutable status.

Sources: Phase 2 PRD audit closure; function module table row 59; rows 71, 73, 74 for backtest evidence and decision linkage.

### Agent Decision

Priority: P0

- Build AnalysisContext from local/data-platform data only.
- Store `input_snapshot_ids`, `data_versions`, `as_of_time`, `available_time` visibility checks, and `context_hash`.
- Distinguish fast TradingAgents mode from full graph/patched graph mode.
- Persist Agent role input summaries, role outputs, model metadata, elapsed time, final recommendation, confidence, and risk notes.
- Each decision must be traceable to audit records and, where applicable, OrderIntent and paper execution.

Sources: Phase 2 PRD decision chain; function module table rows 32-37 and 59; data platform PRD local-first and PIT storage semantics.

### OrderIntent and RiskGuard

Priority: P0

- Convert actionable TradingAgents recommendations into standardized OrderIntent.
- Required normalized fields include `direction`, `position_ratio` or equivalent position percent, `effective_until` or TTL, `confidence`, `reason`, and `source_decision_id`.
- RiskGuard must at least cover single-position maximum, total exposure maximum, forbidden symbols, and daily-loss circuit breaker.
- Risk pass/fail must be written to audit.
- Risk fail must produce BLOCKED/REJECTED evidence and prevent paper execution.

Sources: Phase 2 PRD execution layer; function module table rows 46-47.

### Paper Execution

Priority: P0

- P0 execution is paper/simulated only.
- Accepted OrderIntent should become a simulated order/fill.
- Execution result must record order lifecycle, filled quantity/notional, price, fees/slippage where available, PnL where available, and linked audit IDs.
- Rejected paper orders must write audit evidence.

Sources: Phase 2 PRD execution closure; no live trading rule.

### Backtest

Priority: P0

- Support parameters: symbol, interval, start/end time, initial capital, fee rate, slippage, risk config, and Agent mode where available.
- Every backtest step must satisfy `available_time <= as_of_time`.
- Agent should be invoked only when a strong signal or configured condition warrants it, not for every bar by default.
- Persist equity curve, drawdown, trades, Agent decision points, risk blocks, metrics, and reproducibility metadata.
- Backtest results must link to audit detail or replay state.

Sources: Phase 2 PRD backtest closure; function module table rows 71, 73, 74.

### Replay

Priority: P0

- Replay should reconstruct a decision from immutable audit/context evidence.
- Replay result must state whether the original snapshot/context was reused and whether strict snapshot replay was possible.
- Replay must not mutate original audit records.

Sources: Phase 2 PRD audit replay/export closure.

### Frontend Audit Page

Priority: P0

- Show audit list, filters, detail, input snapshot, Agent output, risk/execution chain, PIT checks, hash/immutable evidence, and JSON export action.

Sources: Phase 2 PRD visualization/audit closure; function module table row 59.

### Frontend Agent Decision Page

Priority: P0

- Provide controls, status, input summary, role outputs, final decision card, and historical decisions.
- Show enough IDs and hashes for users to trace the local data basis.

Sources: function module table rows 32-37 and 59.

### Frontend Backtest Page

Priority: P0

- Provide configuration, task status/results, metrics, trade table, PIT checks, Agent participation statistics, and audit/replay links where available.

Sources: Phase 2 PRD backtest closure; function module table rows 71, 73, 74.

### Research Desk Linkage

Priority: P0/P1

- P0 must ensure research snapshots and AnalysisContext can provide local, PIT-safe input to Agent decisions.
- P1 can add richer research-desk UI and cross-navigation after the P0 loop is stable.

Sources: Data platform PRD local API; Phase 2 PRD data-to-decision loop.

### Configuration Center

Priority: P1/P2

- TradingAgents and risk configuration pages are useful but are not the first P0 slice unless already implemented and only need wiring.
- P1 coverage now includes a read-only TradingAgents effective configuration/readiness endpoint and monitor-page panel.
- P1/P2 coverage now includes a RiskGuard configuration center for thresholds, forbidden symbols, reset, and kill-switch controls.
- Custom role marketplace, complex approval flow, and large configuration-center redesign remain deferred P2 document requirements.

Sources: function module table row 95.

### System Monitoring

Priority: P1/P2

- Monitor data freshness, Agent runs, backtests, and audit integrity after P0 closure.
- P0 acceptance may include script-level checks for key invariants.
- P1 coverage now includes TradingAgents mode/provider/model/full graph readiness and Agent local-only PIT input boundary on the monitor page.

Sources: Phase 2 PRD operational closure; data platform PRD platform operations.

### Data Platform Dependency

Priority: P0 dependency, P1 feature surface

- The platform may use ClickHouse, DuckDB, and PostgreSQL instead of TimescaleDB; this is acceptable if point-in-time semantics and local API/storage boundaries are enforced.
- Data platform compatibility should expose or emulate as-of/snapshot capabilities for Agent/backtest consumers.

Sources: Data platform PRD local-first API and PIT storage; hard rule excluding direct external live Agent input.

## Owned vs Non-Owned

Owned:

- Backend audit, decision traceability, OrderIntent, RiskGuard, paper execution linkage, replay, backtest evidence, acceptance script.
- Frontend pages for audit, decisions, replay, and backtest where directly required for the loop.
- Documentation and verification artifacts for the above.

Not owned in P0:

- Full data ingestion pipeline expansion.
- New external market/data integrations.
- Live broker trading.
- Full strategy marketplace.
- Full configuration center redesign.
- Full system observability dashboard beyond necessary acceptance evidence.
