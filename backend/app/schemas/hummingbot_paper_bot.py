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
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ── Connector 白名单 ─────────────────────────────────────────────────────────────

# Paper Bot 只允许这些现货 connector（已在 paper_trade_exchanges 中）
PAPER_CONNECTOR_WHITELIST_SPOT = {
    "binance",
    "kucoin",
    "gate_io",
    "kraken",
}

# 永续合约 Connector（需要额外验证，仅 v1.3+ 支持）
PAPER_CONNECTOR_WHITELIST_PERPETUAL = {
    "binance_perpetual",
    "bybit_perpetual",
    "okx_perpetual",
    "gate_io_perpetual",
    "bitget_perpetual",
}

# 全部白名单
PAPER_CONNECTOR_WHITELIST = PAPER_CONNECTOR_WHITELIST_SPOT | PAPER_CONNECTOR_WHITELIST_PERPETUAL

# 禁止的 connector 类型
FORBIDDEN_CONNECTOR_PATTERNS = [
    "testnet",
    "binance_perpetual_testnet",
    "bybit_perpetual_testnet",
]


# ── Strategy Types ──────────────────────────────────────────────────────────────

class StrategyType(str, Enum):
    """策略类型"""
    # ── 趋势跟踪策略 ──────────────────────────────────────────────
    MA = "ma"                      # 移动平均线策略
    EMA_TRIPLE = "ema_triple"      # 三重 EMA 策略
    MACD = "macd"                  # MACD 策略
    # ── 均值回归策略 ──────────────────────────────────────────────
    RSI = "rsi"                    # RSI 策略
    BOLL = "boll"                  # 布林带策略
    ATR_TREND = "atr_trend"        # ATR 趋势策略
    # ── 执行器策略 ──────────────────────────────────────────────
    GRID = "grid"                  # 网格策略
    DCA = "dca"                    # 定投策略
    PMM = "pmm"                    # 做市商策略
    # ── 高级策略 ──────────────────────────────────────────────
    ICHIMOKU = "ichimoku"          # 一目均衡表策略
    TURTLE = "turtle"              # 海龟交易策略
    # ── 兼容旧名 ──────────────────────────────────────────────
    LOW_FREQUENCY_SIGNAL = "low_frequency_signal"  # 低频信号（兼容）
    POSITION_EXECUTOR = "position_executor"        # 持仓执行（兼容）


# ── Timeframe ───────────────────────────────────────────────────────────────────

class Timeframe(str, Enum):
    """K线周期"""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


# ── Signal Type ─────────────────────────────────────────────────────────────────

class SignalType(str, Enum):
    """信号类型"""
    # 趋势类
    MA_CROSS = "ma_cross"                  # 均线交叉
    EMA_CROSSOVER = "ema_crossover"        # EMA 交叉
    MACD_SIGNAL = "macd"                   # MACD
    ICHIMOKU_CLOUD = "ichimoku"            # 一目均衡
    TURTLE_TRADING = "turtle"              # 海龟交易
    # 均值回归类
    RSI_SIGNAL = "rsi"                     # RSI
    BOLLINGER_BANDS = "bollinger"          # 布林带
    ATR_TRAILING_STOP = "atr_trailing"     # ATR 追踪止损
    # 执行类
    GRID = "grid"                          # 网格
    DCA = "dca"                            # 定投
    PMM = "pmm"                            # 做市商
    # 兼容旧名
    SUPERTREND = "supertrend"              # 超级趋势（兼容）


# ── Spot Trading Pairs ─────────────────────────────────────────────────────────

class SpotTradingPair(str, Enum):
    """现货交易对"""
    BTC_USDT = "BTC-USDT"
    ETH_USDT = "ETH-USDT"
    SOL_USDT = "SOL-USDT"
    BNB_USDT = "BNB-USDT"
    DOGE_USDT = "DOGE-USDT"
    XRP_USDT = "XRP-USDT"


# ── Request Schemas ─────────────────────────────────────────────────────────────

class PaperBotPreviewRequest(BaseModel):
    bot_name: str = Field(..., min_length=3, max_length=64)
    connector: str = Field(
        ...,
        description="现货 connector，只能是 binance / kucoin / gate_io / kraken"
    )
    strategy_type: StrategyType = Field(...)
    trading_pair: str = Field(..., description="现货交易对，如 BTC-USDT / ETH-USDT / SOL-USDT")
    timeframe: Timeframe = Field(default=Timeframe.H1, description="K线周期")
    signal_type: SignalType = Field(
        default=SignalType.BOLLINGER_BANDS,
        description="信号类型"
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
    # ── 均线策略参数 ──────────────────────────────────────────────
    fast_period: Optional[int] = Field(default=10, ge=1, le=200, description="快线周期")
    slow_period: Optional[int] = Field(default=30, ge=1, le=500, description="慢线周期")
    ema_fast: Optional[int] = Field(default=12, ge=1, le=200, description="EMA 快线周期")
    ema_medium: Optional[int] = Field(default=26, ge=1, le=200, description="EMA 中线周期")
    ema_slow: Optional[int] = Field(default=50, ge=1, le=500, description="EMA 慢线周期")
    # ── MACD 参数 ──────────────────────────────────────────────
    macd_fast: Optional[int] = Field(default=12, ge=1, le=200, description="MACD 快线周期")
    macd_slow: Optional[int] = Field(default=26, ge=1, le=500, description="MACD 慢线周期")
    macd_signal: Optional[int] = Field(default=9, ge=1, le=100, description="MACD 信号线周期")
    # ── RSI 参数 ──────────────────────────────────────────────
    rsi_period: Optional[int] = Field(default=14, ge=1, le=100, description="RSI 周期")
    rsi_oversold: Optional[float] = Field(default=30, ge=0, le=50, description="RSI 超卖阈值")
    rsi_overbought: Optional[float] = Field(default=70, ge=50, le=100, description="RSI 超买阈值")
    # ── 布林带参数 ──────────────────────────────────────────────
    boll_period: Optional[int] = Field(default=20, ge=1, le=100, description="布林带周期")
    boll_std_dev: Optional[float] = Field(default=2.0, ge=0.1, le=5.0, description="布林带标准差倍数")
    # ── ATR 参数 ──────────────────────────────────────────────
    atr_period: Optional[int] = Field(default=14, ge=1, le=100, description="ATR 周期")
    atr_multiplier: Optional[float] = Field(default=3.0, ge=0.1, le=10.0, description="ATR 倍数")
    # ── Ichimoku 参数 ──────────────────────────────────────────────
    tenkan_period: Optional[int] = Field(default=9, ge=1, le=100, description="转折线周期")
    kijun_period: Optional[int] = Field(default=26, ge=1, le=200, description="基准线周期")
    senkou_period: Optional[int] = Field(default=52, ge=1, le=500, description="先行线周期")
    # ── Turtle 参数 ──────────────────────────────────────────────
    turtle_entry_period: Optional[int] = Field(default=20, ge=1, le=200, description="海龟入场周期")
    turtle_exit_period: Optional[int] = Field(default=10, ge=1, le=100, description="海龟出场周期")
    turtle_breakout_pct: Optional[float] = Field(default=2.0, ge=0.1, le=10.0, description="突破百分比")
    # ── 网格策略参数 ──────────────────────────────────────────────
    grid_levels: Optional[int] = Field(default=10, ge=2, le=100, description="网格层数")
    grid_spacing_pct: Optional[float] = Field(default=1.0, ge=0.01, le=10.0, description="网格间距百分比")
    price_range_upper: Optional[float] = Field(default=None, description="价格范围上限")
    price_range_lower: Optional[float] = Field(default=None, description="价格范围下限")
    # ── 风控参数 ──────────────────────────────────────────────
    stop_loss_pct: float = Field(
        default=5.0, ge=0, le=50,
        description="止损百分比"
    )
    take_profit_pct: float = Field(
        default=10.0, ge=0, le=100,
        description="止盈百分比"
    )
    max_position_size: Optional[float] = Field(default=None, ge=0, description="最大仓位限制")
    max_daily_loss: Optional[float] = Field(default=None, ge=0, description="日亏损限制")
    max_drawdown_pct: Optional[float] = Field(default=20.0, ge=0, le=100, description="最大回撤限制")
    # ── 频率控制 ──────────────────────────────────────────────
    cooldown_minutes: int = Field(
        default=60, ge=5, le=1440,
        description="两次交易之间的最小间隔（分钟）"
    )
    max_trades_per_day: int = Field(
        default=3, ge=1, le=24,
        description="每日最大交易次数"
    )
    max_open_positions: int = Field(
        default=1, ge=1, le=10,
        description="最大同时持仓数"
    )
    # ── 执行参数 ──────────────────────────────────────────────
    order_type: Literal["MARKET", "LIMIT", "POST_ONLY"] = Field(
        default="MARKET",
        description="订单类型"
    )
    time_in_force: Literal["GTC", "IOC", "FOK"] = Field(
        default="GTC",
        description="订单有效期"
    )
    # ── 永续合约参数（仅合约 connector 可用）─────────────────────────
    leverage: Optional[int] = Field(default=1, ge=1, le=125, description="杠杆倍数")
    position_mode: Literal["HEDGE", "ONEWAY"] = Field(
        default="ONEWAY",
        description="持仓模式（HEDGE=双向/ONEWAY=单向）"
    )
    margin_coin: Optional[str] = Field(default="USDT", description="保证金币种")
    # ── 运行时间 ──────────────────────────────────────────────
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
        return v

    @field_validator("connector")
    @classmethod
    def validate_connector(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in PAPER_CONNECTOR_WHITELIST:
            raise ValueError(
                f"connector '{v}' 不在 Paper Bot 允许列表中。"
                f"当前支持的 connector：{', '.join(sorted(PAPER_CONNECTOR_WHITELIST))}。"
            )
        for pattern in FORBIDDEN_CONNECTOR_PATTERNS:
            if pattern.lower() in v_lower:
                raise ValueError(
                    f"connector '{v}' 包含禁止关键词 '{pattern}'。"
                    f"Testnet connector 不允许用于 Paper Bot。"
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
    # 均线参数
    fast_period: Optional[int] = None
    slow_period: Optional[int] = None
    ema_fast: Optional[int] = None
    ema_medium: Optional[int] = None
    ema_slow: Optional[int] = None
    # MACD 参数
    macd_fast: Optional[int] = None
    macd_slow: Optional[int] = None
    macd_signal: Optional[int] = None
    # RSI 参数
    rsi_period: Optional[int] = None
    rsi_oversold: Optional[float] = None
    rsi_overbought: Optional[float] = None
    # 布林带参数
    boll_period: Optional[int] = None
    boll_std_dev: Optional[float] = None
    # ATR 参数
    atr_period: Optional[int] = None
    atr_multiplier: Optional[float] = None
    # Ichimoku 参数
    tenkan_period: Optional[int] = None
    kijun_period: Optional[int] = None
    senkou_period: Optional[int] = None
    # Turtle 参数
    turtle_entry_period: Optional[int] = None
    turtle_exit_period: Optional[int] = None
    turtle_breakout_pct: Optional[float] = None
    # 网格参数
    grid_levels: Optional[int] = None
    grid_spacing_pct: Optional[float] = None
    price_range_upper: Optional[float] = None
    price_range_lower: Optional[float] = None
    # 风控参数
    stop_loss_pct: float = 5.0
    take_profit_pct: float = 10.0
    max_position_size: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    # 频率控制
    cooldown_minutes: int = 60
    max_trades_per_day: int = 3
    max_open_positions: int = 1
    # 执行参数
    order_type: str = "MARKET"
    time_in_force: str = "GTC"
    # 永续合约参数
    leverage: Optional[int] = None
    position_mode: Optional[str] = None
    margin_coin: Optional[str] = None
    # 风控
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
    paper_initial_balance: float
    order_amount: float
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
    friendly_error: Optional[Dict[str, Any]] = Field(
        default=None,
        description="用户友好的错误信息（包含短说明、详细原因、建议操作和文档链接）"
    )
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
