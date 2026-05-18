"""
Hummingbot Config Mapper

将 QuantAgent Paper Bot 配置映射为 Hummingbot V2 Controller 配置。

设计原则：
1. 只映射已验证可运行的策略组合
2. 未知/未支持组合返回 unsupported，不伪造 payload
3. 所有现货策略使用 binance / kucoin / gate_io 等现货 connector
4. 永续/期货 connector 永远返回 unsupported
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.schemas.hummingbot_paper_bot import (
    FORBIDDEN_CONNECTOR_PATTERNS,
    PAPER_CONNECTOR_WHITELIST,
    PaperConnectorCheck,
    PaperConnectorResponse,
    PreflightCheckResult,
    SignalType,
    StrategyMappingInfo,
    StrategyType,
)


# ── Spot 交易对映射 ──────────────────────────────────────────────────────────────

# QuantAgent 现货交易对 → Hummingbot connector 支持的现货对
SPOT_TRADING_PAIRS = {
    "BTC-USDT": {"binance": "BTC-USDT", "kucoin": "BTC-USDT", "gate_io": "BTC-USDT", "kraken": "BTC-USDT"},
    "ETH-USDT": {"binance": "ETH-USDT", "kucoin": "ETH-USDT", "gate_io": "ETH-USDT", "kraken": "ETH-USDT"},
    "SOL-USDT": {"binance": "SOL-USDT", "kucoin": "SOL-USDT", "gate_io": "SOL-USDT", "kraken": "SOL-USDT"},
    "BNB-USDT": {"binance": "BNB-USDT", "kucoin": "BNB-USDT", "gate_io": "BNB-USDT", "kraken": "BNB-USDT"},
    "DOGE-USDT": {"binance": "DOGE-USDT", "kucoin": "DOGE-USDT", "gate_io": "DOGE-USDT", "kraken": "DOGE-USDT"},
    "XRP-USDT": {"binance": "XRP-USDT", "kucoin": "XRP-USDT", "gate_io": "XRP-USDT", "kraken": "XRP-USDT"},
}


# ── 策略 → Controller 映射表 ──────────────────────────────────────────────────

@dataclass
class StrategyMapperEntry:
    controller_type: str
    controller_name: str
    supported: bool = True
    unsupported_reason: Optional[str] = None
    # 最小初始资金（USDT）
    min_initial_balance: float = 100.0
    # 支持的时间周期
    supported_timeframes: List[str] = field(
        default_factory=lambda: ["1m", "5m", "15m", "1h", "4h", "1d"]
    )


STRATEGY_MAPPING: Dict[str, Dict[str, StrategyMapperEntry]] = {
    # ── 已验证可用的策略（Hummingbot 镜像中存在对应 controller）──────────────────
    "boll": {
        "bollinger": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="bollinger_v1",
            supported_timeframes=["5m", "15m", "1h", "4h", "1d"],
            min_initial_balance=100.0,
        ),
    },
    # ── 兼容旧名映射（low_frequency_signal）───────────────────────────────────
    "low_frequency_signal": {
        "bollinger": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="bollinger_v1",
            supported_timeframes=["15m", "1h"],
        ),
        "supertrend": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="supertrend_v1",
            supported_timeframes=["15m", "1h"],
        ),
        "ma_cross": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="macd_bb_v1",
            supported_timeframes=["15m", "1h"],
        ),
        "rsi": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="macd_bb_v1",
            supported=False,
            unsupported_reason=(
                "RSI 信号类型当前暂不支持。"
                " 请改用已支持的信号类型：bollinger（bollinger_v1）、"
                "supertrend（supertrend_v1）或 ma_cross（macd_bb_v1）。"
            ),
            supported_timeframes=["15m", "1h"],
            min_initial_balance=100.0,
        ),
        "ma_crossover": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="macd_bb_v1",
            supported_timeframes=["15m", "1h"],
        ),
        "macd": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="macd_bb_v1",
            supported_timeframes=["15m", "1h"],
        ),
    },
    # ── 尚未支持的策略（controller 在 Hummingbot 镜像中不存在）────────────────
    # supported=False：preflight 直接拒绝，不调用 deploy
    # 禁止改为 supported=True，否则用户看到 HTTP 200，容器却 Exited(1)
    "ma": {
        "ma_cross": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="dman_v3",
            supported=False,
            unsupported_reason=(
                "ma_cross 映射到的控制器 directional_trading/dman_v3 "
                "在当前 Hummingbot 镜像中不存在（ModuleNotFoundError）。"
                " 请改用已支持的策略：bollinger（低频 signal → bollinger_v1）。"
            ),
            supported_timeframes=["5m", "15m", "1h", "4h", "1d"],
        ),
        "ma_crossover": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="dman_v3",
            supported=False,
            unsupported_reason=(
                "ma_crossover 的控制器 directional_trading/dman_v3 不存在。"
                " 请改用 bollinger（bollinger_v1）或 low_frequency_signal/ma_cross（macd_bb_v1）。"
            ),
            supported_timeframes=["5m", "15m", "1h", "4h", "1d"],
        ),
    },
    "ema_triple": {
        "ema_crossoverover": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="dman_v3",
            supported=False,
            unsupported_reason=(
                "ema_triple 的控制器 directional_trading/dman_v3 不存在。"
                " 请改用已支持的策略：bollinger、supertrend、macd。"
            ),
            supported_timeframes=["5m", "15m", "1h", "4h", "1d"],
            min_initial_balance=100.0,
        ),
        "ema_cross": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="dman_v3",
            supported=False,
            unsupported_reason=(
                "ema_cross 的控制器 directional_trading/dman_v3 不存在。"
                " 请改用已支持的策略：bollinger、supertrend、macd。"
            ),
            supported_timeframes=["5m", "15m", "1h", "4h", "1d"],
            min_initial_balance=100.0,
        ),
    },
    "macd": {
        "macd": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="dman_v3",
            supported=False,
            unsupported_reason=(
                "macd 的控制器 directional_trading/dman_v3 不存在。"
                " 请改用 low_frequency_signal/macd（映射到 directional_trading/macd_bb_v1）。"
            ),
            supported_timeframes=["5m", "15m", "1h", "4h", "1d"],
            min_initial_balance=100.0,
        ),
    },
    "rsi": {
        "rsi": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="dman_v3",
            supported=False,
            unsupported_reason=(
                "rsi 的控制器 directional_trading/dman_v3 不存在。"
                " 请改用 bollinger（rsi 信号映射到 bollinger_v1）。"
            ),
            supported_timeframes=["5m", "15m", "1h", "4h", "1d"],
            min_initial_balance=100.0,
        ),
    },
    "atr_trend": {
        "atr_trailing": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="dman_v3",
            supported=False,
            unsupported_reason=(
                "atr_trailing 的控制器 directional_trading/dman_v3 不存在。"
                " 请改用已支持的策略：bollinger、supertrend、macd。"
            ),
            supported_timeframes=["15m", "1h", "4h", "1d"],
            min_initial_balance=100.0,
        ),
    },
    "grid": {
        "grid": StrategyMapperEntry(
            controller_type="generic",
            controller_name="grid_strike",
            supported=False,
            unsupported_reason=(
                "grid 的控制器 generic/grid_strike 在当前 Hummingbot 镜像中不存在。"
                " 请改用已支持的策略：bollinger、supertrend、macd。"
            ),
            supported_timeframes=["1m", "5m", "15m", "1h"],
            min_initial_balance=500.0,
        ),
    },
    "dca": {
        "dca": StrategyMapperEntry(
            controller_type="generic",
            controller_name="dca",
            supported=False,
            unsupported_reason=(
                "dca 的控制器 generic/dca 在当前 Hummingbot 镜像中不存在。"
                " 请改用已支持的策略：bollinger、supertrend、macd。"
            ),
            supported_timeframes=["5m", "15m", "1h", "4h", "1d"],
            min_initial_balance=200.0,
        ),
    },
    "pmm": {
        "pmm": StrategyMapperEntry(
            controller_type="generic",
            controller_name="pmm",
            supported=False,
            unsupported_reason=(
                "pmm 的控制器 generic/pmm 在当前 Hummingbot 镜像中不存在。"
                " 请改用已支持的策略：bollinger、supertrend、macd。"
            ),
            supported_timeframes=["1m", "5m", "15m"],
            min_initial_balance=1000.0,
        ),
    },
    "ichimoku": {
        "ichimoku": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="dman_v3",
            supported=False,
            unsupported_reason=(
                "ichimoku 的控制器 directional_trading/dman_v3 不存在。"
                " 请改用已支持的策略：bollinger、supertrend、macd。"
            ),
            supported_timeframes=["1h", "4h", "1d"],
            min_initial_balance=500.0,
        ),
    },
    "turtle": {
        "turtle": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="dman_v3",
            supported=False,
            unsupported_reason=(
                "turtle 的控制器 directional_trading/dman_v3 不存在。"
                " 请改用已支持的策略：bollinger、supertrend、macd。"
            ),
            supported_timeframes=["1h", "4h", "1d"],
            min_initial_balance=1000.0,
        ),
    },
    "position_executor": {
        "default": StrategyMapperEntry(
            controller_type="generic",
            controller_name="pmm",
            supported=False,
            unsupported_reason="position_executor 当前需要永续 connector，请改用已支持的现货策略。",
        ),
    },
}


# ── Connector 检查 ──────────────────────────────────────────────────────────────

def check_connector(connector: str, available_connectors: List[str]) -> PaperConnectorCheck:
    """
    检查 connector 是否可用于 Paper Bot。

    检查项：
    1. 是否在 PAPER_CONNECTOR_WHITELIST 中
    2. 是否包含禁止关键词（testnet）
    3. 是否在 Hummingbot 可用 connectors 列表中
    """
    c_lower = connector.lower()

    in_whitelist = c_lower in {c.lower() for c in PAPER_CONNECTOR_WHITELIST}
    not_forbidden = not any(p in c_lower for p in FORBIDDEN_CONNECTOR_PATTERNS)
    paper_trade_enabled = (
        in_whitelist
        and not_forbidden
        and c_lower in {c.lower() for c in available_connectors}
    )

    return PaperConnectorCheck(
        connector=connector,
        available=paper_trade_enabled,
        in_whitelist=in_whitelist,
        not_forbidden=not_forbidden,
        paper_trade_enabled=paper_trade_enabled,
    )


# ── 策略映射 ───────────────────────────────────────────────────────────────────

def map_strategy(
    strategy_type: str,
    signal_type: str,
) -> StrategyMappingInfo:
    """
    将策略类型 + 信号类型映射到 Hummingbot controller。

    返回 supported=False 时表示当前组合不支持，preflight 直接拒绝，不调用 deploy。
    """
    strategy_map = STRATEGY_MAPPING.get(strategy_type, {})

    # 精确匹配
    entry = strategy_map.get(signal_type)

    # 如果没有精确匹配，尝试模糊匹配（同策略类型的 keys）
    if entry is None and strategy_type in STRATEGY_MAPPING:
        for key, e in strategy_map.items():
            if signal_type.lower() in key.lower() or key.lower() in signal_type.lower():
                entry = e
                break

    # 兼容：如果策略类型不存在，尝试在 low_frequency_signal 中查找
    if entry is None:
        legacy_map = STRATEGY_MAPPING.get("low_frequency_signal", {})
        entry = legacy_map.get(signal_type)
        if entry:
            # 如果在 legacy 中找到，复制回来以便下次快速查找
            if strategy_type not in STRATEGY_MAPPING:
                STRATEGY_MAPPING[strategy_type] = {}
            STRATEGY_MAPPING[strategy_type][signal_type] = entry

    # 全局模糊匹配（仅作为最后的兜底，不跨 strategy_type 匹配）
    if entry is None:
        for stype, smap in STRATEGY_MAPPING.items():
            for skey, e in smap.items():
                if signal_type.lower() in skey.lower() or skey.lower() in signal_type.lower():
                    # 仅在 low_frequency_signal 内部模糊匹配，禁止跨策略类型
                    if stype == "low_frequency_signal":
                        entry = e
                        strategy_type = stype
                        break
            if entry:
                break

    if entry is None:
        return StrategyMappingInfo(
            strategy_type=strategy_type,
            controller_type="",
            controller_name="",
            signal_type=signal_type,
            supported=False,
            unsupported_reason=f"策略 {strategy_type} + 信号 {signal_type} 的组合尚未支持。"
            f" 当前支持的策略类型：{', '.join(sorted(STRATEGY_MAPPING.keys()))}",
        )

    if not entry.supported:
        return StrategyMappingInfo(
            strategy_type=strategy_type,
            controller_type=entry.controller_type,
            controller_name=entry.controller_name,
            signal_type=signal_type,
            supported=False,
            unsupported_reason=entry.unsupported_reason,
        )

    return StrategyMappingInfo(
        strategy_type=strategy_type,
        controller_type=entry.controller_type,
        controller_name=entry.controller_name,
        signal_type=signal_type,
        supported=True,
    )


# ── Controller Config Payload 生成 ──────────────────────────────────────────────

def _normalize_timeframe(timeframe: str) -> str:
    """规范化时间周期名称"""
    mapping = {
        "1m": "1m", "m1": "1m",
        "5m": "5m", "m5": "5m",
        "15m": "15m", "m15": "15m",
        "1h": "1h", "h1": "1h",
        "4h": "4h", "h4": "4h",
        "1d": "1d", "d1": "1d",
    }
    return mapping.get(timeframe.lower(), "1h")


def build_controller_config_payload(
    config_id: str,
    controller_type: str,
    controller_name: str,
    connector: str,
    trading_pair: str,
    signal_type: str,
    timeframe: str,
    paper_initial_balance: float,
    order_amount: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    cooldown_minutes: int,
    max_trades_per_day: int,
    max_open_positions: int,
    extra_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    为已验证可用的 controller 生成 Hummingbot V2 Controller config payload。

    字段完全对齐 Hummingbot 镜像中的真实 Pydantic schema：
    - BollingerV1ControllerConfig
    - SuperTrendConfig
    - MACDBBV1ControllerConfig

    严禁发送 extra 字段（Hummingbot 使用 Pydantic extra_forbidden，会直接拒绝）。
    所有字段值以 docker exec python 查询到的 schema 为准。
    """
    ep = extra_params or {}

    # 转换风控百分比为 Decimal（schema 要求 Decimal 类型）
    stop_loss_decimal = Decimal(str(round(stop_loss_pct / 100.0, 6)))
    take_profit_decimal = Decimal(str(round(take_profit_pct / 100.0, 6)))
    # cooldown_time: schema 要求整数（秒）
    cooldown_seconds = int(cooldown_minutes * 60)
    # time_limit: schema 默认 2700 秒（45 分钟）
    max_runtime_minutes = ep.get("max_runtime_minutes", 60)
    time_limit_seconds = int(max_runtime_minutes * 60)

    # ── 所有 directional_trading controller 的共同基础字段 ─────────────────────
    base = {
        "id": config_id,
        "controller_type": controller_type,
        "controller_name": controller_name,
        # connector_name：使用现货 connector（如 binance），schema 默认 binance_perpetual
        "connector_name": connector,
        "trading_pair": trading_pair.upper(),
        # total_amount_quote：schema 要求 Decimal
        "total_amount_quote": Decimal(str(paper_initial_balance)),
        # 通用风控（schema 中 stop_loss/take_profit 是 Decimal，值 0.03=3%）
        "stop_loss": stop_loss_decimal,
        "take_profit": take_profit_decimal,
        # cooldown_time：schema 要求整数（秒），默认值 300
        "cooldown_time": cooldown_seconds if cooldown_seconds >= 60 else 300,
        # time_limit：schema 默认 2700 秒（45 分钟）
        "time_limit": time_limit_seconds,
        # 现货交易使用 ONEWAY，不使用 HEDGE
        "position_mode": "ONEWAY",
        # 现货不使用杠杆
        "leverage": 1,
    }

    # ── directional_trading/bollinger_v1 ──────────────────────────────────────
    if controller_name == "bollinger_v1":
        base.update({
            "interval": _normalize_timeframe(timeframe),
            # bb_length：schema 默认 100
            "bb_length": ep.get("boll_period", 100),
            # bb_std：schema 默认 2.0
            "bb_std": ep.get("boll_std_dev", 2.0),
            "bb_long_threshold": 0.0,
            "bb_short_threshold": 1.0,
            # max_executors_per_side：控制同时挂单数量
            "max_executors_per_side": max_open_positions,
        })

    # ── directional_trading/supertrend_v1 ────────────────────────────────────
    elif controller_name == "supertrend_v1":
        base.update({
            "interval": _normalize_timeframe(timeframe),
            "length": 20,
            "multiplier": ep.get("atr_multiplier", 4.0),
            "percentage_threshold": 0.01,
            "max_executors_per_side": max_open_positions,
        })

    # ── directional_trading/macd_bb_v1 ───────────────────────────────────────
    elif controller_name == "macd_bb_v1":
        base.update({
            "interval": _normalize_timeframe(timeframe),
            "bb_length": ep.get("boll_period", 100),
            "bb_std": ep.get("boll_std_dev", 2.0),
            "bb_long_threshold": 0.0,
            "bb_short_threshold": 1.0,
            "macd_fast": ep.get("macd_fast", 12),
            "macd_slow": ep.get("macd_slow", 26),
            "macd_signal": ep.get("macd_signal", 9),
            "max_executors_per_side": max_open_positions,
        })

    return base


# ── Hummingbot API 调用 ─────────────────────────────────────────────────────────

import httpx


async def get_available_connectors(
    base_url: str,
    username: str = "",
    password: str = "",
    timeout: float = 10.0,
) -> List[str]:
    """从 Hummingbot API 获取可用 connectors 列表。"""
    try:
        url = f"{base_url.rstrip('/')}/connectors"
        auth = httpx.BasicAuth(username, password) if username and password else None
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, auth=auth)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("data", [])
        return []
    except Exception:
        return []


async def check_paper_connectors_available(
    base_url: str,
    username: str = "",
    password: str = "",
) -> PaperConnectorResponse:
    """
    检查 Paper Bot 可用的 connector。

    逻辑：
    1. 从 Hummingbot API 获取可用 connectors
    2. 检查 whitelist 中的 connector 是否在可用列表中
    3. 返回可用 connector 列表
    """
    available = await get_available_connectors(base_url, username, password)

    available_lower = {c.lower() for c in available}
    available_paper_connectors = [
        c for c in PAPER_CONNECTOR_WHITELIST
        if c.lower() in available_lower
    ]

    if available_paper_connectors:
        return PaperConnectorResponse(
            connected=True,
            data={
                "paper_connectors": available_paper_connectors,
                "available_connectors": available,
                "available": True,
                "message": None,
            },
        )
    else:
        return PaperConnectorResponse(
            connected=True,
            data={
                "paper_connectors": [],
                "available_connectors": available,
                "available": False,
                "message": "当前 Hummingbot 未检测到可用 paper connector，无法启动纯 Paper Bot。",
            },
        )


# ── Preflight Check ─────────────────────────────────────────────────────────────

async def run_preflight_check(
    base_url: str,
    username: str,
    password: str,
    connector: str,
    strategy_type: str,
    signal_type: str,
) -> PreflightCheckResult:
    """
    执行 Paper Bot 启动前的 preflight 检查。

    检查项：
    1. Hummingbot API 是否在线
    2. connector 是否在白名单且不在禁止列表
    3. connector 是否在 Hummingbot 可用 connectors 中
    4. 策略是否已映射（supported=False 时直接拒绝）
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Step 1: API 在线检测
    api_online = False
    try:
        url = f"{base_url.rstrip('/')}/"
        auth = httpx.BasicAuth(username, password) if username and password else None
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            r = await client.get(url, auth=auth)
            api_online = r.status_code == 200
    except Exception as e:
        errors.append(f"Hummingbot API 不在线或无法访问: {str(e)}")

    if not api_online:
        return PreflightCheckResult(
            passed=False,
            api_online=False,
            connector_check=None,
            controller_available=False,
            errors=errors,
        )

    # Step 2: 获取可用 connectors
    available = await get_available_connectors(base_url, username, password)
    available_set = set(available)

    # Step 3: Connector 检查
    connector_check = check_connector(connector, list(available_set))

    if not connector_check.not_forbidden:
        errors.append(
            f"connector '{connector}' 包含禁止关键词（testnet）。"
            " Testnet connector 不允许用于 Paper Bot。"
        )

    if not connector_check.in_whitelist:
        errors.append(
            f"connector '{connector}' 不在 Paper Bot 允许列表中。"
            f" 当前支持的 connector：{', '.join(sorted(PAPER_CONNECTOR_WHITELIST))}。"
        )

    if connector_check.in_whitelist and not connector_check.paper_trade_enabled:
        warnings.append(
            f"connector '{connector}' 在白名单中但未在 Hummingbot 可用 connectors 中。"
            " 请确保 Hummingbot 的 paper_trade_exchanges 配置中包含此 connector。"
        )

    # Step 4: 策略映射检查（supported=False 直接拒绝）
    mapping = map_strategy(strategy_type, signal_type)

    if not mapping.supported:
        errors.append(mapping.unsupported_reason or "策略映射失败")

    # Step 5: 综合判断
    passed = (
        api_online
        and connector_check.not_forbidden
        and connector_check.in_whitelist
        and mapping.supported
        and len(errors) == 0
    )

    return PreflightCheckResult(
        passed=passed,
        api_online=api_online,
        connector_check=connector_check,
        controller_available=mapping.supported,
        errors=errors,
        warnings=warnings,
    )
