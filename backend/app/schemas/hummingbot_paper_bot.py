"""
Hummingbot Paper Bot Schema Definitions

v1.2.x: 本地状态与远端状态分离
- local_status: QuantAgent 本地记录状态（created/submitted/starting/running/stopped/error）
- remote_status: Hummingbot 远端检测状态（running/not_detected/unknown/disconnected/unsupported）
- 对账: GET /paper-bots 会尝试用 Hummingbot API active_bots 匹配本地记录
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class StrategyType(str, Enum):
    """策略类型"""
    POSITION_EXECUTOR = "position_executor"
    GRID = "grid"


class TradingPair(str, Enum):
    """支持的交易对"""
    BTC_USDT = "BTC-USDT"
    ETH_USDT = "ETH-USDT"
    SOL_USDT = "SOL-USDT"


# ── Request Schemas ────────────────────────────────────────────────────────────

class PaperBotPreviewRequest(BaseModel):
    bot_name: str = Field(..., min_length=3, max_length=64)
    strategy_type: StrategyType = Field(...)
    trading_pair: str = Field(...)
    paper_initial_balance: float = Field(..., gt=0, le=1000000)
    order_amount: float = Field(..., gt=0)
    max_runtime_minutes: int = Field(..., ge=1, le=10080)
    spread_pct: Optional[float] = Field(None, ge=0, le=20)
    grid_spacing_pct: Optional[float] = Field(None, ge=0.01, le=20)
    grid_levels: Optional[int] = Field(20, ge=2, le=200)
    stop_loss_pct: Optional[float] = Field(0, ge=0, le=50)
    take_profit_pct: Optional[float] = Field(0, ge=0, le=100)

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


# ── Response Schemas ───────────────────────────────────────────────────────────

class RiskConfig(BaseModel):
    stop_loss_pct: float
    take_profit_pct: float
    max_runtime_minutes: int


class ConfigPreview(BaseModel):
    bot_name: str
    mode: str = "paper"
    live_trading: bool = False
    testnet: bool = False
    uses_real_exchange_account: bool = False
    requires_api_key: bool = False
    strategy_type: str
    trading_pair: str
    paper_initial_balance: float
    order_amount: float
    risk: RiskConfig
    strategy_params: Dict[str, Any]
    notes: List[str]


class PaperBotPreviewData(BaseModel):
    config_preview: ConfigPreview
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
    strategy_type: str
    trading_pair: str
    local_status: str = Field(
        description=(
            "本地状态: created=已创建本地记录, submitted=已提交到 Hummingbot API, "
            "starting=正在启动, running=远端已确认运行, stopped=已停止, error=错误"
        )
    )
    remote_confirmed: bool = Field(
        description="Hummingbot API 是否已确认该 Bot 真正运行"
    )
    hummingbot_bot_id: Optional[str] = Field(
        None,
        description="Hummingbot API 返回的 Bot ID（如果有）"
    )
    started_at: str
    config: Optional[Dict[str, Any]] = None
    hummingbot_response: Optional[Dict[str, Any]] = None


class PaperBotStartResponse(BaseModel):
    """
    Paper Bot 启动响应

    关键设计：
    - submitted: 是否已提交到 Hummingbot API（不等于 running）
    - remote_confirmed: Hummingbot API 是否已确认 Bot 在运行
    - 如果 remote_confirmed=False，说明只是本地记录，远端未确认
    """
    submitted: bool = Field(
        description="是否已提交到 Hummingbot API（但不一定成功运行）"
    )
    remote_confirmed: bool = Field(
        description="Hummingbot API 是否确认该 Bot 已真正运行"
    )
    source: str = "quantagent"
    mode: str = "paper"
    live_trading: bool = False
    testnet: bool = False
    data: Optional[PaperBotStartData] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ── Paper Bot 列表/详情中的状态字段 ────────────────────────────────────────────

class PaperBotReconciliationInfo(BaseModel):
    """对账信息：本地状态与远端检测结果的对比"""
    local_status: str = Field(
        description="QuantAgent 本地状态: created/submitted/starting/running/stopped/error"
    )
    remote_status: str = Field(
        description="远端检测状态: running/not_detected/unknown/disconnected/unsupported"
    )
    matched_remote_bot: bool = Field(
        description="Hummingbot API active_bots 中是否找到了这个 Bot"
    )
    matched_by: str = Field(
        description="匹配方式: active_bots/docker/bot_api/none"
    )
    hummingbot_bot_id: Optional[str] = Field(
        None,
        description="Hummingbot API 中的 Bot ID"
    )
    last_remote_check_at: Optional[str] = Field(
        None,
        description="最后一次远端检测时间"
    )
    last_error: Optional[str] = Field(
        None,
        description="最近的错误信息"
    )


class PaperBotRecord(BaseModel):
    """Paper Bot 完整记录"""
    paper_bot_id: str
    bot_name: str
    strategy_type: str
    trading_pair: str
    mode: str = "paper"
    live_trading: bool = False
    testnet: bool = False
    # 状态字段
    local_status: str = "created"
    remote_status: str = "not_detected"
    # 对账信息
    matched_remote_bot: bool = False
    matched_by: str = "none"
    hummingbot_bot_id: Optional[str] = None
    last_remote_check_at: Optional[str] = None
    last_error: Optional[str] = None
    # 时间
    created_at: str
    started_at: Optional[str] = None
    runtime_seconds: int = 0
    # 配置
    config: Optional[Dict[str, Any]] = None
    hummingbot_status_raw: Optional[Dict[str, Any]] = None
