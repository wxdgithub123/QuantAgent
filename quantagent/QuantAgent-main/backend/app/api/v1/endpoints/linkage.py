"""Workbench linkage contract for research, backtest, replay, and audit desks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.models.instrument import Instrument
from app.services.database import get_db

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _clean_symbol(symbol: Optional[str]) -> Optional[str]:
    if not symbol:
        return None
    return Instrument.from_raw(symbol).symbol


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _row_dict(row: Any) -> Dict[str, Any]:
    if not row:
        return {}
    if isinstance(row, dict):
        return dict(row)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return dict(mapping)
    try:
        return dict(row)
    except Exception:
        return {}


def _with_query(path: str, **params: Any) -> str:
    filtered = {key: _iso(value) for key, value in params.items() if value not in (None, "")}
    return f"{path}?{urlencode(filtered)}" if filtered else path


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _visible_check(records: List[Any], *, as_of_time: Optional[str], label: str) -> Dict[str, Any]:
    as_of_dt = _parse_dt(as_of_time)
    checked = 0
    violations: List[Dict[str, Any]] = []
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            continue
        visible_time = _first_present(
            item.get("available_time"),
            item.get("availableTime"),
            item.get("ingest_time"),
            item.get("ts"),
            item.get("timestamp"),
            item.get("event_time"),
            item.get("published_at"),
        )
        visible_dt = _parse_dt(visible_time)
        if not visible_dt or not as_of_dt:
            continue
        checked += 1
        if visible_dt > as_of_dt:
            violations.append(
                {
                    "index": index,
                    "visible_time": _iso(visible_dt),
                    "as_of_time": as_of_time,
                    "record_id": _first_present(item.get("id"), item.get("record_id"), item.get("snapshot_id")),
                }
            )
    return {
        "dataset": label,
        "rule": "available_time <= as_of_time",
        "count": len(records),
        "checked_count": checked,
        "passed": None if checked == 0 else len(violations) == 0,
        "violations": violations[:20],
    }


def _response(data: Any, *, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "schema_version": "workbench_linkage_response.v1",
            "generated_at": _now_iso(),
            **(meta or {}),
        },
        "errors": [],
    }


def build_workbench_linkage(
    *,
    symbol: Optional[str] = None,
    interval: str = "1h",
    as_of_time: Optional[datetime] = None,
    decision_id: Optional[str] = None,
    audit_id: Optional[str] = None,
    backtest_id: Optional[str] = None,
    replay_session_id: Optional[str] = None,
    order_intent_id: Optional[str] = None,
    order_id: Optional[str] = None,
    context_hash: Optional[str] = None,
    source: str = "workbench",
) -> Dict[str, Any]:
    canonical_symbol = _clean_symbol(symbol) or "BTCUSDT"
    as_of_value = _iso(as_of_time)

    common = {
        "symbol": canonical_symbol,
        "interval": interval,
        "as_of_time": as_of_value,
    }
    audit_filters = {
        "symbol": canonical_symbol if symbol else None,
        "decision_id": decision_id,
        "audit_id": audit_id,
        "backtest_id": backtest_id,
        "replay_session_id": replay_session_id,
        "order_intent_id": order_intent_id,
        "order_id": order_id,
    }
    replay_params = {
        "session_id": replay_session_id,
        "as_of_time": as_of_value,
        "event_time": as_of_value,
        "source": source,
    }
    links = {
        "research": _with_query("/dashboard", **common),
        "research_snapshot_api": _with_query(f"/api/v1/market/research-snapshot/{canonical_symbol}", interval=interval, as_of_time=as_of_value),
        "bars_as_of_api": _with_query("/api/v1/bars/as-of", symbol=canonical_symbol, interval=interval, as_of_time=as_of_value, limit=120),
        "snapshot_api": _with_query("/api/v1/snapshot", symbol=canonical_symbol, interval=interval, as_of_time=as_of_value),
        "replay_package_api": _with_query("/api/v1/linkage/replay-package", symbol=canonical_symbol if symbol else None, interval=interval, as_of_time=as_of_value, decision_id=decision_id, audit_id=audit_id, backtest_id=backtest_id, replay_session_id=replay_session_id, order_intent_id=order_intent_id, order_id=order_id, context_hash=context_hash),
        "backtest": _with_query("/backtest", backtest_id=backtest_id, symbol=canonical_symbol if symbol else None, interval=interval, as_of_time=as_of_value),
        "replay": _with_query("/replay", **replay_params),
        "audit": _with_query("/audit", **audit_filters),
        "audit_export_api": _with_query(f"/api/v1/audit/records/{audit_id}/export") if audit_id else None,
        "decisions": _with_query("/decisions", symbol=canonical_symbol if symbol else None, as_of_time=as_of_value),
        "analytics": _with_query("/analytics", backtest_id=backtest_id, replay_session_id=replay_session_id),
    }
    links = {key: value for key, value in links.items() if value}

    return {
        "identity": {
            "symbol": canonical_symbol,
            "interval": interval,
            "as_of_time": as_of_value,
            "decision_id": decision_id,
            "audit_id": audit_id,
            "backtest_id": backtest_id,
            "replay_session_id": replay_session_id,
            "order_intent_id": order_intent_id,
            "order_id": order_id,
            "context_hash": context_hash,
            "source": source,
        },
        "pit": {
            "rule": "available_time <= as_of_time",
            "bar_rule": "COALESCE(available_time, event_time) <= as_of_time",
            "agent_input_policy": "local_storage_only",
            "external_fallback_allowed": False,
            "as_of_time": as_of_value,
        },
        "links": links,
        "filters": {
            "audit": audit_filters,
            "replay": replay_params,
            "backtest": {"backtest_id": backtest_id, "symbol": canonical_symbol, "interval": interval, "as_of_time": as_of_value},
            "research": common,
        },
        "replayability": {
            "requires_snapshot_ids": True,
            "context_hash": context_hash,
            "snapshot_api": links["snapshot_api"],
            "replay_package_api": links.get("replay_package_api"),
            "audit_export_api": links.get("audit_export_api"),
        },
    }


def _extract_snapshot(audit_record: Dict[str, Any]) -> Dict[str, Any]:
    details = _safe_dict(audit_record.get("details"))
    candidates = [
        details.get("normalizedSnapshot"),
        _safe_dict(details.get("inputSummary")).get("normalizedSnapshot"),
        _safe_dict(details.get("input_materials")).get("normalizedSnapshot"),
        _safe_dict(details.get("decision_evidence")).get("normalized_snapshot"),
        _safe_dict(details.get("decision")).get("normalizedSnapshot"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _decision_from_row(decision_row: Dict[str, Any], audit_record: Dict[str, Any]) -> Dict[str, Any]:
    details = _safe_dict(audit_record.get("details"))
    decision = _safe_dict(details.get("decision"))
    return {
        "decision_id": _first_present(decision_row.get("id"), audit_record.get("decision_id"), details.get("decisionId"), decision.get("id")),
        "symbol": _first_present(decision_row.get("symbol"), audit_record.get("symbol"), details.get("symbol"), decision.get("symbol")),
        "action": _first_present(decision_row.get("final_signal"), decision.get("final_signal"), details.get("action")),
        "confidence": _first_present(decision_row.get("confidence"), decision.get("confidence"), details.get("confidence")),
        "summary": _first_present(decision_row.get("summary"), decision.get("summary"), details.get("summary")),
        "risk_veto": _first_present(decision_row.get("risk_veto"), decision.get("risk_veto")),
        "created_at": _iso(_first_present(decision_row.get("created_at"), audit_record.get("created_at"))),
        "as_of_time": _iso(_first_present(decision_row.get("timestamp"), details.get("asOfTime"))),
        "available_time": _iso(_first_present(decision_row.get("available_time"), details.get("availableTime"))),
        "context_id": _first_present(decision_row.get("context_id"), audit_record.get("context_id"), details.get("contextId")),
        "context_hash": _first_present(decision_row.get("context_hash"), audit_record.get("context_hash"), details.get("contextHash"), decision.get("context_hash")),
        "model_version": _first_present(decision_row.get("model_version"), details.get("modelVersion")),
        "prompt_version": _first_present(decision_row.get("prompt_version"), details.get("promptVersion")),
    }


def _event_from_audit(row: Dict[str, Any]) -> Dict[str, Any]:
    details = _safe_dict(row.get("details"))
    return {
        "audit_id": row.get("id"),
        "event_type": _first_present(row.get("event_type"), details.get("eventType"), row.get("action")),
        "action": row.get("action"),
        "created_at": _iso(row.get("created_at")),
        "payload_hash": row.get("payload_hash"),
        "prev_hash": row.get("prev_hash"),
        "immutable": row.get("immutable", True),
        "risk_status": row.get("risk_status"),
        "execution_status": row.get("execution_status"),
        "order_intent_id": _first_present(row.get("order_intent_id"), details.get("orderIntentId")),
        "order_id": _first_present(row.get("order_id"), details.get("orderId"), _safe_dict(details.get("executionResult")).get("orderId")),
        "details": details,
    }


def build_replay_package(
    *,
    symbol: Optional[str] = None,
    interval: str = "1h",
    as_of_time: Optional[datetime] = None,
    decision_row: Optional[Dict[str, Any]] = None,
    audit_record: Optional[Dict[str, Any]] = None,
    audit_events: Optional[List[Dict[str, Any]]] = None,
    backtest_id: Optional[str] = None,
    replay_session_id: Optional[str] = None,
    order_intent_id: Optional[str] = None,
    order_id: Optional[str] = None,
    context_hash: Optional[str] = None,
    source: str = "workbench_replay_package",
) -> Dict[str, Any]:
    audit_record = audit_record or {}
    audit_events = audit_events or ([] if not audit_record else [audit_record])
    decision_row = decision_row or {}
    snapshot = _extract_snapshot(audit_record)
    details = _safe_dict(audit_record.get("details"))
    decision = _decision_from_row(decision_row, audit_record)

    canonical_symbol = _clean_symbol(
        _first_present(symbol, decision.get("symbol"), snapshot.get("symbol"), audit_record.get("symbol"))
    ) or "BTCUSDT"
    active_interval = str(
        _first_present(interval, snapshot.get("interval"), snapshot.get("timeframe"), snapshot.get("time_frame"), "1h")
    )
    active_as_of = _first_present(
        _iso(as_of_time),
        snapshot.get("as_of_time"),
        decision.get("as_of_time"),
        details.get("asOfTime"),
    )
    active_context_hash = _first_present(context_hash, decision.get("context_hash"), snapshot.get("context_hash"))
    decision_id = _first_present(decision.get("decision_id"), details.get("decisionId"))
    audit_id = audit_record.get("id")
    snapshot_ids = _safe_dict(
        _first_present(
            snapshot.get("input_snapshot_ids"),
            snapshot.get("snapshot_ids"),
            details.get("snapshotId"),
            decision_row.get("input_snapshot_ids"),
        )
    )
    bars = _safe_list(snapshot.get("bars"))
    factors = _safe_dict(_first_present(snapshot.get("latest_factors"), snapshot.get("factorSnapshot")))
    signals = _safe_list(_first_present(snapshot.get("recent_signals"), snapshot.get("signalEvents")))
    news = _safe_list(_first_present(snapshot.get("news_events"), snapshot.get("newsEvents")))
    macro = _safe_list(_first_present(snapshot.get("macro_events"), snapshot.get("macroEvents")))
    role_outputs = _safe_list(
        _first_present(
            details.get("agentOutputs"),
            details.get("role_outputs"),
            decision_row.get("role_opinions"),
            decision_row.get("agent_signals"),
        )
    )
    events = [_event_from_audit(row) for row in audit_events]
    latest_risk = next(
        (
            _safe_dict(event["details"].get("riskCheckResult") or event["details"].get("risk_preview"))
            for event in reversed(events)
            if event.get("event_type") in {"RISK_CHECK_PASSED", "RISK_BLOCKED", "RISK_CHECK_UNAVAILABLE"}
            or event["details"].get("riskCheckResult")
            or event["details"].get("risk_preview")
        ),
        {},
    )
    latest_execution = next(
        (
            _safe_dict(event["details"].get("executionResult") or event["details"].get("execution"))
            for event in reversed(events)
            if event.get("event_type") in {"PAPER_ORDER_FILLED", "PAPER_ORDER_REJECTED"}
            or event["details"].get("executionResult")
            or event["details"].get("execution")
        ),
        {},
    )
    latest_intent = next(
        (
            _safe_dict(event["details"].get("intent"))
            for event in reversed(events)
            if event["details"].get("intent") or event.get("event_type") == "ORDER_INTENT_CREATED"
        ),
        {},
    )
    strict_snapshot_replay = bool(snapshot)
    missing: List[str] = []
    if not snapshot:
        missing.append("normalizedSnapshot")
    if not snapshot_ids:
        missing.append("input_snapshot_ids")
    if not active_context_hash:
        missing.append("context_hash")
    if not role_outputs:
        missing.append("agent_role_outputs")

    linkage = build_workbench_linkage(
        symbol=canonical_symbol,
        interval=active_interval,
        as_of_time=_parse_dt(active_as_of),
        decision_id=str(decision_id) if decision_id is not None else None,
        audit_id=str(audit_id) if audit_id is not None else None,
        backtest_id=str(backtest_id) if backtest_id is not None else None,
        replay_session_id=replay_session_id,
        order_intent_id=order_intent_id or latest_intent.get("id") or latest_intent.get("intent_id"),
        order_id=order_id or latest_execution.get("orderId") or latest_execution.get("order_id"),
        context_hash=active_context_hash,
        source=source,
    )
    data_record_ids_required = ["bars", "factors", "signals", "news", "macro"]
    visible_data_checks = [
        _visible_check(bars, as_of_time=active_as_of, label="bars"),
        _visible_check(list(factors.values()), as_of_time=active_as_of, label="factors"),
        _visible_check(signals, as_of_time=active_as_of, label="signals"),
        _visible_check(news, as_of_time=active_as_of, label="news"),
        _visible_check(macro, as_of_time=active_as_of, label="macro"),
    ]

    return {
        "identity": {
            "package_id": f"rpkg:{decision_id or audit_id or canonical_symbol}:{active_context_hash or 'pit-rebuild'}",
            "symbol": canonical_symbol,
            "interval": active_interval,
            "as_of_time": active_as_of,
            "decision_id": decision_id,
            "audit_id": audit_id,
            "backtest_id": backtest_id,
            "replay_session_id": replay_session_id,
            "context_hash": active_context_hash,
            "source": source,
        },
        "pit": {
            "rule": "available_time <= as_of_time",
            "agent_input_policy": "local_storage_only",
            "external_fallback_allowed": False,
            "strict_snapshot_replay": strict_snapshot_replay,
            "replay_method": "strict_snapshot_replay" if strict_snapshot_replay else "pit_rebuild_from_local_storage",
            "visible_data_checks": visible_data_checks,
        },
        "agent_input_package": {
            "schema_version": "agent_replay_input_package.v1",
            "source": "audit_logs.normalizedSnapshot" if strict_snapshot_replay else "AnalysisContextBuilder.PIT",
            "record_ids": snapshot_ids,
            "data_record_ids_required": data_record_ids_required,
            "data_versions": _safe_dict(snapshot.get("data_versions")),
            "counts": {
                "bars": len(bars),
                "factors": len(factors),
                "signals": len(signals),
                "news": len(news),
                "macro": len(macro),
            },
            "normalized_snapshot": snapshot or None,
        },
        "decision": decision,
        "agent_outputs": role_outputs,
        "execution_chain": {
            "events": events,
            "order_intent": latest_intent or None,
            "risk_guard": latest_risk or None,
            "execution_result": latest_execution or None,
            "immutable_event_count": len([event for event in events if event.get("immutable") is not False]),
        },
        "replayability": {
            "strict_snapshot_replay_available": strict_snapshot_replay,
            "requires_snapshot_ids": True,
            "missing_for_strict_replay": missing,
            "context_hash": active_context_hash,
            "can_replay_without_external_source": True,
            "audit_is_append_only": True,
        },
        "replay_plan": [
            {"step": "load_agent_input_package", "status": "ready" if strict_snapshot_replay else "pit_rebuild_required"},
            {"step": "verify_point_in_time", "rule": "available_time <= as_of_time", "status": "ready"},
            {"step": "run_agent_local_only", "policy": "local_storage_only", "status": "ready" if decision_id else "needs_decision_id"},
            {"step": "compare_context_hash", "context_hash": active_context_hash, "status": "ready" if active_context_hash else "missing"},
            {"step": "append_audit_record", "policy": "immutable_append_only", "status": "ready"},
        ],
        "links": linkage["links"],
        "filters": linkage["filters"],
    }


@router.get("/context")
async def get_linkage_context(
    symbol: Optional[str] = Query(None),
    interval: str = Query("1h"),
    as_of_time: Optional[datetime] = Query(None),
    decision_id: Optional[str] = Query(None),
    audit_id: Optional[str] = Query(None),
    backtest_id: Optional[str] = Query(None),
    replay_session_id: Optional[str] = Query(None),
    order_intent_id: Optional[str] = Query(None),
    order_id: Optional[str] = Query(None),
    context_hash: Optional[str] = Query(None),
    source: str = Query("workbench"),
) -> Dict[str, Any]:
    data = build_workbench_linkage(
        symbol=symbol,
        interval=interval,
        as_of_time=as_of_time,
        decision_id=decision_id,
        audit_id=audit_id,
        backtest_id=backtest_id,
        replay_session_id=replay_session_id,
        order_intent_id=order_intent_id,
        order_id=order_id,
        context_hash=context_hash,
        source=source,
    )
    return _response(data, meta={"source": source, "pit_rule": "available_time <= as_of_time"})


async def _fetch_audit_record(
    *,
    audit_id: Optional[str],
    decision_id: Optional[str],
    context_hash: Optional[str],
) -> Dict[str, Any]:
    clauses: List[str] = []
    params: Dict[str, Any] = {}
    if audit_id:
        clauses.append("id = :audit_id")
        params["audit_id"] = int(audit_id)
    if decision_id:
        clauses.append(
            """
            (
              decision_id = :decision_id
              OR source_decision_id = :decision_id
              OR replay_decision_id = :decision_id
              OR details->>'decisionId' = :decision_id_text
              OR details->'decision'->>'id' = :decision_id_text
            )
            """
        )
        params["decision_id"] = int(decision_id)
        params["decision_id_text"] = str(decision_id)
    if context_hash:
        clauses.append("(context_hash = :context_hash OR details->>'contextHash' = :context_hash OR details->'decision'->>'context_hash' = :context_hash)")
        params["context_hash"] = context_hash
    if not clauses:
        return {}
    where_sql = " OR ".join(f"({clause})" for clause in clauses)
    async with get_db() as session:
        row = (
            await session.execute(
                text(
                    f"""
                    SELECT id, action, user_id, resource, details, ip_address, created_at,
                           event_type, symbol, decision_id, source_decision_id, replay_decision_id,
                           order_intent_id, order_id, context_id, context_hash, risk_status,
                           execution_status, backtest_id, replay_session_id, execution_mode,
                           payload_hash, prev_hash, immutable
                    FROM audit_logs
                    WHERE {where_sql}
                    ORDER BY
                      CASE WHEN event_type = 'AGENT_DECISION' OR action = 'AGENT_DECISION' THEN 0 ELSE 1 END,
                      created_at DESC,
                      id DESC
                    LIMIT 1
                    """
                ),
                params,
            )
        ).mappings().first()
    return _row_dict(row)


async def _fetch_decision_row(decision_id: Optional[str], context_hash: Optional[str]) -> Dict[str, Any]:
    clauses: List[str] = []
    params: Dict[str, Any] = {}
    if decision_id:
        clauses.append("id = :decision_id")
        params["decision_id"] = int(decision_id)
    if context_hash:
        clauses.append("context_hash = :context_hash")
        params["context_hash"] = context_hash
    if not clauses:
        return {}
    async with get_db() as session:
        row = (
            await session.execute(
                text(
                    f"""
                    SELECT id, symbol, timestamp, final_signal, confidence, risk_veto,
                           summary, input_snapshot_ids, role_opinions, agent_signals,
                           position_advice, risk_notes, created_at,
                           context_id, context_hash, available_time,
                           model_version, prompt_version
                    FROM coordination_history
                    WHERE {" OR ".join(f"({clause})" for clause in clauses)}
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1
                    """
                ),
                params,
            )
        ).mappings().first()
    return _row_dict(row)


async def _fetch_audit_chain(
    *,
    audit_record: Dict[str, Any],
    decision_id: Optional[str],
    context_hash: Optional[str],
    backtest_id: Optional[str],
    replay_session_id: Optional[str],
    order_intent_id: Optional[str],
    order_id: Optional[str],
) -> List[Dict[str, Any]]:
    details = _safe_dict(audit_record.get("details"))
    active_decision_id = _first_present(
        decision_id,
        audit_record.get("decision_id"),
        audit_record.get("source_decision_id"),
        audit_record.get("replay_decision_id"),
        details.get("decisionId"),
        _safe_dict(details.get("decision")).get("id"),
    )
    active_context_hash = _first_present(context_hash, audit_record.get("context_hash"), details.get("contextHash"))
    active_backtest_id = _first_present(backtest_id, audit_record.get("backtest_id"), details.get("backtestId"), details.get("backtest_id"))
    active_replay_session_id = _first_present(replay_session_id, audit_record.get("replay_session_id"), details.get("replaySessionId"), details.get("replay_session_id"))
    active_order_intent_id = _first_present(order_intent_id, audit_record.get("order_intent_id"), details.get("orderIntentId"))
    active_order_id = _first_present(order_id, audit_record.get("order_id"), details.get("orderId"))

    where: List[str] = []
    params: Dict[str, Any] = {"limit": 100}
    if active_decision_id:
        where.append(
            """
            (
              decision_id = :decision_id
              OR source_decision_id = :decision_id
              OR replay_decision_id = :decision_id
              OR details->>'decisionId' = :decision_id_text
              OR details->>'sourceDecisionId' = :decision_id_text
              OR details->>'replayDecisionId' = :decision_id_text
              OR details->'decision'->>'id' = :decision_id_text
              OR details->'intent'->>'sourceDecisionId' = :decision_id_text
            )
            """
        )
        params["decision_id"] = int(active_decision_id)
        params["decision_id_text"] = str(active_decision_id)
    if active_context_hash:
        where.append("(context_hash = :context_hash OR details->>'contextHash' = :context_hash OR details->'decision'->>'context_hash' = :context_hash)")
        params["context_hash"] = str(active_context_hash)
    if active_backtest_id:
        where.append("(backtest_id = :backtest_id OR details->>'backtestId' = :backtest_id_text OR details->>'backtest_id' = :backtest_id_text)")
        params["backtest_id"] = int(active_backtest_id)
        params["backtest_id_text"] = str(active_backtest_id)
    if active_replay_session_id:
        where.append("(replay_session_id = :replay_session_id OR details->>'replaySessionId' = :replay_session_id OR details->>'replay_session_id' = :replay_session_id)")
        params["replay_session_id"] = str(active_replay_session_id)
    if active_order_intent_id:
        where.append("(order_intent_id = :order_intent_id OR details->>'orderIntentId' = :order_intent_id OR details->'intent'->>'id' = :order_intent_id)")
        params["order_intent_id"] = str(active_order_intent_id)
    if active_order_id:
        where.append("(order_id = :order_id OR details->>'orderId' = :order_id OR details->'executionResult'->>'orderId' = :order_id)")
        params["order_id"] = str(active_order_id)
    if audit_record.get("id"):
        where.append("id = :audit_id")
        params["audit_id"] = int(audit_record["id"])
    if not where:
        return [] if not audit_record else [audit_record]
    async with get_db() as session:
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT id, action, user_id, resource, details, ip_address, created_at,
                           event_type, symbol, decision_id, source_decision_id, replay_decision_id,
                           order_intent_id, order_id, context_id, context_hash, risk_status,
                           execution_status, backtest_id, replay_session_id, execution_mode,
                           payload_hash, prev_hash, immutable
                    FROM audit_logs
                    WHERE {" OR ".join(f"({clause})" for clause in where)}
                    ORDER BY created_at ASC, id ASC
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).mappings().all()
    rows_dict = [_row_dict(row) for row in rows]
    if audit_record and audit_record.get("id") not in {row.get("id") for row in rows_dict}:
        rows_dict.insert(0, audit_record)
    return rows_dict


@router.get("/replay-package")
async def get_replay_package(
    symbol: Optional[str] = Query(None),
    interval: str = Query("1h"),
    as_of_time: Optional[datetime] = Query(None),
    decision_id: Optional[str] = Query(None),
    audit_id: Optional[str] = Query(None),
    backtest_id: Optional[str] = Query(None),
    replay_session_id: Optional[str] = Query(None),
    order_intent_id: Optional[str] = Query(None),
    order_id: Optional[str] = Query(None),
    context_hash: Optional[str] = Query(None),
    source: str = Query("workbench_replay_package"),
) -> Dict[str, Any]:
    """Return the immutable/PIT replay package for one workbench context."""
    audit_record = await _fetch_audit_record(audit_id=audit_id, decision_id=decision_id, context_hash=context_hash)
    active_decision_id = _first_present(decision_id, audit_record.get("decision_id"), _safe_dict(audit_record.get("details")).get("decisionId"))
    active_context_hash = _first_present(context_hash, audit_record.get("context_hash"), _safe_dict(audit_record.get("details")).get("contextHash"))
    decision_row = await _fetch_decision_row(str(active_decision_id) if active_decision_id else None, str(active_context_hash) if active_context_hash else None)
    if not audit_record and not decision_row:
        if not any([symbol, as_of_time, context_hash]):
            raise HTTPException(status_code=404, detail="No audit or decision context found for replay package")
        data = build_replay_package(
            symbol=symbol,
            interval=interval,
            as_of_time=as_of_time,
            backtest_id=backtest_id,
            replay_session_id=replay_session_id,
            order_intent_id=order_intent_id,
            order_id=order_id,
            context_hash=context_hash,
            source=source,
        )
        return _response(data, meta={"source": source, "fallback": "pit_rebuild_only"})

    chain = await _fetch_audit_chain(
        audit_record=audit_record,
        decision_id=str(active_decision_id) if active_decision_id else None,
        context_hash=str(active_context_hash) if active_context_hash else None,
        backtest_id=backtest_id,
        replay_session_id=replay_session_id,
        order_intent_id=order_intent_id,
        order_id=order_id,
    )
    data = build_replay_package(
        symbol=symbol,
        interval=interval,
        as_of_time=as_of_time,
        decision_row=decision_row,
        audit_record=audit_record,
        audit_events=chain,
        backtest_id=backtest_id,
        replay_session_id=replay_session_id,
        order_intent_id=order_intent_id,
        order_id=order_id,
        context_hash=context_hash,
        source=source,
    )
    return _response(data, meta={"source": source, "pit_rule": "available_time <= as_of_time"})
