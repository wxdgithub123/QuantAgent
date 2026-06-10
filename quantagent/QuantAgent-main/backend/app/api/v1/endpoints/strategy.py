"""
Strategy Endpoints
Provides strategy templates, backtest execution, result history,
parameter grid optimization, and multi-symbol batch backtests.
"""

import asyncio
import itertools
import logging
import time
import uuid
from datetime import datetime, date, timezone, timedelta
from typing import List, Optional, Dict, Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.strategy_templates import get_all_templates_meta, build_signal_func, get_template, update_template_default_params, get_template_default_params
from app.services.clickhouse_service import clickhouse_service
from app.services.market_data_gateway import market_data_gateway
from app.services.database import get_db
from app.models.db_models import (
    AuditLog,
    BacktestResult,
    OptimizationResult,
    PaperTrade,
    ReplaySession,
    SignalEventDB,
)
from app.services.backtester import GridOptimizer, OptunaOptimizer
from app.services.backtester.annualization import annualize_return, annualize_sharpe, infer_annualization_factor
from app.services.backtester.signal_resolution import resolve_signal_output
from app.services.reproducibility import enrich_pit_metadata, stable_params_hash
from app.services.risk_manager import risk_manager
from app.services.audit_service import audit_service
from app.services.backtest_duckdb_store import backtest_duckdb_store, build_backtest_archive_record

logger = logging.getLogger(__name__)
router = APIRouter()

BACKTEST_TASKS: Dict[str, Dict[str, Any]] = {}
BACKTEST_TASK_HISTORY_LIMIT = 50
EXECUTION_MODE_RULE_ONLY = "rule_only"
EXECUTION_MODE_AGENT_AUDITED = "agent_audited"
DEFAULT_MAX_AGENT_CALLS = 5
MAX_AGENT_CALLS_HARD_LIMIT = 20


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    strategy_type:   str             # "ma" | "rsi" | "boll"
    symbol:          str = "BTCUSDT"
    interval:        str = "1d"      # "1h" | "4h" | "1d"
    limit:           int = 500       # number of candles to fetch
    initial_capital: float = 10000.0
    params:          Dict[str, Any] = {}
    start_time:      Optional[datetime] = None  # 按时间范围查询（ClickHouse）
    end_time:        Optional[datetime] = None  # 按时间范围查询（ClickHouse）
    as_of_time:      Optional[datetime] = None  # point-in-time 数据截止时间
    end_time:        Optional[datetime] = None
    as_of_time:      Optional[datetime] = None
    executionMode:   str = EXECUTION_MODE_RULE_ONLY
    maxAgentCalls:   int = DEFAULT_MAX_AGENT_CALLS


class TradeRecord(BaseModel):
    tradeId: Optional[str] = None
    trade_id: Optional[str] = None
    backtestId: Optional[int] = None
    symbol: Optional[str] = None
    side: Optional[str] = "LONG"
    entry_time:   str
    exit_time:    str
    entry_price:  float
    exit_price:   float
    quantity:     float
    fee: Optional[float] = 0.0
    slippage: Optional[float] = 0.0
    pnl:          float
    pnl_pct:      float
    realizedPnl: Optional[float] = None
    realizedPnlPct: Optional[float] = None
    source: Optional[str] = "backtest"
    relatedDecisionId: Optional[int] = None
    relatedOrderIntentId: Optional[str] = None
    relatedOrderId: Optional[str] = None
    relatedAuditIds: List[int] = Field(default_factory=list)
    replaySessionId: Optional[str] = None
    signalEventId: Optional[int] = None
    asOfTime: Optional[str] = None
    executionMode: str = EXECUTION_MODE_RULE_ONLY
    riskUnavailable: Optional[bool] = False
    replayUrl: Optional[str] = None
    auditUrl: Optional[str] = None


class BacktestMetrics(BaseModel):
    total_return:    float
    annual_return:   float
    annualized_return: Optional[float] = None
    max_drawdown:    float
    sharpe_ratio:    float
    win_rate:        float
    profit_factor:   float
    total_trades:    int
    total_commission: float
    total_fee: Optional[float] = 0.0
    total_slippage: Optional[float] = 0.0
    initial_capital: float
    final_capital:   float
    executionMode: Optional[str] = None
    execution_mode: Optional[str] = None
    maxAgentCalls: Optional[int] = None
    signalsCount: Optional[int] = None
    agentCallCount: Optional[int] = None
    orderIntentCount: Optional[int] = None
    paperOrderCount: Optional[int] = None
    auditRecordCount: Optional[int] = None
    riskBlockedCount: Optional[int] = None
    riskUnavailableCount: Optional[int] = None
    skippedAgentCalls: Optional[int] = None
    skippedCount: Optional[int] = None
    failedAgentCalls: Optional[int] = None
    failedCount: Optional[int] = None


class TradeMarker(BaseModel):
    time:  str    # ISO timestamp
    price: float
    side:  str    # "BUY" | "SELL"
    pnl:   Optional[float] = None


class BacktestResponse(BaseModel):
    id:            Optional[int]
    strategy_type: str
    symbol:        str
    interval:      str
    params:        Dict[str, Any]
    metrics:       BacktestMetrics
    equity_curve:  List[Dict[str, Any]]  # [{t: ISO-string, v: float}]
    baseline_curve: List[Dict[str, Any]] # [{t: ISO-string, v: float}] buy-and-hold
    benchmark_curve: List[Dict[str, Any]] = []
    drawdown_curve: List[Dict[str, Any]] = []
    markers:       List[TradeMarker]     # buy/sell markers on price chart
    trades:        List[TradeRecord]
    created_at:    str
    pit:           Dict[str, Any] = {}
    pitCheck:      Dict[str, Any] = {}
    dataRange:     Dict[str, Any] = {}
    auditRecordIds: List[int] = []
    executionMode: str = EXECUTION_MODE_RULE_ONLY


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_backtest_pit_metadata(
    *,
    df: pd.DataFrame,
    requested_as_of_time: Optional[datetime],
    requested_start_time: Optional[datetime],
    requested_end_time: Optional[datetime],
    data_source: str,
) -> Dict[str, Any]:
    index_min = df.index.min() if df is not None and len(df) else None
    index_max = df.index.max() if df is not None and len(df) else None
    effective_as_of_time = requested_as_of_time or (
        index_max.to_pydatetime() if isinstance(index_max, pd.Timestamp) else index_max
    )
    return {
        "enabled": True,
        "rule": "bar_time <= as_of_time",
        "scope": "backtest_ohlcv",
        "as_of_time": _iso(effective_as_of_time),
        "requested_as_of_time": _iso(requested_as_of_time),
        "requested_start_time": _iso(requested_start_time),
        "requested_end_time": _iso(requested_end_time),
        "actual_start_time": _iso(index_min),
        "actual_end_time": _iso(index_max),
        "row_count": int(len(df)) if df is not None else 0,
        "data_source": data_source,
        "note": "普通策略回测按 K 线时间裁剪；TradingAgents AnalysisContext 使用 available_time <= as_of_time。",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Templates
# ─────────────────────────────────────────────────────────────────────────────

def _to_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str) and value:
        try:
            return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
    except Exception:
        if value is None:
            return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_execution_mode(value: Optional[str]) -> str:
    mode = (value or EXECUTION_MODE_RULE_ONLY).strip().lower()
    if mode in {"agent", "audited", EXECUTION_MODE_AGENT_AUDITED}:
        return EXECUTION_MODE_AGENT_AUDITED
    return EXECUTION_MODE_RULE_ONLY


def _clamp_max_agent_calls(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_AGENT_CALLS
    return max(0, min(parsed, MAX_AGENT_CALLS_HARD_LIMIT))


def _backtest_trade_time(trade: Dict[str, Any]) -> datetime:
    return (
        _to_datetime(trade.get("entry_time") or trade.get("entryTime"))
        or _to_datetime(trade.get("exit_time") or trade.get("exitTime"))
        or datetime.now(timezone.utc)
    )


def _trade_entry_action(trade: Dict[str, Any]) -> str:
    side = str(trade.get("side") or "LONG").upper()
    return "SELL" if side in {"SHORT", "SELL"} else "BUY"


def _agent_action_to_order_action(value: Any) -> str:
    action = str(getattr(value, "value", value) or "WAIT").upper()
    if action in {"BUY", "LONG", "LONG_REVERSAL"}:
        return "BUY"
    if action in {"SELL", "SHORT", "SHORT_REVERSAL"}:
        return "SELL"
    if action in {"HOLD", "WAIT"}:
        return action
    return "WAIT"


def _build_order_intent_payload(
    *,
    intent_id: str,
    symbol: str,
    action: str,
    quantity: float,
    price: float,
    confidence: float,
    source_decision_id: int,
    as_of_time: datetime,
    initial_capital: float,
) -> Dict[str, Any]:
    order_value = max(quantity * price, 0.0)
    position_ratio = order_value / initial_capital if initial_capital > 0 else 0.0
    return {
        "id": intent_id,
        "intent_id": intent_id,
        "symbol": symbol,
        "action": action,
        "side": "long" if action == "BUY" else "short" if action == "SELL" else "flat",
        "positionRatio": round(min(position_ratio, 1.0), 6),
        "quantity": quantity,
        "confidence": confidence,
        "validUntil": _iso(as_of_time + timedelta(hours=4)),
        "reason": "Agent audited backtest converts a strong strategy signal into a local simulated OrderIntent.",
        "sourceDecisionId": source_decision_id,
        "createdAt": _iso(as_of_time),
        "status": "CREATED",
        "source": "backtest",
        "executionMode": EXECUTION_MODE_AGENT_AUDITED,
    }


def _risk_result_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    checked_rules = rows or []
    passed = all(bool(row.get("passed")) for row in checked_rules) if checked_rules else True
    blocked = next((row for row in checked_rules if not row.get("passed")), None)
    unavailable = any(bool(row.get("unavailable") or row.get("riskUnavailable")) for row in checked_rules)
    return {
        "passed": passed,
        "riskUnavailable": unavailable,
        "blockedReason": (blocked or {}).get("message") if blocked else None,
        "checkedRules": checked_rules,
    }


async def _build_backtest_risk_rows(
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    initial_capital: float,
    portfolio_value: float,
    leverage: int = 1,
) -> List[Dict[str, Any]]:
    """RiskGuard preview isolated to this backtest, avoiding global paper-account peak state."""
    config = await risk_manager.get_config()
    order_value = max(quantity * price, 0.0)
    portfolio = max(portfolio_value, 0.0)
    single_limit_pct = float(config.get("MAX_SINGLE_POSITION_PCT", 0.20))
    total_limit_pct = float(config.get("MAX_TOTAL_EXPOSURE_PCT", 1.0))
    drawdown_limit_pct = float(config.get("MAX_TOTAL_DRAWDOWN_PCT", 0.15))
    daily_loss_limit_pct = float(config.get("MAX_DAILY_LOSS_PCT", 0.05))
    min_order_notional = float(config.get("MIN_ORDER_NOTIONAL", 5.0))
    wait_policy = str(config.get("WAIT_ORDER_INTENT_POLICY", "record_flat")).lower()
    failure_action = str(config.get("RISK_FAILURE_ACTION", "block")).lower()
    forbidden_symbols = {str(item).upper() for item in (config.get("FORBIDDEN_SYMBOLS") or [])}
    max_leverage = risk_manager._calculate_dynamic_leverage(portfolio)  # noqa: SLF001 - shared RiskGuard rule.
    local_drawdown_pct = max(0.0, (initial_capital - portfolio) / initial_capital) if initial_capital > 0 else 0.0

    def row(rule_name: str, current: Any, limit: Any, passed: bool, message: str) -> Dict[str, Any]:
        return {
            "ruleName": rule_name,
            "rule_name": rule_name,
            "currentValue": current,
            "current_value": current,
            "limitValue": limit,
            "limit_value": limit,
            "passed": bool(passed),
            "message": message,
        }

    return [
        row("Trading switch", "enabled", "enabled", True, "Local backtest simulation is enabled."),
        row("Single position limit", round(order_value, 4), round(portfolio * single_limit_pct, 4), order_value <= portfolio * single_limit_pct or portfolio <= 0, "Single simulated order value must stay within the configured cap."),
        row("Total exposure limit", round(order_value, 4), round(portfolio * total_limit_pct, 4), order_value <= portfolio * total_limit_pct or portfolio <= 0, "Backtest exposure is checked in this isolated replay session."),
        row("Daily loss limit", 0.0, round(daily_loss_limit_pct * 100, 4), True, "No live daily loss cache is used in agent_audited backtest."),
        row("Maximum drawdown", round(local_drawdown_pct * 100, 4), round(drawdown_limit_pct * 100, 4), local_drawdown_pct < drawdown_limit_pct, "Drawdown is measured from this backtest initial capital, not global paper state."),
        row("Forbidden symbol", symbol.upper(), "not forbidden", symbol.upper() not in forbidden_symbols, "Configured forbidden symbols cannot be traded."),
        row("Maximum leverage", leverage, max_leverage, int(leverage) <= max_leverage, "Leverage must stay within RiskGuard dynamic cap."),
        row("Minimum order notional", round(order_value, 4), round(min_order_notional, 4), order_value >= min_order_notional, "Backtest orders below the configured minimum notional are blocked."),
        row("WAIT order intent policy", wait_policy, "record_flat|skip", wait_policy in {"record_flat", "skip"}, "WAIT/flat Agent decisions are either recorded as flat intents or explicitly skipped."),
        row("Risk failure action", failure_action, "block|reduce|warn", failure_action in {"block", "reduce", "warn"}, "Backtest audit records the configured failure-action intent; failed RiskGuard checks remain blocked."),
        row("Order notional", round(order_value, 4), round(portfolio * 1.05, 4), order_value <= portfolio * 1.05 or portfolio <= 0, "Prevents confusing USDT notional with coin quantity."),
    ]


def _build_pit_check(
    pit_metadata: Optional[Dict[str, Any]] = None,
    records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return the P3 PIT check shape for bars or generic available_time records."""
    pit = pit_metadata or {}
    violations: List[Dict[str, Any]] = []
    as_of_start = _to_datetime(pit.get("actual_start_time") or pit.get("requested_start_time"))
    as_of_end = _to_datetime(pit.get("actual_end_time") or pit.get("as_of_time"))
    max_available = _to_datetime(pit.get("max_available_time") or pit.get("actual_end_time"))
    cutoff = _to_datetime(pit.get("as_of_time"))

    if cutoff and as_of_end and as_of_end > cutoff:
        violations.append(
            {
                "asOfTime": _iso(cutoff),
                "availableTime": _iso(as_of_end),
                "dataType": "bar",
                "recordId": pit.get("source_snapshot_id") or pit.get("data_snapshot_id"),
                "message": "K线窗口包含 as_of_time 之后的数据，存在未来函数风险。",
            }
        )

    for index, record in enumerate(records or []):
        record_as_of = _to_datetime(record.get("asOfTime") or record.get("as_of_time") or pit.get("as_of_time"))
        available = _to_datetime(record.get("availableTime") or record.get("available_time"))
        if available and (max_available is None or available > max_available):
            max_available = available
        if available and record_as_of and available > record_as_of:
            violations.append(
                {
                    "asOfTime": _iso(record_as_of),
                    "availableTime": _iso(available),
                    "dataType": record.get("dataType") or record.get("data_type") or "unknown",
                    "recordId": record.get("recordId") or record.get("id") or index,
                    "message": record.get("message") or "available_time 晚于 as_of_time，不能作为该时点输入。",
                }
            )

    return {
        "passed": len(violations) == 0,
        "asOfTimeRange": {"start": _iso(as_of_start), "end": _iso(cutoff or as_of_end)},
        "maxAvailableTime": _iso(max_available),
        "violationCount": len(violations),
        "violations": violations[:50],
        "rule": pit.get("rule") or "available_time <= as_of_time",
    }


def _build_drawdown_curve(equity_curve: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    peak = 0.0
    output: List[Dict[str, Any]] = []
    for point in equity_curve or []:
        value = _safe_float(point.get("v", point.get("equity")), 0.0)
        if value > peak:
            peak = value
        drawdown = ((value / peak) - 1.0) * 100.0 if peak > 0 else 0.0
        output.append({"t": point.get("t") or point.get("time"), "v": round(drawdown, 4)})
    return output


def _normalize_backtest_trade(
    trade: Dict[str, Any],
    *,
    index: int,
    backtest_id: Optional[int],
    symbol: str,
    audit_ids: Optional[List[int]] = None,
    linked_replay_id: Optional[str] = None,
) -> Dict[str, Any]:
    entry_time = str(trade.get("entry_time") or trade.get("entryTime") or "")
    exit_time = str(trade.get("exit_time") or trade.get("exitTime") or "")
    pnl = _safe_float(trade.get("pnl", trade.get("realizedPnl")), 0.0)
    pnl_pct = _safe_float(trade.get("pnl_pct", trade.get("realizedPnlPct")), 0.0)
    trade_id = str(trade.get("tradeId") or trade.get("trade_id") or f"BT-{backtest_id or 'unsaved'}-{index + 1}")
    trade_audit_ids = list(trade.get("relatedAuditIds") or [])
    related_audit_ids = trade_audit_ids if trade_audit_ids else list(audit_ids or [])
    replay_session_id = trade.get("replaySessionId") or trade.get("replay_session_id") or linked_replay_id
    as_of_time = trade.get("asOfTime") or trade.get("as_of_time") or entry_time
    replay_url = None
    if replay_session_id and as_of_time:
        replay_url = f"/replay?session_id={replay_session_id}&as_of_time={as_of_time}&event_time={as_of_time}&source=backtest_trade"
    audit_url = f"/audit?backtest_id={backtest_id}" if backtest_id else None
    return {
        **trade,
        "tradeId": trade_id,
        "trade_id": trade_id,
        "backtestId": backtest_id,
        "symbol": trade.get("symbol") or symbol,
        "side": trade.get("side") or "LONG",
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_price": _safe_float(trade.get("entry_price", trade.get("entryPrice")), 0.0),
        "exit_price": _safe_float(trade.get("exit_price", trade.get("exitPrice")), 0.0),
        "quantity": _safe_float(trade.get("quantity"), 0.0),
        "fee": _safe_float(trade.get("fee", trade.get("commission")), 0.0),
        "slippage": _safe_float(trade.get("slippage"), 0.0),
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "realizedPnl": pnl,
        "realizedPnlPct": pnl_pct,
        "source": trade.get("source") or "backtest",
        "relatedDecisionId": trade.get("relatedDecisionId"),
        "relatedOrderIntentId": trade.get("relatedOrderIntentId"),
        "relatedOrderId": trade.get("relatedOrderId"),
        "relatedAuditIds": related_audit_ids,
        "replaySessionId": replay_session_id,
        "signalEventId": trade.get("signalEventId") or trade.get("signal_event_id"),
        "asOfTime": as_of_time,
        "executionMode": trade.get("executionMode") or trade.get("execution_mode") or EXECUTION_MODE_RULE_ONLY,
        "replayUrl": replay_url,
        "auditUrl": audit_url,
    }


def _normalize_metrics(raw_metrics: Dict[str, Any], trades: List[Dict[str, Any]], equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
    metrics = raw_metrics or {}
    initial = _safe_float(metrics.get("initial_capital"), 10000.0)
    final = _safe_float(metrics.get("final_capital"), _safe_float((equity_curve or [{}])[-1].get("v") if equity_curve else None, initial))
    total_fee = _safe_float(metrics.get("total_fee", metrics.get("total_commission")), 0.0)
    total_slippage = _safe_float(metrics.get("total_slippage"), sum(_safe_float(t.get("slippage"), 0.0) for t in trades))
    annual = _safe_float(metrics.get("annualized_return", metrics.get("annual_return")), 0.0)
    return {
        "total_return": _safe_float(metrics.get("total_return"), 0.0),
        "annual_return": annual,
        "annualized_return": annual,
        "max_drawdown": _safe_float(metrics.get("max_drawdown"), 0.0),
        "sharpe_ratio": _safe_float(metrics.get("sharpe_ratio"), 0.0),
        "win_rate": _safe_float(metrics.get("win_rate"), 0.0),
        "profit_factor": _safe_float(metrics.get("profit_factor"), 0.0),
        "total_trades": int(metrics.get("total_trades") or len(trades)),
        "total_commission": total_fee,
        "total_fee": total_fee,
        "total_slippage": total_slippage,
        "initial_capital": initial,
        "final_capital": final,
    }


def _build_backtest_payload(
    row: BacktestResult,
    *,
    audit_ids: Optional[List[int]] = None,
    linked_replay_id: Optional[str] = None,
    include_raw: bool = False,
) -> Dict[str, Any]:
    raw_metrics = row.metrics or {}
    effective_audit_ids = audit_ids or raw_metrics.get("auditRecordIds") or raw_metrics.get("audit_record_ids") or []
    effective_replay_id = linked_replay_id or raw_metrics.get("linkedReplayId") or raw_metrics.get("linked_replay_id")
    execution_mode = _normalize_execution_mode(raw_metrics.get("executionMode") or raw_metrics.get("execution_mode"))
    pit_metadata = raw_metrics.get("pit") if isinstance(raw_metrics.get("pit"), dict) else {}
    if not pit_metadata and row.params_hash:
        pit_metadata = {
            "enabled": False,
            "params_hash": row.params_hash,
            "data_source": row.data_source,
            "note": "历史记录未保存完整 PIT 元数据，只能展示参数哈希与数据源。",
        }

    equity_curve = row.equity_curve or []
    trades = [
        _normalize_backtest_trade(
            trade,
            index=index,
            backtest_id=row.id,
            symbol=row.symbol,
            audit_ids=effective_audit_ids,
            linked_replay_id=effective_replay_id,
        )
        for index, trade in enumerate(row.trades_summary or [])
    ]
    metrics = _normalize_metrics(raw_metrics, trades, equity_curve)
    pit_check = raw_metrics.get("pitCheck") or raw_metrics.get("pit_check") or _build_pit_check(pit_metadata)
    benchmark_curve = raw_metrics.get("benchmark_curve") or raw_metrics.get("baseline_curve")
    if not benchmark_curve and equity_curve:
        initial_value = _safe_float(equity_curve[0].get("v"), metrics["initial_capital"])
        benchmark_curve = [{"t": point.get("t"), "v": initial_value} for point in equity_curve]
    drawdown_curve = raw_metrics.get("drawdown_curve") or _build_drawdown_curve(equity_curve)
    markers: List[Dict[str, Any]] = []
    for trade in trades:
        markers.append({"time": trade["entry_time"], "price": trade["entry_price"], "side": "BUY", "pnl": None})
        markers.append({"time": trade["exit_time"], "price": trade["exit_price"], "side": "SELL", "pnl": trade["pnl"]})
    markers.sort(key=lambda item: item.get("time") or "")

    payload = {
        "id": row.id,
        "backtestId": row.id,
        "strategy_type": row.strategy_type,
        "strategyName": row.strategy_type,
        "symbol": row.symbol,
        "interval": row.interval,
        "timeframe": row.interval,
        "params": row.params or {},
        "strategyParams": row.params or {},
        "metrics": metrics,
        "equity_curve": equity_curve,
        "strategyEquityCurve": equity_curve,
        "baseline_curve": benchmark_curve or [],
        "benchmark_curve": benchmark_curve or [],
        "benchmarkEquityCurve": benchmark_curve or [],
        "drawdown_curve": drawdown_curve,
        "drawdownCurve": drawdown_curve,
        "markers": markers,
        "trades": trades,
        "executionMode": execution_mode,
        "pit": pit_metadata,
        "pitCheck": pit_check,
        "auditRecordIds": effective_audit_ids,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "data_source": row.data_source,
        "params_hash": row.params_hash,
        "dataRange": {
            "startTime": pit_metadata.get("actual_start_time") or pit_metadata.get("requested_start_time"),
            "endTime": pit_metadata.get("actual_end_time") or pit_metadata.get("requested_end_time"),
            "barsCount": pit_metadata.get("row_count") or len(equity_curve),
            "signalsCount": raw_metrics.get("signalsCount", 0),
            "agentCallCount": raw_metrics.get("agentCallCount", 0),
            "orderIntentCount": raw_metrics.get("orderIntentCount", 0),
            "paperOrderCount": raw_metrics.get("paperOrderCount", len(trades)),
            "auditRecordCount": raw_metrics.get("auditRecordCount", len(effective_audit_ids)),
        },
        "config": {
            "backtestId": row.id,
            "strategyName": row.strategy_type,
            "symbol": row.symbol,
            "timeframe": row.interval,
            "startTime": pit_metadata.get("actual_start_time") or pit_metadata.get("requested_start_time"),
            "endTime": pit_metadata.get("actual_end_time") or pit_metadata.get("requested_end_time"),
            "initialCapital": metrics["initial_capital"],
            "feeRate": raw_metrics.get("fee_rate"),
            "slippageRate": raw_metrics.get("slippage_rate"),
            "riskConfig": raw_metrics.get("risk_config") or {},
            "strategyParams": row.params or {},
        },
        "linkedReplay": {
            "replaySessionId": effective_replay_id,
            "status": "completed",
            "startTime": pit_metadata.get("actual_start_time") or pit_metadata.get("requested_start_time"),
            "endTime": pit_metadata.get("actual_end_time") or pit_metadata.get("requested_end_time"),
        } if effective_replay_id else None,
        "links": {
            "audit": f"/audit?backtest_id={row.id}",
            "replay": f"/replay?session_id={effective_replay_id}" if effective_replay_id else None,
        },
    }
    if include_raw:
        payload["raw"] = {
            "metrics": raw_metrics,
            "trades_summary": row.trades_summary or [],
        }
    return payload


@router.get("/templates")
async def get_templates():
    """Return all available strategy templates with parameter definitions.
    Includes custom default params loaded from database."""
    return {"templates": get_all_templates_meta()}


class UpdateTemplateParamsRequest(BaseModel):
    params: Dict[str, Any]  # { "fast_period": 15, "slow_period": 45 }
    updated_by: str = "optimization"  # Who updated: optimization, manual_backtest, manual_replay


@router.put("/templates/{strategy_type}/params")
async def update_template_params(
    strategy_type: str,
    req: UpdateTemplateParamsRequest,
):
    """
    Update the default parameter values for a strategy template.
    This is typically used after running parameter optimization to save
    the best found parameters as the new defaults.
    
    Saves params to database for persistence across restarts.
    
    Returns the updated template definition.
    """
    try:
        updated_template = update_template_default_params(
            strategy_type, 
            req.params,
            updated_by=req.updated_by
        )
        return {
            "success": True,
            "message": f"策略 '{strategy_type}' 的预设参数已更新",
            "template": {
                "id": updated_template["id"],
                "name": updated_template["name"],
                "params": updated_template["params"],
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/templates/{strategy_type}/default-params")
async def get_strategy_default_params(strategy_type: str):
    """
    Get the current default params for a specific strategy.
    Returns merged params from database + hardcoded defaults.
    """
    try:
        params = get_template_default_params(strategy_type)
        return {
            "strategy_type": strategy_type,
            "params": params
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Backtest Execution
# ─────────────────────────────────────────────────────────────────────────────

from app.services.backtester.event_driven import EventDrivenBacktester

# ... (existing imports)


async def _add_backtest_audit_event(
    session,
    *,
    event_type: str,
    symbol: str,
    details: Dict[str, Any],
) -> int:
    payload = {
        "eventType": event_type,
        "symbol": symbol,
        "immutable": True,
        **details,
    }
    audit = await audit_service.add_event(
        session,
        action=event_type,
        user_id="system",
        resource=symbol,
        details=payload,
        flush=True,
    )
    return audit.id


async def _apply_agent_audited_backtest_chain(
    *,
    session,
    bt_row: BacktestResult,
    trades: List[Dict[str, Any]],
    req: BacktestRequest,
    symbol: str,
    interval: str,
    pit_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach an auditable AgentDecision -> OrderIntent -> RiskGuard trace to strong backtest trades."""
    max_agent_calls = _clamp_max_agent_calls(req.maxAgentCalls)
    replay_session_id = f"BTAG-{bt_row.id}-{uuid.uuid4().hex[:8]}"[:50]
    start_dt = _to_datetime(pit_metadata.get("actual_start_time") or pit_metadata.get("requested_start_time"))
    end_dt = _to_datetime(pit_metadata.get("actual_end_time") or pit_metadata.get("requested_end_time"))
    if trades:
        start_dt = start_dt or _backtest_trade_time(trades[0])
        end_dt = end_dt or _to_datetime(trades[-1].get("exit_time") or trades[-1].get("exitTime")) or _backtest_trade_time(trades[-1])
    now = datetime.now(timezone.utc)
    start_dt = start_dt or now
    end_dt = end_dt or start_dt

    replay_row = ReplaySession(
        replay_session_id=replay_session_id,
        strategy_id=0,
        strategy_type=req.strategy_type,
        params={
            **(req.params or {}),
            "interval": interval,
            "executionMode": EXECUTION_MODE_AGENT_AUDITED,
            "maxAgentCalls": max_agent_calls,
        },
        symbol=symbol,
        start_time=start_dt,
        end_time=end_dt,
        speed=1,
        initial_capital=req.initial_capital,
        status="completed",
        current_timestamp=end_dt,
        is_saved=True,
        data_source="BACKTEST",
        backtest_id=bt_row.id,
        params_hash=bt_row.params_hash,
        metrics={
            "executionMode": EXECUTION_MODE_AGENT_AUDITED,
            "backtestId": bt_row.id,
            "note": "Agent audited backtest replay session; local simulation only.",
        },
    )
    session.add(replay_row)
    await session.flush()

    audit_ids: List[int] = []
    pit_records: List[Dict[str, Any]] = []
    agent_calls = 0
    order_intents = 0
    paper_orders = 0
    blocked_count = 0
    risk_unavailable_count = 0
    skipped_count = 0
    failed_count = 0
    updated_trades: List[Dict[str, Any]] = []

    for index, original_trade in enumerate(trades):
        trade = dict(original_trade)
        trade_audit_ids = list(trade.get("relatedAuditIds") or [])
        as_of_time = _backtest_trade_time(trade)
        action = _trade_entry_action(trade)
        quantity = max(_safe_float(trade.get("quantity"), 0.0), 0.0)
        price = max(_safe_float(trade.get("entry_price", trade.get("entryPrice")), 0.0), 0.0)
        risk_sized_quantity = quantity
        if price > 0 and req.initial_capital > 0:
            demo_position_value = req.initial_capital * 0.10
            risk_sized_quantity = min(quantity, demo_position_value / price)
        pnl = _safe_float(trade.get("pnl", trade.get("realizedPnl")), 0.0)
        pnl_pct = _safe_float(trade.get("pnl_pct", trade.get("realizedPnlPct")), 0.0)
        confidence = round(min(0.95, max(0.55, 0.68 + min(abs(pnl_pct) / 100.0, 0.2))), 4)
        snapshot_id = f"BT-{bt_row.id}-SNAP-{index + 1}"

        signal_row = SignalEventDB(
            symbol=symbol,
            timestamp=as_of_time,
            event_time=as_of_time,
            available_time=as_of_time,
            as_of_time=as_of_time,
            signal_type=action,
            signal_value=1.0 if action == "BUY" else -1.0,
            confidence=confidence,
            source_strategy=f"backtest:{req.strategy_type}",
            strategy_id=f"backtest-{bt_row.id}",
            interval=interval,
            provider="QuantAgent",
            data_source="BACKTEST",
            source_version="agent_audited.v1",
            factors={
                "entryPrice": price,
                "exitPrice": _safe_float(trade.get("exit_price", trade.get("exitPrice")), 0.0),
                "pnlPct": pnl_pct,
            },
            extra_data={
                "backtestId": bt_row.id,
                "replaySessionId": replay_session_id,
                "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                "tradeId": trade.get("tradeId") or trade.get("trade_id"),
            },
        )
        session.add(signal_row)
        await session.flush()
        pit_records.append(
            {
                "id": signal_row.id,
                "dataType": "signal",
                "asOfTime": _iso(as_of_time),
                "availableTime": _iso(as_of_time),
            }
        )

        input_summary = {
            "snapshotId": snapshot_id,
            "asOfTime": _iso(as_of_time),
            "availableTime": _iso(as_of_time),
            "dataProvider": "BACKTEST",
            "barsCount": pit_metadata.get("row_count"),
            "newsCount": 0,
            "factorsCount": 3,
            "signalsCount": 1,
            "signalEventId": signal_row.id,
            "pitRule": "available_time <= as_of_time",
            "pitPassed": True,
        }
        signal_audit_id = await _add_backtest_audit_event(
            session,
            event_type="SIGNAL_TRIGGERED",
            symbol=symbol,
            details={
                "asOfTime": _iso(as_of_time),
                "availableTime": _iso(as_of_time),
                "snapshotId": snapshot_id,
                "signalEventId": signal_row.id,
                "backtestId": bt_row.id,
                "replaySessionId": replay_session_id,
                "replayTime": _iso(as_of_time),
                "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                "action": action,
                "source": "backtest",
                "inputSummary": input_summary,
            },
        )
        audit_ids.append(signal_audit_id)
        trade_audit_ids.append(signal_audit_id)
        trade.update(
            {
                "signalEventId": signal_row.id,
                "replaySessionId": replay_session_id,
                "asOfTime": _iso(as_of_time),
                "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                "auditedQuantity": risk_sized_quantity,
                "source": "agent",
            }
        )

        if agent_calls >= max_agent_calls:
            skipped_count += 1
            skip_audit_id = await _add_backtest_audit_event(
                session,
                event_type="SKIPPED_AGENT_CALL",
                symbol=symbol,
                details={
                    "asOfTime": _iso(as_of_time),
                    "availableTime": _iso(as_of_time),
                    "snapshotId": snapshot_id,
                    "signalEventId": signal_row.id,
                    "backtestId": bt_row.id,
                    "replaySessionId": replay_session_id,
                    "replayTime": _iso(as_of_time),
                    "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                    "maxAgentCalls": max_agent_calls,
                    "action": action,
                    "source": "backtest",
                    "inputSummary": input_summary,
                    "message": "Agent call skipped by maxAgentCalls performance guard.",
                },
            )
            audit_ids.append(skip_audit_id)
            trade_audit_ids.append(skip_audit_id)
            trade["relatedAuditIds"] = trade_audit_ids
            updated_trades.append(trade)
            continue

        agent_calls += 1
        try:
            from app.agents.coordinator_agent import CoordinatorAgent

            agent_result = await CoordinatorAgent(fast_mode=True).coordinate_at(
                symbol=symbol,
                interval=interval,
                as_of_time=as_of_time,
                extra_input_snapshot_ids={
                    "snapshotId": snapshot_id,
                    "signalEventId": signal_row.id,
                    "backtestId": bt_row.id,
                    "replaySessionId": replay_session_id,
                    "pit": input_summary,
                    "strategyAction": action,
                },
                audit_metadata={
                    "backtestId": bt_row.id,
                    "replaySessionId": replay_session_id,
                    "signalEventId": signal_row.id,
                    "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                    "source": "backtest",
                    "strategyAction": action,
                },
                draft_order_intent=False,
            )
            if agent_result.data_source == "error" or not agent_result.decision_id:
                raise RuntimeError(agent_result.summary or "TradingAgents returned no decision_id")
        except Exception as exc:
            failed_count += 1
            logger.warning("Agent decision failed in agent_audited backtest: %s", exc)
            failure_audit_id = await _add_backtest_audit_event(
                session,
                event_type="AGENT_DECISION_FAILED",
                symbol=symbol,
                details={
                    "asOfTime": _iso(as_of_time),
                    "availableTime": _iso(as_of_time),
                    "snapshotId": snapshot_id,
                    "signalEventId": signal_row.id,
                    "backtestId": bt_row.id,
                    "replaySessionId": replay_session_id,
                    "replayTime": _iso(as_of_time),
                    "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                    "action": action,
                    "source": "backtest",
                    "inputSummary": input_summary,
                    "error": str(exc),
                    "message": "TradingAgents decision failed; no mock/cached decision was generated.",
                },
            )
            audit_ids.append(failure_audit_id)
            trade_audit_ids.append(failure_audit_id)
            trade["relatedAuditIds"] = trade_audit_ids
            updated_trades.append(trade)
            continue

        decision_id = int(agent_result.decision_id)
        agent_action = _agent_action_to_order_action(agent_result.final_signal)
        agent_outputs = agent_result.role_opinions or agent_result.agent_signals or []
        confidence = round(float(agent_result.confidence or confidence), 4)
        trade["relatedDecisionId"] = decision_id
        trade["agentAction"] = agent_action
        trade["strategyAction"] = action

        decision_audit_id = await _add_backtest_audit_event(
            session,
            event_type="AGENT_DECISION",
            symbol=symbol,
            details={
                "asOfTime": _iso(as_of_time),
                "availableTime": _iso(as_of_time),
                "snapshotId": snapshot_id,
                "decisionId": decision_id,
                "signalEventId": signal_row.id,
                "backtestId": bt_row.id,
                "replaySessionId": replay_session_id,
                "replayTime": _iso(as_of_time),
                "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                "action": agent_action,
                "strategyAction": action,
                "source": "backtest",
                "model": agent_result.data_source,
                "agentGraph": "QuantAgentTradingAgentsGraphAdapter",
                "contextId": agent_result.context_id,
                "contextHash": agent_result.context_hash,
                "inputSummary": input_summary,
                "agentOutputs": agent_outputs,
                "decision": {
                    "id": decision_id,
                    "final_signal": agent_action,
                    "confidence": confidence,
                    "summary": agent_result.summary,
                    "context_id": agent_result.context_id,
                    "context_hash": agent_result.context_hash,
                },
            },
        )
        audit_ids.append(decision_audit_id)
        trade_audit_ids.append(decision_audit_id)

        if agent_action in {"WAIT", "HOLD"}:
            hold_audit_id = await _add_backtest_audit_event(
                session,
                event_type="HOLD_RECORDED",
                symbol=symbol,
                details={
                    "asOfTime": _iso(as_of_time),
                    "availableTime": _iso(as_of_time),
                    "snapshotId": snapshot_id,
                    "decisionId": decision_id,
                    "signalEventId": signal_row.id,
                    "backtestId": bt_row.id,
                    "replaySessionId": replay_session_id,
                    "replayTime": _iso(as_of_time),
                    "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                    "action": agent_action,
                    "strategyAction": action,
                    "source": "backtest",
                    "inputSummary": input_summary,
                    "agentOutputs": agent_outputs,
                    "decision": {
                        "id": decision_id,
                        "final_signal": agent_action,
                        "confidence": confidence,
                        "summary": agent_result.summary,
                    },
                    "message": "Agent final decision was WAIT/HOLD; no historical simulated PaperOrder was generated.",
                },
            )
            audit_ids.append(hold_audit_id)
            trade_audit_ids.append(hold_audit_id)
            trade["relatedAuditIds"] = trade_audit_ids
            trade["source"] = "agent_hold"
            updated_trades.append(trade)
            continue

        action = agent_action

        intent_id = f"OI-BT-{bt_row.id}-{index + 1}-{uuid.uuid4().hex[:6]}"[:50]
        intent = _build_order_intent_payload(
            intent_id=intent_id,
            symbol=symbol,
            action=action,
            quantity=risk_sized_quantity,
            price=price,
            confidence=confidence,
            source_decision_id=decision_id,
            as_of_time=as_of_time,
            initial_capital=req.initial_capital,
        )
        order_intents += 1
        trade["relatedOrderIntentId"] = intent_id
        intent_audit_id = await _add_backtest_audit_event(
            session,
            event_type="ORDER_INTENT_CREATED",
            symbol=symbol,
            details={
                "asOfTime": _iso(as_of_time),
                "availableTime": _iso(as_of_time),
                "snapshotId": snapshot_id,
                "decisionId": decision_id,
                "orderIntentId": intent_id,
                "signalEventId": signal_row.id,
                "backtestId": bt_row.id,
                "replaySessionId": replay_session_id,
                "replayTime": _iso(as_of_time),
                "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                "action": action,
                "strategyAction": trade.get("strategyAction"),
                "source": "backtest",
                "inputSummary": input_summary,
                "agentOutputs": agent_outputs,
                "intent": intent,
            },
        )
        audit_ids.append(intent_audit_id)
        trade_audit_ids.append(intent_audit_id)

        try:
            risk_rows = await _build_backtest_risk_rows(
                symbol=symbol,
                side=action,
                quantity=risk_sized_quantity,
                price=price,
                initial_capital=req.initial_capital,
                portfolio_value=max(req.initial_capital, req.initial_capital + pnl),
                leverage=1,
            )
        except Exception as exc:
            logger.warning("RiskGuard preview failed in agent_audited backtest: %s", exc)
            risk_rows = [
                {
                    "ruleName": "RiskGuard unavailable",
                    "rule_name": "RiskGuard unavailable",
                    "currentValue": "unavailable",
                    "current_value": "unavailable",
                    "limitValue": "required",
                    "limit_value": "required",
                    "passed": False,
                    "unavailable": True,
                    "message": f"RiskGuard preview was unavailable: {exc}",
                }
            ]
        risk_result = _risk_result_from_rows(risk_rows)
        risk_unavailable = bool(risk_result.get("riskUnavailable"))
        risk_event = (
            "RISK_CHECK_PASSED"
            if risk_result["passed"]
            else "RISK_CHECK_UNAVAILABLE" if risk_unavailable
            else "RISK_BLOCKED"
        )
        if risk_unavailable:
            risk_unavailable_count += 1
            trade["riskUnavailable"] = True
        elif not risk_result["passed"]:
            blocked_count += 1
        risk_audit_id = await _add_backtest_audit_event(
            session,
            event_type=risk_event,
            symbol=symbol,
            details={
                "asOfTime": _iso(as_of_time),
                "availableTime": _iso(as_of_time),
                "snapshotId": snapshot_id,
                "decisionId": decision_id,
                "orderIntentId": intent_id,
                "signalEventId": signal_row.id,
                "backtestId": bt_row.id,
                "replaySessionId": replay_session_id,
                "replayTime": _iso(as_of_time),
                "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                "action": action,
                "strategyAction": trade.get("strategyAction"),
                "source": "backtest",
                "inputSummary": input_summary,
                "agentOutputs": agent_outputs,
                "intent": {
                    **intent,
                    "status": "RISK_CHECKED"
                    if risk_result["passed"]
                    else "RISK_UNAVAILABLE" if risk_unavailable else "BLOCKED",
                },
                "riskCheckResult": risk_result,
                "riskUnavailable": risk_unavailable,
            },
        )
        audit_ids.append(risk_audit_id)
        trade_audit_ids.append(risk_audit_id)

        if risk_result["passed"]:
            fee = _safe_float(trade.get("fee"), 0.0)
            paper_trade = PaperTrade(
                strategy_id="agent_backtest",
                client_order_id=intent_id,
                symbol=symbol,
                exchange_id="local",
                side=action,
                order_type="MARKET",
                quantity=risk_sized_quantity,
                price=price,
                leverage=1,
                benchmark_price=_safe_float(trade.get("exit_price", trade.get("exitPrice")), price),
                fee=fee,
                funding_fee=0,
                pnl=pnl,
                status="FILLED",
                mode="backtest",
                session_id=replay_session_id,
                created_at=as_of_time,
                data_source="BACKTEST",
            )
            session.add(paper_trade)
            await session.flush()
            paper_orders += 1
            order_id = f"PT-{paper_trade.id}"
            trade["relatedOrderId"] = order_id
            execution_result = {
                "generatedPaperOrder": True,
                "orderId": order_id,
                "source": "backtest",
                "fillPrice": price,
                "quantity": risk_sized_quantity,
                "strategyQuantity": quantity,
                "filledAt": _iso(as_of_time),
                "fee": fee,
                "slippage": _safe_float(trade.get("slippage"), 0.0),
                "realizedPnl": pnl,
                "status": "FILLED",
                "positionAfterTrade": {
                    "symbol": symbol,
                    "quantity": 0,
                    "note": "Round-trip BacktestTrade is represented as an audited local PaperOrder plus PnL update.",
                },
                "executionMode": EXECUTION_MODE_AGENT_AUDITED,
            }
            for event_type in ("PAPER_ORDER_FILLED", "POSITION_UPDATED", "PNL_UPDATED"):
                event_audit_id = await _add_backtest_audit_event(
                    session,
                    event_type=event_type,
                    symbol=symbol,
                    details={
                        "asOfTime": _iso(as_of_time),
                        "availableTime": _iso(as_of_time),
                        "snapshotId": snapshot_id,
                        "decisionId": decision_id,
                        "orderIntentId": intent_id,
                        "orderId": order_id,
                        "signalEventId": signal_row.id,
                        "backtestId": bt_row.id,
                        "replaySessionId": replay_session_id,
                        "replayTime": _iso(as_of_time),
                        "executionMode": EXECUTION_MODE_AGENT_AUDITED,
                        "action": action,
                        "strategyAction": trade.get("strategyAction"),
                        "source": "backtest",
                        "inputSummary": input_summary,
                        "agentOutputs": agent_outputs,
                        "intent": {**intent, "status": "EXECUTED"},
                        "riskCheckResult": risk_result,
                        "executionResult": execution_result,
                    },
                )
                audit_ids.append(event_audit_id)
                trade_audit_ids.append(event_audit_id)
        elif risk_unavailable:
            trade["source"] = "risk_unavailable"

        trade["relatedAuditIds"] = trade_audit_ids
        updated_trades.append(trade)

    return {
        "trades": updated_trades,
        "auditRecordIds": audit_ids,
        "linkedReplayId": replay_session_id,
        "pitRecords": pit_records,
        "stats": {
            "signalsCount": len(pit_records),
            "agentCallCount": agent_calls,
            "orderIntentCount": order_intents,
            "paperOrderCount": paper_orders,
            "riskBlockedCount": blocked_count,
            "riskUnavailableCount": risk_unavailable_count,
            "skippedAgentCalls": skipped_count,
            "skippedCount": skipped_count,
            "failedAgentCalls": failed_count,
            "failedCount": failed_count,
            "maxAgentCalls": max_agent_calls,
        },
    }

@router.post("/backtest/run", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest):
    """
    Run a strategy backtest using real Binance historical data.
    Results are persisted to PostgreSQL for later retrieval.
    """
    # Validate strategy type
    try:
        signal_func = build_signal_func(req.strategy_type, req.params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    execution_mode = _normalize_execution_mode(req.executionMode)
    max_agent_calls = _clamp_max_agent_calls(req.maxAgentCalls)

    # Risk control: limit candles for high-frequency intervals
    MAX_LIMITS = {"15m": 500, "1h": 1000, "4h": 2000, "1d": 2000, "1w": 2000, "1M": 2000}
    effective_limit = min(req.limit, MAX_LIMITS.get(req.interval, 1000))
    if execution_mode == EXECUTION_MODE_AGENT_AUDITED and req.start_time is None and req.end_time is None:
        effective_limit = min(effective_limit, 720)

    # Normalize symbol to ccxt format
    symbol_ccxt = _normalize_symbol(req.symbol)
    symbol_clean = req.symbol.upper()  # ClickHouse uses "BTCUSDT" format
    pit_cutoff = _as_utc(req.as_of_time) if req.as_of_time else None
    effective_end_time = req.end_time
    if pit_cutoff and (effective_end_time is None or _as_utc(effective_end_time) > pit_cutoff):
        effective_end_time = pit_cutoff

    # Fetch historical OHLCV data
    df = None
    data_source_used = "market_data_gateway"
    use_time_range = req.start_time is not None and effective_end_time is not None

    if use_time_range:
        # 按时间范围查询（优先使用 ClickHouse 历史数据）
        logger.info(f"Backtest with time range: {req.start_time} ~ {effective_end_time}")
        try:
            df = await clickhouse_service.get_klines_dataframe(
                symbol=symbol_clean,
                interval=req.interval,
                start=req.start_time,
                end=effective_end_time,
                limit=10000,  # 时间范围查询允许更多数据
            )
            if df is not None and len(df) >= 50:
                data_source_used = "clickhouse:klines"
                logger.info(f"ClickHouse returned {len(df)} bars for {symbol_clean}/{req.interval}")
            else:
                logger.warning(
                    "ClickHouse data insufficient (%s bars), retrying local gateway without external fallback",
                    len(df) if df is not None else 0,
                )
                df = None
        except Exception as e:
            logger.warning("ClickHouse query failed: %s; retrying local gateway without external fallback", e)
            df = None

        # 如果 ClickHouse 数据不足，仅允许本地网关补读；回测不得隐式调用外部实时/历史源。
        if df is None:
            try:
                df = await market_data_gateway.get_dataframe(
                    symbol_ccxt, 
                    req.interval, 
                    limit=effective_limit,
                    start=req.start_time,
                    end=effective_end_time,
                    allow_external_fallback=False,
                    allow_ccxt_fallback=False,
                    allow_binance_fallback=False,
                )
                if df is not None and len(df) >= 50:
                    data_source_used = "market_data_gateway:local_storage"
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"指定时间范围内本地数据不足：请先回填 {symbol_clean}/{req.interval}，"
                            "回测不会隐式回退到外部数据源"
                        ),
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=503, detail=f"Failed to fetch local market data: {e}")
    else:
        # 使用本地持久化行情；回测必须与研究台共享 PIT/local-only 数据边界。
        try:
            df = await market_data_gateway.get_dataframe(
                symbol_ccxt,
                req.interval,
                limit=effective_limit,
                end=effective_end_time,
                allow_external_fallback=False,
                allow_ccxt_fallback=False,
                allow_binance_fallback=False,
            )
            data_source_used = "market_data_gateway:local_storage"
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to fetch local market data: {e}")

    if df is not None and pit_cutoff is not None and len(df) > 0:
        cutoff = pd.Timestamp(pit_cutoff)
        if df.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        else:
            cutoff = cutoff.tz_convert(df.index.tz)
        df = df[df.index <= cutoff]

    if df is None or len(df) < 300:
        raise HTTPException(status_code=400, detail=f"历史K线数据不足：当前 {len(df) if df is not None else 0} 根，至少需要 300 根才能执行回测")

    params_hash = stable_params_hash(req.params)
    pit_metadata = enrich_pit_metadata(
        _build_backtest_pit_metadata(
            df=df,
            requested_as_of_time=pit_cutoff,
            requested_start_time=req.start_time,
            requested_end_time=req.end_time,
            data_source=data_source_used,
        ),
        symbol=symbol_clean,
        interval=req.interval,
        strategy_type=req.strategy_type,
        params=req.params,
        params_hash=params_hash,
        data_source=data_source_used,
    )

    # Run backtest engine (EventDrivenBacktester with Numba)
    try:
        # Use EventDrivenBacktester for high performance
        backtester = EventDrivenBacktester(
            df=df,
            signal_func=signal_func,
            initial_capital=req.initial_capital,
        )
        result = backtester.run()
        
        # Convert result to API format
        # 1. Equity Curve: Convert list of floats to [{t: time, v: value}]
        equity_values = result["equity_curve"]
        # Downsample for frontend performance if too large
        step = max(1, len(equity_values) // 500)
        equity_curve = [
            {"t": str(df.index[i])[:19], "v": round(equity_values[i], 2)}
            for i in range(0, len(equity_values), step)
        ]
        
        # 2. Trades: Already in list of dicts, ensure keys match TradeRecord
        trades_list = result["trades"]
        
        # 3. Markers: Generate from trades
        markers = []
        for t in trades_list:
            # Buy marker (Entry for Long)
            markers.append({
                "time": t["entry_time"],
                "price": t["entry_price"],
                "side": "BUY",
                "pnl": None
            })
            # Sell marker (Exit for Long)
            markers.append({
                "time": t["exit_time"],
                "price": t["exit_price"],
                "side": "SELL",
                "pnl": t["pnl"]
            })
        # Sort markers by time
        markers.sort(key=lambda x: x["time"])

    except Exception as e:
        logger.error(f"Backtest engine error: {e}", exc_info=True)
        # Fallback to pure python engine if Numba fails
        logger.warning("Falling back to pure Python engine due to error.")
        try:
             result = _run_backtest_engine(
                df=df,
                signal_func=signal_func,
                initial_capital=req.initial_capital,
                symbol=symbol_clean,
                timeframe=req.interval,
            )
             equity_curve = result["equity_curve"]
             trades_list = result["trades"]
             markers = result["markers"]
        except Exception as e2:
             raise HTTPException(status_code=500, detail=f"Backtest engine error: {e2}")

    # Run buy-and-hold baseline for comparison
    try:
        # Baseline can also use EventDriven for consistency, or keep pure python for simplicity
        baseline_result = _run_backtest_engine(
            df=df,
            signal_func=_buy_and_hold_signal,
            initial_capital=req.initial_capital,
            symbol=symbol_clean,
            timeframe=req.interval,
        )
        baseline_curve = baseline_result["equity_curve"]
    except Exception:
        baseline_curve = []

    drawdown_curve = _build_drawdown_curve(equity_curve)
    pit_check = _build_pit_check(pit_metadata)
    normalized_trades = [
        _normalize_backtest_trade(
            t,
            index=index,
            backtest_id=None,
            symbol=symbol_clean,
        )
        for index, t in enumerate(trades_list)
    ]

    # Build response data
    metrics_dict = {
        "total_return":     result["total_return"],
        "annual_return":    result["annual_return"],
        "annualized_return": result["annual_return"],
        "max_drawdown":     result["max_drawdown"],
        "sharpe_ratio":     result["sharpe_ratio"],
        "win_rate":         result["win_rate"],
        "profit_factor":    result["profit_factor"],
        "total_trades":     result["total_trades"],
        "total_commission": result.get("total_commission", 0.0),
        "total_fee":        result.get("total_commission", 0.0),
        "total_slippage":   sum(_safe_float(t.get("slippage"), 0.0) for t in normalized_trades),
        "initial_capital":  req.initial_capital,
        "final_capital":    result["final_capital"],
        "pit":              pit_metadata,
        "pitCheck":         pit_check,
        "pit_check":        pit_check,
        "benchmark_curve":  baseline_curve[:2000],
        "drawdown_curve":   drawdown_curve[:2000],
        "executionMode":    execution_mode,
        "execution_mode":   execution_mode,
        "maxAgentCalls":    max_agent_calls,
    }

    # Persist to PostgreSQL
    db_id = None
    audit_record_ids: List[int] = []
    linked_replay_id: Optional[str] = None
    trace_stats: Dict[str, Any] = {
        "signalsCount": 0,
        "agentCallCount": 0,
        "orderIntentCount": 0,
        "paperOrderCount": len(normalized_trades),
        "auditRecordCount": 0,
        "riskBlockedCount": 0,
        "riskUnavailableCount": 0,
        "skippedAgentCalls": 0,
        "skippedCount": 0,
        "failedAgentCalls": 0,
        "failedCount": 0,
        "maxAgentCalls": max_agent_calls,
    }
    duckdb_archive_status: Dict[str, Any] = {
        "enabled": True,
        "status": "pending",
        "storage": "DuckDB backtest_results",
    }
    try:
        async with get_db() as session:
            bt_row = BacktestResult(
                strategy_type=req.strategy_type,
                symbol=symbol_clean,
                interval=req.interval,
                params=req.params,
                params_hash=params_hash,
                metrics=metrics_dict,
                equity_curve=equity_curve[:2000],   # cap to 2000 points (match max candles)
                trades_summary=normalized_trades[:100],    # store up to 100 trades for mid-freq strategies
                data_source="BACKTEST",
            )
            session.add(bt_row)
            await session.flush()
            db_id = bt_row.id
            normalized_trades = [
                _normalize_backtest_trade(
                    {**t, "executionMode": execution_mode},
                    index=index,
                    backtest_id=db_id,
                    symbol=symbol_clean,
                )
                for index, t in enumerate(normalized_trades)
            ]

            if execution_mode == EXECUTION_MODE_AGENT_AUDITED:
                trace = await _apply_agent_audited_backtest_chain(
                    session=session,
                    bt_row=bt_row,
                    trades=normalized_trades[:100],
                    req=req,
                    symbol=symbol_clean,
                    interval=req.interval,
                    pit_metadata=pit_metadata,
                )
                normalized_trades = trace["trades"]
                linked_replay_id = trace["linkedReplayId"]
                audit_record_ids.extend(trace["auditRecordIds"])
                trace_stats.update(trace["stats"])
                pit_check = _build_pit_check(pit_metadata, trace["pitRecords"])
                metrics_dict["pitCheck"] = pit_check
                metrics_dict["pit_check"] = pit_check
                metrics_dict["linkedReplayId"] = linked_replay_id

            trace_stats["auditRecordCount"] = len(audit_record_ids)
            metrics_dict.update(trace_stats)
            audit_log = await audit_service.add_event(
                session,
                action="BACKTEST_RUN",
                user_id="system",
                resource=symbol_clean,
                details={
                    "eventType": "BACKTEST_RUN",
                    "backtest_id": db_id,
                    "backtestId": db_id,
                    "strategy_type": req.strategy_type,
                    "interval": req.interval,
                    "params": req.params,
                    "executionMode": execution_mode,
                    "maxAgentCalls": max_agent_calls,
                    "replaySessionId": linked_replay_id,
                    "pit": pit_metadata,
                    "pitCheck": pit_check,
                    "metrics": {
                        "total_return": metrics_dict["total_return"],
                        "max_drawdown": metrics_dict["max_drawdown"],
                        "total_trades": metrics_dict["total_trades"],
                    },
                },
                flush=True,
            )
            audit_record_ids.append(audit_log.id)
            metrics_dict["auditRecordIds"] = audit_record_ids
            metrics_dict["auditRecordCount"] = len(audit_record_ids)
            duckdb_archive_status = _archive_backtest_payload(
                backtest_id=db_id,
                task_id=None,
                req=req,
                symbol=symbol_clean,
                params_hash=params_hash,
                metrics=metrics_dict,
                equity_curve=equity_curve[:2000],
                trades=normalized_trades[:100],
                pit_metadata=pit_metadata,
                pit_check=pit_check,
                execution_mode=execution_mode,
            )
            metrics_dict["duckdbArchive"] = duckdb_archive_status
            bt_row.metrics = metrics_dict
            bt_row.trades_summary = normalized_trades[:100]
    except Exception as e:
        logger.warning(f"Failed to persist backtest result: {e}")

    normalized_trades = [
        _normalize_backtest_trade(
            t,
            index=index,
            backtest_id=db_id,
            symbol=symbol_clean,
            audit_ids=audit_record_ids,
            linked_replay_id=linked_replay_id,
        )
        for index, t in enumerate(normalized_trades)
    ]

    return BacktestResponse(
        id=db_id,
        strategy_type=req.strategy_type,
        symbol=symbol_clean,
        interval=req.interval,
        params=req.params,
        metrics=BacktestMetrics(**metrics_dict),
        equity_curve=equity_curve,
        baseline_curve=baseline_curve,
        benchmark_curve=baseline_curve,
        drawdown_curve=drawdown_curve,
        markers=[TradeMarker(**m) for m in markers],
        trades=[TradeRecord(**t) for t in normalized_trades],
        created_at=datetime.utcnow().isoformat(),
        pit=pit_metadata,
        pitCheck=pit_check,
        dataRange={
            "startTime": pit_metadata.get("actual_start_time"),
            "endTime": pit_metadata.get("actual_end_time"),
            "barsCount": pit_metadata.get("row_count"),
            "signalsCount": trace_stats.get("signalsCount", 0),
            "agentCallCount": trace_stats.get("agentCallCount", 0),
            "orderIntentCount": trace_stats.get("orderIntentCount", 0),
            "paperOrderCount": trace_stats.get("paperOrderCount", len(normalized_trades)),
            "auditRecordCount": len(audit_record_ids),
            "riskBlockedCount": trace_stats.get("riskBlockedCount", 0),
            "riskUnavailableCount": trace_stats.get("riskUnavailableCount", 0),
            "skippedAgentCalls": trace_stats.get("skippedAgentCalls", 0),
            "skippedCount": trace_stats.get("skippedCount", trace_stats.get("skippedAgentCalls", 0)),
            "failedAgentCalls": trace_stats.get("failedAgentCalls", 0),
            "failedCount": trace_stats.get("failedCount", trace_stats.get("failedAgentCalls", 0)),
            "maxAgentCalls": max_agent_calls,
            "duckdbArchive": duckdb_archive_status,
            "resultStorage": "PostgreSQL backtest_results + DuckDB backtest_results archive",
        },
        auditRecordIds=audit_record_ids,
        executionMode=execution_mode,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Backtest History
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/backtest/history")
async def get_backtest_history(
    strategy_type: Optional[str] = Query(None),
    symbol:        Optional[str] = Query(None),
    limit:         int = Query(20, ge=1, le=100),
):
    """Return previously saved backtest results (newest first)."""
    from sqlalchemy import select
    async with get_db() as session:
        stmt = (
            select(BacktestResult)
            .order_by(BacktestResult.created_at.desc())
            .limit(limit)
        )
        if strategy_type:
            stmt = stmt.where(BacktestResult.strategy_type == strategy_type)
        if symbol:
            stmt = stmt.where(BacktestResult.symbol == symbol.upper())
        result = await session.execute(stmt)
        rows = result.scalars().all()

    history = [_build_backtest_payload(row) for row in rows]
    return {"history": history, "total": len(history)}


@router.get("/backtest/history/{record_id}")
async def get_backtest_record_detail(record_id: int):
    """Return a full, replay/audit-linked backtest detail payload for P3."""
    from sqlalchemy import select

    async with get_db() as session:
        row = (
            await session.execute(select(BacktestResult).where(BacktestResult.id == record_id))
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="回测记录不存在")

        audit_rows = (
            await session.execute(
                select(AuditLog)
                .order_by(AuditLog.created_at.desc())
                .limit(2000)
            )
        ).scalars().all()
        audit_ids = [
            item.id
            for item in audit_rows
            if str((item.details or {}).get("backtest_id") or (item.details or {}).get("backtestId")) == str(record_id)
        ]

        replay_row = (
            await session.execute(
                select(ReplaySession)
                .where(ReplaySession.backtest_id == record_id)
                .order_by(ReplaySession.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not replay_row and row.params_hash:
            replay_row = (
                await session.execute(
                    select(ReplaySession)
                    .where(ReplaySession.params_hash == row.params_hash)
                    .order_by(ReplaySession.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

    linked_replay_id = replay_row.replay_session_id if replay_row else None
    payload = _build_backtest_payload(
        row,
        audit_ids=audit_ids,
        linked_replay_id=linked_replay_id,
        include_raw=True,
    )
    return {
        "schema_version": "backtest_detail.v1",
        "generated_at": datetime.utcnow().isoformat(),
        "backtestResult": payload,
        "linkedReplay": {
            "replaySessionId": replay_row.replay_session_id,
            "status": replay_row.status,
            "startTime": _iso(replay_row.start_time),
            "endTime": _iso(replay_row.end_time),
        } if replay_row else None,
        "auditRecords": [{"id": audit_id, "url": f"/audit?audit_id={audit_id}"} for audit_id in audit_ids],
    }


@router.delete("/backtest/history/{record_id}")
async def delete_backtest_record(record_id: int):
    """
    Delete a specific backtest record by ID.
    Returns success confirmation.
    """
    from sqlalchemy import delete, select
    async with get_db() as session:
        # Check if record exists
        stmt = select(BacktestResult).where(BacktestResult.id == record_id)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        
        if not record:
            raise HTTPException(status_code=404, detail="回测记录不存在")
        
        # Delete the record
        delete_stmt = delete(BacktestResult).where(BacktestResult.id == record_id)
        await session.execute(delete_stmt)
        await session.commit()
    
    return {"success": True, "message": "回测记录已删除", "id": record_id}


# ─────────────────────────────────────────────────────────────────────────────
# Internal Backtest Engine
# ─────────────────────────────────────────────────────────────────────────────

def _run_backtest_engine(
    df: pd.DataFrame,
    signal_func,
    initial_capital: float,
    symbol: str,
    timeframe: str,
    commission: float = 0.001,
) -> Dict[str, Any]:
    """
    Pure-Python backtest engine (no external dependency).
    Returns dict with metrics, equity_curve, trades.
    """
    import numpy as np

    signals = resolve_signal_output(signal_func(df))
    
    from app.services.paper_trading_service import SLIPPAGE_PCT
    slippage_pct = float(SLIPPAGE_PCT)

    capital = initial_capital
    position = 0.0
    entry_price = 0.0
    entry_time = None
    trades = []
    markers = []   # buy/sell markers
    equity_list = []
    total_commission = 0.0

    prices = df["close"]
    times  = df.index
    execution_signals = signals.shift(1).fillna(0).astype(int)

    for i in range(len(df)):
        price  = float(prices.iloc[i])
        signal = int(execution_signals.iloc[i]) if i < len(execution_signals) else 0
        current_time = times[i]

        # 权益计算使用市场价（不含滑点）
        current_equity = capital + position * price
        equity_list.append(current_equity)

        if signal == 1 and position == 0 and capital > 0:
            effective_buy_price = price * (1 + slippage_pct)  # 买入滑点
            fee = capital * commission
            invest = capital - fee
            position = invest / effective_buy_price
            entry_price = effective_buy_price
            entry_time = current_time
            total_commission += fee
            capital = 0.0
            markers.append({
                "time":  str(current_time)[:19],
                "price": round(price, 6),
                "side":  "BUY",
                "pnl":   None,
            })

        elif signal == -1 and position > 0:
            effective_sell_price = price * (1 - slippage_pct)  # 卖出滑点
            gross = position * effective_sell_price
            fee = gross * commission
            net = gross - fee
            total_commission += fee

            pnl = net - (entry_price * position * (1 + commission))
            pnl_pct = (effective_sell_price / entry_price - 1) * 100 - commission * 200

            trades.append({
                "entry_time":  str(entry_time)[:19],
                "exit_time":   str(current_time)[:19],
                "entry_price": round(entry_price, 6),
                "exit_price":  round(effective_sell_price, 6),
                "quantity":    round(position, 8),
                "pnl":         round(pnl, 4),
                "pnl_pct":     round(pnl_pct, 4),
            })
            markers.append({
                "time":  str(current_time)[:19],
                "price": round(price, 6),
                "side":  "SELL",
                "pnl":   round(pnl, 4),
            })
            capital = net
            position = 0.0
            entry_price = 0.0
            entry_time = None

    # Force-close at last bar
    if position > 0:
        price = float(prices.iloc[-1])
        effective_sell_price = price * (1 - slippage_pct)  # 卖出滑点
        fee = position * effective_sell_price * commission
        net = position * effective_sell_price - fee
        total_commission += fee
        pnl = net - (entry_price * position * (1 + commission))
        pnl_pct = (effective_sell_price / entry_price - 1) * 100 - commission * 200
        trades.append({
            "entry_time":  str(entry_time)[:19],
            "exit_time":   str(times[-1])[:19],
            "entry_price": round(entry_price, 6),
            "exit_price":  round(effective_sell_price, 6),
            "quantity":    round(position, 8),
            "pnl":         round(pnl, 4),
            "pnl_pct":     round(pnl_pct, 4),
        })
        markers.append({
            "time":  str(times[-1])[:19],
            "price": round(price, 6),
            "side":  "SELL",
            "pnl":   round(pnl, 4),
        })
        capital = net
        position = 0.0

    equity_series = pd.Series(equity_list, index=times)
    final_capital = capital

    # Metrics
    total_return = (final_capital / initial_capital - 1) * 100
    annualization_factor = infer_annualization_factor(times)
    daily_ret = equity_series.pct_change().dropna()
    annual_return = annualize_return(total_return / 100, len(daily_ret), annualization_factor)

    rolling_max  = equity_series.cummax()
    drawdown     = (equity_series - rolling_max) / rolling_max
    max_drawdown = abs(float(drawdown.min())) * 100

    sharpe = annualize_sharpe(daily_ret, annualization_factor)

    n_trades = len(trades)
    if n_trades > 0:
        winning = [t for t in trades if t["pnl"] > 0]
        losing  = [t for t in trades if t["pnl"] < 0]
        win_rate = len(winning) / n_trades * 100
        avg_win  = float(np.mean([t["pnl"] for t in winning])) if winning else 0.0
        avg_loss = abs(float(np.mean([t["pnl"] for t in losing]))) if losing else 0.0
        profit_factor = avg_win / avg_loss if avg_loss > 0 else float("inf")
    else:
        win_rate = profit_factor = 0.0

    # Equity curve: sample to max 500 points to keep response small
    step = max(1, len(equity_series) // 500)
    sampled = equity_series.iloc[::step]
    equity_curve = [
        {"t": str(idx)[:19], "v": round(val, 2)}
        for idx, val in sampled.items()
    ]

    return {
        "total_return":    round(total_return, 4),
        "annual_return":   round(annual_return, 4),
        "max_drawdown":    round(max_drawdown, 4),
        "sharpe_ratio":    round(sharpe, 4),
        "win_rate":        round(win_rate, 4),
        "profit_factor":   round(min(profit_factor, 999.0), 4),
        "total_trades":    n_trades,
        "total_commission": round(total_commission, 4),
        "final_capital":   round(final_capital, 4),
        "equity_curve":    equity_curve,
        "markers":         markers,
        "trades":          trades,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Buy-and-Hold baseline signal
# ─────────────────────────────────────────────────────────────────────────────

def _buy_and_hold_signal(df):
    """Buy first candle, sell last candle — market benchmark."""
    import pandas as pd
    signals = pd.Series(0, index=df.index)
    signals.iloc[0]  = 1
    signals.iloc[-1] = -1
    return signals

def _normalize_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if "/" not in symbol:
        for quote in ("USDT", "BTC", "ETH", "BNB", "BUSD"):
            if symbol.endswith(quote):
                base = symbol[: -len(quote)]
                return f"{base}/{quote}"
    return symbol


# ─────────────────────────────────────────────────────────────────────────────
# Parameter Grid Optimization
# ─────────────────────────────────────────────────────────────────────────────

class OptimizeRequest(BaseModel):
    strategy_type:   str
    symbol:          str = "BTCUSDT"
    interval:        str = "1d"
    limit:           int = 500
    initial_capital: float = 10000.0
    commission:      float = 0.001    # maker fee, e.g. 0.001 = 0.1%
    slippage:        float = 0.0005   # price slippage, e.g. 0.0005 = 0.05%
    param_ranges:    Dict[str, List[Any]] = {}
    max_combos:      int = 5000
    algorithm:       str = "grid"     # "grid" | "optuna"
    n_trials:        int = 50         # For Optuna
    target_metric:   str = "sharpe"   # "sharpe" | "return" | "return_per_dd"
    use_numba:       bool = False     # Experimental


class OptimizeResponse(BaseModel):
    strategy_type: str
    symbol:        str
    interval:      str
    best_params:   Dict[str, Any]
    best_sharpe:   float
    best_return:   float
    best_max_drawdown: float
    best_equity_curve: List[Dict[str, Any]]
    best_drawdown_curve: List[Dict[str, Any]]
    best_trades: List[Dict[str, Any]]
    total_combos:  int
    algorithm:     str
    target_metric: str
    results:       List[Dict[str, Any]]
    warnings:      List[Dict[str, Any]] = []
    saved_id:      Optional[int] = None


def _compute_target_score(result: Dict[str, Any], target_metric: str) -> float:
    """Compute a scalar score for ranking optimization results."""
    sharpe = result.get("sharpe", 0.0)
    total_return = result.get("total_return", 0.0)
    max_drawdown = abs(result.get("max_drawdown", 0.001))

    if target_metric == "return":
        return total_return
    elif target_metric == "return_per_dd":
        return total_return / max_drawdown if max_drawdown > 0 else total_return * 999
    else:  # sharpe (default)
        return sharpe


def _run_backtest_for_params(
    df: pd.DataFrame,
    strategy_type: str,
    params: Dict[str, Any],
    initial_capital: float,
    commission: float,
    slippage: float,
) -> Dict[str, Any]:
    """Run a single backtest and return full result with equity curve."""
    import numpy as np

    signal_func = build_signal_func(strategy_type, params)
    signals = resolve_signal_output(signal_func(df))

    capital = initial_capital
    position = 0.0
    entry_price = 0.0
    entry_time = None
    trades = []
    markers = []
    equity_list = []
    total_commission = 0.0

    prices = df["close"]
    times = df.index
    execution_signals = signals.shift(1).fillna(0).astype(int)

    for i in range(len(df)):
        price = float(prices.iloc[i])
        signal = int(execution_signals.iloc[i]) if i < len(execution_signals) else 0
        current_time = times[i]

        current_equity = capital + position * price
        equity_list.append(current_equity)

        if signal == 1 and position == 0 and capital > 0:
            effective_buy_price = price * (1 + slippage)
            fee = capital * commission
            invest = capital - fee
            position = invest / effective_buy_price
            entry_price = effective_buy_price
            entry_time = current_time
            total_commission += fee
            capital = 0.0
            markers.append({
                "time": str(current_time)[:19],
                "price": round(price, 6),
                "side": "BUY",
                "pnl": None,
            })

        elif signal == -1 and position > 0:
            effective_sell_price = price * (1 - slippage)
            gross = position * effective_sell_price
            fee = gross * commission
            net = gross - fee
            total_commission += fee
            pnl = net - (entry_price * position * (1 + commission))
            pnl_pct = (effective_sell_price / entry_price - 1) * 100 - commission * 200
            trades.append({
                "entry_time": str(entry_time)[:19],
                "exit_time": str(current_time)[:19],
                "entry_price": round(entry_price, 6),
                "exit_price": round(effective_sell_price, 6),
                "quantity": round(position, 8),
                "pnl": round(pnl, 4),
                "pnl_pct": round(pnl_pct, 4),
            })
            markers.append({
                "time": str(current_time)[:19],
                "price": round(price, 6),
                "side": "SELL",
                "pnl": round(pnl, 4),
            })
            capital = net
            position = 0.0
            entry_price = 0.0
            entry_time = None

    # Force-close at last bar
    if position > 0:
        price = float(prices.iloc[-1])
        effective_sell_price = price * (1 - slippage)
        fee = position * effective_sell_price * commission
        net = position * effective_sell_price - fee
        total_commission += fee
        pnl = net - (entry_price * position * (1 + commission))
        pnl_pct = (effective_sell_price / entry_price - 1) * 100 - commission * 200
        trades.append({
            "entry_time": str(entry_time)[:19],
            "exit_time": str(times[-1])[:19],
            "entry_price": round(entry_price, 6),
            "exit_price": round(effective_sell_price, 6),
            "quantity": round(position, 8),
            "pnl": round(pnl, 4),
            "pnl_pct": round(pnl_pct, 4),
        })
        markers.append({
            "time": str(times[-1])[:19],
            "price": round(price, 6),
            "side": "SELL",
            "pnl": round(pnl, 4),
        })
        capital = net
        position = 0.0

    equity_series = pd.Series(equity_list, index=times)
    final_capital = capital

    total_return = (final_capital / initial_capital - 1) * 100
    annualization_factor = infer_annualization_factor(times)
    daily_ret = equity_series.pct_change().dropna()
    annual_return = annualize_return(total_return / 100, len(daily_ret), annualization_factor)

    rolling_max = equity_series.cummax()
    drawdown = (equity_series - rolling_max) / rolling_max
    max_drawdown = abs(float(drawdown.min())) * 100

    # Build drawdown curve (downsampled)
    dd_step = max(1, len(drawdown) // 500)
    drawdown_curve = [
        {"t": str(idx)[:19], "v": round(float(v) * 100, 4)}
        for idx, v in drawdown.iloc[::dd_step].items()
    ]

    sharpe = annualize_sharpe(daily_ret, annualization_factor)

    n_trades = len(trades)
    if n_trades > 0:
        winning = [t for t in trades if t["pnl"] > 0]
        losing = [t for t in trades if t["pnl"] < 0]
        win_rate = len(winning) / n_trades * 100
        avg_win = float(np.mean([t["pnl"] for t in winning])) if winning else 0.0
        avg_loss = abs(float(np.mean([t["pnl"] for t in losing]))) if losing else 0.0
        profit_factor = avg_win / avg_loss if avg_loss > 0 else float("inf")
    else:
        win_rate = profit_factor = 0.0

    # Equity curve downsampled
    step = max(1, len(equity_series) // 500)
    equity_curve = [
        {"t": str(idx)[:19], "v": round(float(val), 2)}
        for idx, val in equity_series.iloc[::step].items()
    ]

    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "max_drawdown": round(max_drawdown, 4),
        "sharpe": round(sharpe, 4),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(min(profit_factor, 999.0), 4),
        "total_trades": n_trades,
        "total_commission": round(total_commission, 4),
        "final_capital": round(final_capital, 4),
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "trades": trades,
        "markers": markers,
    }


def _generate_optimization_warnings(
    results: List[Dict[str, Any]],
    best_result: Dict[str, Any],
    n_total: int,
) -> List[Dict[str, Any]]:
    """Generate anti-overfitting warnings for optimization results."""
    warnings = []
    best_sharpe = best_result.get("sharpe", 0.0)
    best_return = best_result.get("total_return", 0.0)
    best_dd = abs(best_result.get("max_drawdown", 0.0))
    best_trades = best_result.get("total_trades", 0)

    # 1. Trade count too low
    if best_trades < 10:
        warnings.append({
            "type": "low_trades",
            "severity": "high",
            "message": f"最优参数交易次数过少（{best_trades} 次），结果统计不具代表性",
            "recommendation": "增加回测数据量或放宽参数范围以产生更多交易",
        })
    elif best_trades < 20:
        warnings.append({
            "type": "low_trades",
            "severity": "medium",
            "message": f"最优参数交易次数偏低（{best_trades} 次），建议谨慎参考",
            "recommendation": "建议增加回测数据量以获得更稳定的统计",
        })

    # 2. Max drawdown too high
    if best_dd > 30:
        warnings.append({
            "type": "high_drawdown",
            "severity": "high",
            "message": f"最大回撤过高（{best_dd:.1f}%），存在较大风险",
            "recommendation": "考虑收紧止损参数或降低仓位以控制回撤",
        })
    elif best_dd > 20:
        warnings.append({
            "type": "high_drawdown",
            "severity": "medium",
            "message": f"最大回撤偏高（{best_dd:.1f}%）",
            "recommendation": "建议关注实盘资金管理，控制单笔仓位",
        })

    # 3. Best params isolated (sharpe much better than second best)
    if len(results) >= 2:
        second_sharpe = results[1].get("sharpe", 0.0)
        sharpe_gap = best_sharpe - second_sharpe
        if best_sharpe > 0 and sharpe_gap / best_sharpe > 0.3:
            warnings.append({
                "type": "isolated_best",
                "severity": "medium",
                "message": f"最优 Sharpe ({best_sharpe:.3f}) 与第二名差距过大（+{sharpe_gap:.3f}），可能存在过拟合",
                "recommendation": "建议选择 Sharpe 排名靠前且稳定的参数组合",
            })

    # 4. Negative Sharpe
    if best_sharpe < 0:
        warnings.append({
            "type": "negative_sharpe",
            "severity": "high",
            "message": f"最优 Sharpe 为负（{best_sharpe:.3f}），策略在该参数下表现不佳",
            "recommendation": "不建议使用当前参数，建议扩大参数搜索范围",
        })

    # 5. WFE-like estimate: best vs median performance
    if len(results) >= 5:
        median_sharpe = sorted([r.get("sharpe", 0.0) for r in results])[len(results) // 2]
        if best_sharpe > 0 and median_sharpe > 0:
            wfe = median_sharpe / best_sharpe if best_sharpe != 0 else 0
            if wfe < 0.3:
                warnings.append({
                    "type": "low_wfe",
                    "severity": "medium",
                    "message": f"Walk-Forward 类似指标偏低（WFE≈{wfe:.2f}），最优参数在样本内表现过于突出",
                    "recommendation": "建议选择中上游参数而非最优参数，或进入 WFA 验证",
                })

    # 6. All returns negative
    all_returns = [r.get("total_return", 0.0) for r in results]
    if all(r < 0 for r in all_returns):
        warnings.append({
            "type": "all_negative",
            "severity": "high",
            "message": "全部参数组合收益率均为负，当前市场环境下策略不适用",
            "recommendation": "建议更换策略或等待市场环境变化",
        })

    return warnings


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_strategy(req: OptimizeRequest):
    """
    Run parameter optimization for a strategy.
    Supports Grid Search (default) and Optuna (Bayesian Optimization).
    Returns full equity/drawdown curves for the best params and anti-overfitting warnings.
    """
    try:
        get_template(req.strategy_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Validate combos for Grid Search
    if req.algorithm == "grid":
        param_names = list(req.param_ranges.keys()) if req.param_ranges else []
        param_values = [req.param_ranges[k] for k in param_names]
        if not param_names:
            total_combos = 1
        else:
            total_combos = 1
            for v in param_values:
                total_combos *= len(v)
        if total_combos > req.max_combos:
            raise HTTPException(
                status_code=400,
                detail=f"参数组合总数 {total_combos} 超过安全上限 {req.max_combos}"
            )
    else:
        total_combos = req.n_trials

    symbol_ccxt = _normalize_symbol(req.symbol)
    symbol_clean = req.symbol.upper()
    MAX_LIMITS = {"15m": 500, "1h": 1000, "4h": 2000, "1d": 2000, "1w": 2000, "1M": 2000}
    effective_limit = min(req.limit, MAX_LIMITS.get(req.interval, 1000))

    try:
        df = await market_data_gateway.get_dataframe(
            symbol_ccxt,
            req.interval,
            limit=effective_limit,
            allow_external_fallback=False,
            allow_ccxt_fallback=False,
            allow_binance_fallback=False,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch local market data: {e}")

    if df is None or len(df) < 300:
        raise HTTPException(status_code=400, detail=f"K线数据不足：当前 {len(df) if df is not None else 0} 根，至少需要 300 根")

    # Run Optimization
    if req.algorithm == "optuna":
        optimizer = OptunaOptimizer(df, req.strategy_type, req.initial_capital)
        result = await asyncio.to_thread(optimizer.optimize, n_trials=req.n_trials, use_numba=req.use_numba)
        valid_results = result["results"]
        best_params = result["best_params"]
    else:
        optimizer = GridOptimizer(df, req.strategy_type, req.initial_capital)
        valid_results = await optimizer.optimize(req.param_ranges, use_numba=req.use_numba)
        best_params = valid_results[0]["params"] if valid_results else {}

    if not valid_results:
        raise HTTPException(status_code=400, detail="所有参数组合均失败，请检查参数范围或策略配置")

    # Re-rank results by target metric
    for r in valid_results:
        r["_target_score"] = _compute_target_score(r, req.target_metric)
    valid_results.sort(key=lambda x: x["_target_score"], reverse=True)

    # Extract best result after re-ranking
    best = valid_results[0]
    best_sharpe = best.get("sharpe", 0.0)
    best_return = best.get("total_return", 0.0)
    best_max_drawdown = best.get("max_drawdown", 0.0)

    # Run full backtest for best params to get equity/drawdown curves
    try:
        full_result = _run_backtest_for_params(
            df=df,
            strategy_type=req.strategy_type,
            params=best_params,
            initial_capital=req.initial_capital,
            commission=req.commission,
            slippage=req.slippage,
        )
        best_equity_curve = full_result.get("equity_curve", [])
        best_drawdown_curve = full_result.get("drawdown_curve", [])
        best_trades = full_result.get("trades", [])[:100]
        # Update best metrics with more accurate values from full backtest
        best_sharpe = full_result.get("sharpe", best_sharpe)
        best_return = full_result.get("total_return", best_return)
        best_max_drawdown = full_result.get("max_drawdown", best_max_drawdown)
        # Update best result entry with full metrics
        best.update({
            "sharpe": best_sharpe,
            "total_return": best_return,
            "max_drawdown": best_max_drawdown,
            "win_rate": full_result.get("win_rate", 0),
            "total_trades": full_result.get("total_trades", 0),
        })
    except Exception as e:
        logger.warning(f"Failed to run full backtest for best params: {e}")
        best_equity_curve = []
        best_drawdown_curve = []
        best_trades = []

    # Generate anti-overfitting warnings
    warnings = _generate_optimization_warnings(valid_results, best, total_combos)

    # Prepare result grid (top 50, stripped of internal fields)
    params_grid = [
        {k: v for k, v in r.items() if k != "_target_score"}
        for r in valid_results[:50]
    ]

    # Persist to DB
    saved_id = None
    try:
        async with get_db() as session:
            row = OptimizationResult(
                strategy_type=req.strategy_type,
                symbol=symbol_clean,
                interval=req.interval,
                params_grid=params_grid,
                best_params=best_params,
                best_sharpe=round(best_sharpe, 4),
                best_return=round(best_return, 4),
                best_max_drawdown=round(best_max_drawdown, 4),
                best_equity_curve=best_equity_curve,
                best_drawdown_curve=best_drawdown_curve,
                best_trades=best_trades,
                target_metric=req.target_metric,
                commission=req.commission,
                slippage=req.slippage,
                param_ranges=req.param_ranges,
                algorithm=req.algorithm,
                total_combos=total_combos,
            )
            session.add(row)
            await session.flush()
            saved_id = row.id
    except Exception as e:
        logger.warning(f"Failed to persist optimization result: {e}")

    return OptimizeResponse(
        strategy_type=req.strategy_type,
        symbol=symbol_clean,
        interval=req.interval,
        best_params=best_params,
        best_sharpe=round(best_sharpe, 4),
        best_return=round(best_return, 4),
        best_max_drawdown=round(best_max_drawdown, 4),
        best_equity_curve=best_equity_curve,
        best_drawdown_curve=best_drawdown_curve,
        best_trades=best_trades,
        total_combos=total_combos,
        algorithm=req.algorithm,
        target_metric=req.target_metric,
        results=params_grid,
        warnings=warnings,
        saved_id=saved_id,
    )


@router.get("/optimize/history")
async def get_optimization_history(
    strategy_type: Optional[str] = Query(None),
    symbol:        Optional[str] = Query(None),
    limit:         int = Query(20, ge=1, le=100),
):
    """Return previously saved optimization results (newest first)."""
    from sqlalchemy import select as sa_select
    async with get_db() as session:
        stmt = (
            sa_select(OptimizationResult)
            .order_by(OptimizationResult.created_at.desc())
            .limit(limit)
        )
        if strategy_type:
            stmt = stmt.where(OptimizationResult.strategy_type == strategy_type)
        if symbol:
            stmt = stmt.where(OptimizationResult.symbol == symbol.upper())
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return {
        "history": [
            {
                "id":             row.id,
                "strategy_type":  row.strategy_type,
                "symbol":         row.symbol,
                "interval":       row.interval,
                "best_params":    row.best_params,
                "best_sharpe":    row.best_sharpe,
                "best_return":    row.best_return,
                "best_max_drawdown": row.best_max_drawdown,
                "algorithm":      row.algorithm,
                "target_metric":  row.target_metric,
                "total_combos":  row.total_combos,
                "created_at":    row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "total": len(rows),
    }


@router.get("/optimize/{record_id}")
async def get_optimization_detail(record_id: int):
    """Return full details of a saved optimization result."""
    from sqlalchemy import select
    async with get_db() as session:
        stmt = select(OptimizationResult).where(OptimizationResult.id == record_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="优化记录不存在")

    return {
        "id": row.id,
        "strategy_type": row.strategy_type,
        "symbol": row.symbol,
        "interval": row.interval,
        "best_params": row.best_params,
        "best_sharpe": row.best_sharpe,
        "best_return": row.best_return,
        "best_max_drawdown": row.best_max_drawdown,
        "best_equity_curve": row.best_equity_curve or [],
        "best_drawdown_curve": row.best_drawdown_curve or [],
        "best_trades": row.best_trades or [],
        "params_grid": row.params_grid or [],
        "param_ranges": row.param_ranges or {},
        "algorithm": row.algorithm,
        "target_metric": row.target_metric,
        "commission": row.commission,
        "slippage": row.slippage,
        "total_combos": row.total_combos,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Create Paper Bot from Optimization Result
# ─────────────────────────────────────────────────────────────────────────────

class OptimizePaperBotRequest(BaseModel):
    strategy_type: str
    symbol: str
    interval: str
    params: Dict[str, Any]
    initial_capital: float = 10000.0
    commission: float = 0.001
    slippage: float = 0.0005


@router.post("/optimize/create-paper-bot")
async def create_paper_bot_from_optimization(req: OptimizePaperBotRequest):
    """
    Create a Paper Bot directly from optimization result parameters.
    No backtest_id needed — takes params from the optimization run.
    """
    from app.schemas.hummingbot_paper_bot import PaperBotPreviewRequest, PaperBotStartResponse, StrategyType, Timeframe
    from app.services.hummingbot_paper_bot_service import start_paper_bot

    # Map strategy_type string to enum
    strategy_map: Dict[str, StrategyType] = {
        "ma": StrategyType.MA,
        "rsi": StrategyType.RSI,
        "boll": StrategyType.BOLL,
        "bollinger": StrategyType.BOLL,
        "macd": StrategyType.MACD,
        "atr": StrategyType.ATR_TREND,
        "atr_trend": StrategyType.ATR_TREND,
    }
    mapped_strategy = strategy_map.get(req.strategy_type.lower(), StrategyType.MA)

    timeframe_map: Dict[str, Timeframe] = {
        "1m": Timeframe.M1,
        "5m": Timeframe.M5,
        "15m": Timeframe.M15,
        "1h": Timeframe.H1,
        "4h": Timeframe.H4,
        "1d": Timeframe.D1,
    }
    mapped_timeframe = timeframe_map.get(req.interval, Timeframe.D1)

    params = req.params

    symbol_parts = req.symbol.replace("USDT", "-USDT") if "-" not in req.symbol else req.symbol
    request = PaperBotPreviewRequest(
        bot_name=f"{req.strategy_type}-{symbol_parts}-{int(time.time())}",
        connector="binance",
        strategy_type=mapped_strategy,
        trading_pair=symbol_parts,
        timeframe=mapped_timeframe,
        paper_initial_balance=req.initial_capital,
        order_amount=100,
        max_runtime_minutes=60 * 24,
        fast_period=params.get("fast_period", 10),
        slow_period=params.get("slow_period", 30),
        rsi_period=params.get("rsi_period", 14),
        rsi_oversold=params.get("rsi_oversold", 30),
        rsi_overbought=params.get("rsi_overbought", 70),
        boll_period=params.get("boll_period", 20),
        boll_std_dev=float(params.get("boll_std_dev", 2.0)),
        macd_fast=params.get("macd_fast", 12),
        macd_slow=params.get("macd_slow", 26),
        macd_signal=params.get("macd_signal", 9),
    )

    try:
        response = await start_paper_bot(
            request=request,
            raw_request_data={"source": "optimization", "params": req.params},
        )
        return {
            "success": True,
            "paper_bot_id": response.data.paper_bot_id if response.data else None,
            "bot_name": response.data.bot_name if response.data else req.strategy_type,
            "remote_started": response.remote_started,
            "remote_confirmed": response.remote_confirmed,
            "error": response.friendly_error or response.error,
        }
    except Exception as e:
        logger.error(f"Paper bot creation from optimization failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Create Testnet Bot from Optimization Result
# ─────────────────────────────────────────────────────────────────────────────

class OptimizeTestnetRequest(BaseModel):
    strategy_type: str
    symbol: str
    interval: str
    params: Dict[str, Any]
    initial_capital: float = 10000.0


@router.post("/optimize/create-testnet-bot")
async def create_testnet_bot_from_optimization(req: OptimizeTestnetRequest):
    """
    Create a Testnet Perpetual Bot directly from optimization result parameters.
    """
    from app.schemas.hummingbot_testnet_bot import TestnetBotStartRequest, TestnetBotMode
    from app.services.hummingbot_testnet_bot_service import start_testnet_bot

    strategy_type_val = req.strategy_type.lower()
    params = req.params

    trading_pair = req.symbol.replace("USDT", "-USDT")
    if "PERP" not in trading_pair and "USDT" in trading_pair:
        trading_pair = trading_pair.replace("-USDT", "-USDT-PERP")

    request = TestnetBotStartRequest(
        bot_name=f"test_{req.strategy_type}_{req.symbol}_{datetime.now().strftime('%Y%m%d%H%M')}",
        trading_pair=trading_pair,
        strategy_type=strategy_type_val,
        timeframe=req.interval,
        initial_capital=req.initial_capital,
        mode=TestnetBotMode.HEDGE,
        fast_period=params.get("fast_period", 10),
        slow_period=params.get("slow_period", 30),
        rsi_period=params.get("rsi_period", 14),
        rsi_oversold=params.get("rsi_oversold", 30),
        rsi_overbought=params.get("rsi_overbought", 70),
        boll_period=params.get("boll_period", 20),
        boll_std_dev=float(params.get("boll_std_dev", 2.0)),
    )

    try:
        response = await start_testnet_bot(request, raw_request_data=req.model_dump())
        return {
            "success": True,
            "bot_id": getattr(response, "bot_id", None),
            "bot_name": getattr(response, "bot_name", request.bot_name),
            "error": getattr(response, "friendly_error", None) or getattr(response, "error", None),
        }
    except Exception as e:
        logger.error(f"Testnet bot creation from optimization failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Symbol Batch Backtest
# ─────────────────────────────────────────────────────────────────────────────

class BatchBacktestRequest(BaseModel):
    strategy_type:   str
    symbols:         List[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    interval:        str = "1d"
    limit:           int = 500
    initial_capital: float = 10000.0
    params:          Dict[str, Any] = {}


class BatchBacktestItem(BaseModel):
    symbol:        str
    total_return:  float
    annual_return: float
    sharpe_ratio:  float
    max_drawdown:  float
    win_rate:      float
    total_trades:  int
    error:         Optional[str] = None


class BatchBacktestResponse(BaseModel):
    strategy_type: str
    interval:      str
    params:        Dict[str, Any]
    results:       List[BatchBacktestItem]
    total_symbols: int
    success_count: int


class ParameterBatchBacktestRequest(BacktestRequest):
    param_grid: Dict[str, List[Any]]
    max_parallel: int = 5


class BacktestTaskSubmitResponse(BaseModel):
    task_id: str
    status: str
    total_runs: int
    max_parallel: int
    note: str


def _trim_backtest_tasks() -> None:
    if len(BACKTEST_TASKS) <= BACKTEST_TASK_HISTORY_LIMIT:
        return
    ordered = sorted(
        BACKTEST_TASKS.items(),
        key=lambda item: item[1].get("created_at") or "",
    )
    for task_id, task in ordered[: max(0, len(BACKTEST_TASKS) - BACKTEST_TASK_HISTORY_LIMIT)]:
        if task.get("status") in {"queued", "running"}:
            continue
        BACKTEST_TASKS.pop(task_id, None)


def _parameter_combinations(param_grid: Dict[str, List[Any]], max_runs: int = 100) -> List[Dict[str, Any]]:
    keys = [key for key, values in param_grid.items() if values]
    if not keys:
        raise HTTPException(status_code=400, detail="请至少配置一个参数组合")
    combos = [
        dict(zip(keys, values))
        for values in itertools.product(*(param_grid[key] for key in keys))
    ]
    if len(combos) > max_runs:
        raise HTTPException(status_code=400, detail=f"参数组合过多：当前 {len(combos)} 个，最多允许 {max_runs} 个")
    return combos


def _task_public_view(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in task.items()
        if key not in {"request", "param_combinations"}
    }


def _task_is_active(task: Dict[str, Any]) -> bool:
    return str(task.get("status") or "").lower() in {"queued", "running", "cancelling"}


def _archive_backtest_payload(
    *,
    backtest_id: Optional[int],
    task_id: Optional[str],
    req: BacktestRequest,
    symbol: str,
    params_hash: Optional[str],
    metrics: Dict[str, Any],
    equity_curve: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    pit_metadata: Dict[str, Any],
    pit_check: Dict[str, Any],
    execution_mode: str,
    status: str = "completed",
) -> Dict[str, Any]:
    record = build_backtest_archive_record(
        backtest_id=backtest_id,
        task_id=task_id,
        strategy_type=req.strategy_type,
        symbol=symbol,
        interval=req.interval,
        params=req.params,
        params_hash=params_hash,
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trades,
        pit=pit_metadata,
        pit_check=pit_check,
        execution_mode=execution_mode,
        status=status,
    )
    return backtest_duckdb_store.archive_result(record)


async def _run_parameter_batch_task(task_id: str, req: ParameterBatchBacktestRequest, combos: List[Dict[str, Any]]) -> None:
    task = BACKTEST_TASKS[task_id]
    if task.get("status") == "cancelled":
        return
    task["status"] = "running"
    task["started_at"] = datetime.utcnow().isoformat()
    backtest_duckdb_store.append_task_event(task_id, "running", "task_started", _task_public_view(task))
    semaphore = asyncio.Semaphore(max(1, min(req.max_parallel, 5)))

    async def run_one(index: int, combo: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            if task.get("cancel_requested"):
                return {
                    "index": index,
                    "status": "cancelled",
                    "params": {**(req.params or {}), **combo},
                    "error": "Task cancellation requested before this run started.",
                }
            run_req = BacktestRequest(
                strategy_type=req.strategy_type,
                symbol=req.symbol,
                interval=req.interval,
                limit=req.limit,
                initial_capital=req.initial_capital,
                params={**(req.params or {}), **combo},
                start_time=req.start_time,
                end_time=req.end_time,
                as_of_time=req.as_of_time,
            )
            try:
                result = await run_backtest(run_req)
                payload = result.model_dump()
                duckdb_archive = payload.get("dataRange", {}).get("duckdbArchive") or payload.get("metrics", {}).get("duckdbArchive")
                return {
                    "index": index,
                    "status": "completed",
                    "params": run_req.params,
                    "backtest_id": payload.get("id"),
                    "metrics": payload.get("metrics", {}),
                    "pit": payload.get("pit", {}),
                    "created_at": payload.get("created_at"),
                    "duckdbArchive": duckdb_archive,
                }
            except Exception as exc:
                detail = getattr(exc, "detail", None)
                return {
                    "index": index,
                    "status": "failed",
                    "params": run_req.params,
                    "error": str(detail or exc)[:500],
                }

    try:
        results = await asyncio.gather(*(run_one(index, combo) for index, combo in enumerate(combos)))
        completed = sum(1 for item in results if item.get("status") == "completed")
        cancelled = sum(1 for item in results if item.get("status") == "cancelled")
        failed = len(results) - completed - cancelled
        final_status = "cancelled" if task.get("cancel_requested") else ("completed" if failed == 0 else "completed_with_errors")
        task.update(
            {
                "status": final_status,
                "completed_at": datetime.utcnow().isoformat(),
                "completed_runs": completed,
                "failed_runs": failed,
                "cancelled_runs": cancelled,
                "results": sorted(results, key=lambda item: item["index"]),
            }
        )
        backtest_duckdb_store.append_task_event(task_id, task["status"], "task_completed", _task_public_view(task))
    except Exception as exc:
        task.update(
            {
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": str(exc)[:500],
            }
        )
        backtest_duckdb_store.append_task_event(task_id, "failed", "task_failed", _task_public_view(task))


@router.post("/backtest/parameter-batch", response_model=BacktestTaskSubmitResponse)
async def submit_parameter_batch_backtest(req: ParameterBatchBacktestRequest):
    """
    Submit a lightweight in-process background backtest task for parameter combinations.
    Each completed run is persisted through the existing BacktestResult path.
    """
    combos = _parameter_combinations(req.param_grid)
    max_parallel = max(1, min(req.max_parallel, 5))
    task_id = f"bt-{uuid.uuid4().hex[:12]}"
    BACKTEST_TASKS[task_id] = {
        "task_id": task_id,
        "status": "queued",
        "kind": "parameter_batch",
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "completed_at": None,
        "symbol": req.symbol.upper(),
        "interval": req.interval,
        "strategy_type": req.strategy_type,
        "total_runs": len(combos),
        "completed_runs": 0,
        "failed_runs": 0,
        "max_parallel": max_parallel,
        "storage": "PostgreSQL backtest_results + DuckDB backtest_results archive",
        "result_storage": {
            "primary": "PostgreSQL backtest_results",
            "archive": "DuckDB data/backtest/backtest_results.duckdb",
            "archive_schema": "backtest_duckdb_archive.v1",
        },
        "queue_scope": "in_process_memory",
        "cancel_supported": True,
        "retry_supported": True,
        "request": req.model_copy(deep=True),
        "param_combinations": combos,
        "pit": {
            "requested_as_of_time": _iso(req.as_of_time),
            "requested_start_time": _iso(req.start_time),
            "requested_end_time": _iso(req.end_time),
            "rule": "bar_time <= as_of_time",
        },
        "results": [],
    }
    _trim_backtest_tasks()
    req.max_parallel = max_parallel
    backtest_duckdb_store.append_task_event(task_id, "queued", "task_submitted", _task_public_view(BACKTEST_TASKS[task_id]))
    asyncio.create_task(_run_parameter_batch_task(task_id, req, combos))
    return BacktestTaskSubmitResponse(
        task_id=task_id,
        status="queued",
        total_runs=len(combos),
        max_parallel=max_parallel,
        note="任务在当前后端进程内异步执行；服务重启会丢失任务状态，但成功的单次回测结果会保存到 PostgreSQL 并归档到 DuckDB。",
    )


@router.get("/backtest/tasks")
async def list_backtest_tasks(limit: int = Query(20, ge=1, le=50)):
    tasks = sorted(
        (_task_public_view(task) for task in BACKTEST_TASKS.values()),
        key=lambda task: task.get("created_at") or "",
        reverse=True,
    )
    return {"tasks": tasks[:limit], "total": len(tasks)}


@router.get("/backtest/tasks/{task_id}")
async def get_backtest_task(task_id: str):
    task = BACKTEST_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="回测任务不存在或后端服务已重启")
    return _task_public_view(task)


@router.get("/backtest/duckdb-archive")
async def get_backtest_duckdb_archive(limit: int = Query(20, ge=1, le=100)):
    rows = backtest_duckdb_store.latest_results(limit=limit)
    return {
        "schema_version": "backtest_duckdb_archive_response.v1",
        "storage": "DuckDB data/backtest/backtest_results.duckdb",
        "available": backtest_duckdb_store.available,
        "count": len(rows),
        "results": rows,
        "pit_rule": "available_time <= as_of_time",
        "supports": ["result_compare", "agent_audited_metrics", "trade_replay_links", "pit_check"],
    }


@router.post("/backtest/tasks/{task_id}/cancel")
async def cancel_backtest_task(task_id: str):
    task = BACKTEST_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="回测任务不存在或后端服务已重启")
    if task.get("status") in {"completed", "completed_with_errors", "failed", "cancelled"}:
        return {**_task_public_view(task), "cancelAccepted": False, "message": "任务已结束，不能取消。"}
    task["cancel_requested"] = True
    task["status"] = "cancelling"
    task["cancel_requested_at"] = datetime.utcnow().isoformat()
    backtest_duckdb_store.append_task_event(task_id, "cancelling", "task_cancel_requested", _task_public_view(task))
    return {**_task_public_view(task), "cancelAccepted": True}


@router.post("/backtest/tasks/{task_id}/retry", response_model=BacktestTaskSubmitResponse)
async def retry_backtest_task(task_id: str):
    task = BACKTEST_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="回测任务不存在或后端服务已重启")
    if _task_is_active(task):
        raise HTTPException(status_code=409, detail="任务仍在运行，不能重试")
    req = task.get("request")
    combos = task.get("param_combinations") or []
    if not isinstance(req, ParameterBatchBacktestRequest) or not combos:
        raise HTTPException(status_code=400, detail="任务缺少可重试的原始配置")
    new_task_id = f"bt-{uuid.uuid4().hex[:12]}"
    cloned_request = req.model_copy(deep=True)
    BACKTEST_TASKS[new_task_id] = {
        **{key: value for key, value in task.items() if key not in {"results", "error", "completed_at", "started_at", "cancel_requested", "cancel_requested_at"}},
        "task_id": new_task_id,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "completed_at": None,
        "completed_runs": 0,
        "failed_runs": 0,
        "cancelled_runs": 0,
        "results": [],
        "request": cloned_request,
        "param_combinations": combos,
        "retry_of": task_id,
    }
    _trim_backtest_tasks()
    backtest_duckdb_store.append_task_event(new_task_id, "queued", "task_retry_submitted", _task_public_view(BACKTEST_TASKS[new_task_id]))
    asyncio.create_task(_run_parameter_batch_task(new_task_id, cloned_request, combos))
    return BacktestTaskSubmitResponse(
        task_id=new_task_id,
        status="queued",
        total_runs=len(combos),
        max_parallel=int(BACKTEST_TASKS[new_task_id].get("max_parallel") or 5),
        note=f"已从 {task_id} 创建重试任务；结果继续归档到 PostgreSQL + DuckDB。",
    )


@router.post("/backtest/batch", response_model=BatchBacktestResponse)
async def batch_backtest(req: BatchBacktestRequest):
    """
    Run the same strategy across multiple symbols concurrently.
    Returns a leaderboard ranked by total return.
    """
    if len(req.symbols) > 20:
        raise HTTPException(status_code=400, detail="最多同时回测 20 个标的")

    try:
        build_signal_func(req.strategy_type, req.params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    MAX_LIMITS = {"15m": 500, "1h": 1000, "4h": 2000, "1d": 2000, "1w": 2000, "1M": 2000}
    effective_limit = min(req.limit, MAX_LIMITS.get(req.interval, 1000))

    async def _run_one(symbol: str) -> BatchBacktestItem:
        try:
            symbol_ccxt  = _normalize_symbol(symbol)
            symbol_clean = symbol.upper()
            df = await market_data_gateway.get_dataframe(
                symbol_ccxt,
                req.interval,
                limit=effective_limit,
                allow_external_fallback=False,
                allow_ccxt_fallback=False,
                allow_binance_fallback=False,
            )
            if df is None or len(df) < 300:
                return BatchBacktestItem(symbol=symbol_clean, total_return=0, annual_return=0,
                                         sharpe_ratio=0, max_drawdown=0, win_rate=0,
                                         total_trades=0, error=f"数据不足（当前 {len(df) if df is not None else 0} 根，需要 300 根）")
            sig_func = build_signal_func(req.strategy_type, req.params)
            result   = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _run_backtest_engine(
                    df=df, signal_func=sig_func, initial_capital=req.initial_capital,
                    symbol=symbol_clean, timeframe=req.interval,
                )
            )
            return BatchBacktestItem(
                symbol=symbol_clean,
                total_return=result["total_return"],
                annual_return=result["annual_return"],
                sharpe_ratio=result["sharpe_ratio"],
                max_drawdown=result["max_drawdown"],
                win_rate=result["win_rate"],
                total_trades=result["total_trades"],
            )
        except Exception as e:
            return BatchBacktestItem(
                symbol=symbol.upper(), total_return=0, annual_return=0,
                sharpe_ratio=0, max_drawdown=0, win_rate=0,
                total_trades=0, error=str(e)[:120],
            )

    items       = await asyncio.gather(*[_run_one(s) for s in req.symbols])
    items_list  = sorted(items, key=lambda x: x.total_return if not x.error else -9999, reverse=True)
    success_cnt = sum(1 for i in items_list if not i.error)

    return BatchBacktestResponse(
        strategy_type=req.strategy_type,
        interval=req.interval,
        params=req.params,
        results=items_list,
        total_symbols=len(req.symbols),
        success_count=success_cnt,
    )
