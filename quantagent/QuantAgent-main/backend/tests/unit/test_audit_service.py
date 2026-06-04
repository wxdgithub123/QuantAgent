from app.services.audit_service import AuditService


def test_audit_service_standardizes_lookup_ids():
    service = AuditService()

    details = service._standardize_details(
        action="PAPER_ORDER_FILLED",
        resource="BTCUSDT",
        details={
            "intent": {
                "id": "OI-101-okx-0500",
                "decision_id": 101,
                "symbol": "BTCUSDT",
                "action": "BUY",
            },
            "execution": {
                "order_id": "PT-999",
                "status": "FILLED",
            },
            "risk_preview": {
                "passed": True,
                "checkedRules": [],
            },
        },
    )

    assert details["eventType"] == "PAPER_ORDER_FILLED"
    assert details["symbol"] == "BTCUSDT"
    assert details["decisionId"] == 101
    assert details["orderIntentId"] == "OI-101-okx-0500"
    assert details["orderId"] == "PT-999"
    assert details["riskCheckResult"]["passed"] is True
    assert details["executionResult"]["status"] == "FILLED"
    assert details["immutable"] is True
