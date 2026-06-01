"""PRD 10.5 backtest, replay, audit, and comparison overview endpoints."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.services.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


async def _scalar(session, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
    result = await session.execute(text(sql), params or {})
    return int(result.scalar() or 0)


def _support_level(key: str, counts: Dict[str, int]) -> str:
    if key == "point_in_time":
        if counts.get("pit_backtests"):
            return "回测记录已写 PIT 元数据"
        return "已接入上下文" if counts["pit_factor_snapshots"] or counts["pit_signal_events"] else "需要补充 PIT 样例"
    if key == "decision_replay":
        return "已有完整回放" if counts["completed_replays"] else "可创建，待跑完整样例"
    if key == "audit_trail":
        return "已有记录" if counts["audit_logs"] or counts["coordination_history"] else "待产生记录"
    if key == "result_comparison":
        return "已有严格关联样例" if counts["comparison_ready"] else "需要完整回放和严格匹配回测"
    return "未知"


def _match_label(match_type: str) -> str:
    labels = {
        "linked_backtest": "已关联回测",
        "same_params_hash": "参数哈希一致",
        "same_symbol_strategy": "同标的/同策略候选",
        "none": "暂无匹配",
    }
    return labels.get(match_type, match_type or "未知")


@router.get("/overview")
async def get_prd105_audit_overview(
    limit: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    """Return the visible PRD 10.5 state for the frontend.

    The endpoint intentionally reports real persisted data only. It does not
    manufacture demo rows, so the UI can distinguish usable capability from
    capability that still needs a completed replay/backtest sample.
    """
    try:
        async with get_db() as session:
            counts = {
                "backtest_results": await _scalar(session, "SELECT COUNT(*) FROM backtest_results"),
                "replay_sessions": await _scalar(session, "SELECT COUNT(*) FROM replay_sessions"),
                "completed_replays": await _scalar(session, "SELECT COUNT(*) FROM replay_sessions WHERE status = 'completed'"),
                "running_replays": await _scalar(session, "SELECT COUNT(*) FROM replay_sessions WHERE status = 'running'"),
                "pending_replays": await _scalar(session, "SELECT COUNT(*) FROM replay_sessions WHERE status = 'pending'"),
                "failed_replays": await _scalar(session, "SELECT COUNT(*) FROM replay_sessions WHERE status = 'failed'"),
                "audit_logs": await _scalar(session, "SELECT COUNT(*) FROM audit_logs"),
                "coordination_history": await _scalar(session, "SELECT COUNT(*) FROM coordination_history"),
                "paper_trades": await _scalar(session, "SELECT COUNT(*) FROM paper_trades"),
                "equity_snapshots": await _scalar(session, "SELECT COUNT(*) FROM equity_snapshots"),
                "pit_factor_snapshots": await _scalar(
                    session,
                    "SELECT COUNT(*) FROM factor_snapshots WHERE available_time IS NOT NULL",
                ),
                "pit_signal_events": await _scalar(
                    session,
                    "SELECT COUNT(*) FROM signal_events WHERE available_time IS NOT NULL",
                ),
                "pit_backtests": await _scalar(
                    session,
                    "SELECT COUNT(*) FROM backtest_results WHERE metrics ? 'pit'",
                ),
                "pit_repro_backtests": await _scalar(
                    session,
                    "SELECT COUNT(*) FROM backtest_results WHERE metrics->'pit'->>'schema_version' = 'pit-repro-v1'",
                ),
                "linked_replays": await _scalar(
                    session,
                    "SELECT COUNT(*) FROM replay_sessions WHERE backtest_id IS NOT NULL",
                ),
                "comparison_ready": await _scalar(
                    session,
                    """
                    SELECT COUNT(DISTINCT rs.id)
                    FROM replay_sessions rs
                    JOIN backtest_results bt ON bt.id = rs.backtest_id
                    WHERE rs.status = 'completed'
                    """,
                ),
                "candidate_comparisons": await _scalar(
                    session,
                    """
                    SELECT COUNT(DISTINCT rs.id)
                    FROM replay_sessions rs
                    JOIN backtest_results bt
                      ON bt.symbol = rs.symbol
                     AND bt.strategy_type = rs.strategy_type
                    WHERE rs.status = 'completed'
                    """,
                ),
            }
            counts["strict_comparison_ready"] = counts["comparison_ready"]

            status_rows = (
                await session.execute(
                    text("SELECT status, COUNT(*) AS count FROM replay_sessions GROUP BY status ORDER BY status")
                )
            ).mappings().all()
            replay_status_counts = {str(row["status"]): int(row["count"] or 0) for row in status_rows}

            pit_window_row = (
                await session.execute(
                    text(
                        """
                        SELECT
                            MIN(available_time) AS min_available_time,
                            MAX(available_time) AS max_available_time,
                            COUNT(DISTINCT symbol) AS symbol_count
                        FROM factor_snapshots
                        WHERE available_time IS NOT NULL
                        """
                    )
                )
            ).mappings().first()

            backtest_rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, strategy_type, symbol, interval, params, metrics,
                               data_source, params_hash, created_at
                        FROM backtest_results
                        ORDER BY created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings().all()

            replay_rows = (
                await session.execute(
                    text(
                        """
                        SELECT
                            rs.replay_session_id, rs.strategy_id, rs.strategy_type, rs.symbol,
                            rs.start_time, rs.end_time, rs.speed, rs.initial_capital,
                            rs.status, rs.current_timestamp, rs.is_saved, rs.created_at,
                            rs.updated_at, rs.data_source, rs.backtest_id, rs.params_hash,
                            rs.metrics, rs.params,
                            COALESCE(ts.pnl, 0) AS pnl,
                            COALESCE(ts.trade_count, 0) AS trade_count,
                            COALESCE(eq.equity_points, 0) AS equity_points
                        FROM replay_sessions rs
                        LEFT JOIN (
                            SELECT session_id, SUM(pnl) AS pnl, COUNT(*) AS trade_count
                            FROM paper_trades
                            GROUP BY session_id
                        ) ts ON ts.session_id = rs.replay_session_id
                        LEFT JOIN (
                            SELECT session_id, COUNT(*) AS equity_points
                            FROM equity_snapshots
                            GROUP BY session_id
                        ) eq ON eq.session_id = rs.replay_session_id
                        ORDER BY rs.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings().all()

            audit_rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, action, user_id, resource, details, ip_address, created_at
                        FROM audit_logs
                        ORDER BY created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings().all()

            decision_rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, symbol, timestamp, final_signal, confidence, risk_veto,
                               summary, input_snapshot_ids, role_opinions, agent_signals, created_at
                        FROM coordination_history
                        ORDER BY timestamp DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings().all()

            comparison_rows = (
                await session.execute(
                    text(
                        """
                        SELECT
                            rs.replay_session_id, rs.symbol, rs.strategy_type, rs.status,
                            rs.backtest_id, rs.params, rs.params_hash,
                            COALESCE(linked.id, exact_match.id, fuzzy_match.id) AS candidate_backtest_id,
                            COALESCE(linked.interval, exact_match.interval, fuzzy_match.interval) AS candidate_interval,
                            COALESCE(linked.data_source, exact_match.data_source, fuzzy_match.data_source) AS candidate_data_source,
                            COALESCE(linked.metrics, exact_match.metrics, fuzzy_match.metrics) AS candidate_metrics,
                            CASE
                                WHEN linked.id IS NOT NULL THEN 'linked_backtest'
                                WHEN exact_match.id IS NOT NULL THEN 'same_params_hash'
                                WHEN fuzzy_match.id IS NOT NULL THEN 'same_symbol_strategy'
                                ELSE 'none'
                            END AS match_type,
                            rs.created_at
                        FROM replay_sessions rs
                        LEFT JOIN backtest_results linked
                          ON linked.id = rs.backtest_id
                        LEFT JOIN LATERAL (
                            SELECT bt.id, bt.interval, bt.data_source, bt.metrics
                            FROM backtest_results bt
                            WHERE rs.params_hash IS NOT NULL
                              AND bt.params_hash = rs.params_hash
                            ORDER BY bt.created_at DESC
                            LIMIT 1
                        ) exact_match ON linked.id IS NULL
                        LEFT JOIN LATERAL (
                            SELECT bt.id, bt.interval, bt.data_source, bt.metrics
                            FROM backtest_results bt
                            WHERE bt.symbol = rs.symbol
                              AND bt.strategy_type = rs.strategy_type
                            ORDER BY
                                CASE
                                    WHEN bt.interval = COALESCE(rs.params ->> 'interval', '') THEN 0
                                    ELSE 1
                                END,
                                bt.created_at DESC
                            LIMIT 1
                        ) fuzzy_match ON linked.id IS NULL AND exact_match.id IS NULL
                        ORDER BY
                            CASE
                                WHEN rs.status = 'completed' AND linked.id IS NOT NULL THEN 0
                                WHEN rs.status = 'completed' AND exact_match.id IS NOT NULL THEN 1
                                WHEN rs.status = 'completed' AND fuzzy_match.id IS NOT NULL THEN 2
                                ELSE 3
                            END,
                            rs.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings().all()

            latest_backtests = []
            for row in backtest_rows:
                metrics = _safe_dict(row["metrics"])
                latest_backtests.append(
                    {
                        "id": row["id"],
                        "strategy_type": row["strategy_type"],
                        "symbol": row["symbol"],
                        "interval": row["interval"],
                        "params": _safe_dict(row["params"]),
                        "metrics": metrics,
                        "pit": _safe_dict(metrics.get("pit")),
                        "total_return": _safe_float(metrics.get("total_return")),
                        "max_drawdown": _safe_float(metrics.get("max_drawdown")),
                        "sharpe_ratio": _safe_float(metrics.get("sharpe_ratio")),
                        "total_trades": int(metrics.get("total_trades") or 0),
                        "data_source": row["data_source"],
                        "params_hash": row["params_hash"],
                        "created_at": _iso(row["created_at"]),
                    }
                )

            latest_replays = []
            for row in replay_rows:
                initial_capital = _safe_float(row["initial_capital"], 0)
                pnl = _safe_float(row["pnl"], 0)
                latest_replays.append(
                    {
                        "replay_session_id": row["replay_session_id"],
                        "strategy_id": row["strategy_id"],
                        "strategy_type": row["strategy_type"],
                        "symbol": row["symbol"],
                        "start_time": _iso(row["start_time"]),
                        "end_time": _iso(row["end_time"]),
                        "speed": row["speed"],
                        "initial_capital": initial_capital,
                        "status": row["status"],
                        "current_timestamp": _iso(row["current_timestamp"]),
                        "is_saved": row["is_saved"],
                        "created_at": _iso(row["created_at"]),
                        "updated_at": _iso(row["updated_at"]),
                        "data_source": row["data_source"],
                        "backtest_id": row["backtest_id"],
                        "params_hash": row["params_hash"],
                        "params": _safe_dict(row["params"]),
                        "metrics": _safe_dict(row["metrics"]),
                        "pnl": pnl,
                        "total_return": (pnl / initial_capital * 100) if initial_capital > 0 else 0,
                        "trade_count": int(row["trade_count"] or 0),
                        "equity_points": int(row["equity_points"] or 0),
                    }
                )

            latest_audit_logs = [
                {
                    "id": row["id"],
                    "action": row["action"],
                    "user_id": row["user_id"],
                    "resource": row["resource"],
                    "details": _safe_dict(row["details"]),
                    "ip_address": row["ip_address"],
                    "created_at": _iso(row["created_at"]),
                }
                for row in audit_rows
            ]

            latest_decisions = [
                {
                    "id": row["id"],
                    "symbol": row["symbol"],
                    "timestamp": _iso(row["timestamp"]),
                    "final_signal": row["final_signal"],
                    "confidence": _safe_float(row["confidence"]),
                    "risk_veto": bool(row["risk_veto"]),
                    "summary": row["summary"] or "",
                    "input_snapshot_ids": _safe_dict(row["input_snapshot_ids"]),
                    "role_opinions": row["role_opinions"] or [],
                    "agent_signals": row["agent_signals"] or [],
                    "created_at": _iso(row["created_at"]),
                }
                for row in decision_rows
            ]

            comparison_candidates = []
            for row in comparison_rows:
                match_type = row["match_type"] or "none"
                candidate_metrics = _safe_dict(row["candidate_metrics"])
                strict_ready = row["status"] == "completed" and match_type in {
                    "linked_backtest",
                    "same_params_hash",
                }
                comparison_candidates.append(
                    {
                        "replay_session_id": row["replay_session_id"],
                        "symbol": row["symbol"],
                        "strategy_type": row["strategy_type"],
                        "status": row["status"],
                        "backtest_id": row["backtest_id"],
                        "candidate_backtest_id": row["candidate_backtest_id"],
                        "candidate_interval": row["candidate_interval"],
                        "candidate_data_source": row["candidate_data_source"],
                        "candidate_initial_capital": _safe_float(candidate_metrics.get("initial_capital")),
                        "match_type": match_type,
                        "match_label": _match_label(match_type),
                        "ready": strict_ready,
                        "strict": row["status"] == "completed" and match_type == "linked_backtest",
                        "needs_review": bool(row["candidate_backtest_id"]) and not strict_ready,
                        "created_at": _iso(row["created_at"]),
                    }
                )

            ready_candidates = [item for item in comparison_candidates if item["ready"]]

            modules = [
                {
                    "key": "point_in_time",
                    "title": "Point-in-time 回测输入",
                    "support_level": _support_level("point_in_time", counts),
                    "status": "ready" if counts["pit_backtests"] else ("partial" if counts["pit_factor_snapshots"] or counts["pit_signal_events"] else "todo"),
                    "description": (
                        "普通回测已开始保存 as_of_time、数据窗口和行数；AnalysisContext 仍按 available_time <= as_of_time 取数。"
                        if counts["pit_backtests"]
                        else "AnalysisContext 已按 available_time <= as_of_time 取数，适合做决策回放和复现。普通策略回测入口还需要继续把 as_of_time 串到底。"
                    ),
                },
                {
                    "key": "decision_replay",
                    "title": "决策回放",
                    "support_level": _support_level("decision_replay", counts),
                    "status": "ready" if counts["completed_replays"] else "partial",
                    "description": "历史回放会话、状态、交易流水和权益快照已有表结构与接口；当前是否完整可用取决于是否跑完 completed 会话。",
                },
                {
                    "key": "audit_trail",
                    "title": "审计追踪",
                    "support_level": _support_level("audit_trail", counts),
                    "status": "ready" if counts["audit_logs"] or counts["coordination_history"] else "partial",
                    "description": "系统动作进入 audit_logs，TradingAgents/协调决策进入 coordination_history，可追溯输入快照、角色意见和最终建议。",
                },
                {
                    "key": "result_comparison",
                    "title": "结果对比",
                    "support_level": _support_level("result_comparison", counts),
                    "status": "ready" if counts["comparison_ready"] else "partial",
                    "description": (
                        "已有 completed 回放和严格关联回测样例，可进入回放 vs 回测对比。"
                        if counts["comparison_ready"]
                        else "已有回放 vs 回测对比接口；需要 completed 回放，并生成或关联同条件回测后才算严格可比。"
                    ),
                },
            ]

            next_actions = []
            if ready_candidates:
                first_ready = ready_candidates[0]
                href = f"/analytics?replay_session_id={first_ready['replay_session_id']}"
                if first_ready["candidate_backtest_id"]:
                    href += f"&backtest_id={first_ready['candidate_backtest_id']}"
                next_actions.append(
                    {
                        "title": "打开严格对比样例",
                        "href": href,
                        "reason": "已存在 completed 回放和明确关联的回测结果，可以查看收益、回撤、胜率和权益曲线差异。",
                    }
                )
            elif counts["completed_replays"]:
                next_actions.append(
                    {
                        "title": "为已完成回放生成快速回测",
                        "href": "/analytics",
                        "reason": "已有 completed 回放，但还缺严格关联的同条件 backtest_id。",
                    }
                )
            else:
                next_actions.append(
                    {
                        "title": "先跑一个完整历史回放",
                        "href": "/replay",
                        "reason": "只有 completed 回放才适合进入回放 vs 回测对比。",
                    }
                )

            if counts["running_replays"]:
                next_actions.append(
                    {
                        "title": "观察正在运行的回放",
                        "href": "/replay",
                        "reason": "当前仍有 running 会话，跑完后可以继续补更多严格对比样例。",
                    }
                )

            next_actions.append(
                {
                    "title": "查看决策输入快照",
                    "href": "/decisions",
                    "reason": "确认 TradingAgents 使用了哪些因子、信号、新闻和宏观材料。",
                }
            )

            return {
                "generated_at": datetime.utcnow().isoformat(),
                "counts": counts,
                "replay_status_counts": replay_status_counts,
                "point_in_time": {
                    "rule": "available_time <= as_of_time",
                    "factor_snapshot_count": counts["pit_factor_snapshots"],
                    "signal_event_count": counts["pit_signal_events"],
                    "backtest_count": counts["pit_backtests"],
                    "reproducible_backtest_count": counts["pit_repro_backtests"],
                    "symbol_count": int((pit_window_row or {}).get("symbol_count") or 0),
                    "min_available_time": _iso((pit_window_row or {}).get("min_available_time")),
                    "max_available_time": _iso((pit_window_row or {}).get("max_available_time")),
                    "sample_context_url": "/api/v1/signals/context/BTCUSDT?interval=1h&as_of_time=2026-05-28T06:00:00Z",
                },
                "modules": modules,
                "latest_backtests": latest_backtests,
                "latest_replays": latest_replays,
                "latest_audit_logs": latest_audit_logs,
                "latest_decisions": latest_decisions,
                "comparison_candidates": comparison_candidates,
                "next_actions": next_actions,
            }
    except Exception as exc:
        logger.error("Failed to build audit overview: %s", exc, exc_info=True)
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "error": str(exc),
            "counts": {},
            "modules": [],
            "latest_backtests": [],
            "latest_replays": [],
            "latest_audit_logs": [],
            "latest_decisions": [],
            "comparison_candidates": [],
        }
