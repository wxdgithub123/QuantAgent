"""
Hummingbot Paper Bot Schema Definitions

v1.2.x: 低频信号策略（现货交易）
- 只支持现货 connector（binance / kucoin / gate_io）
- 禁止所有 perpetual / testnet / live connector
- 低频 signal-based / position-based 策略
- 最小闭环：策略可启动 + 远端可检测
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ── Connector 白名单 ─────────────────────────────────────────────────────────────

# Paper Bot 只允许这些现货 connector（已在 paper_trade_exchanges 中）
PAPER_CONNECTOR_WHITELIST = {
    "binance",
    "kucoin",
    "gate_io",
    "kraken",
}

# 禁止的 connector 类型
FORBIDDEN_CONNECTOR_PATTERNS = [
    "perpetual",
    "testnet",
    "binance_perpetual",
    "bybit_perpetual",
    "binance_perpetual_testnet",
    "bybit_perpetual_testnet",
]


# ── Strategy Types ──────────────────────────────────────────────────────────────

class StrategyType(str, Enum):
    """策略类型（低频信号 / 现货）"""
    LOW_FREQUENCY_SIGNAL = "low_frequency_signal"
    POSITION_EXECUTOR = "position_executor"


# ── Timeframe ───────────────────────────────────────────────────────────────────

class Timeframe(str, Enum):
    """K线周期（低频：15m / 1h）"""
    M15 = "15m"
    H1 = "1h"


# ── Signal Type ─────────────────────────────────────────────────────────────────

class SignalType(str, Enum):
    """信号类型"""
    MA_CROSS = "ma_cross"
    BOLLINGER = "bollinger"
    SUPERTREND = "supertrend"
    RSI = "rsi"


# ── Spot Trading Pairs ──────────────────────────────────────────────────────────

class SpotTradingPair(str, Enum):
    """现货交易对"""
    BTC_USDT = "BTC-USDT"
    ETH_USDT = "ETH-USDT"
    SOL_USDT = "SOL-USDT"


# ── Request Schemas ─────────────────────────────────────────────────────────────

class PaperBotPreviewRequest(BaseModel):
    bot_name: str = Field(..., min_length=3, max_length=64)
    connector: str = Field(
        ...,
        description="现货 connector，只能是 binance / kucoin / gate_io / kraken"
    )
    strategy_type: StrategyType = Field(...)
    trading_pair: str = Field(..., description="现货交易对，如 BTC-USDT / ETH-USDT / SOL-USDT")
    timeframe: Timeframe = Field(default=Timeframe.H1, description="K线周期：15m / 1h")
    signal_type: SignalType = Field(
        default=SignalType.BOLLINGER,
        description="信号类型：ma_cross / bollinger / supertrend / rsi"
    )
    paper_initial_balance: float = Field(
        ..., gt=0, le=1000000,
        description="模拟初始资金（USDT）"
    )
    order_amount: float = Field(
        ...,
        gt=0,
        description="每笔模拟订单金额（USDT）"
    )
    # 风控
    stop_loss_pct: float = Field(
        default=5.0, ge=0, le=50,
        description="止损百分比"
    )
    take_profit_pct: float = Field(
        default=10.0, ge=0, le=100,
        description="止盈百分比"
    )
    # 频率控制
    cooldown_minutes: int = Field(
        default=60, ge=5, le=1440,
        description="两次交易之间的最小间隔（分钟）"
    )
    max_trades_per_day: int = Field(
        default=3, ge=1, le=24,
        description="每日最大交易次数"
    )
    max_open_positions: int = Field(
        default=1, ge=1, le=5,
        description="最大同时持仓数（当前固定为 1）"
    )
    # 运行时间
    max_runtime_minutes: int = Field(..., ge=1, le=10080, description="最大运行时间（分钟）")

    @field_validator("bot_name")
    @classmethod
    def validate_bot_name(cls, v: str) -> str:
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("bot_name 只能包含字母、数字、下划线和中划线")
        return v

    @field_validator("trading_pair")
    @classmethod
    def validate_trading_pair(cls, v: str) -> str:
        import re
        if not re.match(r'^[A-Z0-9-]+$', v):
            raise ValueError("trading_pair 必须使用大写格式，如 BTC-USDT")
        # 禁止永续格式
        v_upper = v.upper()
        if "PERP" in v_upper or "PERPETUAL" in v_upper:
            raise ValueError("永续合约交易对不允许用于 Paper Bot。请使用现货交易对如 BTC-USDT。")
        return v

    @field_validator("connector")
    @classmethod
    def validate_connector(cls, v: str) -> str:
        v_lower = v.lower()
        # 检查是否在白名单
        if v_lower not in PAPER_CONNECTOR_WHITELIST:
            raise ValueError(
                f"connector '{v}' 不在 Paper Bot 允许列表中。"
                f"当前仅支持现货 connector：{', '.join(sorted(PAPER_CONNECTOR_WHITELIST))}。"
            )
        # 检查是否包含禁止关键词
        for pattern in FORBIDDEN_CONNECTOR_PATTERNS:
            if pattern.lower() in v_lower:
                raise ValueError(
                    f"connector '{v}' 包含禁止关键词 '{pattern}'。"
                    f"永续合约 / Testnet / Live connector 不允许用于 Paper Bot。"
                )
        return v_lower

    @field_validator("order_amount")
    @classmethod
    def validate_order_amount(cls, v: float, info) -> float:
        # 注意：这里不直接访问其他字段，通过 model_validator 验证
        return v


class PaperBotStartRequest(PaperBotPreviewRequest):
    """启动 Paper Bot 的请求（继承自预览请求）"""
    pass


# ── Preflight Check Schemas ─────────────────────────────────────────────────────

class PaperConnectorCheck(BaseModel):
    """Paper Connector 可用性"""
    connector: str
    available: bool
    in_whitelist: bool
    not_forbidden: bool
    paper_trade_enabled: bool


class PreflightCheckResult(BaseModel):
    """Preflight 检查结果"""
    passed: bool
    api_online: bool
    connector_check: Optional[PaperConnectorCheck] = None
    controller_available: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ── Strategy Mapping Info ────────────────────────────────────────────────────────

class StrategyMappingInfo(BaseModel):
    """策略映射信息"""
    strategy_type: str
    controller_type: str
    controller_name: str
    signal_type: Optional[str] = None
    supported: bool
    unsupported_reason: Optional[str] = None


# ── Response Schemas ─────────────────────────────────────────────────────────────

class RiskConfig(BaseModel):
    stop_loss_pct: float
    take_profit_pct: float
    max_runtime_minutes: int
    cooldown_minutes: int
    max_trades_per_day: int
    max_open_positions: int


class StrategyParams(BaseModel):
    """策略参数"""
    timeframe: str
    signal_type: str
    connector: str
    trading_pair: str
    paper_initial_balance: float
    order_amount: float
    risk: RiskConfig


class ConfigPreview(BaseModel):
    """Paper Bot 配置预览"""
    bot_name: str
    mode: str = "paper"
    live_trading: bool = False
    testnet: bool = False
    uses_real_exchange_account: bool = False
    requires_api_key: bool = False
    connector: str
    strategy_type: str
    trading_pair: str
    strategy_params: StrategyParams
    notes: List[str]


class PaperBotPreviewData(BaseModel):
    config_preview: ConfigPreview
    strategy_mapping: Optional[StrategyMappingInfo] = None
    warnings: List[str]


class PaperBotPreviewResponse(BaseModel):
    valid: bool
    source: str = "quantagent"
    mode: str = "paper"
    live_trading: bool = False
    testnet: bool = False
    data: Optional[PaperBotPreviewData] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ── Paper Bot 启动响应 Schemas ─────────────────────────────────────────────────

class PaperBotStartData(BaseModel):
    paper_bot_id: str
    bot_name: str
    connector: str
    strategy_type: str
    trading_pair: str
    local_status: str = Field(
        description="本地状态: submitted=已提交待对账, start_failed=启动失败, running=远端已确认"
    )
    remote_confirmed: bool = Field(
        description="Hummingbot API 是否已确认该 Bot 真正在运行"
    )
    local_record_created: bool
    remote_started: bool
    hummingbot_bot_id: Optional[str] = None
    started_at: str
    config: Optional[Dict[str, Any]] = None
    hummingbot_response: Optional[Dict[str, Any]] = None


class PaperBotStartResponse(BaseModel):
    local_record_created: bool
    remote_started: bool
    remote_confirmed: bool
    source: str = "quantagent"
    mode: str = "paper"
    live_trading: bool = False
    testnet: bool = False
    data: Optional[PaperBotStartData] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ── Paper Connector 可用性 ───────────────────────────────────────────────────────

class PaperConnectorResponse(BaseModel):
    """GET /paper-connectors 响应"""
    connected: bool
    data: Dict[str, Any]
    error: Optional[str] = None


# ── Paper Bot 列表/详情 ────────────────────────────────────────────────────────

class PaperBotReconciliationInfo(BaseModel):
    local_status: str
    remote_status: str
    matched_remote_bot: bool
    matched_by: str
    hummingbot_bot_id: Optional[str] = None
    last_remote_check_at: Optional[str] = None
    last_error: Optional[str] = None


class PaperBotRecord(BaseModel):
    paper_bot_id: str
    bot_name: str
    connector: str
    strategy_type: str
    trading_pair: str
    mode: str = "paper"
    live_trading: bool = False
    testnet: bool = False
    local_status: str = "created"
    remote_status: str = "not_detected"
    matched_remote_bot: bool = False
    matched_by: str = "none"
    hummingbot_bot_id: Optional[str] = None
    last_remote_check_at: Optional[str] = None
    last_error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    runtime_seconds: int = 0
    config: Optional[Dict[str, Any]] = None
    hummingbot_status_raw: Optional[Dict[str, Any]] = None
