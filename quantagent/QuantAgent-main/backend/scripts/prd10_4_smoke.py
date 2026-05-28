"""PRD 10.4 smoke test for the OpenBB -> L5 -> TradingAgents path.

Run from the project root while the Docker stack is up:
    python backend/scripts/prd10_4_smoke.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://localhost:8002"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class SmokeClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        return self._request("GET", f"{self.base_url}{path}{query}")

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", f"{self.base_url}{path}", payload)

    def _request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _layer(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def check_health(client: SmokeClient) -> CheckResult:
    data = client.get("/api/v1/system/health")
    checks = {
        "openbb": _layer(data, "layers", "L1_data_source", "openbb", "status"),
        "fred": _layer(data, "layers", "L1_data_source", "fred", "status"),
        "clickhouse": _layer(data, "layers", "L4_storage", "clickhouse", "status"),
        "l5": _layer(data, "layers", "L5_factors_signals", "pipeline", "status"),
        "tradingagents": _layer(data, "layers", "L6_decision", "tradingagents_service", "status"),
    }
    failed = [name for name, status in checks.items() if status != "ok"]
    if failed:
        return CheckResult("system_health", False, f"failed={failed}; checks={checks}")
    return CheckResult("system_health", True, "OpenBB/FRED/ClickHouse/L5/TradingAgents all ok")


def check_backfill(client: SmokeClient) -> CheckResult:
    data = client.get("/api/v1/market/backfill/status")
    intervals = data.get("intervals") or []
    failed = [
        f"{row.get('symbol')}:{row.get('interval')}={row.get('status')}"
        for row in intervals
        if row.get("status") != "ok"
    ]
    if failed:
        return CheckResult("backfill_status", False, ", ".join(failed[:10]))
    return CheckResult("backfill_status", True, f"{len(intervals)} symbol/interval checks ok")


def check_signal(client: SmokeClient, symbol: str, interval: str, limit: int) -> CheckResult:
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
    data = client.post("/api/v1/signals/run", payload)
    if data.get("status") != "ok":
        return CheckResult("l5_signals", False, f"status={data.get('status')}")
    if not data.get("analysis_context"):
        return CheckResult("l5_signals", False, "missing analysis_context")
    detail = (
        f"{symbol} {interval}: bars={data.get('bars')}, "
        f"factors={data.get('factor_rows_written')}, signals={data.get('signal_rows_written')}, "
        f"news={data.get('news_events_used')}, macro={data.get('macro_events_used')}"
    )
    return CheckResult("l5_signals", True, detail)


def check_coordinator(
    client: SmokeClient,
    symbol: str,
    interval: str,
    use_tradingagents: bool,
) -> CheckResult:
    data = client.get(
        f"/api/v1/market/coordinate/{symbol}",
        {
            "interval": interval,
            "fast": "true",
            "use_tradingagents": "true" if use_tradingagents else "false",
        },
    )
    expected_source = "tradingagents-service" if use_tradingagents else "analysis_context"
    name = "coordinator_tradingagents" if use_tradingagents else "coordinator_default"
    if data.get("data_source") != expected_source:
        return CheckResult(
            name,
            False,
            f"data_source={data.get('data_source')}; expected={expected_source}",
        )
    signal = data.get("final_signal") or data.get("action")
    return CheckResult(name, True, f"{symbol}: signal={signal}, source={expected_source}")


def run(args: argparse.Namespace) -> int:
    client = SmokeClient(args.base_url, args.timeout)
    started = time.perf_counter()
    checks = [
        ("system_health", lambda: check_health(client)),
        ("backfill_status", lambda: check_backfill(client)),
        ("l5_signals", lambda: check_signal(client, args.symbol, args.interval, args.limit)),
        ("coordinator_default", lambda: check_coordinator(client, args.symbol, args.interval, False)),
        ("coordinator_tradingagents", lambda: check_coordinator(client, args.symbol, args.interval, True)),
    ]

    results: list[CheckResult] = []
    for _, check in checks:
        try:
            results.append(check())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            results.append(CheckResult(checks[len(results)][0], False, str(exc)))

    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")

    elapsed = time.perf_counter() - started
    passed = all(result.ok for result in results)
    print(f"\nPRD 10.4 smoke {'passed' if passed else 'failed'} in {elapsed:.1f}s")
    return 0 if passed else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the PRD 10.4 integration path.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
