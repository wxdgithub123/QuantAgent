"""Phase 2 paper-trading workbench aggregation.

The workbench is a read model over existing execution services. It does not
place orders by itself; writes still go through OrderIntentService,
RiskManager, PaperTradingService, and immutable audit records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.database import get_db

logger = logging.getLogger(__name__)

PAPER_TRADING_WORKBENCH_SCHEMA_VERSION = "paper_trading_workbench.v1"

ORDER_INTENT_ACTIONS = {
    "ORDER_INTENT_CREATED",
    "HOLD_RECORDED",
    "RISK_CHECK_PASSED",
    "RISK_BLOCKED",
    "ORDER_INTENT_EXECUTION_LINKED",
    "PAPER_ORDER_FILLED",
    "PAPER_ORDER_REJECTED",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _nested(record: Dict[str, Any], *keys: str) -> Any:
    current: Any = record
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _stage_for_action(action: str) -> str:
    mapping = {
        "ORDER_INTENT_CREATED": "created",
        "HOLD_RECORDED": "no_action",
        "RISK_CHECK_PASSED": "risk_checked",
        "RISK_BLOCKED": "blocked",
        "ORDER_INTENT_EXECUTION_LINKED": "execution_linked",
        "PAPER_ORDER_FILLED": "filled",
        "PAPER_ORDER_REJECTED": "rejected",
    }
    return mapping.get(action, "audit")


def _status_for_event(action: str, details: Dict[str, Any], intent: Dict[str, Any], execution: Dict[str, Any]) -> str:
    """Prefer lifecycle event status over stale draft intent status."""
    if action == "RISK_BLOCKED":
        return "BLOCKED"
    if action == "RISK_CHECK_PASSED":
        return "RISK_CHECKED"
    if action == "PAPER_ORDER_REJECTED":
        return "REJECTED"
    if action == "ORDER_INTENT_CREATED":
        return str(_first_present(details.get("status"), intent.get("status"), "CREATED"))
    if action == "HOLD_RECORDED":
        return str(_first_present(details.get("status"), intent.get("status"), "NO_ACTION"))
    return str(_first_present(execution.get("status"), details.get("status"), intent.get("status"), action) or action)


def summarize_order_intent_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one audit event into the paper-workbench row contract."""
    details = _as_dict(event.get("details"))
    intent = _as_dict(_first_present(details.get("intent"), details.get("internal_intent")))
    risk = _as_dict(_first_present(details.get("riskCheckResult"), details.get("risk_preview"), details.get("riskPreview")))
    execution = _as_dict(_first_present(details.get("executionResult"), details.get("execution")))
    decision = _as_dict(details.get("decision"))
    action = str(event.get("action") or "")
    order_intent_id = _first_present(
        event.get("order_intent_id"),
        details.get("orderIntentId"),
        details.get("order_intent_id"),
        intent.get("id"),
        intent.get("intent_id"),
        _nested(details, "internal_intent", "intent_id"),
    )
    decision_id = _first_present(
        event.get("decision_id"),
        details.get("decisionId"),
        details.get("sourceDecisionId"),
        intent.get("sourceDecisionId"),
        intent.get("decision_id"),
        decision.get("id"),
        _nested(details, "internal_intent", "decision_id"),
    )
    order_id = _first_present(
        event.get("order_id"),
        details.get("orderId"),
        details.get("order_id"),
        execution.get("orderId"),
        execution.get("order_id"),
    )
    symbol = str(_first_present(event.get("symbol"), event.get("resource"), details.get("symbol"), intent.get("symbol")) or "").upper()
    status = _status_for_event(action, details, intent, execution)
    return {
        "audit_id": event.get("id"),
        "action": action,
        "stage": _stage_for_action(action),
        "symbol": symbol,
        "status": status,
        "created_at": _iso(event.get("created_at")),
        "orderIntentId": order_intent_id,
        "decisionId": decision_id,
        "orderId": order_id,
        "dedupeKey": _dedupe_key(action, order_intent_id, order_id),
        "side": _first_present(intent.get("side"), intent.get("action"), details.get("action")),
        "positionRatio": _first_present(intent.get("positionRatio"), intent.get("position_pct")),
        "risk": {
            "passed": _first_present(risk.get("passed"), risk.get("allowed")),
            "rule": risk.get("rule"),
            "reason": _first_present(risk.get("reason"), risk.get("blockedReason"), risk.get("blocked_reason")),
            "checkedRules": _first_present(risk.get("checkedRules"), risk.get("checked_rules"), []),
        },
        "execution": {
            "orderId": order_id,
            "status": execution.get("status"),
            "fillPrice": _first_present(execution.get("fillPrice"), execution.get("price")),
            "quantity": execution.get("quantity"),
            "fee": execution.get("fee"),
            "pnl": _first_present(execution.get("pnl"), execution.get("realizedPnl")),
        },
        "links": {
            "audit": f"/audit?audit_id={event.get('id')}" if event.get("id") else "/audit",
            "decision": f"/audit?decision_id={decision_id}" if decision_id else "/decisions",
            "order_intent": f"/audit?order_intent_id={order_intent_id}" if order_intent_id else "/audit",
        },
    }


def _dedupe_key(action: str, order_intent_id: Any, order_id: Any) -> str:
    if action in {"PAPER_ORDER_FILLED", "PAPER_ORDER_REJECTED", "ORDER_INTENT_EXECUTION_LINKED"}:
        if order_intent_id or order_id:
            return f"{action}:{order_intent_id or '-'}:{order_id or '-'}"
    return f"{action}:{order_intent_id or '-'}:{order_id or '-'}"


def dedupe_order_intent_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse duplicate immutable audit rows for the same lifecycle stage.

    Audit rows remain append-only. This read model prevents a wrapper event and
    a PaperTradingService fill row from making one order look like two fills.
    """
    seen: set[str] = set()
    unique: List[Dict[str, Any]] = []
    for event in events:
        key = str(event.get("dedupeKey") or _dedupe_key(str(event.get("action") or ""), event.get("orderIntentId"), event.get("orderId")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def build_execution_chain(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    unique_events = dedupe_order_intent_events(events)
    counts = {
        "created": 0,
        "no_action": 0,
        "risk_checked": 0,
        "execution_linked": 0,
        "blocked": 0,
        "filled": 0,
        "rejected": 0,
        "audit_events": len(unique_events),
        "raw_audit_events": len(events),
        "deduped_audit_events": max(len(events) - len(unique_events), 0),
    }
    for event in unique_events:
        stage = str(event.get("stage") or _stage_for_action(str(event.get("action") or "")))
        if stage in counts:
            counts[stage] += 1
    stages = [
        {"key": "created", "label": "创建", "count": counts["created"] + counts["no_action"]},
        {"key": "risk_checked", "label": "风控检查", "count": counts["risk_checked"] + counts["blocked"]},
        {"key": "filled_or_rejected", "label": "成交/拒绝", "count": counts["filled"] + counts["rejected"] + counts["blocked"]},
        {"key": "pnl", "label": "PnL", "count": counts["filled"]},
        {"key": "audit", "label": "审计", "count": counts["audit_events"]},
    ]
    return {
        "schema_version": "paper_execution_chain.v1",
        "chain": ["OrderIntent", "RiskGuard", "PaperOrder", "PnL", "AuditRecord"],
        "stages": stages,
        "counts": counts,
        "closed_loop_ready": counts["audit_events"] > 0 and (counts["filled"] + counts["blocked"] + counts["no_action"] > 0),
        "dedupe_rule": "action + orderIntentId + orderId",
        "audit_export_api": "/api/v1/audit/records/{audit_id}/export",
    }


def build_account_summary(balance: Dict[str, Any], positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    available = _safe_float(balance.get("available_balance"), _safe_float(balance.get("total_balance")))
    cash_total = _safe_float(balance.get("total_balance"), available)
    position_value = 0.0
    unrealized_pnl = 0.0
    for position in positions:
        qty = abs(_safe_float(_first_present(position.get("quantity"), position.get("qty"))))
        price = _safe_float(_first_present(position.get("mark_price"), position.get("markPrice"), position.get("avg_price"), position.get("avgEntryPrice")))
        position_value += qty * price
        unrealized_pnl += _safe_float(_first_present(position.get("pnl"), position.get("unrealizedPnl")))
    return {
        "available_balance": round(available, 8),
        "cash_balance": round(cash_total, 8),
        "position_value": round(position_value, 8),
        "total_equity": round(available + position_value, 8),
        "open_positions": len(positions),
        "unrealized_pnl": round(unrealized_pnl, 8),
    }


def _orders_summary(orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    realized_pnl = sum(_safe_float(_first_present(order.get("pnl"), order.get("realizedPnl"))) for order in orders)
    fees = sum(_safe_float(order.get("fee")) for order in orders)
    slippage = sum(abs(_safe_float(order.get("slippage"))) for order in orders)
    return {
        "order_count": len(orders),
        "realized_pnl": round(realized_pnl, 8),
        "total_fee": round(fees, 8),
        "total_abs_slippage": round(slippage, 8),
    }


def _section_error(name: str, exc: Exception) -> Dict[str, Any]:
    logger.debug("Paper trading workbench section %s unavailable: %s", name, exc)
    return {
        "status": "unavailable",
        "degraded": True,
        "error": str(exc)[:240],
    }


async def _collect_order_intent_events(symbol: Optional[str], limit: int) -> Dict[str, Any]:
    action_sql = ", ".join(f"'{action}'" for action in sorted(ORDER_INTENT_ACTIONS))
    where = """
    (
      action IN (__ORDER_INTENT_ACTIONS__)
      OR details->>'orderIntentId' IS NOT NULL
      OR details->'intent'->>'intent_id' IS NOT NULL
      OR details->'intent'->>'id' IS NOT NULL
    )
    """.replace("__ORDER_INTENT_ACTIONS__", action_sql)
    query_limit = max(limit * 3, limit)
    params: Dict[str, Any] = {"limit": query_limit}
    if symbol:
        where += " AND (resource = :symbol OR symbol = :symbol OR details->>'symbol' = :symbol)"
        params["symbol"] = symbol.upper()
    async with get_db() as session:
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT
                        id,
                        action,
                        resource,
                        symbol,
                        order_intent_id,
                        order_id,
                        decision_id,
                        details,
                        created_at
                    FROM audit_logs
                    WHERE {where}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).mappings().all()
    raw_items = [summarize_order_intent_event(dict(row)) for row in rows]
    items = dedupe_order_intent_events(raw_items)[:limit]
    return {
        "status": "ready",
        "items": items,
        "total": len(items),
        "raw_total": len(raw_items),
        "deduped_total": max(len(raw_items) - len(items), 0),
        "dedupe_rule": "action + orderIntentId + orderId",
        "source": "immutable audit_logs",
    }


async def _collect_equity_curve(limit: int) -> Dict[str, Any]:
    async with get_db() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT timestamp, total_equity, cash_balance, position_value, daily_pnl, drawdown
                    FROM equity_snapshots
                    WHERE session_id IS NULL AND data_source = 'PAPER'
                    ORDER BY timestamp DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).mappings().all()
    points = [
        {
            "t": _iso(row.get("timestamp")),
            "v": _safe_float(row.get("total_equity")),
            "cash": _safe_float(row.get("cash_balance")),
            "position_value": _safe_float(row.get("position_value")),
            "daily_pnl": _safe_float(row.get("daily_pnl")),
            "drawdown": _safe_float(row.get("drawdown")),
        }
        for row in reversed(rows)
    ]
    return {"status": "ready", "points": points, "source": "equity_snapshots", "total": len(points)}


async def build_paper_trading_workbench(
    *,
    symbol: Optional[str] = None,
    exchange_id: str = "okx",
    limit: int = 25,
) -> Dict[str, Any]:
    from app.services.paper_trading_service import paper_trading_service
    from app.services.risk_manager import risk_manager

    errors: List[Dict[str, Any]] = []
    balance: Dict[str, Any] = {}
    positions: List[Dict[str, Any]] = []
    orders: List[Dict[str, Any]] = []

    try:
        balance = await paper_trading_service.get_balance()
        account_section = {"status": "ready", "balance": balance}
    except Exception as exc:
        account_section = _section_error("account", exc)
        errors.append({"section": "account", "message": account_section["error"]})

    try:
        positions = await paper_trading_service.get_positions(exchange_id=exchange_id)
        if symbol:
            positions = [item for item in positions if str(item.get("symbol", "")).upper() == symbol.upper()]
        positions_section = {"status": "ready", "items": positions, "total": len(positions)}
    except Exception as exc:
        positions_section = _section_error("positions", exc)
        errors.append({"section": "positions", "message": positions_section["error"]})

    try:
        orders_payload = await paper_trading_service.get_orders(symbol=symbol.upper() if symbol else None, limit=limit)
        orders = list(orders_payload.get("orders", [])) if isinstance(orders_payload, dict) else []
        orders_section = {"status": "ready", "items": orders, "total": len(orders)}
    except Exception as exc:
        orders_section = _section_error("orders", exc)
        errors.append({"section": "orders", "message": orders_section["error"]})

    try:
        risk_status = await risk_manager.get_risk_status(
            build_account_summary(balance, positions)["total_equity"] or _safe_float(balance.get("total_balance")),
            positions=positions,
        )
        risk_config = await risk_manager.get_config()
        risk_section = {
            "status": "ready",
            "risk_status": risk_status,
            "config": risk_config,
            "required_before_fill": True,
            "failure_actions": ["block", "reduce", "warn"],
            "blocked_action_audit": "RISK_BLOCKED",
        }
    except Exception as exc:
        risk_section = _section_error("risk_guard", exc)
        errors.append({"section": "risk_guard", "message": risk_section["error"]})

    try:
        order_intents_section = await _collect_order_intent_events(symbol, limit)
    except Exception as exc:
        order_intents_section = _section_error("order_intents", exc)
        order_intents_section["items"] = []
        order_intents_section["total"] = 0
        errors.append({"section": "order_intents", "message": order_intents_section["error"]})

    try:
        equity_section = await _collect_equity_curve(limit)
    except Exception as exc:
        equity_section = _section_error("equity_curve", exc)
        equity_section["points"] = []
        errors.append({"section": "equity_curve", "message": equity_section["error"]})

    account_summary = build_account_summary(balance, positions)
    order_summary = _orders_summary(orders)
    intent_items = list(order_intents_section.get("items", []))
    execution_chain = build_execution_chain(intent_items)

    if not equity_section.get("points"):
        equity_section["points"] = [
            {
                "t": _now_iso(),
                "v": account_summary["total_equity"],
                "cash": account_summary["cash_balance"],
                "position_value": account_summary["position_value"],
                "daily_pnl": 0,
                "drawdown": 0,
            }
        ]
        equity_section["source"] = "live_paper_account_fallback"

    return {
        "schema_version": PAPER_TRADING_WORKBENCH_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "mode": {
            "account_mode": "paper",
            "real_ordering_enabled": False,
            "live_broker_submission": False,
            "exchange_id": exchange_id,
        },
        "data_boundary": {
            "execution_mode": "paper_trading_only",
            "order_intent_required": True,
            "risk_guard_required": True,
            "audit_required": True,
            "audit_mutability": "append_only",
        },
        "account": {**account_section, "summary": account_summary},
        "order_intents": order_intents_section,
        "risk_guard": risk_section,
        "orders": orders_section,
        "positions": positions_section,
        "pnl": {
            "status": "ready",
            "summary": {
                **account_summary,
                **order_summary,
            },
            "equity_curve": equity_section,
        },
        "execution_chain": execution_chain,
        "apis": {
            "preview_order_intent": "/api/v1/execution/order-intents/preview",
            "execute_order_intent": "/api/v1/execution/order-intents/execute",
            "manual_order": "/api/v1/trading/orders",
            "risk_config": "/api/v1/risk/config-metadata",
            "audit_export": "/api/v1/audit/records/{audit_id}/export",
        },
        "errors": errors,
    }
