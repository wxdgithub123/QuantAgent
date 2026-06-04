from app.services.research_assets import (
    classify_factor,
    factor_blueprint,
    infer_availability_status,
    signal_related_factor_names,
    strategies_using_factor,
    strategy_asset_base,
    strategy_factor_names,
)


def test_factor_classification_matches_prd_categories():
    assert classify_factor("close") == "行情基础因子"
    assert classify_factor("rsi_14") == "技术指标因子"
    assert classify_factor("return_20") == "收益率因子"
    assert classify_factor("atr_14") == "波动率因子"
    assert classify_factor("volume_change") == "成交量因子"
    assert classify_factor("news_sentiment") == "新闻事件因子"
    assert classify_factor("cpi") == "宏观因子"
    assert classify_factor("funding_rate") == "加密特有因子"


def test_factor_availability_status_is_compatible_with_missing_data():
    assert infer_availability_status(snapshot_count=12, latest_value=101.5, supports_pit=True) == "available"
    assert infer_availability_status(snapshot_count=12, latest_value=None, supports_pit=True) == "partial"
    assert infer_availability_status(snapshot_count=0, latest_value=None, supports_pit=False) == "unavailable"


def test_strategy_detail_can_return_used_factors():
    assert "close" in strategy_factor_names("ma")
    assert "sma_10" in strategy_factor_names("ma")
    asset = strategy_asset_base("macd", {"name": "MACD 策略", "description": "test"})
    assert asset["strategyName"] == "MACD 策略"
    assert "macd_hist" in asset["usedFactors"]
    assert "agent_audited" in asset["supportedExecutionModes"]


def test_factor_detail_can_reverse_link_strategies():
    assert "ma" in strategies_using_factor("close")
    assert "macd" in strategies_using_factor("macd_hist")
    assert strategies_using_factor("unknown_factor") == []


def test_signal_event_related_factors_are_extracted_from_payload():
    factors = {"rsi_14": 62.0, "macd_hist": 0.2, "close": 73500.0}
    assert signal_related_factor_names(factors) == ["close", "macd_hist", "rsi_14"]
    assert signal_related_factor_names(None) == []


def test_factor_blueprint_returns_p4_card_fields():
    item = factor_blueprint("btc_dominance")
    assert item["category"] == "加密特有因子"
    assert item["factorName"] == "btc_dominance"
    assert item["formula"]
    assert item["dataSource"]
