"""
Hummingbot Testnet Perpetual Bot Schema Definitions

v1.3.x: Testnet 永续合约 Bot

设计原则：
1. 使用 binance_perpetual_testnet（测试网 API Key）
2. 对接 Hummingbot directional_trading controller
3. 不动真钱，走交易所测试环境
4. 所有字段与 Hummingbot 真实 Pydantic schema 完全对齐
5. 不使用现货 connector
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ── Connectors ──────────────────────────────────────────────────────────────

ALLOWED_TESTNET_CONNECTORS = {
    "binance_perpetual_testnet",
    "bybit_perpetual_testnet",
    "okx_perpetual_testnet",
    "gate_io_perpetual_testnet",
    "bitget_perpetual_testnet",
}

ALLOWED_TESTNET_ACCOUNTS = {
    "binance_testnet_account",
    "bybit_testnet_account",
    "okx_testnet_account",
    "gate_io_testnet_account",
    "bitget_testnet_account",
}


# ── Strategy Types ──────────────────────────────────────────────────────────────

class TestnetStrategyType(str, Enum):
    """策略类型"""
    DIRECTIONAL_TRADING = "directional_trading"
    MARKET_MAKING = "market_making"
    ARBITRAGE = "arbitrage"


class TestnetSignalType(str, Enum):
    """信号类型"""
    BOLLINGER = "bollinger"
    SUPERTREND = "supertrend"
    MACD_BB = "macd_bb"
    RSI = "rsi"


class TestnetTimeframe(str, Enum):
    """K线周期"""
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"


class TestnetPositionMode(str, Enum):
    """持仓模式"""
    ONEWAY = "ONEWAY"
    HEDGE = "HEDGE"


# ── Request Schemas ─────────────────────────────────────────────────────────────

class TestnetBotPreviewRequest(BaseModel):
    """Testnet Bot 配置预览请求"""
    bot_name: str = Field(..., min_length=3, max_length=64)
    connector: str = Field(
        ...,
        description="测试网 connector，只能是 binance_perpetual_testnet 等"
    )
    credentials_profile: str = Field(
        ...,
        description="测试网凭证 profile，如 binance_testnet_account"
    )
    controller_name: str = Field(
        default="bollinger_v1",
        description="Hummingbot controller 名称"
    )
    trading_pair: str = Field(..., description="永续合约交易对，如 BTC-USDT")
    timeframe: TestnetTimeframe = Field(default=TestnetTimeframe.M15, description="K线周期")
    # ── 策略参数 ──────────────────────────────────────────────
    # 布林带参数
    bb_length: int = Field(default=100, ge=1, le=500, description="布林带周期")
    bb_std: float = Field(default=2.0, ge=0.1, le=5.0, description="布林带标准差倍数")
    bb_long_threshold: float = Field(default=0.0, ge=-1.0, le=1.0, description="布林带做多阈值")
    bb_short_threshold: float = Field(default=1.0, ge=-1.0, le=2.0, description="布林带做空阈值")
    # MACD 参数
    macd_fast: int = Field(default=12, ge=1, le=200, description="MACD 快线周期")
    macd_slow: int = Field(default=26, ge=1, le=500, description="MACD 慢线周期")
    macd_signal: int = Field(default=9, ge=1, le=100, description="MACD 信号线周期")
    # 账户参数
    total_amount_quote: float = Field(
        ..., gt=0, le=10000000,
        description="测试网账户总资金（USDT）"
    )
    # ── 杠杆与持仓 ──────────────────────────────────────────────
    leverage: int = Field(default=1, ge=1, le=125, description="杠杆倍数")
    position_mode: TestnetPositionMode = Field(default=TestnetPositionMode.ONEWAY, description="持仓模式")
    # ── 风控参数（Hummingbot schema 中对应 stop_loss/take_profit）─────────
    stop_loss_pct: float = Field(
        default=3.0, ge=0.0, le=50.0,
        description="止损百分比（Hummingbot 传入 stop_loss = stop_loss_pct / 100）"
    )
    take_profit_pct: float = Field(
        default=5.0, ge=0.0, le=100.0,
        description="止盈百分比（Hummingbot 传入 take_profit = take_profit_pct / 100）"
    )
    # ── 执行参数 ──────────────────────────────────────────────
    cooldown_minutes: int = Field(
        default=5, ge=1, le=1440,
        description="冷却时间（分钟），Hummingbot 传入 cooldown_time = cooldown_minutes * 60"
    )
    time_limit_minutes: int = Field(
        default=45, ge=1, le=10080,
        description="最大运行时间（分钟），Hummingbot 传入 time_limit = time_limit_minutes * 60"
    )
    max_executors_per_side: int = Field(
        default=1, ge=1, le=10,
        description="每侧最大 executors 数量"
    )

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
        return v

    @field_validator("connector")
    @classmethod
    def validate_connector(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in ALLOWED_TESTNET_CONNECTORS:
            raise ValueError(
                f"connector '{v}' 不在 Testnet 允许列表中。"
                f" 当前支持的 Testnet connector：{', '.join(sorted(ALLOWED_TESTNET_CONNECTORS))}。"
                " 请使用测试网 connector（如 binance_perpetual_testnet），不要使用主网或现货 connector。"
            )
        return v_lower

    @field_validator("credentials_profile")
    @classmethod
    def validate_credentials(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in ALLOWED_TESTNET_ACCOUNTS:
            raise ValueError(
                f"credentials_profile '{v}' 不在 Testnet 允许列表中。"
                f" 当前支持的：{', '.join(sorted(ALLOWED_TESTNET_ACCOUNTS))}。"
            )
        return v_lower


class TestnetBotStartRequest(TestnetBotPreviewRequest):
    """启动 Testnet Bot 的请求"""
    pass


# ── Response Schemas ─────────────────────────────────────────────────────────────

class TestnetControllerConfig(BaseModel):
    """生成的 Hummingbot Controller 配置（Preview 用）"""
    id: str
    controller_name: str
    controller_type: str = "directional_trading"
    connector_name: str
    trading_pair: str
    total_amount_quote: float
    leverage: int
    position_mode: str
    stop_loss: float = Field(description="stop_loss_pct / 100")
    take_profit: float = Field(description="take_profit_pct / 100")
    cooldown_time: int = Field(description="cooldown_minutes * 60（秒）")
    time_limit: int = Field(description="time_limit_minutes * 60（秒）")
    max_executors_per_side: int
    interval: str
    bb_length: int = 100
    bb_std: float = 2.0
    bb_long_threshold: float = 0.0
    bb_short_threshold: float = 1.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


class TestnetBotPreviewData(BaseModel):
    """Preview 响应数据"""
    controller_config: TestnetControllerConfig
    warnings: List[str]


class TestnetBotPreviewResponse(BaseModel):
    """Preview 响应"""
    valid: bool
    source: str = "quantagent"
    mode: str = "testnet"
    market_type: str = "perpetual"
    uses_real_exchange_account: bool = False
    requires_api_key: bool = True
    live_trading: bool = False
    testnet: bool = True
    data: Optional[TestnetBotPreviewData] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class TestnetBotStartData(BaseModel):
    """启动响应数据"""
    testnet_bot_id: str
    bot_name: str
    connector: str
    credentials_profile: str
    controller_name: str
    trading_pair: str
    local_status: str = Field(description="submitted=已提交, start_failed=失败")
    remote_confirmed: bool
    local_record_created: bool
    remote_started: bool
    hummingbot_bot_id: Optional[str] = None
    started_at: str
    config: Optional[Dict[str, Any]] = None
    hummingbot_response: Optional[Dict[str, Any]] = None


class TestnetBotStartResponse(BaseModel):
    """启动响应"""
    local_record_created: bool
    remote_started: bool
    remote_confirmed: bool
    source: str = "quantagent"
    mode: str = "testnet"
    market_type: str = "perpetual"
    uses_real_exchange_account: bool = False
    requires_api_key: bool = True
    live_trading: bool = False
    testnet: bool = True
    data: Optional[TestnetBotStartData] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class TestnetBotRecord(BaseModel):
    """Testnet Bot 记录"""
    testnet_bot_id: str
    bot_name: str
    connector: str
    credentials_profile: str
    controller_name: str
    trading_pair: str
    mode: str = "testnet"
    market_type: str = "perpetual"
    live_trading: bool = False
    testnet: bool = True
    uses_real_exchange_account: bool = False
    requires_api_key: bool = True
    local_status: str = "submitted"
    remote_status: str = "not_detected"
    matched_remote_bot: bool = False
    matched_by: str = "none"
    hummingbot_bot_id: Optional[str] = None
    can_fetch_runtime_data: bool = False
    started_at: Optional[str] = None
    runtime_seconds: int = 0
    config: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None


class TestnetBotReconciliationInfo(BaseModel):
    """对账信息"""
    local_status: str
    remote_status: str
    matched_remote_bot: bool
    matched_by: str
    hummingbot_bot_id: Optional[str] = None
    can_fetch_runtime_data: bool
    reconciliation_message: Optional[str] = None
    last_remote_check_at: Optional[str] = None
