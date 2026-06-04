"""Research asset taxonomy for factors, strategies, and signal events.

This module is intentionally lightweight: it does not calculate new factors.
It describes how existing factor snapshots, signal events, and backtest records
should be grouped and explained in the research UI.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


FACTOR_CATEGORY_ORDER = [
    "行情基础因子",
    "技术指标因子",
    "收益率因子",
    "波动率因子",
    "成交量因子",
    "新闻事件因子",
    "宏观因子",
    "加密特有因子",
    "未分类",
]


FACTOR_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "open": {"displayName": "开盘价", "category": "行情基础因子", "formula": "标准化 Bar.open", "dataSource": "标准化 K 线 Bar", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "high": {"displayName": "最高价", "category": "行情基础因子", "formula": "标准化 Bar.high", "dataSource": "标准化 K 线 Bar", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "low": {"displayName": "最低价", "category": "行情基础因子", "formula": "标准化 Bar.low", "dataSource": "标准化 K 线 Bar", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "close": {"displayName": "收盘价", "category": "行情基础因子", "formula": "标准化 Bar.close", "dataSource": "标准化 K 线 Bar", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "volume": {"displayName": "成交量", "category": "行情基础因子", "formula": "标准化 Bar.volume", "dataSource": "标准化 K 线 Bar", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "vwap": {"displayName": "成交量加权均价", "category": "行情基础因子", "formula": "sum(price * volume) / sum(volume)，按当前 Bar 或窗口口径计算", "dataSource": "标准化 K 线 Bar", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "sma_5": {"displayName": "5周期简单均线", "category": "技术指标因子", "formula": "close 最近 5 个周期简单平均", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "sma_10": {"displayName": "10周期简单均线", "category": "技术指标因子", "formula": "close 最近 10 个周期简单平均", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "sma_20": {"displayName": "20周期简单均线", "category": "技术指标因子", "formula": "close 最近 20 个周期简单平均", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "sma_30": {"displayName": "30周期简单均线", "category": "技术指标因子", "formula": "close 最近 30 个周期简单平均", "dataSource": "策略运行时计算", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "sma_60": {"displayName": "60周期简单均线", "category": "技术指标因子", "formula": "close 最近 60 个周期简单平均", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "ema_5": {"displayName": "5周期 EMA", "category": "技术指标因子", "formula": "close 的指数移动平均", "dataSource": "策略运行时计算", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "ema_12": {"displayName": "12周期 EMA", "category": "技术指标因子", "formula": "MACD 快线 EMA", "dataSource": "策略运行时计算", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "ema_20": {"displayName": "20周期 EMA", "category": "技术指标因子", "formula": "close 的指数移动平均", "dataSource": "策略运行时计算", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "ema_26": {"displayName": "26周期 EMA", "category": "技术指标因子", "formula": "MACD 慢线 EMA", "dataSource": "策略运行时计算", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "ema_60": {"displayName": "60周期 EMA", "category": "技术指标因子", "formula": "close 的指数移动平均", "dataSource": "策略运行时计算", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "rsi_14": {"displayName": "RSI 14", "category": "技术指标因子", "formula": "14周期上涨/下跌强弱比转换为 0-100 指标", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "macd_dif": {"displayName": "MACD DIF", "category": "技术指标因子", "formula": "EMA(12) - EMA(26)", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "macd_dea": {"displayName": "MACD DEA", "category": "技术指标因子", "formula": "DIF 的 9周期 EMA", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "macd_hist": {"displayName": "MACD 柱", "category": "技术指标因子", "formula": "(DIF - DEA) * 2", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "atr_14": {"displayName": "ATR 14", "category": "波动率因子", "formula": "14周期 True Range 指数平均", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "boll_mid": {"displayName": "布林带中轨", "category": "技术指标因子", "formula": "20周期 SMA", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "boll_upper": {"displayName": "布林带上轨", "category": "技术指标因子", "formula": "SMA(20) + 2 * std(close,20)", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "boll_lower": {"displayName": "布林带下轨", "category": "技术指标因子", "formula": "SMA(20) - 2 * std(close,20)", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "boll_pct_b": {"displayName": "布林带 %B", "category": "技术指标因子", "formula": "(close - lower) / (upper - lower)", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "boll_width": {"displayName": "布林带宽度", "category": "波动率因子", "formula": "(upper - lower) / mid", "dataSource": "factor_signal_pipeline", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "return_1": {"displayName": "1周期收益率", "category": "收益率因子", "formula": "close / close.shift(1) - 1", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "return_5": {"displayName": "5周期收益率", "category": "收益率因子", "formula": "close / close.shift(5) - 1", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "return_20": {"displayName": "20周期收益率", "category": "收益率因子", "formula": "close / close.shift(20) - 1", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "momentum_20": {"displayName": "20周期动量", "category": "收益率因子", "formula": "20周期收益率或价格斜率", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "reversal_5": {"displayName": "5周期反转", "category": "收益率因子", "formula": "-1 * 5周期收益率", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "volatility_20": {"displayName": "20周期历史波动率", "category": "波动率因子", "formula": "std(return_1, 20)", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "high_low_range": {"displayName": "高低价振幅", "category": "波动率因子", "formula": "(high - low) / close", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "drawdown_20": {"displayName": "20周期回撤", "category": "波动率因子", "formula": "close / rolling_max(close,20) - 1", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "volume_change": {"displayName": "成交量变化率", "category": "成交量因子", "formula": "volume / volume.shift(1) - 1", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "volume_price_divergence": {"displayName": "量价背离", "category": "成交量因子", "formula": "价格方向与成交量变化方向的组合标签", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "vwap_deviation": {"displayName": "VWAP 偏离", "category": "成交量因子", "formula": "close / vwap - 1", "dataSource": "预留：因子管道", "updateFrequency": "随 K 线周期更新", "supportsPIT": True},
    "news_sentiment": {"displayName": "新闻情绪", "category": "新闻事件因子", "formula": "新闻事件情绪评分聚合", "dataSource": "新闻/RSS/OpenBB 新闻管道", "updateFrequency": "随新闻入库更新", "supportsPIT": True},
    "regulatory_event": {"displayName": "监管事件标签", "category": "新闻事件因子", "formula": "监管相关新闻分类标签", "dataSource": "新闻/RSS/OpenBB 新闻管道", "updateFrequency": "随新闻入库更新", "supportsPIT": True},
    "etf_event": {"displayName": "ETF 事件标签", "category": "新闻事件因子", "formula": "ETF 相关新闻分类标签", "dataSource": "新闻/RSS/OpenBB 新闻管道", "updateFrequency": "随新闻入库更新", "supportsPIT": True},
    "macro_event": {"displayName": "宏观事件标签", "category": "新闻事件因子", "formula": "宏观相关新闻或事件标签", "dataSource": "新闻/宏观数据管道", "updateFrequency": "随事件入库更新", "supportsPIT": True},
    "exchange_event": {"displayName": "交易所事件标签", "category": "新闻事件因子", "formula": "交易所公告、宕机、上市/下架事件标签", "dataSource": "新闻/RSS/交易所公告", "updateFrequency": "随事件入库更新", "supportsPIT": True},
    "cpi": {"displayName": "CPI", "category": "宏观因子", "formula": "CPI 指标值或变化率", "dataSource": "OpenBB / FRED / OECD", "updateFrequency": "按宏观数据发布时间更新", "supportsPIT": True},
    "interest_rate": {"displayName": "利率", "category": "宏观因子", "formula": "政策利率或国债收益率", "dataSource": "OpenBB / FRED / OECD", "updateFrequency": "按宏观数据发布时间更新", "supportsPIT": True},
    "dollar_index": {"displayName": "美元指数", "category": "宏观因子", "formula": "DXY 或替代美元强弱指标", "dataSource": "OpenBB / yfinance", "updateFrequency": "按市场数据周期更新", "supportsPIT": True},
    "fred_macro": {"displayName": "FRED 宏观数据", "category": "宏观因子", "formula": "FRED 指标值、变化率或事件标签", "dataSource": "OpenBB / FRED", "updateFrequency": "按 FRED 指标发布时间更新", "supportsPIT": True},
    "funding_rate": {"displayName": "资金费率", "category": "加密特有因子", "formula": "永续合约 funding rate", "dataSource": "预留：CCXT/交易所衍生品接口", "updateFrequency": "通常 8 小时或交易所公布周期", "supportsPIT": False},
    "open_interest": {"displayName": "未平仓量", "category": "加密特有因子", "formula": "合约未平仓量", "dataSource": "预留：交易所衍生品接口", "updateFrequency": "按交易所接口更新", "supportsPIT": False},
    "exchange_netflow": {"displayName": "交易所净流入", "category": "加密特有因子", "formula": "交易所流入 - 流出", "dataSource": "预留：链上数据服务", "updateFrequency": "按链上数据服务更新", "supportsPIT": False},
    "long_short_ratio": {"displayName": "多空比", "category": "加密特有因子", "formula": "多头账户或持仓占比 / 空头占比", "dataSource": "预留：交易所衍生品接口", "updateFrequency": "按交易所接口更新", "supportsPIT": False},
    "stablecoin_supply": {"displayName": "稳定币供给", "category": "加密特有因子", "formula": "主要稳定币流通供给或变化率", "dataSource": "预留：链上/宏观加密数据", "updateFrequency": "按链上数据服务更新", "supportsPIT": False},
    "btc_dominance": {"displayName": "BTC 市占率", "category": "加密特有因子", "formula": "BTC 市值 / 加密总市值", "dataSource": "预留：加密市场聚合数据", "updateFrequency": "按市场数据周期更新", "supportsPIT": False},
}


STRATEGY_FACTOR_MAP: Dict[str, List[str]] = {
    "ma": ["close", "sma_10", "sma_30", "volume", "atr_14"],
    "rsi": ["close", "rsi_14", "volume"],
    "boll": ["close", "boll_mid", "boll_upper", "boll_lower", "boll_pct_b", "boll_width"],
    "macd": ["close", "ema_12", "ema_26", "macd_dif", "macd_dea", "macd_hist"],
    "ema_triple": ["close", "ema_5", "ema_20", "ema_60"],
    "atr_trend": ["high", "low", "close", "atr_14"],
    "turtle": ["high", "low", "close", "atr_14"],
    "ichimoku": ["high", "low", "close", "ichimoku_tenkan", "ichimoku_kijun", "ichimoku_cloud"],
    "smart_beta": ["news_sentiment", "macro_event", "btc_dominance", "stablecoin_supply", "exchange_netflow"],
    "basis": ["funding_rate", "open_interest", "basis"],
}


STRATEGY_TYPES: Dict[str, str] = {
    "ma": "趋势跟踪",
    "rsi": "均值回归",
    "boll": "均值回归",
    "macd": "趋势确认",
    "ema_triple": "趋势跟踪",
    "atr_trend": "波动率趋势",
    "turtle": "突破趋势",
    "ichimoku": "趋势跟踪",
    "smart_beta": "宏观/加密配置",
    "basis": "加密衍生品套利",
}


STRATEGY_RISK_RULES: Dict[str, List[str]] = {
    "ma": ["单笔仓位上限", "ATR 波动过滤", "最大回撤保护"],
    "rsi": ["超买超卖阈值", "单笔仓位上限", "连续亏损降频"],
    "boll": ["布林带触发阈值", "单笔仓位上限", "波动率过高暂停"],
    "macd": ["趋势确认", "单笔仓位上限", "最大回撤保护"],
    "ema_triple": ["多周期趋势一致性", "单笔仓位上限", "最大杠杆限制"],
    "atr_trend": ["ATR 动态止损", "单笔仓位上限", "最大回撤保护"],
    "turtle": ["突破确认", "ATR 风险预算", "最大回撤保护"],
    "ichimoku": ["云层趋势确认", "单笔仓位上限", "最大回撤保护"],
    "smart_beta": ["宏观事件过滤", "总敞口上限", "最大回撤保护"],
    "basis": ["资金费率阈值", "最大杠杆限制", "交易所风险过滤"],
}


def normalize_factor_name(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def classify_factor(factor_name: str, fallback_category: Optional[str] = None) -> str:
    name = normalize_factor_name(factor_name)
    if name in FACTOR_BLUEPRINTS:
        return FACTOR_BLUEPRINTS[name]["category"]

    if fallback_category and fallback_category in FACTOR_CATEGORY_ORDER:
        return fallback_category

    if name in {"open", "high", "low", "close", "volume", "vwap"}:
        return "行情基础因子"
    if name.startswith(("sma_", "ma_", "ema_", "rsi_", "macd_", "boll_", "ichimoku_")):
        return "技术指标因子"
    if name.startswith(("return_", "ret_", "momentum_", "reversal_")) or "return" in name:
        return "收益率因子"
    if name.startswith(("volatility_", "atr_", "drawdown_")) or "range" in name:
        return "波动率因子"
    if name.startswith("volume_") or "vwap" in name:
        return "成交量因子"
    if any(token in name for token in ("news", "sentiment", "event", "regulatory", "etf")):
        return "新闻事件因子"
    if any(token in name for token in ("cpi", "rate", "dollar", "fred", "macro", "oecd")):
        return "宏观因子"
    if any(token in name for token in ("funding", "interest", "netflow", "long_short", "stablecoin", "dominance", "basis")):
        return "加密特有因子"
    return fallback_category or "未分类"


def infer_availability_status(snapshot_count: int, latest_value: Any = None, supports_pit: bool = True) -> str:
    if snapshot_count > 0 and latest_value is not None:
        return "available"
    if snapshot_count > 0 or supports_pit:
        return "partial"
    return "unavailable"


def infer_missing_rate(status: str) -> float:
    if status == "available":
        return 0.0
    if status == "partial":
        return 0.5
    return 1.0


def strategy_factor_names(strategy_type: str) -> List[str]:
    return list(STRATEGY_FACTOR_MAP.get(strategy_type, []))


def strategies_using_factor(factor_name: str) -> List[str]:
    name = normalize_factor_name(factor_name)
    return sorted(
        strategy for strategy, factors in STRATEGY_FACTOR_MAP.items()
        if name in {normalize_factor_name(item) for item in factors}
    )


def signal_related_factor_names(factors: Any) -> List[str]:
    if not isinstance(factors, dict):
        return []
    return sorted(str(key) for key in factors.keys() if key)


def factor_blueprint(factor_name: str, definition: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    name = normalize_factor_name(factor_name)
    blueprint = dict(FACTOR_BLUEPRINTS.get(name, {}))
    definition = definition or {}
    category = classify_factor(name, definition.get("category"))
    display = (
        definition.get("display_name")
        or definition.get("displayName")
        or blueprint.get("displayName")
        or factor_name
    )
    return {
        "factorId": name,
        "factorName": name,
        "displayName": display,
        "category": category,
        "formula": definition.get("calculation") or blueprint.get("formula") or "暂无计算说明",
        "dataSource": definition.get("upstream_data") or blueprint.get("dataSource") or "暂无数据源说明",
        "updateFrequency": definition.get("default_interval") or blueprint.get("updateFrequency") or "随数据入库更新",
        "supportsPIT": bool(blueprint.get("supportsPIT", True)),
        "description": definition.get("description") or blueprint.get("description") or "",
        "unit": definition.get("unit") or blueprint.get("unit") or "",
    }


def category_sort_key(category: str) -> int:
    try:
        return FACTOR_CATEGORY_ORDER.index(category)
    except ValueError:
        return len(FACTOR_CATEGORY_ORDER)


def strategy_asset_base(strategy_type: str, template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    template = template or {}
    return {
        "strategyName": template.get("name") or strategy_type,
        "strategyType": STRATEGY_TYPES.get(strategy_type, "未分类策略"),
        "strategyId": strategy_type,
        "description": template.get("description") or "",
        "usedFactors": strategy_factor_names(strategy_type),
        "triggerSignals": ["BUY", "SELL", "WAIT"],
        "riskRules": STRATEGY_RISK_RULES.get(strategy_type, ["单笔仓位上限", "总敞口上限", "最大回撤保护"]),
        "supportedExecutionModes": ["rule_only", "agent_audited"],
    }


def merge_unique(*groups: Iterable[str]) -> List[str]:
    values = set()
    for group in groups:
        values.update(str(item) for item in group if item)
    return sorted(values)
