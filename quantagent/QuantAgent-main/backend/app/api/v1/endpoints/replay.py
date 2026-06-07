import hashlib
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from sqlalchemy import select, update, delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.database import get_db, get_db_session
from app.models.db_models import ReplaySession, PaperTrade, PaperPosition, EquitySnapshot
from app.models.trading import (
    ReplayCreateRequest, ReplaySessionResponse, ReplayStatusResponse,
    ReplayJumpRequest, ValidDateRangeResponse, ReplaySessionDetailResponse,
    ReplayTradeStatsResponse, PaginatedReplaySessionsResponse, ReplaySessionListItem,
    SessionSummaryMetrics, QuickBacktestResponse, TimeEstimateRequest, TimeEstimateResponse,
    ReplayTradeMarker, ReplayTradesResponse, ReplayEquityCurveResponse,
    KlineBar, IndicatorData, ReplayKlineResponse, ReplayPositionResponse
)
from app.services.replay_metrics_service import replay_metrics_service
from app.services.clickhouse_service import clickhouse_service
from app.services.historical_replay_adapter import HistoricalReplayAdapter
from app.core.bus import TradingBusImpl, ReplayConfig, PaperExecutionRouter
from app.services.strategy_runner_service import strategy_runner_service
from app.services.paper_trading_service import paper_trading_service
from app.services.audit_service import audit_service
from app.strategies.ma_cross import MaCrossStrategy
from app.strategies.signal_based_strategy import SignalBasedStrategy
from app.services.indicators import ema as calc_ema_df, atr as calc_atr_df, donchian_channels as calc_donchian_df, ichimoku_cloud as calc_ichimoku_df
from app.services.reproducibility import enrich_pit_metadata, stable_params_hash
import pandas as pd

logger = logging.getLogger(__name__)
router = APIRouter()

# Global store for active replay instances
# In a distributed system, this would be managed by a separate worker service
active_replays: Dict[str, HistoricalReplayAdapter] = {}


# =============================================================================
# Helper Functions
# =============================================================================

def safe_float(val, default: float = 0.0) -> float:
    """Safely convert a value to float, handling pandas Series cases.
    
    When using df.loc[idx] on a DataFrame with duplicate indices,
    the result can be a Series instead of a scalar. This function
    handles both cases safely.
    
    Args:
        val: Value to convert (can be scalar, Series, or numpy array)
        default: Default value if conversion fails
    
    Returns:
        float value
    """
    if val is None:
        return default
    # Handle pandas Series or numpy array with .item() method
    if hasattr(val, 'item'):
        try:
            return float(val.item())
        except (ValueError, TypeError):
            pass
    # Handle pandas Series with .iloc accessor
    if hasattr(val, 'iloc'):
        try:
            return float(val.iloc[0])
        except (ValueError, TypeError, IndexError):
            pass
    # Standard conversion
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _build_quick_backtest_pit_metadata(
    *,
    df: pd.DataFrame,
    replay_session_id: str,
    start_time: datetime,
    end_time: datetime,
    data_source: str,
) -> Dict[str, object]:
    index_min = df.index.min() if df is not None and len(df) else None
    index_max = df.index.max() if df is not None and len(df) else None
    return {
        "enabled": True,
        "rule": "bar_time <= replay_end_time",
        "scope": "replay_quick_backtest",
        "replay_session_id": replay_session_id,
        "as_of_time": _iso(end_time),
        "requested_start_time": _iso(start_time),
        "requested_end_time": _iso(end_time),
        "actual_start_time": _iso(index_min),
        "actual_end_time": _iso(index_max),
        "row_count": int(len(df)) if df is not None else 0,
        "data_source": data_source,
        "note": "快速回测使用历史回放的时间窗口，用于回放 vs 回测严格对比。",
    }
DEFAULT_INITIAL_CAPITAL = 100000.0


def safe_finite_float(val, default: float = 0.0) -> float:
    f = safe_float(val, default=default)
    if not math.isfinite(f):
        return default
    return f


def _to_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _event_payload(
    *,
    event_id: str,
    event_type: str,
    event_time: Any,
    symbol: str,
    summary: str,
    payload: Dict[str, Any],
    related_decision_id: Optional[int] = None,
    related_order_intent_id: Optional[str] = None,
    related_order_id: Optional[str] = None,
    related_audit_id: Optional[int] = None,
) -> Dict[str, Any]:
    event_time_iso = _iso(event_time)
    as_of_time = payload.get("asOfTime") or payload.get("as_of_time") or event_time_iso
    summary = _demo_replay_summary(event_type, summary)
    return {
        "id": event_id,
        "eventType": event_type,
        "eventTime": event_time_iso,
        "asOfTime": as_of_time,
        "symbol": symbol,
        "summary": summary,
        "relatedDecisionId": related_decision_id,
        "relatedOrderIntentId": related_order_intent_id,
        "relatedOrderId": related_order_id,
        "relatedAuditId": related_audit_id,
        "payload": payload,
        "links": {
            "decision": f"/audit?decision_id={related_decision_id}" if related_decision_id else None,
            "audit": f"/audit?audit_id={related_audit_id}" if related_audit_id else None,
            "orderIntent": f"/audit?order_intent_id={related_order_intent_id}" if related_order_intent_id else None,
        },
    }


REPLAY_EVENT_BUSINESS_ORDER = {
    "BAR_UPDATED": 10,
    "FACTOR_UPDATED": 20,
    "SIGNAL_TRIGGERED": 30,
    "AGENT_DECISION": 40,
    "ORDER_INTENT_CREATED": 50,
    "RISK_CHECK_PASSED": 60,
    "RISK_BLOCKED": 60,
    "PAPER_ORDER_FILLED": 70,
    "PAPER_ORDER_REJECTED": 70,
    "POSITION_UPDATED": 80,
    "PNL_UPDATED": 90,
    "AUDIT_RECORDED": 100,
    "SKIPPED_AGENT_CALL": 110,
}


REPLAY_EVENT_DEMO_SUMMARIES = {
    "SIGNAL_TRIGGERED": "强信号触发，进入 Agent 审计回测链路。",
    "AGENT_DECISION": "Agent 根据行情、因子和上下文生成交易建议。",
    "ORDER_INTENT_CREATED": "系统将 Agent 建议转换为标准交易意图 OrderIntent。",
    "RISK_CHECK_PASSED": "RiskGuard 风控检查通过，允许进入模拟成交。",
    "RISK_BLOCKED": "RiskGuard 拦截该交易，未生成模拟订单。",
    "PAPER_ORDER_FILLED": "模拟订单成交，记录成交价、手续费与滑点。",
    "POSITION_UPDATED": "持仓更新完成。",
    "PNL_UPDATED": "盈亏重新计算完成。",
    "SKIPPED_AGENT_CALL": "已达到 maxAgentCalls 限制，本次强信号跳过 Agent 调用。",
}


def _demo_replay_summary(event_type: str, fallback: str) -> str:
    return REPLAY_EVENT_DEMO_SUMMARIES.get(event_type, fallback)


def _sort_replay_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        events,
        key=lambda item: (
            _to_datetime(item.get("asOfTime") or item.get("eventTime")) or datetime.min.replace(tzinfo=timezone.utc),
            REPLAY_EVENT_BUSINESS_ORDER.get(str(item.get("eventType") or ""), 999),
            _to_datetime(item.get("eventTime")) or datetime.min.replace(tzinfo=timezone.utc),
            str(item.get("id") or ""),
        ),
    )


def _replay_event_merge_key(event: Dict[str, Any]) -> tuple:
    event_type = str(event.get("eventType") or "")
    related_order_id = event.get("relatedOrderId") or ""
    related_intent_id = event.get("relatedOrderIntentId") or ""
    related_audit_id = event.get("relatedAuditId") or ""
    if event_type in {"PAPER_ORDER_FILLED", "PNL_UPDATED"} and related_order_id:
        related_intent_id = ""
        related_audit_id = ""
    elif event_type in {"PAPER_ORDER_FILLED", "PNL_UPDATED"} and related_intent_id:
        related_audit_id = ""
    return (
        event_type,
        related_order_id,
        related_intent_id,
        related_audit_id,
        event.get("asOfTime") or event.get("eventTime") or "",
    )


def _event_completeness_score(event: Dict[str, Any]) -> int:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    links = event.get("links") if isinstance(event.get("links"), dict) else {}
    return (
        (100 if event.get("relatedAuditId") else 0)
        + (30 if event.get("relatedDecisionId") else 0)
        + (30 if event.get("relatedOrderIntentId") else 0)
        + (20 if event.get("relatedOrderId") else 0)
        + len(payload)
        + sum(1 for value in links.values() if value)
    )


def _source_event_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": event.get("id"),
        "eventType": event.get("eventType"),
        "eventTime": event.get("eventTime"),
        "asOfTime": event.get("asOfTime"),
        "relatedAuditId": event.get("relatedAuditId"),
        "relatedOrderId": event.get("relatedOrderId"),
        "relatedOrderIntentId": event.get("relatedOrderIntentId"),
    }


def _merge_replay_event_group(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(group) == 1:
        return group[0]
    base = max(group, key=_event_completeness_score).copy()
    source_events = [_source_event_payload(item) for item in group]
    raw_payloads = [item.get("payload") or {} for item in group]
    base["sourceEvents"] = source_events
    base["rawPayloads"] = raw_payloads
    base["mergedFromCount"] = len(group)
    payload = dict(base.get("payload") or {})
    payload["sourceEvents"] = source_events
    payload["rawPayloads"] = raw_payloads
    payload["mergedFromCount"] = len(group)
    base["payload"] = payload
    base["id"] = f"MERGED-{base.get('eventType')}-{base.get('asOfTime')}-{base.get('relatedOrderId') or base.get('relatedOrderIntentId') or base.get('relatedAuditId') or base.get('id')}"
    return base


def _dedupe_replay_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    passthrough: List[Dict[str, Any]] = []
    for event in events:
        key = _replay_event_merge_key(event)
        if not key[0]:
            passthrough.append(event)
            continue
        grouped.setdefault(key, []).append(event)
    merged = [_merge_replay_event_group(group) for group in grouped.values()]
    return passthrough + merged


def _build_replay_event_stats(events: List[Dict[str, Any]], execution_mode: Optional[str] = None) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    audit_ids = set()
    detected_mode = execution_mode
    for event in events:
        event_type = str(event.get("eventType") or "")
        counts[event_type] = counts.get(event_type, 0) + 1
        if event.get("relatedAuditId"):
            audit_ids.add(str(event.get("relatedAuditId")))
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        detected_mode = detected_mode or payload.get("executionMode") or payload.get("execution_mode")
        for source_event in event.get("sourceEvents") or []:
            if isinstance(source_event, dict) and source_event.get("relatedAuditId"):
                audit_ids.add(str(source_event.get("relatedAuditId")))
    return {
        "signalTriggeredCount": counts.get("SIGNAL_TRIGGERED", 0),
        "agentDecisionCount": counts.get("AGENT_DECISION", 0),
        "skippedAgentCallCount": counts.get("SKIPPED_AGENT_CALL", 0),
        "riskPassedCount": counts.get("RISK_CHECK_PASSED", 0),
        "riskBlockedCount": counts.get("RISK_BLOCKED", 0),
        "paperOrderFilledCount": counts.get("PAPER_ORDER_FILLED", 0),
        "auditRecordCount": len(audit_ids) or counts.get("AUDIT_RECORDED", 0),
        "executionMode": detected_mode or "rule_only",
        "byEventType": counts,
    }



# =============================================================================
# Technical Indicator Calculation Functions
# =============================================================================

def calc_ma(closes: list[float], period: int) -> list[float | None]:
    """Calculate Simple Moving Average."""
    result = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        result[i] = sum(closes[i - period + 1:i + 1]) / period
    return result


def calc_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Calculate Relative Strength Index."""
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        result[period] = 100.0
    else:
        result[period] = 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i-1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i-1]) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            result[i] = 100 - (100 / (1 + avg_gain / avg_loss))
    return result


def calc_boll(closes: list[float], period: int = 20, num_std: float = 2.0):
    """Calculate Bollinger Bands."""
    middle = calc_ma(closes, period)
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        std = (sum((c - middle[i])**2 for c in closes[i-period+1:i+1]) / period) ** 0.5
        upper[i] = middle[i] + num_std * std
        lower[i] = middle[i] - num_std * std
    return upper, middle, lower


def calc_macd(closes: list[float], fast: int = 12, slow: int = 26, signal_period: int = 9):
    """Calculate MACD indicator."""
    def ema(data, period):
        result = [None] * len(data)
        if len(data) < period:
            return result
        k = 2 / (period + 1)
        result[period - 1] = sum(data[:period]) / period
        for i in range(period, len(data)):
            result[i] = data[i] * k + result[i-1] * (1 - k)
        return result
    
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [None] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]
    
    macd_values = [v for v in macd_line if v is not None]
    signal_line_values = ema(macd_values, signal_period) if macd_values else []
    
    signal = [None] * len(closes)
    histogram = [None] * len(closes)
    start_idx = next((i for i, v in enumerate(macd_line) if v is not None), len(closes))
    for i, sv in enumerate(signal_line_values):
        idx = start_idx + i
        if idx < len(closes) and sv is not None:
            signal[idx] = sv
            if macd_line[idx] is not None:
                histogram[idx] = macd_line[idx] - sv
    
    return macd_line, signal, histogram


def compute_indicators(closes: list[float], times: list[str], strategy_type: str, params: dict, highs: list[float] = None, lows: list[float] = None) -> dict[str, list[IndicatorData]]:
    """Compute technical indicators based on strategy type and params."""
    indicators = {}

    def _add_value(values: dict, key: str, val, ndigits: int):
        if not isinstance(values, dict):
            return
        if val is None:
            return
        try:
            if pd.isna(val):
                return
        except Exception:
            pass
        try:
            fval = float(val)
        except (TypeError, ValueError):
            return
        if not math.isfinite(fval):
            return
        values[key] = round(fval, ndigits)
    
    if strategy_type == "ma":
        ma_short_period = params.get("ma_short", params.get("short_period", 10))
        ma_long_period = params.get("ma_long", params.get("long_period", 30))
        ma_short = calc_ma(closes, ma_short_period)
        ma_long = calc_ma(closes, ma_long_period)
        
        indicators["ma"] = []
        for i, t in enumerate(times):
            if i >= len(ma_short) or i >= len(ma_long):
                continue
            values = {}
            # 兼容 None/NaN（回放数据可能含缺失值或计算窗口含 NaN）
            _add_value(values, "ma_short", ma_short[i], 2)
            _add_value(values, "ma_long", ma_long[i], 2)
            if values:
                indicators["ma"].append(IndicatorData(time=t, values=values))
    
    elif strategy_type == "rsi":
        period = params.get("rsi_period", params.get("period", 14))
        rsi = calc_rsi(closes, period)
        
        indicators["rsi"] = []
        for i, t in enumerate(times):
            if i >= len(rsi):
                continue
            values = {}
            _add_value(values, "rsi", rsi[i], 2)
            if values:
                indicators["rsi"].append(IndicatorData(time=t, values=values))
    
    elif strategy_type == "boll":
        period = params.get("boll_period", params.get("period", 20))
        num_std = params.get("num_std", params.get("std_dev", 2.0))
        upper, middle, lower = calc_boll(closes, period, num_std)
        
        indicators["boll"] = []
        for i, t in enumerate(times):
            if i >= len(upper) or i >= len(middle) or i >= len(lower):
                continue
            values = {}
            _add_value(values, "upper", upper[i], 2)
            _add_value(values, "middle", middle[i], 2)
            _add_value(values, "lower", lower[i], 2)
            if values:
                indicators["boll"].append(IndicatorData(time=t, values=values))
    
    elif strategy_type == "macd":
        fast = params.get("macd_fast", params.get("fast_period", 12))
        slow = params.get("macd_slow", params.get("slow_period", 26))
        signal_period = params.get("macd_signal", params.get("signal_period", 9))
        macd_line, signal_line, histogram = calc_macd(closes, fast, slow, signal_period)
        
        indicators["macd"] = []
        for i, t in enumerate(times):
            if i >= len(macd_line) or i >= len(signal_line) or i >= len(histogram):
                continue
            values = {}
            _add_value(values, "macd", macd_line[i], 4)
            _add_value(values, "signal", signal_line[i], 4)
            _add_value(values, "histogram", histogram[i], 4)
            if values:
                indicators["macd"].append(IndicatorData(time=t, values=values))
    
    elif strategy_type == "ema_triple":
        fast_period = int(params.get("fast_period", 5))
        mid_period = int(params.get("mid_period", 20))
        slow_period = int(params.get("slow_period", 60))
        
        df = pd.DataFrame({"close": closes})
        df = calc_ema_df(df, fast_period)
        df = calc_ema_df(df, mid_period)
        df = calc_ema_df(df, slow_period)
        
        indicators["ema"] = []
        for i, t in enumerate(times):
            if i >= len(df):
                continue
            values = {}
            v_fast = df[f"ema_{fast_period}"].iloc[i]
            v_mid = df[f"ema_{mid_period}"].iloc[i]
            v_slow = df[f"ema_{slow_period}"].iloc[i]
            if pd.notna(v_fast):
                values["ema_fast"] = round(float(v_fast), 2)
            if pd.notna(v_mid):
                values["ema_mid"] = round(float(v_mid), 2)
            if pd.notna(v_slow):
                values["ema_slow"] = round(float(v_slow), 2)
            if values:
                indicators["ema"].append(IndicatorData(time=t, values=values))
    
    elif strategy_type == "atr_trend":
        atr_period = int(params.get("atr_period", 14))
        atr_multiplier = float(params.get("atr_multiplier", 2.0))
        trend_period = int(params.get("trend_period", 20))
        
        df = pd.DataFrame({"close": closes, "high": highs or closes, "low": lows or closes})
        df = calc_atr_df(df, atr_period)
        
        rolling_high = df["high"].rolling(window=atr_period).max()
        chandelier_stop = rolling_high - atr_multiplier * df[f"atr_{atr_period}"]
        trend_highest = df["high"].rolling(window=trend_period).max()
        
        indicators["atr"] = []
        for i, t in enumerate(times):
            if i >= len(df) or i >= len(chandelier_stop) or i >= len(trend_highest):
                continue
            values = {}
            atr_val = df[f"atr_{atr_period}"].iloc[i]
            stop_val = chandelier_stop.iloc[i]
            high_val = trend_highest.iloc[i]
            if pd.notna(atr_val):
                values["atr"] = round(float(atr_val), 2)
            if pd.notna(stop_val):
                values["chandelier_stop"] = round(float(stop_val), 2)
            if pd.notna(high_val):
                values["highest"] = round(float(high_val), 2)
            if values:
                indicators["atr"].append(IndicatorData(time=t, values=values))
    
    elif strategy_type == "turtle":
        entry_period = int(params.get("entry_period", 20))
        exit_period = int(params.get("exit_period", 10))
        
        df = pd.DataFrame({"close": closes, "high": highs or closes, "low": lows or closes})
        entry_result = calc_donchian_df(df, entry_period)
        exit_result = calc_donchian_df(df, exit_period)
        
        indicators["turtle"] = []
        for i, t in enumerate(times):
            if i >= len(entry_result) or i >= len(exit_result):
                continue
            values = {}
            upper_val = entry_result["donchian_upper"].iloc[i]
            lower_val = exit_result["donchian_lower"].iloc[i]
            if pd.notna(upper_val):
                values["upper"] = round(float(upper_val), 2)
            if pd.notna(lower_val):
                values["lower"] = round(float(lower_val), 2)
            if values:
                indicators["turtle"].append(IndicatorData(time=t, values=values))
    
    elif strategy_type == "ichimoku":
        tenkan_period = int(params.get("tenkan_period", 9))
        kijun_period = int(params.get("kijun_period", 26))
        senkou_b_period = int(params.get("senkou_b_period", 52))
        
        df = pd.DataFrame({"close": closes, "high": highs or closes, "low": lows or closes})
        result = calc_ichimoku_df(df, tenkan_period, kijun_period, senkou_b_period)
        
        indicators["ichimoku"] = []
        for i, t in enumerate(times):
            if i >= len(result):
                continue
            values = {}
            for col, key in [("ichi_tenkan", "tenkan"), ("ichi_kijun", "kijun"), ("ichi_span_a", "span_a"), ("ichi_span_b", "span_b")]:
                val = result[col].iloc[i]
                if pd.notna(val):
                    values[key] = round(float(val), 2)
            if values:
                indicators["ichimoku"].append(IndicatorData(time=t, values=values))
    
    return indicators

def get_strategy_class(strategy_type: str):
    """Factory to get the class-based strategy implementation."""
    # MA strategy has its own dedicated implementation
    if strategy_type == "ma":
        return MaCrossStrategy
    if strategy_type == "dynamic_selection":
        from app.strategies.dynamic_selection_strategy import DynamicSelectionStrategy
        return DynamicSelectionStrategy
    # Sync strategies use the generic signal-based adapter
    # Supported: rsi, boll, macd, ema_triple, atr_trend, turtle, ichimoku
    sync_types = {"rsi", "boll", "macd", "ema_triple", "atr_trend", "turtle", "ichimoku"}
    if strategy_type in sync_types:
        return SignalBasedStrategy
    # Note: smart_beta and basis are async and not supported for historical replay
    return None

@router.post("/create", response_model=ReplaySessionResponse)
async def create_replay_session(
    request: ReplayCreateRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Create a new historical replay session after validating dates."""
    # 0. Validate strategy type (reject async strategies)
    async_strategies = {"smart_beta", "basis"}
    if request.strategy_type in async_strategies:
        raise HTTPException(
            status_code=400, 
            detail=f"Strategy '{request.strategy_type}' requires real-time macro data and is not supported for historical replay. Please use: ma, rsi, boll, macd, ema_triple, atr_trend, turtle, ichimoku, or dynamic_selection."
        )
    
    if request.strategy_type == "dynamic_selection":
        params = request.params or {}
        atomic_strategies = params.get("atomic_strategies")
        if not atomic_strategies or not isinstance(atomic_strategies, list):
            raise HTTPException(
                status_code=400,
                detail="dynamic_selection strategy requires a non-empty list of 'atomic_strategies' in params."
            )
        
        sync_types = {"ma", "rsi", "boll", "macd", "ema_triple", "atr_trend", "turtle", "ichimoku"}
        for idx, item in enumerate(atomic_strategies):
            if "strategy_id" not in item or "strategy_type" not in item:
                raise HTTPException(
                    status_code=400,
                    detail=f"Atomic strategy at index {idx} must contain 'strategy_id' and 'strategy_type'."
                )
            if item["strategy_type"] not in sync_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Atomic strategy type '{item['strategy_type']}' is not supported. Supported types: {sync_types}"
                )
        
        # Validate evaluation_period: must be a positive integer
        evaluation_period = params.get("evaluation_period")
        if evaluation_period is not None:
            if not isinstance(evaluation_period, int) or evaluation_period <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="evaluation_period must be a positive integer (> 0)"
                )
        
        # Validate elimination_rule: must be a dict with valid field ranges
        elimination_rule = params.get("elimination_rule")
        if elimination_rule is not None:
            if not isinstance(elimination_rule, dict):
                raise HTTPException(
                    status_code=400,
                    detail="elimination_rule must be a dictionary"
                )
            
            # Validate min_score_threshold: must be in range 0-100
            min_score = elimination_rule.get("min_score_threshold")
            if min_score is not None:
                if not isinstance(min_score, (int, float)) or min_score < 0 or min_score > 100:
                    raise HTTPException(
                        status_code=400,
                        detail="elimination_rule.min_score_threshold must be between 0 and 100"
                    )
            
            # Validate elimination_ratio: must be in range 0-1
            elim_ratio = elimination_rule.get("elimination_ratio")
            if elim_ratio is not None:
                if not isinstance(elim_ratio, (int, float)) or elim_ratio < 0 or elim_ratio > 1:
                    raise HTTPException(
                        status_code=400,
                        detail="elimination_rule.elimination_ratio must be between 0 and 1"
                    )
    
    # 1. Validate interval
    valid_intervals = {"1m", "5m", "15m", "1h", "4h", "1d"}
    valid_speeds = {1, 10, 60, 100, 500, 1000, 5000, 10000, 50000, 100000, -1}
    interval = request.interval or "1m"
    if interval not in valid_intervals:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Must be one of: {valid_intervals}")
    
    # Validate speed
    if request.speed not in valid_speeds:
        raise HTTPException(status_code=400, detail=f"Invalid speed. Must be one of: {valid_speeds}")
    
    # Validate equity_snapshot_interval (if provided)
    equity_snapshot_interval = request.equity_snapshot_interval or 3600
    if equity_snapshot_interval < 60 or equity_snapshot_interval > 14400:
        raise HTTPException(
            status_code=400, 
            detail="equity_snapshot_interval must be between 60 and 14400 seconds (1 minute to 4 hours)"
        )
    
    # 2. Validate date range for specific interval
    range_info = await clickhouse_service.get_valid_date_range(request.symbol, interval)
    if not range_info["min_date"] or not range_info["max_date"]:
        raise HTTPException(status_code=400, detail=f"No historical data found for {request.symbol}/{interval}")
    
    # Ensure requested range is within valid range
    start_utc = request.start_time.astimezone(timezone.utc)
    end_utc = request.end_time.astimezone(timezone.utc)
    
    # Simple check: if the requested start/end are completely outside the available range
    if start_utc > range_info["max_date"].replace(tzinfo=timezone.utc) or end_utc < range_info["min_date"].replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail=f"Requested range {start_utc} - {end_utc} has no data. Available: {range_info['min_date']} - {range_info['max_date']}")

    # 3. Generate session ID
    session_id = f"REPLAY_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
    
    # 4. Save to database (always store interval in params for comparison purposes)
    params_with_interval = dict(request.params or {})
    params_with_interval["interval"] = interval  # Always include interval for proper comparison
    
    new_session = ReplaySession(
        replay_session_id=session_id,
        strategy_id=request.strategy_id,
        strategy_type=request.strategy_type,
        params=params_with_interval,
        symbol=request.symbol,
        start_time=start_utc,
        end_time=end_utc,
        speed=request.speed,
        initial_capital=request.initial_capital,
        status="pending",
        data_source='REPLAY',
        params_hash=hashlib.sha256(json.dumps(params_with_interval, sort_keys=True).encode()).hexdigest() if params_with_interval else None,
        backtest_id=request.backtest_id,
        equity_snapshot_interval=equity_snapshot_interval,
    )

    db.add(new_session)
    await audit_service.add_event(
        db,
        action="REPLAY_SESSION_CREATE",
        user_id="system",
        resource=request.symbol,
        details={
            "eventType": "REPLAY_SESSION_CREATE",
            "symbol": request.symbol,
            "replaySessionId": session_id,
            "replay_session_id": session_id,
            "strategy_id": request.strategy_id,
            "strategy_type": request.strategy_type,
            "interval": interval,
            "params": params_with_interval,
            "params_hash": new_session.params_hash,
            "start_time": _iso(start_utc),
            "end_time": _iso(end_utc),
            "initial_capital": request.initial_capital,
            "data_source": "clickhouse:klines",
            "range_min": _iso(range_info.get("min_date")),
            "range_max": _iso(range_info.get("max_date")),
            "backtestId": request.backtest_id,
            "backtest_id": request.backtest_id,
            "executionMode": "historical_replay",
        },
    )
    await db.commit()
    
    return ReplaySessionResponse(
        replay_session_id=session_id,
        status="pending",
        message=f"Replay session created for {request.symbol}/{interval}"
    )

@router.post("/{replay_session_id}/start", response_model=ReplaySessionResponse)
async def start_replay(
    replay_session_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session)
):
    """Start the historical replay in a background task."""
    logger.info(f"Start replay request received for session {replay_session_id}")
    
    try:
        # 1. Fetch session
        stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            logger.warning(f"Replay session {replay_session_id} not found")
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        if session.status == "running":
            return ReplaySessionResponse(replay_session_id=replay_session_id, status="running", message="Already running")

        # Resume: if paused and adapter still exists, just resume instead of creating a new task.
        # This avoids the old background task and new task fighting over the same adapter.
        if session.status == "paused" and replay_session_id in active_replays:
            adapter = active_replays[replay_session_id]
            adapter.resume_playback()
            session.status = "running"
            await db.commit()
            return ReplaySessionResponse(
                replay_session_id=replay_session_id,
                status="running",
                message="Historical replay resumed"
            )

        # 2. Setup Replay Components
        try:
            config = ReplayConfig(
                start_time=session.start_time,
                end_time=session.end_time,
                speed=session.speed,
                initial_capital=session.initial_capital,
                equity_snapshot_interval=session.equity_snapshot_interval or 3600,
            )
            
            # Create Bus and Adapter
            execution_router = PaperExecutionRouter()
            bus = TradingBusImpl(mode="HISTORICAL_REPLAY", data_adapter=None, execution_router=execution_router, session_id=replay_session_id)
            adapter = HistoricalReplayAdapter(bus=bus, config=config)
            bus.data_adapter = adapter
            
            active_replays[replay_session_id] = adapter
            logger.info(f"Replay components setup for session {replay_session_id}")
        except Exception as e:
            logger.error(f"Failed to setup replay components: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Component setup failed: {str(e)}")
        
        # 3. Update status to running
        try:
            session.status = "running"
            await audit_service.add_event(
                db,
                action="REPLAY_SESSION_START",
                user_id="system",
                resource=session.symbol,
                details={
                    "eventType": "REPLAY_SESSION_START",
                    "symbol": session.symbol,
                    "replaySessionId": replay_session_id,
                    "replay_session_id": replay_session_id,
                    "strategy_id": session.strategy_id,
                    "strategy_type": session.strategy_type,
                    "params": session.params or {},
                    "params_hash": session.params_hash,
                    "start_time": _iso(session.start_time),
                    "end_time": _iso(session.end_time),
                    "speed": session.speed,
                    "initial_capital": safe_finite_float(session.initial_capital, DEFAULT_INITIAL_CAPITAL),
                    "backtestId": session.backtest_id,
                    "backtest_id": session.backtest_id,
                    "executionMode": "historical_replay",
                },
            )
            await db.commit()
            logger.info(f"Session {replay_session_id} status updated to running")
        except Exception as e:
            logger.error(f"Failed to update session status: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")
        
        # 4. Start strategy and playback in background
        # Capture needed values from session to avoid DetachedInstanceError in background task
        strategy_id_val = session.strategy_id
        strategy_type_val = session.strategy_type or "ma"
        strategy_params = session.params or {}
        # Ensure initial_capital is passed to strategy params so it can be used for position sizing
        strategy_params["initial_capital"] = safe_finite_float(session.initial_capital, DEFAULT_INITIAL_CAPITAL)
        symbol_val = session.symbol
        end_time_val = session.end_time
        backtest_id_val = session.backtest_id
        # Get interval from params (default to 1m)
        interval_val = strategy_params.get("interval", "1m")

        async def run_replay_task():
            try:
                logger.info(f"Starting replay task for session {replay_session_id}")
                logger.info(f"Strategy type: {strategy_type_val}, interval: {interval_val}, params: {strategy_params}")
                
                # Reset paper trading service to clean state with session's initial capital
                await paper_trading_service.reset_session(
                    initial_capital=safe_finite_float(session.initial_capital, DEFAULT_INITIAL_CAPITAL),
                    session_id=replay_session_id
                )

                # Load strategy class
                strategy_cls = get_strategy_class(strategy_type_val)
                if not strategy_cls:
                    raise ValueError(f"Unsupported strategy type: {strategy_type_val}")
                
                logger.info(f"Strategy class loaded: {strategy_cls.__name__}")
                
                # Handle strategy initialization (SignalBasedStrategy needs strategy_type)
                if strategy_cls is SignalBasedStrategy:
                    strategy = strategy_cls(strategy_id=str(strategy_id_val), bus=bus, strategy_type=strategy_type_val)
                else:
                    strategy = strategy_cls(strategy_id=str(strategy_id_val), bus=bus)
                strategy.set_parameters(strategy_params)
                logger.info(
                    f"Strategy {strategy_type_val} initialized: "
                    f"params={strategy_params}, "
                    f"signal_func={'OK' if getattr(strategy, '_signal_func', None) is not None else 'NONE (WARNING!)'}"
                )
                
                # Subscribe the strategy to the bus with specified interval
                logger.info(f"Subscribing to data for {symbol_val} on {interval_val}")
                await adapter.subscribe([symbol_val], interval_val, strategy.on_bar)
                logger.info(f"Subscribed, data loaded: {len(adapter.data)} bars")
                
                # Start playback
                logger.info("Starting playback...")
                await adapter.start_playback()
                
                # Log signal statistics from strategy
                if hasattr(strategy, '_total_bars_processed'):
                    logger.info(
                        f"Replay signal summary for {replay_session_id}: "
                        f"bars_processed={strategy._total_bars_processed}, "
                        f"buy_signals={strategy._total_buy_signals}, "
                        f"sell_signals={strategy._total_sell_signals}, "
                        f"signal_errors={strategy._signal_errors}"
                    )
                    if strategy._total_buy_signals == 0 and strategy._total_sell_signals == 0:
                        logger.warning(
                            f"⚠️ 回放 {replay_session_id} 零信号! "
                            f"策略类型={strategy_type_val}, 参数={strategy_params}, "
                            f"处理K线数={strategy._total_bars_processed}, 错误数={strategy._signal_errors}"
                        )
                
                logger.info("Playback completed successfully")
                
                # Update status to completed
                async with get_db() as session_db:
                    await session_db.execute(
                        update(ReplaySession)
                        .where(ReplaySession.replay_session_id == replay_session_id)
                        .values(status="completed", current_timestamp=end_time_val)
                    )
                    await audit_service.add_event(
                        session_db,
                        action="REPLAY_COMPLETED",
                        user_id="system",
                        resource=symbol_val,
                        details={
                            "eventType": "REPLAY_COMPLETED",
                            "symbol": symbol_val,
                            "replaySessionId": replay_session_id,
                            "replay_session_id": replay_session_id,
                            "strategy_type": strategy_type_val,
                            "interval": interval_val,
                            "backtestId": backtest_id_val,
                            "backtest_id": backtest_id_val,
                            "executionMode": "historical_replay",
                            "buy_signals": getattr(strategy, '_total_buy_signals', 0) if hasattr(strategy, '_total_buy_signals') else 0,
                            "sell_signals": getattr(strategy, '_total_sell_signals', 0) if hasattr(strategy, '_total_sell_signals') else 0,
                            "bars_processed": getattr(strategy, '_total_bars_processed', 0) if hasattr(strategy, '_total_bars_processed') else 0,
                        },
                    )
                    await session_db.commit()
                    
            except Exception as e:
                import traceback
                error_details = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                logger.error(f"Replay task failed for {replay_session_id}: {error_details}")
                try:
                    async with get_db() as session_db:
                        await session_db.execute(
                            update(ReplaySession)
                            .where(ReplaySession.replay_session_id == replay_session_id)
                            .values(status="failed")
                        )
                        await audit_service.add_event(
                            session_db,
                            action="REPLAY_FAILED",
                            user_id="system",
                            resource=symbol_val,
                            details={
                                "eventType": "REPLAY_FAILED",
                                "symbol": symbol_val,
                                "replaySessionId": replay_session_id,
                                "replay_session_id": replay_session_id,
                                "strategy_type": strategy_type_val,
                                "interval": interval_val,
                                "backtestId": backtest_id_val,
                                "backtest_id": backtest_id_val,
                                "executionMode": "historical_replay",
                                "error": str(e)[:1000],
                            },
                        )
                        await session_db.commit()
                except Exception as db_e:
                    logger.error(f"Failed to update session status to failed: {db_e}")
            finally:
                if replay_session_id in active_replays:
                    del active_replays[replay_session_id]

        background_tasks.add_task(run_replay_task)
        
        return ReplaySessionResponse(
            replay_session_id=replay_session_id,
            status="running",
            message="Historical replay started"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error starting replay {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/sessions", response_model=PaginatedReplaySessionsResponse)
async def list_replay_sessions(
    db: AsyncSession = Depends(get_db_session),
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: str = Query("created_at", description="排序字段: created_at, total_return, trade_count"),
    sort_order: str = Query("desc", description="排序顺序: asc, desc"),
    strategy_type: Optional[str] = Query(None, description="按策略类型筛选"),
    symbol: Optional[str] = Query(None, description="按交易对筛选"),
    saved_only: bool = Query(False, description="仅返回已保存的记录"),
    status: Optional[str] = Query(None, description="按状态筛选: pending, running, completed, failed, paused")
):
    """List replay sessions with pagination, sorting and filtering.
    
    Supports:
    - Pagination: page, page_size
    - Sorting: sort_by (created_at/total_return/trade_count), sort_order (asc/desc)
    - Filtering: strategy_type, symbol, saved_only, status
    - Returns summary metrics per session: total_return, trade_count, final_equity
    """
    try:
        # Build base query with filters
        conditions = []
        if saved_only:
            conditions.append(ReplaySession.is_saved == True)
        if status:
            conditions.append(ReplaySession.status == status)
        if strategy_type:
            conditions.append(ReplaySession.strategy_type == strategy_type)
        if symbol:
            conditions.append(ReplaySession.symbol == symbol.upper())
        
        # Count total matching records
        count_stmt = select(func.count(ReplaySession.id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar() or 0
        
        # Calculate pagination
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        offset = (page - 1) * page_size
        
        # Build main query with sorting
        stmt = select(ReplaySession)
        if conditions:
            stmt = stmt.where(*conditions)
        
        # Apply sorting
        if sort_by == "created_at":
            order_col = ReplaySession.created_at
        elif sort_by == "total_return":
            # For total_return, we need to sort by metrics JSONB field or PNL
            # Since metrics may not always be populated, fallback to created_at
            order_col = ReplaySession.created_at  # Sorting by metrics will be done in-memory
        elif sort_by == "trade_count":
            order_col = ReplaySession.created_at  # Sorting by trade_count will be done in-memory
        else:
            order_col = ReplaySession.created_at
        
        if sort_order.lower() == "asc":
            stmt = stmt.order_by(order_col.asc())
        else:
            stmt = stmt.order_by(order_col.desc())
        
        stmt = stmt.offset(offset).limit(page_size)
        
        result = await db.execute(stmt)
        sessions = result.scalars().all()
        
        # Build response list with PNL info and summary metrics
        response_list = []
        for s in sessions:
            # Calculate PNL and trade count
            pnl = 0.0
            trade_count = 0
            try:
                pnl_stmt = select(func.sum(PaperTrade.pnl), func.count(PaperTrade.id)).where(
                    PaperTrade.session_id == s.replay_session_id
                )
                pnl_result = await db.execute(pnl_stmt)
                row = pnl_result.one()
                pnl = float(row[0] or 0.0)
                trade_count = int(row[1] or 0)
            except Exception:
                pass
            
            # Build summary metrics
            initial_cap = safe_finite_float(s.initial_capital, DEFAULT_INITIAL_CAPITAL)
            final_equity = initial_cap + pnl
            total_return = (pnl / initial_cap * 100) if initial_cap > 0 else 0.0
            
            # Extract metrics from session if available
            metrics_data = s.metrics if hasattr(s, 'metrics') and s.metrics else {}
            win_rate = metrics_data.get('win_rate')
            max_drawdown = metrics_data.get('max_drawdown')
            
            # If metrics has total_return, use it instead
            if 'total_return' in metrics_data:
                total_return = metrics_data['total_return']
            if 'final_equity' in metrics_data:
                final_equity = metrics_data['final_equity']
            
            summary = SessionSummaryMetrics(
                total_return=round(total_return, 4),
                trade_count=trade_count,
                final_equity=round(final_equity, 2),
                win_rate=win_rate,
                max_drawdown=max_drawdown
            )
            
            response_list.append(ReplaySessionListItem(
                replay_session_id=s.replay_session_id,
                strategy_id=s.strategy_id,
                strategy_type=s.strategy_type,
                params=s.params,
                symbol=s.symbol,
                start_time=s.start_time,
                end_time=s.end_time,
                speed=s.speed,
                initial_capital=s.initial_capital,
                status=s.status,
                current_timestamp=s.current_timestamp,
                is_saved=s.is_saved if hasattr(s, 'is_saved') else False,
                created_at=s.created_at,
                pnl=pnl,
                data_source=s.data_source if hasattr(s, 'data_source') else 'REPLAY',
                backtest_id=s.backtest_id if hasattr(s, 'backtest_id') else None,
                params_hash=s.params_hash if hasattr(s, 'params_hash') else None,
                metrics=metrics_data,
                summary=summary
            ))
        
        # Post-sort by total_return or trade_count if requested (in-memory for current page)
        if sort_by == "total_return":
            response_list.sort(
                key=lambda x: x.summary.total_return if x.summary and x.summary.total_return else 0,
                reverse=(sort_order.lower() == "desc")
            )
        elif sort_by == "trade_count":
            response_list.sort(
                key=lambda x: x.summary.trade_count if x.summary else 0,
                reverse=(sort_order.lower() == "desc")
            )
        
        return PaginatedReplaySessionsResponse(
            sessions=response_list,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        logger.error(f"Failed to list replay sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

import math

def _safe_float(value: float, default: float = 0.0) -> float:
    """Convert float value, replacing NaN/Inf with default."""
    if value is None:
        return default
    if math.isnan(value) or math.isinf(value):
        return default
    return value

@router.get("/{replay_session_id}/status", response_model=ReplayStatusResponse)
async def get_replay_status(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Query current status, progress and PNL of a replay session."""
    try:
        import math
        stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        current_time = session.current_timestamp
        progress = 0.0
        pnl = 0.0
        elapsed_seconds = None
        
        # Health summary defaults
        error_count = 0
        warnings = []
        bars_processed = 0
        bars_total = 0

        # If active, get real-time info
        if replay_session_id in active_replays:
            adapter = active_replays[replay_session_id]
            current_time = adapter.get_current_simulated_time()
            if adapter.data and len(adapter.data) > 0:
                data_len = len(adapter.data)
                cursor = adapter.cursor if adapter.cursor is not None else 0
                if data_len > 0:
                    progress = min(1.0, max(0.0, cursor / data_len))
                else:
                    progress = 0.0
            else:
                progress = 0.0
            # Get actual elapsed time
            elapsed_seconds = adapter.get_elapsed_real_time()
            # Get health summary from adapter
            health = adapter.get_health_summary()
            error_count = health.get("error_count", 0)
            warnings = health.get("warnings", [])
            bars_processed = health.get("bars_processed", 0)
            bars_total = health.get("bars_total", 0)
                
        # Calculate progress if not active but has current_timestamp
        elif session.current_timestamp and session.start_time and session.end_time:
            total_duration = (session.end_time - session.start_time).total_seconds()
            if total_duration > 0:
                elapsed = (session.current_timestamp - session.start_time).total_seconds()
                progress = min(1.0, max(0.0, elapsed / total_duration))

        # Calculate PNL from trades and positions
        try:
            # 1. Realized PNL from trades
            from app.models.db_models import PaperTrade, PaperPosition
            from sqlalchemy import func
            pnl_stmt = select(func.sum(PaperTrade.pnl)).where(PaperTrade.session_id == replay_session_id)
            pnl_result = await db.execute(pnl_stmt)
            realized_pnl = float(pnl_result.scalar() or 0.0)
            
            # 2. Unrealized PNL from open positions
            unrealized_pnl = 0.0
            pos_stmt = select(PaperPosition).where(PaperPosition.session_id == replay_session_id)
            pos_result = await db.execute(pos_stmt)
            positions = pos_result.scalars().all()
            
            if positions:
                # Get current mark price for the replay
                mark_price = None
                if replay_session_id in active_replays:
                    adapter = active_replays[replay_session_id]
                    if adapter.data and adapter.cursor < len(adapter.data):
                        raw_mark_price = adapter.data[adapter.cursor].close
                        # Sanitize mark_price to avoid NaN
                        if raw_mark_price is not None and not (isinstance(raw_mark_price, float) and math.isnan(raw_mark_price)):
                            mark_price = raw_mark_price
                
                if mark_price:
                    for pos in positions:
                        qty = float(pos.quantity)
                        avg = float(pos.avg_price)
                        unrealized_pnl += (mark_price - avg) * qty
            
            pnl = realized_pnl + unrealized_pnl
        except Exception as e:
            logger.warning(f"Failed to calculate PNL for session {replay_session_id}: {e}")

        # Sanitize float values before returning
        progress = _safe_float(progress)
        pnl = _safe_float(pnl)
        elapsed_seconds = _safe_float(elapsed_seconds, default=None)
        if elapsed_seconds is not None and elapsed_seconds < 0:
            elapsed_seconds = 0.0

        return ReplayStatusResponse(
            replay_session_id=replay_session_id,
            status=session.status,
            current_simulated_time=current_time,
            progress=progress,
            pnl=pnl,
            elapsed_seconds=elapsed_seconds,
            error_count=error_count,
            warnings=warnings,
            bars_processed=bars_processed,
            bars_total=bars_total
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get replay status for {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.post("/{replay_session_id}/pause", response_model=ReplaySessionResponse)
async def pause_replay(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Pause the historical replay."""
    try:
        if replay_session_id not in active_replays:
            raise HTTPException(status_code=400, detail="Replay session is not active or already completed")
        
        adapter = active_replays[replay_session_id]
        adapter.pause_playback()
        
        # Update DB
        current_time = adapter.data[adapter.cursor].datetime if adapter.data and adapter.cursor < len(adapter.data) else None
        await db.execute(
            update(ReplaySession)
            .where(ReplaySession.replay_session_id == replay_session_id)
            .values(status="paused", current_timestamp=current_time)
        )
        await db.commit()
        
        return ReplaySessionResponse(
            replay_session_id=replay_session_id,
            status="paused",
            message="Historical replay paused"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause replay {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")

@router.post("/{replay_session_id}/resume", response_model=ReplaySessionResponse)
async def resume_replay(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Resume a paused historical replay."""
    try:
        if replay_session_id not in active_replays:
            # If it's not in active_replays but status is paused, we might need to restart the task
            # However, for simplicity, let's assume it must be in active_replays (active task)
            raise HTTPException(status_code=400, detail="Replay session task is not active. Please start it again.")
        
        adapter = active_replays[replay_session_id]
        adapter.resume_playback()
        
        # Update DB
        await db.execute(
            update(ReplaySession)
            .where(ReplaySession.replay_session_id == replay_session_id)
            .values(status="running")
        )
        await db.commit()
        
        return ReplaySessionResponse(
            replay_session_id=replay_session_id,
            status="running",
            message="Historical replay resumed"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume replay {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")

@router.post("/{replay_session_id}/jump", response_model=ReplaySessionResponse)
async def jump_replay(
    replay_session_id: str,
    request: ReplayJumpRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Jump to a specific timestamp in historical replay."""
    try:
        if replay_session_id not in active_replays:
            raise HTTPException(status_code=400, detail="Replay session is not active")
        
        adapter = active_replays[replay_session_id]
        target_utc = request.target_timestamp.astimezone(timezone.utc)
        
        adapter.set_start_timestamp(target_utc)
        # Also update the bus's simulated time
        await adapter.bus.jump_to(target_utc)
        # Jump always pauses so the user can resume from the new position
        adapter.pause_playback()
        
        # Update DB
        await db.execute(
            update(ReplaySession)
            .where(ReplaySession.replay_session_id == replay_session_id)
            .values(current_timestamp=target_utc)
        )
        await db.commit()
        
        return ReplaySessionResponse(
            replay_session_id=replay_session_id,
            status="paused", # Jump usually pauses or maintains pause as per SPEC
            message=f"Replay position jumped to {target_utc}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to jump in replay {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Jump operation failed: {str(e)}")

@router.get("/valid-date-range/{symbol}", response_model=ValidDateRangeResponse)
async def get_valid_date_range(symbol: str, interval: str = Query("1m", description="K线周期: 1m, 5m, 15m, 1h, 4h, 1d")):
    """Query valid data range for a specific symbol and interval from ClickHouse."""
    range_info = await clickhouse_service.get_valid_date_range(symbol.upper(), interval)
    return ValidDateRangeResponse(
        symbol=symbol.upper(),
        min_date=range_info["min_date"],
        max_date=range_info["max_date"],
        valid_dates=range_info["valid_dates"]
    )


@router.patch("/{replay_session_id}/save", response_model=ReplaySessionResponse)
async def toggle_save_replay_session(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Toggle save status of a replay session. If saved, unsave. If not saved, save it."""
    try:
        stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        # Toggle save status
        current_saved = session.is_saved if hasattr(session, 'is_saved') else False
        new_saved = not current_saved
        
        await db.execute(
            update(ReplaySession)
            .where(ReplaySession.replay_session_id == replay_session_id)
            .values(is_saved=new_saved, updated_at=datetime.now(timezone.utc))
        )
        await db.commit()
        
        action = "saved" if new_saved else "unsaved"
        logger.info(f"Replay session {replay_session_id} {action}")
        
        return ReplaySessionResponse(
            replay_session_id=replay_session_id,
            status=session.status,
            message=f"Replay session {action} successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle save status for {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Save operation failed: {str(e)}")


@router.get("/{replay_session_id}/stats", response_model=ReplayTradeStatsResponse)
async def get_replay_trade_stats(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Get detailed trade statistics for a replay session."""
    try:
        # Fetch session info
        stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        # Fetch all trades for this session
        trades_stmt = select(PaperTrade).where(PaperTrade.session_id == replay_session_id).order_by(PaperTrade.created_at)
        trades_result = await db.execute(trades_stmt)
        trades = trades_result.scalars().all()
        
        # Calculate statistics
        total_trades = len(trades)
        winning_trades = 0
        losing_trades = 0
        total_pnl = 0.0
        total_fees = 0.0
        wins = []
        losses = []
        
        for trade in trades:
            if trade.pnl is not None:
                pnl_val = float(trade.pnl)
                total_pnl += pnl_val
                if pnl_val > 0:
                    winning_trades += 1
                    wins.append(pnl_val)
                elif pnl_val < 0:
                    losing_trades += 1
                    losses.append(abs(pnl_val))
            if trade.fee is not None:
                total_fees += float(trade.fee)
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        max_profit = max(wins) if wins else 0.0
        max_loss = max(losses) if losses else 0.0
        
        # Calculate final equity and returns
        initial_capital = safe_finite_float(session.initial_capital, DEFAULT_INITIAL_CAPITAL)
        final_equity = initial_capital + total_pnl
        returns_pct = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0.0
        
        return ReplayTradeStatsResponse(
            replay_session_id=replay_session_id,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=round(win_rate, 2),
            total_pnl=round(total_pnl, 2),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            total_fees=round(total_fees, 2),
            final_equity=round(final_equity, 2),
            returns_pct=round(returns_pct, 2)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trade stats for {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get trade stats: {str(e)}")


@router.get("/{replay_session_id}/metrics")
async def get_replay_metrics(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Get computed performance metrics for a replay session.
    Computes metrics on-demand if not already stored."""
    from app.models.db_models import ReplaySession
    from sqlalchemy import select

    async with get_db_session() as session:
        stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await session.execute(stmt)
        session_row = result.scalar_one_or_none()

        if not session_row:
            raise HTTPException(status_code=404, detail="Replay session not found")

        # Return stored metrics or compute on-demand
        if session_row.metrics and session_row.metrics != {}:
            return {"session_id": replay_session_id, "metrics": session_row.metrics, "computed": False}

        # Compute on-demand
        try:
            metrics = await replay_metrics_service.compute_and_store_metrics(replay_session_id)
            return {"session_id": replay_session_id, "metrics": metrics, "computed": True}
        except Exception as e:
            logger.error(f"Failed to compute metrics: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to compute metrics: {e}")


@router.get("/{replay_session_id}/suggest-backtest")
async def suggest_backtest_matches(
    replay_session_id: str,
    limit: int = Query(3, ge=1, le=10),
    db: AsyncSession = Depends(get_db_session)
):
    """Suggest matching backtest records for a replay session."""
    try:
        matches = await replay_metrics_service.suggest_backtest_matches(replay_session_id, limit=limit)
        return {"session_id": replay_session_id, "matches": matches, "count": len(matches)}
    except Exception as e:
        logger.error(f"Failed to suggest backtest matches: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {e}")


@router.get("/{replay_session_id}/aligned-equity")
async def get_aligned_equity(
    replay_session_id: str,
    backtest_id: Optional[int] = Query(None, description="Specific backtest ID to align with"),
    db: AsyncSession = Depends(get_db_session)
):
    """Get time-aligned equity curves for replay vs backtest comparison."""
    from app.models.db_models import ReplaySession, BacktestResult
    from sqlalchemy import select

    async with get_db_session() as session:
        # Get session
        stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await session.execute(stmt)
        replay = result.scalar_one_or_none()

        if not replay:
            raise HTTPException(status_code=404, detail="Replay session not found")

        # Resolve backtest_id
        bt_id = backtest_id
        if not bt_id and hasattr(replay, 'backtest_id') and replay.backtest_id:
            bt_id = replay.backtest_id

        if not bt_id:
            # Auto-suggest: get first match
            matches = await replay_metrics_service.suggest_backtest_matches(replay_session_id, limit=1)
            if matches:
                bt_id = matches[0]["id"]

        if not bt_id:
            raise HTTPException(status_code=400, detail="No backtest_id provided and no auto-match found")

        # Get aligned curves
        try:
            aligned = await replay_metrics_service.align_equity_curves(replay_session_id, bt_id)
            return aligned
        except Exception as e:
            logger.error(f"Failed to align equity curves: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to align curves: {e}")


@router.post("/{replay_session_id}/quick-backtest", response_model=QuickBacktestResponse)
async def quick_backtest_from_session(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Run a quick backtest using the same parameters as a replay session.
    
    Extracts strategy_type, symbol, interval, start_time, end_time, initial_capital,
    and strategy_params from the replay session, then runs a backtest and saves results.
    
    Returns:
        backtest_id: ID of the saved backtest result for analytics comparison
        status: "completed" on success
        metrics: Backtest performance metrics
    
    Errors:
        404: Session not found
        400: Session not completed (still running)
        500: Backtest execution failed
    """
    from app.services.backtester import EventDrivenBacktester
    from app.services.strategy_templates import build_signal_func
    from app.models.db_models import BacktestResult
    import pandas as pd
    
    try:
        # 1. Fetch the replay session
        stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        # 2. Check session status - must be completed
        if session.status == "running":
            raise HTTPException(
                status_code=400, 
                detail="Session must be completed before running backtest. Current status: running"
            )
        if session.status == "pending":
            raise HTTPException(
                status_code=400,
                detail="Session must be completed before running backtest. Current status: pending"
            )
        
        # 3. Extract parameters from session
        strategy_type = session.strategy_type or "ma"
        symbol = session.symbol
        params = session.params or {}
        interval = params.get("interval", "1m")
        start_time = session.start_time
        end_time = session.end_time
        initial_capital = safe_finite_float(session.initial_capital, DEFAULT_INITIAL_CAPITAL)
        
        # Keep interval in params for comparison purposes (it's important for replay-backtest comparison)
        # Note: interval is also stored separately in BacktestResult.interval field
        strategy_params = dict(params)  # Keep all params including interval
        
        logger.info(f"Quick backtest: {strategy_type} on {symbol}/{interval} from {start_time} to {end_time}")
        
        # 4. Fetch historical data from ClickHouse
        df = await clickhouse_service.get_klines_dataframe(
            symbol=symbol,
            interval=interval,
            start=start_time,
            end=end_time
        )
        
        if df is None or len(df) < 10:
            raise HTTPException(
                status_code=500, 
                detail=f"Insufficient historical data for backtest. Got {len(df) if df is not None else 0} bars."
            )
        
        logger.info(f"Loaded {len(df)} bars for backtest")
        params_hash = stable_params_hash(strategy_params) if strategy_params else session.params_hash
        pit_metadata = enrich_pit_metadata(
            _build_quick_backtest_pit_metadata(
                df=df,
                replay_session_id=replay_session_id,
                start_time=start_time,
                end_time=end_time,
                data_source="clickhouse:klines",
            ),
            symbol=symbol,
            interval=interval,
            strategy_type=strategy_type,
            params=strategy_params,
            params_hash=params_hash,
            data_source="clickhouse:klines",
            replay_session_id=replay_session_id,
        )
        
        # 5. Build signal function and run backtest
        try:
            signal_func = build_signal_func(strategy_type, strategy_params)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid strategy configuration: {str(e)}")
        
        try:
            backtester = EventDrivenBacktester(
                df=df,
                signal_func=signal_func,
                initial_capital=initial_capital,
            )
            backtest_result = backtester.run()
        except Exception as e:
            logger.error(f"Backtest execution failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Backtest execution failed: {str(e)}")
        
        # 6. Prepare metrics dict
        metrics_dict = {
            "total_return": backtest_result["total_return"],
            "annual_return": backtest_result["annual_return"],
            "max_drawdown": backtest_result["max_drawdown"],
            "sharpe_ratio": backtest_result["sharpe_ratio"],
            "win_rate": backtest_result["win_rate"],
            "profit_factor": backtest_result["profit_factor"],
            "total_trades": backtest_result["total_trades"],
            "total_commission": backtest_result.get("total_commission", 0.0),
            "initial_capital": initial_capital,
            "final_capital": backtest_result["final_capital"],
            "pit": pit_metadata,
        }
        
        # 7. Prepare equity curve (downsample if needed)
        equity_values = backtest_result["equity_curve"]
        step = max(1, len(equity_values) // 500)
        equity_curve = [
            {"t": str(df.index[i])[:19], "v": round(equity_values[i], 2)}
            for i in range(0, min(len(equity_values), len(df)), step)
        ]
        
        # 8. params_hash links replay and backtest records with identical settings.
        # 9. Save to database
        bt_row = BacktestResult(
            strategy_type=strategy_type,
            symbol=symbol,
            interval=interval,
            params=strategy_params,
            metrics=metrics_dict,
            equity_curve=equity_curve[:2000],
            trades_summary=backtest_result["trades"][:100],
            data_source='QUICK_BACKTEST',
            params_hash=params_hash,
        )
        db.add(bt_row)
        await db.flush()
        backtest_id = bt_row.id
        
        # 10. Update replay session with backtest_id link
        await db.execute(
            update(ReplaySession)
            .where(ReplaySession.replay_session_id == replay_session_id)
            .values(backtest_id=backtest_id)
        )
        await audit_service.add_event(
            db,
            action="REPLAY_QUICK_BACKTEST_RUN",
            user_id="system",
            resource=symbol,
            details={
                "eventType": "REPLAY_QUICK_BACKTEST_RUN",
                "symbol": symbol,
                "replaySessionId": replay_session_id,
                "replay_session_id": replay_session_id,
                "backtestId": backtest_id,
                "backtest_id": backtest_id,
                "strategy_type": strategy_type,
                "interval": interval,
                "params": strategy_params,
                "pit": pit_metadata,
                "executionMode": "quick_backtest",
                "metrics": {
                    "total_return": metrics_dict["total_return"],
                    "max_drawdown": metrics_dict["max_drawdown"],
                    "total_trades": metrics_dict["total_trades"],
                },
            },
        )
        await db.commit()
        
        logger.info(f"Quick backtest completed: backtest_id={backtest_id}, return={metrics_dict['total_return']:.2f}%")
        
        return QuickBacktestResponse(
            backtest_id=backtest_id,
            status="completed",
            metrics=metrics_dict,
            message=f"Backtest completed successfully. Total return: {metrics_dict['total_return']:.2f}%"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quick backtest failed for session {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Quick backtest failed: {str(e)}")


@router.post("/estimate-time", response_model=TimeEstimateResponse)
async def estimate_replay_time(
    request: TimeEstimateRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Estimate the time required for a historical replay.
    
    Calculates based on:
    - Number of data bars in the requested range
    - Replay speed setting
    - Strategy complexity factor
    - High-speed degradation coefficient
    
    Returns:
        estimated_seconds: Estimated wall-clock time to complete the replay
        bar_count: Number of K-line bars in the data range
        notes: Any warnings about high-speed degradation
        breakdown: Detailed calculation factors
    """
    try:
        # 1. Query bar count from ClickHouse
        bar_count = await clickhouse_service.get_bar_count(
            symbol=request.symbol.upper(),
            interval=request.interval,
            start_time=request.start_time,
            end_time=request.end_time
        )
        
        if bar_count == 0:
            return TimeEstimateResponse(
                estimated_seconds=0,
                bar_count=0,
                notes="No data found in the specified range",
                breakdown={"reason": "no_data"}
            )
        
        # 2. Calculate base time
        speed = request.speed
        if speed == -1:  # Max speed / instant mode
            # Instant mode: estimate based on processing time (~1000 bars/sec)
            base_time_seconds = bar_count / 1000.0
        else:
            base_time_seconds = bar_count / speed
        
        # 3. Strategy complexity factor
        complexity_factors = {
            "ma": 1.0,
            "rsi": 1.1,
            "boll": 1.2,
            "macd": 1.3,
            "ema_triple": 1.15,
            "atr_trend": 1.25,
            "turtle": 1.3,
            "ichimoku": 1.4,
        }
        complexity_factor = complexity_factors.get(request.strategy_type.lower(), 1.0)
        
        # 4. High-speed degradation coefficient
        degradation = 1.0
        notes = None
        if speed > 100 and speed != -1:
            degradation = 1 + (speed - 100) * 0.001
            notes = f"高倍速({speed}x)可能有性能衰减，实际时间可能比预估更长"
        elif speed == -1:
            notes = "最高速模式，估算基于系统处理能力"
        
        # 5. Calculate final estimate
        estimated_seconds = base_time_seconds * complexity_factor * degradation
        
        # 6. Build breakdown
        breakdown = {
            "bar_count": bar_count,
            "speed": speed,
            "base_time_seconds": round(base_time_seconds, 2),
            "complexity_factor": complexity_factor,
            "degradation_factor": round(degradation, 4),
            "strategy_type": request.strategy_type,
        }
        
        return TimeEstimateResponse(
            estimated_seconds=round(estimated_seconds, 2),
            bar_count=bar_count,
            notes=notes,
            breakdown=breakdown
        )
        
    except Exception as e:
        logger.error(f"Failed to estimate replay time: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Time estimation failed: {str(e)}")


@router.get("/{replay_session_id}/trades", response_model=ReplayTradesResponse)
async def get_replay_trades(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Get trade list for a replay session with markers for chart display."""
    logger.info(f"get_replay_trades called for session: {replay_session_id}")
    try:
        # Verify session exists
        session_stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(session_stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        # Fetch all trades for this session
        trades_stmt = select(PaperTrade).where(
            PaperTrade.session_id == replay_session_id
        ).order_by(PaperTrade.created_at)
        trades_result = await db.execute(trades_stmt)
        trades = trades_result.scalars().all()
        
        logger.info(f"Found {len(trades)} trades for session {replay_session_id}")
        
        # Convert to markers
        markers = []
        for trade in trades:
            markers.append(ReplayTradeMarker(
                time=trade.created_at.isoformat() if trade.created_at else None,
                price=float(trade.price) if trade.price else 0.0,
                side=trade.side,
                quantity=float(trade.quantity) if trade.quantity else 0.0,
                pnl=float(trade.pnl) if trade.pnl else None
            ))
        
        return ReplayTradesResponse(
            trades=markers,
            total_count=len(markers)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trades for {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get trades: {str(e)}")


@router.get("/{replay_session_id}/equity-curve", response_model=ReplayEquityCurveResponse)
async def get_replay_equity_curve(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Get equity curve data for a replay session.
    
    Returns:
        equity_curve: List of {t: timestamp, v: value} points
        baseline_curve: Buy-and-hold baseline calculated from K-line data
        markers: Trade markers for buy/sell points
        initial_capital: Starting capital for the session
    """
    try:
        # Fetch session info
        session_stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(session_stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        initial_capital = safe_finite_float(session.initial_capital, DEFAULT_INITIAL_CAPITAL)
        params = session.params or {}
        interval = params.get("interval", "1m")
        
        # Fetch equity snapshots for this session
        snapshots_stmt = select(EquitySnapshot).where(
            EquitySnapshot.session_id == replay_session_id
        ).order_by(EquitySnapshot.timestamp)
        snapshots_result = await db.execute(snapshots_stmt)
        snapshots = snapshots_result.scalars().all()
        
        # Build equity curve
        equity_curve = []
        equity_timestamps = []  # Keep track of timestamps for baseline alignment
        
        if snapshots:
            for snap in snapshots:
                ts = snap.timestamp.isoformat() if snap.timestamp else ""
                equity_curve.append({
                    "t": ts,
                    "v": safe_finite_float(snap.total_equity, initial_capital)
                })
                if snap.timestamp:
                    equity_timestamps.append(snap.timestamp)
        else:
            # Fallback: construct from trades
            trades_stmt = select(PaperTrade).where(
                PaperTrade.session_id == replay_session_id
            ).order_by(PaperTrade.created_at)
            trades_result = await db.execute(trades_stmt)
            trades = trades_result.scalars().all()
            
            # Build equity curve from trades
            equity = initial_capital
            equity_curve = [{"t": session.start_time.isoformat(), "v": equity}]
            equity_timestamps.append(session.start_time)
            
            for trade in trades:
                if trade.pnl:
                    equity += float(trade.pnl)
                equity_curve.append({
                    "t": trade.created_at.isoformat() if trade.created_at else None,
                    "v": equity
                })
                if trade.created_at:
                    equity_timestamps.append(trade.created_at)
            
            # Add end point if session is completed
            if session.status == "completed" and session.end_time:
                equity_curve.append({
                    "t": session.end_time.isoformat(),
                    "v": equity
                })
                equity_timestamps.append(session.end_time)
        
        # Calculate baseline curve (buy-and-hold)
        baseline_curve = []
        try:
            # Fetch K-line data for baseline calculation
            effective_end = session.current_timestamp or session.end_time
            df = await clickhouse_service.get_klines_dataframe(
                symbol=session.symbol,
                interval=interval,
                start=session.start_time,
                end=effective_end
            )
            
            if df is not None and len(df) > 0:
                # Remove duplicate timestamps and ensure ascending order for baseline calculation
                df = df[~df.index.duplicated(keep='last')]
                df = df.sort_index()
                
                # Get base price (first close price)
                base_price = float(df.iloc[0]['close'])
                
                if base_price > 0:
                    # Build baseline curve aligned with equity curve timestamps
                    # Create a price lookup dict from DataFrame
                    price_map = {}
                    for idx in df.index:
                        ts_str = str(idx)[:19]
                        price_map[ts_str] = safe_float(df.loc[idx]['close'])
                    
                    # For each equity timestamp, find closest price and calculate baseline
                    for ec_point in equity_curve:
                        t_str = ec_point["t"][:19] if ec_point.get("t") else ""
                        
                        # Try exact match first
                        if t_str in price_map:
                            current_price = price_map[t_str]
                        else:
                            # Find closest earlier timestamp
                            matching_keys = [k for k in price_map.keys() if k <= t_str]
                            if matching_keys:
                                closest_key = max(matching_keys)
                                current_price = price_map[closest_key]
                            elif price_map:
                                # Use first available price if all are later
                                current_price = list(price_map.values())[0]
                            else:
                                current_price = base_price
                        
                        baseline_value = initial_capital * (current_price / base_price)
                        baseline_curve.append({
                            "t": ec_point["t"],
                            "v": round(baseline_value, 2)
                        })
        except Exception as e:
            logger.warning(f"Failed to calculate baseline curve: {e}")
            # Continue without baseline if calculation fails
        
        # Fetch trades for markers
        trades_stmt = select(PaperTrade).where(
            PaperTrade.session_id == replay_session_id
        ).order_by(PaperTrade.created_at)
        trades_result = await db.execute(trades_stmt)
        trades = trades_result.scalars().all()
        
        markers = []
        for trade in trades:
            markers.append(ReplayTradeMarker(
                time=trade.created_at.isoformat() if trade.created_at else None,
                price=float(trade.price) if trade.price else 0.0,
                side=trade.side,
                quantity=float(trade.quantity) if trade.quantity else 0.0,
                pnl=float(trade.pnl) if trade.pnl else None
            ))
        
        # Deduplicate equity_curve by timestamp (keep last value for each timestamp)
        if equity_curve:
            seen_times = {}
            for point in equity_curve:
                seen_times[point["t"]] = point
            equity_curve = list(seen_times.values())
            # Sort by timestamp to ensure ascending order
            equity_curve.sort(key=lambda x: x["t"])
        
        # Deduplicate baseline_curve by timestamp as well
        if baseline_curve:
            seen_times = {}
            for point in baseline_curve:
                seen_times[point["t"]] = point
            baseline_curve = list(seen_times.values())
            baseline_curve.sort(key=lambda x: x["t"])
        
        # Align marker times to nearest equity_curve timestamp (snap to nearest snapshot time)
        if markers and equity_curve:
            equity_times = [point["t"] for point in equity_curve]
            for marker in markers:
                if marker.time and equity_times:
                    marker_time = marker.time[:19]  # Normalize to same format
                    # Find the nearest equity timestamp
                    nearest_time = min(equity_times, key=lambda et: abs(
                        datetime.fromisoformat(et[:19]).timestamp() - 
                        datetime.fromisoformat(marker_time).timestamp()
                    ) if et else float('inf'))
                    # Update marker time to match equity curve format
                    marker.time = nearest_time
        
        return ReplayEquityCurveResponse(
            equity_curve=equity_curve,
            baseline_curve=baseline_curve,
            markers=markers,
            initial_capital=initial_capital
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get equity curve for {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get equity curve: {str(e)}")


@router.get("/{replay_session_id}/klines", response_model=ReplayKlineResponse)
async def get_replay_klines(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Get K-line OHLCV data and technical indicators for a replay session.
    
    Returns:
        klines: List of KlineBar objects with OHLCV data
        indicators: Dict of indicator name to list of IndicatorData based on strategy_type
        strategy_type: The strategy type used
        params: Strategy parameters
    
    Indicator computation based on strategy_type:
        - ma: ma_short, ma_long (Simple Moving Averages)
        - rsi: rsi (Relative Strength Index)
        - boll: upper, middle, lower (Bollinger Bands)
        - macd: macd, signal, histogram (MACD)
    """
    try:
        # 1. Fetch session info
        session_stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(session_stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        symbol = session.symbol
        start_time = session.start_time
        end_time = session.end_time
        current_timestamp = session.current_timestamp
        strategy_type = session.strategy_type or "ma"
        params = session.params or {}
        interval = params.get("interval", "1m")
        
        # 2. Determine effective end time (use current_timestamp if replay is in progress)
        effective_end = current_timestamp if current_timestamp and session.status == "running" else end_time
        
        # 3. Fetch K-line data from ClickHouse
        df = await clickhouse_service.get_klines_dataframe(
            symbol=symbol,
            interval=interval,
            start=start_time,
            end=effective_end
        )
        
        if df is None or len(df) == 0:
            return ReplayKlineResponse(
                klines=[],
                indicators={},
                strategy_type=strategy_type,
                params=params
            )
        
        # 3.5 Remove duplicate timestamps and ensure ascending order
        # This prevents frontend error: "data must be asc ordered by time"
        df = df[~df.index.duplicated(keep='last')]
        df = df.sort_index()
        
        # 4. Convert DataFrame to KlineBar list
        klines = []
        times = []
        closes = []
        highs = []
        lows = []
        
        for idx in df.index:
            row = df.loc[idx]
            time_str = str(idx)[:19] if hasattr(idx, '__str__') else str(row.get('datetime', ''))[:19]
            klines.append(KlineBar(
                time=time_str,
                open=safe_float(row['open']),
                high=safe_float(row['high']),
                low=safe_float(row['low']),
                close=safe_float(row['close']),
                volume=safe_float(row.get('volume', 0))
            ))
            times.append(time_str)
            closes.append(safe_float(row['close']))
            highs.append(safe_float(row['high']))
            lows.append(safe_float(row['low']))
        
        # 5. Compute technical indicators based on strategy type
        indicators = compute_indicators(closes, times, strategy_type, params, highs=highs, lows=lows)
        
        return ReplayKlineResponse(
            klines=klines,
            indicators=indicators,
            strategy_type=strategy_type,
            params=params
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get klines for {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get klines: {str(e)}")


@router.get("/{replay_session_id}/position", response_model=ReplayPositionResponse)
async def get_replay_position(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Get current position status for a replay session.
    
    Returns:
        has_position: Whether there is an open position
        side: "LONG" | "SHORT" | ""
        quantity: Position size
        avg_price: Average entry price
        current_price: Latest market price
        unrealized_pnl: Unrealized profit/loss
        unrealized_pnl_pct: Unrealized P&L as percentage
    """
    try:
        # 1. Verify session exists
        session_stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(session_stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        # 2. Get all trades for this session, ordered by time
        trades_stmt = select(PaperTrade).where(
            PaperTrade.session_id == replay_session_id
        ).order_by(PaperTrade.created_at)
        trades_result = await db.execute(trades_stmt)
        trades = trades_result.scalars().all()
        
        # 3. Calculate net position by iterating through trades
        net_quantity = 0.0
        total_cost = 0.0  # For calculating weighted average price
        
        for trade in trades:
            qty = float(trade.quantity) if trade.quantity else 0.0
            price = float(trade.price) if trade.price else 0.0
            
            if trade.side == "BUY":
                # Add to position
                if net_quantity >= 0:
                    # Adding to long or opening long
                    total_cost += qty * price
                    net_quantity += qty
                else:
                    # Closing short position
                    if qty >= abs(net_quantity):
                        # Flip to long
                        remaining = qty - abs(net_quantity)
                        net_quantity = remaining
                        total_cost = remaining * price
                    else:
                        # Reduce short
                        ratio = (abs(net_quantity) - qty) / abs(net_quantity) if abs(net_quantity) > 0 else 0
                        total_cost *= ratio
                        net_quantity += qty
            elif trade.side == "SELL":
                # Reduce or reverse position
                if net_quantity <= 0:
                    # Adding to short or opening short
                    total_cost += qty * price
                    net_quantity -= qty
                else:
                    # Closing long position
                    if qty >= net_quantity:
                        # Flip to short
                        remaining = qty - net_quantity
                        net_quantity = -remaining
                        total_cost = remaining * price if remaining > 0 else 0.0
                    else:
                        # Reduce long
                        ratio = (net_quantity - qty) / net_quantity if net_quantity > 0 else 0
                        total_cost *= ratio
                        net_quantity -= qty
        
        # 4. Calculate average price
        avg_price = 0.0
        if abs(net_quantity) > 0.0001:
            avg_price = total_cost / abs(net_quantity)
        
        # 5. Get current price from latest K-line or active adapter
        current_price = 0.0
        
        # Try to get from active replay adapter first
        if replay_session_id in active_replays:
            adapter = active_replays[replay_session_id]
            if adapter.data and adapter.cursor < len(adapter.data):
                current_price = float(adapter.data[adapter.cursor].close)
        
        # If not available, fetch latest from ClickHouse
        if current_price == 0.0:
            params = session.params or {}
            interval = params.get("interval", "1m")
            effective_end = session.current_timestamp or session.end_time
            
            df = await clickhouse_service.get_klines_dataframe(
                symbol=session.symbol,
                interval=interval,
                start=session.start_time,  # 从会话开始时间查询，避免范围过小
                end=effective_end
            )
            if df is not None and len(df) > 0:
                current_price = float(df.iloc[-1]['close'])
        
        # 6. Calculate unrealized P&L
        has_position = abs(net_quantity) > 0.0001
        side = ""
        unrealized_pnl = 0.0
        unrealized_pnl_pct = 0.0
        
        if has_position:
            if net_quantity > 0:
                side = "LONG"
                unrealized_pnl = (current_price - avg_price) * net_quantity
            else:
                side = "SHORT"
                unrealized_pnl = (avg_price - current_price) * abs(net_quantity)
            
            # Calculate percentage
            if avg_price > 0:
                unrealized_pnl_pct = (unrealized_pnl / (avg_price * abs(net_quantity))) * 100
        
        return ReplayPositionResponse(
            has_position=has_position,
            side=side,
            quantity=round(abs(net_quantity), 8),
            avg_price=round(avg_price, 2),
            current_price=round(current_price, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            unrealized_pnl_pct=round(unrealized_pnl_pct, 4)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get position for {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get position: {str(e)}")


@router.get("/{replay_session_id}/events")
async def get_replay_events(
    replay_session_id: str,
    asOfTime: Optional[datetime] = Query(None),
    limit: int = Query(300, ge=20, le=1000),
    db: AsyncSession = Depends(get_db_session),
):
    """Return a player-friendly event stream for a replay session."""
    try:
        session_result = await db.execute(select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id))
        session = session_result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")

        current_as_of = _to_datetime(asOfTime or session.current_timestamp or session.end_time)
        session_start = _to_datetime(session.start_time) or session.start_time
        session_end = _to_datetime(session.end_time) or session.end_time
        params = session.params or {}
        interval = params.get("interval", "1m")
        events: List[Dict[str, Any]] = []

        df = None
        try:
            df = await clickhouse_service.get_klines_dataframe(
                symbol=session.symbol,
                interval=interval,
                start=session_start,
                end=current_as_of,
            )
        except Exception as exc:
            logger.warning("Failed to load replay bars for events: %s", exc)

        current_bar: Optional[Dict[str, Any]] = None
        if df is not None and len(df) > 0:
            df = df[~df.index.duplicated(keep="last")].sort_index()
            for idx, row in df.tail(min(80, limit)).iterrows():
                payload = {
                    "open": safe_finite_float(row.get("open")),
                    "high": safe_finite_float(row.get("high")),
                    "low": safe_finite_float(row.get("low")),
                    "close": safe_finite_float(row.get("close")),
                    "volume": safe_finite_float(row.get("volume")),
                    "interval": interval,
                }
                current_bar = {"time": _iso(idx), **payload}
                events.append(
                    _event_payload(
                        event_id=f"BAR-{replay_session_id}-{_iso(idx)}",
                        event_type="BAR_UPDATED",
                        event_time=idx,
                        symbol=session.symbol,
                        summary=f"K线更新：收盘价 {payload['close']:.2f}",
                        payload=payload,
                    )
                )

        trade_rows = (
            await db.execute(
                select(PaperTrade)
                .where(PaperTrade.session_id == replay_session_id)
                .order_by(PaperTrade.created_at)
            )
        ).scalars().all()
        realized_pnl = 0.0
        for trade in trade_rows:
            trade_time = trade.created_at
            trade_time_cmp = _to_datetime(trade_time)
            if current_as_of and trade_time_cmp and trade_time_cmp > current_as_of:
                continue
            realized_pnl += safe_finite_float(trade.pnl, 0.0)
            order_id = f"PT-{trade.id}"
            payload = {
                "orderId": order_id,
                "clientOrderId": trade.client_order_id,
                "side": trade.side,
                "quantity": safe_finite_float(trade.quantity),
                "price": safe_finite_float(trade.price),
                "fee": safe_finite_float(trade.fee),
                "realizedPnl": safe_finite_float(trade.pnl),
                "source": trade.mode or "historical_replay",
            }
            events.append(
                _event_payload(
                    event_id=f"TRADE-{trade.id}",
                    event_type="PAPER_ORDER_FILLED",
                    event_time=trade_time,
                    symbol=trade.symbol,
                    summary=f"模拟成交：{trade.side} {safe_finite_float(trade.quantity):.6f} @ {safe_finite_float(trade.price):.2f}",
                    payload=payload,
                    related_order_intent_id=trade.client_order_id,
                    related_order_id=order_id,
                )
            )
            events.append(
                _event_payload(
                    event_id=f"PNL-{trade.id}",
                    event_type="PNL_UPDATED",
                    event_time=trade_time,
                    symbol=trade.symbol,
                    summary=f"已实现盈亏更新：{realized_pnl:.2f}",
                    payload={"realizedPnl": realized_pnl, "tradeId": trade.id},
                    related_order_id=order_id,
                )
            )

        snapshot_rows = (
            await db.execute(
                select(EquitySnapshot)
                .where(EquitySnapshot.session_id == replay_session_id)
                .order_by(EquitySnapshot.timestamp)
            )
        ).scalars().all()
        latest_snapshot = None
        for snapshot in snapshot_rows:
            snapshot_time_cmp = _to_datetime(snapshot.timestamp)
            if current_as_of and snapshot_time_cmp and snapshot_time_cmp > current_as_of:
                continue
            latest_snapshot = snapshot
            payload = {
                "accountEquity": safe_finite_float(snapshot.total_equity),
                "cash": safe_finite_float(snapshot.cash_balance),
                "positionValue": safe_finite_float(snapshot.position_value),
                "dailyPnl": safe_finite_float(snapshot.daily_pnl),
                "drawdown": safe_finite_float(snapshot.drawdown),
            }
            events.append(
                _event_payload(
                    event_id=f"EQUITY-{snapshot.id}",
                    event_type="PNL_UPDATED",
                    event_time=snapshot.timestamp,
                    symbol=session.symbol,
                    summary=f"权益快照：{payload['accountEquity']:.2f}",
                    payload=payload,
                )
            )

        position_row = (
            await db.execute(
                select(PaperPosition)
                .where(PaperPosition.session_id == replay_session_id, PaperPosition.symbol == session.symbol)
                .order_by(PaperPosition.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if position_row:
            events.append(
                _event_payload(
                    event_id=f"POSITION-{position_row.id}",
                    event_type="POSITION_UPDATED",
                    event_time=position_row.updated_at,
                    symbol=session.symbol,
                    summary=f"持仓更新：{safe_finite_float(position_row.quantity):.6f}",
                    payload={
                        "quantity": safe_finite_float(position_row.quantity),
                        "avgPrice": safe_finite_float(position_row.avg_price),
                        "leverage": position_row.leverage,
                    },
                )
            )

        audit_rows = (
            await db.execute(select(AuditLog).order_by(AuditLog.created_at.asc()).limit(500))
        ).scalars().all()
        for audit in audit_rows:
            details = audit.details or {}
            if details.get("replay_session_id") != replay_session_id and details.get("replaySessionId") != replay_session_id:
                continue
            event_type = str(details.get("eventType") or audit.action or "AUDIT_RECORDED")
            event_time = _to_datetime(details.get("replayTime") or details.get("replay_time") or details.get("asOfTime")) or audit.created_at
            if current_as_of and event_time and event_time > current_as_of:
                continue
            intent = details.get("intent") if isinstance(details.get("intent"), dict) else {}
            events.append(
                _event_payload(
                    event_id=f"AUDIT-{audit.id}",
                    event_type=event_type if event_type in {
                        "SIGNAL_TRIGGERED",
                        "AGENT_DECISION",
                        "ORDER_INTENT_CREATED",
                        "RISK_CHECK_PASSED",
                        "RISK_BLOCKED",
                        "PAPER_ORDER_FILLED",
                        "PAPER_ORDER_REJECTED",
                        "POSITION_UPDATED",
                        "PNL_UPDATED",
                        "SKIPPED_AGENT_CALL",
                    } else "AUDIT_RECORDED",
                    event_time=event_time,
                    symbol=details.get("symbol") or audit.resource or session.symbol,
                    summary=f"审计记录：{event_type}",
                    payload=details,
                    related_decision_id=details.get("decisionId") or intent.get("decision_id"),
                    related_order_intent_id=details.get("orderIntentId") or intent.get("intent_id"),
                    related_order_id=details.get("orderId"),
                    related_audit_id=audit.id,
                )
            )

        factor_rows = (
            await db.execute(
                text(
                    """
                    SELECT factor_name, factor_value, available_time
                    FROM factor_snapshots
                    WHERE symbol = :symbol AND available_time <= :as_of
                    ORDER BY available_time DESC
                    LIMIT 8
                    """
                ),
                {"symbol": session.symbol, "as_of": current_as_of},
            )
        ).mappings().all() if current_as_of else []
        signal_rows = (
            await db.execute(
                text(
                    """
                    SELECT signal_type, signal_value, confidence, available_time
                    FROM signal_events
                    WHERE symbol = :symbol AND available_time <= :as_of
                    ORDER BY available_time DESC
                    LIMIT 8
                    """
                ),
                {"symbol": session.symbol, "as_of": current_as_of},
            )
        ).mappings().all() if current_as_of else []

        account_equity = safe_finite_float(getattr(latest_snapshot, "total_equity", None), session.initial_capital)
        cash = safe_finite_float(getattr(latest_snapshot, "cash_balance", None), session.initial_capital)
        current_price = safe_finite_float((current_bar or {}).get("close"), 0.0)
        current_position = {
            "quantity": safe_finite_float(getattr(position_row, "quantity", None), 0.0) if position_row else 0.0,
            "avgPrice": safe_finite_float(getattr(position_row, "avg_price", None), 0.0) if position_row else 0.0,
            "side": "LONG" if position_row and safe_finite_float(position_row.quantity) > 0 else "",
        }
        events = _sort_replay_events(_dedupe_replay_events(events))
        event_stats = _build_replay_event_stats(events, execution_mode=(session.metrics or {}).get("executionMode") if isinstance(session.metrics, dict) else None)
        events = events[-limit:]
        duration = max(1.0, (session_end - session_start).total_seconds())
        progress = ((current_as_of - session_start).total_seconds() / duration) if current_as_of else 0.0
        return {
            "schema_version": "replay_events.v1",
            "generated_at": datetime.utcnow().isoformat(),
            "session": {
                "replaySessionId": replay_session_id,
                "symbol": session.symbol,
                "status": session.status,
                "startTime": _iso(session.start_time),
                "endTime": _iso(session.end_time),
                "linkedBacktestId": session.backtest_id,
            },
            "currentAsOfTime": _iso(current_as_of),
            "progress": max(0.0, min(1.0, progress)),
            "currentState": {
                "currentPrice": current_price,
                "currentBar": current_bar,
                "currentFactors": [dict(row) for row in factor_rows],
                "currentSignals": [dict(row) for row in signal_rows],
                "accountEquity": account_equity,
                "cash": cash,
                "currentPosition": current_position,
                "unrealizedPnl": (current_price - current_position["avgPrice"]) * current_position["quantity"] if current_position["quantity"] and current_position["avgPrice"] else 0.0,
                "realizedPnl": realized_pnl,
            },
            "events": events,
            "total": len(events),
            "eventStats": event_stats,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to build replay events for %s: %s", replay_session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to build replay events")


@router.get("/events")
async def query_replay_events(
    replaySessionId: Optional[str] = Query(None),
    backtestId: Optional[int] = Query(None),
    asOfTime: Optional[datetime] = Query(None),
    limit: int = Query(300, ge=20, le=1000),
    db: AsyncSession = Depends(get_db_session),
):
    """Return replay events by replaySessionId or by linked backtestId."""
    replay_session_id = replaySessionId
    if not replay_session_id and backtestId is not None:
        session_result = await db.execute(
            select(ReplaySession)
            .where(ReplaySession.backtest_id == backtestId)
            .order_by(ReplaySession.created_at.desc())
            .limit(1)
        )
        session = session_result.scalar_one_or_none()
        replay_session_id = session.replay_session_id if session else None
    if not replay_session_id:
        return {
            "schema_version": "replay_events.v1",
            "generated_at": datetime.utcnow().isoformat(),
            "session": None,
            "currentAsOfTime": _iso(asOfTime),
            "progress": 0,
            "currentState": {},
            "events": [],
            "total": 0,
            "eventStats": _build_replay_event_stats([]),
            "message": "暂无回放事件",
        }
    return await get_replay_events(
        replay_session_id=replay_session_id,
        asOfTime=asOfTime,
        limit=limit,
        db=db,
    )


# =============================================================================
# GENERIC ROUTES - MUST BE PLACED AFTER ALL SPECIFIC /{replay_session_id}/xxx ROUTES
# FastAPI matches routes top-to-bottom, so generic routes must come last
# =============================================================================

@router.get("/{replay_session_id}", response_model=ReplaySessionDetailResponse)
async def get_replay_session_detail(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Get detailed information about a specific replay session."""
    try:
        stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        # Calculate PNL
        pnl = 0.0
        try:
            pnl_stmt = select(func.sum(PaperTrade.pnl)).where(PaperTrade.session_id == replay_session_id)
            pnl_result = await db.execute(pnl_stmt)
            pnl = float(pnl_result.scalar() or 0.0)
        except Exception:
            pass
        
        return ReplaySessionDetailResponse(
            replay_session_id=session.replay_session_id,
            strategy_id=session.strategy_id,
            strategy_type=session.strategy_type,
            params=session.params,
            symbol=session.symbol,
            start_time=session.start_time,
            end_time=session.end_time,
            speed=session.speed,
            initial_capital=session.initial_capital,
            status=session.status,
            current_timestamp=session.current_timestamp,
            is_saved=session.is_saved if hasattr(session, 'is_saved') else False,
            created_at=session.created_at,
            pnl=pnl,
            data_source=session.data_source if hasattr(session, 'data_source') else 'REPLAY',
            backtest_id=session.backtest_id if hasattr(session, 'backtest_id') else None,
            params_hash=session.params_hash if hasattr(session, 'params_hash') else None,
            metrics=session.metrics if hasattr(session, 'metrics') else {},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get replay session detail for {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")


@router.delete("/{replay_session_id}", response_model=ReplaySessionResponse)
async def delete_replay_session(
    replay_session_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Delete a replay session and its associated trade data."""
    try:
        # Check if session exists
        stmt = select(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Replay session not found")
        
        # Check if session is currently running (cannot delete active sessions)
        if session.status == "running" and replay_session_id in active_replays:
            raise HTTPException(status_code=400, detail="Cannot delete an actively running replay session. Please pause or wait for it to complete.")
        
        # Delete associated paper trades first (if any)
        try:
            await db.execute(
                delete(PaperTrade).where(PaperTrade.session_id == replay_session_id)
            )
        except Exception as e:
            logger.warning(f"Failed to delete trades for session {replay_session_id}: {e}")
        
        # Delete the session record
        await db.execute(
            delete(ReplaySession).where(ReplaySession.replay_session_id == replay_session_id)
        )
        await db.commit()
        
        logger.info(f"Replay session {replay_session_id} and associated data deleted")
        
        return ReplaySessionResponse(
            replay_session_id=replay_session_id,
            status="deleted",
            message="Replay session deleted successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete replay session {replay_session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Delete operation failed: {str(e)}")
