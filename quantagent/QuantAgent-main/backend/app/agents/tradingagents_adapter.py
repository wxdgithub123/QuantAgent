"""HTTP adapter for the isolated TradingAgents service.

TradingAgents is intentionally not imported in the main backend. Its current
dependency tree can require pandas 3.x, while the OpenBB data-entry backend is
kept on the verified pandas 2.x stack. This adapter preserves that boundary:
the backend builds the PRD AnalysisContext, sends it to the isolated service,
and maps the response back to the existing CoordinationResult contract.
"""

from __future__ import annotations

import hashlib
import json
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


def _truncate_text(value: Any, max_chars: int = 700) -> Any:
    if not isinstance(value, str):
        return value
    return value if len(value) <= max_chars else value[:max_chars] + "..."


def _json_size_bytes(value: Dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


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

        Returns ``None`` on service failure; CoordinatorAgent treats that as
        a failed external decision when ``use_tradingagents`` is enabled.
        """
        from app.agents.coordinator_agent import CoordinationResult

        compact_context = self._compact_analysis_context(
            analysis_context or {},
            symbol=symbol,
            interval=interval,
        )
        payload = {
            "symbol": symbol,
            "interval": interval,
            "analysis_context": compact_context,
            "fast": fast,
        }

        effective_timeout = min(float(self.timeout_seconds), 45.0) if fast else max(float(self.timeout_seconds), 900.0)
        timeout = aiohttp.ClientTimeout(total=effective_timeout)
        url = f"{self.service_url}/analyze"

        try:
            logger.info("[tradingagents] POST %s with compact context", url)
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.post(url, json=payload) as resp:
                    body = await resp.json(content_type=None)
                    if resp.status >= 400:
                        logger.warning("[tradingagents] service returned HTTP %s: %s", resp.status, str(body)[:300])
                        return None
                    if not isinstance(body, dict):
                        logger.warning("[tradingagents] service returned non-object body: %s", type(body).__name__)
                        return None

                    svc_status = str(body.get("status", "")).lower()
                    if svc_status and svc_status not in {"ok", "success", "completed"}:
                        logger.warning("[tradingagents] unexpected status=%s, using response anyway", svc_status)
                    return self._map_to_result(symbol=symbol, raw=body)
        except Exception as exc:
            logger.warning("[tradingagents] service call failed: %s: %r", type(exc).__name__, exc)
            return None

    @staticmethod
    def _compact_analysis_context(
        analysis_context: Dict[str, Any],
        *,
        symbol: str,
        interval: str,
        max_payload_bytes: int = 120_000,
    ) -> Dict[str, Any]:
        """Return a bounded but truthful AnalysisContext for TradingAgents.

        Factors, signals and snapshot metadata are never dropped because they
        are the core decision evidence. When size pressure appears, only
        high-cardinality bars/news/macro collections are trimmed.
        """
        ctx = analysis_context if isinstance(analysis_context, dict) else {}
        bars = ctx.get("bars") if isinstance(ctx.get("bars"), list) else []
        news = ctx.get("news_events") if isinstance(ctx.get("news_events"), list) else []
        macro = ctx.get("macro_events") if isinstance(ctx.get("macro_events"), list) else []

        metadata = ctx.get("metadata") if isinstance(ctx.get("metadata"), dict) else {}
        compact = {
            "symbol": ctx.get("symbol") or symbol,
            "timeframe": ctx.get("timeframe") or interval,
            "as_of_time": ctx.get("as_of_time"),
            "schema_version": ctx.get("schema_version") or "analysis_context.v1",
            "bars": bars[-120:],
            "latest_factors": ctx.get("latest_factors") if isinstance(ctx.get("latest_factors"), dict) else {},
            "recent_signals": ctx.get("recent_signals") if isinstance(ctx.get("recent_signals"), list) else [],
            "news_events": TradingAgentsAdapter._compact_events(news),
            "macro_events": TradingAgentsAdapter._compact_events(macro),
            "input_snapshot_ids": ctx.get("input_snapshot_ids") if isinstance(ctx.get("input_snapshot_ids"), dict) else {},
            "data_versions": ctx.get("data_versions") if isinstance(ctx.get("data_versions"), dict) else {},
            "metadata": metadata,
            "backend_api_url": "http://backend:8000",
        }
        compact["context_hash"] = (
            ctx.get("context_hash")
            or metadata.get("context_hash")
            or TradingAgentsAdapter._analysis_context_hash(compact)
        )

        while _json_size_bytes(compact) > max_payload_bytes:
            if len(compact["bars"]) > 20:
                compact["bars"] = compact["bars"][-max(20, len(compact["bars"]) // 2):]
            elif len(compact["news_events"]) > 5:
                compact["news_events"] = compact["news_events"][:max(5, len(compact["news_events"]) // 2)]
            elif len(compact["macro_events"]) > 5:
                compact["macro_events"] = compact["macro_events"][:max(5, len(compact["macro_events"]) // 2)]
            else:
                logger.warning(
                    "[tradingagents] compact AnalysisContext still large (%d bytes); preserving factors/signals/snapshot ids",
                    _json_size_bytes(compact),
                )
                break
            compact["context_hash"] = (
                ctx.get("context_hash")
                or metadata.get("context_hash")
                or TradingAgentsAdapter._analysis_context_hash(compact)
            )

        return compact

    @staticmethod
    def _compact_events(rows: List[Dict[str, Any]], limit: int = 30) -> List[Dict[str, Any]]:
        compacted: List[Dict[str, Any]] = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            item: Dict[str, Any] = {}
            for key in (
                "id",
                "raw_payload_id",
                "indicator",
                "name",
                "title",
                "summary",
                "sentiment",
                "sentiment_score",
                "value",
                "actual",
                "event_time",
                "timestamp",
                "published_at",
                "available_time",
                "provider",
                "source",
                "schema_version",
                "source_version",
            ):
                if key in row:
                    item[key] = _truncate_text(row.get(key))
            if item:
                compacted.append(item)
        return compacted

    @staticmethod
    def _analysis_context_hash(ctx: Dict[str, Any]) -> str:
        stable = {
            "symbol": ctx.get("symbol"),
            "timeframe": ctx.get("timeframe"),
            "as_of_time": ctx.get("as_of_time"),
            "input_snapshot_ids": ctx.get("input_snapshot_ids"),
            "data_versions": ctx.get("data_versions"),
        }
        digest = hashlib.sha256(
            json.dumps(stable, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        return f"sha256:{digest}"

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
        raw_payload = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
        internal_chain = raw_payload.get("internal_chain")
        if isinstance(internal_chain, list) and len(internal_chain) > len(analyst_reports):
            analyst_reports = [
                {
                    **report,
                    "data_source_chain": report.get("data_source_chain")
                    or "AnalysisContext / OpenBB / CCXT / ClickHouse / L5 因子信号",
                }
                for report in internal_chain
                if isinstance(report, dict)
            ]

        vote_breakdown = raw.get("vote_breakdown") or {"tradingagents": confidence}
        if not isinstance(vote_breakdown, dict):
            vote_breakdown = {"tradingagents": confidence}

        risk_flagged = bool(raw.get("risk_flagged", False))
        position_advice = raw.get("position_advice") if isinstance(raw.get("position_advice"), dict) else {}
        graph_mode = str(raw_payload.get("execution_mode") or raw_payload.get("mode") or "unknown")
        is_full_graph = bool(raw_payload.get("is_full_graph")) or graph_mode in {
            "full_graph",
            "quantagent_patched_graph",
            "quantagent_graph",
            "patched_graph",
            "native_graph",
        }
        strong_acceptance_eligible = bool(raw_payload.get("strong_acceptance_eligible", is_full_graph))
        graph_meta = {
            "graphMode": graph_mode,
            "configuredMode": raw_payload.get("configured_mode") or raw_payload.get("mode"),
            "isFullGraph": is_full_graph,
            "strongAcceptanceEligible": strong_acceptance_eligible,
            "modeNote": raw_payload.get("mode_note"),
            "llmProvider": raw_payload.get("llm_provider"),
            "llmUsed": raw_payload.get("llm_used"),
            "quickModel": raw_payload.get("quick_model"),
            "deepModel": raw_payload.get("deep_model"),
        }
        if isinstance(internal_chain, list):
            position_advice = {
                **position_advice,
                "tradingagents_internal_chain": internal_chain,
            }

        def _join_reasoning(opinions: set[str]) -> str:
            parts = []
            for report in analyst_reports:
                if not isinstance(report, dict):
                    continue
                opinion = str(report.get("opinion") or "").lower()
                if opinion in opinions and report.get("reasoning"):
                    role = str(report.get("role") or "role")
                    parts.append(f"[{role}] {str(report.get('reasoning'))[:700]}")
            return "\n".join(parts)

        bull_view = str(raw.get("bull_view") or _join_reasoning({"buy", "bullish", "long"}))
        bear_view = str(raw.get("bear_view") or _join_reasoning({"sell", "bearish", "short"}))
        if not bull_view:
            bull_view = "未形成独立多头结论；看多依据已汇总在角色分析和投票中。"
        if not bear_view:
            bear_view = "未形成独立空头结论；看空依据已汇总在角色分析和投票中。"

        risk_notes = str(raw.get("risk_notes") or "")
        if not risk_notes:
            if risk_flagged:
                risk_notes = "TradingAgents 标记风险，本次建议保持 WAIT 或降低仓位。"
            elif decision == "WAIT":
                risk_notes = "最终建议为 WAIT：证据不充分或多空分歧，暂不生成实际下单。"
            else:
                risk_notes = "未触发风控否决；仍需按账户风险限额控制仓位。"

        if not position_advice:
            position_advice = {
                "action": decision,
                "position_ratio": 0.0 if decision == "WAIT" else round(min(confidence, 0.5), 3),
                "sizing_note": "WAIT 不建立新仓位。" if decision == "WAIT" else "按置信度和账户风险限额小仓位执行。",
                "risk_note": risk_notes,
            }
        position_advice = {
            **position_advice,
            "_graph_meta": {key: value for key, value in graph_meta.items() if value is not None},
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
            bull_view=bull_view,
            bear_view=bear_view,
            role_opinions=analyst_reports,
            input_snapshot_ids=raw_payload.get("input_snapshot_ids", {}),
            risk_notes=risk_notes,
            position_advice=position_advice,
            graph_mode=graph_mode,
            is_full_graph=is_full_graph,
            strong_acceptance_eligible=strong_acceptance_eligible,
            timestamp=datetime.now(timezone.utc),
        )


tradingagents_adapter = TradingAgentsAdapter()
