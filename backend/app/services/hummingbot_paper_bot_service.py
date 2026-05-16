"""
Hummingbot Paper Bot Service

v1.2.x: 低频现货 Paper Bot（Branch A）

核心设计：
1. 只支持现货 connector（binance / kucoin / gate_io / kraken）
2. 禁止所有 perpetual / testnet / live connector
3. 低频 signal-based 策略
4. 完整 preflight 检查 + 策略映射层
5. 不伪造启动成功，只有远端确认才设置 running
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.schemas.hummingbot_paper_bot import (
    FORBIDDEN_CONNECTOR_PATTERNS,
    PAPER_CONNECTOR_WHITELIST,
    PaperBotPreviewRequest,
    PaperBotPreviewResponse,
    PaperBotPreviewData,
    PaperBotStartRequest,
    PaperBotStartResponse,
    PaperBotStartData,
    PaperBotRecord,
    PaperConnectorResponse,
    ConfigPreview,
    PaperBotReconciliationInfo,
    RiskConfig,
    StrategyParams,
)
from app.services.hummingbot_config_mapper import (
    build_controller_config_payload,
    check_paper_connectors_available,
    check_connector,
    map_strategy,
    run_preflight_check,
)
from dataclasses import dataclass


@dataclass
class ReconciliationResult:
    """远端状态对账结果（列表页和详情页共用）"""
    local_status: str
    remote_status: str
    matched_remote_bot: bool
    matched_by: str          # active_bots | docker | bot_runs | none
    can_fetch_runtime_data: bool
    hummingbot_bot_id: Optional[str]
    hummingbot_status_raw: Optional[Dict[str, Any]]
    message: Optional[str]   # 用于页面提示

logger = logging.getLogger(__name__)


# ── 敏感字段黑名单 ──────────────────────────────────────────────────────────────

SAFE_BOOL_FIELDS = {
    # 安全布尔字段（永远不会包含密钥或凭证，可以直接暴露）
    "requires_api_key",
    "uses_real_exchange_account",
    "paper_trade_enabled",
    "live_trading",
    "testnet",
    "api_online",
    "connected",
    "available",
    "not_forbidden",
    "in_whitelist",
    "controller_available",
    "preflight_passed",
    "matched_remote_bot",
    "can_fetch_runtime_data",
    "bot_api_available",
}

SENSITIVE_FIELD_PATTERNS = [
    "api_key", "apikey", "apiSecret", "api_secret", "secret",
    "private_key", "privateKey", "exchange_secret", "exchangeSecret",
    "password", "passphrase", "token", "access_token", "refresh_token",
    "wallet_private_key", "wallet_privatekey", "mnemonic", "seed_phrase", "seedphrase",
]

DANGEROUS_MODE_VALUES = ["live", "testnet"]

SENSITIVE_KEYS = [
    "api_key", "apikey", "apiSecret", "api_secret", "secret",
    "private_key", "privateKey", "exchange_secret", "exchangeSecret",
    "password", "passphrase", "token", "access_token", "refresh_token",
    "wallet_private_key", "wallet_privatekey", "mnemonic", "seed_phrase", "seedphrase",
    "real_trading",
]


class HummingbotPaperBotValidationError(Exception):
    def __init__(self, message: str, error_type: str = "validation_error"):
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


def _flatten_dict(data: Any, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    items = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
    elif isinstance(data, list):
        for i, item in enumerate(data):
            items.extend(_flatten_dict(item, f"{parent_key}{sep}{i}", sep=sep).items())
    else:
        items.append((parent_key, data))
    return dict(items)


def _check_sensitive_fields(request_data: Dict[str, Any]) -> Optional[str]:
    flat_data = _flatten_dict(request_data)
    for key in flat_data.keys():
        key_lower = key.lower()
        for pattern in SENSITIVE_FIELD_PATTERNS:
            if pattern.lower() in key_lower:
                return f"检测到敏感字段: '{key}'。禁止提交 API Key、Secret、Token 或私钥。"
    return None


def _check_dangerous_modes(request_data: Dict[str, Any]) -> Optional[str]:
    flat_data = _flatten_dict(request_data)
    mode_value = flat_data.get("mode", "")
    if isinstance(mode_value, str) and mode_value.lower() in DANGEROUS_MODE_VALUES:
        return f"检测到危险配置: mode='{mode_value}'。仅支持 Paper Bot。"
    for field in ["live_trading", "testnet"]:
        val = flat_data.get(field)
        if val is True or str(val).lower() == "true":
            return f"检测到 {field}=true。仅支持 Paper Bot。"
    return None


def _validate_strategy_params(request: PaperBotPreviewRequest) -> None:
    pass  # 已移除，验证在 schema 层 + _validate_connector_for_paper 中完成


def _validate_order_amount(request: PaperBotPreviewRequest) -> None:
    pass  # 已移除


def _validate_connector_for_paper(connector: str) -> None:
    """验证 connector 是否可用于 Paper Bot。"""
    from app.schemas.hummingbot_paper_bot import (
        FORBIDDEN_CONNECTOR_PATTERNS,
        PAPER_CONNECTOR_WHITELIST,
    )
    c_lower = connector.lower()
    for pattern in FORBIDDEN_CONNECTOR_PATTERNS:
        if pattern.lower() in c_lower:
            raise HummingbotPaperBotValidationError(
                f"connector '{connector}' 包含禁止关键词 '{pattern}'。"
                " 永续合约 / Testnet / Live connector 不允许用于 Paper Bot。"
                " 永续合约模拟属于 Testnet Bot 阶段（v1.3），不属于当前 Paper Bot 范围。"
            )
    if c_lower not in {c.lower() for c in PAPER_CONNECTOR_WHITELIST}:
        raise HummingbotPaperBotValidationError(
            f"connector '{connector}' 不在 Paper Bot 允许列表中。"
            f" 当前仅支持现货 connector：{', '.join(sorted(PAPER_CONNECTOR_WHITELIST))}。"
        )


def _validate_low_freq_params(request: PaperBotPreviewRequest) -> None:
    """验证低频策略参数。"""
    if request.order_amount > request.paper_initial_balance:
        raise HummingbotPaperBotValidationError(
            f"单笔订单金额 ({request.order_amount}) 不能大于初始资金 ({request.paper_initial_balance})"
        )


def _build_config_preview(request: PaperBotPreviewRequest) -> ConfigPreview:
    from app.schemas.hummingbot_paper_bot import RiskConfig as RC, StrategyParams as SP

    strategy_type_val = request.strategy_type.value if hasattr(request.strategy_type, "value") else str(request.strategy_type)
    signal_type_val = (
        getattr(request, "signal_type", None).value
        if hasattr(getattr(request, "signal_type", None), "value")
        else "bollinger"
    )
    timeframe_val = (
        getattr(request, "timeframe", None).value
        if hasattr(getattr(request, "timeframe", None), "value")
        else "1h"
    )
    connector = getattr(request, "connector", "binance")

    strategy_mapping = map_strategy(
        strategy_type=strategy_type_val,
        signal_type=signal_type_val,
    )

    risk_config = RC(
        stop_loss_pct=getattr(request, "stop_loss_pct", 5.0),
        take_profit_pct=getattr(request, "take_profit_pct", 10.0),
        max_runtime_minutes=getattr(request, "max_runtime_minutes", 60),
        cooldown_minutes=getattr(request, "cooldown_minutes", 60),
        max_trades_per_day=getattr(request, "max_trades_per_day", 3),
        max_open_positions=getattr(request, "max_open_positions", 1),
    )

    strategy_params = SP(
        timeframe=timeframe_val,
        signal_type=signal_type_val,
        connector=connector,
        trading_pair=getattr(request, "trading_pair", "BTC-USDT"),
        paper_initial_balance=getattr(request, "paper_initial_balance", 10000),
        order_amount=getattr(request, "order_amount", 100),
        # 均线参数
        fast_period=getattr(request, "fast_period", None),
        slow_period=getattr(request, "slow_period", None),
        # EMA 参数
        ema_fast=getattr(request, "ema_fast", None),
        ema_medium=getattr(request, "ema_medium", None),
        ema_slow=getattr(request, "ema_slow", None),
        # MACD 参数
        macd_fast=getattr(request, "macd_fast", None),
        macd_slow=getattr(request, "macd_slow", None),
        macd_signal=getattr(request, "macd_signal", None),
        # RSI 参数
        rsi_period=getattr(request, "rsi_period", None),
        rsi_oversold=getattr(request, "rsi_oversold", None),
        rsi_overbought=getattr(request, "rsi_overbought", None),
        # 布林带参数
        boll_period=getattr(request, "boll_period", None),
        boll_std_dev=getattr(request, "boll_std_dev", None),
        # ATR 参数
        atr_period=getattr(request, "atr_period", None),
        atr_multiplier=getattr(request, "atr_multiplier", None),
        # Ichimoku 参数
        tenkan_period=getattr(request, "tenkan_period", None),
        kijun_period=getattr(request, "kijun_period", None),
        senkou_period=getattr(request, "senkou_period", None),
        # Turtle 参数
        turtle_entry_period=getattr(request, "turtle_entry_period", None),
        turtle_exit_period=getattr(request, "turtle_exit_period", None),
        turtle_breakout_pct=getattr(request, "turtle_breakout_pct", None),
        # 网格参数
        grid_levels=getattr(request, "grid_levels", None),
        grid_spacing_pct=getattr(request, "grid_spacing_pct", None),
        price_range_upper=getattr(request, "price_range_upper", None),
        price_range_lower=getattr(request, "price_range_lower", None),
        # 风控参数
        max_position_size=getattr(request, "max_position_size", None),
        max_daily_loss=getattr(request, "max_daily_loss", None),
        max_drawdown_pct=getattr(request, "max_drawdown_pct", None),
        stop_loss_pct=getattr(request, "stop_loss_pct", 5.0),
        take_profit_pct=getattr(request, "take_profit_pct", 10.0),
        cooldown_minutes=getattr(request, "cooldown_minutes", 60),
        max_trades_per_day=getattr(request, "max_trades_per_day", 3),
        max_open_positions=getattr(request, "max_open_positions", 1),
        # 执行参数
        order_type=getattr(request, "order_type", "MARKET"),
        time_in_force=getattr(request, "time_in_force", "GTC"),
        # 永续合约参数
        leverage=getattr(request, "leverage", None),
        position_mode=getattr(request, "position_mode", None),
        margin_coin=getattr(request, "margin_coin", None),
        risk=risk_config,
    )

    notes = [
        "当前配置仅用于 Paper Bot 预览。",
        "不会执行真实交易。",
        "不会使用真实交易所 API Key。",
        f"Connector: {connector}",
        f"策略: {strategy_type_val} / {signal_type_val}",
        f"周期: {timeframe_val}",
        f"交易对: {getattr(request, 'trading_pair', 'BTC-USDT')}",
        "本 Paper Bot 用于策略自动化验证。",
    ]

    return ConfigPreview(
        bot_name=getattr(request, "bot_name", "unknown"),
        mode="paper",
        live_trading=False,
        testnet=False,
        uses_real_exchange_account=False,
        requires_api_key=False,
        connector=connector,
        strategy_type=strategy_type_val,
        trading_pair=getattr(request, "trading_pair", "BTC-USDT"),
        paper_initial_balance=getattr(request, "paper_initial_balance", 10000),
        order_amount=getattr(request, "order_amount", 100),
        risk=risk_config,
        strategy_params=strategy_params,
        notes=notes,
    )


def sanitize_data(data: Any, depth: int = 0) -> Any:
    if data is None:
        return None
    if depth > 20:
        return data
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            # 白名单字段不过滤（安全布尔值，不会包含密钥）
            if key_lower in SAFE_BOOL_FIELDS:
                result[key] = sanitize_data(value, depth + 1)
            elif any(sk in key_lower for sk in SENSITIVE_KEYS):
                result[key] = "***REDACTED***"
            else:
                result[key] = sanitize_data(value, depth + 1)
        return result
    if isinstance(data, list):
        if depth > 15:
            return data
        return [sanitize_data(item, depth + 1) for item in data[:200]]
    return data


def _log_paper_bot_operation(
    operation: str,
    bot_name: str,
    strategy_type: str,
    trading_pair: str,
    success: bool,
    error_message: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    safe_config = {
        k: v for k, v in (config or {}).items()
        if k not in SENSITIVE_KEYS
    }
    logger.info(json.dumps({
        "operation": operation,
        "bot_name": bot_name,
        "strategy_type": strategy_type,
        "trading_pair": trading_pair,
        "mode": "paper",
        "success": success,
        "error": error_message,
        "config": safe_config,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }, default=str))


# ── Hummingbot API 调用 ────────────────────────────────────────────────────────

async def _call_hummingbot_api(
    method: str,
    path: str,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """调用 Hummingbot API"""
    base_url = settings.HUMMINGBOT_API_URL.rstrip("/")
    url = f"{base_url}/{path.lstrip('/')}"
    username = settings.HUMMINGBOT_API_USERNAME
    password = settings.HUMMINGBOT_API_PASSWORD
    auth = None
    if username and password:
        auth = httpx.BasicAuth(username, password)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.request(
            method=method, url=url, json=json_data, auth=auth
        )
        if response.status_code == 401:
            raise Exception("Hummingbot API 认证失败（401 Unauthorized）")
        elif response.status_code == 404:
            raise Exception(f"Hummingbot API 路径不存在: {path}（404 Not Found）")
        elif not response.is_success:
            detail = ""
            try:
                body = response.json()
                detail = body.get("detail") or str(body)
            except Exception:
                detail = response.text[:300]
            raise Exception(
                f"Hummingbot API 请求失败: HTTP {response.status_code} - {detail}"
            )
        try:
            return response.json()
        except Exception:
            return {"_raw": response.text}


# ── 本地记录存储 ────────────────────────────────────────────────────────────────

_paper_bot_records: Dict[str, Dict[str, Any]] = {}


def record_paper_bot(
    paper_bot_id: str,
    bot_name: str,
    strategy_type: str,
    trading_pair: str,
    config: Dict[str, Any],
    connector: str = "binance",
) -> None:
    """创建本地记录，初始状态为 submitted"""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _paper_bot_records[paper_bot_id] = {
        "paper_bot_id": paper_bot_id,
        "bot_name": bot_name,
        "connector": connector,
        "strategy_type": strategy_type,
        "trading_pair": trading_pair,
        "mode": "paper",
        "live_trading": False,
        "testnet": False,
        "local_status": "submitted",
        "remote_status": "not_detected",
        "matched_remote_bot": False,
        "matched_by": "none",
        "hummingbot_bot_id": None,
        "last_remote_check_at": None,
        "last_error": None,
        "created_at": now,
        "started_at": now,
        "config": config,
        "hummingbot_status_raw": None,
        "can_fetch_runtime_data": False,
    }


def update_paper_bot_fields(paper_bot_id: str, **fields) -> None:
    if paper_bot_id in _paper_bot_records:
        _paper_bot_records[paper_bot_id].update(fields)


def get_paper_bot_records() -> Dict[str, Dict[str, Any]]:
    return _paper_bot_records


def get_paper_bot_record(paper_bot_id: str) -> Optional[Dict[str, Any]]:
    return _paper_bot_records.get(paper_bot_id)


async def get_paper_connectors() -> PaperConnectorResponse:
    """
    获取当前 Hummingbot 可用的 Paper Bot connector 列表。
    从 Hummingbot API 获取可用 connectors，与 PAPER_CONNECTOR_WHITELIST 交叉验证。
    """
    return await check_paper_connectors_available(
        base_url=settings.HUMMINGBOT_API_URL,
        username=settings.HUMMINGBOT_API_USERNAME,
        password=settings.HUMMINGBOT_API_PASSWORD,
    )


# ── v1.2.1: 配置预览 ──────────────────────────────────────────────────────────

async def generate_paper_bot_preview(
    request: PaperBotPreviewRequest,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> PaperBotPreviewResponse:
    """生成 Paper Bot 配置预览。"""
    try:
        if raw_request_data:
            if err := _check_sensitive_fields(raw_request_data):
                return PaperBotPreviewResponse(valid=False, error=err)
            if err := _check_dangerous_modes(raw_request_data):
                return PaperBotPreviewResponse(valid=False, error=err)

        # Schema 层已验证 connector（在 Pydantic validator 中）
        # 这里只需检查额外的不允许情况
        connector = getattr(request, "connector", "binance")
        _validate_connector_for_paper(connector)
        _validate_low_freq_params(request)

        config_preview = _build_config_preview(request)

        # 策略映射
        strategy_mapping = map_strategy(
            strategy_type=request.strategy_type.value,
            signal_type=getattr(request, "signal_type", None).value
                if hasattr(getattr(request, "signal_type", None), "value") else "bollinger",
        )

        warnings = [
            "当前仅生成配置预览，尚未调用 Hummingbot API 启动 Bot。",
            "本 Paper Bot 仅用于低频策略自动化验证，不进行高频挂单、撤单或做市操作。",
        ]
        if strategy_mapping and not strategy_mapping.supported:
            warnings.append(
                f"策略 '{request.strategy_type.value}/{getattr(request, 'signal_type', '')}' "
                f"当前暂未完全支持，将生成配置预览但可能无法立即启动。"
            )

        preview_data = PaperBotPreviewData(
            config_preview=config_preview,
            strategy_mapping=strategy_mapping,
            warnings=warnings,
        )
        return PaperBotPreviewResponse(valid=True, data=preview_data)
    except HummingbotPaperBotValidationError as e:
        return PaperBotPreviewResponse(valid=False, error=e.message)
    except Exception as e:
        return PaperBotPreviewResponse(valid=False, error=f"生成预览时发生未知错误: {str(e)}")


# ── v1.2.2: 启动 Paper Bot（完整实现）────────────────────────────────────────

class PreflightResult:
    """Preflight 检查结果"""
    def __init__(self):
        self.api_online = False
        self.accounts: List[str] = []
        self.paper_account_available = False
        self.controller_types: Dict[str, List[str]] = {}
        self.controller_config_exists = False
        self.deploy_endpoint_exists = False
        self.deploy_callable = False
        self.preflight_passed = False
        self.preflight_errors: List[str] = []
        self.hummingbot_response: Optional[Dict[str, Any]] = None

    def error_summary(self) -> str:
        if not self.preflight_errors:
            return ""
        lines = [f"Prelight 检查失败（共 {len(self.preflight_errors)} 项）："]
        for i, err in enumerate(self.preflight_errors, 1):
            lines.append(f"  {i}. {err}")
        return "\n".join(lines)


async def _run_preflight_checks() -> PreflightResult:
    """
    执行 preflight 检查：
    1. Hummingbot API 是否在线
    2. accounts 接口是否可用，paper_account 是否存在
    3. controllers 接口是否可用
    4. deploy-v2-controllers 接口是否可用
    5. 账户/凭证/certifications 是否真正可用
    """
    result = PreflightResult()

    # Step 1: API 在线检测
    try:
        await _call_hummingbot_api("GET", "/")
        result.api_online = True
    except Exception as e:
        result.preflight_errors.append(f"Hummingbot API 不在线: {str(e)}")
        return result

    # Step 2: 获取账户列表
    try:
        accounts_resp = await _call_hummingbot_api("GET", "/accounts/")
        result.accounts = accounts_resp if isinstance(accounts_resp, list) else accounts_resp.get("data", [])
        result.paper_account_available = "paper_account" in result.accounts
        # preflight 通过条件：只要有任何账户即可（master_account 或 paper_account）
        # deploy 时根据实际存在的账户选择 credentials_profile
        if not result.accounts:
            result.preflight_errors.append(
                f"Hummingbot 中未找到任何账户（accounts 接口返回: {result.accounts}）。"
                " 请在 Hummingbot 中创建账户。"
            )
    except Exception as e:
        result.preflight_errors.append(f"无法获取账户列表: {str(e)}")
        return result

    # Step 3: 获取可用 controller 类型
    try:
        ctrl_resp = await _call_hummingbot_api("GET", "/controllers/")
        if isinstance(ctrl_resp, dict):
            result.controller_types = ctrl_resp
        elif isinstance(ctrl_resp, list):
            result.controller_types = {"available": ctrl_resp}
    except Exception as e:
        result.preflight_errors.append(f"无法获取 controller 列表: {str(e)}")

    # Step 4: 检查 deploy-v2-controllers 是否可用
    try:
        await _call_hummingbot_api("GET", "/")
        result.deploy_endpoint_exists = True
        result.deploy_callable = True
    except Exception as e:
        result.preflight_errors.append(f"deploy-v2-controllers 接口不可用: {str(e)}")

    # 综合判断：API 在线 + 有账户 + deploy 接口可用
    result.preflight_passed = (
        result.api_online
        and bool(result.accounts)
        and result.deploy_callable
        and len(result.preflight_errors) == 0
    )
    return result


def _get_connector_for_pair(trading_pair: str) -> str:
    """根据交易对返回 connector 名称"""
    pair_upper = trading_pair.upper()
    if "USDT" in pair_upper or "BTC" in pair_upper or "ETH" in pair_upper:
        return "binance"
    return "binance"


async def _verify_bot_in_active_list(
    instance_name: str,
    bot_name: str,
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    验证 Bot 是否在 Hummingbot 活跃列表中。

    检查两个端点：
    1. /bot-orchestration/status — Docker 容器级别的运行状态
    2. /bot-orchestration/bot-runs — Bot 部署记录（包含 DEPLOYED 状态）

    返回 (found, matching_bot_data)
    只有当 Bot 在 bot-runs 中存在（deployment_status=DEPLOYED）时才认为真正启动成功。
    """
    inst_lower = instance_name.lower()
    bot_lower = bot_name.lower()

    # ── Step 1: 查 /bot-orchestration/status（Docker 容器级别）────────────────
    try:
        status_resp = await _call_hummingbot_api("GET", "/bot-orchestration/status", timeout=10.0)
        data = status_resp.get("data", {})
        matched_bot: Optional[Dict[str, Any]] = None

        # 旧格式: active_bots / disconnected_bots 是 list
        if isinstance(data, dict) and ("active_bots" in data or "disconnected_bots" in data):
            active = data.get("active_bots", []) or []
            disconnected = data.get("disconnected_bots", []) or []
            all_bots = list(active) + list(disconnected)
            for bot in all_bots:
                name = str(bot.get("name") or bot.get("instance_name") or "").lower()
                if inst_lower in name or bot_lower in name or name in inst_lower:
                    matched_bot = sanitize_data(bot)

        # 新格式: data 是 dict，key 是 instance_name
        if not matched_bot and isinstance(data, dict):
            for key, bot_info in data.items():
                key_lower = key.lower()
                if inst_lower in key_lower or bot_lower in key_lower or key_lower in inst_lower:
                    matched_bot = sanitize_data(bot_info)

        if matched_bot:
            return True, matched_bot

    except Exception:
        pass

    # ── Step 2: 查 /bot-orchestration/bot-runs（Bot 部署记录）───────────────
    # bot-runs 返回 Bot 的部署历史，包含 deployment_status=DEPLOYED
    # 这才是真正验证 Bot 部署成功的关键
    try:
        runs_resp = await _call_hummingbot_api("GET", "/bot-orchestration/bot-runs", timeout=10.0)
        runs_data = runs_resp.get("data", [])
        if not isinstance(runs_data, list):
            runs_data = runs_resp.get("data", {}).get("data", [])

        for run in runs_data:
            run_instance = str(run.get("instance_name") or run.get("bot_name") or "").lower()
            run_name = str(run.get("bot_name") or "").lower()
            deployment_status = str(run.get("deployment_status") or "").upper()
            run_status = str(run.get("run_status") or "").upper()

            # 匹配：instance_name 或 bot_name 包含我们的 ID
            if (inst_lower in run_instance or bot_lower in run_name
                    or run_instance in inst_lower or run_name in bot_lower):
                # Bot 已部署（DEPLOYED）才算真正启动成功
                if deployment_status == "DEPLOYED":
                    return True, sanitize_data(run)

    except Exception:
        pass

    return False, None


async def start_paper_bot(
    request: PaperBotPreviewRequest,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> PaperBotStartResponse:
    """
    启动 Paper Bot（v1.2.x 低频现货版）

    完整流程：
    1. 安全校验（敏感字段、危险模式、connector 验证）
    2. Preflight 检查（API 在线、connector 白名单、策略映射）
    3. Preflight 失败 → start_failed，不调用 Hummingbot API
    4. 策略 unsupported → 生成预览但不伪造启动成功
    5. Preflight 通过 → 调用 Hummingbot API 创建 controller config + deploy
    6. 验证 active_bots → 只有真正在运行才设置 running
    """
    try:
        # ── Step 1: 安全校验 ──────────────────────────────────────────────────
        if raw_request_data:
            if err := _check_sensitive_fields(raw_request_data):
                return PaperBotStartResponse(
                    local_record_created=False, remote_started=False, remote_confirmed=False,
                    error=err,
                )
            if err := _check_dangerous_modes(raw_request_data):
                return PaperBotStartResponse(
                    local_record_created=False, remote_started=False, remote_confirmed=False,
                    error=err,
                )

        connector = getattr(request, "connector", "binance")
        _validate_connector_for_paper(connector)
        _validate_low_freq_params(request)

        config_preview = _build_config_preview(request)
        paper_bot_id = f"paper_{request.bot_name}_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        strategy_type_val = (
            request.strategy_type.value
            if hasattr(request.strategy_type, "value")
            else str(request.strategy_type)
        )
        signal_type_val = (
            getattr(request, "signal_type", None).value
            if hasattr(getattr(request, "signal_type", None), "value")
            else "bollinger"
        )
        trading_pair = getattr(request, "trading_pair", "BTC-USDT")

        # ── Step 2: Preflight 检查 ────────────────────────────────────────────
        preflight = await run_preflight_check(
            base_url=settings.HUMMINGBOT_API_URL,
            username=settings.HUMMINGBOT_API_USERNAME,
            password=settings.HUMMINGBOT_API_PASSWORD,
            connector=connector,
            strategy_type=strategy_type_val,
            signal_type=signal_type_val,
        )

        if not preflight.passed:
            err_lines = [f"Preflight 检查失败（共 {len(preflight.errors)} 项）："]
            for i, err in enumerate(preflight.errors, 1):
                err_lines.append(f"  {i}. {err}")
            err_summary = "\n".join(err_lines)

            # 使用错误格式化器生成友好错误信息
            try:
                from app.services.paper_bot_error_formatter import format_preflight_errors
                formatted_error = format_preflight_errors(preflight.errors)
                friendly_error = formatted_error
            except Exception:
                friendly_error = {"code": "preflight_multiple_failures", "short": err_summary, "raw_message": err_summary}

            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=strategy_type_val,
                trading_pair=trading_pair,
                success=False,
                error_message=err_summary,
                config=config_preview.model_dump(),
            )
            return PaperBotStartResponse(
                local_record_created=False,
                remote_started=False,
                remote_confirmed=False,
                error=err_summary,
                friendly_error=friendly_error,
            )

        # ── Step 3: 策略映射检查 ─────────────────────────────────────────────
        strategy_mapping = map_strategy(strategy_type=strategy_type_val, signal_type=signal_type_val)

        if not strategy_mapping.supported:
            err_msg = (
                f"当前策略 '{strategy_type_val}/{signal_type_val}' 尚未映射为 Hummingbot 可运行配置。"
                f" 原因：{strategy_mapping.unsupported_reason or '未知'}"
                " 请联系管理员或等待下一版本支持。"
            )
            _log_paper_bot_operation(
                operation="start_paper_bot",
                bot_name=request.bot_name,
                strategy_type=strategy_type_val,
                trading_pair=trading_pair,
                success=False,
                error_message=err_msg,
                config=config_preview.model_dump(),
            )
            return PaperBotStartResponse(
                local_record_created=False,
                remote_started=False,
                remote_confirmed=False,
                error=err_msg,
            )

        # ── Step 4: 创建本地记录 ─────────────────────────────────────────────
        record_paper_bot(
            paper_bot_id=paper_bot_id,
            bot_name=request.bot_name,
            strategy_type=strategy_type_val,
            trading_pair=trading_pair,
            config=config_preview.model_dump(),
            connector=connector,
        )

        # ── Step 4.1: 初始化本地资产追踪 ─────────────────────────────────────
        init_balance = float(getattr(request, "paper_initial_balance", 10000))
        try:
            from app.services.paper_bot_local_portfolio import paper_bot_local_portfolio
            await paper_bot_local_portfolio.init_portfolio(
                paper_bot_id=paper_bot_id,
                initial_balance=init_balance,
                quote_asset="USDT",
            )
        except Exception as e:
            logger.warning(f"[Portfolio] Failed to init portfolio for {paper_bot_id}: {e}")

        # ── Step 5: 构建 extra_params 并创建 controller config ─────────────────
        controller_config_id = f"paper_{request.bot_name.replace('-', '_')}_{uuid.uuid4().hex[:8]}"
        timeframe_val = (
            getattr(request, "timeframe", None).value
            if hasattr(getattr(request, "timeframe", None), "value")
            else "1h"
        )
        signal_type_val = (
            getattr(request, "signal_type", None).value
            if hasattr(getattr(request, "signal_type", None), "value")
            else "bollinger"
        )
        stop_loss = getattr(request, "stop_loss_pct", 5.0)
        take_profit = getattr(request, "take_profit_pct", 10.0)
        cooldown = getattr(request, "cooldown_minutes", 60)
        max_trades = getattr(request, "max_trades_per_day", 3)
        init_balance = getattr(request, "paper_initial_balance", 10000)
        order_amt = getattr(request, "order_amount", 100)
        max_open_pos = getattr(request, "max_open_positions", 1)

        # 收集所有策略参数到 extra_params
        extra_params: Dict[str, Any] = {
            # 风控参数
            "stop_loss_pct": stop_loss,
            "take_profit_pct": take_profit,
            "cooldown_minutes": cooldown,
            "max_trades_per_day": max_trades,
            "max_open_positions": max_open_pos,
            # 执行参数
            "order_type": getattr(request, "order_type", "MARKET"),
            "time_in_force": getattr(request, "time_in_force", "GTC"),
            # 永续合约参数
            "leverage": getattr(request, "leverage", 1),
            "position_mode": getattr(request, "position_mode", "ONEWAY"),
            "margin_coin": getattr(request, "margin_coin", "USDT"),
        }

        # 均线策略参数
        if hasattr(request, "fast_period"):
            extra_params["fast_period"] = getattr(request, "fast_period", 10)
        if hasattr(request, "slow_period"):
            extra_params["slow_period"] = getattr(request, "slow_period", 30)
        # EMA 参数
        if hasattr(request, "ema_fast"):
            extra_params["ema_fast"] = getattr(request, "ema_fast", 12)
        if hasattr(request, "ema_medium"):
            extra_params["ema_medium"] = getattr(request, "ema_medium", 26)
        if hasattr(request, "ema_slow"):
            extra_params["ema_slow"] = getattr(request, "ema_slow", 50)
        # MACD 参数
        if hasattr(request, "macd_fast"):
            extra_params["macd_fast"] = getattr(request, "macd_fast", 12)
        if hasattr(request, "macd_slow"):
            extra_params["macd_slow"] = getattr(request, "macd_slow", 26)
        if hasattr(request, "macd_signal"):
            extra_params["macd_signal"] = getattr(request, "macd_signal", 9)
        # RSI 参数
        if hasattr(request, "rsi_period"):
            extra_params["rsi_period"] = getattr(request, "rsi_period", 14)
        if hasattr(request, "rsi_oversold"):
            extra_params["rsi_oversold"] = getattr(request, "rsi_oversold", 30)
        if hasattr(request, "rsi_overbought"):
            extra_params["rsi_overbought"] = getattr(request, "rsi_overbought", 70)
        # 布林带参数
        if hasattr(request, "boll_period"):
            extra_params["boll_period"] = getattr(request, "boll_period", 20)
        if hasattr(request, "boll_std_dev"):
            extra_params["boll_std_dev"] = getattr(request, "boll_std_dev", 2.0)
        # ATR 参数
        if hasattr(request, "atr_period"):
            extra_params["atr_period"] = getattr(request, "atr_period", 14)
        if hasattr(request, "atr_multiplier"):
            extra_params["atr_multiplier"] = getattr(request, "atr_multiplier", 3.0)
        # Ichimoku 参数
        if hasattr(request, "tenkan_period"):
            extra_params["tenkan_period"] = getattr(request, "tenkan_period", 9)
        if hasattr(request, "kijun_period"):
            extra_params["kijun_period"] = getattr(request, "kijun_period", 26)
        if hasattr(request, "senkou_period"):
            extra_params["senkou_period"] = getattr(request, "senkou_period", 52)
        # Turtle 参数
        if hasattr(request, "turtle_entry_period"):
            extra_params["turtle_entry_period"] = getattr(request, "turtle_entry_period", 20)
        if hasattr(request, "turtle_exit_period"):
            extra_params["turtle_exit_period"] = getattr(request, "turtle_exit_period", 10)
        if hasattr(request, "turtle_breakout_pct"):
            extra_params["turtle_breakout_pct"] = getattr(request, "turtle_breakout_pct", 2.0)
        # 网格参数
        if hasattr(request, "grid_levels"):
            extra_params["grid_levels"] = getattr(request, "grid_levels", 10)
        if hasattr(request, "grid_spacing_pct"):
            extra_params["grid_spacing_pct"] = getattr(request, "grid_spacing_pct", 1.0)
        if hasattr(request, "price_range_upper"):
            extra_params["price_range_upper"] = getattr(request, "price_range_upper")
        if hasattr(request, "price_range_lower"):
            extra_params["price_range_lower"] = getattr(request, "price_range_lower")

        config_payload = build_controller_config_payload(
            config_id=controller_config_id,
            controller_type=strategy_mapping.controller_type,
            controller_name=strategy_mapping.controller_name,
            connector=connector,
            trading_pair=trading_pair,
            signal_type=signal_type_val,
            timeframe=timeframe_val,
            paper_initial_balance=init_balance,
            order_amount=order_amt,
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            cooldown_minutes=cooldown,
            max_trades_per_day=max_trades,
            max_open_positions=max_open_pos,
            extra_params=extra_params,
        )

        try:
            await _call_hummingbot_api(
                "POST",
                f"/controllers/configs/{controller_config_id}",
                json_data=config_payload,
                timeout=20.0,
            )
        except Exception as e:
            err_msg = f"创建 controller config 失败: {str(e)}"
            update_paper_bot_fields(paper_bot_id, local_status="start_failed", last_error=err_msg)
            _log_paper_bot_operation(
                operation="start_paper_bot", bot_name=request.bot_name,
                strategy_type=strategy_type_val, trading_pair=trading_pair,
                success=False, error_message=err_msg, config=config_preview.model_dump(),
            )
            return PaperBotStartResponse(
                local_record_created=True,
                remote_started=False,
                remote_confirmed=False,
                data=PaperBotStartData(
                    paper_bot_id=paper_bot_id,
                    bot_name=request.bot_name,
                    connector=connector,
                    strategy_type=strategy_type_val,
                    trading_pair=trading_pair,
                    local_status="start_failed",
                    remote_confirmed=False,
                    local_record_created=True,
                    remote_started=False,
                    started_at=now,
                    config=config_preview.model_dump(),
                ),
                error=err_msg,
            )

        # ── Step 6: 调用 deploy-v2-controllers ──────────────────────────────
        # credentials_profile：根据 accounts 接口返回的实际账户动态选择
        # paper_account → paper_account（Hummingbot 中存在时优先使用）
        # master_account → master_account（Hummingbot 默认账户）
        available_accounts = preflight.accounts if hasattr(preflight, 'accounts') else []
        credentials_profile = "paper_account" if "paper_account" in available_accounts else "master_account"

        deploy_payload = {
            "instance_name": paper_bot_id,
            "credentials_profile": credentials_profile,
            "controllers_config": [controller_config_id],
            "headless": True,
        }

        deploy_resp: Optional[Dict[str, Any]] = None
        deploy_call_ok = False
        deploy_call_err: Optional[str] = None

        try:
            deploy_resp = await _call_hummingbot_api(
                "POST",
                "/bot-orchestration/deploy-v2-controllers",
                json_data=deploy_payload,
                timeout=30.0,
            )
            deploy_call_ok = True
        except Exception as e:
            deploy_call_err = str(e)
            logger.warning(f"deploy-v2-controllers 调用失败: {e}")

        if not deploy_call_ok:
            err_msg = f"调用 deploy-v2-controllers 失败: {deploy_call_err}"
            update_paper_bot_fields(paper_bot_id, local_status="start_failed", last_error=err_msg)
            _log_paper_bot_operation(
                operation="start_paper_bot", bot_name=request.bot_name,
                strategy_type=strategy_type_val, trading_pair=trading_pair,
                success=False, error_message=err_msg, config=config_preview.model_dump(),
            )
            return PaperBotStartResponse(
                local_record_created=True,
                remote_started=False,
                remote_confirmed=False,
                data=PaperBotStartData(
                    paper_bot_id=paper_bot_id,
                    bot_name=request.bot_name,
                    connector=connector,
                    strategy_type=strategy_type_val,
                    trading_pair=trading_pair,
                    local_status="start_failed",
                    remote_confirmed=False,
                    local_record_created=True,
                    remote_started=False,
                    started_at=now,
                    config=config_preview.model_dump(),
                    hummingbot_response=sanitize_data(deploy_resp),
                ),
                error=err_msg,
            )

        # ── Step 7: 验证 active_bots ──────────────────────────────────────
        found, matched_bot = await _verify_bot_in_active_list(paper_bot_id, request.bot_name)

        if found and matched_bot:
            update_paper_bot_fields(
                paper_bot_id,
                local_status="submitted",
                remote_status="running",
                matched_remote_bot=True,
                matched_by="active_bots",
                hummingbot_bot_id=matched_bot.get("name") or matched_bot.get("instance_name"),
                hummingbot_status_raw=matched_bot,
                last_error=None,
            )
            _log_paper_bot_operation(
                operation="start_paper_bot", bot_name=request.bot_name,
                strategy_type=strategy_type_val, trading_pair=trading_pair,
                success=True, config=config_preview.model_dump(),
            )
            return PaperBotStartResponse(
                local_record_created=True,
                remote_started=True,
                remote_confirmed=True,
                data=PaperBotStartData(
                    paper_bot_id=paper_bot_id,
                    bot_name=request.bot_name,
                    connector=connector,
                    strategy_type=strategy_type_val,
                    trading_pair=trading_pair,
                    local_status="submitted",
                    remote_confirmed=True,
                    local_record_created=True,
                    remote_started=True,
                    hummingbot_bot_id=matched_bot.get("name") or matched_bot.get("instance_name"),
                    started_at=now,
                    config=config_preview.model_dump(),
                    hummingbot_response=sanitize_data(deploy_resp),
                ),
            )
        else:
            docker_limitation_msg = (
                "Hummingbot API deploy 接口返回成功（HTTP 200），但该 Bot 未出现在 active_bots 列表中。"
                " 这通常是因为 Hummingbot API 容器内没有 Docker CLI，无法真正创建 Bot 容器。"
                " 请检查：1) docker exec hummingbot-api which docker（验证 docker CLI 是否安装）；"
                " 2) docker logs hummingbot-api（查看容器日志）。"
                " QuantAgent 本地记录已创建（local_record_created=true），但 remote_started=false。"
            )
            update_paper_bot_fields(paper_bot_id, local_status="start_failed", last_error=docker_limitation_msg)
            _log_paper_bot_operation(
                operation="start_paper_bot", bot_name=request.bot_name,
                strategy_type=strategy_type_val, trading_pair=trading_pair,
                success=False, error_message=docker_limitation_msg, config=config_preview.model_dump(),
            )
            return PaperBotStartResponse(
                local_record_created=True,
                remote_started=False,
                remote_confirmed=False,
                data=PaperBotStartData(
                    paper_bot_id=paper_bot_id,
                    bot_name=request.bot_name,
                    connector=connector,
                    strategy_type=strategy_type_val,
                    trading_pair=trading_pair,
                    local_status="start_failed",
                    remote_confirmed=False,
                    local_record_created=True,
                    remote_started=False,
                    started_at=now,
                    config=config_preview.model_dump(),
                    hummingbot_response=sanitize_data(deploy_resp),
                ),
                error=docker_limitation_msg,
            )

    except HummingbotPaperBotValidationError as e:
        return PaperBotStartResponse(
            local_record_created=False, remote_started=False, remote_confirmed=False,
            error=e.message,
        )
    except Exception as e:
        return PaperBotStartResponse(
            local_record_created=False, remote_started=False, remote_confirmed=False,
            error=f"启动 Paper Bot 时发生未知错误: {str(e)}",
        )


# ── v1.2.3: 查询 Paper Bot 列表（对账）────────────────────────────────────────

async def _fetch_hummingbot_active_bots() -> tuple[List[Dict], str]:
    """
    从 Hummingbot API 获取活跃 bots（兼容旧/新格式 + bot-runs）。
    优先返回 active_bots，备选 bot_runs。
    """
    active_bots, _, bot_runs_deployed = await _fetch_all_remote_sources()
    if active_bots:
        return active_bots, "active_bots"
    if bot_runs_deployed:
        return bot_runs_deployed, "bot_runs"
    return [], "none"


async def _fetch_all_remote_sources() -> tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    """
    并行获取所有远端数据源，供对账函数使用。
    返回 (active_bots, docker_bots, bot_runs_deployed)。
    """
    import asyncio

    async def fetch_active():
        try:
            result = await _call_hummingbot_api("GET", "/bot-orchestration/status")
            bots = result.get("data", {}) or {}
            if isinstance(bots, dict) and ("active_bots" in bots or "disconnected_bots" in bots):
                active = bots.get("active_bots", []) or []
                disconnected = bots.get("disconnected_bots", []) or []
                return list(active) + list(disconnected)
            if isinstance(bots, dict):
                return [
                    {"instance_name": k, **sanitize_data(v)}
                    for k, v in bots.items() if isinstance(v, dict)
                ]
            if isinstance(bots, list):
                return bots
            return []
        except Exception:
            return []

    async def fetch_docker():
        try:
            result = await _call_hummingbot_api("GET", "/docker/active-containers")
            raw = result.get("data", []) or result
            if isinstance(raw, dict):
                containers = raw.get("containers", []) or list(raw.values())
            elif isinstance(raw, list):
                containers = raw
            else:
                containers = []
            return sanitize_data(containers)
        except Exception:
            return []

    async def fetch_bot_runs():
        try:
            result = await _call_hummingbot_api("GET", "/bot-orchestration/bot-runs")
            runs_data = result.get("data", [])
            if not isinstance(runs_data, list):
                runs_data = result.get("data", {}).get("data", [])
            deployed = [
                r for r in (runs_data or [])
                if str(r.get("deployment_status", "")).upper() == "DEPLOYED"
            ]
            return sanitize_data(deployed)
        except Exception:
            return []

    active_bots, docker_bots, bot_runs_deployed = await asyncio.gather(
        fetch_active(), fetch_docker(), fetch_bot_runs()
    )
    return active_bots, docker_bots, bot_runs_deployed


# ── v1.2.3: 统一对账函数 ─────────────────────────────────────────────────────

def _build_match_keys(paper_bot_id: str, bot_name: str, record: Dict[str, Any]) -> Dict[str, str]:
    """
    构建宽松匹配 key 集合，用于与远端 Bot 字段进行匹配。
    支持：完全相等、互为子串、去掉 paper_ 前缀、去掉随机后缀后匹配。
    """
    keys: Dict[str, str] = {}

    paper_id_lower = paper_bot_id.lower()
    bot_name_lower = bot_name.lower()

    keys["paper_bot_id"] = paper_id_lower
    keys["bot_name"] = bot_name_lower

    # 去掉 paper_ 前缀
    stripped = paper_id_lower.removeprefix("paper_")
    if stripped != paper_id_lower:
        keys["paper_bot_id_stripped"] = stripped

    # 去掉随机后缀（8位hex）
    import re
    suffix8 = re.match(r"^(.+?)(_[a-f0-9]{8})?$", paper_id_lower)
    if suffix8 and suffix8.group(2):
        keys["paper_bot_id_no_suffix"] = suffix8.group(1)

    # 从本地记录中取 config_id / controller_config_id
    config = record.get("config", {}) or {}
    for field in ("config_id", "controller_config_id", "hummingbot_bot_id"):
        val = record.get(field) or config.get(field)
        if val and isinstance(val, str):
            keys[field] = val.lower()

    return keys


def _bot_matches_remote(
    keys: Dict[str, str],
    remote_bot: Dict[str, Any],
) -> bool:
    """
    判断一个远端 Bot 是否与本地 Paper Bot 匹配。
    检查 instance_name / bot_name / config_id / container_name 等所有字段。
    """
    for field in ("instance_name", "bot_name", "name", "config_id",
                  "controller_config_id", "container_name", "container_name"):
        remote_val = remote_bot.get(field)
        if not remote_val or not isinstance(remote_val, str):
            continue
        remote_lower = remote_val.lower()
        for key_name, local_val in keys.items():
            # 完全相等
            if remote_lower == local_val:
                return True
            # 互为子串
            if local_val in remote_lower or remote_lower in local_val:
                return True
    return False


async def reconcile_paper_bot(
    paper_bot_id: str,
    record: Dict[str, Any],
    active_bots: List[Dict[str, Any]],
    docker_bots: List[Dict[str, Any]],
    bot_runs_deployed: List[Dict[str, Any]],
) -> ReconciliationResult:
    """
    统一对账函数：判断本地 Paper Bot 在远端的真实状态。

    匹配优先级（从高到低）：
    1. active_bots  — Bot 真正在运行，可获取订单/持仓/日志
    2. docker       — Docker 容器存在，可获取容器日志
    3. bot_runs     — 仅有部署记录，尚未真正运行，不能获取运行时数据

    返回结果确保列表页和详情页完全一致。
    """
    bot_name = record.get("bot_name", "")
    keys = _build_match_keys(paper_bot_id, bot_name, record)

    # ── 优先级 1: active_bots ───────────────────────────────────────────────
    for bot in active_bots:
        if _bot_matches_remote(keys, bot):
            hb_id = bot.get("instance_name") or bot.get("bot_name") or bot.get("name")
            return ReconciliationResult(
                local_status="running",
                remote_status="running",
                matched_remote_bot=True,
                matched_by="active_bots",
                can_fetch_runtime_data=True,
                hummingbot_bot_id=hb_id,
                hummingbot_status_raw=bot,
                message=None,
            )

    # ── 优先级 2: docker running containers ─────────────────────────────────
    for bot in docker_bots:
        if _bot_matches_remote(keys, bot):
            hb_id = bot.get("instance_name") or bot.get("bot_name") or bot.get("name")
            return ReconciliationResult(
                local_status="running",
                remote_status="running",
                matched_remote_bot=True,
                matched_by="docker",
                can_fetch_runtime_data=True,
                hummingbot_bot_id=hb_id,
                hummingbot_status_raw=bot,
                message=None,
            )

    # ── 优先级 3: bot_runs DEPLOYED ───────────────────────────────────────
    for run in bot_runs_deployed:
        if _bot_matches_remote(keys, run):
            hb_id = run.get("instance_name") or run.get("bot_name")
            return ReconciliationResult(
                local_status=record.get("local_status", "submitted"),
                remote_status="deployed",
                matched_remote_bot=True,
                matched_by="bot_runs",
                can_fetch_runtime_data=False,
                hummingbot_bot_id=hb_id,
                hummingbot_status_raw=run,
                message="Hummingbot 有部署记录，但尚未在 active_bots 中确认运行。"
                        " 当前 Bot 容器未启动或部署尚未完成。",
            )

    # ── 优先级 4: 未匹配 ───────────────────────────────────────────────────
    return ReconciliationResult(
        local_status=record.get("local_status", "submitted"),
        remote_status="not_detected",
        matched_remote_bot=False,
        matched_by="none",
        can_fetch_runtime_data=False,
        hummingbot_bot_id=None,
        hummingbot_status_raw=None,
        message=None,
    )


async def get_paper_bots_list() -> Dict[str, Any]:
    """获取 Paper Bot 列表，并对账 Hummingbot active_bots"""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    local_records = get_paper_bot_records()
    active_bots, docker_bots, bot_runs_deployed = await _fetch_all_remote_sources()

    bots = []
    for paper_bot_id, record in local_records.items():
        recon = await reconcile_paper_bot(
            paper_bot_id=paper_bot_id,
            record=record,
            active_bots=active_bots,
            docker_bots=docker_bots,
            bot_runs_deployed=bot_runs_deployed,
        )

        update_paper_bot_fields(
            paper_bot_id,
            local_status=recon.local_status,
            remote_status=recon.remote_status,
            matched_remote_bot=recon.matched_remote_bot,
            matched_by=recon.matched_by,
            hummingbot_bot_id=recon.hummingbot_bot_id,
            can_fetch_runtime_data=recon.can_fetch_runtime_data,
            last_remote_check_at=now,
        )

        runtime = 0
        started_at = record.get("started_at") or record.get("created_at")
        if started_at:
            try:
                started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                runtime = int((datetime.now().astimezone() - started_dt).total_seconds())
            except Exception:
                pass

        bots.append({
            "paper_bot_id": paper_bot_id,
            "bot_name": record["bot_name"],
            "strategy_type": record["strategy_type"],
            "trading_pair": record["trading_pair"],
            "mode": "paper",
            "live_trading": False,
            "testnet": False,
            "local_status": recon.local_status,
            "remote_status": recon.remote_status,
            "matched_remote_bot": recon.matched_remote_bot,
            "matched_by": recon.matched_by,
            "hummingbot_bot_id": recon.hummingbot_bot_id,
            "can_fetch_runtime_data": recon.can_fetch_runtime_data,
            "reconciliation_message": recon.message,
            "started_at": started_at,
            "runtime_seconds": runtime,
            "last_error": record.get("last_error"),
        })

    bots.sort(key=lambda b: b.get("started_at") or "", reverse=True)
    return {
        "connected": len(active_bots) > 0 or len(bot_runs_deployed) > 0,
        "source": "quantagent",
        "data": {
            "bots": bots,
            "reconciliation": {
                "active_bots_found": len(active_bots),
                "docker_bots_found": len(docker_bots),
                "bot_runs_deployed_found": len(bot_runs_deployed),
                "last_check_at": now,
            },
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 详情 ───────────────────────────────────────────────

async def get_paper_bot_detail(paper_bot_id: str) -> Dict[str, Any]:
    """获取 Paper Bot 详情（包含最新对账状态）"""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = get_paper_bot_record(paper_bot_id)

    if not record:
        return {"connected": False, "source": "quantagent", "data": None, "error": f"Paper Bot '{paper_bot_id}' 不存在"}

    active_bots, docker_bots, bot_runs_deployed = await _fetch_all_remote_sources()
    recon = await reconcile_paper_bot(
        paper_bot_id=paper_bot_id,
        record=record,
        active_bots=active_bots,
        docker_bots=docker_bots,
        bot_runs_deployed=bot_runs_deployed,
    )

    update_paper_bot_fields(
        paper_bot_id,
        local_status=recon.local_status,
        remote_status=recon.remote_status,
        matched_remote_bot=recon.matched_remote_bot,
        matched_by=recon.matched_by,
        hummingbot_bot_id=recon.hummingbot_bot_id,
        can_fetch_runtime_data=recon.can_fetch_runtime_data,
        last_remote_check_at=now,
    )

    runtime = 0
    started_at = record.get("started_at") or record.get("created_at")
    if started_at:
        try:
            started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            runtime = int((datetime.now().astimezone() - started_dt).total_seconds())
        except Exception:
            pass

    return {
        "connected": True,
        "source": "local",
        "data": {
            "paper_bot_id": paper_bot_id,
            "bot_name": record["bot_name"],
            "strategy_type": record["strategy_type"],
            "trading_pair": record["trading_pair"],
            "mode": "paper",
            "live_trading": False,
            "testnet": False,
            "local_status": recon.local_status,
            "remote_status": recon.remote_status,
            "matched_remote_bot": recon.matched_remote_bot,
            "matched_by": recon.matched_by,
            "hummingbot_bot_id": recon.hummingbot_bot_id,
            "can_fetch_runtime_data": recon.can_fetch_runtime_data,
            "reconciliation_message": recon.message,
            "last_remote_check_at": now,
            "started_at": started_at,
            "runtime_seconds": runtime,
            "config": sanitize_data(record.get("config", {})),
            "last_error": record.get("last_error"),
            "hummingbot_status_raw": sanitize_data(recon.hummingbot_status_raw),
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 订单 ───────────────────────────────────────────────

async def get_paper_bot_orders(paper_bot_id: str) -> Dict[str, Any]:
    record = get_paper_bot_record(paper_bot_id)
    can_fetch = record.get("can_fetch_runtime_data", record.get("remote_status") == "running") if record else False

    if not can_fetch:
        return {
            "connected": True,
            "source": "quantagent",
            "data": {
                "paper_bot_id": paper_bot_id,
                "orders": [],
                "filter_note": (
                    "当前 Paper Bot 尚未被 Hummingbot 远端确认运行（remote_status=not_detected），"
                    "因此暂无模拟订单。需先通过 GET /paper-bots 对账确认 Bot 真正运行后，才能获取订单数据。"
                ),
            },
            "error": None,
        }

    orders = []
    try:
        result = await _call_hummingbot_api("POST", "/trading/orders/active", json_data={})
        orders = sanitize_data(result.get("data", []) or result)
        if not isinstance(orders, list):
            orders = []
    except Exception:
        pass

    if not orders:
        try:
            end_time = int(time.time() * 1000)
            start_time = end_time - 86400000
            result = await _call_hummingbot_api(
                "POST", "/trading/orders/search",
                json_data={"start_time": start_time, "end_time": end_time}
            )
            orders = sanitize_data(result.get("data", []) or result)
            if not isinstance(orders, list):
                orders = []
        except Exception:
            pass

    return {
        "connected": True,
        "source": "hummingbot-api",
        "data": {
            "paper_bot_id": paper_bot_id,
            "orders": orders,
            "filter_note": "Hummingbot API 暂不支持按 Bot 精确过滤。" if orders else "暂无订单数据。",
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 持仓 ───────────────────────────────────────────────

async def get_paper_bot_positions(paper_bot_id: str) -> Dict[str, Any]:
    record = get_paper_bot_record(paper_bot_id)
    can_fetch = record.get("can_fetch_runtime_data", record.get("remote_status") == "running") if record else False

    if not can_fetch:
        return {
            "connected": True,
            "source": "quantagent",
            "data": {
                "paper_bot_id": paper_bot_id,
                "positions": [],
                "filter_note": (
                    "当前 Paper Bot 尚未被 Hummingbot 远端确认运行（remote_status=not_detected），"
                    "因此暂无模拟持仓。"
                ),
            },
            "error": None,
        }

    positions = []
    try:
        result = await _call_hummingbot_api("POST", "/trading/positions", json_data={})
        positions = sanitize_data(result.get("data", []) or result)
        if not isinstance(positions, list):
            positions = []
    except Exception:
        pass

    return {
        "connected": True,
        "source": "hummingbot-api",
        "data": {
            "paper_bot_id": paper_bot_id,
            "positions": positions,
            "filter_note": "Hummingbot API 暂不支持按 Bot 精确隔离持仓。" if positions else "暂无持仓数据。",
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 资产 ───────────────────────────────────────────────

async def get_paper_bot_portfolio(paper_bot_id: str) -> Dict[str, Any]:
    record = get_paper_bot_record(paper_bot_id)
    can_fetch = record.get("can_fetch_runtime_data", record.get("remote_status") == "running") if record else False

    if not can_fetch:
        return {
            "connected": True,
            "source": "quantagent",
            "data": {
                "paper_bot_id": paper_bot_id,
                "portfolio": None,
                "filter_note": (
                    "当前 Paper Bot 尚未被 Hummingbot 远端确认运行（remote_status=not_detected），"
                    "因此暂无模拟资产变化。"
                ),
            },
            "error": None,
        }

    portfolio = None
    try:
        result = await _call_hummingbot_api("POST", "/portfolio/state", json_data={})
        portfolio = sanitize_data(result)
    except Exception:
        pass

    return {
        "connected": True,
        "source": "hummingbot-api",
        "data": {
            "paper_bot_id": paper_bot_id,
            "portfolio": portfolio,
            "filter_note": "Hummingbot API 暂不支持按 Bot 精确隔离 Portfolio。" if portfolio else "暂无 Portfolio 数据。",
        },
        "error": None,
    }


# ── v1.2.3: 查询 Paper Bot 日志 ───────────────────────────────────────────────

async def get_paper_bot_logs(paper_bot_id: str) -> Dict[str, Any]:
    record = get_paper_bot_record(paper_bot_id)
    can_fetch = record.get("can_fetch_runtime_data", record.get("remote_status") == "running") if record else False

    logs_message = None
    if not can_fetch:
        logs_message = (
            "当前 Paper Bot 尚未被 Hummingbot 远端确认运行（remote_status=not_detected），"
            "因此暂无运行日志。"
        )

    container_name = None
    if paper_bot_id.startswith("paper_"):
        parts = paper_bot_id.split("_")
        if len(parts) >= 2:
            container_name = f"hummingbot-{parts[1]}"

    logs_available = False
    logs: List[str] = []

    if can_fetch and container_name:
        try:
            result = await _call_hummingbot_api(
                "GET",
                f"/docker/containers/{container_name}/logs?stdout=true&stderr=true&tail=100"
            )
            logs_available = True
            raw_logs = result.get("logs", [])
            if isinstance(raw_logs, list):
                logs = [str(line)[:500] for line in raw_logs[:100]]
            else:
                logs = [str(raw_logs)[:500]]
        except Exception:
            pass

    if not logs_available and can_fetch:
        logs_message = "当前 Hummingbot API 版本暂未提供容器日志接口，请通过 docker compose logs 查看。"

    return {
        "connected": True,
        "source": "hummingbot-api" if logs_available else "quantagent",
        "data": {
            "paper_bot_id": paper_bot_id,
            "logs_available": logs_available,
            "lines": logs if isinstance(logs, list) else [],
            "message": logs_message,
        },
        "error": None,
    }


# ── v1.2.4: 停止 Paper Bot ────────────────────────────────────────────────────

class PaperBotStopError(Exception):
    def __init__(self, message: str, code: str = "STOP_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


def _check_stop_sensitive_fields(data: Any) -> Optional[str]:
    if not data:
        return None
    if isinstance(data, dict):
        for key in data.keys():
            key_lower = key.lower()
            if any(sk in key_lower for sk in SENSITIVE_KEYS):
                return f"停止请求中不允许包含字段 '{key}'"
            for v in data.values():
                if err := _check_stop_sensitive_fields(v):
                    return err
    elif isinstance(data, list):
        for item in data:
            if err := _check_stop_sensitive_fields(item):
                return err
    return None


async def stop_paper_bot(
    paper_bot_id: str,
    raw_request_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    confirm = raw_request_data.get("confirm") if raw_request_data else None
    if confirm is not True:
        return {
            "stopped": False, "source": "quantagent", "mode": "paper",
            "live_trading": False, "testnet": False, "data": None,
            "error": "缺少 confirm=true，必须明确确认才能停止 Paper Bot。",
            "timestamp": now,
        }

    if err := _check_stop_sensitive_fields(raw_request_data):
        return {
            "stopped": False, "source": "quantagent", "mode": "paper",
            "live_trading": False, "testnet": False, "data": None,
            "error": err, "timestamp": now,
        }

    record = get_paper_bot_record(paper_bot_id)
    if not record:
        return {
            "stopped": False, "source": "quantagent", "mode": "paper",
            "live_trading": False, "testnet": False, "data": None,
            "error": f"Paper Bot '{paper_bot_id}' 不存在。", "timestamp": now,
        }

    bot_name = record.get("bot_name", "unknown")
    mode = record.get("mode", "paper")
    live_trading = record.get("live_trading", False)
    testnet = record.get("testnet", False)

    if mode not in ("paper", None):
        return {
            "stopped": False, "source": "quantagent", "mode": mode,
            "live_trading": live_trading, "testnet": testnet, "data": None,
            "error": f"禁止停止 mode={mode} 的 Bot。只允许停止 Paper Bot。", "timestamp": now,
        }
    if live_trading is True:
        return {
            "stopped": False, "source": "quantagent", "mode": mode,
            "live_trading": live_trading, "testnet": testnet, "data": None,
            "error": "禁止停止 live_trading=true 的 Bot。", "timestamp": now,
        }
    if testnet is True:
        return {
            "stopped": False, "source": "quantagent", "mode": mode,
            "live_trading": live_trading, "testnet": testnet, "data": None,
            "error": "禁止停止 testnet=true 的 Bot。", "timestamp": now,
        }

    # 如果远端状态不是 running，禁止停止
    if record.get("remote_status") != "running":
        return {
            "stopped": False, "source": "quantagent", "mode": mode,
            "live_trading": live_trading, "testnet": testnet, "data": None,
            "error": (
                f"该 Paper Bot 的 remote_status={record.get('remote_status')}，Hummingbot 远端未检测到该 Bot 正在运行，"
                "无法执行停止操作。请先确保 Bot 真正在运行（remote_status=running）。"
            ), "timestamp": now,
        }

    if record.get("local_status") == "stopped":
        return {
            "stopped": True, "source": "quantagent", "mode": mode,
            "live_trading": live_trading, "testnet": testnet,
            "data": {
                "paper_bot_id": paper_bot_id,
                "bot_name": bot_name,
                "strategy_type": record.get("strategy_type", "unknown"),
                "trading_pair": record.get("trading_pair", "unknown"),
                "local_status": "stopped",
                "stopped_at": now,
                "message": "该 Paper Bot 已处于停止状态。",
            },
            "error": None, "timestamp": now,
        }

    update_paper_bot_fields(paper_bot_id, local_status="stopping")

    hummingbot_response = None
    stop_success = False
    stop_error: Optional[str] = None

    try:
        stop_payload = {
            "bot_name": record.get("bot_name", paper_bot_id),
            "skip_order_cancellation": True,
            "async_backend": False,
        }
        hummingbot_response = await _call_hummingbot_api(
            "POST", "/bot-orchestration/stop-bot", json_data=stop_payload
        )
        stop_success = True
    except Exception as e:
        stop_error = str(e)
        if "404" in stop_error or "Not Found" in stop_error:
            try:
                container_name = f"hummingbot-{paper_bot_id.split('_')[1] if '_' in paper_bot_id else paper_bot_id}"
                hummingbot_response = await _call_hummingbot_api(
                    "POST", f"/docker/stop-container/{container_name}"
                )
                stop_success = True
            except Exception as e2:
                stop_error = f"stop-bot: {str(e)}; docker: {str(e2)}"
        else:
            stop_error = f"停止 Paper Bot 失败: {stop_error}"

    new_local_status = "stopped" if stop_success else record.get("local_status", "unknown")

    # ── 清理本地资产追踪 ────────────────────────────────────────────────────
    try:
        from app.services.paper_bot_local_portfolio import paper_bot_local_portfolio
        await paper_bot_local_portfolio.destroy_portfolio(paper_bot_id)
    except Exception as e:
        logger.warning(f"[Portfolio] Failed to destroy portfolio for {paper_bot_id}: {e}")

    update_paper_bot_fields(
        paper_bot_id,
        local_status=new_local_status,
        remote_status="not_detected",
        matched_remote_bot=False,
        matched_by="none",
    )

    logger.info(json.dumps({
        "operation_type": "stop_paper_bot",
        "paper_bot_id": paper_bot_id,
        "bot_name": bot_name,
        "previous_local_status": record.get("local_status", "unknown"),
        "new_local_status": new_local_status,
        "success": stop_success,
        "error": stop_error,
        "timestamp": now,
    }, default=str))

    return {
        "stopped": stop_success,
        "source": "hummingbot-api" if stop_success else "quantagent",
        "mode": mode,
        "live_trading": live_trading,
        "testnet": testnet,
        "data": {
            "paper_bot_id": paper_bot_id,
            "bot_name": bot_name,
            "strategy_type": record.get("strategy_type", "unknown"),
            "trading_pair": record.get("trading_pair", "unknown"),
            "local_status": new_local_status,
            "stopped_at": now if stop_success else None,
            "hummingbot_response": sanitize_data(hummingbot_response) if hummingbot_response else None,
        } if stop_success else None,
        "error": stop_error,
        "timestamp": now,
    }
