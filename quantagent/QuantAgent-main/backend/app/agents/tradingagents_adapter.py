"""HTTP adapter for the isolated TradingAgents service.

TradingAgents is intentionally not imported in the main backend. Its current
dependency tree can require pandas 3.x, while the OpenBB data-entry backend is
kept on the verified pandas 2.x stack. This adapter preserves that boundary:
the backend builds the PRD AnalysisContext, sends it to the isolated service,
and maps the response back to the existing CoordinationResult contract.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from app.agents.base_agent import SignalType
from app.core.config import settings

logger = logging.getLogger(__name__)


def _normalize_decision(value: Any) -> str:
    decision = str(value or "WAIT").upper()
    if decision in {"BUY", "LONG"}:
        return "BUY"
    if decision in {"SELL", "SHORT"}:
        return "SELL"
    return "WAIT"


def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        return float(value)
    except Exception:
        return default


class TradingAgentsAdapter:
    """Remote client for ``tradingagents-service``."""

    available: bool = True

    def __init__(
        self,
        service_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self.service_url = (service_url or settings.TRADINGAGENTS_SERVICE_URL).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.TRADINGAGENTS_TIMEOUT_SECONDS
        )

    async def health(self) -> Dict[str, Any]:
        """Return service health, or an unavailable status when unreachable."""
        url = f"{self.service_url}/health"
        timeout = aiohttp.ClientTimeout(total=min(float(self.timeout_seconds), 10.0))
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.get(url) as resp:
                    data = await resp.json(content_type=None)
                    return {
                        "status": "ok" if resp.status == 200 else "error",
                        "service_url": self.service_url,
                        "http_status": resp.status,
                        "detail": data,
                    }
        except Exception as exc:
            return {
                "status": "unavailable",
                "service_url": self.service_url,
                "detail": str(exc)[:200],
            }

    async def native_preview(self, symbol: str, interval: str = "1h") -> Dict[str, Any]:
        """Return the native upstream TradingAgentsGraph sandbox preview."""
        url = f"{self.service_url}/native/preview/{symbol}"
        timeout = aiohttp.ClientTimeout(total=min(float(self.timeout_seconds), 10.0))
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.get(url, params={"interval": interval}) as resp:
                    data = await resp.json(content_type=None)
                    return {
                        "status": "ok" if resp.status == 200 else "error",
                        "service_url": self.service_url,
                        "http_status": resp.status,
                        "detail": data,
                    }
        except Exception as exc:
            return {
                "status": "unavailable",
                "service_url": self.service_url,
                "detail": str(exc)[:200],
            }

    async def run_native_graph(
        self,
        symbol: str,
        interval: str = "1h",
        trade_date: Optional[str] = None,
        selected_analysts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run the native upstream TradingAgentsGraph sandbox path."""
        payload = {
            "symbol": symbol,
            "interval": interval,
            "trade_date": trade_date,
            "selected_analysts": selected_analysts or ["market", "news", "social", "fundamentals"],
        }
        url = f"{self.service_url}/native/analyze"
        timeout = aiohttp.ClientTimeout(total=max(float(self.timeout_seconds), 240.0))
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.post(url, json=payload) as resp:
                    body = await resp.json(content_type=None)
                    body["http_status"] = resp.status
                    return body
        except Exception as exc:
            return {
                "status": "error",
                "symbol": symbol,
                "error": str(exc)[:500],
                "raw": {
                    "mode": "native_graph",
                    "service_url": self.service_url,
                },
            }

    async def run_analysis(
        self,
        symbol: str,
        interval: str = "1h",
        analysis_context: Optional[Dict[str, Any]] = None,
        fast: bool = False,
        market_data: Optional[Dict[str, Any]] = None,
        signal_events: Optional[List[Dict[str, Any]]] = None,
        macro_context: Optional[Dict[str, Any]] = None,
    ) -> Optional["CoordinationResult"]:
        """Call the isolated service and map its response.

        Returns ``None`` on any service failure so CoordinatorAgent can fall
        back to the in-process PRD 10.4 decision pipeline.
        """
        from app.agents.coordinator_agent import CoordinationResult

        context = analysis_context or {
            "symbol": symbol,
            "timeframe": interval,
            "market_data": market_data or {},
            "recent_signals": signal_events or [],
            "macro_events": (macro_context or {}).get("macro_events", []),
            "latest_factors": (macro_context or {}).get("latest_factors", {}),
        }
        payload = {
            "symbol": symbol,
            "interval": interval,
            "analysis_context": context,
            "fast": fast,
        }

        url = f"{self.service_url}/analyze"
        timeout = aiohttp.ClientTimeout(total=max(float(self.timeout_seconds), 300.0))
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.post(url, json=payload) as resp:
                    body = await resp.json(content_type=None)
                    if resp.status >= 400:
                        logger.warning(
                            "[tradingagents] service returned HTTP %s: %s",
                            resp.status,
                            str(body)[:300],
                        )
                        return None
        except Exception as exc:
            logger.warning(
                "[tradingagents] service call failed: %s: %r",
                type(exc).__name__,
                exc,
            )
            return None

        if str(body.get("status", "")).lower() not in {"ok", "success"}:
            logger.warning("[tradingagents] service status not ok: %s", body)
            return None

        return self._map_to_result(symbol=symbol, raw=body)

    def _map_to_result(
        self,
        symbol: str,
        raw: Dict[str, Any],
    ) -> "CoordinationResult":
        """Convert service output into the backend coordination contract."""
        from app.agents.coordinator_agent import CoordinationResult

        decision = _normalize_decision(raw.get("decision"))
        signal_map = {
            "BUY": SignalType.BUY,
            "SELL": SignalType.SELL,
            "WAIT": SignalType.WAIT,
        }

        confidence = max(0.0, min(1.0, _safe_float(raw.get("confidence"), 0.5)))
        analyst_reports = raw.get("analyst_reports") or []
        if not isinstance(analyst_reports, list):
            analyst_reports = [analyst_reports]

        vote_breakdown = raw.get("vote_breakdown") or {"tradingagents": confidence}
        if not isinstance(vote_breakdown, dict):
            vote_breakdown = {"tradingagents": confidence}

        risk_flagged = bool(raw.get("risk_flagged", False))
        raw_payload = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
        position_advice = raw.get("position_advice") if isinstance(raw.get("position_advice"), dict) else {}
        internal_chain = raw_payload.get("internal_chain")
        if isinstance(internal_chain, list):
            position_advice = {
                **position_advice,
                "tradingagents_internal_chain": internal_chain,
            }

        return CoordinationResult(
            symbol=symbol,
            final_signal=signal_map[decision],
            confidence=confidence,
            summary=str(raw.get("reasoning") or "TradingAgents service analysis completed"),
            agent_signals=analyst_reports,
            vote_breakdown=vote_breakdown,
            risk_veto=risk_flagged,
            data_source="tradingagents-service",
            role_opinions=analyst_reports,
            input_snapshot_ids=raw_payload.get("input_snapshot_ids", {}),
            risk_notes=str(raw.get("risk_notes") or ""),
            position_advice=position_advice,
            timestamp=datetime.now(timezone.utc),
        )


tradingagents_adapter = TradingAgentsAdapter()
