"""Isolated TradingAgents service.

This service intentionally lives outside the main backend environment because
TradingAgents currently requires pandas 3.x while OpenBB is verified in the
main backend with pandas 2.x. The API accepts the PRD AnalysisContext built by
the main backend, preserving OpenBB as the unified data entry.
"""

from __future__ import annotations

import asyncio
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(title="QuantAgent TradingAgents Service")


class AnalyzeRequest(BaseModel):
    symbol: str
    interval: str = "1h"
    analysis_context: Dict[str, Any] = Field(default_factory=dict)
    fast: bool = False
    trade_date: Optional[str] = None
    selected_analysts: Optional[List[str]] = None


class AnalyzeResponse(BaseModel):
    status: str
    symbol: str
    decision: str = "WAIT"
    confidence: float = 0.0
    reasoning: str = ""
    analyst_reports: List[Dict[str, Any]] = Field(default_factory=list)
    vote_breakdown: Dict[str, float] = Field(default_factory=dict)
    risk_flagged: bool = False
    raw: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


_TA_IMPORT_ERROR: Optional[str] = None
_TA_GRAPH_AVAILABLE = False

try:
    from tradingagents.config import TradingAgentsConfig
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    _TA_GRAPH_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on optional runtime deps
    TradingAgentsConfig = None  # type: ignore[assignment]
    TradingAgentsGraph = None  # type: ignore[assignment]
    _TA_IMPORT_ERROR = str(exc)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "tradingagents-service",
        "tradingagents_available": _TA_GRAPH_AVAILABLE,
        "tradingagents_error": _TA_IMPORT_ERROR,
        "mode": os.getenv("TRADINGAGENTS_MODE", "context_adapter"),
        "llm_provider": _llm_provider(),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "openai_base_url": _openai_base_url(),
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "ollama_enabled": _ollama_enabled(),
        "ollama_model": os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"),
        "native_graph": _native_preview(),
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """Analyze a main-backend AnalysisContext.

    The first implementation is a deterministic context adapter that preserves
    the service boundary and response contract. It can be replaced internally
    with a native TradingAgentsGraph call without changing the main backend.
    """
    ctx = req.analysis_context or {}
    signals = ctx.get("recent_signals") or []
    macro = ctx.get("macro_events") or []
    news = ctx.get("news_events") or []
    factors = ctx.get("latest_factors") or {}

    bullish = 0.0
    bearish = 0.0
    neutral = 0.0
    confidence_samples: List[float] = []

    for signal in signals[:20]:
        value = str(signal.get("signal_type") or "").upper()
        confidence = _safe_float(signal.get("confidence"), 0.5)
        confidence_samples.append(confidence)
        if value in {"BUY", "LONG", "LONG_REVERSAL"}:
            bullish += confidence
        elif value in {"SELL", "SHORT", "SHORT_REVERSAL"}:
            bearish += confidence
        else:
            neutral += confidence

    macro_bias = _macro_bias(macro)
    news_bias = _news_bias(news)
    risk_flagged = _risk_flag(factors, news_bias, macro_bias)

    bullish += max(0.0, macro_bias) + max(0.0, news_bias)
    bearish += max(0.0, -macro_bias) + max(0.0, -news_bias)
    neutral += 0.5 if not signals else 0.0

    total = bullish + bearish + neutral
    if total <= 0:
        vote = {"bullish": 0.0, "bearish": 0.0, "neutral": 1.0}
    else:
        vote = {
            "bullish": round(bullish / total, 3),
            "bearish": round(bearish / total, 3),
            "neutral": round(neutral / total, 3),
        }

    if risk_flagged:
        decision = "WAIT"
    elif vote["bullish"] > vote["bearish"] and vote["bullish"] >= 0.45:
        decision = "BUY"
    elif vote["bearish"] > vote["bullish"] and vote["bearish"] >= 0.45:
        decision = "SELL"
    else:
        decision = "WAIT"

    confidence = max(vote.values())
    if confidence_samples:
        confidence = min(0.95, max(confidence, sum(confidence_samples) / len(confidence_samples)))

    reports = [
        {
            "role": "tradingagents_context_adapter",
            "opinion": decision.lower(),
            "confidence": round(confidence, 3),
            "risk_flag": risk_flagged,
            "reasoning": "TradingAgents isolated service consumed the PRD AnalysisContext from the main OpenBB backend.",
            "key_points": [
                f"signals={len(signals)}",
                f"macro_events={len(macro)}",
                f"news_events={len(news)}",
                f"tradingagents_library_available={_TA_GRAPH_AVAILABLE}",
            ],
        }
    ]

    llm_raw: Optional[Dict[str, Any]] = None
    llm_error: Optional[str] = None
    llm_provider = _llm_provider()
    if llm_provider != "none":
        try:
            if llm_provider == "openai":
                llm_raw = await _call_openai(req, ctx, vote, decision, confidence, risk_flagged)
            elif llm_provider == "ollama" and _ollama_enabled():
                llm_raw = await _call_ollama(req, ctx, vote, decision, confidence, risk_flagged)

            if llm_raw:
                decision = _normalize_decision(llm_raw.get("decision"), decision)
                confidence = _clamp(_safe_float(llm_raw.get("confidence"), confidence), 0.0, 0.95)
                risk_flagged = bool(llm_raw.get("risk_flagged", risk_flagged))
                vote = _normalize_vote(llm_raw.get("vote_breakdown"), vote)
                key_points = llm_raw.get("key_points")
                if not isinstance(key_points, list):
                    key_points = []
                reports.insert(0, {
                    "role": f"tradingagents_{llm_provider}_decision",
                    "opinion": decision.lower(),
                    "confidence": round(confidence, 3),
                    "risk_flag": risk_flagged,
                    "reasoning": str(llm_raw.get("reasoning") or f"{llm_provider} refined the TradingAgents context decision."),
                    "key_points": [str(point) for point in key_points[:6]],
                })
        except Exception as exc:  # pragma: no cover - network/runtime fallback
            llm_error = str(exc)[:300]

    reasoning = (
        str(llm_raw.get("reasoning"))
        if llm_raw and llm_raw.get("reasoning")
        else (
            f"Isolated TradingAgents service decision={decision}; "
            f"vote={vote}; risk_flagged={risk_flagged}; "
            f"library_available={_TA_GRAPH_AVAILABLE}"
        )
    )

    return AnalyzeResponse(
        status="ok",
        symbol=req.symbol,
        decision=decision,
        confidence=round(confidence, 3),
        reasoning=reasoning,
        analyst_reports=reports,
        vote_breakdown=vote,
        risk_flagged=risk_flagged,
        raw={
            "mode": os.getenv("TRADINGAGENTS_MODE", "context_adapter"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tradingagents_available": _TA_GRAPH_AVAILABLE,
            "llm_provider": llm_provider,
            "llm_used": bool(llm_raw),
            "llm_error": llm_error,
            "openai_base_url": _openai_base_url(),
            "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "ollama_enabled": _ollama_enabled(),
            "ollama_model": os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"),
            "input_snapshot_ids": ctx.get("input_snapshot_ids") or {},
        },
    )


@app.get("/native/preview/{symbol}")
async def native_preview(symbol: str, interval: str = "1h") -> Dict[str, Any]:
    """Preview how the native upstream TradingAgentsGraph would run.

    This endpoint is intentionally cheap: it does not call any LLM or external
    market-data tool. It exists so the main app can show the original Graph as
    an isolated, manual environment without accidentally spending tokens.
    """
    preview = _native_preview(symbol=symbol, interval=interval)
    return {
        "status": "ok" if preview["available"] else "error",
        **preview,
    }


@app.post("/native/analyze", response_model=AnalyzeResponse)
async def analyze_native(req: AnalyzeRequest) -> AnalyzeResponse:
    """Run the upstream TradingAgentsGraph in the isolated service.

    Native graph execution is a manual/experimental path. It uses upstream
    TradingAgents tools, which are stock/yfinance-oriented, so it should not be
    confused with QuantAgent's crypto-first OpenBB/CCXT AnalysisContext path.
    """
    if not _TA_GRAPH_AVAILABLE or TradingAgentsGraph is None or TradingAgentsConfig is None:
        return AnalyzeResponse(
            status="error",
            symbol=req.symbol,
            error=f"Native TradingAgentsGraph is unavailable: {_TA_IMPORT_ERROR}",
            raw={"mode": "native_graph", "tradingagents_available": _TA_GRAPH_AVAILABLE},
        )

    native_provider = _native_llm_provider()
    if native_provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return AnalyzeResponse(
            status="error",
            symbol=req.symbol,
            error="OPENAI_API_KEY is required for native TradingAgentsGraph with provider=openai",
            raw=_native_preview(symbol=req.symbol, interval=req.interval),
        )

    try:
        return await asyncio.to_thread(_run_native_graph, req)
    except Exception as exc:  # pragma: no cover - depends on LLM/network/yfinance
        return AnalyzeResponse(
            status="error",
            symbol=req.symbol,
            error=str(exc)[:500],
            raw={
                **_native_preview(symbol=req.symbol, interval=req.interval),
                "mode": "native_graph",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _native_preview(symbol: str = "BTCUSDT", interval: str = "1h") -> Dict[str, Any]:
    provider = _native_llm_provider()
    quick_model = _native_model("TRADINGAGENTS_NATIVE_QUICK_MODEL")
    deep_model = _native_model("TRADINGAGENTS_NATIVE_DEEP_MODEL")
    native_symbol = _to_native_tradingagents_symbol(symbol)
    return {
        "available": _TA_GRAPH_AVAILABLE,
        "import_error": _TA_IMPORT_ERROR,
        "mode": "native_graph",
        "manual_only": True,
        "symbol": symbol,
        "native_symbol": native_symbol,
        "interval_note": f"Upstream TradingAgentsGraph runs by trade_date, not intraday interval={interval}.",
        "trade_date": _default_trade_date(None),
        "selected_analysts": _native_selected_analysts(None),
        "llm_provider": provider,
        "quick_model": quick_model,
        "deep_model": deep_model,
        "response_language": os.getenv("TRADINGAGENTS_NATIVE_RESPONSE_LANGUAGE", "zh-CN"),
        "disable_reasoning_effort": _native_disable_reasoning_effort(),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "openai_base_url": _openai_base_url(),
        "data_source_note": (
            "Native upstream TradingAgentsGraph uses its own yfinance/Google News RSS "
            "tool chain. It does not consume QuantAgent OpenBB/CCXT AnalysisContext."
        ),
        "crypto_note": (
            "Crypto symbols are mapped for yfinance where possible, e.g. BTCUSDT -> BTC-USD. "
            "The fundamentals analyst is stock-oriented, so crypto results should be treated as comparison-only."
        ),
    }


def _run_native_graph(req: AnalyzeRequest) -> AnalyzeResponse:
    _prepare_native_llm_environment()

    provider = _native_llm_provider()
    trade_date = _default_trade_date(req.trade_date)
    native_symbol = _to_native_tradingagents_symbol(req.symbol)
    selected_analysts = _native_selected_analysts(req.selected_analysts)

    config = TradingAgentsConfig(  # type: ignore[misc]
        results_dir=Path(os.getenv("TRADINGAGENTS_NATIVE_RESULTS_DIR", "/tmp/tradingagents-native-results")),
        llm_provider=provider,
        deep_think_llm=_native_model("TRADINGAGENTS_NATIVE_DEEP_MODEL"),
        quick_think_llm=_native_model("TRADINGAGENTS_NATIVE_QUICK_MODEL"),
        reasoning_effort=os.getenv("TRADINGAGENTS_NATIVE_REASONING_EFFORT", "low"),
        response_language=os.getenv("TRADINGAGENTS_NATIVE_RESPONSE_LANGUAGE", "zh-CN"),
        max_debate_rounds=_safe_int(os.getenv("TRADINGAGENTS_NATIVE_MAX_DEBATE_ROUNDS"), 1),
        max_risk_discuss_rounds=_safe_int(os.getenv("TRADINGAGENTS_NATIVE_MAX_RISK_ROUNDS"), 1),
        max_recur_limit=max(30, _safe_int(os.getenv("TRADINGAGENTS_NATIVE_MAX_RECUR_LIMIT"), 60)),
    )

    graph = TradingAgentsGraph(  # type: ignore[operator]
        selected_analysts=selected_analysts,
        debug=os.getenv("TRADINGAGENTS_NATIVE_DEBUG", "false").lower() in {"1", "true", "yes", "on"},
        config=config,
    )
    state, recommendation = graph.propagate(native_symbol, trade_date)
    rec = recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else {}
    signal = str(rec.get("signal") or "HOLD").upper()
    decision = "WAIT" if signal == "HOLD" else _normalize_decision(signal, "WAIT")
    confidence = _clamp(_safe_float(rec.get("confidence"), 0.5), 0.0, 0.95)
    reports = _native_reports_from_state(state, decision, confidence)
    reasoning = str(rec.get("rationale") or getattr(state, "final_trade_decision", "") or "").strip()
    if not reasoning:
        reasoning = "原版 TradingAgentsGraph 已完成，但没有返回明确中文解释。"

    return AnalyzeResponse(
        status="ok",
        symbol=req.symbol,
        decision=decision,
        confidence=round(confidence, 3),
        reasoning=_trim_text(reasoning, 1200),
        analyst_reports=reports,
        vote_breakdown=_vote_from_decision(decision),
        risk_flagged=bool(rec.get("warning_message")),
        raw={
            **_native_preview(symbol=req.symbol, interval=req.interval),
            "mode": "native_graph",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "native_symbol": native_symbol,
            "trade_date": trade_date,
            "selected_analysts": selected_analysts,
            "recommendation": rec,
            "warning_message": rec.get("warning_message"),
        },
    )


def _native_selected_analysts(value: Optional[List[str]]) -> List[str]:
    raw = value or [
        part.strip()
        for part in os.getenv("TRADINGAGENTS_NATIVE_ANALYSTS", "market,news").split(",")
        if part.strip()
    ]
    allowed = {"market", "social", "news", "fundamentals"}
    analysts = [item for item in raw if item in allowed]
    return analysts or ["market", "news"]


def _native_llm_provider() -> str:
    allowed = {"openai", "anthropic", "google_genai", "xai", "huggingface", "openrouter", "ollama", "litellm"}
    provider = os.getenv(
        "TRADINGAGENTS_NATIVE_LLM_PROVIDER",
        os.getenv("TRADINGAGENTS_LLM_PROVIDER", "openai"),
    ).strip().lower()
    return provider if provider in allowed else "openai"


def _native_model(env_name: str) -> str:
    return os.getenv(env_name, os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip() or "gpt-4o-mini"


def _prepare_native_llm_environment() -> None:
    if _native_llm_provider() == "openai":
        base_url = _openai_base_url()
        if not os.getenv("OPENAI_API_BASE"):
            os.environ["OPENAI_API_BASE"] = base_url
        if not os.getenv("OPENAI_BASE_URL"):
            os.environ["OPENAI_BASE_URL"] = base_url
    _patch_native_reasoning_effort()


def _native_disable_reasoning_effort() -> bool:
    return os.getenv("TRADINGAGENTS_NATIVE_DISABLE_REASONING_EFFORT", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _patch_native_reasoning_effort() -> None:
    if not _native_disable_reasoning_effort():
        return
    try:
        import tradingagents.llm as ta_llm
    except Exception:
        return
    if getattr(ta_llm, "_quantagent_reasoning_patch", False):
        return

    original_apply_reasoning = ta_llm._apply_reasoning

    def _apply_reasoning_without_openai_compat(provider: str, effort: str, kwargs: Dict[str, Any]) -> None:
        if provider == "openai":
            return
        original_apply_reasoning(provider, effort, kwargs)

    ta_llm._apply_reasoning = _apply_reasoning_without_openai_compat
    ta_llm._quantagent_reasoning_patch = True


def _default_trade_date(value: Optional[str]) -> str:
    if value:
        return value
    return datetime.now(timezone.utc).date().isoformat()


def _to_native_tradingagents_symbol(symbol: str) -> str:
    raw = (symbol or "").strip().upper().replace("/", "").replace("_", "").replace("-", "")
    if not raw:
        return "BTC-USD"
    if raw.endswith("USDT"):
        return f"{raw[:-4]}-USD"
    if raw.endswith("USDC"):
        return f"{raw[:-4]}-USD"
    if raw.endswith("USD") and len(raw) > 3:
        return f"{raw[:-3]}-USD"
    return symbol.strip().upper()


def _native_reports_from_state(state: Any, decision: str, confidence: float) -> List[Dict[str, Any]]:
    fields = [
        ("tradingagents_native_market", "原版市场分析", getattr(state, "market_report", "")),
        ("tradingagents_native_sentiment", "原版情绪分析", getattr(state, "sentiment_report", "")),
        ("tradingagents_native_news", "原版新闻分析", getattr(state, "news_report", "")),
        ("tradingagents_native_fundamentals", "原版基本面分析", getattr(state, "fundamentals_report", "")),
        ("tradingagents_native_situation", "原版情景摘要", getattr(state, "situation_summary", "")),
        ("tradingagents_native_trader", "原版交易员计划", getattr(state, "trader_investment_plan", "")),
        ("tradingagents_native_final_judge", "原版最终裁决", getattr(state, "final_trade_decision", "")),
    ]
    reports: List[Dict[str, Any]] = []
    for role, label, content in fields:
        text = _trim_text(str(content or "").strip(), 900)
        if not text:
            continue
        reports.append(
            {
                "role": role,
                "opinion": decision.lower(),
                "confidence": round(confidence, 3),
                "risk_flag": role == "tradingagents_native_final_judge" and decision == "WAIT",
                "reasoning": text,
                "key_points": [
                    label,
                    "来源：原版 TradingAgentsGraph",
                    "工具链：yfinance / Google News RSS",
                ],
            }
        )
    return reports


def _trim_text(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3]}..."


def _vote_from_decision(decision: str) -> Dict[str, float]:
    if decision == "BUY":
        return {"bullish": 1.0, "bearish": 0.0, "neutral": 0.0}
    if decision == "SELL":
        return {"bullish": 0.0, "bearish": 1.0, "neutral": 0.0}
    return {"bullish": 0.0, "bearish": 0.0, "neutral": 1.0}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ollama_enabled() -> bool:
    return os.getenv("TRADINGAGENTS_USE_OLLAMA", "true").strip().lower() in {"1", "true", "yes", "on"}


def _llm_provider() -> str:
    provider = os.getenv("TRADINGAGENTS_LLM_PROVIDER", "openai").strip().lower()
    return provider if provider in {"openai", "ollama", "none"} else "none"


def _openai_base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")


def _openai_chat_completions_url() -> str:
    base_url = _openai_base_url()
    if base_url.endswith("/chat/completions"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


def _normalize_decision(value: Any, fallback: str) -> str:
    decision = str(value or "").upper()
    return decision if decision in {"BUY", "SELL", "WAIT"} else fallback


def _normalize_vote(value: Any, fallback: Dict[str, float]) -> Dict[str, float]:
    if not isinstance(value, dict):
        return fallback
    vote = {
        "bullish": _clamp(_safe_float(value.get("bullish"), fallback.get("bullish", 0.0)), 0.0, 1.0),
        "bearish": _clamp(_safe_float(value.get("bearish"), fallback.get("bearish", 0.0)), 0.0, 1.0),
        "neutral": _clamp(_safe_float(value.get("neutral"), fallback.get("neutral", 0.0)), 0.0, 1.0),
    }
    total = sum(vote.values())
    if total <= 0:
        return fallback
    return {key: round(val / total, 3) for key, val in vote.items()}


async def _call_openai(
    req: AnalyzeRequest,
    ctx: Dict[str, Any],
    vote: Dict[str, float],
    decision: str,
    confidence: float,
    risk_flagged: bool,
) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    timeout = _safe_float(os.getenv("TRADINGAGENTS_OPENAI_TIMEOUT_SECONDS"), 60.0)
    prompt = _build_llm_prompt(req, ctx, vote, decision, confidence, risk_flagged)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are QuantAgent TradingAgents final decision engine. Return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout, trust_env=True) as client:
        response = await client.post(_openai_chat_completions_url(), json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()

    choices = body.get("choices") or []
    if not choices:
        raise ValueError("OpenAI returned no choices")
    message = choices[0].get("message") or {}
    raw_text = str(message.get("content") or "").strip()
    if not raw_text:
        raise ValueError("OpenAI returned an empty message")
    return _parse_json_object(raw_text, "OpenAI")


async def _call_ollama(
    req: AnalyzeRequest,
    ctx: Dict[str, Any],
    vote: Dict[str, float],
    decision: str,
    confidence: float,
    risk_flagged: bool,
) -> Dict[str, Any]:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
    timeout = _safe_float(os.getenv("TRADINGAGENTS_OLLAMA_TIMEOUT_SECONDS"), 45.0)
    prompt = _build_llm_prompt(req, ctx, vote, decision, confidence, risk_flagged)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 700,
        },
    }

    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        response = await client.post(f"{base_url}/api/generate", json=payload)
        response.raise_for_status()
        body = response.json()

    raw_text = str(body.get("response") or "").strip()
    if not raw_text:
        raise ValueError("Ollama returned an empty response")
    return _parse_json_object(raw_text, "Ollama")


def _parse_json_object(raw_text: str, provider: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(raw_text[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError(f"{provider} response was not a JSON object")
    return parsed


def _build_llm_prompt(
    req: AnalyzeRequest,
    ctx: Dict[str, Any],
    vote: Dict[str, float],
    decision: str,
    confidence: float,
    risk_flagged: bool,
) -> str:
    compact_context = {
        "symbol": req.symbol,
        "interval": req.interval,
        "deterministic_baseline": {
            "decision": decision,
            "reference_confidence": round(confidence, 3),
            "vote_breakdown": vote,
            "risk_flagged": risk_flagged,
            "note": "Reference score from deterministic context adapter. Do not copy it as your final confidence.",
        },
        "recent_signals": (ctx.get("recent_signals") or [])[:12],
        "latest_factors": ctx.get("latest_factors") or {},
        "macro_events": (ctx.get("macro_events") or [])[:8],
        "news_events": (ctx.get("news_events") or [])[:8],
        "market_snapshot": ctx.get("market_snapshot") or {},
    }
    return (
        "You are the LLM decision brain inside QuantAgent TradingAgents. "
        "Use the provided trading context to produce a cautious, structured trading decision. "
        "The deterministic_baseline is only a reference and a fallback; do NOT simply copy its reference_confidence. "
        "Set confidence from your own evidence assessment: mixed/unclear evidence should usually be 0.45-0.70, "
        "strong confluence can be 0.70-0.90, and use 0.90+ only for unusually clear evidence. "
        "Use two decimal places for confidence. Do not invent missing prices or news. "
        "Return ONLY valid JSON with this schema: "
        "{\"decision\":\"BUY|SELL|WAIT\",\"confidence\":0.0,"
        "\"reasoning\":\"short Chinese explanation\",\"risk_flagged\":false,"
        "\"vote_breakdown\":{\"bullish\":0.0,\"bearish\":0.0,\"neutral\":1.0},"
        "\"key_points\":[\"point\"]}.\n\n"
        f"Context:\n{json.dumps(compact_context, ensure_ascii=False, default=str)}"
    )


def _macro_bias(events: List[Dict[str, Any]]) -> float:
    bias = 0.0
    for event in events[:20]:
        indicator = str(event.get("indicator") or "").lower()
        value = _safe_float(event.get("value"))
        if indicator in {"fed_funds_rate", "treasury_10y"} and value >= 4.0:
            bias -= 0.2
        elif indicator in {"m2_money_supply"} and value > 0:
            bias += 0.1
        elif indicator in {"inflation_expect", "cpi"} and value >= 3.0:
            bias -= 0.1
    return max(-1.0, min(1.0, bias))


def _news_bias(events: List[Dict[str, Any]]) -> float:
    scores = [_safe_float(event.get("sentiment_score")) for event in events[:20]]
    if not scores:
        return 0.0
    avg = sum(scores) / len(scores)
    return max(-1.0, min(1.0, avg))


def _risk_flag(factors: Dict[str, Any], news_bias: float, macro_bias: float) -> bool:
    atr = _safe_float(factors.get("atr_14"))
    close = _safe_float(factors.get("close") or factors.get("last_close"))
    atr_ratio = atr / close if close > 0 else 0.0
    return atr_ratio > 0.08 or news_bias < -0.4 or macro_bias < -0.6
