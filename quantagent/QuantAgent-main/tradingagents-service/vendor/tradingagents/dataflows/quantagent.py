"""QuantAgent AnalysisContext-backed data tools for patched TradingAgentsGraph.

The upstream TradingAgents package is stock-first and normally calls yfinance
and Google News RSS from tool functions. QuantAgent is crypto-first, so this
module lets the original graph consume the platform's point-in-time
AnalysisContext while preserving the original tool names and graph topology.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tradingagents.runtime import get_run_context

_NO_CONTEXT = "[NO_DATA] QuantAgent AnalysisContext is not attached to this TradingAgents run."


def active_analysis_context() -> dict[str, Any] | None:
    context = get_run_context()
    if context is None or not isinstance(context.analysis_context, dict):
        return None
    return context.analysis_context


def has_analysis_context() -> bool:
    return active_analysis_context() is not None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except Exception:
        return str(value)
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _event_time(row: dict[str, Any]) -> str:
    return str(
        row.get("event_time")
        or row.get("timestamp")
        or row.get("available_time")
        or row.get("date")
        or ""
    )

def _latest_bar(ctx: dict[str, Any]) -> dict[str, Any]:
    bars = ctx.get("bars") or []
    return bars[-1] if bars and isinstance(bars[-1], dict) else {}


def quantagent_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    ctx = active_analysis_context()
    if not ctx:
        return _NO_CONTEXT
    bars = [bar for bar in (ctx.get("bars") or []) if isinstance(bar, dict)]
    if not bars:
        return "[NO_DATA] QuantAgent AnalysisContext contains no OHLCV bars."

    lines = [
        f"## QuantAgent OHLCV for {ctx.get('symbol') or symbol}",
        f"Requested window: {start_date} to {end_date}",
        f"Context timeframe: {ctx.get('timeframe')}; as_of_time: {ctx.get('as_of_time')}",
        "Source: QuantAgent AnalysisContext -> ClickHouse market cache; upstream provider is recorded in data_versions.",
        "",
        "timestamp,open,high,low,close,volume,provider,data_source",
    ]
    for bar in bars[-120:]:
        lines.append(
            ",".join(
                [
                    _event_time(bar),
                    _fmt(bar.get("open")),
                    _fmt(bar.get("high")),
                    _fmt(bar.get("low")),
                    _fmt(bar.get("close")),
                    _fmt(bar.get("volume"), 2),
                    str(bar.get("provider") or ""),
                    str(bar.get("data_source") or ""),
                ]
            )
        )
    return "\n".join(lines)


def quantagent_indicators(symbol: str, indicators: list[str], curr_date: str, look_back_days: int) -> str:
    ctx = active_analysis_context()
    if not ctx:
        return _NO_CONTEXT
    factors = ctx.get("latest_factors") or {}
    if not isinstance(factors, dict) or not factors:
        return "[NO_DATA] QuantAgent AnalysisContext contains no latest_factors."

    requested = [item.lower() for item in indicators if item]
    selected: list[tuple[str, Any]] = []
    for key, value in factors.items():
        key_l = str(key).lower()
        if not requested or any(req in key_l or key_l in req for req in requested):
            selected.append((str(key), value))
    if not selected:
        selected = list(factors.items())[:24]

    lines = [
        f"## QuantAgent factor/indicator snapshot for {ctx.get('symbol') or symbol}",
        f"curr_date={curr_date}; look_back_days={look_back_days}; as_of_time={ctx.get('as_of_time')}",
        "Source: factor_snapshots / L5 factor pipeline, generated from platform OHLCV/news/macro context.",
        "",
    ]
    for key, value in selected[:40]:
        lines.append(f"- {key}: {_fmt(value, 6)}")
    return "\n".join(lines)


def quantagent_news(ticker: str, start_date: str, end_date: str, limit: int = 20) -> str:
    ctx = active_analysis_context()
    if not ctx:
        return _NO_CONTEXT
    events = [event for event in (ctx.get("news_events") or []) if isinstance(event, dict)]
    if not events:
        return "[NO_DATA] QuantAgent AnalysisContext contains no news_events."

    lines = [
        f"## QuantAgent crypto news for {ctx.get('symbol') or ticker}",
        f"Requested window: {start_date} to {end_date}; as_of_time={ctx.get('as_of_time')}",
        "Source: QuantAgent news_events, currently populated from OpenBB/yfinance and configured feeds.",
        "",
    ]
    for event in events[:limit]:
        title = event.get("title") or "Untitled"
        source = event.get("source") or event.get("provider") or "unknown"
        published = event.get("published_at") or event.get("event_time") or event.get("available_time") or ""
        sentiment = event.get("sentiment_score")
        lines.append(f"### {title} (source: {source})")
        lines.append(f"Published: {published}")
        if sentiment is not None:
            lines.append(f"Sentiment score: {_fmt(sentiment, 4)}")
        summary = event.get("summary") or event.get("excerpt") or event.get("body") or ""
        if summary:
            lines.append(str(summary)[:800])
        url = event.get("url")
        if url:
            lines.append(f"Link: {url}")
        lines.append("")
    return "\n".join(lines)


def quantagent_global_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    ctx = active_analysis_context()
    if not ctx:
        return _NO_CONTEXT
    macro = [event for event in (ctx.get("macro_events") or []) if isinstance(event, dict)]
    news = [event for event in (ctx.get("news_events") or []) if isinstance(event, dict)]
    lines = [
        "## QuantAgent macro and market-wide context",
        f"curr_date={curr_date}; look_back_days={look_back_days}; as_of_time={ctx.get('as_of_time')}",
        "Source: macro_events from OpenBB/FRED/OECD plus recent crypto market news.",
        "",
    ]
    if macro:
        lines.append("### Macro events")
        for event in macro[:limit]:
            lines.append(
                f"- {event.get('indicator') or 'indicator'}: {_fmt(event.get('value'), 6)} "
                f"at {event.get('event_time') or event.get('timestamp') or event.get('date')}; "
                f"provider={event.get('provider') or event.get('source') or ''}"
            )
    if news:
        lines.append("")
        lines.append("### Market headlines")
        for event in news[:limit]:
            lines.append(f"- {event.get('title') or 'Untitled'} ({event.get('source') or event.get('provider') or 'unknown'})")
    if not macro and not news:
        lines.append("[NO_DATA] No macro_events or news_events available in AnalysisContext.")
    return "\n".join(lines)


def quantagent_market_context(ticker: str, curr_date: str, look_back_days: int = 5) -> str:
    ctx = active_analysis_context()
    if not ctx:
        return _NO_CONTEXT
    bar = _latest_bar(ctx)
    factors = ctx.get("latest_factors") or {}
    signals = [row for row in (ctx.get("recent_signals") or []) if isinstance(row, dict)]
    signal_counts: dict[str, int] = {}
    for signal in signals[:40]:
        key = str(signal.get("signal_type") or "WAIT").upper()
        signal_counts[key] = signal_counts.get(key, 0) + 1
    return "\n".join(
        [
            f"## QuantAgent market context for {ctx.get('symbol') or ticker}",
            f"curr_date={curr_date}; as_of_time={ctx.get('as_of_time')}",
            f"Latest close={_fmt(bar.get('close'))}; high={_fmt(bar.get('high'))}; low={_fmt(bar.get('low'))}; volume={_fmt(bar.get('volume'), 2)}",
            f"Signal counts={signal_counts}",
            "Selected factors:",
            f"- rsi_14={_fmt(factors.get('rsi_14'), 6)}",
            f"- macd_hist={_fmt(factors.get('macd_hist'), 6)}",
            f"- boll_pct_b={_fmt(factors.get('boll_pct_b'), 6)}",
            f"- atr_14={_fmt(factors.get('atr_14'), 6)}",
        ]
    )


def quantagent_fundamentals(ticker: str, curr_date: str) -> str:
    ctx = active_analysis_context()
    if not ctx:
        return _NO_CONTEXT
    factors = ctx.get("latest_factors") or {}
    signals = [row for row in (ctx.get("recent_signals") or []) if isinstance(row, dict)]
    input_ids = ctx.get("input_snapshot_ids") or {}
    metadata = ctx.get("metadata") or {}
    bar = _latest_bar(ctx)
    atr = _safe_float(factors.get("atr_14"))
    close = _safe_float(bar.get("close") or factors.get("close"))
    atr_ratio = atr / close if close > 0 else 0.0
    return "\n".join(
        [
            f"## QuantAgent crypto fundamentals/context report for {ctx.get('symbol') or ticker}",
            "This is a patched crypto-first replacement for the upstream stock fundamentals tool.",
            f"curr_date={curr_date}; as_of_time={ctx.get('as_of_time')}; timeframe={ctx.get('timeframe')}",
            f"Latest close={_fmt(close)}; ATR ratio={_fmt(atr_ratio, 6)}",
            f"Recent signal rows={len(signals)}; factor snapshots={len(input_ids.get('factor_snapshot_ids') or [])}; signal snapshots={len(input_ids.get('signal_event_ids') or [])}",
            f"Point-in-time rule={metadata.get('point_in_time_rule') or metadata.get('rule') or 'available_time <= as_of_time'}",
            "Top factors:",
            *[f"- {key}: {_fmt(value, 6)}" for key, value in list(factors.items())[:24]],
        ]
    )
