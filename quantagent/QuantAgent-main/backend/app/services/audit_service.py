"""
Audit Logging Service
Records critical system actions and user interventions.
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.models.db_models import AuditLog
from app.services.database import get_db

logger = logging.getLogger(__name__)

LEGACY_EVENT_MAP = {
    "ORDER_INTENT_NOOP": "HOLD_RECORDED",
    "ORDER_INTENT_PREVIEW": "ORDER_INTENT_CREATED",
    "ORDER_INTENT_RISK_CHECKED": "RISK_CHECK_PASSED",
    "ORDER_INTENT_BLOCKED": "RISK_BLOCKED",
    "ORDER_INTENT_EXECUTED": "PAPER_ORDER_FILLED",
    "ORDER_CREATE": "PAPER_ORDER_FILLED",
    "ORDER_FILL": "PAPER_ORDER_FILLED",
    "ORDER_CANCEL": "PAPER_ORDER_REJECTED",
}

STANDARD_EVENT_TYPES = {
    "AGENT_DECISION",
    "ORDER_INTENT_CREATED",
    "HOLD_RECORDED",
    "RISK_CHECK_PASSED",
    "RISK_BLOCKED",
    "RISK_CHECK_UNAVAILABLE",
    "ORDER_INTENT_EXECUTION_LINKED",
    "PAPER_ORDER_FILLED",
    "PAPER_ORDER_REJECTED",
    "DECISION_REPLAY_REQUESTED",
    "DECISION_REPLAY_COMPLETED",
    "DECISION_REPLAY_FAILED",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any, limit: int) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)[:limit]


def _event_type_from_action(action: str, details: Dict[str, Any]) -> str:
    raw = _first_present(details.get("eventType"), details.get("event_type"), action)
    return LEGACY_EVENT_MAP.get(str(raw), str(raw))


def _stable_hash(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class AuditService:
    def _standardize_details(
        self,
        *,
        action: str,
        resource: Optional[str],
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Attach the PRD stage-2 audit shape and keep legacy JSON compatibility."""
        payload = dict(details or {})
        intent = _safe_dict(payload.get("intent"))
        decision = _safe_dict(payload.get("decision"))
        risk = _safe_dict(payload.get("risk_preview") or payload.get("riskCheckResult"))
        execution = _safe_dict(payload.get("execution") or payload.get("executionResult"))

        event_type = _event_type_from_action(action, payload)
        source_decision_id = _first_present(
            payload.get("sourceDecisionId"),
            payload.get("source_decision_id"),
            intent.get("sourceDecisionId"),
            intent.get("source_decision_id"),
        )
        replay_decision_id = _first_present(
            payload.get("replayDecisionId"),
            payload.get("replay_decision_id"),
            intent.get("replayDecisionId"),
            intent.get("replay_decision_id"),
        )
        decision_id = _first_present(
            payload.get("decisionId"),
            payload.get("decision_id"),
            replay_decision_id,
            source_decision_id,
            intent.get("sourceDecisionId"),
            intent.get("decision_id"),
            decision.get("id"),
        )
        order_intent_id = _first_present(
            payload.get("orderIntentId"),
            intent.get("id"),
            intent.get("intent_id"),
        )
        order_id = _first_present(
            payload.get("orderId"),
            payload.get("order_id"),
            execution.get("orderId"),
            execution.get("order_id"),
        )

        payload.update(
            {
                "eventType": event_type,
                "symbol": _first_present(payload.get("symbol"), intent.get("symbol"), resource),
                "asOfTime": _first_present(payload.get("asOfTime"), decision.get("timestamp")),
                "snapshotId": _first_present(payload.get("snapshotId"), decision.get("snapshot_id")),
                "decisionId": decision_id,
                "sourceDecisionId": source_decision_id,
                "replayDecisionId": replay_decision_id,
                "orderIntentId": order_intent_id,
                "orderId": order_id,
                "inputSummary": payload.get("inputSummary") or decision,
                "agentOutputs": payload.get("agentOutputs") or payload.get("agent_outputs") or [],
                "riskCheckResult": risk,
                "executionResult": execution,
                "immutable": True,
            }
        )
        return payload

    def _standard_columns(
        self,
        *,
        action: str,
        resource: Optional[str],
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        intent = _safe_dict(details.get("intent"))
        decision = _safe_dict(details.get("decision"))
        risk = _safe_dict(details.get("riskCheckResult") or details.get("risk_preview"))
        execution = _safe_dict(details.get("executionResult") or details.get("execution"))
        event_type = _event_type_from_action(action, details)

        risk_passed = risk.get("passed")
        if risk_passed is None:
            risk_passed = risk.get("allowed")
        risk_status = (
            "unavailable"
            if event_type == "RISK_CHECK_UNAVAILABLE" or risk.get("riskUnavailable") is True
            else "passed"
            if risk_passed is True
            else "blocked"
            if risk_passed is False or event_type == "RISK_BLOCKED"
            else "not_checked"
        )
        execution_status = _first_present(
            execution.get("status"),
            details.get("status") if event_type.startswith("PAPER_ORDER") else None,
            "FILLED" if event_type == "PAPER_ORDER_FILLED" else None,
            "REJECTED" if event_type == "PAPER_ORDER_REJECTED" else None,
        )
        decision_id = _safe_int(
            _first_present(
                details.get("decisionId"),
                details.get("decision_id"),
                intent.get("decision_id"),
                intent.get("sourceDecisionId"),
                decision.get("id"),
            )
        )
        source_decision_id = _safe_int(
            _first_present(details.get("sourceDecisionId"), details.get("source_decision_id"))
        )
        replay_decision_id = _safe_int(
            _first_present(details.get("replayDecisionId"), details.get("replay_decision_id"))
        )
        return {
            "event_type": _safe_str(event_type, 80),
            "symbol": _safe_str(_first_present(details.get("symbol"), intent.get("symbol"), resource), 100),
            "decision_id": decision_id,
            "source_decision_id": source_decision_id,
            "replay_decision_id": replay_decision_id,
            "order_intent_id": _safe_str(
                _first_present(details.get("orderIntentId"), intent.get("id"), intent.get("intent_id")),
                128,
            ),
            "order_id": _safe_str(
                _first_present(
                    details.get("orderId"),
                    details.get("order_id"),
                    execution.get("orderId"),
                    execution.get("order_id"),
                ),
                128,
            ),
            "context_id": _safe_str(_first_present(details.get("contextId"), decision.get("context_id")), 128),
            "context_hash": _safe_str(_first_present(details.get("contextHash"), decision.get("context_hash")), 128),
            "risk_status": _safe_str(risk_status, 32),
            "execution_status": _safe_str(execution_status, 32),
            "backtest_id": _safe_int(_first_present(details.get("backtestId"), details.get("backtest_id"))),
            "replay_session_id": _safe_str(
                _first_present(details.get("replaySessionId"), details.get("replay_session_id")),
                100,
            ),
            "execution_mode": _safe_str(
                _first_present(
                    details.get("executionMode"),
                    details.get("execution_mode"),
                    intent.get("executionMode"),
                    execution.get("executionMode"),
                ),
                50,
            ),
            "payload_hash": _stable_hash(details),
            "immutable": True,
        }

    async def _previous_hash(self, session: Any, columns: Dict[str, Any]) -> Optional[str]:
        chain_id = _first_present(
            columns.get("decision_id"),
            columns.get("source_decision_id"),
            columns.get("replay_decision_id"),
        )
        if chain_id is not None:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT payload_hash
                        FROM audit_logs
                        WHERE payload_hash IS NOT NULL
                          AND (
                            decision_id = :chain_id
                            OR source_decision_id = :chain_id
                            OR replay_decision_id = :chain_id
                          )
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"chain_id": int(chain_id)},
                )
            ).first()
        else:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT payload_hash
                        FROM audit_logs
                        WHERE payload_hash IS NOT NULL
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    )
                )
            ).first()
        return row[0] if row else None

    async def add_event(
        self,
        session: Any,
        *,
        action: str,
        user_id: str = "system",
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        flush: bool = False,
    ) -> AuditLog:
        """Add one standardized append-only audit row to an existing transaction."""
        standardized = self._standardize_details(
            action=action,
            resource=resource,
            details=details or {},
        )
        columns = self._standard_columns(
            action=action,
            resource=resource,
            details=standardized,
        )
        columns["prev_hash"] = await self._previous_hash(session, columns)
        log_entry = AuditLog(
            action=action,
            user_id=user_id,
            resource=resource,
            details=standardized,
            ip_address=ip_address,
            **columns,
        )
        session.add(log_entry)
        if flush:
            await session.flush()
        return log_entry

    async def log_event(
        self,
        action: str,
        user_id: str = "system",
        resource: str = None,
        details: Dict[str, Any] = None,
        ip_address: str = None,
        raise_on_failure: bool = False,
    ) -> bool:
        """
        Record an audit log entry.
        
        Args:
            action: The action performed (e.g., "ORDER_CREATE", "CONFIG_UPDATE")
            user_id: ID of the user or "system"
            resource: Target resource (e.g., "BTCUSDT", "settings")
            details: JSON details
            ip_address: Origin IP
        """
        if details is None:
            details = {}

        try:
            async with get_db() as session:
                await self.add_event(
                    session,
                    action=action,
                    user_id=user_id,
                    resource=resource,
                    details=details,
                    ip_address=ip_address,
                )
                # Commit is handled by context manager
            logger.info(f"Audit Log: {action} by {user_id} on {resource}")
            return True
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            if raise_on_failure:
                raise
            return False

# Singleton
audit_service = AuditService()
