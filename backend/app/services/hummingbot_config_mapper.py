"""
Hummingbot Config Mapper

将 QuantAgent Paper Bot 配置映射为 Hummingbot V2 Controller 配置。

设计原则：
1. 只映射已验证可运行的策略组合
2. 未知/未支持组合返回 unsupported，不伪造 payload
3. 所有现货策略使用 binance / kucoin / gate_io 等现货 connector
4. 永续/期货 connector 永远返回 unsupported
"""

from dataclasses import dataclass
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


STRATEGY_MAPPING: Dict[str, Dict[str, StrategyMapperEntry]] = {
    # ── low_frequency_signal ──────────────────────────────────────────────────
    "low_frequency_signal": {
        "bollinger": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="bollinger_v1",
        ),
        "supertrend": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="supertrend_v1",
        ),
        "ma_cross": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="macd_bb_v1",
        ),
        "rsi": StrategyMapperEntry(
            controller_type="directional_trading",
            controller_name="bollinger_v1",  # RSI 作为 BB 参数传入
        ),
    },
    # ── position_executor ────────────────────────────────────────────────────
    "position_executor": {
        "default": StrategyMapperEntry(
            controller_type="generic",
            controller_name="pmm",
            supported=False,
            unsupported_reason="position_executor 当前需要永续 connector，不属于 Branch A 范围",
        ),
    },
}


# ── Connector 检查 ──────────────────────────────────────────────────────────────

def check_connector(connector: str, available_connectors: List[str]) -> PaperConnectorCheck:
    """
    检查 connector 是否可用于 Paper Bot。

    检查项：
    1. 是否在 PAPER_CONNECTOR_WHITELIST 中
    2. 是否包含禁止关键词（perpetual / testnet）
    3. 是否在 Hummingbot 可用 connectors 列表中
    """
    c_lower = connector.lower()

    in_whitelist = c_lower in {c.lower() for c in PAPER_CONNECTOR_WHITELIST}
    not_forbidden = not any(p in c_lower for p in FORBIDDEN_CONNECTOR_PATTERNS)
    # paper_trade_enabled：connector 在 whitelist 且不在 forbidden 且在可用列表中
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

    返回 supported=False 时表示当前组合不支持，不生成 payload。
    """
    strategy_map = STRATEGY_MAPPING.get(strategy_type, {})
    entry = strategy_map.get(signal_type)

    if entry is None:
        return StrategyMappingInfo(
            strategy_type=strategy_type,
            controller_type="",
            controller_name="",
            signal_type=signal_type,
            supported=False,
            unsupported_reason=f"策略 {strategy_type} + 信号 {signal_type} 的组合尚未支持",
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
    为指定 controller 生成 Hummingbot V2 Controller config payload。

    所有参数都从 request 中来，不引用外部数据。
    不支持永续 connector。
    """
    base = {
        "id": config_id,
        "controller_type": controller_type,
        "controller_name": controller_name,
        "connector_name": connector,
        "trading_pair": trading_pair,
        "total_amount_quote": paper_initial_balance,
        "min_order_amount_quote": order_amount,
    }

    if controller_name == "bollinger_v1":
        # Bollinger Bands 低频信号策略
        # 映射 timeframe：15m / 1h
        interval_map = {"15m": "15m", "1h": "1h"}
        interval = interval_map.get(timeframe, "1h")

        base.update({
            "interval": interval,
            "bb_length": 100,
            "bb_std": 2.0,
            "bb_long_threshold": 0.0,
            "bb_short_threshold": 1.0,
            # 风险参数（由 executor 层处理，controller 层面只是配置）
        })

    elif controller_name == "supertrend_v1":
        interval_map = {"15m": "15m", "1h": "1h"}
        interval = interval_map.get(timeframe, "1h")

        base.update({
            "interval": interval,
            "length": 20,
            "multiplier": 4.0,
            "percentage_threshold": 0.01,
        })

    elif controller_name == "macd_bb_v1":
        interval_map = {"15m": "15m", "1h": "1h"}
        interval = interval_map.get(timeframe, "1h")

        base.update({
            "interval": interval,
            "bb_length": 100,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
        })

    if extra_params:
        base.update(extra_params)

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

    # 检查 whitelist 中的 connector 是否可用
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
    4. connector 是否是现货 connector（不包含 perpetual/testnet）
    5. 策略是否已映射
    6. 策略是否支持
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
    available_lower = {c.lower() for c in available}
    available_set = set(available)

    # Step 3: Connector 检查
    connector_check = check_connector(connector, list(available_set))

    if not connector_check.not_forbidden:
        errors.append(
            f"connector '{connector}' 包含禁止关键词（perpetual / testnet）。"
            " 永续合约 / Testnet / Live connector 不允许用于 Paper Bot。"
        )

    if not connector_check.in_whitelist:
        errors.append(
            f"connector '{connector}' 不在 Paper Bot 允许列表中。"
            f" 当前仅支持现货 connector：{', '.join(sorted(PAPER_CONNECTOR_WHITELIST))}。"
        )
        warnings.append(
            "永续合约模拟属于 Testnet Bot 阶段（v1.3），不属于当前 Paper Bot 范围。"
        )

    if connector_check.in_whitelist and not connector_check.paper_trade_enabled:
        # 在 whitelist 但不在 Hummingbot 可用列表 → 可能是 paper_trade_exchanges 未配置
        warnings.append(
            f"connector '{connector}' 在白名单中但未在 Hummingbot 可用 connectors 中。"
            " 请确保 Hummingbot 的 paper_trade_exchanges 配置中包含此 connector。"
        )

    # Step 4: 策略映射检查
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
