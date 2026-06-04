"""
Coordinator Agent — PRD 10.4 TradingAgents Decision Layer.

Consumes AnalysisContext from L5 signal pipeline.
No longer reads raw ClickHouse data or computes indicators directly.

Pipeline:
  1. _load_analysis_context()      → AnalysisContext (bars, factors, signals, news, macro)
  2. 4-role parallel analysis       → RoleOpinion (tech, news, macro, risk)
  3. _bull_bear_debate()            → bull_view / bear_view / final_decision
  4. Vote aggregation + risk veto
  5. LLM final synthesis            → AgentDecision
  6. _persist_result()              → coordination_history (full audit trail)
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import aiohttp

from app.agents.base_agent import AgentSignal, SignalType
from app.agents.trend_agent import TrendAgent
from app.agents.mean_reversion_agent import MeanReversionAgent
from app.agents.risk_agent import RiskAgent
from app.core.config import settings
from app.models.db_models import CoordinationHistoryDB
from app.models.instrument import Instrument
from app.services.llm.base import LLMFactory
from app.services.database import get_db
from sqlalchemy import text as sql_text

logger = logging.getLogger(__name__)

BULLISH_SIGNALS = {SignalType.BUY, SignalType.LONG_REVERSAL}
BEARISH_SIGNALS = {SignalType.SELL, SignalType.SHORT_REVERSAL}

# How many recent coordination decisions to check for duplicates
RECENT_COORD_LIMIT = 5
MIN_COORD_INTERVAL_SECONDS = 60


# ── Structured outputs ──────────────────────────────────────────────────────

@dataclass
class RoleOpinion:
    """Structured output from a single analysis role."""
    role: str                # "technical" | "news" | "macro" | "risk"
    opinion: str             # e.g. "bullish" / "bearish" / "neutral"
    confidence: float        # 0.0 ~ 1.0
    risk_flag: bool          # True if this role flags elevated risk
    reasoning: str           # LLM analysis text
    key_points: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "opinion": self.opinion,
            "confidence": round(self.confidence, 3),
            "risk_flag": self.risk_flag,
            "reasoning": self.reasoning,
            "key_points": self.key_points,
        }


@dataclass
class AgentDecision:
    """PRD 10.4 final structured decision."""
    symbol: str
    action: str              # BUY / SELL / WAIT
    confidence: float
    position_advice: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    risk_notes: str = ""
    bull_view: str = ""
    bear_view: str = ""
    final_decision: str = ""
    role_opinions: List[Dict[str, Any]] = field(default_factory=list)
    vote_breakdown: Dict[str, float] = field(default_factory=dict)
    risk_veto: bool = False
    input_snapshot_ids: Dict[str, Any] = field(default_factory=dict)
    data_source: str = "analysis_context"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "position_advice": self.position_advice,
            "reasoning": self.reasoning,
            "risk_notes": self.risk_notes,
            "bull_view": self.bull_view,
            "bear_view": self.bear_view,
            "final_decision": self.final_decision,
            "role_opinions": self.role_opinions,
            "vote_breakdown": self.vote_breakdown,
            "risk_veto": self.risk_veto,
            "input_snapshot_ids": self.input_snapshot_ids,
            "data_source": self.data_source,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class CoordinationResult:
    """Legacy-compatible output, wraps AgentDecision."""
    symbol: str
    final_signal: SignalType
    confidence: float
    summary: str
    agent_signals: List[Dict[str, Any]] = field(default_factory=list)
    vote_breakdown: Dict[str, float] = field(default_factory=dict)
    risk_veto: bool = False
    data_source: str = "analysis_context"
    # PRD 10.4 fields
    bull_view: str = ""
    bear_view: str = ""
    input_snapshot_ids: Dict[str, Any] = field(default_factory=dict)
    role_opinions: List[Dict[str, Any]] = field(default_factory=list)
    position_advice: Dict[str, Any] = field(default_factory=dict)
    risk_notes: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "final_signal": self.final_signal.value,
            "action": self.final_signal.value,
            "confidence": round(self.confidence, 3),
            "summary": self.summary,
            "agent_signals": self.agent_signals,
            "vote_breakdown": self.vote_breakdown,
            "risk_veto": self.risk_veto,
            "data_source": self.data_source,
            "bull_view": self.bull_view,
            "bear_view": self.bear_view,
            "role_opinions": self.role_opinions,
            "position_advice": self.position_advice,
            "risk_notes": self.risk_notes,
            "timestamp": self.timestamp.isoformat(),
        }


# ── Coordinator ──────────────────────────────────────────────────────────────

class CoordinatorAgent:
    """
    PRD 10.4 decision layer. Consumes AnalysisContext from L5.

    Four analysis roles run in parallel:
      - technical: reads indicators, factors, signals → trend/momentum/reversal
      - news: reads news sentiment, events → sentiment direction + event risk
      - macro: reads macro factors → macro environment assessment
      - risk: reads confidence, volatility, ATR → position advice + veto

    Then a three-round debate (bull → bear → final judge) synthesizes a
    final AgentDecision with full audit trail.
    """

    def __init__(
        self,
        provider_name: Optional[str] = None,
        use_tradingagents: Optional[bool] = None,
        fast_mode: bool = False,
    ):
        self.use_tradingagents = (
            settings.USE_TRADINGAGENTS
            if use_tradingagents is None
            else use_tradingagents
        )
        self.fast_mode = fast_mode
        self.trend_agent = TrendAgent(provider_name)
        self.mr_agent = MeanReversionAgent(provider_name)
        self.risk_agent = RiskAgent(provider_name)
        try:
            self.llm = LLMFactory.create_provider(provider_name)
        except Exception as e:
            logger.warning(f"[coordinator] LLM provider unavailable, using deterministic fallback: {e}")
            self.llm = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def coordinate(
        self,
        symbol: str,
        interval: str = "1h",
    ) -> CoordinationResult:
        """
        Main entry point. Loads AnalysisContext, runs 4-role analysis,
        debate, and produces a structured decision.

        In fast_mode, skips the 3-round debate (saves ~3 LLM calls).
        """
        instrument = Instrument.from_raw(symbol)
        canonical_symbol = instrument.symbol

        # ── TradingAgents path ─────────────────────────────────────────────
        if self.use_tradingagents:
            try:
                from app.agents.tradingagents_adapter import tradingagents_adapter

                ctx = await self._load_analysis_context(canonical_symbol, interval)
                result = await tradingagents_adapter.run_analysis(
                    symbol=canonical_symbol,
                    interval=interval,
                    analysis_context=ctx,
                    fast=self.fast_mode,
                )
                if result is not None:
                    result.symbol = canonical_symbol
                    await self._persist_result(result)
                    return result
            except Exception as e:
                logger.warning(f"[coordinator] TradingAgents fallback: {e}")

        # ── PRD 10.4 standard path ─────────────────────────────────────────
        return await self._coordinate_prd104(canonical_symbol, interval)

    async def _coordinate_prd104(
        self,
        symbol: str,
        interval: str,
    ) -> CoordinationResult:
        """PRD 10.4 decision pipeline: context → 4 roles → debate → decision."""
        symbol = Instrument.from_raw(symbol).symbol

        # Step 1: Load AnalysisContext
        ctx = await self._load_analysis_context(symbol, interval)

        # Step 2: Run 4 analysis roles in parallel
        tech, news, macro, risk = await asyncio.gather(
            self._analyze_technical(ctx),
            self._analyze_news(ctx),
            self._analyze_macro(ctx),
            self._analyze_risk(ctx),
            return_exceptions=True,
        )

        role_opinions: List[RoleOpinion] = []
        for r in [tech, news, macro, risk]:
            if isinstance(r, Exception):
                logger.warning(f"[coordinator] Role failed: {r}")
            else:
                role_opinions.append(r)

        if not role_opinions:
            return CoordinationResult(
                symbol=symbol,
                final_signal=SignalType.WAIT,
                confidence=0.0,
                summary="所有分析角色均发生错误",
                data_source="analysis_context",
            )

        # Step 3: Risk veto check
        risk_veto = any(
            r.role == "risk" and r.risk_flag and r.confidence >= 0.7
            for r in role_opinions
        )
        if risk_veto:
            logger.info(f"[coordinator] Risk veto triggered for {symbol}")

        # Step 4: Multi-round debate (bull / bear / judge) — skip in fast_mode
        if self.fast_mode:
            bull_view = self._fallback_bull(role_opinions)
            bear_view = self._fallback_bear(role_opinions)
            final_decision = self._fallback_decision(role_opinions)
        else:
            bull_view, bear_view, final_decision = await self._bull_bear_debate(
                ctx, role_opinions, symbol
            )

        # Step 5: Vote from role opinions
        vote_breakdown = self._aggregate_votes(role_opinions)
        final_signal, confidence = self._determine_signal(
            vote_breakdown, risk_veto
        )

        # Step 6: LLM final synthesis — skip in fast_mode to save time
        if self.fast_mode:
            summary = self._fallback_summary(final_signal, vote_breakdown, role_opinions)
        else:
            summary = await self._synthesize_final(
                symbol, role_opinions, final_signal, vote_breakdown,
                bull_view, bear_view, final_decision
            )

        # Step 7: Risk notes
        risk_notes = self._build_risk_notes(role_opinions, risk_veto)
        position_advice = self._build_position_advice(role_opinions, risk_veto, ctx)

        result = CoordinationResult(
            symbol=symbol,
            final_signal=final_signal,
            confidence=confidence,
            summary=summary,
            agent_signals=[r.to_dict() for r in role_opinions],
            vote_breakdown=vote_breakdown,
            risk_veto=risk_veto,
            data_source="analysis_context",
            bull_view=bull_view,
            bear_view=bear_view,
            input_snapshot_ids=ctx.get("input_snapshot_ids", {}),
            role_opinions=[r.to_dict() for r in role_opinions],
            position_advice=position_advice,
            risk_notes=risk_notes,
        )
        await self._persist_result(result)
        return result

    # ── AnalysisContext loader ────────────────────────────────────────────────

    async def _load_analysis_context(
        self,
        symbol: str,
        interval: str = "1h",
    ) -> Dict[str, Any]:
        """
        Load AnalysisContext. Uses local Builder directly to avoid
        self-request deadlock in single-worker uvicorn.

        Returns the agent payload dict (same as AnalysisContext.to_agent_payload()).
        """
        symbol = Instrument.from_raw(symbol).symbol

        try:
            from app.services.analysis_context_builder import analysis_context_builder

            ctx = await analysis_context_builder.build(
                symbol=symbol,
                interval=interval,
            )
            logger.info(
                f"[coordinator] Loaded AnalysisContext for {symbol}: "
                f"{len(ctx.bars)} bars, {len(ctx.latest_factors)} factors, "
                f"{len(ctx.recent_signals)} signals"
            )
            return ctx.to_agent_payload()
        except Exception as e:
            logger.error(f"[coordinator] AnalysisContext Builder failed: {e}")
            return self._empty_context(symbol, interval)

    @staticmethod
    def _empty_context(symbol: str, interval: str) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "timeframe": interval,
            "as_of_time": datetime.now(timezone.utc).isoformat(),
            "bars": [],
            "latest_factors": {},
            "recent_signals": [],
            "macro_events": [],
            "news_events": [],
            "input_snapshot_ids": {},
        }

    # ── 4-Role Analysis ──────────────────────────────────────────────────────

    async def _analyze_technical(self, ctx: Dict[str, Any]) -> RoleOpinion:
        """
        Technical analysis role: reads indicators, factors, signals.
        Produces trend/momentum/overbought-oversold assessment.
        """
        factors = ctx.get("latest_factors", {})
        signals = ctx.get("recent_signals", [])
        bars = ctx.get("bars", [])
        symbol = ctx.get("symbol", "unknown")

        # Summarize factors for the prompt
        factor_lines = []
        for k, v in sorted(factors.items())[:20]:
            factor_lines.append(f"- {k}: {v}")

        # Summarize recent signals
        signal_lines = []
        for s in signals[:10]:
            signal_lines.append(
                f"- [{s.get('source_strategy','?')}] {s.get('signal_type','?')} "
                f"(conf={float(s.get('confidence',0.5)):.0%})"
            )

        price = None
        if bars:
            last_bar = bars[-1]
            price = last_bar.get("close", None)

        prompt = f"""
## 技术分析角色: {symbol}
当前价格: {price or 'N/A'}

### 最新因子
{chr(10).join(factor_lines) if factor_lines else '（无因子数据）'}

### 近期信号
{chr(10).join(signal_lines) if signal_lines else '（无信号数据）'}

### 分析要求
1. 判断当前趋势方向（上涨/下跌/横盘）和动量强度
2. 识别超买超卖状态（如果有 RSI/布林带数据）
3. 评估均线排列和 MACD 交叉信号
4. 输出结构化判断:
   opinion: bullish / bearish / neutral
   confidence: 0.0 ~ 1.0
   risk_flag: true/false (是否出现技术性风险信号)
   key_points: 2-3个关键发现

请用中文输出，格式如下：
OPINION: <bullish/bearish/neutral>
CONFIDENCE: <0.0-1.0>
RISK_FLAG: <true/false>
REASONING: <分析文本>
KEY_POINTS:
- <要点1>
- <要点2>
"""
        return await self._invoke_role_llm("technical", prompt)

    async def _analyze_news(self, ctx: Dict[str, Any]) -> RoleOpinion:
        """
        News analysis role: reads news events, sentiment, titles/tags.
        Produces sentiment direction and event risk assessment.
        """
        news = ctx.get("news_events", [])
        symbol = ctx.get("symbol", "unknown")

        # Extract key fields from news
        news_lines = []
        sentiment_values = []
        for n in news[:15]:
            title = n.get("title", "")[:100]
            sentiment = n.get("sentiment") or n.get("sentiment_score")
            tags = n.get("tags", []) or []
            if isinstance(tags, str):
                tags = [tags]
            news_lines.append(f"- [{sentiment}] {title} {', '.join(tags[:3])}")
            if sentiment is not None:
                try:
                    sentiment_values.append(float(sentiment))
                except (ValueError, TypeError):
                    pass

        avg_sentiment = (
            sum(sentiment_values) / len(sentiment_values)
            if sentiment_values else None
        )
        avg_str = f"{avg_sentiment:.3f}" if avg_sentiment is not None else "N/A"

        prompt = f"""
## 新闻分析角色: {symbol}
新闻数量: {len(news)}

### 近期新闻
{chr(10).join(news_lines) if news_lines else '（无新闻数据）'}

平均情绪: {avg_str}

### 分析要求
1. 判断整体新闻情绪方向（正面/负面/中性）
2. 识别重大事件风险（如监管、安全漏洞、宏观经济公告）
3. 评估新闻对短期价格的可能影响
4. 输出结构化判断:
   opinion: bullish / bearish / neutral
   confidence: 0.0 ~ 1.0
   risk_flag: true/false (是否有重大事件风险)

请用中文输出，格式如下：
OPINION: <bullish/bearish/neutral>
CONFIDENCE: <0.0-1.0>
RISK_FLAG: <true/false>
REASONING: <分析文本>
KEY_POINTS:
- <要点1>
- <要点2>
"""
        return await self._invoke_role_llm("news", prompt)

    async def _analyze_macro(self, ctx: Dict[str, Any]) -> RoleOpinion:
        """
        Macro analysis role: reads macro factors.
        Judges whether macro environment supports the current trade direction.
        """
        macro = ctx.get("macro_events", [])
        factors = ctx.get("latest_factors", {})
        symbol = ctx.get("symbol", "unknown")

        # Extract macro-relevant factors
        macro_keys = {k: v for k, v in factors.items() if any(
            prefix in k.lower() for prefix in ["macro", "market_cap", "volume_24h", "dominance"]
        )}
        macro_lines = [f"- {k}: {v}" for k, v in sorted(macro_keys.items())[:15]]

        # Macro events
        event_lines = []
        for m in macro[:10]:
            indicator = m.get("indicator", m.get("name", "?"))
            value = m.get("value", m.get("actual", "?"))
            event_lines.append(f"- {indicator}: {value}")

        prompt = f"""
## 宏观分析角色: {symbol}

### 宏观因子
{chr(10).join(macro_lines) if macro_lines else '（无宏观因子数据）'}

### 宏观事件
{chr(10).join(event_lines) if event_lines else '（无宏观事件数据）'}

### 分析要求
1. 判断当前宏观环境是否支持风险资产（加密货币/股票）
2. 评估流动性、波动率、市场整体情绪
3. 识别系统性风险
4. 输出结构化判断:
   opinion: bullish / bearish / neutral
   confidence: 0.0 ~ 1.0
   risk_flag: true/false

请用中文输出，格式如下：
OPINION: <bullish/bearish/neutral>
CONFIDENCE: <0.0-1.0>
RISK_FLAG: <true/false>
REASONING: <分析文本>
KEY_POINTS:
- <要点1>
- <要点2>
"""
        return await self._invoke_role_llm("macro", prompt)

    async def _analyze_risk(self, ctx: Dict[str, Any]) -> RoleOpinion:
        """
        Risk analysis role: reads confidence, volatility, ATR, macro/news risk.
        Produces position sizing advice and veto opinion.
        """
        factors = ctx.get("latest_factors", {})
        signals = ctx.get("recent_signals", [])
        symbol = ctx.get("symbol", "unknown")

        # Extract risk-relevant factors
        risk_keys = {k: v for k, v in factors.items() if any(
            p in k.lower()
            for p in ["atr", "volatility", "rsi", "drawdown", "var", "sharpe"]
        )}
        risk_lines = [f"- {k}: {v}" for k, v in sorted(risk_keys.items())[:15]]

        # Aggregate signal confidences
        avg_conf = (
            sum(float(s.get("confidence", 0.5)) for s in signals) / len(signals)
            if signals else 0.5
        )

        # Count signals by type
        signal_counts: Dict[str, int] = {}
        for s in signals:
            t = s.get("signal_type", "WAIT")
            signal_counts[t] = signal_counts.get(t, 0) + 1

        prompt = f"""
## 风控分析角色: {symbol}

### 风险相关因子
{chr(10).join(risk_lines) if risk_lines else '（无风险因子数据）'}

### 信号概况
- 信号总数: {len(signals)}
- 平均置信度: {avg_conf:.0%}
- 信号分布: {signal_counts}

### 分析要求
1. 评估当前市场波动性水平（低/中/高/极高）
2. 建议仓位大小（占账户百分比）和最大杠杆
3. 基于 ATR 给出止损距离建议
4. 综合判断是否触发风险否决（veto）
5. 输出结构化判断:
   opinion: long / short / wait
   confidence: 0.0 ~ 1.0
   risk_flag: true/false (是否建议否决当前交易)
   key_points: 仓位建议、杠杆、止损

请用中文输出，格式如下：
OPINION: <long/short/wait>
CONFIDENCE: <0.0-1.0>
RISK_FLAG: <true/false>
REASONING: <分析文本>
KEY_POINTS:
- <要点1>
- <要点2>
"""
        return await self._invoke_role_llm("risk", prompt)

    async def _invoke_role_llm(self, role: str, prompt: str) -> RoleOpinion:
        """Call LLM for a single role analysis and parse structured output."""
        if not self.llm:
            return self._default_role_opinion(role)

        system_prompt = f"""You are a quantitative trading {role} analyst.
Respond STRICTLY in the format specified. Use Chinese for reasoning text."""

        try:
            raw = await self.llm.generate(
                prompt, system_prompt=system_prompt, temperature=0.5
            )
            return self._parse_role_response(role, raw)
        except Exception as e:
            logger.warning(f"[coordinator] {role} role LLM failed: {e}")
            return self._default_role_opinion(role)

    def _parse_role_response(self, role: str, raw: str) -> RoleOpinion:
        """Parse LLM output into structured RoleOpinion."""
        opinion = "neutral"
        confidence = 0.5
        risk_flag = False
        reasoning = raw[:2000]
        key_points: List[str] = []

        for line in raw.split("\n"):
            line_stripped = line.strip()
            if line_stripped.upper().startswith("OPINION:"):
                opinion = line_stripped.split(":", 1)[1].strip().lower()
            elif line_stripped.upper().startswith("CONFIDENCE:"):
                try:
                    confidence = float(line_stripped.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line_stripped.upper().startswith("RISK_FLAG:"):
                risk_flag = "true" in line_stripped.split(":", 1)[1].strip().lower()
            elif line_stripped.startswith("- ") and "KEY_POINTS" not in line_stripped.upper():
                # Collect from lines below KEY_POINTS tag
                pass

        # Extract key_points by splitting around KEY_POINTS section
        kp_match = re.search(
            r'KEY_POINTS\s*:?\s*\n(.*?)(?:\n\S|\Z)',
            raw, re.DOTALL | re.IGNORECASE
        )
        if kp_match:
            for line in kp_match.group(1).strip().split("\n"):
                pt = line.strip().lstrip("- ").strip()
                if pt:
                    key_points.append(pt)

        # Normalize opinion
        opinion = opinion.lower()
        if opinion not in ("bullish", "bearish", "neutral", "long", "short", "wait"):
            opinion = "neutral"

        return RoleOpinion(
            role=role,
            opinion=opinion,
            confidence=min(1.0, max(0.0, confidence)),
            risk_flag=risk_flag,
            reasoning=reasoning,
            key_points=key_points[:5],
        )

    def _default_role_opinion(self, role: str) -> RoleOpinion:
        return RoleOpinion(
            role=role,
            opinion="wait" if role == "risk" else "neutral",
            confidence=0.3,
            risk_flag=False,
            reasoning=f"[{role}] LLM 不可用，返回默认判断",
        )

    # ── Multi-round Debate: Bull / Bear / Final Judge ──────────────────────

    async def _bull_bear_debate(
        self,
        ctx: Dict[str, Any],
        role_opinions: List[RoleOpinion],
        symbol: str,
    ) -> Tuple[str, str, str]:
        """
        Three-round debate using LLM:
          Round 1: Bull view — maximize bullish arguments from context
          Round 2: Bear view — maximize bearish arguments, address bull points
          Round 3: Final judge — weigh both sides, issue decision
        """
        if not self.llm:
            return (
                self._fallback_bull(role_opinions),
                self._fallback_bear(role_opinions),
                self._fallback_decision(role_opinions),
            )

        context_summary = self._summarize_context_for_debate(ctx, role_opinions)

        # Round 1: Bull
        bull_prompt = f"""
## 多头辩论 (Bull View)
{context_summary}

你是多头分析师。请从以下角度最大程度地论证做多 {symbol} 的理由:
1. 技术面支撑（趋势、支撑位、指标信号）
2. 情绪/新闻面支撑
3. 宏观环境支撑
4. 对空头可能提出的风险点进行反驳

请用 2-3 段中文输出你的多头论点。简洁有力，基于数据。
"""
        bull_view = await self._safe_llm(bull_prompt, "bull")

        # Round 2: Bear
        bear_prompt = f"""
## 空头辩论 (Bear View)
{context_summary}

多头观点:
{bull_view[:800]}

你是空头分析师。请从以下角度最大程度地论证做空或观望 {symbol} 的理由:
1. 技术面风险（阻力位、超买、背离）
2. 情绪/新闻面风险
3. 宏观风险
4. 对多头论点的逐一反驳

请用 2-3 段中文输出你的空头论点。简洁有力，基于数据。
"""
        bear_view = await self._safe_llm(bear_prompt, "bear")

        # Round 3: Final judge
        judge_prompt = f"""
## 最终裁决 (Final Judge)
{context_summary}

多头观点:
{bull_view[:800]}

空头观点:
{bear_view[:800]}

你是首席交易决策官。请综合两方面论点，做出最终裁决:
1. 判断多空双方哪方的论据更有说服力
2. 给出最终交易方向: BUY / SELL / WAIT
3. 置信度 (0.0-1.0)
4. 裁决理由 (2-3段中文)

格式:
FINAL_ACTION: <BUY/SELL/WAIT>
CONFIDENCE: <0.0-1.0>
DECISION_REASONING: <裁决理由>
"""
        final_decision = await self._safe_llm(judge_prompt, "judge")

        return bull_view, bear_view, final_decision

    async def _safe_llm(self, prompt: str, tag: str) -> str:
        """Call LLM safely, return fallback on failure."""
        try:
            result = await self.llm.generate(
                prompt,
                system_prompt="You are a professional quantitative trading analyst. Respond in Chinese.",
                temperature=0.6,
            )
            result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
            result = re.sub(r'<think>.*$', '', result, flags=re.DOTALL)
            return result.strip()
        except Exception as e:
            logger.warning(f"[coordinator] LLM {tag} failed: {e}")
            return f"[{tag}] LLM 不可用"

    def _summarize_context_for_debate(
        self,
        ctx: Dict[str, Any],
        role_opinions: List[RoleOpinion],
    ) -> str:
        lines = [f"### 分析标的: {ctx.get('symbol', 'unknown')}"]
        lines.append(f"时间周期: {ctx.get('timeframe', '1h')}")

        bars = ctx.get("bars", [])
        if bars:
            last = bars[-1]
            lines.append(f"最新价格: {last.get('close', 'N/A')}")

        factors = ctx.get("latest_factors", {})
        if factors:
            factor_line = "关键因子: "
            factor_line += ", ".join(
                f"{k}={v}" for k, v in sorted(factors.items())[:12]
            )
            lines.append(factor_line)

        lines.append(f"\n### 角色分析摘要")
        for r in role_opinions:
            lines.append(
                f"- [{r.role}] opinion={r.opinion} "
                f"conf={r.confidence:.0%} risk_flag={r.risk_flag}"
            )

        return "\n".join(lines)

    # ── Vote aggregation ───────────────────────────────────────────────────

    def _aggregate_votes(
        self, role_opinions: List[RoleOpinion]
    ) -> Dict[str, float]:
        """Aggregate role opinions into vote breakdown."""
        bullish_w = sum(
            r.confidence for r in role_opinions
            if r.opinion in ("bullish", "long")
        )
        bearish_w = sum(
            r.confidence for r in role_opinions
            if r.opinion in ("bearish", "short")
        )
        neutral_w = sum(
            r.confidence for r in role_opinions
            if r.opinion not in ("bullish", "bearish", "long", "short")
        )
        total = bullish_w + bearish_w + neutral_w or 1.0
        return {
            "bullish": round(bullish_w / total, 3),
            "bearish": round(bearish_w / total, 3),
            "neutral": round(neutral_w / total, 3),
        }

    def _determine_signal(
        self,
        vote: Dict[str, float],
        risk_veto: bool,
    ) -> Tuple[SignalType, float]:
        if risk_veto:
            return SignalType.WAIT, round(max(vote.get("neutral", 0.5) * 0.5, 0.3), 3)

        b, s, n = vote["bullish"], vote["bearish"], vote["neutral"]
        if b > s and b > n:
            return SignalType.BUY, round(b, 3)
        elif s > b and s > n:
            return SignalType.SELL, round(s, 3)
        else:
            return SignalType.WAIT, round(n, 3)

    # ── LLM synthesis ───────────────────────────────────────────────────────

    async def _synthesize_final(
        self,
        symbol: str,
        role_opinions: List[RoleOpinion],
        final_signal: SignalType,
        vote_breakdown: Dict[str, float],
        bull_view: str,
        bear_view: str,
        final_decision: str,
    ) -> str:
        """Generate final narrative summary."""
        if not self.llm:
            return self._fallback_summary(final_signal, vote_breakdown, role_opinions)

        role_text = "\n".join(
            f"- [{r.role}] {r.opinion} (conf={r.confidence:.0%}, risk_flag={r.risk_flag})"
            for r in role_opinions
        )

        prompt = f"""
## 最终决策综合: {symbol}

### 角色投票
{role_text}

### 投票结果
看多: {vote_breakdown['bullish']:.1%} | 看空: {vote_breakdown['bearish']:.1%} | 中性: {vote_breakdown['neutral']:.1%}

### 多头论点
{bull_view[:600]}

### 空头论点
{bear_view[:600]}

### 最终裁决
{final_decision[:600]}

请用 3-5 段中文，总结本次分析的:
1. 关键发现（各角色共识/分歧）
2. 多空双方核心论点对比
3. 最终决策逻辑和置信度
4. 主要风险提示

简洁专业。
"""
        try:
            result = await self.llm.generate(
                prompt,
                system_prompt="You are a chief trading strategist. Summarize analysis in Chinese.",
                temperature=0.4,
            )
            result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
            result = re.sub(r'<think>.*$', '', result, flags=re.DOTALL)
            return result.strip() or self._fallback_summary(final_signal, vote_breakdown, role_opinions)
        except Exception as e:
            logger.warning(f"[coordinator] Final synthesis failed: {e}")
            return self._fallback_summary(final_signal, vote_breakdown, role_opinions)

    @staticmethod
    def _fallback_summary(
        final_signal: SignalType,
        vote: Dict[str, float],
        role_opinions: List[RoleOpinion],
    ) -> str:
        lines = [f"最终信号: {final_signal.value}"]
        for r in role_opinions:
            lines.append(
                f"- [{r.role}] {r.opinion} (conf={r.confidence:.0%}, risk_flag={r.risk_flag})"
            )
        lines.append(
            f"投票: 看多{vote['bullish']:.0%} | 看空{vote['bearish']:.0%} | 中性{vote['neutral']:.0%}"
        )
        return "\n".join(lines)

    # ── Risk notes & position advice ────────────────────────────────────────

    def _build_risk_notes(
        self,
        role_opinions: List[RoleOpinion],
        risk_veto: bool,
    ) -> str:
        lines = []
        if risk_veto:
            lines.append("⚠️ 风控否决已触发")
        for r in role_opinions:
            if r.risk_flag:
                lines.append(f"[{r.role}] 风险标记: {(r.reasoning or '')[:200]}")
        return "\n".join(lines) if lines else "无明显风险"

    def _build_position_advice(
        self,
        role_opinions: List[RoleOpinion],
        risk_veto: bool,
        ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        advice: Dict[str, Any] = {
            "suggested_position_pct": 0.0 if risk_veto else 10.0,
            "max_leverage": 1,
            "stop_loss_pct": 0.0,
        }

        # Use ATR from factors if available
        factors = ctx.get("latest_factors", {})
        atr_pct = factors.get("atr_pct") or factors.get("atr_14_pct")
        if atr_pct and not risk_veto:
            advice["stop_loss_pct"] = round(float(atr_pct) * 2, 2)
            if float(atr_pct) > 5:
                advice["suggested_position_pct"] = 5.0
                advice["max_leverage"] = 1
            elif float(atr_pct) > 2:
                advice["suggested_position_pct"] = 10.0
                advice["max_leverage"] = 2
            else:
                advice["suggested_position_pct"] = 20.0
                advice["max_leverage"] = 3

        # Risk role provides more specific advice
        for r in role_opinions:
            if r.role == "risk":
                for pt in r.key_points:
                    if "仓位" in pt or "position" in pt.lower():
                        advice["risk_suggestion"] = pt
                    if "杠杆" in pt or "leverage" in pt.lower():
                        advice["leverage_suggestion"] = pt

        return advice

    # ── Fallback debate methods ───────────────────────────────────────────

    def _fallback_bull(self, role_opinions: List[RoleOpinion]) -> str:
        bullish = [r for r in role_opinions if r.opinion in ("bullish", "long")]
        if bullish:
            return "\n".join(f"[{r.role}] {r.reasoning[:300]}" for r in bullish)
        return "未找到明确的多头论点（LLM不可用）"

    def _fallback_bear(self, role_opinions: List[RoleOpinion]) -> str:
        bearish = [r for r in role_opinions if r.opinion in ("bearish", "short")]
        if bearish:
            return "\n".join(f"[{r.role}] {r.reasoning[:300]}" for r in bearish)
        return "未找到明确的空头论点（LLM不可用）"

    def _fallback_decision(self, role_opinions: List[RoleOpinion]) -> str:
        b = sum(1 for r in role_opinions if r.opinion in ("bullish", "long"))
        s = sum(1 for r in role_opinions if r.opinion in ("bearish", "short"))
        if b > s:
            return "FINAL_ACTION: BUY\nCONFIDENCE: 0.6\nDECISION_REASONING: 多头角色占多数"
        elif s > b:
            return "FINAL_ACTION: SELL\nCONFIDENCE: 0.6\nDECISION_REASONING: 空头角色占多数"
        return "FINAL_ACTION: WAIT\nCONFIDENCE: 0.5\nDECISION_REASONING: 多空均衡，建议观望"

    # ── Persistence ────────────────────────────────────────────────────────

    @staticmethod
    async def _persist_result(result: CoordinationResult) -> None:
        """Persist full coordination result to coordination_history."""
        import json as json_module
        decision_id = None
        try:
            async with get_db() as session:
                persisted = await session.execute(
                    sql_text("""
                        INSERT INTO coordination_history
                            (symbol, timestamp, final_signal, confidence,
                             vote_breakdown, risk_veto, summary, agent_signals,
                             bull_view, bear_view, input_snapshot_ids,
                             role_opinions, position_advice, risk_notes)
                        VALUES
                            (:symbol, :timestamp, :final_signal, :confidence,
                             :vote_breakdown, :risk_veto, :summary, :agent_signals,
                             :bull_view, :bear_view, :input_snapshot_ids,
                             :role_opinions, :position_advice, :risk_notes)
                        RETURNING id
                    """),
                    {
                        "symbol": result.symbol,
                        "timestamp": result.timestamp,
                        "final_signal": result.final_signal.value,
                        "confidence": result.confidence,
                        "vote_breakdown": json_module.dumps(result.vote_breakdown),
                        "risk_veto": result.risk_veto,
                        "summary": (result.summary or "")[:5000],
                        "agent_signals": json_module.dumps(result.agent_signals),
                        "bull_view": (result.bull_view or "")[:5000],
                        "bear_view": (result.bear_view or "")[:5000],
                        "input_snapshot_ids": json_module.dumps(result.input_snapshot_ids),
                        "role_opinions": json_module.dumps(result.role_opinions),
                        "position_advice": json_module.dumps(result.position_advice),
                        "risk_notes": (result.risk_notes or "")[:2000],
                    },
                )
                decision_id = persisted.scalar()
        except Exception as e:
            logger.error(f"[coordinator] Failed to persist result: {e}")
            return

        if decision_id:
            try:
                from app.services.audit_service import audit_service

                await audit_service.log_event(
                    action="AGENT_DECISION",
                    user_id="system",
                    resource=result.symbol,
                    details={
                        "decisionId": decision_id,
                        "asOfTime": result.timestamp.isoformat() if result.timestamp else None,
                        "snapshotId": result.input_snapshot_ids,
                        "inputSummary": {
                            "snapshot_ids": result.input_snapshot_ids,
                            "risk_notes": result.risk_notes,
                        },
                        "agentOutputs": result.role_opinions or result.agent_signals,
                        "decision": {
                            "id": decision_id,
                            "symbol": result.symbol,
                            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
                            "final_signal": result.final_signal.value,
                            "confidence": result.confidence,
                            "risk_veto": result.risk_veto,
                            "summary": result.summary,
                        },
                    },
                    ip_address="internal",
                )
            except Exception as exc:
                logger.warning("[coordinator] Failed to write AGENT_DECISION audit: %s", exc)

    # ── Streaming ────────────────────────────────────────────────────────────

    async def coordinate_stream(
        self,
        symbol: str,
        interval: str = "1h",
    ) -> AsyncGenerator[str, None]:
        """Stream the PRD 10.4 decision process step-by-step."""
        symbol = Instrument.from_raw(symbol).symbol
        yield f"## PRD 10.4 多 Agent 协作分析: {symbol}\n\n"

        # Load context
        yield "[1/6] 加载 AnalysisContext...\n"
        ctx = await self._load_analysis_context(symbol, interval)
        yield (
            f"✅ 加载完成: {len(ctx.get('bars',[]))} bars, "
            f"{len(ctx.get('latest_factors',{}))} factors, "
            f"{len(ctx.get('recent_signals',[]))} signals\n\n"
        )

        # Run 4 roles
        yield "[2/6] 运行四角色分析...\n"
        yield "  - 技术分析角色...\n"
        yield "  - 新闻分析角色...\n"
        yield "  - 宏观分析角色...\n"
        yield "  - 风控分析角色...\n"

        tech, news, macro, risk = await asyncio.gather(
            self._analyze_technical(ctx),
            self._analyze_news(ctx),
            self._analyze_macro(ctx),
            self._analyze_risk(ctx),
            return_exceptions=True,
        )
        role_opinions: List[RoleOpinion] = []
        for r in [tech, news, macro, risk]:
            if isinstance(r, Exception):
                continue
            role_opinions.append(r)
            yield (
                f"  ✅ [{r.role}] opinion={r.opinion} "
                f"conf={r.confidence:.0%} risk_flag={r.risk_flag}\n"
            )

        # Risk veto
        risk_veto = any(
            r.role == "risk" and r.risk_flag and r.confidence >= 0.7
            for r in role_opinions
        )
        if risk_veto:
            yield "\n⚠️ 风控否决已触发!\n"

        # Debate
        yield "\n[3/6] 多空辩论...\n"
        bull_view, bear_view, final_decision = await self._bull_bear_debate(
            ctx, role_opinions, symbol
        )
        yield f"\n### 🟢 多头观点\n{bull_view[:600]}\n"
        yield f"\n### 🔴 空头观点\n{bear_view[:600]}\n"
        yield f"\n### ⚖️ 最终裁决\n{final_decision[:600]}\n"

        # Vote
        yield "\n[4/6] 投票汇总...\n"
        vote = self._aggregate_votes(role_opinions)
        final_signal, confidence = self._determine_signal(vote, risk_veto)
        yield (
            f"看多: {vote['bullish']:.1%} | 看空: {vote['bearish']:.1%} | "
            f"中性: {vote['neutral']:.1%}\n"
        )
        yield f"最终信号: **{final_signal.value}** (置信度: {confidence:.0%})\n"

        # Synthesize
        yield "\n[5/6] 综合决策...\n"
        summary = await self._synthesize_final(
            symbol, role_opinions, final_signal, vote,
            bull_view, bear_view, final_decision
        )
        yield f"\n{summary}\n"

        # Persist
        yield "\n[6/6] 持久化决策记录...\n"
        risk_notes = self._build_risk_notes(role_opinions, risk_veto)
        position_advice = self._build_position_advice(role_opinions, risk_veto, ctx)

        result = CoordinationResult(
            symbol=symbol,
            final_signal=final_signal,
            confidence=confidence,
            summary=summary,
            agent_signals=[r.to_dict() for r in role_opinions],
            vote_breakdown=vote,
            risk_veto=risk_veto,
            bull_view=bull_view,
            bear_view=bear_view,
            input_snapshot_ids=ctx.get("input_snapshot_ids", {}),
            role_opinions=[r.to_dict() for r in role_opinions],
            position_advice=position_advice,
            risk_notes=risk_notes,
        )
        await self._persist_result(result)
        yield "\n✅ 决策已写入 coordination_history\n"

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _extract_macro_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "macro_events": ctx.get("macro_events", []),
            "latest_factors": ctx.get("latest_factors", {}),
        }

    # ── Real-time fallback (kept for backward compatibility) ───────────────

    async def _run_realtime_agents(
        self, symbol: str, interval: str
    ) -> Tuple[List[AgentSignal], Optional[bool]]:
        """Run the 3 classic agents in real-time. Returns (signals, risk_veto)."""
        trend_sig, mr_sig, risk_sig = await asyncio.gather(
            self.trend_agent.run(symbol, interval),
            self.mr_agent.run(symbol, interval),
            self.risk_agent.run(symbol, interval),
            return_exceptions=True,
        )
        signals: List[AgentSignal] = []
        risk_veto = None
        for sig in [trend_sig, mr_sig, risk_sig]:
            if isinstance(sig, Exception):
                logger.warning(f"[coordinator] Real-time agent failed: {sig}")
            else:
                signals.append(sig)
                if sig.agent_id == "risk" and sig.signal == SignalType.WAIT and sig.confidence >= 0.75:
                    risk_veto = True
        return signals, risk_veto
