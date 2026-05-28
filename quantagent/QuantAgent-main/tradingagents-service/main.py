"""Isolated TradingAgents service.

This service intentionally lives outside the main backend environment because
TradingAgents currently requires pandas 3.x while OpenBB is verified in the
main backend with pandas 2.x. The API accepts the PRD AnalysisContext built by
the main backend, preserving OpenBB as the unified data entry.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(title="QuantAgent TradingAgents Service")


class AnalyzeRequest(BaseModel):
    symbol: str
    interval: str = "1h"
    analysis_context: Dict[str, Any] = Field(default_factory=dict)
    fast: bool = False


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
    from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: F401

    _TA_GRAPH_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on optional runtime deps
    _TA_IMPORT_ERROR = str(exc)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "tradingagents-service",
        "tradingagents_available": _TA_GRAPH_AVAILABLE,
        "tradingagents_error": _TA_IMPORT_ERROR,
        "mode": os.getenv("TRADINGAGENTS_MODE", "context_adapter"),
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

    return AnalyzeResponse(
        status="ok",
        symbol=req.symbol,
        decision=decision,
        confidence=round(confidence, 3),
        reasoning=(
            f"Isolated TradingAgents service decision={decision}; "
            f"vote={vote}; risk_flagged={risk_flagged}; "
            f"library_available={_TA_GRAPH_AVAILABLE}"
        ),
        analyst_reports=reports,
        vote_breakdown=vote,
        risk_flagged=risk_flagged,
        raw={
            "mode": os.getenv("TRADINGAGENTS_MODE", "context_adapter"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tradingagents_available": _TA_GRAPH_AVAILABLE,
            "input_snapshot_ids": ctx.get("input_snapshot_ids") or {},
        },
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


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
