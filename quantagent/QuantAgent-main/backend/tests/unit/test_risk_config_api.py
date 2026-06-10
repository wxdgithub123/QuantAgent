import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.risk import _normalize_risk_config_update


def _base_config():
    return {
        "MAX_SINGLE_POSITION_PCT": 0.20,
        "MAX_TOTAL_EXPOSURE_PCT": 1.00,
        "MAX_TOTAL_DRAWDOWN_PCT": 0.15,
        "MAX_DAILY_LOSS_PCT": 0.05,
        "PRICE_DEVIATION_PCT": 0.05,
        "MAX_VOLATILITY_THRESHOLD": 0.80,
        "MAINTENANCE_MARGIN_RATE": 0.05,
        "MARGIN_WARNING_LEVEL": 0.70,
        "PRE_LIQUIDATION_LEVEL": 0.90,
        "VOLATILITY_TARGET_PCT": 0.02,
        "FORBIDDEN_SYMBOLS": [],
        "MIN_ORDER_NOTIONAL": 5.0,
        "WAIT_ORDER_INTENT_POLICY": "record_flat",
        "RISK_FAILURE_ACTION": "block",
    }


def test_risk_config_accepts_full_p1_fields():
    update = _normalize_risk_config_update(
        {
            "MAX_TOTAL_EXPOSURE_PCT": 1.25,
            "FORBIDDEN_SYMBOLS": "btcusdt, eth/usdt, BTCUSDT",
            "MARGIN_WARNING_LEVEL": 0.60,
            "PRE_LIQUIDATION_LEVEL": 0.85,
            "MIN_ORDER_NOTIONAL": 10.0,
            "WAIT_ORDER_INTENT_POLICY": "skip",
            "RISK_FAILURE_ACTION": "warn",
        },
        _base_config(),
    )

    assert update["MAX_TOTAL_EXPOSURE_PCT"] == 1.25
    assert update["FORBIDDEN_SYMBOLS"] == ["BTCUSDT", "ETHUSDT"]
    assert update["MARGIN_WARNING_LEVEL"] == 0.60
    assert update["PRE_LIQUIDATION_LEVEL"] == 0.85
    assert update["MIN_ORDER_NOTIONAL"] == 10.0
    assert update["WAIT_ORDER_INTENT_POLICY"] == "skip"
    assert update["RISK_FAILURE_ACTION"] == "warn"


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"UNKNOWN_KEY": 1}, "Invalid config key"),
        ({"MAX_DAILY_LOSS_PCT": True}, "Invalid value"),
        ({"MAX_DAILY_LOSS_PCT": 1.5}, "must be between"),
        ({"MAX_SINGLE_POSITION_PCT": 1.2}, "must be between"),
        ({"FORBIDDEN_SYMBOLS": ["BTCUSDT", "bad symbol"]}, "Invalid forbidden symbol"),
        ({"MIN_ORDER_NOTIONAL": -1}, "must be between"),
        ({"WAIT_ORDER_INTENT_POLICY": "trade_wait"}, "WAIT_ORDER_INTENT_POLICY"),
        ({"RISK_FAILURE_ACTION": "bypass"}, "RISK_FAILURE_ACTION"),
        ({"MARGIN_WARNING_LEVEL": 0.95}, "MARGIN_WARNING_LEVEL"),
        ({"MAX_TOTAL_EXPOSURE_PCT": 0.10}, "MAX_SINGLE_POSITION_PCT"),
    ],
)
def test_risk_config_rejects_invalid_updates(payload, expected):
    with pytest.raises(HTTPException) as exc:
        _normalize_risk_config_update(payload, _base_config())

    assert expected in str(exc.value.detail)
