"""
TradingAgents Adapter — L6 multi-round debate decision layer.

Wraps the ``tradingagents`` library's LangGraph-based multi-agent framework
and maps its output to the existing ``CoordinationResult`` dataclass.

Architecture (5 stages, 13+ agents):
  1. Analyst Team (parallel): Fundamentals, Sentiment, News, Technical
  2. Research Team: Bull vs Bear researcher debate (configurable rounds)
  3. Trading Agent: Position sizing and execution strategy
  4. Risk Agent: Aggressive/Conservative/Neutral perspectives
  5. Portfolio Manager: Final capital allocation decision

Graceful degradation:
  - If ``tradingagents`` is not installed, ``available = False``.
  - ``CoordinatorAgent`` falls back to existing 3-agent parallel voting.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.agents.base_agent import SignalType

logger = logging.getLogger(__name__)

# ── Lazy import of tradingagents ────────────────────────────────────────────────

_TA_GRAPH = None
_TA_AVAILABLE = False


def _try_import_tradingagents() -> bool:
    """Attempt to import TradingAgentsGraph. Returns True on success."""
    global _TA_GRAPH, _TA_AVAILABLE
    if _TA_GRAPH is not None:
        return _TA_AVAILABLE
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        _TA_GRAPH = TradingAgentsGraph
        _TA_AVAILABLE = True
        logger.info("TradingAgents library loaded successfully")
        return True
    except ImportError:
        _TA_AVAILABLE = False
        logger.warning(
            "TradingAgents library not installed. "
            "L6 will use existing CoordinatorAgent (3-agent parallel voting). "
            "Install with: pip install tradingagents"
        )
        return False


# ── Adapter class ───────────────────────────────────────────────────────────────


class TradingAgentsAdapter:
    """Adapter wrapping TradingAgentsGraph's multi-stage debate.

    Maps its output (decision, confidence, reasoning) to the existing
    ``CoordinationResult`` format so the downstream execution layer
    is unchanged regardless of which L6 implementation is active.
    """

    available: bool = _TA_AVAILABLE

    def __init__(
        self,
        quick_think_llm: str = "gpt-4o-mini",
        deep_think_llm: str = "gpt-4o",
        max_debate_rounds: int = 2,
        enable_chinese_llm: bool = False,
    ):
        self.quick_think_llm = quick_think_llm
        self.deep_think_llm = deep_think_llm
        self.max_debate_rounds = max_debate_rounds
        self.graph: Optional[Any] = None
        self._initialized = False

        if not _try_import_tradingagents():
            return

        try:
            self._init_graph(enable_chinese_llm)
        except Exception as e:
            logger.error(f"TradingAgentsGraph init failed: {e}")
            self.graph = None

    def _init_graph(self, enable_chinese_llm: bool = False):
        """Build the TradingAgents graph with LLM configuration."""
        config: Dict[str, Any] = {
            "quick_think_llm": self.quick_think_llm,
            "deep_think_llm": self.deep_think_llm,
            "max_debate_rounds": self.max_debate_rounds,
            "online_tools": False,  # Use our own data pipeline
        }

        if enable_chinese_llm:
            from app.core.config import settings

            dashscope_key = getattr(settings, "DASHSCOPE_API_KEY", None) or ""
            if dashscope_key:
                import os
                os.environ["DASHSCOPE_API_KEY"] = dashscope_key
            config.update(
                {
                    "llm_provider": "dashscope",
                    "deep_think_llm": "qwen-max",
                    "quick_think_llm": "qwen-plus",
                }
            )

        self.graph = _TA_GRAPH(config=config, debug=False)
        self._initialized = True
        logger.info(
            f"TradingAgentsGraph initialized "
            f"(quick={config['quick_think_llm']}, deep={config['deep_think_llm']})"
        )

    # ── Main entry point ───────────────────────────────────────────────────

    async def run_analysis(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None,
        signal_events: Optional[List[Dict[str, Any]]] = None,
        macro_context: Optional[Dict[str, Any]] = None,
    ) -> Optional["CoordinationResult"]:
        """Run the full TradingAgents pipeline.

        Returns ``CoordinationResult`` on success, ``None`` if unavailable.
        Callers should fall back to CoordinatorAgent on None.
        """
        from app.agents.coordinator_agent import CoordinationResult

        if not _TA_AVAILABLE or self.graph is None:
            return None

        try:
            analysis_input = {
                "symbol": symbol,
                "market_data": market_data or {},
                "signals": signal_events or [],
                "macro": macro_context or {},
                "timestamp": datetime.utcnow().isoformat(),
            }

            # TradingAgentsGraph.invoke() returns a dict
            # Expected keys: decision, confidence, reasoning, analyst_reports
            raw = await self._invoke_graph(analysis_input)

            if raw is None:
                return None

            return self._map_to_result(symbol, raw)

        except Exception as e:
            logger.error(f"TradingAgents analysis failed: {e}", exc_info=True)
            return None

    async def _invoke_graph(self, inputs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Invoke the TradingAgents graph (sync wrapper in thread pool)."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.graph.invoke, inputs)

    # ── Output mapping ─────────────────────────────────────────────────────

    def _map_to_result(
        self, symbol: str, raw: Dict[str, Any]
    ) -> "CoordinationResult":
        """Convert TradingAgents output to CoordinationResult."""
        from app.agents.coordinator_agent import CoordinationResult

        decision = str(raw.get("decision", "HOLD")).upper()

        signal_map = {
            "BUY": SignalType.BUY,
            "SELL": SignalType.SELL,
            "HOLD": SignalType.WAIT,
            "WAIT": SignalType.WAIT,
        }
        final_signal = signal_map.get(decision, SignalType.WAIT)

        analyst_reports = raw.get("analyst_reports", [])
        if not isinstance(analyst_reports, list):
            analyst_reports = [analyst_reports] if analyst_reports else []

        risk_flagged = raw.get("risk_flagged", False)

        return CoordinationResult(
            symbol=symbol,
            final_signal=final_signal,
            confidence=float(raw.get("confidence", 0.5)),
            summary=str(raw.get("reasoning", "TradingAgents analysis completed")),
            agent_signals=analyst_reports,
            vote_breakdown={"tradingagents": float(raw.get("confidence", 0.5))},
            risk_veto=decision == "HOLD" and risk_flagged,
            timestamp=datetime.utcnow(),
        )


# ── Module-level singleton ─────────────────────────────────────────────────────

tradingagents_adapter = TradingAgentsAdapter()
