"""
Audit Logging Service
Records critical system actions and user interventions.
"""

import logging
from typing import Dict, Any, Optional
from app.services.database import get_db
from app.models.db_models import AuditLog

logger = logging.getLogger(__name__)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _event_type_from_action(action: str, details: Dict[str, Any]) -> str:
    if details.get("eventType"):
        return str(details["eventType"])
    if details.get("event_type"):
        return str(details["event_type"])
    mapping = {
        "ORDER_INTENT_NOOP": "HOLD_RECORDED",
        "ORDER_INTENT_PREVIEW": "ORDER_INTENT_CREATED",
        "ORDER_INTENT_RISK_CHECKED": "RISK_CHECK_PASSED",
        "ORDER_INTENT_BLOCKED": "RISK_BLOCKED",
        "ORDER_INTENT_EXECUTED": "PAPER_ORDER_FILLED",
        "ORDER_CREATE": "PAPER_ORDER_FILLED",
        "ORDER_CANCEL": "PAPER_ORDER_REJECTED",
    }
    return mapping.get(action, action)


class AuditService:
    def _standardize_details(
        self,
        *,
        action: str,
        resource: Optional[str],
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Attach the PRD stage-2 audit shape without changing the DB schema."""
        payload = dict(details or {})
        intent = _safe_dict(payload.get("intent"))
        decision = _safe_dict(payload.get("decision"))
        risk = _safe_dict(payload.get("risk_preview") or payload.get("riskCheckResult"))
        execution = _safe_dict(payload.get("execution") or payload.get("executionResult"))

        event_type = _event_type_from_action(action, payload)
        decision_id = _first_present(
            payload.get("decisionId"),
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

    async def log_event(
        self,
        action: str,
        user_id: str = "system",
        resource: str = None,
        details: Dict[str, Any] = None,
        ip_address: str = None
    ):
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
        details = self._standardize_details(action=action, resource=resource, details=details)
            
        try:
            async with get_db() as session:
                log_entry = AuditLog(
                    action=action,
                    user_id=user_id,
                    resource=resource,
                    details=details,
                    ip_address=ip_address
                )
                session.add(log_entry)
                # Commit is handled by context manager
            logger.info(f"Audit Log: {action} by {user_id} on {resource}")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

# Singleton
audit_service = AuditService()
