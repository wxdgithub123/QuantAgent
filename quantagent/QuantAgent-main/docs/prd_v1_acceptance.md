# PRD v1 Acceptance

This document maps the PRD v1 flow to the current QuantAgent implementation and
the commands used to verify it.

## Scope

The PRD v1 flow is:

1. External data enters through OpenBB and fallback adapters.
2. Data is standardized into internal objects and stored.
3. L5 generates factors, signals, news/macro enrichment, and AnalysisContext.
4. L6 sends AnalysisContext through the coordinator and TradingAgents service.
5. Decisions, backtests, and replay sessions are persisted for audit/review.
6. Frontend/API surfaces expose status, factors, decisions, replay, and backtest.

## Acceptance Command

Run from the project root while Docker services are up:

```powershell
python backend\scripts\prd_v1_acceptance.py --write-checks
```

Expected result: every check prints `PASS`.

The `--write-checks` mode performs DB-writing checks:

- Runs a real MA backtest against ClickHouse historical data.
- Persists the backtest result.
- Creates a replay session linked to that backtest id.
- Archives standardized ClickHouse K-lines into DuckDB/Parquet partitions.

For a faster read-mostly readiness check:

```powershell
python backend\scripts\prd_v1_acceptance.py
```

## Current Evidence

Latest local acceptance run:

```text
[PASS] prd_health: L1/L4/L5/L6/infrastructure healthy
[PASS] l1_data: crypto_tickers=6, headlines=12, macro=6, equity=SPY@750.4600219726562
[PASS] standard_storage: 30 symbol/interval rows ok
[PASS] prd_flow_api: 6 PRD stages ok
[PASS] l5_signal_context: bars=120, factors=1766, signals=961, news=20, macro=30
[PASS] l6_decision_audit: default=WAIT, tradingagents=WAIT, history_rows=5
[PASS] replay_backtest_readiness: templates=8, replay_range=2026-04-28T18:00:00..2026-05-28T08:00:00
[PASS] frontend_visibility: pages=/dashboard,/signals,/decisions,/replay,/backtest
[PASS] parquet_archive_write: rows=360, files=16, path=data/market
[PASS] replay_backtest_write: backtest_id=7, replay_session_id=REPLAY_20260528_b57a23, final_capital=9221.432001704117
```

## API Visibility

The full PRD status is exposed at:

```text
GET /api/v1/system/prd-flow
```

It returns:

- `overall_status`
- per-stage status for PRD sections 10.1 through 10.6
- persisted counts for factors, signals, coordination decisions, backtests, and replay sessions

The dashboard also displays this as the `PRD v1 Full Flow` panel.

## PRD Mapping

| PRD section | Evidence |
| --- | --- |
| 10.1 Data ingestion | `/api/v1/system/health`, `/api/v1/market/overview`, `/api/v1/market/macro`, `/api/v1/market/news`, `/api/v1/market/equity/ticker/SPY` |
| 10.2 Standardization and storage | `/api/v1/market/backfill/status`, `/api/v1/market/archive/parquet`, ClickHouse/PostgreSQL/Redis health, DuckDB/Parquet stats |
| 10.3 Factors and signals | `/api/v1/signals/run`, `/api/v1/signals/context/{symbol}`, `/api/v1/signals/summary` |
| 10.4 TradingAgents analysis | `/api/v1/market/coordinate/{symbol}?use_tradingagents=true`, TradingAgents service health |
| 10.5 Backtest and audit | `/api/v1/strategy/backtest/run`, `/api/v1/replay/create`, `/api/v1/coordination/history` |
| 10.6 Frontend and API | `/dashboard`, `/signals`, `/decisions`, `/replay`, `/backtest`, `/api/v1/system/prd-flow` |

## Notes

- TradingAgents remains isolated in a separate service to avoid dependency conflicts with OpenBB.
- The default decision route still supports the local coordinator; TradingAgents can be requested per call with `use_tradingagents=true`.
- DuckDB/Parquet is reported by health checks. The active production time-series backend remains ClickHouse in Docker.
