"""PRD 10.5 backtest, replay, audit, and comparison overview endpoints."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
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


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalized_snapshot_from_details(details: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(details.get("normalizedSnapshot"))
    if snapshot:
        return snapshot
    input_summary = _safe_dict(details.get("inputSummary"))
    return _safe_dict(input_summary.get("normalizedSnapshot") or input_summary.get("normalized_snapshot"))


def _analysis_context_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Return the Agent-visible AnalysisContext stored in an audit snapshot."""
    if not snapshot:
        return {}
    return {
        "symbol": snapshot.get("symbol"),
        "timeframe": snapshot.get("timeframe"),
        "as_of_time": snapshot.get("as_of_time"),
        "schema_version": snapshot.get("schema_version") or "audit_analysis_context_snapshot.v1",
        "bars": _safe_list(snapshot.get("bars")),
        "latest_factors": _safe_dict(snapshot.get("latest_factors")),
        "recent_signals": _safe_list(snapshot.get("recent_signals")),
        "news_events": _safe_list(snapshot.get("news_events")),
        "macro_events": _safe_list(snapshot.get("macro_events")),
        "input_snapshot_ids": _safe_dict(snapshot.get("input_snapshot_ids")),
        "data_versions": _safe_dict(snapshot.get("data_versions")),
        "context_hash": snapshot.get("context_hash"),
        "metadata": {
            **_safe_dict(snapshot.get("metadata")),
            "strict_snapshot_replay": True,
            "snapshot_schema_version": snapshot.get("schema_version"),
        },
    }


def _cp1252_reverse_map() -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    for byte in range(0x80, 0xA0):
        try:
            char = bytes([byte]).decode("cp1252")
        except UnicodeDecodeError:
            continue
        mapping[ord(char)] = byte
    return mapping


_CP1252_REVERSE = _cp1252_reverse_map()
_MOJIBAKE_MARKERS = ("Ã", "Â", "â", "å", "æ", "ç", "ä", "ï¼", "\ufffd")


def _looks_like_mojibake(value: str) -> bool:
    return any(marker in value for marker in _MOJIBAKE_MARKERS) or any(
        0x80 <= ord(char) <= 0x9F for char in value
    )


def _repair_text(value: str) -> str:
    """Repair common UTF-8 text accidentally decoded as Latin-1/Windows-1252.

    The database remains immutable; this only improves human-facing API output.
    """
    if not value or not _looks_like_mojibake(value):
        return value

    raw = bytearray()
    for char in value:
        codepoint = ord(char)
        if codepoint <= 0xFF:
            raw.append(codepoint)
        elif codepoint in _CP1252_REVERSE:
            raw.append(_CP1252_REVERSE[codepoint])
        else:
            return value

    try:
        repaired = raw.decode("utf-8")
    except UnicodeDecodeError:
        return value

    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in repaired)
    if has_cjk and not _looks_like_mojibake(repaired):
        return repaired
    return value


def _repair_json(value: Any) -> Any:
    if isinstance(value, str):
        return _repair_text(value)
    if isinstance(value, list):
        return [_repair_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _repair_json(item) for key, item in value.items()}
    return value


async def _scalar(session, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
    result = await session.execute(text(sql), params or {})
    return int(result.scalar() or 0)


def _snapshot_count(snapshot: Dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = snapshot.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _int_ids(value: Any, limit: int = 50) -> List[int]:
    if not isinstance(value, list):
        return []
    out: List[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
        if len(out) >= limit:
            break
    return out


def _in_clause(prefix: str, values: List[int]) -> tuple[str, Dict[str, int]]:
    params = {f"{prefix}{index}": value for index, value in enumerate(values)}
    placeholders = ", ".join(f":{key}" for key in params)
    return placeholders or "NULL", params


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    getter = getattr(row, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except Exception:
            pass
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return default
    except Exception as exc:
        if "Could not locate column" in str(exc):
            return default
        raise


def _decision_payload(row: Any) -> Dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "symbol": _row_get(row, "symbol"),
        "timestamp": _iso(_row_get(row, "timestamp")),
        "final_signal": _row_get(row, "final_signal"),
        "confidence": _safe_float(_row_get(row, "confidence")),
        "vote_breakdown": _safe_dict(_row_get(row, "vote_breakdown")),
        "risk_veto": bool(_row_get(row, "risk_veto")),
        "summary": _repair_text(_row_get(row, "summary", "") or ""),
        "agent_signals": _repair_json(_safe_list(_row_get(row, "agent_signals"))),
        "bull_view": _repair_text(_row_get(row, "bull_view", "") or ""),
        "bear_view": _repair_text(_row_get(row, "bear_view", "") or ""),
        "input_snapshot_ids": _safe_dict(_row_get(row, "input_snapshot_ids")),
        "role_opinions": _repair_json(_safe_list(_row_get(row, "role_opinions"))),
        "position_advice": _repair_json(_safe_dict(_row_get(row, "position_advice"))),
        "risk_notes": _repair_text(_row_get(row, "risk_notes", "") or ""),
        "created_at": _iso(_row_get(row, "created_at")),
        "context_id": _row_get(row, "context_id"),
        "context_hash": _row_get(row, "context_hash"),
        "available_time": _iso(_row_get(row, "available_time")),
        "model_version": _row_get(row, "model_version"),
        "prompt_version": _row_get(row, "prompt_version"),
    }


def _signal_name(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value).upper()
    return str(value or "").upper()


def _replay_value(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _extract_interval_from_snapshot(snapshot: Dict[str, Any], fallback: str = "1h") -> str:
    bar_meta = snapshot.get("bar_meta") if isinstance(snapshot, dict) else None
    if isinstance(bar_meta, list) and bar_meta:
        bar_meta = bar_meta[0]
    if isinstance(bar_meta, dict):
        interval = bar_meta.get("interval") or bar_meta.get("timeframe")
        if interval:
            return str(interval)
    interval = snapshot.get("interval") or snapshot.get("timeframe") if isinstance(snapshot, dict) else None
    return str(interval or fallback)


def _decision_diff_summary(source_decision: Dict[str, Any], replay_result: Any) -> Dict[str, Any]:
    original_action = _signal_name(source_decision.get("final_signal") or source_decision.get("action"))
    replay_signal = _replay_value(replay_result, "final_signal")
    replay_action = _signal_name(replay_signal or _replay_value(replay_result, "action"))
    original_confidence = _safe_float(source_decision.get("confidence"))
    replay_confidence = _safe_float(_replay_value(replay_result, "confidence"))
    original_hash = source_decision.get("context_hash") or source_decision.get("contextHash")
    replay_hash = _replay_value(replay_result, "context_hash") or _replay_value(replay_result, "contextHash")
    original_summary = str(source_decision.get("summary") or "")
    replay_summary = str(_replay_value(replay_result, "summary", "") or "")
    original_risk = bool(source_decision.get("risk_veto"))
    replay_risk = bool(_replay_value(replay_result, "risk_veto", False))

    return {
        "originalAction": original_action,
        "replayAction": replay_action,
        "actionChanged": bool(original_action and replay_action and original_action != replay_action),
        "originalConfidence": round(original_confidence, 4),
        "replayConfidence": round(replay_confidence, 4),
        "confidenceDelta": round(replay_confidence - original_confidence, 4),
        "originalRiskVeto": original_risk,
        "replayRiskVeto": replay_risk,
        "riskVetoChanged": original_risk != replay_risk,
        "originalContextHash": original_hash,
        "replayContextHash": replay_hash,
        "contextHashChanged": bool(original_hash and replay_hash and original_hash != replay_hash),
        "summaryChanged": bool(original_summary and replay_summary and original_summary != replay_summary),
    }


AUDIT_EVENT_TYPES = {
    "AGENT_DECISION",
    "DECISION_REPLAY_REQUESTED",
    "DECISION_REPLAY_COMPLETED",
    "DECISION_REPLAY_FAILED",
    "ORDER_INTENT_CREATED",
    "RISK_CHECK_PASSED",
    "RISK_BLOCKED",
    "RISK_CHECK_UNAVAILABLE",
    "PAPER_ORDER_FILLED",
    "PAPER_ORDER_REJECTED",
    "POSITION_UPDATED",
    "PNL_UPDATED",
    "HOLD_RECORDED",
}

AUDIT_RECORD_SELECT_COLUMNS = """
id, action, user_id, resource, details, ip_address, created_at,
event_type, symbol, decision_id, source_decision_id, replay_decision_id,
order_intent_id, order_id, context_id, context_hash, risk_status,
execution_status, backtest_id, replay_session_id, execution_mode,
payload_hash, prev_hash, immutable
"""


def _nested_dict(source: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    current: Any = source
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


FULL_GRAPH_MODES = {
    "full_graph",
    "quantagent_patched_graph",
    "quantagent_graph",
    "patched_graph",
    "native_graph",
}
QUICK_GRAPH_MODES = {
    "context_adapter",
    "analysis_context",
    "fast",
    "quick",
    "quick_research",
}


def _first_bool_present(*values: Any) -> Optional[bool]:
    for value in values:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y"}:
                return True
            if normalized in {"false", "0", "no", "n"}:
                return False
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
    return None


def _graph_execution_meta(*sources: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        candidates.append(source)
        for key in ("_graph_meta", "graph_meta", "graphMeta", "decision"):
            nested = _safe_dict(source.get(key))
            if nested:
                candidates.append(nested)

    graph_mode = _first_present(
        *[
            _first_present(
                item.get("graphMode"),
                item.get("graph_mode"),
                item.get("executionMode"),
                item.get("execution_mode"),
                item.get("mode"),
            )
            for item in candidates
        ]
    )
    normalized_mode = str(graph_mode).strip().lower() if graph_mode else None
    is_full_graph = _first_bool_present(
        *[
            _first_present(
                item.get("isFullGraph"),
                item.get("is_full_graph"),
            )
            for item in candidates
        ]
    )
    if is_full_graph is None and normalized_mode:
        if normalized_mode in FULL_GRAPH_MODES:
            is_full_graph = True
        elif normalized_mode in QUICK_GRAPH_MODES:
            is_full_graph = False

    strong_acceptance_eligible = _first_bool_present(
        *[
            _first_present(
                item.get("strongAcceptanceEligible"),
                item.get("strong_acceptance_eligible"),
            )
            for item in candidates
        ]
    )
    if strong_acceptance_eligible is None and is_full_graph is not None:
        strong_acceptance_eligible = bool(is_full_graph)

    return {
        "graphMode": str(graph_mode) if graph_mode else None,
        "configuredMode": _first_present(
            *[
                _first_present(item.get("configuredMode"), item.get("configured_mode"))
                for item in candidates
            ]
        ),
        "isFullGraph": is_full_graph,
        "strongAcceptanceEligible": strong_acceptance_eligible,
        "modeNote": _first_present(
            *[
                _first_present(item.get("modeNote"), item.get("mode_note"))
                for item in candidates
            ]
        ),
    }


def _audit_record_payload(row: Any) -> Dict[str, Any]:
    details = _repair_json(_safe_dict(_row_get(row, "details")))
    intent = _safe_dict(details.get("intent"))
    decision = _safe_dict(details.get("decision"))
    risk = _safe_dict(details.get("riskCheckResult") or details.get("risk_preview"))
    execution = _safe_dict(details.get("executionResult") or details.get("execution"))
    graph_meta = _graph_execution_meta(details, decision, intent, execution)

    legacy_event_map = {
        "ORDER_INTENT_NOOP": "HOLD_RECORDED",
        "ORDER_INTENT_PREVIEW": "ORDER_INTENT_CREATED",
        "ORDER_INTENT_RISK_CHECKED": "RISK_CHECK_PASSED",
        "ORDER_INTENT_BLOCKED": "RISK_BLOCKED",
        "ORDER_INTENT_EXECUTED": "PAPER_ORDER_FILLED",
        "ORDER_CREATE": "PAPER_ORDER_FILLED",
        "ORDER_FILL": "PAPER_ORDER_FILLED",
        "ORDER_CANCEL": "PAPER_ORDER_REJECTED",
    }
    raw_event_type = str(
        _first_present(
            _row_get(row, "event_type"),
            details.get("eventType"),
            details.get("event_type"),
            _row_get(row, "action"),
        )
    )
    event_type = legacy_event_map.get(raw_event_type, raw_event_type)
    source_decision_id = _first_present(
        _row_get(row, "source_decision_id"),
        details.get("sourceDecisionId"),
        details.get("source_decision_id"),
        intent.get("sourceDecisionId"),
        intent.get("source_decision_id"),
    )
    replay_decision_id = _first_present(
        _row_get(row, "replay_decision_id"),
        details.get("replayDecisionId"),
        details.get("replay_decision_id"),
        intent.get("replayDecisionId"),
        intent.get("replay_decision_id"),
    )
    decision_id = _first_present(
        _row_get(row, "decision_id"),
        details.get("decisionId"),
        details.get("decision_id"),
        replay_decision_id,
        source_decision_id,
        intent.get("sourceDecisionId"),
        intent.get("decision_id"),
        decision.get("id"),
    )
    order_intent_id = _first_present(
        _row_get(row, "order_intent_id"),
        details.get("orderIntentId"),
        intent.get("id"),
        intent.get("intent_id"),
    )
    order_id = _first_present(
        _row_get(row, "order_id"),
        details.get("orderId"),
        details.get("order_id"),
        execution.get("orderId"),
        execution.get("order_id"),
    )
    backtest_id = _first_present(_row_get(row, "backtest_id"), details.get("backtestId"), details.get("backtest_id"))
    replay_session_id = _first_present(
        _row_get(row, "replay_session_id"),
        details.get("replaySessionId"),
        details.get("replay_session_id"),
    )
    replay_time = _first_present(details.get("replayTime"), details.get("replay_time"), details.get("asOfTime"))
    execution_mode = _first_present(
        _row_get(row, "execution_mode"),
        details.get("executionMode"),
        details.get("execution_mode"),
        intent.get("executionMode"),
        execution.get("executionMode"),
    )
    risk_passed = risk.get("passed")
    if risk_passed is None:
        risk_passed = risk.get("allowed")
    risk_status = (
        "unavailable" if event_type == "RISK_CHECK_UNAVAILABLE" or risk.get("riskUnavailable") is True else
        "passed" if risk_passed is True else
        "blocked" if risk_passed is False or event_type == "RISK_BLOCKED" else
        "not_checked"
    )
    execution_status = _first_present(
        _row_get(row, "execution_status"),
        execution.get("status"),
        details.get("status") if event_type.startswith("PAPER_ORDER") else None,
        "FILLED" if event_type == "PAPER_ORDER_FILLED" else None,
        "REJECTED" if event_type == "PAPER_ORDER_REJECTED" else None,
    )
    risk_status = _first_present(_row_get(row, "risk_status"), risk_status)
    source = _first_present(
        details.get("source"),
        intent.get("source"),
        execution.get("source"),
        _nested_dict(details, "execution", "source").get("source"),
    )

    return {
        "id": _row_get(row, "id"),
        "eventType": event_type,
        "action": _first_present(intent.get("action"), decision.get("final_signal"), details.get("action")),
        "symbol": _first_present(
            _row_get(row, "symbol"),
            details.get("symbol"),
            intent.get("symbol"),
            _row_get(row, "resource"),
        ),
        "asOfTime": details.get("asOfTime"),
        "snapshotId": details.get("snapshotId"),
        "decisionId": decision_id,
        "sourceDecisionId": source_decision_id,
        "replayDecisionId": replay_decision_id,
        "contextId": _first_present(_row_get(row, "context_id"), details.get("contextId"), decision.get("context_id")),
        "contextHash": _first_present(_row_get(row, "context_hash"), details.get("contextHash"), decision.get("context_hash")),
        "modelVersion": _first_present(details.get("modelVersion"), decision.get("model_version")),
        "promptVersion": _first_present(details.get("promptVersion"), decision.get("prompt_version")),
        "orderIntentId": order_intent_id,
        "orderId": order_id,
        "backtestId": backtest_id,
        "replaySessionId": replay_session_id,
        "replayTime": replay_time,
        "executionMode": execution_mode,
        "graphMode": graph_meta.get("graphMode"),
        "configuredMode": graph_meta.get("configuredMode"),
        "isFullGraph": graph_meta.get("isFullGraph"),
        "strongAcceptanceEligible": graph_meta.get("strongAcceptanceEligible"),
        "modeNote": graph_meta.get("modeNote"),
        "inputSummary": details.get("inputSummary") or decision,
        "agentOutputs": details.get("agentOutputs") or [],
        "riskCheckResult": risk,
        "riskUnavailable": bool(
            event_type == "RISK_CHECK_UNAVAILABLE"
            or details.get("riskUnavailable") is True
            or risk.get("riskUnavailable") is True
        ),
        "executionResult": execution,
        "executionStatus": execution_status,
        "riskStatus": risk_status,
        "source": source,
        "createdAt": _iso(_row_get(row, "created_at")),
        "created_at": _iso(_row_get(row, "created_at")),
        "payloadHash": _row_get(row, "payload_hash"),
        "prevHash": _row_get(row, "prev_hash"),
        "immutable": bool(_row_get(row, "immutable", True)),
        "synthetic": False,
        "auditSource": "audit_logs",
        "auditLogBacked": True,
        "raw": {
            "action": _row_get(row, "action"),
            "user_id": _row_get(row, "user_id"),
            "resource": _row_get(row, "resource"),
            "details": details,
            "ip_address": _row_get(row, "ip_address"),
            "standard_columns": {
                "event_type": _row_get(row, "event_type"),
                "symbol": _row_get(row, "symbol"),
                "decision_id": _row_get(row, "decision_id"),
                "source_decision_id": _row_get(row, "source_decision_id"),
                "replay_decision_id": _row_get(row, "replay_decision_id"),
                "order_intent_id": _row_get(row, "order_intent_id"),
                "order_id": _row_get(row, "order_id"),
                "context_id": _row_get(row, "context_id"),
                "context_hash": _row_get(row, "context_hash"),
                "risk_status": _row_get(row, "risk_status"),
                "execution_status": _row_get(row, "execution_status"),
                "backtest_id": _row_get(row, "backtest_id"),
                "replay_session_id": _row_get(row, "replay_session_id"),
                "execution_mode": _row_get(row, "execution_mode"),
                "payload_hash": _row_get(row, "payload_hash"),
                "prev_hash": _row_get(row, "prev_hash"),
                "immutable": _row_get(row, "immutable", True),
            },
        },
    }


def _support_level(key: str, counts: Dict[str, int]) -> str:
    if key == "point_in_time":
        if counts.get("pit_backtests"):
            return "回测记录已写 PIT 元数据"
        return "已接入上下文" if counts["pit_factor_snapshots"] or counts["pit_signal_events"] else "需要补充 PIT 样例"
    if key == "decision_replay":
        return "已有完整回放" if counts["completed_replays"] else "可创建，待跑完整样例"
    if key == "audit_trail":
        if counts.get("agent_decision_audit_logs"):
            return "已有原始 AGENT_DECISION 审计记录"
        if counts.get("coordination_history"):
            return "仅有决策历史，缺原始审计事件"
        return "待产生记录"
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
                "agent_decision_audit_logs": await _scalar(
                    session,
                    """
                    SELECT COUNT(*)
                    FROM audit_logs
                    WHERE action = 'AGENT_DECISION'
                    """,
                ),
                "strict_snapshot_audit_logs": await _scalar(
                    session,
                    """
                    SELECT COUNT(*)
                    FROM audit_logs
                    WHERE action = 'AGENT_DECISION'
                      AND details ? 'normalizedSnapshot'
                    """,
                ),
                "order_intent_events": await _scalar(
                    session,
                    """
                    SELECT COUNT(*)
                    FROM audit_logs
                    WHERE action LIKE 'ORDER_INTENT_%'
                       OR action IN ('ORDER_INTENT_CREATED','RISK_CHECK_PASSED','RISK_BLOCKED','PAPER_ORDER_FILLED','PAPER_ORDER_REJECTED','HOLD_RECORDED')
                       OR details->>'orderIntentId' IS NOT NULL
                       OR details->'intent'->>'intent_id' IS NOT NULL
                    """,
                ),
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
                        f"""
                        SELECT {AUDIT_RECORD_SELECT_COLUMNS}
                        FROM audit_logs
                        ORDER BY created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings().all()

            order_intent_rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT {AUDIT_RECORD_SELECT_COLUMNS}
                        FROM audit_logs
                        WHERE action LIKE 'ORDER_INTENT_%'
                           OR action IN ('ORDER_INTENT_CREATED','RISK_CHECK_PASSED','RISK_BLOCKED','PAPER_ORDER_FILLED','PAPER_ORDER_REJECTED','HOLD_RECORDED')
                           OR details->>'orderIntentId' IS NOT NULL
                           OR details->'intent'->>'intent_id' IS NOT NULL
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

            latest_order_intents = [
                {
                    "id": row["id"],
                    "action": row["action"],
                    "user_id": row["user_id"],
                    "resource": row["resource"],
                    "details": _safe_dict(row["details"]),
                    "ip_address": row["ip_address"],
                    "created_at": _iso(row["created_at"]),
                }
                for row in order_intent_rows
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
                    "status": "ready" if counts["agent_decision_audit_logs"] else ("partial" if counts["coordination_history"] else "todo"),
                    "description": (
                        "每次 Agent 决策都有原始 AGENT_DECISION 审计事件，详情页可追溯输入快照、角色意见和最终建议。"
                        if counts["agent_decision_audit_logs"]
                        else "已有 coordination_history 决策历史，但缺原始 AGENT_DECISION 审计事件时只能兼容展示，不能算强验收通过。"
                    ),
                },
                {
                    "key": "execution_chain",
                    "title": "执行闭环",
                    "support_level": "已有 OrderIntent 记录" if counts["order_intent_events"] else "待生成 OrderIntent 样例",
                    "status": "ready" if counts["order_intent_events"] else "partial",
                    "description": "TradingAgents 建议可手动生成 OrderIntent，经 RiskGuard 检查后进入模拟盘；WAIT/观望会明确记录为 NO_ACTION，不会下单。",
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
                "latest_order_intents": latest_order_intents,
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
            "latest_order_intents": [],
            "latest_decisions": [],
            "comparison_candidates": [],
        }


@router.get("/records")
async def list_audit_records(
    symbol: Optional[str] = Query(None),
    eventType: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    executionStatus: Optional[str] = Query(None),
    riskStatus: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    decisionId: Optional[int] = Query(None),
    orderIntentId: Optional[str] = Query(None),
    orderId: Optional[str] = Query(None),
    backtestId: Optional[int] = Query(None),
    replaySessionId: Optional[str] = Query(None),
    executionMode: Optional[str] = Query(None),
    startTime: Optional[datetime] = Query(None),
    endTime: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List immutable AuditRecord rows with PRD stage-2 filters."""
    where = ["1=1"]
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if symbol:
        where.append("(symbol = :symbol OR resource = :symbol OR details->>'symbol' = :symbol OR details->'intent'->>'symbol' = :symbol)")
        params["symbol"] = symbol.upper()
    if eventType:
        where.append(
            """
            (
              event_type = :event_type
              OR action = :event_type
              OR details->>'eventType' = :event_type
              OR details->>'event_type' = :event_type
              OR (:event_type = 'PAPER_ORDER_FILLED' AND action IN ('ORDER_CREATE','ORDER_FILL','ORDER_INTENT_EXECUTED'))
              OR (:event_type = 'PAPER_ORDER_REJECTED' AND action IN ('ORDER_CANCEL'))
              OR (:event_type = 'HOLD_RECORDED' AND action IN ('ORDER_INTENT_NOOP'))
              OR (:event_type = 'ORDER_INTENT_CREATED' AND action IN ('ORDER_INTENT_PREVIEW'))
              OR (:event_type = 'RISK_CHECK_PASSED' AND action IN ('ORDER_INTENT_RISK_CHECKED'))
              OR (:event_type = 'RISK_BLOCKED' AND action IN ('ORDER_INTENT_BLOCKED'))
            )
            """
        )
        params["event_type"] = eventType
    if executionStatus:
        where.append(
            """
            (
              execution_status = :execution_status
              OR details->'executionResult'->>'status' = :execution_status
              OR details->'execution'->>'status' = :execution_status
              OR (:execution_status = 'FILLED' AND (event_type = 'PAPER_ORDER_FILLED' OR action IN ('PAPER_ORDER_FILLED','ORDER_CREATE','ORDER_FILL')))
              OR (:execution_status = 'REJECTED' AND (event_type = 'PAPER_ORDER_REJECTED' OR action IN ('PAPER_ORDER_REJECTED','ORDER_CANCEL')))
            )
            """
        )
        params["execution_status"] = executionStatus.upper()
    if riskStatus:
        where.append(
            """
            (
              risk_status = :risk_status
              OR details->>'riskStatus' = :risk_status
              OR details->>'risk_status' = :risk_status
              OR details->'riskCheckResult'->>'status' = :risk_status
              OR details->'risk_preview'->>'status' = :risk_status
              OR (:risk_status = 'blocked' AND (
                    event_type = 'RISK_BLOCKED'
                    OR action = 'RISK_BLOCKED'
                    OR details->>'eventType' = 'RISK_BLOCKED'
                    OR details->'riskCheckResult'->>'passed' = 'false'
                    OR details->'risk_preview'->>'allowed' = 'false'
                 ))
              OR (:risk_status = 'passed' AND (
                    event_type = 'RISK_CHECK_PASSED'
                    OR action = 'RISK_CHECK_PASSED'
                    OR details->>'eventType' = 'RISK_CHECK_PASSED'
                    OR details->'riskCheckResult'->>'passed' = 'true'
                    OR details->'risk_preview'->>'allowed' = 'true'
                 ))
              OR (:risk_status = 'unavailable' AND (
                    event_type = 'RISK_CHECK_UNAVAILABLE'
                    OR action = 'RISK_CHECK_UNAVAILABLE'
                    OR details->>'eventType' = 'RISK_CHECK_UNAVAILABLE'
                 ))
            )
            """
        )
        params["risk_status"] = riskStatus.lower()
    if decisionId is not None:
        where.append(
            """
            (
              decision_id = :decision_id_int
              OR source_decision_id = :decision_id_int
              OR replay_decision_id = :decision_id_int
              OR details->>'decisionId' = :decision_id
              OR details->>'sourceDecisionId' = :decision_id
              OR details->>'replayDecisionId' = :decision_id
              OR details->'intent'->>'decision_id' = :decision_id
              OR details->'intent'->>'sourceDecisionId' = :decision_id
              OR details->'decision'->>'id' = :decision_id
            )
            """
        )
        params["decision_id_int"] = decisionId
        params["decision_id"] = str(decisionId)
    if orderIntentId:
        where.append(
            """
            (
              order_intent_id = :order_intent_id
              OR details->>'orderIntentId' = :order_intent_id
              OR details->'intent'->>'id' = :order_intent_id
              OR details->'intent'->>'intent_id' = :order_intent_id
            )
            """
        )
        params["order_intent_id"] = orderIntentId
    if orderId:
        where.append(
            """
            (
              order_id = :order_id
              OR details->>'orderId' = :order_id
              OR details->>'order_id' = :order_id
              OR details->'execution'->>'order_id' = :order_id
              OR details->'executionResult'->>'orderId' = :order_id
              OR details->'executionResult'->>'order_id' = :order_id
            )
            """
        )
        params["order_id"] = orderId
    if backtestId is not None:
        where.append("(backtest_id = :backtest_id_int OR details->>'backtestId' = :backtest_id OR details->>'backtest_id' = :backtest_id)")
        params["backtest_id_int"] = backtestId
        params["backtest_id"] = str(backtestId)
    if replaySessionId:
        where.append("(replay_session_id = :replay_session_id OR details->>'replaySessionId' = :replay_session_id OR details->>'replay_session_id' = :replay_session_id)")
        params["replay_session_id"] = replaySessionId
    if executionMode:
        where.append("(execution_mode = :execution_mode OR details->>'executionMode' = :execution_mode OR details->>'execution_mode' = :execution_mode OR details->'executionResult'->>'executionMode' = :execution_mode)")
        params["execution_mode"] = executionMode
    if source:
        where.append(
            """
            (
              details->>'source' = :source
              OR details->'intent'->>'source' = :source
              OR details->'execution'->>'source' = :source
              OR details->'executionResult'->>'source' = :source
            )
            """
        )
        params["source"] = source
    if action:
        where.append(
            """
            (
              action = :business_action
              OR details->>'action' = :business_action
              OR details->'intent'->>'action' = :business_action
              OR details->'decision'->>'final_signal' = :business_action
            )
            """
        )
        params["business_action"] = action.upper()
    if startTime:
        where.append("created_at >= :start_time")
        params["start_time"] = startTime
    if endTime:
        where.append("created_at <= :end_time")
        params["end_time"] = endTime

    where_sql = " AND ".join(where)
    async with get_db() as session:
        total = int(
            (
                await session.execute(
                    text(f"SELECT COUNT(*) FROM audit_logs WHERE {where_sql}"),
                    params,
                )
            ).scalar()
            or 0
        )
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT {AUDIT_RECORD_SELECT_COLUMNS}
                    FROM audit_logs
                    WHERE {where_sql}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()

    records = [_audit_record_payload(row) for row in rows]
    if action:
        normalized_action = action.upper()
        records = [row for row in records if str(row.get("action") or "").upper() == normalized_action]
    if executionStatus:
        normalized_status = executionStatus.upper()
        records = [row for row in records if str(row.get("executionStatus") or "").upper() == normalized_status]
    if riskStatus:
        normalized_risk_status = riskStatus.lower()
        records = [row for row in records if str(row.get("riskStatus") or "").lower() == normalized_risk_status]

    return {
        "schema_version": "audit_records.v1",
        "generated_at": datetime.utcnow().isoformat(),
        "immutability_note": "审计记录写入后不可修改，后续变化通过新增事件记录追踪。",
        "data": records,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "symbol": symbol,
            "eventType": eventType,
            "action": action,
            "executionStatus": executionStatus,
            "riskStatus": riskStatus,
            "source": source,
            "decisionId": decisionId,
            "orderIntentId": orderIntentId,
            "orderId": orderId,
            "backtestId": backtestId,
            "replaySessionId": replaySessionId,
            "executionMode": executionMode,
            "startTime": _iso(startTime),
            "endTime": _iso(endTime),
        },
    }


@router.get("/records/{audit_id}")
async def get_audit_record(audit_id: int) -> Dict[str, Any]:
    """Return one immutable AuditRecord with normalized fields and raw JSON."""
    async with get_db() as session:
        row = (
            await session.execute(
                text(
                    f"""
                    SELECT {AUDIT_RECORD_SELECT_COLUMNS}
                    FROM audit_logs
                    WHERE id = :audit_id
                    """
                ),
                {"audit_id": audit_id},
            )
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"Audit record {audit_id} not found")

    return {
        "schema_version": "audit_record.v1",
        "generated_at": datetime.utcnow().isoformat(),
        "immutability_note": "审计记录写入后不可修改，后续变化通过新增事件记录追踪。",
        "audit_record": _audit_record_payload(row),
    }


@router.get("/records/{audit_id}/export")
async def export_audit_record(audit_id: int) -> Dict[str, Any]:
    """Export one immutable audit log row as JSON for manual review."""
    async with get_db() as session:
        row = (
            await session.execute(
                text(
                    f"""
                    SELECT {AUDIT_RECORD_SELECT_COLUMNS}
                    FROM audit_logs
                    WHERE id = :audit_id
                    """
                ),
                {"audit_id": audit_id},
            )
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"Audit record {audit_id} not found")

    details = _repair_json(_safe_dict(row["details"]))
    standard_record = _audit_record_payload(row)
    decision_ids = _int_ids(
        [
            standard_record.get("decisionId"),
            standard_record.get("sourceDecisionId"),
            standard_record.get("replayDecisionId"),
        ],
        limit=3,
    )

    decisions = []
    if decision_ids:
        placeholders, decision_params = _in_clause("decision_id_", decision_ids)
        async with get_db() as session:
            decision_rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT id, symbol, timestamp, final_signal, confidence, risk_veto,
                               summary, input_snapshot_ids, role_opinions, agent_signals,
                               position_advice, risk_notes, created_at,
                               context_id, context_hash, available_time,
                               model_version, prompt_version
                        FROM coordination_history
                        WHERE id IN ({placeholders})
                        """
                    ),
                    decision_params,
                )
            ).mappings().all()
        for decision_row in decision_rows:
            decisions.append(
                {
                "id": decision_row["id"],
                "symbol": decision_row["symbol"],
                "timestamp": _iso(decision_row["timestamp"]),
                "final_signal": decision_row["final_signal"],
                "confidence": _safe_float(decision_row["confidence"]),
                "risk_veto": bool(decision_row["risk_veto"]),
                "summary": decision_row["summary"] or "",
                "input_snapshot_ids": _safe_dict(decision_row["input_snapshot_ids"]),
                "role_opinions": decision_row["role_opinions"] or [],
                "agent_signals": decision_row["agent_signals"] or [],
                "position_advice": _safe_dict(decision_row["position_advice"]),
                "risk_notes": decision_row["risk_notes"] or "",
                "created_at": _iso(decision_row["created_at"]),
                "context_id": decision_row["context_id"],
                "context_hash": decision_row["context_hash"],
                "available_time": _iso(decision_row["available_time"]),
                "model_version": decision_row["model_version"],
                "prompt_version": decision_row["prompt_version"],
                }
            )

    return {
        "schema_version": "audit_export.v1",
        "exported_at": datetime.utcnow().isoformat(),
        "immutability_note": "This endpoint only reads audit_logs and related decision context; it does not modify persisted records.",
        "audit_record": {
            "id": _row_get(row, "id"),
            "action": _row_get(row, "action"),
            "user_id": _row_get(row, "user_id"),
            "resource": _row_get(row, "resource"),
            "event_type": _row_get(row, "event_type"),
            "symbol": _row_get(row, "symbol"),
            "decision_id": _row_get(row, "decision_id"),
            "source_decision_id": _row_get(row, "source_decision_id"),
            "replay_decision_id": _row_get(row, "replay_decision_id"),
            "order_intent_id": _row_get(row, "order_intent_id"),
            "order_id": _row_get(row, "order_id"),
            "context_id": _row_get(row, "context_id"),
            "context_hash": _row_get(row, "context_hash"),
            "risk_status": _row_get(row, "risk_status"),
            "execution_status": _row_get(row, "execution_status"),
            "backtest_id": _row_get(row, "backtest_id"),
            "replay_session_id": _row_get(row, "replay_session_id"),
            "execution_mode": _row_get(row, "execution_mode"),
            "payload_hash": _row_get(row, "payload_hash"),
            "prev_hash": _row_get(row, "prev_hash"),
            "immutable": _row_get(row, "immutable", True),
            "details": details,
            "ip_address": _row_get(row, "ip_address"),
            "created_at": _iso(_row_get(row, "created_at")),
        },
        "standard_audit_record": standard_record,
        "linked_decision": decisions[0] if decisions else None,
        "linked_decisions": decisions,
    }


@router.post("/decisions/{decision_id}/replay")
async def replay_decision(decision_id: int) -> Dict[str, Any]:
    """Re-run TradingAgents from the source decision's PIT context.

    The original decision remains immutable; a replay always creates a new
    coordination_history row and append-only audit events.
    """
    async with get_db() as session:
        source_row = (
            await session.execute(
                text(
                    """
                    SELECT id, symbol, timestamp, final_signal, confidence,
                           vote_breakdown, risk_veto, summary, input_snapshot_ids,
                           role_opinions, agent_signals, bull_view, bear_view,
                           position_advice, risk_notes, created_at,
                           context_id, context_hash, available_time,
                           model_version, prompt_version
                    FROM coordination_history
                    WHERE id = :decision_id
                    """
                ),
                {"decision_id": decision_id},
            )
        ).mappings().first()
        source_audit_row = (
            await session.execute(
                text(
                    f"""
                    SELECT {AUDIT_RECORD_SELECT_COLUMNS}
                    FROM audit_logs
                    WHERE (event_type = 'AGENT_DECISION' OR action = 'AGENT_DECISION')
                      AND (
                        decision_id = :decision_id
                        OR details->>'decisionId' = :decision_id_text
                        OR details->'decision'->>'id' = :decision_id_text
                      )
                    ORDER BY created_at ASC, id ASC
                    LIMIT 1
                    """
                ),
                {"decision_id": decision_id, "decision_id_text": str(decision_id)},
            )
        ).mappings().first()

    if not source_row:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

    source_decision = _decision_payload(source_row)
    source_audit_details = _repair_json(_safe_dict(source_audit_row["details"])) if source_audit_row else {}
    normalized_snapshot = _normalized_snapshot_from_details(source_audit_details)
    strict_snapshot_replay = bool(normalized_snapshot)
    fallback_reason = (
        None
        if strict_snapshot_replay
        else "原始 AGENT_DECISION 审计记录缺少 normalizedSnapshot；已降级为 PIT 重建上下文。"
    )
    replay_method = (
        "strict_audit_normalized_snapshot"
        if strict_snapshot_replay
        else "pit_rebuild_from_as_of_time_and_snapshot_ids"
    )
    snapshot_context = _analysis_context_from_snapshot(normalized_snapshot)
    snapshot_ids = (
        _safe_dict(snapshot_context.get("input_snapshot_ids"))
        or _safe_dict(source_decision.get("input_snapshot_ids"))
    )
    as_of_time = normalized_snapshot.get("as_of_time") if strict_snapshot_replay else (
        source_row["available_time"] or source_row["timestamp"]
    )
    if isinstance(as_of_time, str):
        try:
            as_of_time = datetime.fromisoformat(as_of_time.replace("Z", "+00:00"))
        except ValueError:
            as_of_time = source_row["available_time"] or source_row["timestamp"]
    if isinstance(as_of_time, datetime) and as_of_time.tzinfo is None:
        as_of_time = as_of_time.replace(tzinfo=timezone.utc)
    interval = str(snapshot_context.get("timeframe") or _extract_interval_from_snapshot(snapshot_ids))

    from app.services.audit_service import audit_service

    request_details = {
        "decisionId": decision_id,
        "sourceDecisionId": decision_id,
        "asOfTime": _iso(as_of_time),
        "contextId": source_decision.get("context_id"),
        "contextHash": source_decision.get("context_hash"),
        "snapshotId": snapshot_ids,
        "source": "audit_decision_replay",
        "strictSnapshotReplay": strict_snapshot_replay,
        "replayMethod": replay_method,
        "fallbackReason": fallback_reason,
        "inputSummary": {
            "sourceDecisionId": decision_id,
            "originalContextHash": source_decision.get("context_hash"),
            "snapshot_ids": snapshot_ids,
            "pitRule": "available_time <= as_of_time",
            "strictSnapshotReplay": strict_snapshot_replay,
            "normalizedSnapshotAvailable": strict_snapshot_replay,
            "fallbackReason": fallback_reason,
        },
    }
    if fallback_reason is None:
        request_details.pop("fallbackReason", None)
        request_details["inputSummary"].pop("fallbackReason", None)

    await audit_service.log_event(
        action="DECISION_REPLAY_REQUESTED",
        user_id="system",
        resource=source_decision["symbol"],
        details=request_details,
        ip_address="internal",
        raise_on_failure=True,
    )

    try:
        from app.agents.coordinator_agent import CoordinatorAgent

        coordinator = CoordinatorAgent(fast_mode=False)
        replay_result = await coordinator.coordinate_at(
            symbol=source_decision["symbol"],
            interval=interval,
            as_of_time=as_of_time,
            extra_input_snapshot_ids=None if strict_snapshot_replay else {
                "sourceDecisionId": decision_id,
                "replayOfDecisionId": decision_id,
                "original_snapshot_ids": snapshot_ids,
            },
            audit_metadata={
                "source": "audit_decision_replay",
                "sourceDecisionId": decision_id,
                "originalContextHash": source_decision.get("context_hash"),
                "replayKind": "decision_replay",
                "strictSnapshotReplay": strict_snapshot_replay,
                "replayMethod": replay_method,
                **({"fallbackReason": fallback_reason} if fallback_reason else {}),
            },
            draft_order_intent=True,
            analysis_context_override=snapshot_context if strict_snapshot_replay else None,
        )
        if replay_result.data_source == "error" or not replay_result.decision_id:
            raise RuntimeError(replay_result.summary or "TradingAgents replay failed")

        diff_summary = _decision_diff_summary(source_decision, replay_result)
        response = {
            "sourceDecisionId": decision_id,
            "replayDecisionId": replay_result.decision_id,
            "originalContextHash": source_decision.get("context_hash"),
            "replayContextHash": replay_result.context_hash,
            "strictSnapshotReplay": strict_snapshot_replay,
            "replayMethod": replay_method,
            "contextHashChanged": diff_summary.get("contextHashChanged"),
            "contextHashChangeReason": (
                "底层 PIT 数据可能被回填或修正；复跑会新增决策，不覆盖原决策。"
                if diff_summary.get("contextHashChanged")
                else None
            ),
            "fallbackReason": fallback_reason,
            "diffSummary": diff_summary,
            "auditUrl": f"/audit?decision_id={replay_result.decision_id}",
        }
        if fallback_reason is None:
            response.pop("fallbackReason", None)

        completed_details = {
            "decisionId": replay_result.decision_id,
            "sourceDecisionId": decision_id,
            "replayDecisionId": replay_result.decision_id,
            "asOfTime": _iso(as_of_time),
            "contextId": replay_result.context_id,
            "contextHash": replay_result.context_hash,
            "originalContextHash": source_decision.get("context_hash"),
            "replayContextHash": replay_result.context_hash,
            "snapshotId": replay_result.input_snapshot_ids,
            "source": "audit_decision_replay",
            "strictSnapshotReplay": strict_snapshot_replay,
            "replayMethod": replay_method,
            "fallbackReason": fallback_reason,
            "contextHashChanged": diff_summary.get("contextHashChanged"),
            "contextHashChangeReason": (
                "底层 PIT 数据可能被回填或修正；复跑会新增决策，不覆盖原决策。"
                if diff_summary.get("contextHashChanged")
                else None
            ),
            "diffSummary": diff_summary,
            "inputSummary": {
                "sourceDecisionId": decision_id,
                "replayDecisionId": replay_result.decision_id,
                "originalContextHash": source_decision.get("context_hash"),
                "replayContextHash": replay_result.context_hash,
                "pitRule": "available_time <= as_of_time",
                "strictSnapshotReplay": strict_snapshot_replay,
                "normalizedSnapshotAvailable": strict_snapshot_replay,
                "fallbackReason": fallback_reason,
            },
            "decision": {
                "id": replay_result.decision_id,
                "final_signal": replay_result.final_signal.value,
                "confidence": replay_result.confidence,
                "context_hash": replay_result.context_hash,
                "timestamp": _iso(replay_result.timestamp),
                "summary": replay_result.summary,
            },
            "agentOutputs": replay_result.role_opinions or replay_result.agent_signals,
        }
        if fallback_reason is None:
            completed_details.pop("fallbackReason", None)
            completed_details["inputSummary"].pop("fallbackReason", None)

        await audit_service.log_event(
            action="DECISION_REPLAY_COMPLETED",
            user_id="system",
            resource=source_decision["symbol"],
            details=completed_details,
            ip_address="internal",
            raise_on_failure=True,
        )
        return response
    except Exception as exc:
        logger.error("Decision replay failed for %s: %s", decision_id, exc, exc_info=True)
        failed_details = {
            "decisionId": decision_id,
            "sourceDecisionId": decision_id,
            "asOfTime": _iso(as_of_time),
            "contextHash": source_decision.get("context_hash"),
            "source": "audit_decision_replay",
            "strictSnapshotReplay": strict_snapshot_replay,
            "replayMethod": replay_method,
            "fallbackReason": fallback_reason,
            "error": str(exc),
            "inputSummary": {
                "sourceDecisionId": decision_id,
                "originalContextHash": source_decision.get("context_hash"),
                "pitRule": "available_time <= as_of_time",
                "strictSnapshotReplay": strict_snapshot_replay,
                "normalizedSnapshotAvailable": strict_snapshot_replay,
                "fallbackReason": fallback_reason,
            },
        }
        if fallback_reason is None:
            failed_details.pop("fallbackReason", None)
            failed_details["inputSummary"].pop("fallbackReason", None)
        await audit_service.log_event(
            action="DECISION_REPLAY_FAILED",
            user_id="system",
            resource=source_decision["symbol"],
            details=failed_details,
            ip_address="internal",
            raise_on_failure=True,
        )
        raise HTTPException(status_code=502, detail=f"Decision replay failed: {exc}")


@router.get("/decisions/{decision_id}")
async def get_decision_audit_detail(decision_id: int) -> Dict[str, Any]:
    """Return one decision with its immutable audit and execution chain.

    This endpoint is intentionally read-only. It joins the persisted
    coordination decision with OrderIntent audit events and paper trades so the
    frontend can show the PRD stage-2 audit trail without inventing rows.
    """
    async with get_db() as session:
        decision_row = (
            await session.execute(
                text(
                    """
                    SELECT id, symbol, timestamp, final_signal, confidence,
                           vote_breakdown, risk_veto, summary, agent_signals,
                           bull_view, bear_view, input_snapshot_ids, role_opinions,
                           position_advice, risk_notes, created_at,
                           context_id, context_hash, available_time,
                           model_version, prompt_version
                    FROM coordination_history
                    WHERE id = :decision_id
                    """
                ),
                {"decision_id": decision_id},
            )
        ).mappings().first()

        if not decision_row:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

        snapshot_for_query = _safe_dict(decision_row["input_snapshot_ids"])
        factor_ids = _int_ids(snapshot_for_query.get("factor_snapshot_ids") or snapshot_for_query.get("factor_ids"), limit=40)
        signal_ids = _int_ids(snapshot_for_query.get("signal_event_ids") or snapshot_for_query.get("signal_ids"), limit=40)

        factor_rows = []
        if factor_ids:
            placeholders, factor_params = _in_clause("factor_id_", factor_ids)
            factor_rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT fs.id, fs.symbol, fs.timestamp, fs.available_time, fs.as_of_time,
                               fs.factor_name, fs.factor_value, fs.provider, fs.data_source,
                               fs.source_version, fs.schema_version,
                               fd.display_name, fd.description
                        FROM factor_snapshots fs
                        LEFT JOIN factor_definitions fd ON fd.factor_name = fs.factor_name
                        WHERE fs.id IN ({placeholders})
                        ORDER BY fs.timestamp DESC
                        """
                    ),
                    factor_params,
                )
            ).mappings().all()

        signal_rows = []
        if signal_ids:
            placeholders, signal_params = _in_clause("signal_id_", signal_ids)
            signal_rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT id, symbol, timestamp, available_time, as_of_time,
                               signal_type, signal_value, confidence, source_strategy,
                               strategy_id, provider, data_source, source_version, schema_version
                        FROM signal_events
                        WHERE id IN ({placeholders})
                        ORDER BY timestamp DESC
                        """
                    ),
                    signal_params,
                )
            ).mappings().all()

        order_intent_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT {AUDIT_RECORD_SELECT_COLUMNS}
                    FROM audit_logs
                    WHERE (
                        decision_id = :decision_id
                        OR source_decision_id = :decision_id
                        OR replay_decision_id = :decision_id
                        OR details->>'decisionId' = :decision_id_text
                        OR details->'intent'->>'decision_id' = :decision_id_text
                        OR details->'intent'->>'sourceDecisionId' = :decision_id_text
                        OR details->'decision'->>'id' = :decision_id_text
                    )
                    ORDER BY created_at ASC
                    """
                ),
                {"decision_id": decision_id, "decision_id_text": str(decision_id)},
            )
        ).mappings().all()

        intent_ids_for_trade_query: List[str] = []
        for row in order_intent_rows:
            details = _repair_json(_safe_dict(row["details"]))
            intent = _safe_dict(details.get("intent"))
            intent_id = _first_present(
                details.get("orderIntentId"),
                intent.get("id"),
                intent.get("intent_id"),
            )
            if intent_id:
                intent_ids_for_trade_query.append(str(intent_id))
        intent_ids_for_trade_query = list(dict.fromkeys(intent_ids_for_trade_query))[:50]
        if intent_ids_for_trade_query:
            placeholders = ", ".join(f":intent_id_{index}" for index, _ in enumerate(intent_ids_for_trade_query))
            trade_params = {f"intent_id_{index}": value for index, value in enumerate(intent_ids_for_trade_query)}
            trade_where = f"client_order_id IN ({placeholders})"
        else:
            trade_params = {"intent_prefix": f"OI-{decision_id}-%"}
            trade_where = "client_order_id LIKE :intent_prefix"
        trade_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT id, strategy_id, client_order_id, symbol, exchange_id, side,
                           order_type, quantity, price, benchmark_price, fee,
                           funding_fee, pnl, status, mode, session_id, data_source,
                           created_at
                    FROM paper_trades
                    WHERE {trade_where}
                    ORDER BY created_at DESC
                    LIMIT 50
                    """
                ),
                trade_params,
            )
        ).mappings().all()

        audit_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT {AUDIT_RECORD_SELECT_COLUMNS}
                    FROM audit_logs
                    WHERE (
                        decision_id = :decision_id
                        OR source_decision_id = :decision_id
                        OR replay_decision_id = :decision_id
                        OR details->>'decisionId' = :decision_id_text
                        OR details->'intent'->>'decision_id' = :decision_id_text
                        OR details->'intent'->>'sourceDecisionId' = :decision_id_text
                        OR details->'decision'->>'id' = :decision_id_text
                    )
                    ORDER BY created_at ASC, id ASC
                    """
                ),
                {"decision_id": decision_id, "decision_id_text": str(decision_id)},
            )
        ).mappings().all()

        replay_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT {AUDIT_RECORD_SELECT_COLUMNS}
                    FROM audit_logs
                    WHERE (event_type IN (
                        'DECISION_REPLAY_REQUESTED',
                        'DECISION_REPLAY_COMPLETED',
                        'DECISION_REPLAY_FAILED'
                    )
                    OR action IN (
                        'DECISION_REPLAY_REQUESTED',
                        'DECISION_REPLAY_COMPLETED',
                        'DECISION_REPLAY_FAILED'
                    ))
                      AND (
                        decision_id = :decision_id
                        OR source_decision_id = :decision_id
                        OR replay_decision_id = :decision_id
                        OR details->>'decisionId' = :decision_id_text
                        OR details->>'sourceDecisionId' = :decision_id_text
                        OR details->>'replayDecisionId' = :decision_id_text
                      )
                    ORDER BY created_at ASC, id ASC
                    """
                ),
                {"decision_id": decision_id, "decision_id_text": str(decision_id)},
            )
        ).mappings().all()

    decision = _decision_payload(decision_row)
    snapshot = _safe_dict(decision.get("input_snapshot_ids"))
    role_opinions = _safe_list(decision.get("role_opinions"))
    agent_signals = _safe_list(decision.get("agent_signals"))
    roles = agent_signals if len(agent_signals) > len(role_opinions) else (role_opinions or agent_signals)
    for role in roles:
        if isinstance(role, dict) and not role.get("data_source_chain"):
            role["data_source_chain"] = "AnalysisContext / OpenBB / CCXT / ClickHouse / 因子信号（推断）"
    decision_time = decision_row["timestamp"]

    def _role_reasoning_for(opinions: set[str]) -> str:
        parts = []
        for role in roles:
            if not isinstance(role, dict):
                continue
            opinion = str(role.get("opinion") or "").lower()
            reasoning = role.get("reasoning")
            if opinion in opinions and reasoning:
                parts.append(f"[{role.get('role') or 'role'}] {str(reasoning)[:700]}")
        return "\n".join(parts)

    final_signal = str(decision.get("final_signal") or "").upper()
    if not decision.get("bull_view"):
        decision["bull_view"] = _role_reasoning_for({"buy", "bullish", "long"}) or "未形成独立多头结论；看多依据已汇总在角色分析和投票中。"
    if not decision.get("bear_view"):
        decision["bear_view"] = _role_reasoning_for({"sell", "bearish", "short"}) or "未形成独立空头结论；看空依据已汇总在角色分析和投票中。"
    if not decision.get("risk_notes"):
        if decision.get("risk_veto"):
            decision["risk_notes"] = "本次决策被风险控制标记，建议保持观望或降低仓位。"
        elif final_signal in {"WAIT", "HOLD"}:
            decision["risk_notes"] = "最终建议为 WAIT：证据不充分或多空分歧，暂不生成实际下单。"
        else:
            decision["risk_notes"] = "未触发风控否决；仍需按账户风险限额控制仓位。"
    if not decision.get("position_advice"):
        decision["position_advice"] = {
            "action": final_signal or "WAIT",
            "position_ratio": 0.0 if final_signal in {"WAIT", "HOLD"} else min(_safe_float(decision.get("confidence")), 0.5),
            "sizing_note": "WAIT 不建立新仓位。" if final_signal in {"WAIT", "HOLD"} else "按置信度和账户风险限额小仓位执行。",
            "risk_note": decision["risk_notes"],
        }

    order_intents = [
        {
            "id": row["id"],
            "action": row["action"],
            "user_id": row["user_id"],
            "resource": row["resource"],
            "details": _safe_dict(row["details"]),
            "ip_address": row["ip_address"],
            "created_at": _iso(row["created_at"]),
            "export_url": f"/api/v1/audit/records/{row['id']}/export",
        }
        for row in order_intent_rows
    ]
    intent_ids = {
        _safe_dict(_safe_dict(row.get("details")).get("intent")).get("intent_id")
        for row in order_intents
    }
    intent_ids.discard(None)

    linked_trades = []
    for row in trade_rows:
        client_order_id = row["client_order_id"]
        if intent_ids and client_order_id not in intent_ids:
            continue
        if not intent_ids and client_order_id and not str(client_order_id).startswith(f"OI-{decision_id}-"):
            continue
        linked_trades.append(
            {
                "id": row["id"],
                "strategy_id": row["strategy_id"],
                "client_order_id": client_order_id,
                "symbol": row["symbol"],
                "exchange_id": row["exchange_id"],
                "side": row["side"],
                "order_type": row["order_type"],
                "quantity": _safe_float(row["quantity"]),
                "price": _safe_float(row["price"]),
                "benchmark_price": _safe_float(row["benchmark_price"]),
                "fee": _safe_float(row["fee"]),
                "funding_fee": _safe_float(row["funding_fee"]),
                "pnl": _safe_float(row["pnl"]),
                "status": row["status"],
                "mode": row["mode"],
                "session_id": row["session_id"],
                "data_source": row["data_source"],
                "created_at": _iso(row["created_at"]),
            }
        )

    audit_timeline = [_audit_record_payload(row) for row in audit_rows]
    original_agent_decision_audit = next(
        (
            item
            for item in audit_timeline
            if item.get("eventType") == "AGENT_DECISION"
            and item.get("synthetic") is not True
            and item.get("auditLogBacked") is True
        ),
        None,
    )
    original_agent_decision_audit_present = bool(original_agent_decision_audit)
    original_agent_details = (
        _safe_dict(_safe_dict(original_agent_decision_audit.get("raw")).get("details"))
        if original_agent_decision_audit
        else {}
    )
    graph_execution = _graph_execution_meta(
        _safe_dict(original_agent_decision_audit or {}),
        original_agent_details,
        _safe_dict(original_agent_details.get("decision")),
        _safe_dict(decision.get("position_advice")),
    )
    normalized_snapshot = _normalized_snapshot_from_details(original_agent_details)
    strict_snapshot_replay_available = bool(normalized_snapshot)
    normalized_bars_summary = _safe_dict(normalized_snapshot.get("bars_summary"))
    normalized_snapshot_ids = _safe_dict(normalized_snapshot.get("input_snapshot_ids"))
    normalized_factor_snapshot = _safe_dict(normalized_snapshot.get("latest_factors"))
    normalized_recent_signals = _safe_list(normalized_snapshot.get("recent_signals"))
    normalized_news_events = _safe_list(normalized_snapshot.get("news_events"))
    normalized_macro_events = _safe_list(normalized_snapshot.get("macro_events"))
    normalized_data_versions = _safe_dict(normalized_snapshot.get("data_versions"))
    replay_runs = []
    for row in replay_rows:
        details = _repair_json(_safe_dict(row["details"]))
        replay_input_summary = _safe_dict(details.get("inputSummary"))
        event_type = str(details.get("eventType") or row["action"])
        status = (
            "completed" if event_type == "DECISION_REPLAY_COMPLETED"
            else "failed" if event_type == "DECISION_REPLAY_FAILED"
            else "requested"
        )
        replay_decision_id = _first_present(details.get("replayDecisionId"), details.get("decisionId"))
        source_decision_id = _first_present(details.get("sourceDecisionId"), decision_id)
        original_context_hash = details.get("originalContextHash")
        replay_context_hash = details.get("replayContextHash") or details.get("contextHash")
        diff_summary = _safe_dict(details.get("diffSummary"))
        context_hash_changed = bool(
            _first_present(diff_summary.get("contextHashChanged"), details.get("contextHashChanged"))
        )
        if not context_hash_changed and original_context_hash and replay_context_hash:
            context_hash_changed = original_context_hash != replay_context_hash
        replay_strict_snapshot = bool(
            _first_present(
                details.get("strictSnapshotReplay"),
                replay_input_summary.get("strictSnapshotReplay"),
            )
        )
        fallback_reason = _first_present(
            details.get("fallbackReason"),
            replay_input_summary.get("fallbackReason"),
        )
        replay_runs.append(
            {
                "id": row["id"],
                "eventType": event_type,
                "status": status,
                "sourceDecisionId": source_decision_id,
                "replayDecisionId": replay_decision_id,
                "originalContextHash": original_context_hash,
                "replayContextHash": replay_context_hash,
                "contextHashChanged": context_hash_changed,
                "contextHashChangeReason": details.get("contextHashChangeReason") or (
                    "底层 PIT 数据可能被回填或修正；复跑会新增决策，不覆盖原决策。"
                    if context_hash_changed
                    else None
                ),
                "strictSnapshotReplay": replay_strict_snapshot,
                "replayMethod": details.get("replayMethod") or "pit_rebuild_from_as_of_time_and_snapshot_ids",
                "fallbackReason": fallback_reason,
                "diffSummary": diff_summary,
                "auditUrl": f"/audit?decision_id={replay_decision_id}" if replay_decision_id else None,
                "error": details.get("error"),
                "createdAt": _iso(row["created_at"]),
                "raw": details,
            }
        )
    if not original_agent_decision_audit_present:
        audit_timeline.insert(
            0,
            {
                "id": None,
                "eventType": "AGENT_DECISION",
                "action": decision.get("final_signal"),
                "symbol": decision.get("symbol"),
                "asOfTime": decision.get("timestamp"),
                "snapshotId": snapshot,
                "decisionId": decision_id,
                "orderIntentId": None,
                "orderId": None,
                "inputSummary": snapshot,
                "agentOutputs": roles,
                "riskCheckResult": {},
                "executionResult": {},
                "executionStatus": None,
                "riskStatus": "not_checked",
                "source": "coordination_history",
                "graphMode": graph_execution.get("graphMode"),
                "configuredMode": graph_execution.get("configuredMode"),
                "isFullGraph": graph_execution.get("isFullGraph"),
                "strongAcceptanceEligible": graph_execution.get("strongAcceptanceEligible"),
                "modeNote": graph_execution.get("modeNote"),
                "createdAt": decision.get("created_at") or decision.get("timestamp"),
                "immutable": False,
                "synthetic": True,
                "auditSource": "coordination_history",
                "auditLogBacked": False,
                "syntheticReason": "coordination_history 中存在决策，但 audit_logs 缺少 AGENT_DECISION 原始事件；此行仅用于详情展示。",
            },
        )

    input_summary = (
        _safe_dict(original_agent_decision_audit.get("inputSummary"))
        if original_agent_decision_audit
        else {}
    )
    if not input_summary and original_agent_details:
        input_summary = _safe_dict(original_agent_details.get("inputSummary"))
    if not input_summary:
        for record in audit_timeline:
            if record.get("synthetic") and original_agent_decision_audit_present:
                continue
            input_summary = _safe_dict(record.get("inputSummary"))
            if input_summary:
                break
            raw_details = _safe_dict(_safe_dict(record.get("raw")).get("details"))
            input_summary = _safe_dict(raw_details.get("inputSummary"))
            if input_summary:
                break
    if not input_summary and normalized_snapshot:
        last_bar = _safe_list(normalized_snapshot.get("bars"))[-1] if _safe_list(normalized_snapshot.get("bars")) else {}
        input_summary = {
            "snapshot_ids": normalized_snapshot_ids,
            "risk_notes": decision.get("risk_notes"),
            "factor_snapshot": normalized_factor_snapshot,
            "recent_signals": normalized_recent_signals,
            "price": _safe_dict(last_bar).get("close"),
            "bars_count": normalized_bars_summary.get("count"),
            "news_count": len(normalized_news_events),
            "macro_count": len(normalized_macro_events),
            "normalizedSnapshot": normalized_snapshot,
        }

    latest_intent = {}
    latest_risk = {}
    latest_execution = {}
    for record in audit_timeline:
        raw_details = _safe_dict(_safe_dict(record.get("raw")).get("details"))
        intent = _safe_dict(raw_details.get("intent"))
        if intent:
            latest_intent = intent
        risk = _safe_dict(raw_details.get("risk_preview") or raw_details.get("riskCheckResult"))
        if risk:
            latest_risk = risk
        execution = _safe_dict(raw_details.get("execution") or raw_details.get("executionResult"))
        if execution:
            latest_execution = execution

    factor_evidence = []
    for row in factor_rows:
        available_time = row["available_time"]
        pit_ok = bool(available_time and decision_time and available_time <= decision_time)
        factor_evidence.append(
            {
                "snapshotId": row["id"],
                "factorName": row["display_name"] or row["factor_name"],
                "rawFactorName": row["factor_name"],
                "value": _safe_float(row["factor_value"]),
                "signal": "因子证据",
                "strength": abs(_safe_float(row["factor_value"])),
                "explanation": row["description"] or "暂无说明",
                "availableTime": _iso(available_time),
                "asOfTime": _iso(row["as_of_time"]),
                "dataProvider": row["provider"] or row["data_source"] or "暂无数据",
                "dataVersion": row["source_version"] or row["schema_version"],
                "pitRulePassed": pit_ok,
            }
        )
    for row in signal_rows:
        available_time = row["available_time"]
        pit_ok = bool(available_time and decision_time and available_time <= decision_time)
        factor_evidence.append(
            {
                "snapshotId": row["id"],
                "factorName": row["source_strategy"] or row["signal_type"],
                "rawFactorName": row["signal_type"],
                "value": _safe_float(row["signal_value"]),
                "signal": row["signal_type"],
                "strength": _safe_float(row["confidence"]),
                "explanation": f"策略信号 {row['source_strategy'] or row['strategy_id'] or '暂无数据'}",
                "availableTime": _iso(available_time),
                "asOfTime": _iso(row["as_of_time"]),
                "dataProvider": row["provider"] or row["data_source"] or "暂无数据",
                "dataVersion": row["source_version"] or row["schema_version"],
                "pitRulePassed": pit_ok,
            }
        )
    if not factor_evidence and input_summary:
        captured_at = decision.get("available_time") or decision.get("timestamp")
        for name, value in _safe_dict(input_summary.get("factor_snapshot")).items():
            factor_evidence.append(
                {
                    "snapshotId": f"inputSummary.factor_snapshot.{name}",
                    "factorName": name,
                    "rawFactorName": name,
                    "value": _safe_float(value),
                    "signal": "审计输入因子",
                    "strength": abs(_safe_float(value)),
                    "explanation": "决策审计日志 inputSummary 捕获的因子值。",
                    "availableTime": captured_at,
                    "asOfTime": decision.get("timestamp"),
                    "dataProvider": "audit_input_summary",
                    "dataVersion": "inputSummary.v1",
                    "pitRulePassed": True,
                }
            )
        for idx, signal in enumerate(_safe_list(input_summary.get("recent_signals")), start=1):
            if not isinstance(signal, dict):
                continue
            signal_name = signal.get("strategy") or signal.get("source_strategy") or f"signal_{idx}"
            factor_evidence.append(
                {
                    "snapshotId": f"inputSummary.recent_signals.{idx}",
                    "factorName": signal_name,
                    "rawFactorName": signal_name,
                    "value": _safe_float(signal.get("conf") or signal.get("confidence")),
                    "signal": signal.get("type") or signal.get("signal_type") or "SIGNAL",
                    "strength": _safe_float(signal.get("conf") or signal.get("confidence")),
                    "explanation": "决策审计日志 inputSummary 捕获的近期策略信号。",
                    "availableTime": captured_at,
                    "asOfTime": decision.get("timestamp"),
                    "dataProvider": "audit_input_summary",
                    "dataVersion": "inputSummary.v1",
                    "pitRulePassed": True,
                }
            )

    def role_output(*keywords: str) -> Dict[str, Any]:
        for role in roles:
            label = " ".join(
                str(role.get(key, ""))
                for key in ("role", "agent_type", "agent", "label")
            ).lower()
            if any(keyword in label for keyword in keywords):
                # Ensure data_source_chain is present even if backend didn't record it
                if "data_source_chain" not in role:
                    role["data_source_chain"] = "AnalysisContext / OpenBB / CCXT / ClickHouse / 因子信号（推断）"
                return role
        return {
            "output": "暂无数据",
            "available": False,
            "data_source_chain": "AnalysisContext / OpenBB / CCXT / ClickHouse（该角色未产生独立输出）",
        }

    raw_agent_analysis = {
        "technicalAgent": role_output("technical", "market", "quantagent_market"),
        "newsAgent": role_output("news", "sentiment", "social"),
        "macroAgent": role_output("macro", "fundamental"),
        "riskAgent": role_output("risk"),
        "portfolioAgent": role_output("portfolio", "trader", "execution"),
        "finalDecision": role_output("final", "judge", "decision"),
    }
    agent_analysis = {
        key: value
        for key, value in raw_agent_analysis.items()
        if value.get("available", True) is not False
    }

    final_signal = str(decision.get("final_signal") or "").upper()
    no_action = final_signal in {"WAIT", "HOLD"}
    order_intent_detail = {
        "orderIntentId": latest_intent.get("id") or latest_intent.get("intent_id") or ("NO_ACTION" if no_action else None),
        "action": latest_intent.get("action") or decision.get("final_signal"),
        "side": latest_intent.get("side") or ("flat" if no_action else "暂无数据"),
        "positionRatio": latest_intent.get("positionRatio") or latest_intent.get("position_pct"),
        "quantity": latest_intent.get("quantity"),
        "confidence": latest_intent.get("confidence") or decision.get("confidence"),
        "validUntil": latest_intent.get("validUntil") or latest_intent.get("valid_until"),
        "reason": latest_intent.get("reason") or latest_intent.get("trigger_reason") or decision.get("summary") or ("最终建议为 WAIT，本次不生成下单意图。" if no_action else None),
        "status": latest_intent.get("status") or ("NO_ACTION" if no_action else "暂无数据"),
        "sourceDecisionId": latest_intent.get("sourceDecisionId") or latest_intent.get("decision_id") or decision_id,
    }

    execution_trade = linked_trades[0] if linked_trades else {}
    execution_result = {
        "paperOrderGenerated": bool(latest_execution or execution_trade),
        "orderId": latest_execution.get("order_id") or latest_execution.get("orderId") or (f"PT-{execution_trade.get('id')}" if execution_trade else None),
        "source": latest_execution.get("source") or execution_trade.get("mode") or "暂无数据",
        "fillPrice": latest_execution.get("fillPrice") or latest_execution.get("price") or execution_trade.get("price"),
        "filledAt": latest_execution.get("filledAt") or latest_execution.get("created_at") or execution_trade.get("created_at"),
        "fee": latest_execution.get("fee") or execution_trade.get("fee"),
        "slippage": latest_execution.get("slippage"),
        "realizedPnl": latest_execution.get("realizedPnl") or latest_execution.get("pnl") or execution_trade.get("pnl"),
        "orderStatus": latest_execution.get("status") or execution_trade.get("status") or "暂无数据",
        "positionAfterTrade": latest_execution.get("positionAfterTrade") or "暂无数据",
    }

    available_times = [item.get("availableTime") for item in factor_evidence if item.get("availableTime")]
    data_providers = [
        item.get("dataProvider")
        for item in factor_evidence
        if item.get("dataProvider") and item.get("dataProvider") != "暂无数据"
    ]
    data_versions = [item.get("dataVersion") for item in factor_evidence if item.get("dataVersion")]
    # ── Read bar count from bar_meta if available, else fallback to counting IDs ──
    raw_bar_meta = snapshot.get("bar_meta", {}) if isinstance(snapshot, dict) else {}
    bar_meta = raw_bar_meta[0] if isinstance(raw_bar_meta, list) and raw_bar_meta else raw_bar_meta
    bars_count = normalized_bars_summary.get("count")
    if bars_count is None:
        bars_count = bar_meta.get("count") if isinstance(bar_meta, dict) else None
    if bars_count is None:
        bars_count = _snapshot_count(snapshot, "bar_ids", "bar_snapshot_ids", "bars")
    snapshot_bars = _safe_list(normalized_snapshot.get("bars"))
    snapshot_last_bar = _safe_dict(snapshot_bars[-1]) if snapshot_bars else {}
    summary_factor_snapshot = normalized_factor_snapshot or _safe_dict(input_summary.get("factor_snapshot"))
    summary_recent_signals = normalized_recent_signals or _safe_list(input_summary.get("recent_signals"))
    summary_factor_count = len(summary_factor_snapshot)
    summary_signal_count = len(summary_recent_signals)
    summary_news_count = len(normalized_news_events) if normalized_snapshot else int(_safe_float(input_summary.get("news_count"), 0.0))
    summary_macro_count = len(normalized_macro_events) if normalized_snapshot else int(_safe_float(input_summary.get("macro_count"), 0.0))
    summary_snapshot_ids = normalized_snapshot_ids or _safe_dict(input_summary.get("snapshot_ids")) or snapshot
    input_material_source = "audit_logs.normalizedSnapshot" if normalized_snapshot else (
        "audit_logs.inputSummary" if input_summary else "coordination_history.input_snapshot_ids"
    )
    counts_source = {
        "bars": "normalizedSnapshot.bars" if snapshot_bars else ("bar_meta" if bars_count else "missing"),
        "factors": "normalizedSnapshot.latest_factors" if normalized_factor_snapshot else (
            "audit_logs.inputSummary.factor_snapshot" if _safe_dict(input_summary.get("factor_snapshot")) else "coordination_history.input_snapshot_ids"
        ),
        "signals": "normalizedSnapshot.recent_signals" if normalized_recent_signals else (
            "audit_logs.inputSummary.recent_signals" if _safe_list(input_summary.get("recent_signals")) else "coordination_history.input_snapshot_ids"
        ),
        "news": "normalizedSnapshot.news_events" if normalized_news_events else (
            "audit_logs.inputSummary.news_count" if input_summary.get("news_count") is not None else "coordination_history.input_snapshot_ids"
        ),
        "macro": "normalizedSnapshot.macro_events" if normalized_macro_events else (
            "audit_logs.inputSummary.macro_count" if input_summary.get("macro_count") is not None else "coordination_history.input_snapshot_ids"
        ),
    }
    normalized_data_version = (
        normalized_snapshot.get("schema_version")
        if normalized_snapshot
        else None
    )
    input_materials = {
        "source": input_material_source,
        "price": _first_present(input_summary.get("price"), snapshot_last_bar.get("close")),
        "riskNotes": input_summary.get("risk_notes"),
        "snapshotIds": summary_snapshot_ids,
        "bars": snapshot_bars,
        "newsEvents": normalized_news_events,
        "macroEvents": normalized_macro_events,
        "factorSnapshot": summary_factor_snapshot,
        "recentSignals": summary_recent_signals,
        "signalEvents": summary_recent_signals,
        "factorEvidence": factor_evidence,
        "normalizedSnapshot": normalized_snapshot or None,
        "countsSource": counts_source,
        "detailCompleteness": {
            "hasNormalizedSnapshot": bool(normalized_snapshot),
            "hasBars": bool(snapshot_bars),
            "hasFactorValues": bool(summary_factor_snapshot),
            "hasSignalRows": bool(summary_recent_signals),
            "hasNewsRows": bool(normalized_news_events),
            "hasMacroRows": bool(normalized_macro_events),
            "fallbackSource": input_material_source,
            "note": None if normalized_snapshot else "旧记录未固化完整 normalizedSnapshot；只能展示已保存摘要和可从快照 ID 查询到的证据。",
        },
        "barsCount": bars_count,
        "newsCount": summary_news_count,
        "macroCount": summary_macro_count,
        "factorsCount": summary_factor_count,
        "signalsCount": summary_signal_count,
    }
    role_input_materials = [
        {
            "role": role.get("role") or role.get("agent") or role.get("label") or f"role_{idx}",
            "label": role.get("label") or role.get("role") or f"角色 {idx}",
            "phase": role.get("phase"),
            "dataSourceChain": role.get("data_source_chain"),
            "inputMaterialSource": input_materials["source"],
            "sharedInputSnapshot": summary_snapshot_ids,
            "visibleData": {
                "price": input_materials["price"],
                "factorSnapshot": input_materials["factorSnapshot"],
                "recentSignals": input_materials["recentSignals"],
                "newsCount": summary_news_count,
                "macroCount": summary_macro_count,
            },
        }
        for idx, role in enumerate(roles, start=1)
        if isinstance(role, dict)
    ]

    input_snapshot = {
        "snapshotId": summary_snapshot_ids,
        "asOfTime": normalized_snapshot.get("as_of_time") or decision.get("timestamp"),
        "availableTime": (
            normalized_bars_summary.get("last_available_time")
            or _first_present(*available_times)
            or decision.get("available_time")
        ),
        "dataProvider": _first_present(*data_providers) or (
            ", ".join(_safe_list(normalized_bars_summary.get("providers")))
            if _safe_list(normalized_bars_summary.get("providers"))
            else "暂无数据"
        ),
        "barsCount": bars_count,
        "newsCount": _snapshot_count(snapshot, "news_payload_ids", "news_event_ids") or summary_news_count,
        "factorsCount": _snapshot_count(snapshot, "factor_snapshot_ids", "factor_ids") or summary_factor_count,
        "signalsCount": _snapshot_count(snapshot, "signal_event_ids", "signal_ids") or summary_signal_count,
        "macroCount": _snapshot_count(snapshot, "macro_keys", "macro_event_ids") or summary_macro_count,
        "price": input_materials["price"],
        "factorSnapshot": input_materials["factorSnapshot"],
        "recentSignals": input_materials["recentSignals"],
        "dataVersion": _first_present(*data_versions) or normalized_data_version or "暂无数据",
        "sourceVersion": _first_present(*data_versions) or normalized_data_version or "暂无数据",
        "dataVersions": normalized_data_versions or None,
        "barMeta": normalized_bars_summary or (bar_meta if isinstance(bar_meta, dict) and bar_meta else None),
    }

    def _time_lte(left: Any, right: Any) -> Optional[bool]:
        if not left or not right:
            return None
        try:
            left_dt = left if isinstance(left, datetime) else datetime.fromisoformat(str(left).replace("Z", "+00:00"))
            right_dt = right if isinstance(right, datetime) else datetime.fromisoformat(str(right).replace("Z", "+00:00"))
            if left_dt.tzinfo is not None and right_dt.tzinfo is None:
                right_dt = right_dt.replace(tzinfo=left_dt.tzinfo)
            if right_dt.tzinfo is not None and left_dt.tzinfo is None:
                left_dt = left_dt.replace(tzinfo=right_dt.tzinfo)
            return left_dt <= right_dt
        except Exception:
            return None

    pit_checks = [
        {
            "key": "point_in_time_rule",
            "label": "available_time <= as_of_time",
            "passed": _time_lte(input_snapshot.get("availableTime"), input_snapshot.get("asOfTime")),
            "detail": {
                "availableTime": input_snapshot.get("availableTime"),
                "asOfTime": input_snapshot.get("asOfTime"),
            },
        },
        {
            "key": "factor_signal_evidence",
            "label": "factor/signal evidence has no future data",
            "passed": all(item.get("pitRulePassed") is not False for item in factor_evidence) if factor_evidence else None,
            "detail": {
                "evidence_count": len(factor_evidence),
                "failed_count": len([item for item in factor_evidence if item.get("pitRulePassed") is False]),
            },
        },
        {
            "key": "role_outputs",
            "label": "role outputs persisted",
            "passed": len(roles) > 0,
            "detail": {"role_count": len(roles)},
        },
        {
            "key": "original_agent_decision_audit",
            "label": "original AGENT_DECISION audit log present",
            "passed": original_agent_decision_audit_present,
            "detail": {
                "auditLogId": original_agent_decision_audit.get("id") if original_agent_decision_audit else None,
                "syntheticAuditCount": len([row for row in audit_timeline if row.get("synthetic")]),
            },
        },
        {
            "key": "strict_snapshot_replay_available",
            "label": "normalizedSnapshot available for strict replay",
            "passed": strict_snapshot_replay_available,
            "detail": {
                "schemaVersion": normalized_snapshot.get("schema_version"),
                "contextHash": normalized_snapshot.get("context_hash"),
                "fallbackReason": None
                if strict_snapshot_replay_available
                else "原始 AGENT_DECISION 审计记录缺少 normalizedSnapshot；strict replay 会降级为 PIT 重建。",
            },
        },
        {
            "key": "context_hash",
            "label": "context hash persisted",
            "passed": bool(decision.get("context_hash")),
            "detail": {
                "contextId": decision.get("context_id"),
                "contextHash": decision.get("context_hash"),
            },
        },
        {
            "key": "full_graph_execution",
            "label": "full TradingAgentsGraph execution",
            "passed": graph_execution.get("isFullGraph"),
            "detail": {
                "graphMode": graph_execution.get("graphMode"),
                "configuredMode": graph_execution.get("configuredMode"),
                "strongAcceptanceEligible": graph_execution.get("strongAcceptanceEligible"),
                "modeNote": graph_execution.get("modeNote"),
                "fallbackReason": None
                if graph_execution.get("isFullGraph") is True
                else (
                    "当前为快速研究模式，不计入完整多 Agent 强验收。"
                    if graph_execution.get("isFullGraph") is False
                    else "旧记录未保存 TradingAgentsGraph 执行模式，无法判定是否完整图。"
                ),
            },
        },
    ]

    risk_guard = {
        "passed": latest_risk.get("passed") if "passed" in latest_risk else latest_risk.get("allowed"),
        "riskUnavailable": bool(
            latest_risk.get("riskUnavailable")
            or any(row.get("eventType") == "RISK_CHECK_UNAVAILABLE" for row in audit_timeline)
        ),
        "blockedReason": latest_risk.get("blockedReason") or latest_risk.get("blocked_reason") or latest_risk.get("reason"),
        "checkedRules": latest_risk.get("checkedRules") or latest_risk.get("checked_rules") or [],
    }
    decision_evidence = {
        "analysis_context": input_snapshot,
        "input_materials": input_materials,
        "role_outputs": roles,
        "agent_analysis": agent_analysis,
        "final_decision": decision,
        "draft_order_intent": order_intent_detail,
        "pit_checks": pit_checks,
        "replay_runs": replay_runs,
        "strictSnapshotReplay": strict_snapshot_replay_available,
        "strictSnapshotReplayAvailable": strict_snapshot_replay_available,
        "originalAgentDecisionAuditPresent": original_agent_decision_audit_present,
        "graphExecution": graph_execution,
    }
    execution_preview_or_result = {
        "risk_guard": risk_guard,
        "execution_result": execution_result,
        "paper_trades": linked_trades,
        "latest_risk_preview": latest_risk,
        "latest_execution": latest_execution,
        "riskUnavailable": risk_guard["riskUnavailable"],
    }

    synthetic_audit_count = len([row for row in audit_timeline if row.get("synthetic")])
    risk_unavailable = bool(risk_guard["riskUnavailable"])
    linked_backtest_id = _first_present(
        *[row.get("backtestId") for row in audit_timeline],
        *[
            _first_present(
                _safe_dict(row.get("details")).get("backtestId"),
                _safe_dict(row.get("details")).get("backtest_id"),
            )
            for row in order_intents
        ],
    )
    linked_replay_session_id = _first_present(
        *[row.get("replaySessionId") for row in audit_timeline],
        *[trade.get("session_id") for trade in linked_trades],
        *[
            _first_present(
                _safe_dict(row.get("details")).get("replaySessionId"),
                _safe_dict(row.get("details")).get("replay_session_id"),
            )
            for row in order_intents
        ],
    )
    analytics_url = (
        f"/analytics?replay_session_id={linked_replay_session_id}"
        f"{f'&backtest_id={linked_backtest_id}' if linked_backtest_id else ''}"
        if linked_replay_session_id
        else None
    )
    return {
        "schema_version": "decision_audit_detail.v1",
        "generated_at": datetime.utcnow().isoformat(),
        "immutability_note": "This endpoint only reads persisted decision, audit, and paper trade records.",
        "strictSnapshotReplay": strict_snapshot_replay_available,
        "strictSnapshotReplayAvailable": strict_snapshot_replay_available,
        "originalAgentDecisionAuditPresent": original_agent_decision_audit_present,
        "riskUnavailable": risk_unavailable,
        "syntheticAuditCount": synthetic_audit_count,
        "graphExecution": graph_execution,
        "basic_info": {
            "decisionId": decision["id"],
            "symbol": decision["symbol"],
            "action": decision["final_signal"],
            "side": order_intent_detail.get("side") or "暂无数据",
            "confidence": decision["confidence"],
            "createdAt": decision.get("created_at") or decision.get("timestamp"),
            "source": "coordination_history",
            "model": decision.get("model_version") or "TradingAgents / QuantAgent agentGraph",
            "agentGraph": "TradingAgentsGraph QuantAgent adapter",
            "status": "risk_veto" if decision.get("risk_veto") else "created",
            # ── Audit traceability fields ──
            "contextId": decision.get("context_id") or (f"ctx-{decision['id']}" if decision.get("id") else None),
            "contextHash": decision.get("context_hash"),
            "availableTime": decision.get("available_time"),
            "modelVersion": decision.get("model_version"),
            "promptVersion": decision.get("prompt_version"),
            "graphMode": graph_execution.get("graphMode"),
            "configuredMode": graph_execution.get("configuredMode"),
            "isFullGraph": graph_execution.get("isFullGraph"),
            "strongAcceptanceEligible": graph_execution.get("strongAcceptanceEligible"),
            "modeNote": graph_execution.get("modeNote"),
        },
        "input_snapshot": input_snapshot,
        "factor_evidence": factor_evidence,
        "agent_analysis": agent_analysis,
        "order_intent": order_intent_detail,
        "risk_guard": risk_guard,
        "execution_result": execution_result,
        "decision_evidence": decision_evidence,
        "draft_order_intent": order_intent_detail,
        "execution_preview_or_result": execution_preview_or_result,
        "pit_checks": pit_checks,
        "replay_runs": replay_runs,
        "audit_timeline": audit_timeline,
        "decision": decision,
        "trace_summary": {
            "input_snapshot_id_groups": len(summary_snapshot_ids),
            "factor_snapshots": _snapshot_count(snapshot, "factor_snapshot_ids", "factor_ids") or summary_factor_count,
            "signal_events": _snapshot_count(snapshot, "signal_event_ids", "signal_ids") or summary_signal_count,
            "news_events": _snapshot_count(snapshot, "news_payload_ids", "news_event_ids") or summary_news_count,
            "macro_events": _snapshot_count(snapshot, "macro_keys", "macro_event_ids") or summary_macro_count,
            "role_outputs": len(roles),
            "order_intent_events": len(order_intents),
            "paper_trades": len(linked_trades),
            "replay_runs": len(replay_runs),
            "risk_blocked": any(row.get("eventType") == "RISK_BLOCKED" for row in audit_timeline),
            "risk_unavailable": risk_unavailable,
            "synthetic_audit_events": synthetic_audit_count,
            "executed": any(row.get("eventType") == "PAPER_ORDER_FILLED" for row in audit_timeline),
        },
        "role_outputs": roles,
        "input_materials": input_materials,
        "role_input_materials": role_input_materials,
        "order_intent_events": order_intents,
        "paper_trades": linked_trades,
        "links": {
            "research_snapshot": f"/dashboard?symbol={decision['symbol']}&interval=1h&as_of_time={decision['timestamp'] or ''}",
            "decision_center": f"/decisions?symbol={decision['symbol']}",
            "backtest": f"/backtest?backtest_id={linked_backtest_id}" if linked_backtest_id else None,
            "replay": f"/replay?session_id={linked_replay_session_id}" if linked_replay_session_id else None,
            "analytics": analytics_url,
            "audit_export": order_intents[-1]["export_url"] if order_intents else None,
        },
    }
