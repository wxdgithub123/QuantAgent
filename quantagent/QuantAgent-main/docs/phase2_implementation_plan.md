# Phase 2 Implementation Plan

Last updated: 2026-06-10

This plan prioritizes executable P0 slices and reuses target repository capabilities before adding new abstractions.

## P0-0 Baseline and Documentation

Goal:

- Persist requirements, gap analysis, implementation plan, acceptance checklist, and current goal state.
- Run focused baseline checks before code changes when possible.

Files:

- `docs/phase2_goal_state.md`
- `docs/phase2_requirements_context.md`
- `docs/phase2_gap_analysis.md`
- `docs/phase2_implementation_plan.md`
- `docs/phase2_acceptance_checklist.md`

Backend changes:

- None.

Frontend changes:

- None.

Database changes:

- None.

Tests/commands:

- `git status --short`
- Focused backend pytest baseline after inspecting test availability.

Acceptance:

- All five Phase 2 documents exist and name the owned scope, P0 requirements, gaps, and acceptance path.

## P0-1 Audit Immutability and Export

Goal:

- Prove and harden append-only audit, hash chain, linked evidence fields, detail API, and JSON export.

Files:

- `backend/app/models/db_models.py`
- `backend/app/services/audit_service.py`
- `backend/migrations/versions/015_harden_audit_logs.py`
- `backend/app/api/v1/endpoints/audit.py`
- `backend/tests/unit/test_audit_service.py`
- `backend/scripts/phase2_acceptance.py`
- `frontend/app/audit/page.tsx`

Backend changes:

- Reuse current schema/service if complete.
- Add missing export/evidence fields only if inspection finds gaps.
- Add deterministic tests for write, hash verification, immutable flag, detail/export evidence, and update/delete rejection where DB is available.

Frontend changes:

- Ensure audit page shows hash, immutable status, PIT evidence, Agent output, risk/execution chain, and JSON export.

Database changes:

- Prefer existing migration `015_harden_audit_logs.py`.
- Add migration only if a required Phase 2 field/index is actually absent.

Tests/commands:

- `python -m pytest tests/unit/test_audit_service.py`
- `python backend/scripts/phase2_acceptance.py --offline` or equivalent script mode if services are unavailable.

Acceptance:

- Audit events are append-only.
- Export contains input, Agent, RiskGuard, execution, PIT, hash, and immutable evidence.

## P0-2 Agent Decision Traceability

Goal:

- Ensure every Agent decision is based on local/PIT AnalysisContext and writes traceable audit evidence.

Files:

- `backend/app/services/analysis_context_builder.py`
- `backend/app/models/analysis_context.py`
- `backend/app/agents/coordinator_agent.py`
- `backend/app/agents/tradingagents_adapter.py`
- `tradingagents-service/main.py`
- `backend/tests/unit/test_tradingagents_adapter_context.py`
- `backend/scripts/phase2_acceptance.py`
- `frontend/app/decisions/page.tsx`

Backend changes:

- Confirm or enforce local-only/data-platform-only Agent input.
- Preserve `input_snapshot_ids`, `data_versions`, `as_of_time`, `available_time` checks, and `context_hash`.
- Confirm fast/full graph metadata appears in output and audit details.
- Add tests for stable context hash and mode differentiation.

Frontend changes:

- Ensure decision page shows input summary, snapshot/context IDs, role outputs, final decision, and history.

Database changes:

- None expected unless decision-history fields are absent.

Tests/commands:

- `python -m pytest tests/unit/test_tradingagents_adapter_context.py`

Acceptance:

- Agent decision audit can be traced back to local input IDs/hash and PIT checks.
- Fast/full mode is visible.

## P0-3 OrderIntent, RiskGuard, and Paper Execution Linkage

Goal:

- Complete decision-to-OrderIntent-to-risk-to-paper-execution-to-audit linkage.

Files:

- `backend/app/services/order_intent_service.py`
- `backend/app/services/risk_manager.py`
- `backend/app/api/v1/endpoints/execution.py`
- `backend/tests/unit/test_order_intent_service.py`
- `backend/scripts/phase2_acceptance.py`
- `frontend/app/decisions/page.tsx`
- `frontend/app/audit/page.tsx`

Backend changes:

- Reuse existing OrderIntent normalization and execution methods.
- Add missing audit links for pass/block/fill/reject if needed.
- Control any nondeterministic risk checks in tests.

Frontend changes:

- Surface OrderIntent status and RiskGuard pass/block outcome in decision/audit pages.

Database changes:

- None expected unless link fields are absent.

Tests/commands:

- `python -m pytest tests/unit/test_order_intent_service.py`

Acceptance:

- Passing risk check produces paper execution and linked audit.
- Blocking risk check produces BLOCKED/REJECTED audit and no paper fill.

## P0-4 Point-in-Time Backtest and Replay

Goal:

- Verify or harden PIT backtest execution and replay/audit linkage.

Files:

- `backend/app/api/v1/endpoints/replay.py`
- `backend/app/api/v1/endpoints/analytics.py`
- `backend/app/services/backtester/event_driven.py`
- `backend/app/services/backtester/vectorized.py`
- `backend/app/services/backtester/reproducibility.py`
- `backend/tests/unit/test_backtest_p3_helpers.py`
- `backend/scripts/phase2_acceptance.py`
- `frontend/app/backtest/page.tsx`
- `frontend/app/replay/page.tsx`

Backend changes:

- Confirm backtest uses `available_time <= as_of_time` and persists evidence.
- Add lightweight evidence fields or acceptance checks if missing.
- Confirm replay reconstructs from immutable audit/context evidence without mutating originals.

Frontend changes:

- Ensure backtest page shows config, status, metrics, trade table, PIT checks, Agent stats, and audit/replay links where available.
- Ensure replay page is non-empty and shows replay state/evidence.

Database changes:

- Add migration only if backtest/audit linkage fields are absent.

Tests/commands:

- `python -m pytest tests/unit/test_backtest_p3_helpers.py`
- Add/extend focused tests if backtest PIT evidence is missing.

Acceptance:

- Backtest prevents future data, records Agent call count/decision points, writes metrics/trade evidence, and can link to audit/replay.

## P0-5 Acceptance Script and Verification

Goal:

- Provide a machine-runnable acceptance script and record actual verification results.

Files:

- `backend/scripts/phase2_acceptance.py`
- `docs/phase2_goal_state.md`
- `docs/phase2_acceptance_checklist.md`

Backend changes:

- Add script with offline/static checks and optional live API checks if services are configured.

Frontend changes:

- None expected unless smoke finds broken UI.

Database changes:

- None expected.

Tests/commands:

- `python backend/scripts/phase2_acceptance.py`
- Focused pytest suite.
- Frontend lint/typecheck where available.
- Browser smoke for `/audit`, `/decisions`, `/backtest`, and `/replay` if the app can run locally.

Acceptance:

- Script reports pass/fail for:
  - data-platform as-of/snapshot availability or equivalent AnalysisContext endpoint,
  - Agent audit generation,
  - local snapshot/context hash,
  - OrderIntent generation,
  - RiskGuard pass/block audit,
  - paper execution audit linkage,
  - backtest metrics,
  - no-future-data evidence,
  - audit JSON export,
  - append-only audit enforcement.

## P1-1 TradingAgents Configuration and Monitor Readiness

Goal:

- Expose the effective TradingAgents configuration, readiness, and local-data boundary so operators can see whether the system is in fast research mode, patched/full graph mode, or unavailable.

Files:

- `backend/app/api/v1/endpoints/system_health.py`
- `backend/tests/unit/test_system_tradingagents_config.py`
- `backend/scripts/phase2_acceptance.py`
- `frontend/app/monitor/page.tsx`
- `docs/phase2_goal_state.md`
- `docs/phase2_acceptance_checklist.md`
- `docs/phase2_gap_analysis.md`

Backend changes:

- Added `GET /api/v1/system/tradingagents-config`.
- Added `GET /api/v1/system/phase2-p1p2-status`.
- Redact service and LLM URLs before returning them to the UI.
- Report provider/model/mode, fast research readiness, full graph readiness, strong acceptance eligibility, selected analysts/roles, and local/PIT data boundary.

Frontend changes:

- Added a TradingAgents configuration panel to `/monitor`.
- Added a running-readiness panel that separates fast research readiness from full TradingAgentsGraph readiness.
- Hardened monitor page API error handling so non-JSON backend failures show a friendly message.

Tests/commands:

- `python -m pytest tests/unit/test_system_tradingagents_config.py tests/unit/test_tradingagents_adapter_context.py tests/unit/test_analysis_context_builder_pit.py -q`
- `python backend/scripts/phase2_acceptance.py`
- `npx eslint app/monitor/page.tsx`
- `npx tsc --noEmit --pretty false --incremental false`
- Browser smoke for `http://localhost:3002/monitor`

Acceptance:

- P1 config/readiness endpoint returns redacted LLM/service config and local-only PIT Agent boundary.
- Monitor page renders the TradingAgents configuration/readiness panels without a Next error overlay.
- Offline acceptance script reports 12/12 checks passed.

## P1-2 RiskGuard Configuration Center

Goal:

- Complete the P1/P2 configuration-center coverage for RiskGuard without changing the paper-only execution boundary.

Files:

- `backend/app/services/risk_manager.py`
- `backend/app/api/v1/endpoints/risk.py`
- `backend/app/api/v1/endpoints/system_health.py`
- `backend/tests/unit/test_risk_config_api.py`
- `backend/scripts/phase2_acceptance.py`
- `frontend/app/risk/page.tsx`
- `frontend/components/navigation/AppTopNav.tsx`
- `frontend/components/navigation/Breadcrumb.tsx`
- Phase 2 docs

Backend changes:

- Risk config reads merge hot-updated Redis values with settings defaults.
- Risk config updates store a complete merged config and include total exposure, forbidden symbols, margin thresholds, volatility thresholds, and price deviation.
- Added `GET /api/v1/risk/config-metadata`.
- Added `POST /api/v1/risk/config/reset`.
- Risk config update/reset paths write audit events when the database is available.

Frontend changes:

- Added `/risk` as a dedicated RiskGuard configuration page.
- Added navigation and breadcrumb entries.
- The page supports threshold editing, forbidden symbols, config reset, and kill-switch trigger/reset controls.

Tests/commands:

- `python -m pytest tests/unit/test_risk_config_api.py tests/unit/test_system_tradingagents_config.py tests/unit/test_tradingagents_adapter_context.py tests/unit/test_analysis_context_builder_pit.py -q`
- `python backend/scripts/phase2_acceptance.py`
- `npx eslint app/risk/page.tsx components/navigation/AppTopNav.tsx components/navigation/Breadcrumb.tsx app/monitor/page.tsx`
- `npx tsc --noEmit --pretty false --incremental false`
- Browser smoke for `http://localhost:3002/risk`

Acceptance:

- RiskGuard config metadata exposes all editable P1/P2 fields.
- Invalid risk config updates are rejected before hot update.
- The `/risk` page renders without a Next error overlay and degrades cleanly when the backend is unavailable.
- Offline acceptance script reports 14/14 checks passed.

## P1/P2 Remaining Work

- Full custom Agent marketplace.
- Complex approval workflows.
- Multi-market expansion.
- Live broker execution.
- Prefect/TimescaleDB migration.
- Large UI redesign.
