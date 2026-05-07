"""
Hummingbot Paper Bot Schema Definitions

v1.2.1 阶段：仅用于配置预览，不启动 Bot，不执行真实交易。
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
    """
    Paper Bot 配置预览请求

    必填字段全部校验通过后，生成一份标准化 config_preview JSON。
    本接口不调用 Hummingbot API，不启动 Bot。
    """

    # 必填字段
    bot_name: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Bot 名称，3-64字符，只能包含字母、数字、下划线、中划线"
    )
    strategy_type: StrategyType = Field(
        ...,
        description="策略类型：position_executor 或 grid"
    )
    trading_pair: str = Field(
        ...,
        description="交易对，如 BTC-USDT、ETH-USDT、SOL-USDT"
    )
    paper_initial_balance: float = Field(
        ...,
        gt=0,
        le=1000000,
        description="Paper 初始资金，0-1000000"
    )
    order_amount: float = Field(
        ...,
        gt=0,
        description="单笔订单金额，必须 > 0"
    )
    max_runtime_minutes: int = Field(
        ...,
        ge=1,
        le=10080,
        description="最大运行时间，1-10080 分钟（10080=7天）"
    )

    # 可选字段
    spread_pct: Optional[float] = Field(
        None,
        ge=0,
        le=20,
        description="价差百分比，仅 position_executor 使用，0-20%"
    )
    grid_spacing_pct: Optional[float] = Field(
        None,
        ge=0.01,
        le=20,
        description="网格间距百分比，仅 grid 使用，0.01-20%"
    )
    grid_levels: Optional[int] = Field(
        20,
        ge=2,
        le=200,
        description="网格层数，仅 grid 使用，2-200"
    )
    stop_loss_pct: Optional[float] = Field(
        0,
        ge=0,
        le=50,
        description="止损比例，0-50%，0 表示不启用"
    )
    take_profit_pct: Optional[float] = Field(
        0,
        ge=0,
        le=100,
        description="止盈比例，0-100%，0 表示不启用"
    )

    @field_validator("bot_name")
    @classmethod
    def validate_bot_name(cls, v: str) -> str:
        """校验 bot_name 格式"""
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError(
                "bot_name 只能包含字母、数字、下划线和中划线，不能包含空格和中文标点"
            )
        return v

    @field_validator("trading_pair")
    @classmethod
    def validate_trading_pair(cls, v: str) -> str:
        """校验交易对格式"""
        import re
        # 只允许大写字母、数字、中划线
        if not re.match(r'^[A-Z0-9-]+$', v):
            raise ValueError("trading_pair 只能包含大写字母、数字和中划线，请使用 BTC-USDT 格式，不要使用斜杠")
        # 检查是否为支持的值
        valid_pairs = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNBUSDT", "DOGEUSDT"]
        if v not in valid_pairs:
            # 允许但给出警告
            pass
        return v

    @field_validator("order_amount")
    @classmethod
    def validate_order_amount(cls, v: float, info) -> float:
        """校验 order_amount <= paper_initial_balance"""
        # 这里只能部分校验，完整校验在 service 层
        if v <= 0:
            raise ValueError("order_amount 必须大于 0")
        return v


# ── Response Schemas ───────────────────────────────────────────────────────────

class RiskConfig(BaseModel):
    """风险配置"""
    stop_loss_pct: float = Field(description="止损比例 %")
    take_profit_pct: float = Field(description="止盈比例 %")
    max_runtime_minutes: int = Field(description="最大运行时间（分钟）")


class StrategyParams(BaseModel):
    """策略参数"""
    pass  # 动态填充


class ConfigPreview(BaseModel):
    """配置预览"""
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


class WarningsData(BaseModel):
    """警告信息"""
    warnings: List[str]


class PaperBotPreviewData(BaseModel):
    """预览数据"""
    config_preview: ConfigPreview
    warnings: List[str]


class PaperBotPreviewResponse(BaseModel):
    """
    Paper Bot 配置预览响应

    统一响应格式：
    - valid: 是否校验通过
    - source: 数据来源
    - mode: 固定为 paper
    - live_trading: 固定为 false
    - testnet: 固定为 false
    - data: 预览数据或 null
    - error: 错误信息或 null
    - timestamp: 时间戳
    """
    valid: bool
    source: str = "quantagent"
    mode: str = "paper"
    live_trading: bool = False
    testnet: bool = False
    data: Optional[PaperBotPreviewData] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    class Config:
        json_schema_extra = {
            "example_success": {
                "valid": True,
                "source": "quantagent",
                "mode": "paper",
                "live_trading": False,
                "testnet": False,
                "data": {
                    "config_preview": {
                        "bot_name": "paper_grid_btc_001",
                        "mode": "paper",
                        "live_trading": False,
                        "testnet": False,
                        "uses_real_exchange_account": False,
                        "requires_api_key": False,
                        "strategy_type": "grid",
                        "trading_pair": "BTC-USDT",
                        "paper_initial_balance": 10000,
                        "order_amount": 100,
                        "risk": {
                            "stop_loss_pct": 3,
                            "take_profit_pct": 5,
                            "max_runtime_minutes": 120
                        },
                        "strategy_params": {
                            "grid_spacing_pct": 0.5,
                            "grid_levels": 20
                        },
                        "notes": [
                            "当前配置仅用于 Paper Bot 预览。",
                            "不会启动 Bot。",
                            "不会执行真实交易。",
                            "不会使用真实交易所 API Key。"
                        ]
                    },
                    "warnings": [
                        "当前仅生成配置预览，尚未调用 Hummingbot API 启动 Bot。"
                    ]
                },
                "error": None,
                "timestamp": "2026-05-07T12:00:00Z"
            },
            "example_error": {
                "valid": False,
                "source": "quantagent",
                "mode": "paper",
                "live_trading": False,
                "testnet": False,
                "data": None,
                "error": "order_amount 不能大于 paper_initial_balance",
                "timestamp": "2026-05-07T12:00:00Z"
            }
        }


# ── Paper Bot Start Response Schemas ─────────────────────────────────────────

class PaperBotStartData(BaseModel):
    """Paper Bot 启动数据"""
    paper_bot_id: str = Field(description="Paper Bot 唯一标识")
    bot_name: str = Field(description="Bot 名称")
    strategy_type: str = Field(description="策略类型")
    trading_pair: str = Field(description="交易对")
    status: str = Field(description="Bot 状态: starting, running, stopped")
    started_at: str = Field(description="启动时间 ISO 格式")
    hummingbot_response: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Hummingbot API 原始响应"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="使用的配置（不含敏感信息）"
    )


class PaperBotStartResponse(BaseModel):
    """
    Paper Bot 启动响应

    统一响应格式：
    - started: 是否启动成功
    - source: 数据来源
    - mode: 固定为 paper
    - live_trading: 固定为 false
    - testnet: 固定为 false
    - data: 启动数据或 null
    - error: 错误信息或 null
    - timestamp: 时间戳
    """
    started: bool
    source: str = "hummingbot-api"
    mode: str = "paper"
    live_trading: bool = False
    testnet: bool = False
    data: Optional[PaperBotStartData] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    class Config:
        json_schema_extra = {
            "example_success": {
                "started": True,
                "source": "hummingbot-api",
                "mode": "paper",
                "live_trading": False,
                "testnet": False,
                "data": {
                    "paper_bot_id": "paper_paper_grid_btc_001_a1b2c3d4",
                    "bot_name": "paper_grid_btc_001",
                    "strategy_type": "grid",
                    "trading_pair": "BTC-USDT",
                    "status": "starting",
                    "started_at": "2026-05-07T12:00:00Z",
                    "hummingbot_response": {},
                    "config": {
                        "mode": "paper",
                        "live_trading": False
                    }
                },
                "error": None,
                "timestamp": "2026-05-07T12:00:00Z"
            },
            "example_error": {
                "started": False,
                "source": "quantagent",
                "mode": "paper",
                "live_trading": False,
                "testnet": False,
                "data": None,
                "error": "当前 Hummingbot API 版本未提供可用的 Paper Bot 启动接口",
                "timestamp": "2026-05-07T12:00:00Z"
            }
        }
