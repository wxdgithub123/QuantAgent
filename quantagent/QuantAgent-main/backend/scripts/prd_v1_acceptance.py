"""PRD v1 end-to-end acceptance checks.

Run from the project root while the Docker stack is up:
    python backend/scripts/prd_v1_acceptance.py --write-checks

The default mode is read-mostly and verifies that every PRD layer is reachable.
Use --write-checks for release acceptance: it also runs a real backtest and
creates a replay session from the resulting backtest id.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BACKEND_URL = "http://localhost:8002"
DEFAULT_FRONTEND_URL = "http://localhost:3002"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class AcceptanceClient:
    def __init__(self, backend_url: str, frontend_url: str, timeout: float) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.frontend_url = frontend_url.rstrip("/")
        self.timeout = timeout

    def get_api(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        return self._request_json("GET", f"{self.backend_url}{path}{query}")

    def post_api(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request_json("POST", f"{self.backend_url}{path}", payload)

    def get_frontend(self, path: str) -> str:
        request = Request(f"{self.frontend_url}{path}", method="GET")
        with urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    def _request_json(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _path(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_dt(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def check_health(client: AcceptanceClient) -> CheckResult:
    data = client.get_api("/api/v1/system/health")
    checks = {
        "openbb": _path(data, "layers", "L1_data_source", "openbb", "status"),
        "fred": _path(data, "layers", "L1_data_source", "fred", "status"),
        "market_data": _path(data, "layers", "L1_data_source", "market_data", "status"),
        "clickhouse": _path(data, "layers", "L4_storage", "clickhouse", "status"),
        "l5_pipeline": _path(data, "layers", "L5_factors_signals", "pipeline", "status"),
        "l5_counts": _path(data, "layers", "L5_factors_signals", "counts", "status"),
        "tradingagents": _path(data, "layers", "L6_decision", "tradingagents_service", "status"),
        "coordinator": _path(data, "layers", "L6_decision", "coordinator", "status"),
    }
    infra = data.get("infrastructure") or {}
    checks.update({
        "postgresql": infra.get("postgresql"),
        "redis": infra.get("redis"),
        "nats": infra.get("nats"),
    })
    failed = [name for name, status in checks.items() if status not in {"ok", "connected"}]
    if failed:
        return CheckResult("prd_health", False, f"failed={failed}; checks={checks}")
    return CheckResult("prd_health", True, "L1/L4/L5/L6/infrastructure healthy")


def check_l1_data(client: AcceptanceClient) -> CheckResult:
    overview = client.get_api("/api/v1/market/overview")
    macro = client.get_api("/api/v1/market/macro")
    news = client.get_api("/api/v1/market/news", {"symbol": "BTC", "limit": 5})
    equity = client.get_api("/api/v1/market/equity/ticker/SPY", {"provider": "yfinance"})

    tickers = _as_list(overview.get("tickers"))
    headlines = _as_list(overview.get("headlines"))
    indicators = macro.get("indicators") or {}
    articles = _as_list(news.get("articles"))
    if not tickers:
        return CheckResult("l1_data", False, "market overview has no tickers")
    if not headlines and not articles:
        return CheckResult("l1_data", False, "news endpoints returned no articles")
    if not indicators:
        return CheckResult("l1_data", False, "macro endpoint returned no indicators")
    if not equity.get("price"):
        return CheckResult("l1_data", False, f"equity ticker missing price: {equity}")
    return CheckResult(
        "l1_data",
        True,
        (
            f"crypto_tickers={len(tickers)}, headlines={len(headlines) or len(articles)}, "
            f"macro={len(indicators)}, equity=SPY@{equity.get('price')}"
        ),
    )


def check_backfill(client: AcceptanceClient) -> CheckResult:
    data = client.get_api("/api/v1/market/backfill/status")
    intervals = _as_list(data.get("intervals"))
    failed = [
        f"{row.get('symbol')}:{row.get('interval')}={row.get('status')}"
        for row in intervals
        if isinstance(row, dict) and row.get("status") != "ok"
    ]
    if not intervals:
        return CheckResult("standard_storage", False, "backfill status returned no interval rows")
    if failed:
        return CheckResult("standard_storage", False, ", ".join(failed[:10]))
    return CheckResult("standard_storage", True, f"{len(intervals)} symbol/interval rows ok")


def check_prd_flow_api(client: AcceptanceClient) -> CheckResult:
    data = client.get_api("/api/v1/system/prd-flow")
    stages = _as_list(data.get("stages"))
    failed = [
        f"{stage.get('label')}={stage.get('status')}"
        for stage in stages
        if isinstance(stage, dict) and stage.get("status") != "ok"
    ]
    if data.get("overall_status") != "ok" or failed:
        return CheckResult("prd_flow_api", False, f"overall={data.get('overall_status')}; failed={failed}")
    return CheckResult("prd_flow_api", True, f"{len(stages)} PRD stages ok")


def check_signal_context(client: AcceptanceClient, symbol: str, interval: str, limit: int) -> CheckResult:
    payload = {
        "symbol": symbol,
        "asset_type": "crypto",
        "interval": interval,
        "limit": limit,
        "provider": "yfinance",
        "include_wait_signals": True,
        "persist_fetched_bars": False,
        "refresh_from_source": False,
        "include_context": True,
    }
    data = client.post_api("/api/v1/signals/run", payload)
    context = data.get("analysis_context") or {}
    metadata = context.get("metadata") or {}
    if data.get("status") != "ok":
        return CheckResult("l5_signal_context", False, f"status={data.get('status')}")
    if not context:
        return CheckResult("l5_signal_context", False, "missing AnalysisContext")
    if metadata.get("point_in_time_rule") != "available_time <= as_of_time":
        return CheckResult("l5_signal_context", False, f"missing point-in-time rule: {metadata}")
    return CheckResult(
        "l5_signal_context",
        True,
        (
            f"bars={data.get('bars')}, factors={data.get('factor_rows_written')}, "
            f"signals={data.get('signal_rows_written')}, news={data.get('news_events_used')}, "
            f"macro={data.get('macro_events_used')}"
        ),
    )


def check_decision_and_audit(client: AcceptanceClient, symbol: str, interval: str) -> CheckResult:
    default = client.get_api(
        f"/api/v1/market/coordinate/{symbol}",
        {"interval": interval, "fast": "true", "use_tradingagents": "false"},
    )
    tradingagents = client.get_api(
        f"/api/v1/market/coordinate/{symbol}",
        {"interval": interval, "fast": "true", "use_tradingagents": "true"},
    )
    history = client.get_api("/api/v1/coordination/history", {"symbol": symbol, "limit": 5})
    stats = client.get_api("/api/v1/coordination/stats")

    if default.get("data_source") != "analysis_context":
        return CheckResult("l6_decision_audit", False, f"default source={default.get('data_source')}")
    if tradingagents.get("data_source") != "tradingagents-service":
        return CheckResult("l6_decision_audit", False, f"TradingAgents source={tradingagents.get('data_source')}")
    rows = _as_list(history.get("data"))
    if not rows:
        return CheckResult("l6_decision_audit", False, "coordination history is empty after decision run")
    if (stats.get("total") or 0) <= 0:
        return CheckResult("l6_decision_audit", False, "coordination stats total is zero")
    return CheckResult(
        "l6_decision_audit",
        True,
        (
            f"default={default.get('final_signal') or default.get('action')}, "
            f"tradingagents={tradingagents.get('final_signal') or tradingagents.get('action')}, "
            f"history_rows={len(rows)}"
        ),
    )


def check_replay_backtest_readiness(client: AcceptanceClient, symbol: str, interval: str) -> CheckResult:
    templates = client.get_api("/api/v1/strategy/templates")
    history = client.get_api("/api/v1/strategy/backtest/history", {"limit": 5})
    date_range = client.get_api(f"/api/v1/replay/valid-date-range/{symbol}", {"interval": interval})
    sessions = client.get_api("/api/v1/replay/sessions", {"limit": 1})

    template_rows = _as_list(templates.get("templates"))
    replay_templates = [row.get("id") for row in template_rows if isinstance(row, dict) and row.get("supports_replay")]
    if "ma" not in replay_templates:
        return CheckResult("replay_backtest_readiness", False, f"MA template missing from replay templates={replay_templates}")
    if not date_range.get("min_date") or not date_range.get("max_date"):
        return CheckResult("replay_backtest_readiness", False, f"invalid replay date range={date_range}")
    if "history" not in history:
        return CheckResult("replay_backtest_readiness", False, "backtest history endpoint missing history field")
    if "sessions" not in sessions:
        return CheckResult("replay_backtest_readiness", False, "replay sessions endpoint missing sessions field")
    return CheckResult(
        "replay_backtest_readiness",
        True,
        f"templates={len(template_rows)}, replay_range={date_range.get('min_date')}..{date_range.get('max_date')}",
    )


def check_parquet_archive_write(client: AcceptanceClient, symbol: str, interval: str) -> CheckResult:
    archive = client.post_api(
        "/api/v1/market/archive/parquet",
        {"symbols": [symbol], "intervals": [interval], "limit": 360},
    )
    if archive.get("status") != "ok" or (archive.get("total_written") or 0) <= 0:
        return CheckResult("parquet_archive_write", False, f"archive failed: {archive}")

    health = client.get_api("/api/v1/system/health")
    parquet = _path(health, "layers", "L4_storage", "parquet") or {}
    if (parquet.get("files") or 0) <= 0:
        return CheckResult("parquet_archive_write", False, f"health parquet stats empty: {parquet}")
    return CheckResult(
        "parquet_archive_write",
        True,
        f"rows={archive.get('total_written')}, files={parquet.get('files')}, path={archive.get('archive_path')}",
    )


def check_backtest_and_replay_write(client: AcceptanceClient, symbol: str, interval: str, capital: float) -> CheckResult:
    date_range = client.get_api(f"/api/v1/replay/valid-date-range/{symbol}", {"interval": interval})
    min_dt = _parse_dt(date_range["min_date"])
    max_dt = _parse_dt(date_range["max_date"])
    start_dt = max(min_dt, max_dt - timedelta(hours=360))
    available_hours = (max_dt - start_dt).total_seconds() / 3600
    if available_hours < 300:
        return CheckResult("replay_backtest_write", False, f"not enough 1h data for write check: {available_hours:.0f}h")

    backtest_payload = {
        "strategy_type": "ma",
        "symbol": symbol,
        "interval": interval,
        "limit": 360,
        "initial_capital": capital,
        "start_time": start_dt.isoformat().replace("+00:00", "Z"),
        "end_time": max_dt.isoformat().replace("+00:00", "Z"),
        "params": {"fast_period": 10, "slow_period": 30},
    }
    backtest = client.post_api("/api/v1/strategy/backtest/run", backtest_payload)
    backtest_id = backtest.get("id")
    metrics = backtest.get("metrics") or {}
    equity = _as_list(backtest.get("equity_curve"))
    if not backtest_id or not equity:
        return CheckResult("replay_backtest_write", False, f"backtest did not persist: id={backtest_id}, equity={len(equity)}")
    if "final_capital" not in metrics:
        return CheckResult("replay_backtest_write", False, f"backtest metrics missing final_capital: {metrics}")

    replay_payload = {
        "strategy_id": 1,
        "strategy_type": "ma",
        "symbol": symbol,
        "interval": interval,
        "start_time": start_dt.isoformat().replace("+00:00", "Z"),
        "end_time": max_dt.isoformat().replace("+00:00", "Z"),
        "speed": -1,
        "initial_capital": capital,
        "params": {"fast_period": 10, "slow_period": 30},
        "backtest_id": backtest_id,
        "equity_snapshot_interval": 3600,
    }
    replay = client.post_api("/api/v1/replay/create", replay_payload)
    replay_id = replay.get("replay_session_id")
    if not replay_id or replay.get("status") != "pending":
        return CheckResult("replay_backtest_write", False, f"replay create failed: {replay}")
    return CheckResult(
        "replay_backtest_write",
        True,
        f"backtest_id={backtest_id}, replay_session_id={replay_id}, final_capital={metrics.get('final_capital')}",
    )


def check_frontend(client: AcceptanceClient) -> CheckResult:
    pages = ["/dashboard", "/signals", "/decisions", "/replay", "/backtest"]
    loaded: list[str] = []
    for page in pages:
        html = client.get_frontend(page)
        if "<html" not in html.lower() and "__next" not in html.lower():
            return CheckResult("frontend_visibility", False, f"{page} did not return an HTML app shell")
        loaded.append(page)
    return CheckResult("frontend_visibility", True, f"pages={','.join(loaded)}")


def run_check(name: str, fn: Callable[[], CheckResult]) -> CheckResult:
    try:
        return fn()
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return CheckResult(name, False, str(exc))


def run(args: argparse.Namespace) -> int:
    client = AcceptanceClient(args.backend_url, args.frontend_url, args.timeout)
    started = time.perf_counter()
    checks: list[tuple[str, Callable[[], CheckResult]]] = [
        ("prd_health", lambda: check_health(client)),
        ("l1_data", lambda: check_l1_data(client)),
        ("standard_storage", lambda: check_backfill(client)),
        ("prd_flow_api", lambda: check_prd_flow_api(client)),
        ("l5_signal_context", lambda: check_signal_context(client, args.symbol, args.interval, args.limit)),
        ("l6_decision_audit", lambda: check_decision_and_audit(client, args.symbol, args.interval)),
        ("replay_backtest_readiness", lambda: check_replay_backtest_readiness(client, args.symbol, args.interval)),
        ("frontend_visibility", lambda: check_frontend(client)),
    ]
    if args.write_checks:
        checks.append(
            (
                "parquet_archive_write",
                lambda: check_parquet_archive_write(client, args.symbol, args.interval),
            )
        )
        checks.append(
            (
                "replay_backtest_write",
                lambda: check_backtest_and_replay_write(client, args.symbol, args.interval, args.initial_capital),
            )
        )

    results = [run_check(name, fn) for name, fn in checks]
    for result in results:
        print(f"[{'PASS' if result.ok else 'FAIL'}] {result.name}: {result.detail}")

    elapsed = time.perf_counter() - started
    passed = all(result.ok for result in results)
    mode = "write" if args.write_checks else "readiness"
    print(f"\nPRD v1 acceptance ({mode}) {'passed' if passed else 'failed'} in {elapsed:.1f}s")
    return 0 if passed else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the full PRD v1 QuantAgent flow.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--initial-capital", type=float, default=10000.0)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--write-checks", action="store_true", help="Run DB-writing backtest and replay create checks.")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
